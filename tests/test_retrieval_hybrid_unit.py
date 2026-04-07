"""Đơn vị: min-max normalize trên pool."""

from __future__ import annotations

import numpy as np


def test_minmax_inside_hybrid_constant_pool() -> None:
    """Khi pool TF-IDF không đổi, hybrid vẫn trả thứ tự hợp lệ."""
    # Không mock toàn bộ scipy sparse — kiểm tra trực tiếp _minmax qua tfidf_only trong module
    import tools.retrieval_hybrid as rh

    x = np.array([3.0, 3.0, 3.0], dtype=np.float64)
    y = rh._minmax01(x)
    assert np.allclose(y, 0.5)

    x2 = np.array([0.0, 0.5, 1.0], dtype=np.float64)
    y2 = rh._minmax01(x2)
    assert abs(float(y2[0])) < 1e-6 and abs(float(y2[-1]) - 1.0) < 1e-6


def test_hybrid_retrieve_toy_matrix() -> None:
    """Ma trận 1 chunk: hybrid trả đúng 1 meta."""
    from sklearn.feature_extraction.text import TfidfVectorizer

    from tools.retrieval_hybrid import hybrid_retrieve

    v = TfidfVectorizer(min_df=1, token_pattern=r"(?u)\b\w+\b")
    m = v.fit_transform(["kinh doanh van tai duong bo viet nam"])
    metas = [{"chunk_text": "kinh doanh van tai duong bo viet nam", "law_number": "1", "article_ref": "Điều 1"}]
    dm = np.ones((1, 8), dtype=np.float32)
    dm = dm / np.linalg.norm(dm, axis=1, keepdims=True)

    def enc(_q: str) -> np.ndarray:
        e = np.ones(8, dtype=np.float32)
        return e / np.linalg.norm(e)

    out, scores, low, best = hybrid_retrieve(
        "van tai duong bo",
        v,
        m,
        metas,
        dense_matrix=dm,
        encode_query=enc,
        retrieve_k=1,
        top_k=1,
        alpha=0.5,
        min_score=None,
    )
    assert len(out) == 1
    assert not low
    assert len(scores) == 1
