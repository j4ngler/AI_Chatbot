"""
Tạo dense_matrix.npy (L2-normalized rows) đồng bộ thứ tự với metadatas.jsonl / TF-IDF.
Chạy sau: python tools/build_embeddings_file_based.py
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Trùng thứ tự với build_embeddings_file_based
from tools.build_embeddings_file_based import iter_chunk_records  # noqa: E402


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    persist_dir = PROJECT_ROOT / os.getenv("VECTOR_STORE_DIR", "data/vector_db/file_based_demo")
    metas_path = persist_dir / os.getenv("METAS_FILENAME", "metadatas.jsonl")
    dense_path = persist_dir / os.getenv("DENSE_MATRIX_FILENAME", "dense_matrix.npy")
    model_name = os.getenv("DENSE_MODEL_NAME", "paraphrase-multilingual-MiniLM-L12-v2")

    if not metas_path.exists():
        raise FileNotFoundError(f"Thiếu {metas_path}. Chạy build_embeddings_file_based.py trước.")

    if dense_path.exists() and not args.rebuild:
        print(f"SKIP (exists): {dense_path.name}")
        return

    records = iter_chunk_records()
    texts = [r.get("chunk_text") or "" for r in records]
    if not texts:
        raise RuntimeError("Không có chunk_text.")

    print(f"Loading model {model_name!r} ...")
    model = SentenceTransformer(model_name)

    embeddings = model.encode(
        texts,
        batch_size=args.batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    arr = embeddings.astype(np.float32)
    np.save(dense_path, arr)
    print(f"DONE dense embeddings shape={arr.shape} -> {dense_path}")


if __name__ == "__main__":
    main()
