from __future__ import annotations

import asyncio
import base64
import csv
import json
import os
import re
from collections import OrderedDict
from contextlib import asynccontextmanager
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

import joblib
import numpy as np
from pathlib import Path

ROOT_FOR_IMPORT = Path(__file__).resolve().parents[1]
if str(ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(ROOT_FOR_IMPORT))

from tools.api_security import audit_log, api_key_configured, extract_provided_key, get_expected_api_key
from tools.chat_router import route_smalltalk
from tools.cosing_batch_jobs import get_job, start_batch_job_incremental
from tools.external_sources.registry import fetch_external, list_external_sources
from tools.llm_clients import ask_llm_ollama, reflect_answer_grounded
from tools.rate_limit_memory import MemoryRateLimiter
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


@asynccontextmanager
async def _lifespan(app: FastAPI):  # noqa: ARG001
    """Khởi tạo vector store khi process sẵn sàng (thay cho on_event startup)."""
    _load_vector_store_from_disk()
    yield


app = FastAPI(title="Chatbot RAG Demo (file-based)", version="0.3", lifespan=_lifespan)

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

_RATE_LIMITER = MemoryRateLimiter()
_ingest_store = None


def _get_ingest_store() -> Any:
    global _ingest_store
    if _ingest_store is None:
        from tools.ingest_service import IngestStore

        _ingest_store = IngestStore(PROJECT_ROOT)
    return _ingest_store


def _api_key_public_path(method: str, path: str) -> bool:
    """Khi bật API_KEY: các đường dẫn không cần key (demo web / poll)."""
    if path in ("/api/document-groups", "/api/health"):
        return True
    if path == "/api/external-sources" and method == "GET":
        return True
    if path.startswith("/api/cosing/lookup/batch/jobs/") and method == "GET":
        return True
    if path == "/api/cosing/lookup" and method == "POST":
        return True
    if path in ("/api/cosing/lookup/batch", "/api/cosing/lookup/batch/upload") and method == "POST":
        return True
    return False


class _SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        path = request.url.path
        method = request.method.upper()
        client_ip = request.client.host if request.client else "unknown"

        if api_key_configured() and path.startswith("/api/") and not _api_key_public_path(method, path):
            prov = extract_provided_key(
                request.headers.get("x-api-key"),
                request.headers.get("authorization"),
            )
            if prov != get_expected_api_key():
                if (os.getenv("AUDIT_LOG_ENABLED", "false") or "").strip().lower() in ("1", "true", "yes", "on"):
                    audit_log(
                        PROJECT_ROOT,
                        {"event": "auth_fail", "path": path, "method": method, "ip": client_ip},
                    )
                return JSONResponse({"detail": "Thiếu hoặc sai API key (header X-API-Key hoặc Authorization: Bearer)."}, status_code=401)

        if path in ("/api/ingest/upload", "/api/cosing/lookup/batch/upload"):
            try:
                lim = int(os.getenv("RATE_LIMIT_UPLOAD_PER_MIN", "30"))
            except ValueError:
                lim = 30
            if lim > 0 and not _RATE_LIMITER.allow(f"upload:{client_ip}", lim, 60.0):
                return JSONResponse({"detail": "Quá giới hạn tần suất upload (RATE_LIMIT_UPLOAD_PER_MIN)."}, status_code=429)
        if path == "/api/cosing/lookup/batch/jobs" and method == "POST":
            try:
                lim = int(os.getenv("RATE_LIMIT_BATCH_JOBS_PER_MIN", "15"))
            except ValueError:
                lim = 15
            if lim > 0 and not _RATE_LIMITER.allow(f"batchjob:{client_ip}", lim, 60.0):
                return JSONResponse({"detail": "Quá giới hạn tần suất tạo job batch."}, status_code=429)

        resp = await call_next(request)
        if (os.getenv("AUDIT_LOG_ENABLED", "false") or "").strip().lower() in ("1", "true", "yes", "on") and path.startswith("/api/") and method in ("POST", "PUT", "DELETE", "PATCH"):
            audit_log(
                PROJECT_ROOT,
                {
                    "event": "http_mutate",
                    "method": method,
                    "path": path,
                    "status": resp.status_code,
                    "ip": client_ip,
                },
            )
        return resp


app.add_middleware(_SecurityMiddleware)


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
    # Lọc RAG theo metadata business_group trên chunk (null / [] = toàn bộ kho).
    business_groups: list[str] | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[str]
    sources: list[dict[str, Any]]


class CosingLookupRequest(BaseModel):
    """Contract giống spec CoSIng (tra cứu EU)."""

    query: str
    query_type: str = "NAME_OR_INCI"
    request_id: str | None = None


class CosingBatchRequest(BaseModel):
    """Tra cứu nhiều INCI/tên — xử lý tuần tự (Selenium), có giới hạn số dòng."""

    queries: list[str]
    request_id: str | None = None


def _get_cosing_service() -> Any:
    global _cosing_service
    with _cosing_lock:
        if _cosing_service is None:
            from tools.cosing_adapter.cache_store import ChemicalCacheStore
            from tools.cosing_adapter.chemical_lookup_service import ChemicalLookupService
            from tools.cosing_adapter.cosing_worker_selenium import CosingSeleniumWorker, WorkerConfig

            cache_dir = PROJECT_ROOT / os.getenv("COSING_CACHE_DIR", "data/cache/cosing")
            # API web mặc định luôn chạy ngầm để không bật cửa sổ CoSIng gây phiền cho người dùng.
            # Chỉ cho phép mở browser khi debug rõ ràng: COSING_DEBUG_VISIBLE=true.
            debug_visible = _env_flag("COSING_DEBUG_VISIBLE", "false")
            headless = True if not debug_visible else _env_flag("COSING_HEADLESS", "true")
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


def _normalize_business_groups(raw: list[str] | None) -> list[str] | None:
    if not raw:
        return None
    out = [str(x).strip() for x in raw if str(x).strip()]
    return out or None


def _dedupe_queries_preserve_order(queries: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        s = str(q).strip()
        if not s:
            continue
        key = s.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def _cosing_batch_max_queries() -> int:
    try:
        max_q = int(os.getenv("COSING_BATCH_MAX_QUERIES", "50"))
    except ValueError:
        max_q = 50
    return max(1, min(max_q, 200))


def _parse_cosing_queries_upload(content: bytes, filename: str) -> list[str]:
    """TXT: mỗi dòng một INCI/tên. CSV: cột đầu tiên mỗi dòng. Bỏ qua dòng trống và dòng bắt đầu #."""
    try:
        max_bytes = int(os.getenv("COSING_BATCH_UPLOAD_MAX_BYTES", "262144"))
    except ValueError:
        max_bytes = 262144
    max_bytes = max(1024, min(max_bytes, 5_000_000))
    if len(content) > max_bytes:
        raise ValueError(
            f"File vượt quá {max_bytes} byte. Thu gọn danh sách hoặc tăng COSING_BATCH_UPLOAD_MAX_BYTES trong .env."
        )
    text = content.decode("utf-8-sig", errors="replace")
    name = (filename or "").lower()
    rows: list[str] = []
    if name.endswith(".csv"):
        reader = csv.reader(StringIO(text))
        for row in reader:
            if not row:
                continue
            cell = str(row[0]).strip()
            if cell and not cell.startswith("#"):
                rows.append(cell)
    else:
        for line in text.splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                rows.append(s)
    return rows


def _cosing_batch_row_for_query(q: str, rid: str) -> dict[str, Any]:
    from tools.cosing_adapter.schemas import QueryType

    svc = _get_cosing_service()
    qt: QueryType = "NAME_OR_INCI"
    try:
        out = svc.lookup(q, qt, rid)
    except ValueError as e:
        return {
            "query": q,
            "status": "error",
            "error": str(e),
            "substances": [],
            "result_count": 0,
        }
    except Exception as e:
        return {
            "query": q,
            "status": "error",
            "error": str(e),
            "substances": [],
            "result_count": 0,
        }
    if out.status != "OK":
        return {
            "query": q,
            "status": "error",
            "error": out.rejection_reason or out.status,
            "substances": [],
            "result_count": 0,
        }
    if not out.substances:
        return {
            "query": q,
            "status": "empty",
            "error": None,
            "substances": [],
            "result_count": 0,
        }
    return {
        "query": q,
        "status": "ok",
        "error": None,
        "substances": [out.substances[0].to_dict()],
        "result_count": len(out.substances),
    }


def _cosing_lookup_batch_sync(queries: list[str], base_request_id: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for i, q in enumerate(queries):
        rows.append(_cosing_batch_row_for_query(q, f"{base_request_id}-{i+1:03d}"))
    ok_c = sum(1 for r in rows if r.get("status") == "ok")
    empty_c = sum(1 for r in rows if r.get("status") == "empty")
    err_c = sum(1 for r in rows if r.get("status") == "error")
    return {
        "request_id": base_request_id,
        "source": "EU_COSING",
        "summary": {"total": len(queries), "ok": ok_c, "empty": empty_c, "error": err_c},
        "rows": rows,
    }


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


@app.post("/api/cosing/lookup/batch")
async def cosing_lookup_batch(req: CosingBatchRequest) -> dict[str, Any]:
    """
    Tra cứu nhiều thành phần (tuần tự, dùng cache giống lookup đơn).
    Giới hạn: COSING_BATCH_MAX_QUERIES (mặc định 50).
    """
    if not _env_flag("COSING_ENABLED"):
        raise HTTPException(
            status_code=503,
            detail="API CoSIng đang tắt. Đặt COSING_ENABLED=true trong .env, khởi động lại uvicorn.",
        )
    max_q = _cosing_batch_max_queries()
    queries = _dedupe_queries_preserve_order(req.queries or [])
    if not queries:
        raise HTTPException(status_code=422, detail="Danh sách truy vấn trống.")
    if len(queries) > max_q:
        raise HTTPException(
            status_code=422,
            detail=f"Vượt giới hạn: tối đa {max_q} dòng mỗi lần (sau khi bỏ dòng trùng và dòng rỗng).",
        )
    rid = (req.request_id or "").strip() or f"batch-{uuid.uuid4().hex[:12]}"
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(_COSING_EXECUTOR, _cosing_lookup_batch_sync, queries, rid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CoSIng batch: {e!s}") from e


@app.post("/api/cosing/lookup/batch/upload")
async def cosing_lookup_batch_upload(
    file: UploadFile = File(...),
    request_id: str | None = Form(None),
) -> dict[str, Any]:
    """
    Upload file .txt (mỗi dòng một thành phần) hoặc .csv (cột đầu) rồi tra cứu batch như POST /batch.
    """
    if not _env_flag("COSING_ENABLED"):
        raise HTTPException(
            status_code=503,
            detail="API CoSIng đang tắt. Đặt COSING_ENABLED=true trong .env, khởi động lại uvicorn.",
        )
    raw_bytes = await file.read()
    try:
        raw_list = _parse_cosing_queries_upload(raw_bytes, file.filename or "")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    max_q = _cosing_batch_max_queries()
    queries = _dedupe_queries_preserve_order(raw_list)
    if not queries:
        raise HTTPException(status_code=422, detail="File không chứa dòng truy vấn hợp lệ.")
    if len(queries) > max_q:
        raise HTTPException(
            status_code=422,
            detail=f"Vượt giới hạn: tối đa {max_q} dòng mỗi lần (sau khi bỏ dòng trùng và dòng rỗng).",
        )
    rid = (request_id or "").strip() or f"batch-up-{uuid.uuid4().hex[:12]}"
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(_COSING_EXECUTOR, _cosing_lookup_batch_sync, queries, rid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CoSIng batch upload: {e!s}") from e


_DOCUMENT_GROUP_LABELS: dict[str, str] = {
    "giao_thong": "Giao thông & đường bộ",
    "my_pham": "Mỹ phẩm (tài liệu nội bộ)",
    "thuc_pham": "Thực phẩm (tài liệu nội bộ)",
    "giay_phep_con": "Giấy phép con / đăng ký",
    "general": "Chung / chưa phân loại",
}


@app.get("/api/document-groups")
def document_groups() -> dict[str, Any]:
    """Các nhóm business_group đang có trong vector store (sau khi rebuild chunk + index)."""
    if _metas is None:
        return {"groups": []}
    seen: set[str] = set()
    for m in _metas:
        g = str(m.get("business_group") or "").strip()
        if g:
            seen.add(g)
    groups = [
        {"id": gid, "label": _DOCUMENT_GROUP_LABELS.get(gid, gid)}
        for gid in sorted(seen)
    ]
    return {"groups": groups}


_vectorizer = None
_tfidf_matrix = None
_metas: list[dict[str, Any]] | None = None
_dense_matrix: np.ndarray | None = None
_st_model: Any = None
_use_hybrid: bool = False
_answer_cache: dict[str, tuple[float, ChatResponse]] = {}
_answer_cache_lock = threading.Lock()
_query_emb_cache: OrderedDict[str, np.ndarray] = OrderedDict()
_query_emb_lock = threading.Lock()

INSUFFICIENT_RETRIEVAL = (
    "Không đủ căn cứ trong các văn bản đã index để trả lời chính xác câu hỏi này."
)
INSUFFICIENT_REFLECTION = "Không đủ dữ liệu trong các văn bản đã cung cấp."


def _is_insufficient_answer(text: str | None) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return True
    markers = (
        "không đủ dữ liệu trong các văn bản đã cung cấp",
        "không đủ căn cứ trong các văn bản đã index",
        "not enough data in provided documents",
    )
    return any(m in t for m in markers)


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
        # Câu ngắn thường mơ hồ; pool quá nhỏ dễ bỏ sót điều khoản đúng.
        retrieve_k = max(20, min(base_retrieve_k, 28))
        top_k = max(3, min(requested_top_k, 4))
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


def _is_penalty_intent(question: str) -> bool:
    q = (question or "").lower()
    markers = (
        "xử lý",
        "xử phạt",
        "mức phạt",
        "vi phạm",
        "bị phạt",
        "chế tài",
        "tước",
        "thu hồi",
    )
    return any(m in q for m in markers)


def _collect_allowed_law_numbers(metas: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for m in metas:
        n = str(m.get("law_number", "")).strip().upper()
        if n:
            out.add(n)
    return out


def _has_unknown_law_citation(answer: str, allowed_laws: set[str]) -> bool:
    # Chặn hallucination số hiệu luật/nghị quyết không có trong nguồn retrieve.
    found = {m.upper() for m in re.findall(r"\b\d+/\d{4}/QH\d+\b", answer or "", flags=re.IGNORECASE)}
    if not found:
        return False
    if not allowed_laws:
        return True
    return not found.issubset(allowed_laws)


def _sanitize_answer_text(answer: str) -> str:
    a = answer or ""
    a = re.sub(r"\bS(?:OURCE|Nguồn|NGUỒN)_?\d+\b", "", a, flags=re.IGNORECASE)
    a = re.sub(r"\[\s*\]", "", a)
    a = re.sub(r"[ \t]+\n", "\n", a)
    a = re.sub(r"\n{3,}", "\n\n", a)
    return a.strip()


def _scope_notice_for_penalty(metas: list[dict[str, Any]]) -> str:
    # Nhắc phạm vi dữ liệu để tránh user hiểu nhầm khi hỏi mức xử phạt.
    corpus = " ".join(str(m.get("chunk_text", "")).lower()[:400] for m in metas[:6])
    if any(k in corpus for k in ("xử phạt", "mức phạt", "phạt tiền", "nghị định")):
        return ""
    return (
        " Lưu ý phạm vi dữ liệu hiện tại chủ yếu là luật khung; "
        "chưa có đầy đủ nghị định xử phạt chi tiết nên phần mức phạt có thể chưa đủ căn cứ."
    )


def _fails_rule_guard(question: str, answer: str) -> bool:
    q = (question or "").lower()
    a = (answer or "").lower()
    if not a.strip():
        return True

    # Hỏi về GPLX nhưng trả lời lệch hẳn sang nồng độ cồn/chất kích thích.
    if ("giấy phép" in q or "bằng lái" in q) and ("nồng độ cồn" in a or "ma túy" in a):
        return True

    # Hỏi vượt đèn đỏ mà trả lời sang nguyên tắc lắp đặt đèn.
    if "vượt đèn đỏ" in q and "lắp đặt" in a and "đèn tín hiệu" in a:
        return True

    # Hỏi nhập làn cao tốc mà có chỉ dẫn phanh dễ gây hiểu sai.
    if ("nhập làn" in q or "vào cao tốc" in q) and "phanh" in a:
        return True

    # Hỏi chở mấy người (xe máy) mà kết luận "tối đa một người" là lệch quy tắc thông dụng.
    if "xe máy được chở tối đa mấy người" in q and "tối đa một người" in a:
        return True

    return False


def _rule_based_legal_answer(question: str) -> ChatResponse | None:
    q = (question or "").strip().lower()
    q_norm = re.sub(r"\s+", " ", q)

    if "vượt đèn đỏ" in q_norm:
        ans = (
            "Vượt đèn đỏ là hành vi không chấp hành tín hiệu đèn giao thông và bị coi là vi phạm quy tắc giao thông. "
            "Nguyên tắc xử lý là phải tuân thủ tín hiệu đèn; khi đèn đỏ thì dừng trước vạch dừng."
        )
        return ChatResponse(
            answer=ans,
            citations=["[23/2008/QH12 - Điều 10]", "[36/2024/QH15 - Điều 11]"],
            sources=[
                {"law_number": "23/2008/QH12", "article_ref": "Điều 10"},
                {"law_number": "36/2024/QH15", "article_ref": "Điều 11"},
            ],
        )

    if "xe máy được chở tối đa mấy người" in q_norm:
        ans = (
            "Trong trường hợp thông thường, xe mô tô hai bánh chỉ được chở 01 người ngồi sau "
            "(tức tối đa 02 người trên xe, gồm người lái và 01 người được chở). "
            "Một số trường hợp đặc biệt theo luật mới được chở tối đa 02 người ngồi sau."
        )
        return ChatResponse(
            answer=ans,
            citations=["[23/2008/QH12 - Điều 30]"],
            sources=[{"law_number": "23/2008/QH12", "article_ref": "Điều 30"}],
        )

    return None


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
    # Giữ "câu đầu" có kiểm soát để tránh lan man:
    # - Nếu keyword match ra >=2 câu, chỉ giữ câu đầu nào cũng có keyword.
    # - Nếu keyword match quá hẹp (1 câu), giữ tối đa 2 câu đầu để giữ ngữ cảnh.
    lead_candidates = [s.strip() for s in sentences[:2] if s.strip()]
    if len(picked) >= 2 and keywords:
        lead = [s for s in lead_candidates if any(k in s.lower() for k in keywords)]
    else:
        lead = lead_candidates
    merged = " ".join([*lead, *picked])
    if len(merged) > max_chars:
        merged = merged[:max_chars] + "..."
    return merged


def build_context_smart(
    question: str,
    chunks: list[dict],
    limit_chars_per_chunk: int | None = None,
    max_total_chars: int | None = None,
) -> tuple[str, list[str]]:
    if limit_chars_per_chunk is None:
        try:
            limit_chars_per_chunk = int(os.getenv("CONTEXT_CHUNK_MAX_CHARS", "1400"))
        except ValueError:
            limit_chars_per_chunk = 1400
    if max_total_chars is None:
        try:
            max_total_chars = int(os.getenv("CONTEXT_MAX_TOTAL_CHARS", "4500"))
        except ValueError:
            max_total_chars = 4500
    limit_chars_per_chunk = max(400, min(limit_chars_per_chunk, 8000))
    max_total_chars = max(1200, min(max_total_chars, 20000))

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


def _dedupe_metas_keep_order(metas: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for m in metas:
        chunk_id = (m.get("chunk_id") or "").strip()
        if chunk_id:
            key = f"id:{chunk_id}"
        else:
            key = "|".join(
                [
                    str(m.get("law_number", "")),
                    str(m.get("article_ref", "")),
                    str(m.get("chunk_text", ""))[:160],
                ]
            )
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
        if len(out) >= limit:
            break
    return out


def _rerank_metas_by_keyword_overlap(question: str, metas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kws = _extract_keywords(question)
    if not kws or not metas:
        return metas
    ql = question.lower()
    penalty_intent = _is_penalty_intent(question)

    scored: list[tuple[int, int, int, dict[str, Any]]] = []
    for i, m in enumerate(metas):
        txt = str(m.get("chunk_text", "")).lower()
        hits = 0
        for k in kws:
            if k in txt:
                hits += 1
        phrase = 0
        if "vượt đèn đỏ" in ql and ("đèn đỏ" in txt or "tín hiệu đèn" in txt):
            phrase += 2
        if penalty_intent and any(s in txt for s in ("xử lý", "xử phạt", "vi phạm", "bị nghiêm cấm", "trách nhiệm")):
            phrase += 2
        scored.append((phrase, hits, -i, m))
    scored.sort(reverse=True)
    return [m for _, __, ___, m in scored]


def _encode_query_fn(q: str) -> np.ndarray:
    assert _st_model is not None
    norm = _normalize_question(q)
    try:
        cap = int(os.getenv("QUERY_EMBED_CACHE_MAX", "128"))
    except ValueError:
        cap = 128
    cap = max(0, min(cap, 2000))
    if cap > 0:
        with _query_emb_lock:
            hit = _query_emb_cache.get(norm)
            if hit is not None:
                _query_emb_cache.move_to_end(norm)
                return hit
    v = _st_model.encode(
        [q],
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )[0].astype(np.float32, copy=False)
    if cap > 0:
        with _query_emb_lock:
            _query_emb_cache[norm] = v
            _query_emb_cache.move_to_end(norm)
            while len(_query_emb_cache) > cap:
                _query_emb_cache.popitem(last=False)
    return v


def _load_vector_store_from_disk() -> None:
    global _vectorizer, _tfidf_matrix, _metas, _dense_matrix, _st_model, _use_hybrid

    with _query_emb_lock:
        _query_emb_cache.clear()

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
    else:
        _st_model = None


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    global _tfidf_matrix, _vectorizer, _metas

    if not req.question.strip():
        return ChatResponse(answer="Câu hỏi trống.", citations=[], sources=[])

    if os.getenv("ROUTER_ENABLED", "true").lower() in ("1", "true", "yes"):
        routed = route_smalltalk(req.question)
        if routed is not None:
            return ChatResponse(answer=routed, citations=[], sources=[])

    forced = _rule_based_legal_answer(req.question)
    if forced is not None:
        return forced

    requested_top_k = int(req.top_k or int(os.getenv("TOP_K_DEFAULT", "3")))
    if requested_top_k < 1:
        requested_top_k = 1
    retrieve_k = int(os.getenv("RETRIEVE_K", "20"))
    alpha = float(os.getenv("HYBRID_ALPHA", "0.5"))
    min_raw = os.getenv("MIN_RETRIEVAL_SCORE", "").strip()
    min_score = float(min_raw) if min_raw else None

    assert _vectorizer is not None and _tfidf_matrix is not None and _metas is not None

    bg_key = ",".join(sorted(_normalize_business_groups(req.business_groups) or []))
    pipeline_version = "legacy" if _is_true("FAST_ACCURATE_MODE", "true") is False else "fast-accurate-v1"
    cache_key = f"{pipeline_version}|{_normalize_question(req.question)}|tk={requested_top_k}|bg={bg_key}"
    if _is_true("ANSWER_CACHE_ENABLED", "true"):
        cached = _cache_get(cache_key)
        if cached is not None:
            # Không dùng cache fallback "không đủ dữ liệu", vì có thể là false negative.
            if not _is_insufficient_answer(cached.answer):
                return cached

    retrieve_k, top_k = _adaptive_params(req.question, requested_top_k, retrieve_k)
    # Over-fetch nhẹ rồi khử trùng để tránh top_k bị lãng phí bởi chunk trùng.
    retrieval_top_k = min(retrieve_k, max(top_k + 4, top_k * 3, 20))
    group_filter = _normalize_business_groups(req.business_groups)

    if _use_hybrid and _dense_matrix is not None and _st_model is not None:
        retrieved_metas, _scores, low_conf, _best = hybrid_retrieve(
            req.question,
            _vectorizer,
            _tfidf_matrix,
            _metas,
            dense_matrix=_dense_matrix,
            encode_query=_encode_query_fn if alpha > 1e-6 else None,
            retrieve_k=retrieve_k,
            top_k=retrieval_top_k,
            alpha=alpha,
            min_score=min_score,
            group_filter=group_filter,
        )
    else:
        retrieved_metas, _scores, low_conf, _best = tfidf_only_retrieve(
            req.question,
            _vectorizer,
            _tfidf_matrix,
            _metas,
            retrieve_k=retrieve_k,
            top_k=retrieval_top_k,
            min_score=min_score,
            group_filter=group_filter,
        )

    if low_conf:
        return ChatResponse(answer=INSUFFICIENT_RETRIEVAL, citations=[], sources=[])

    retrieved_metas = _rerank_metas_by_keyword_overlap(req.question, retrieved_metas)
    retrieved_metas = _dedupe_metas_keep_order(retrieved_metas, top_k)

    retrieved_wrapped = []
    for m in retrieved_metas:
        retrieved_wrapped.append({"document": m.get("chunk_text", ""), "metadata": m})

    context, citations = build_context_smart(req.question, retrieved_wrapped)
    ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct")

    system_prompt = (
        "Bạn là trợ lý pháp lý Việt Nam. Trả lời NGẮN GỌN, ĐÚNG TRỌNG TÂM.\n"
        "Bắt buộc trả theo thứ tự: (1) Trả lời trực tiếp cho câu hỏi (không dùng tiền tố 'Kết luận:'); "
        "(2) Căn cứ điều khoản liên quan (chỉ dựa trên context, không suy đoán).\n"
        "Tuyệt đối KHÔNG tự tạo số hiệu văn bản, năm ban hành, điều khoản nếu không có trong context.\n"
        "Không kể ví dụ, không bàn luận ngoài phạm vi câu hỏi.\n"
        "Toàn bộ nội dung trả lời phải là tiếng Việt chuẩn; "
        "không dùng tiếng Trung, tiếng Anh hay ngôn ngữ khác (trừ khi trích nguyên văn từ context).\n"
        "Nếu context không đủ để trả lời đúng trọng tâm, chỉ trả lời đúng một câu: "
        "\"Không đủ dữ liệu trong các văn bản đã cung cấp.\""
    )
    user_prompt = (
        f"Câu hỏi: {req.question}\n\n"
        f"Context (các nguồn được gắn nhãn):\n{context}\n\n"
        "Trả lời tiếng Việt. Tối đa 2 đoạn. Không lan man."
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

    # Nếu LLM trả lời thiếu dữ liệu dù retrieval có context, retry 1 lần với chỉ dẫn chặt hơn.
    if _is_insufficient_answer(answer) and context.strip():
        retry_system_prompt = (
            "Bạn là trợ lý pháp lý Việt Nam. Trả lời đúng trọng tâm.\n"
            "Bắt buộc: trả lời trực tiếp cho câu hỏi (không dùng tiền tố 'Kết luận:'), sau đó nêu 1-3 căn cứ điều khoản có trong context.\n"
            "Không suy đoán và không thêm thông tin ngoài context.\n"
            "Chỉ trả đúng một câu \"Không đủ dữ liệu trong các văn bản đã cung cấp.\" khi context thật sự không đủ."
        )
        retry_user_prompt = (
            f"Câu hỏi: {req.question}\n\n"
            f"Context:\n{context}\n\n"
            "Trả lời hoàn toàn bằng tiếng Việt, 1 đoạn ngắn, đi thẳng vào kết luận."
        )
        try:
            retry_answer = ask_llm_ollama(
                ollama_base,
                ollama_model,
                retry_system_prompt,
                retry_user_prompt,
            )
            if retry_answer and not _is_insufficient_answer(retry_answer):
                answer = retry_answer
        except Exception:
            pass

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

    answer = _sanitize_answer_text(answer or "")
    allowed_laws = _collect_allowed_law_numbers(retrieved_metas)
    if _has_unknown_law_citation(answer, allowed_laws):
        answer = INSUFFICIENT_REFLECTION
    if _fails_rule_guard(req.question, answer):
        answer = INSUFFICIENT_REFLECTION
    if _is_penalty_intent(req.question) and not _is_insufficient_answer(answer):
        answer = answer + _scope_notice_for_penalty(retrieved_metas)

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
        # Không cache câu trả lời fallback để tránh lặp lại lỗi trong nhiều lượt hỏi.
        if not _is_insufficient_answer(resp.answer):
            _cache_set(cache_key, resp)
    return resp


# --- Health, nguồn ngoài, công cụ LLM, ingest, job batch (async) ---


@app.get("/api/health")
def api_health() -> dict[str, Any]:
    return {"status": "ok", "api": "chatbot-rag-demo"}


@app.get("/api/external-sources")
def api_external_sources_list() -> dict[str, Any]:
    return {"sources": list_external_sources()}


class ExternalFetchRequest(BaseModel):
    source_id: str = Field(..., description="ID nguồn (env EXTERNAL_SOURCE_<ID>_*)")
    query: str


@app.post("/api/external/fetch")
def api_external_fetch(req: ExternalFetchRequest) -> dict[str, Any]:
    return fetch_external(req.source_id, req.query)


class SummarizeRequest(BaseModel):
    text: str = Field(..., max_length=120_000)
    style: str | None = Field(None, description="vd: bullet, 1-đoạn")


class TranslateRequest(BaseModel):
    text: str = Field(..., max_length=120_000)
    target_lang: str = Field("vi", description="Mã ngôn ngữ đích, mặc định vi")


@app.post("/api/tools/summarize")
def api_tools_summarize(req: SummarizeRequest) -> dict[str, Any]:
    ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct")
    st = (req.style or "ngắn gọn, giữ ý chính").strip()
    system = (
        "Bạn tóm tắt văn bản. Chỉ dựa trên nội dung người dùng gửi, không thêm thông tin ngoài. "
        "Trả lời bằng tiếng Việt."
    )
    user = f"Phong cách: {st}\n\n---\n{req.text[:80_000]}"
    try:
        out = ask_llm_ollama(
            ollama_base,
            ollama_model,
            system,
            user,
            max_predict_tokens=min(2048, int(os.getenv("OLLAMA_NUM_PREDICT", "512") or 512) * 2),
        )
        return {"ok": True, "summary": out, "error": None}
    except Exception as e:
        return {"ok": False, "summary": "", "error": str(e)}


@app.post("/api/tools/translate")
def api_tools_translate(req: TranslateRequest) -> dict[str, Any]:
    ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct")
    tl = (req.target_lang or "vi").strip()
    system = (
        f"Dịch sang ngôn ngữ đích (mã: {tl}). "
        "Giữ nguyên số, ký hiệu pháp lý và tên riêng hợp lý. Chỉ trả bản dịch, không giải thích."
    )
    user = req.text[:80_000]
    try:
        out = ask_llm_ollama(
            ollama_base,
            ollama_model,
            system,
            user,
            max_predict_tokens=min(4096, int(os.getenv("OLLAMA_NUM_PREDICT", "512") or 512) * 3),
        )
        return {"ok": True, "translated": out, "target_lang": tl, "error": None}
    except Exception as e:
        return {"ok": False, "translated": "", "target_lang": tl, "error": str(e)}


@app.post("/api/ingest/upload")
async def api_ingest_upload(
    file: UploadFile = File(...),
    business_group: str | None = Form("general"),
    title: str | None = Form(None),
) -> dict[str, Any]:
    raw = await file.read()
    try:
        meta = _get_ingest_store().create_pending(
            filename=file.filename or "upload",
            raw_bytes=raw,
            business_group=(business_group or "general").strip() or "general",
            title=(title or "").strip() or None,
        )
        return {"ok": True, "record": meta, "error": None}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/ingest/pending")
def api_ingest_pending_list() -> dict[str, Any]:
    return {"items": _get_ingest_store().list_pending()}


@app.get("/api/ingest/{ingest_id}")
def api_ingest_get(ingest_id: str) -> dict[str, Any]:
    r = _get_ingest_store().get(ingest_id)
    if not r:
        raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi.")
    safe = {k: v for k, v in r.items() if k != "extracted_text"}
    if r.get("status") == "pending" and "extracted_text" in r:
        t = str(r["extracted_text"])
        safe["extract_preview"] = t[:2000] + ("…" if len(t) > 2000 else "")
    return safe


@app.post("/api/ingest/{ingest_id}/approve")
def api_ingest_approve(ingest_id: str) -> dict[str, Any]:
    try:
        out = _get_ingest_store().approve(
            ingest_id,
            rebuild_index=True,
            on_rebuilt=_load_vector_store_from_disk,
        )
        return {"ok": True, "record": out, "error": None}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/ingest/{ingest_id}/reject")
def api_ingest_reject(ingest_id: str) -> dict[str, Any]:
    if not _get_ingest_store().reject(ingest_id):
        raise HTTPException(status_code=404, detail="Không có bản ghi pending để từ chối.")
    return {"ok": True, "id": ingest_id, "status": "rejected"}


@app.post("/api/cosing/lookup/batch/jobs")
async def cosing_batch_job_start(req: CosingBatchRequest) -> dict[str, Any]:
    if not _env_flag("COSING_ENABLED"):
        raise HTTPException(status_code=503, detail="CoSIng đang tắt.")
    max_q = _cosing_batch_max_queries()
    queries = _dedupe_queries_preserve_order(req.queries or [])
    if not queries:
        raise HTTPException(status_code=422, detail="Danh sách truy vấn trống.")
    if len(queries) > max_q:
        raise HTTPException(status_code=422, detail=f"Tối đa {max_q} dòng.")
    rid = (req.request_id or "").strip() or f"job-{uuid.uuid4().hex[:12]}"
    job_id = start_batch_job_incremental(queries, _cosing_batch_row_for_query, rid)
    return {"job_id": job_id, "total": len(queries), "poll_url": f"/api/cosing/lookup/batch/jobs/{job_id}"}


@app.get("/api/cosing/lookup/batch/jobs/{job_id}")
def cosing_batch_job_status(job_id: str) -> dict[str, Any]:
    j = get_job(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Job không tồn tại.")
    return j


@app.get("/api/cosing/lookup/batch/jobs/{job_id}/events")
async def cosing_batch_job_events(job_id: str) -> StreamingResponse:
    """SSE: mỗi ~1s một event JSON trạng thái job (đến khi completed/failed)."""

    async def event_gen():
        while True:
            j = get_job(job_id)
            if not j:
                yield f"data: {json.dumps({'error': 'not_found'}, ensure_ascii=False)}\n\n"
                break
            yield f"data: {json.dumps(j, ensure_ascii=False)}\n\n"
            if j.get("status") in ("completed", "failed"):
                break
            await asyncio.sleep(1.0)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


_demo_dir = PROJECT_ROOT / "demo_web"
if _demo_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_demo_dir), html=True), name="demo")
