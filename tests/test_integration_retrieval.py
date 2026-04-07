"""T2–T4: cần vector store thật trong repo (skip nếu thiếu)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import joblib
import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

PERSIST = PROJECT_ROOT / "data" / "vector_db" / "file_based_demo"


def _have_tfidf() -> bool:
    return (
        (PERSIST / "vectorizer.joblib").exists()
        and (PERSIST / "tfidf_matrix.joblib").exists()
        and (PERSIST / "metadatas.jsonl").exists()
    )


@pytest.mark.skipif(not _have_tfidf(), reason="Thiếu TF-IDF vector store")
def test_t2_dense_rows_match_metas() -> None:
    dense_path = PERSIST / os.getenv("DENSE_MATRIX_FILENAME", "dense_matrix.npy")
    if not dense_path.exists():
        pytest.skip("Chưa build dense_matrix.npy")
    metas = [json.loads(l) for l in (PERSIST / "metadatas.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    arr = np.load(dense_path)
    tfidf = joblib.load(PERSIST / "tfidf_matrix.joblib")
    assert len(metas) == arr.shape[0] == tfidf.shape[0]


@pytest.mark.skipif(not _have_tfidf(), reason="Thiếu vector store")
def test_t3_hybrid_top1_known_queries() -> None:
    dense_path = PERSIST / "dense_matrix.npy"
    if not dense_path.exists():
        pytest.skip("Cần dense để test hybrid T3")

    from sentence_transformers import SentenceTransformer

    from tools.retrieval_hybrid import hybrid_retrieve

    vectorizer = joblib.load(PERSIST / "vectorizer.joblib")
    tfidf_matrix = joblib.load(PERSIST / "tfidf_matrix.joblib")
    metas = [json.loads(l) for l in (PERSIST / "metadatas.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    dm = np.load(dense_path).astype(np.float32)
    model_name = os.getenv("DENSE_MODEL_NAME", "paraphrase-multilingual-MiniLM-L12-v2")
    model = SentenceTransformer(model_name)

    def enc(q: str) -> np.ndarray:
        v = model.encode([q], convert_to_numpy=True, normalize_embeddings=True)[0]
        return v.astype(np.float32)

    cases = [
        ("phần mềm hỗ trợ kết nối vận tải bằng xe ô tô", "35/2024/QH15", "Điều 80"),
        ("vận chuyển hàng nguy hiểm xe có giấy phép", "23/2008/QH12", "Điều 78"),
    ]
    for q, expect_law, expect_art in cases:
        out, _, low, _ = hybrid_retrieve(
            q,
            vectorizer,
            tfidf_matrix,
            metas,
            dense_matrix=dm,
            encode_query=enc,
            retrieve_k=20,
            top_k=1,
            alpha=0.5,
            min_score=None,
        )
        assert not low
        assert out[0].get("law_number") == expect_law
        assert expect_art in (out[0].get("article_ref") or "")


@pytest.mark.skipif(not _have_tfidf(), reason="Thiếu vector store")
def test_t4_min_score_triggers_low_confidence() -> None:
    from tools.retrieval_hybrid import tfidf_only_retrieve

    vectorizer = joblib.load(PERSIST / "vectorizer.joblib")
    tfidf_matrix = joblib.load(PERSIST / "tfidf_matrix.joblib")
    metas = [json.loads(l) for l in (PERSIST / "metadatas.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

    _out, _s, low, _b = tfidf_only_retrieve(
        "bitcoin staking defi ethereum unrelated",
        vectorizer,
        tfidf_matrix,
        metas,
        retrieve_k=20,
        top_k=3,
        min_score=0.95,
    )
    assert low is True
