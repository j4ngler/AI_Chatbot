"""
Smoke test: RAG retrieval + LLM (Ollama).

  python tools/smoke_test_rag_llm.py
  python tools/smoke_test_rag_llm.py --rag-only
  python tools/smoke_test_rag_llm.py --question "Điều kiện hợp đồng lao động"
  python tools/smoke_test_rag_llm.py --suite --rag-only
  python tools/smoke_test_rag_llm.py --suite --llm-first 3

Hồi quy (so sánh trước/sau đổi retrieval): chạy --suite --rag-only, lưu log top-1 law/article.
Staging thủ công: xem tests/MANUAL_STAGING.md (M1–M5).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import numpy as np
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from tools.query_rag_file_based import load_vector_store, build_context
from tools.llm_clients import ask_llm_ollama

RagBundle = tuple[object, object, list[dict]]

# Bám theo data/raw_laws/manifest.json (+ chunks đã index). Không có BLĐ riêng trong raw_laws.
SUITE_CASES: list[tuple[str, str]] = [
    # 36/2024/QH15 — Luật Trật tự, an toàn giao thông đường bộ
    ("36_2024_tt", "cấm dùng điện thoại khi điều khiển phương tiện đang di chuyển trên đường bộ"),
    ("36_2024_tt", "người lái xe ô tô thắt dây đai an toàn khi tham gia giao thông"),
    ("36_2024_tt", "cơ sở dữ liệu về đăng ký xe và giấy phép lái xe"),
    # 35/2024/QH15 — Luật Đường bộ
    ("35_2024_db", "đầu tư đường bộ theo phương thức đối tác công tư PPP"),
    ("35_2024_db", "tốc độ thiết kế và tốc độ khai thác của đường bộ"),
    ("35_2024_db", "phần mềm hỗ trợ kết nối vận tải bằng xe ô tô"),
    # 23/2008/QH12 — Luật Giao thông đường bộ 2008
    ("23_2008_gt", "điều kiện kinh doanh vận tải bằng xe ô tô"),
    ("23_2008_gt", "giấy phép lái xe các hạng B C D E"),
    ("23_2008_gt", "vận chuyển hàng nguy hiểm bằng xe trên đường bộ"),
    # 35/2018/QH14 — sửa 37 luật liên quan quy hoạch (trong corpus có nhiều đoạn sửa Luật GTĐB)
    ("35_2018_qh", "quy hoạch mạng lưới đường bộ quốc gia ai tổ chức lập"),
    ("35_2018_qh", "quy hoạch kết cấu hạ tầng giao thông đường bộ thời kỳ và tầm nhìn"),
    ("35_2018_qh", "trạm kiểm tra tải trọng xe và trạm thu phí trên đường bộ"),
    # 26/2001/QH10 — Luật GTĐB 2001 (file gốc RTF thường lỗi encoding; truy vấn có thể kém ổn định)
    ("26_2001_gt", "hành lang an toàn đường bộ và phần đường xe chạy"),
    # Edge / ngoài phạm vi hợp lý
    ("edge", "bitcoin staking defi không liên quan pháp luật Việt Nam trong tài liệu"),
    ("edge", "z"),
]


def print_rag_block(
    tag: str,
    question: str,
    top_k: int,
    bundle: RagBundle,
) -> str:
    vectorizer, tfidf_matrix, metas = bundle
    q_vec = vectorizer.transform([question])
    sims = (tfidf_matrix @ q_vec.T).toarray().ravel()
    top_idx = np.argsort(-sims)[:top_k]
    retrieved = [metas[int(i)] for i in top_idx]

    print(f"### [{tag}] {question}")
    print(f"    Vector store: {tfidf_matrix.shape[0]} chunks, top_k={top_k}")
    for rank, i in enumerate(top_idx, 1):
        m = metas[int(i)]
        print(f"    #{rank} sim={float(sims[int(i)]):.4f} | law={m.get('law_number','')} | art={m.get('article_ref','')}")
        t = (m.get("chunk_text") or "")[:160].replace("\n", " ")
        print(f"        {t}...")
    context, _ = build_context(retrieved)
    print("    RAG: OK\n")
    return str(context)


def test_rag(question: str, top_k: int) -> str:
    print("=== 1) RAG (TF-IDF retrieval) ===")
    bundle = load_vector_store()
    ctx = print_rag_block("single", question, top_k, bundle)
    return ctx


def test_llm(context: str, question: str) -> None:
    print("=== 2) LLM (Ollama) ===")
    system = "Bạn là trợ lý pháp lý. Trả lời cực ngắn, chỉ dựa trên context."
    user = f"Câu hỏi: {question}\n\nContext:\n{context[:4000]}\n\nTrả lời tiếng Việt một câu."

    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct")
    try:
        out = ask_llm_ollama(base, model, system, user)
        print(f"Ollama ({model}): {out[:500]}{'...' if len(out) > 500 else ''}")
        print("LLM Ollama: OK\n")
    except Exception as e:
        print(
            "Không gọi được Ollama.\n"
            f"  Chạy Ollama tại {base} với model {model} (ollama pull {model})\n"
            f"  Chi tiết: {e!r}"
        )


def run_suite(top_k: int, rag_only: bool, llm_first: int) -> None:
    print("========== SUITE: nhiều câu hỏi (load vector store 1 lần) ==========\n")
    bundle = load_vector_store()
    for idx, (tag, q) in enumerate(SUITE_CASES, start=1):
        print(f"--- Case {idx}/{len(SUITE_CASES)} ---")
        ctx = print_rag_block(tag, q, top_k, bundle)
        if not rag_only and idx <= llm_first:
            print(f"    >>> LLM (case {idx})")
            test_llm(ctx, q)
    if rag_only:
        print(f"Kết thúc suite: {len(SUITE_CASES)} câu, chỉ RAG.")
    elif llm_first <= 0:
        print("Kết thúc suite: không gọi LLM (--llm-first 0). Thêm --llm-first N để gọi LLM N câu đầu.")
    else:
        print(f"Kết thúc suite: LLM đã chạy cho {min(llm_first, len(SUITE_CASES))} câu đầu.")


def main() -> None:
    p = argparse.ArgumentParser(description="Smoke test RAG + LLM")
    p.add_argument("--rag-only", action="store_true", help="Chỉ kiểm tra retrieval, không gọi LLM")
    p.add_argument("--top-k", type=int, default=3)
    p.add_argument("--question", default="hợp đồng lao động thử việc")
    p.add_argument("--suite", action="store_true", help="Chạy nhiều câu hỏi mẫu (xem SUITE_CASES)")
    p.add_argument(
        "--llm-first",
        type=int,
        default=0,
        metavar="N",
        help="Khi dùng --suite: gọi LLM cho N câu đầu (0 = không gọi). Mặc định 0 vì lâu.",
    )
    args = p.parse_args()

    if args.suite:
        run_suite(args.top_k, args.rag_only, args.llm_first)
        return

    ctx = test_rag(args.question, args.top_k)
    if not args.rag_only:
        test_llm(ctx, args.question)


if __name__ == "__main__":
    main()
