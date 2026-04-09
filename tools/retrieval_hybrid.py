"""
Hybrid retrieval: TF-IDF pool retrieve_k + min-max normalize + alpha * dense + (1-alpha) * tfidf.
Dense: cosine = dot vì vectors L2-normalized.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import numpy as np


def row_indices_for_business_groups(metas: list[dict], group_filter: list[str] | None) -> np.ndarray | None:
    """
    None = không lọc (toàn bộ chỉ mục).
    np.ndarray int64: chỉ các dòng thuộc nhóm; rỗng nghĩa là không có chunk nào khớp.
    Chunk không có business_group (legacy) vẫn được giữ khi đang lọc — tránh gãy kho cũ chưa rebuild.
    """
    if not group_filter:
        return None
    allowed = {str(g).strip() for g in group_filter if str(g).strip()}
    if not allowed:
        return None
    idx_list: list[int] = []
    for i, m in enumerate(metas):
        raw = m.get("business_group")
        g = str(raw).strip() if raw is not None and raw != "" else ""
        if not g:
            idx_list.append(i)
        elif g in allowed:
            idx_list.append(i)
    return np.array(idx_list, dtype=np.int64)


def _minmax01(x: np.ndarray) -> np.ndarray:
    mn = float(x.min())
    mx = float(x.max())
    if mx - mn < 1e-9:
        return np.full_like(x, 0.5)
    return (x - mn) / (mx - mn)


def hybrid_retrieve(
    question: str,
    vectorizer: Any,
    tfidf_matrix: Any,
    metas: list[dict],
    *,
    dense_matrix: np.ndarray | None,
    encode_query: Callable[[str], np.ndarray] | None,
    retrieve_k: int,
    top_k: int,
    alpha: float,
    min_score: float | None,
    group_filter: list[str] | None = None,
) -> tuple[list[dict], np.ndarray, bool, float]:
    """
    Returns: (retrieved_metas, scores_for_retrieved, low_confidence, best_score)
    """
    n = int(tfidf_matrix.shape[0])
    if len(metas) != n:
        raise RuntimeError("metas length != tfidf rows")

    allowed_idx = row_indices_for_business_groups(metas, group_filter)
    if allowed_idx is not None and allowed_idx.size == 0:
        return [], np.array([], dtype=np.float64), True, 0.0

    retrieve_k = max(1, min(retrieve_k, n))
    top_k = max(1, min(top_k, retrieve_k))

    q_tfidf = vectorizer.transform([question])
    tfidf_sims = sparse_or_dense_dot_tfidf_query(tfidf_matrix, q_tfidf)

    if allowed_idx is not None:
        sims_allowed = tfidf_sims[allowed_idx]
        order_local = np.argsort(-sims_allowed)
        take = min(retrieve_k, int(order_local.size))
        pool_idx = allowed_idx[order_local[:take]]
    else:
        pool_idx = np.argsort(-tfidf_sims)[:retrieve_k]
    pool_t = tfidf_sims[pool_idx].astype(np.float64)

    if dense_matrix is not None and encode_query is not None and alpha > 1e-6:
        q_dense = encode_query(question).astype(np.float64)
        if q_dense.shape[0] != dense_matrix.shape[1]:
            raise ValueError("Query embedding dim != dense_matrix columns")
        d_sims = (dense_matrix @ q_dense).astype(np.float64)
        pool_d = d_sims[pool_idx]
        t_n = _minmax01(pool_t)
        d_n = _minmax01(pool_d)
        hybrid = alpha * d_n + (1.0 - alpha) * t_n
    else:
        hybrid = _minmax01(pool_t)

    order = np.argsort(-hybrid)
    ranked_pool = pool_idx[order]
    hybrid_sorted = hybrid[order]

    best = float(hybrid_sorted[0]) if hybrid_sorted.size else 0.0
    low = bool(min_score is not None and best < min_score)

    final_idx = ranked_pool[:top_k]
    final_scores = hybrid_sorted[:top_k]
    retrieved = [metas[int(i)] for i in final_idx]
    return retrieved, final_scores, low, best


def load_dense_matrix(persist_dir: Any, n_rows: int) -> np.ndarray | None:
    path = persist_dir / os.getenv("DENSE_MATRIX_FILENAME", "dense_matrix.npy")
    if not path.exists():
        return None
    arr = np.load(path)
    if arr.dtype != np.float32:
        arr = arr.astype(np.float32)
    if arr.shape[0] != n_rows:
        raise RuntimeError(f"dense_matrix rows {arr.shape[0]} != metas {n_rows}")
    return arr


def sparse_or_dense_dot_tfidf_query(tfidf_matrix: Any, q_tfidf: Any) -> np.ndarray:
    """Full corpus TF-IDF similarity (for tfidf-only path)."""
    return (tfidf_matrix @ q_tfidf.T).toarray().ravel()


def tfidf_only_retrieve(
    question: str,
    vectorizer: Any,
    tfidf_matrix: Any,
    metas: list[dict],
    retrieve_k: int,
    top_k: int,
    min_score: float | None,
    group_filter: list[str] | None = None,
) -> tuple[list[dict], np.ndarray, bool, float]:
    """Pool retrieve_k by TF-IDF, min-max on pool, cut top_k; min_score on best normalized score."""
    n = int(tfidf_matrix.shape[0])
    allowed_idx = row_indices_for_business_groups(metas, group_filter)
    if allowed_idx is not None and allowed_idx.size == 0:
        return [], np.array([], dtype=np.float64), True, 0.0

    retrieve_k = max(1, min(retrieve_k, n))
    top_k = max(1, min(top_k, retrieve_k))

    q_tfidf = vectorizer.transform([question])
    tfidf_sims = sparse_or_dense_dot_tfidf_query(tfidf_matrix, q_tfidf)

    if allowed_idx is not None:
        sims_allowed = tfidf_sims[allowed_idx]
        order_local = np.argsort(-sims_allowed)
        take = min(retrieve_k, int(order_local.size))
        pool_idx = allowed_idx[order_local[:take]]
    else:
        pool_idx = np.argsort(-tfidf_sims)[:retrieve_k]
    pool_t = tfidf_sims[pool_idx].astype(np.float64)
    hybrid = _minmax01(pool_t)
    order = np.argsort(-hybrid)
    ranked_pool = pool_idx[order]
    hybrid_sorted = hybrid[order]

    best = float(hybrid_sorted[0]) if hybrid_sorted.size else 0.0
    low = bool(min_score is not None and best < min_score)

    final_idx = ranked_pool[:top_k]
    final_scores = hybrid_sorted[:top_k]
    retrieved = [metas[int(i)] for i in final_idx]
    return retrieved, final_scores, low, best
