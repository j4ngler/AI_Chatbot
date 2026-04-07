from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import joblib
import numpy as np
from pathlib import Path

ROOT_FOR_IMPORT = Path(__file__).resolve().parents[1]
if str(ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(ROOT_FOR_IMPORT))

from tools.chat_router import route_smalltalk
from tools.llm_clients import ask_llm_ollama, reflect_answer_grounded
from tools.retrieval_hybrid import (
    hybrid_retrieve,
    load_dense_matrix,
    tfidf_only_retrieve,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

# override=True: giá trị trong .env luôn được áp dụng khi chạy local (tránh biến COSING_ENABLED rỗng trong Windows vẫn “thắng” file .env).
load_dotenv(PROJECT_ROOT / ".env", override=True)


def _env_flag(name: str, default: str = "") -> bool:
    v = (os.getenv(name, default) or "").strip().strip('"').strip("'").lower()
    return v in ("1", "true", "yes", "on")

app = FastAPI(title="Chatbot RAG Demo (file-based)", version="0.3")

_COSING_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cosing")
_cosing_service = None
_cosing_lock = threading.Lock()

_cors = os.getenv("CORS_ALLOW_ORIGINS", "*").strip()
_origins = [o.strip() for o in _cors.split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


_favicon_svg = PROJECT_ROOT / "demo_web" / "favicon.svg"
# GIF 1×1 trong suốt — không phụ thuộc file trên đĩa; tránh 404 khi thiếu favicon.svg hoặc Mount static.
_FAVICON_ICO_BODY = base64.b64decode(
    "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)


@app.api_route("/favicon.ico", methods=["GET", "HEAD"], include_in_schema=False)
def favicon_ico() -> Response:
    """Trình duyệt (Cốc Cốc, Chrome, …) gọi /favicon.ico — luôn 200, không 404."""
    if _favicon_svg.is_file():
        return FileResponse(_favicon_svg, media_type="image/svg+xml")
    return Response(content=_FAVICON_ICO_BODY, media_type="image/gif")


class ChatRequest(BaseModel):
    question: str
    top_k: int | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[str]
    sources: list[dict[str, Any]]


class CosingLookupRequest(BaseModel):
    """Contract giống spec CoSIng (tra cứu EU)."""

    query: str
    query_type: str = "NAME_OR_INCI"
    request_id: str | None = None


def _get_cosing_service() -> Any:
    global _cosing_service
    with _cosing_lock:
        if _cosing_service is None:
            from tools.cosing_adapter.cache_store import ChemicalCacheStore
            from tools.cosing_adapter.chemical_lookup_service import ChemicalLookupService
            from tools.cosing_adapter.cosing_worker_selenium import CosingSeleniumWorker, WorkerConfig

            cache_dir = PROJECT_ROOT / os.getenv("COSING_CACHE_DIR", "data/cache/cosing")
            # Giống CLI: --no-headless => COSING_HEADLESS=false (mở cửa sổ trình duyệt để xem Selenium).
            headless = _env_flag("COSING_HEADLESS", "true")
            enrich_detail = _env_flag("COSING_ENRICH_DETAIL", "true")
            browser = os.getenv("COSING_BROWSER", "chrome").strip().lower()
            if browser not in ("chrome", "edge"):
                browser = "chrome"
            artifacts = PROJECT_ROOT / "data/artifacts/cosing"
            worker = CosingSeleniumWorker(
                WorkerConfig(
                    headless=headless,
                    browser=browser,
                    artifacts_dir=artifacts,
                    enrich_detail=enrich_detail,
                )
            )
            store = ChemicalCacheStore(cache_dir=cache_dir, ttl_hours=24)
            _cosing_service = ChemicalLookupService(cache_store=store, worker=worker)
        return _cosing_service


def _cosing_lookup_sync(payload: dict[str, Any]) -> Any:
    return _get_cosing_service().lookup_payload(payload)


@app.post("/api/cosing/lookup")
async def cosing_lookup(req: CosingLookupRequest) -> dict[str, Any]:
    """
    Tra cứu hóa chất EU CoSIng (Selenium + cache). Có thể mất 30–120 giây.
    Bật: COSING_ENABLED=true; cần Chrome hoặc Edge trên máy chạy API.
    """
    if not _env_flag("COSING_ENABLED"):
        raise HTTPException(
            status_code=503,
            detail="API CoSIng đang tắt. Đặt COSING_ENABLED=true trong .env ở thư mục gốc dự án (cùng cấp với api/), khởi động lại uvicorn, và cài Chrome/Edge cho Selenium.",
        )
    if req.query_type != "NAME_OR_INCI":
        raise HTTPException(status_code=422, detail="query_type chỉ hỗ trợ NAME_OR_INCI.")
    rid = (req.request_id or "").strip() or f"web-{uuid.uuid4().hex[:12]}"
    payload: dict[str, Any] = {
        "query": req.query.strip(),
        "query_type": req.query_type,
        "request_id": rid,
    }
    loop = asyncio.get_event_loop()
    try:
        out = await loop.run_in_executor(_COSING_EXECUTOR, _cosing_lookup_sync, payload)
        return out.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CoSIng: {e!s}") from e


_vectorizer = None
_tfidf_matrix = None
_metas: list[dict[str, Any]] | None = None
_dense_matrix: np.ndarray | None = None
_st_model: Any = None
_use_hybrid: bool = False
_answer_cache: dict[str, tuple[float, ChatResponse]] = {}
_answer_cache_lock = threading.Lock()

INSUFFICIENT_RETRIEVAL = (
    "Không đủ căn cứ trong các văn bản đã index để trả lời chính xác câu hỏi này."
)
INSUFFICIENT_REFLECTION = "Không đủ dữ liệu trong các văn bản đã cung cấp."


def build_context(chunks: list[dict], limit_chars_per_chunk: int = 1800) -> tuple[str, list[str]]:
    citations: list[str] = []
    parts: list[str] = []
    for i, c in enumerate(chunks):
        meta = c["metadata"] or {}
        law_number = meta.get("law_number", "")
        article_ref = meta.get("article_ref", "")
        citation = f"[{law_number} - {article_ref}]".strip()
        citations.append(citation)

        text = c["document"] or ""
        if len(text) > limit_chars_per_chunk:
            text = text[:limit_chars_per_chunk] + "..."

        parts.append(f"SOURCE_{i+1} {citation}\n{text}")
    return "\n\n".join(parts), citations


def _is_true(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _normalize_question(q: str) -> str:
    q = q.strip().lower()
    q = re.sub(r"\s+", " ", q)
    return q


def _cache_get(key: str) -> ChatResponse | None:
    ttl = int(os.getenv("ANSWER_CACHE_TTL_SECONDS", "300"))
    if ttl <= 0:
        return None
    now = time.time()
    with _answer_cache_lock:
        hit = _answer_cache.get(key)
        if not hit:
            return None
        exp, val = hit
        if exp < now:
            _answer_cache.pop(key, None)
            return None
        return val


def _cache_set(key: str, val: ChatResponse) -> None:
    ttl = int(os.getenv("ANSWER_CACHE_TTL_SECONDS", "300"))
    max_items = int(os.getenv("ANSWER_CACHE_MAX_ITEMS", "300"))
    if ttl <= 0 or max_items <= 0:
        return
    now = time.time()
    with _answer_cache_lock:
        if len(_answer_cache) >= max_items:
            # Simple eviction: remove expired first, else oldest by insertion.
            expired = [k for k, (exp, _) in _answer_cache.items() if exp < now]
            for k in expired:
                _answer_cache.pop(k, None)
            if len(_answer_cache) >= max_items:
                first_key = next(iter(_answer_cache))
                _answer_cache.pop(first_key, None)
        _answer_cache[key] = (now + ttl, val)


def _adaptive_params(question: str, requested_top_k: int, base_retrieve_k: int) -> tuple[int, int]:
    # Keep high precision for complex questions, reduce work for simple/short ones.
    if not _is_true("FAST_ACCURATE_MODE", "true"):
        return base_retrieve_k, requested_top_k

    q = question.strip()
    words = len(q.split())
    simple = words <= 9 and len(q) <= 90 and not any(tok in q for tok in (";", " và ", " hoặc ", " so sánh ", "trường hợp"))
    if simple:
        retrieve_k = max(8, min(base_retrieve_k, 12))
        top_k = min(requested_top_k, 2 if words <= 5 else 3)
        return retrieve_k, max(1, top_k)
    return base_retrieve_k, requested_top_k


def _extract_keywords(question: str) -> list[str]:
    stop = {
        "là",
        "và",
        "hoặc",
        "của",
        "cho",
        "theo",
        "thế",
        "nào",
        "bao",
        "nhiêu",
        "được",
        "không",
        "khi",
        "với",
        "trong",
        "các",
        "những",
    }
    tokens = re.findall(r"[0-9A-Za-zÀ-ỹ_]+", question.lower())
    kws = [t for t in tokens if len(t) >= 3 and t not in stop]
    uniq: list[str] = []
    for t in kws:
        if t not in uniq:
            uniq.append(t)
    return uniq[:10]


def _compress_chunk_text(text: str, keywords: list[str], max_chars: int) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    if not keywords:
        return t[:max_chars] + "..."
    sentences = re.split(r"(?<=[\.\!\?;\n])\s+", t)
    picked: list[str] = []
    for s in sentences:
        sl = s.lower()
        if any(k in sl for k in keywords):
            picked.append(s.strip())
    if not picked:
        return t[:max_chars] + "..."
    merged = " ".join(p for p in picked if p)
    if len(merged) > max_chars:
        merged = merged[:max_chars] + "..."
    return merged


def build_context_smart(
    question: str,
    chunks: list[dict],
    limit_chars_per_chunk: int = 1400,
    max_total_chars: int = 4500,
) -> tuple[str, list[str]]:
    if not _is_true("FAST_ACCURATE_MODE", "true"):
        return build_context(chunks, limit_chars_per_chunk=1800)

    keywords = _extract_keywords(question)
    citations: list[str] = []
    parts: list[str] = []
    total = 0
    for i, c in enumerate(chunks):
        meta = c["metadata"] or {}
        law_number = meta.get("law_number", "")
        article_ref = meta.get("article_ref", "")
        citation = f"[{law_number} - {article_ref}]".strip()
        citations.append(citation)
        text = _compress_chunk_text(c.get("document", "") or "", keywords, limit_chars_per_chunk)
        part = f"SOURCE_{i+1} {citation}\n{text}"
        if total + len(part) > max_total_chars:
            break
        parts.append(part)
        total += len(part) + 2
    if not parts:
        return build_context(chunks, limit_chars_per_chunk=1200)
    return "\n\n".join(parts), citations


def _encode_query_fn(q: str) -> np.ndarray:
    assert _st_model is not None
    v = _st_model.encode([q], convert_to_numpy=True, normalize_embeddings=True)[0]
    return v.astype(np.float32)


@app.on_event("startup")
def startup() -> None:
    global _vectorizer, _tfidf_matrix, _metas, _dense_matrix, _st_model, _use_hybrid

    persist_dir = PROJECT_ROOT / os.getenv("VECTOR_STORE_DIR", "data/vector_db/file_based_demo")
    vectorizer_path = persist_dir / os.getenv("TFIDF_VECTORIZER_FILENAME", "vectorizer.joblib")
    matrix_path = persist_dir / os.getenv("TFIDF_MATRIX_FILENAME", "tfidf_matrix.joblib")
    metas_path = persist_dir / os.getenv("METAS_FILENAME", "metadatas.jsonl")

    if not vectorizer_path.exists() or not matrix_path.exists() or not metas_path.exists():
        raise RuntimeError(
            f"Thiếu vector store tại {persist_dir}. Hãy chạy build_embeddings_file_based.py trước."
        )

    _vectorizer = joblib.load(vectorizer_path)
    _tfidf_matrix = joblib.load(matrix_path)
    metas: list[dict[str, Any]] = []
    with metas_path.open("r", encoding="utf-8") as f:
        for line in f:
            metas.append(json.loads(line))
    _metas = metas
    if len(_metas) != int(_tfidf_matrix.shape[0]):
        raise RuntimeError("Vector store bị lệch metadata.")

    mode = os.getenv("RAG_MODE", "").strip().lower()
    dm = load_dense_matrix(persist_dir, len(_metas))
    if mode == "hybrid":
        _use_hybrid = dm is not None
    elif mode == "tfidf":
        _use_hybrid = False
    else:
        _use_hybrid = dm is not None

    _dense_matrix = dm if _use_hybrid else None
    if _use_hybrid:
        from sentence_transformers import SentenceTransformer

        model_name = os.getenv("DENSE_MODEL_NAME", "paraphrase-multilingual-MiniLM-L12-v2")
        _st_model = SentenceTransformer(model_name)


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    global _tfidf_matrix, _vectorizer, _metas

    if not req.question.strip():
        return ChatResponse(answer="Câu hỏi trống.", citations=[], sources=[])

    if os.getenv("ROUTER_ENABLED", "true").lower() in ("1", "true", "yes"):
        routed = route_smalltalk(req.question)
        if routed is not None:
            return ChatResponse(answer=routed, citations=[], sources=[])

    top_k = int(req.top_k or int(os.getenv("TOP_K_DEFAULT", "3")))
    if top_k < 1:
        top_k = 1
    retrieve_k = int(os.getenv("RETRIEVE_K", "20"))
    alpha = float(os.getenv("HYBRID_ALPHA", "0.5"))
    min_raw = os.getenv("MIN_RETRIEVAL_SCORE", "").strip()
    min_score = float(min_raw) if min_raw else None

    assert _vectorizer is not None and _tfidf_matrix is not None and _metas is not None

    pipeline_version = "legacy" if _is_true("FAST_ACCURATE_MODE", "true") is False else "fast-accurate-v1"
    cache_key = f"{pipeline_version}|{_normalize_question(req.question)}|tk={top_k}"
    if _is_true("ANSWER_CACHE_ENABLED", "true"):
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    retrieve_k, top_k = _adaptive_params(req.question, top_k, retrieve_k)

    if _use_hybrid and _dense_matrix is not None and _st_model is not None:
        retrieved_metas, _scores, low_conf, _best = hybrid_retrieve(
            req.question,
            _vectorizer,
            _tfidf_matrix,
            _metas,
            dense_matrix=_dense_matrix,
            encode_query=_encode_query_fn,
            retrieve_k=retrieve_k,
            top_k=top_k,
            alpha=alpha,
            min_score=min_score,
        )
    else:
        retrieved_metas, _scores, low_conf, _best = tfidf_only_retrieve(
            req.question,
            _vectorizer,
            _tfidf_matrix,
            _metas,
            retrieve_k=retrieve_k,
            top_k=top_k,
            min_score=min_score,
        )

    if low_conf:
        return ChatResponse(answer=INSUFFICIENT_RETRIEVAL, citations=[], sources=[])

    retrieved_wrapped = []
    for m in retrieved_metas:
        retrieved_wrapped.append({"document": m.get("chunk_text", ""), "metadata": m})

    context, citations = build_context_smart(req.question, retrieved_wrapped)
    ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct")

    system_prompt = (
        "Bạn là trợ lý pháp lý Việt Nam. Trả lời CỰC KỲ NGẮN GỌN, đúng trọng tâm, "
        "CHỈ dựa trên context hệ thống cung cấp. "
        "Toàn bộ nội dung trả lời phải là tiếng Việt chuẩn; "
        "không dùng tiếng Trung, tiếng Anh hay ngôn ngữ khác (trừ khi trích nguyên văn từ context). "
        "Nếu context không đủ, nói đúng một câu: \"Không đủ dữ liệu trong các văn bản đã cung cấp.\""
    )
    user_prompt = (
        f"Câu hỏi: {req.question}\n\n"
        f"Context (các nguồn được gắn nhãn):\n{context}\n\n"
        "Hãy trả lời hoàn toàn bằng tiếng Việt, một đoạn ngắn."
    )

    answer = None
    try:
        answer = ask_llm_ollama(ollama_base, ollama_model, system_prompt, user_prompt)
    except Exception as e:
        print(f"[WARN] Ollama error: {e!r}")
        preview = "\n\n".join(
            [r.get("metadata", {}).get("chunk_text", "")[:1200] for r in retrieved_wrapped[:top_k]]
        )
        if not preview:
            preview = context[:5000]
        answer = (
            "Không gọi được Ollama. "
            "Dưới đây là trích dẫn từ các đoạn context liên quan:\n\n"
            + preview
        )

    if (
        answer
        and os.getenv("REFLECTION_ENABLED", "").lower() in ("1", "true", "yes")
        and not answer.startswith("Không gọi được")
    ):
        ok = reflect_answer_grounded(
            context,
            answer,
            ollama_base=ollama_base,
            ollama_model=ollama_model,
        )
        if not ok:
            answer = INSUFFICIENT_REFLECTION

    sources = []
    for r in retrieved_wrapped:
        sources.append(
            {
                "law_number": (r["metadata"] or {}).get("law_number"),
                "article_ref": (r["metadata"] or {}).get("article_ref"),
            }
        )

    resp = ChatResponse(answer=answer or INSUFFICIENT_REFLECTION, citations=citations, sources=sources)
    if _is_true("ANSWER_CACHE_ENABLED", "true"):
        _cache_set(cache_key, resp)
    return resp


_demo_dir = PROJECT_ROOT / "demo_web"
if _demo_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_demo_dir), html=True), name="demo")
