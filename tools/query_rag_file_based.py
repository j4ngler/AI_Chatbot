from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import joblib
import numpy as np
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.chat_router import route_smalltalk
from tools.llm_clients import ask_llm_ollama, reflect_answer_grounded
from tools.retrieval_hybrid import hybrid_retrieve, load_dense_matrix, tfidf_only_retrieve


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

    return vectorizer, tfidf_matrix, metas, persist_dir


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
    parser.add_argument("--json-meta", action="store_true", help="In thêm low_confidence, best_score")
    args = parser.parse_args()

    if os.getenv("ROUTER_ENABLED", "true").lower() in ("1", "true", "yes"):
        routed = route_smalltalk(args.question)
        if routed is not None:
            out = {"answer": routed, "citations": [], "sources": [], "routed": True}
            print(json.dumps(out, ensure_ascii=True, indent=2))
            return

    vectorizer, tfidf_matrix, metas, persist_dir = load_vector_store()

    retrieve_k = int(os.getenv("RETRIEVE_K", "20"))
    alpha = float(os.getenv("HYBRID_ALPHA", "0.5"))
    min_raw = os.getenv("MIN_RETRIEVAL_SCORE", "").strip()
    min_score = float(min_raw) if min_raw else None
    mode = os.getenv("RAG_MODE", "").strip().lower()
    dm = load_dense_matrix(persist_dir, len(metas))
    use_hybrid = (mode == "hybrid" and dm is not None) or (mode not in ("hybrid", "tfidf") and dm is not None)
    if mode == "tfidf":
        use_hybrid = False

    st_model = None

    def encode_q(q: str) -> np.ndarray:
        nonlocal st_model
        if st_model is None:
            from sentence_transformers import SentenceTransformer

            model_name = os.getenv("DENSE_MODEL_NAME", "paraphrase-multilingual-MiniLM-L12-v2")
            st_model = SentenceTransformer(model_name)
        v = st_model.encode([q], convert_to_numpy=True, normalize_embeddings=True)[0]
        return v.astype(np.float32)

    if use_hybrid and dm is not None:
        retrieved_metas, scores, low_conf, best = hybrid_retrieve(
            args.question,
            vectorizer,
            tfidf_matrix,
            metas,
            dense_matrix=dm,
            encode_query=encode_q,
            retrieve_k=retrieve_k,
            top_k=args.top_k,
            alpha=alpha,
            min_score=min_score,
        )
    else:
        retrieved_metas, scores, low_conf, best = tfidf_only_retrieve(
            args.question,
            vectorizer,
            tfidf_matrix,
            metas,
            retrieve_k=retrieve_k,
            top_k=args.top_k,
            min_score=min_score,
        )

    if low_conf:
        out = {
            "answer": "Không đủ căn cứ trong các văn bản đã index để trả lời chính xác câu hỏi này.",
            "citations": [],
            "sources": [],
            "low_confidence": True,
            "best_score": best,
        }
        print(json.dumps(out, ensure_ascii=True, indent=2))
        return

    context, citations = build_context(retrieved_metas)
    ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct")

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
    try:
        answer = ask_llm_ollama(ollama_base, ollama_model, system_prompt, user_prompt)
    except Exception as e:
        print(f"[WARN] Ollama error: {e!r}")
        preview = "\n\n".join(
            [m.get("chunk_text", "")[:1200] for m in retrieved_metas[: args.top_k]]
        )
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
            answer = "Không đủ dữ liệu trong các văn bản đã cung cấp."

    out = {"answer": answer, "citations": citations}
    if args.json_meta:
        out["low_confidence"] = low_conf
        out["best_score"] = float(best)
    print(json.dumps(out, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
