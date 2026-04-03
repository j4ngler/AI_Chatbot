from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import joblib
import numpy as np
from dotenv import load_dotenv
from openai import OpenAI


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    # Cho phép import `tools.*` kể cả khi chạy script theo kiểu: python path/to/tools/query_rag_file_based.py
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.llm_clients import ask_llm_ollama, ask_llm_gemini


def load_vector_store():
    persist_dir = PROJECT_ROOT / os.getenv("VECTOR_STORE_DIR", "data/vector_db/file_based_demo")
    vectorizer_path = persist_dir / os.getenv("TFIDF_VECTORIZER_FILENAME", "vectorizer.joblib")
    matrix_path = persist_dir / os.getenv("TFIDF_MATRIX_FILENAME", "tfidf_matrix.joblib")
    metas_path = persist_dir / os.getenv("METAS_FILENAME", "metadatas.jsonl")

    if not vectorizer_path.exists() or not matrix_path.exists() or not metas_path.exists():
        raise FileNotFoundError(
            f"Thiếu vector store tại {persist_dir}. Hãy chạy build_embeddings_file_based.py trước."
        )

    vectorizer = joblib.load(vectorizer_path)
    tfidf_matrix = joblib.load(matrix_path)
    metas: list[dict] = []
    with metas_path.open("r", encoding="utf-8") as f:
        for line in f:
            metas.append(json.loads(line))

    if len(metas) != tfidf_matrix.shape[0]:
        raise RuntimeError(f"Lệch số lượng: {tfidf_matrix.shape[0]} rows vs {len(metas)} metadata.")

    return vectorizer, tfidf_matrix, metas


def build_context(metas: list[dict], limit_chars_per_chunk: int = 1800) -> tuple[str, list[str]]:
    citations: list[str] = []
    parts: list[str] = []
    for i, m in enumerate(metas):
        law_number = m.get("law_number", "") or ""
        article_ref = m.get("article_ref", "") or ""
        citation = f"[{law_number} - {article_ref}]".strip()
        citations.append(citation)

        text = m.get("chunk_text", "") or ""
        if len(text) > limit_chars_per_chunk:
            text = text[:limit_chars_per_chunk] + "..."

        parts.append(f"SOURCE_{i+1} {citation}\n{text}")
    return "\n\n".join(parts), citations


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    parser = argparse.ArgumentParser()
    parser.add_argument("--question", required=True)
    parser.add_argument("--top-k", type=int, default=int(os.getenv("TOP_K_DEFAULT", "3")))
    args = parser.parse_args()

    vectorizer, tfidf_matrix, metas = load_vector_store()

    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    api_key = os.getenv("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key) if api_key else None
    gemini_key = os.getenv("GEMINI_API_KEY")
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    q_vec = vectorizer.transform([args.question])
    # tf-idf đã được chuẩn hóa L2 => dot product xấp xỉ cosine
    sims = (tfidf_matrix @ q_vec.T).toarray().ravel()
    top_idx = np.argsort(-sims)[: args.top_k]

    retrieved_metas = [metas[i] for i in top_idx]
    context, citations = build_context(retrieved_metas)

    system_prompt = (
        "You are a legal assistant. Answer shortly, correct and only use the given context. "
        "If context is insufficient, reply: \"Not enough data in provided documents.\""
    )
    user_prompt = (
        f"Question: {args.question}\n\n"
        f"Context (sources are labeled):\n{context}\n\n"
        "Answer in Vietnamese."
    )

    answer = None
    # 1) Thử OpenAI
    if client is not None:
        try:
            resp = client.chat.completions.create(
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

    # 2) Thử Gemini
    if answer is None and gemini_key:
        try:
            answer = ask_llm_gemini(gemini_key, gemini_model, system_prompt, user_prompt)
        except Exception as e:
            print(f"[WARN] Gemini error: {e!r}")
            answer = None

    # 3) Thử Ollama
    if answer is None:
        try:
            ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct")
            answer = ask_llm_ollama(ollama_base, ollama_model, system_prompt, user_prompt)
        except Exception as e:
            print(f"[WARN] Ollama error: {e!r}")
            preview = "\n\n".join(
                [m.get("chunk_text", "")[:1200] for m in retrieved_metas[: args.top_k]]
            )
            answer = (
                "Không gọi được OpenAI/Gemini/Ollama. "
                "Dưới đây là trích dẫn từ các đoạn context liên quan:\n\n"
                + preview
            )
    out = {"answer": answer, "citations": citations}
    # Windows console đôi khi không encode UTF-8 tốt (CP1252),
    # nên in ra với ensure_ascii=True để tránh UnicodeEncodeError.
    print(json.dumps(out, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()

