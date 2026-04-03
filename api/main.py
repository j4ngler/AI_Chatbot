from __future__ import annotations

import json
import os
import sys
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

import joblib
from openai import OpenAI

from pathlib import Path
import numpy as np

# Cho phép import `tools.*` ổn định khi chạy uvicorn theo cấu hình khác
ROOT_FOR_IMPORT = Path(__file__).resolve().parents[1]
if str(ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(ROOT_FOR_IMPORT))
from tools.llm_clients import ask_llm_ollama, ask_llm_gemini


PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")

app = FastAPI(title="Chatbot RAG Demo (file-based)", version="0.1")


class ChatRequest(BaseModel):
    question: str
    top_k: int | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[str]
    sources: list[dict[str, Any]]


_collection = None
_llm: OpenAI | None = None
_vectorizer = None
_tfidf_matrix = None
_metas: list[dict[str, Any]] | None = None


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


@app.on_event("startup")
def startup() -> None:
    global _llm, _vectorizer, _tfidf_matrix, _metas

    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        _llm = OpenAI(api_key=api_key)
    else:
        _llm = None

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


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    global _tfidf_matrix, _vectorizer, _metas, _llm

    if not req.question.strip():
        return ChatResponse(answer="Câu hỏi trống.", citations=[], sources=[])

    top_k = int(req.top_k or int(os.getenv("TOP_K_DEFAULT", "3")))
    if top_k < 1:
        top_k = 1

    # TF-IDF retrieval
    q_vec = _vectorizer.transform([req.question])
    # tf-idf matrix đã L2-normalized -> dot ~ cosine
    sims = (_tfidf_matrix @ q_vec.T).toarray().ravel()
    top_idx = np.argsort(-sims)[:top_k]

    retrieved_metas = [_metas[i] for i in top_idx]
    # build_context mong đợi list dict {metadata?, document?} nên ta bọc theo format cũ
    retrieved_wrapped = []
    for m in retrieved_metas:
        retrieved_wrapped.append({"document": m.get("chunk_text", ""), "metadata": m})

    context, citations = build_context(retrieved_wrapped)
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    gemini_key = os.getenv("GEMINI_API_KEY")
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    system_prompt = (
        "Bạn là trợ lý pháp lý. Hãy trả lời CỰC KỲ NGẮN GỌN, đúng trọng tâm, "
        "và CHỈ dựa trên phần context do hệ thống cung cấp. "
        "Nếu context không đủ để trả lời chính xác, hãy nói: \"Không đủ dữ liệu trong các văn bản đã cung cấp.\""
    )
    user_prompt = (
        f"Câu hỏi: {req.question}\n\n"
        f"Context (các nguồn được gắn nhãn):\n{context}\n\n"
        "Trả lời bằng tiếng Việt."
    )

    answer = None
    # 1) Ưu tiên OpenAI nếu có key
    if _llm is not None:
        try:
            resp = _llm.chat.completions.create(
                model=openai_model,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            answer = resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"[WARN] OpenAI error: {e!r}")
            answer = None

    # 2) Nếu OpenAI fail, thử Gemini
    if answer is None and gemini_key:
        try:
            answer = ask_llm_gemini(gemini_key, gemini_model, system_prompt, user_prompt)
        except Exception as e:
            print(f"[WARN] Gemini error: {e!r}")
            answer = None

    # 3) Nếu vẫn fail, thử Ollama; cuối cùng mới fallback extractive
    if answer is None:
        try:
            ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct")
            answer = ask_llm_ollama(ollama_base, ollama_model, system_prompt, user_prompt)
        except Exception as e:
            print(f"[WARN] Ollama error: {e!r}")
            preview = "\n\n".join(
                [r.get("metadata", {}).get("chunk_text", "")[:1200] for r in retrieved_wrapped[:top_k]]
            )
            if not preview:
                preview = context[:5000]
            answer = (
                "Không gọi được OpenAI/Gemini/Ollama. "
                "Dưới đây là trích dẫn từ các đoạn context liên quan:\n\n"
                + preview
            )

    # sources: dùng cho UI hiển thị
    sources = []
    for r in retrieved_wrapped:
        sources.append(
            {
                "law_number": (r["metadata"] or {}).get("law_number"),
                "article_ref": (r["metadata"] or {}).get("article_ref"),
            }
        )

    return ChatResponse(answer=answer, citations=citations, sources=sources)

