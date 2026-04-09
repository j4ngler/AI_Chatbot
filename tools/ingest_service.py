"""Upload PDF/ảnh → text → chờ duyệt → ghi chunk + rebuild index."""
from __future__ import annotations

import io
import json
import re
import uuid
from pathlib import Path
from typing import Any, Callable

from tools.build_dense_embeddings import rebuild_dense_vector_store
from tools.build_embeddings_file_based import rebuild_tfidf_vector_store


def _normalize_ws(s: str) -> str:
    s = s.replace("\x00", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _split_if_too_long(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for para in paras:
        if not buf:
            buf = para
            continue
        if len(buf) + 2 + len(para) <= max_chars:
            buf = buf + "\n\n" + para
        else:
            chunks.append(buf)
            buf = para
    if buf:
        chunks.append(buf)
    out: list[str] = []
    for c in chunks:
        if len(c) <= max_chars:
            out.append(c)
        else:
            for i in range(0, len(c), max_chars):
                out.append(c[i : i + max_chars])
    return out


def extract_text_from_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    for page in reader.pages:
        t = page.extract_text() or ""
        if t.strip():
            parts.append(t)
    return _normalize_ws("\n\n".join(parts))


def extract_text_from_image(data: bytes) -> tuple[str, bool]:
    try:
        from PIL import Image
        import pytesseract
    except ImportError as e:
        raise RuntimeError(
            "OCR cần cài pillow và pytesseract, và Tesseract OCR trên hệ thống. " + str(e)
        ) from e
    img = Image.open(io.BytesIO(data))
    text = pytesseract.image_to_string(img, lang="vie+eng") or ""
    return _normalize_ws(text), True


class IngestStore:
    def __init__(self, project_root: Path, *, pending_dir: str | None = None) -> None:
        import os

        rel = pending_dir or os.getenv("INGEST_PENDING_DIR", "data/ingest_pending")
        self.root = project_root
        self.pending_path = project_root / rel
        self.chunks_dir = project_root / "data" / "processed" / "chunks"
        self.pending_path.mkdir(parents=True, exist_ok=True)
        self.chunks_dir.mkdir(parents=True, exist_ok=True)

    def _record_path(self, rid: str) -> Path:
        return self.pending_path / f"{rid}.json"

    def create_pending(
        self,
        *,
        filename: str,
        raw_bytes: bytes,
        business_group: str,
        title: str | None,
    ) -> dict[str, Any]:
        import os

        max_b = int(os.getenv("INGEST_MAX_UPLOAD_BYTES", str(15 * 1024 * 1024)))
        max_b = max(1024, min(max_b, 30 * 1024 * 1024))
        if len(raw_bytes) > max_b:
            raise ValueError(f"File vượt quá {max_b} byte.")
        fn = (filename or "upload").lower()
        ocr_used = False
        if fn.endswith(".pdf"):
            text = extract_text_from_pdf(raw_bytes)
        elif fn.endswith((".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp")):
            text, ocr_used = extract_text_from_image(raw_bytes)
        else:
            raise ValueError("Chỉ hỗ trợ .pdf hoặc ảnh (.png, .jpg, .jpeg, .webp, …).")
        if not text or len(text) < 20:
            raise ValueError("Không trích được đủ văn bản (file rỗng, scan kém, hoặc PDF không có lớp text).")
        rid = uuid.uuid4().hex[:16]
        bg = (business_group or "general").strip() or "general"
        ttl = (title or filename or "Tài liệu tải lên").strip()[:500]
        rec = {
            "id": rid,
            "filename": filename,
            "title": ttl,
            "business_group": bg,
            "status": "pending",
            "extracted_text": text[:500_000],
            "ocr_used": ocr_used,
            "error": None,
        }
        self._record_path(rid).write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        return {k: v for k, v in rec.items() if k != "extracted_text"}

    def get(self, rid: str) -> dict[str, Any] | None:
        p = self._record_path(rid)
        if not p.is_file():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def list_pending(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for p in sorted(self.pending_path.glob("*.json")):
            try:
                r = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if r.get("status") == "pending":
                out.append({k: v for k, v in r.items() if k != "extracted_text"})
        return out

    def reject(self, rid: str) -> bool:
        r = self.get(rid)
        if not r or r.get("status") != "pending":
            return False
        r["status"] = "rejected"
        self._record_path(rid).write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
        return True

    def approve(
        self,
        rid: str,
        *,
        max_chars: int = 2200,
        rebuild_index: bool = True,
        on_rebuilt: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        r = self.get(rid)
        if not r or r.get("status") != "pending":
            raise ValueError("Bản ghi không ở trạng thái chờ duyệt.")
        text = str(r.get("extracted_text") or "")
        doc_id = f"ingest_{rid}"
        title = str(r.get("title") or "Upload")
        bg = str(r.get("business_group") or "general")
        law_number = "UPLOAD"
        pieces = _split_if_too_long(_normalize_ws(text), max_chars=max_chars)
        chunk_path = self.chunks_dir / f"{doc_id}.jsonl"
        if chunk_path.exists():
            chunk_path.unlink()
        with chunk_path.open("w", encoding="utf-8") as f:
            for i, piece in enumerate(pieces):
                cid = f"{doc_id}_s{i}"
                row = {
                    "chunk_id": cid,
                    "doc_id": doc_id,
                    "law_number": law_number,
                    "title": title,
                    "article_ref": f"Đoạn {i + 1}",
                    "page_start": None,
                    "page_end": None,
                    "chunk_text": piece,
                    "business_group": bg,
                }
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        r["status"] = "approved"
        r["doc_id"] = doc_id
        r["chunks_file"] = str(chunk_path.relative_to(self.root))
        r.pop("extracted_text", None)
        self._record_path(rid).write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
        if rebuild_index:
            rebuild_tfidf_vector_store(project_root=self.root)
            rebuild_dense_vector_store(project_root=self.root)
            if on_rebuilt:
                on_rebuilt()
        return r
