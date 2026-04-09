from __future__ import annotations

"""
Chạy test hàng loạt các câu hỏi mẫu trong demo_questions.md:
- Pháp luật: gọi trực tiếp chat()
- CoSIng: gọi trực tiếp dịch vụ _get_cosing_service()
Không phụ thuộc server HTTP.
"""

import argparse
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path

from api.main import ChatRequest, _get_cosing_service, _is_insufficient_answer, chat, startup

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_timeout(name: str) -> float | None:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        return None
    try:
        val = float(raw)
    except ValueError:
        return None
    if val <= 0:
        return None
    return val


def load_questions() -> tuple[list[str], list[str]]:
    path = PROJECT_ROOT / "demo_questions.md"
    text = path.read_text(encoding="utf-8")
    legal_questions: list[str] = []
    cosing_questions: list[str] = []
    mode = "ignore"
    for line in text.splitlines():
        s = line.strip()
        if re.match(r"^##\s+[1-8]\)", s):
            mode = "legal"
            continue
        if re.match(r"^##\s+9\)", s, flags=re.IGNORECASE):
            mode = "cosing"
            continue
        m = re.match(r"^\s*-\s+(.+?)\s*$", line)
        if m:
            q = m.group(1).strip()
            if mode == "legal":
                legal_questions.append(q)
            elif mode == "cosing":
                cosing_questions.append(q)
    return legal_questions, cosing_questions


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch test demo_questions.md (in-process).")
    parser.add_argument(
        "--legal-only",
        action="store_true",
        help="Chỉ chạy câu pháp luật (bỏ qua CoSIng).",
    )
    args = parser.parse_args()

    # Khởi tạo vector store giống sự kiện startup của FastAPI.
    startup()
    legal_qs, cosing_qs = load_questions()
    if args.legal_only:
        print(f"Loaded {len(legal_qs)} legal questions (CoSIng skipped).")
    else:
        print(f"Loaded {len(legal_qs)} legal questions + {len(cosing_qs)} CoSIng questions.")
    legal_timeout = _read_timeout("BATCH_LEGAL_TIMEOUT_SECONDS")
    cosing_timeout = _read_timeout("BATCH_COSING_TIMEOUT_SECONDS")

    legal_failures: list[tuple[str, str]] = []
    with ThreadPoolExecutor(max_workers=1) as ex:
        for i, q in enumerate(legal_qs, 1):
            print(f"[LEGAL {i}/{len(legal_qs)}] {q}", flush=True)
            fut = ex.submit(chat, ChatRequest(question=q))
            try:
                if legal_timeout is None:
                    resp = fut.result()
                else:
                    resp = fut.result(timeout=legal_timeout)
            except TimeoutError:
                legal_failures.append((q, f"TIMEOUT (>{legal_timeout}s)"))
                continue
            except Exception as e:
                legal_failures.append((q, f"ERROR: {e!s}"))
                continue
            if _is_insufficient_answer(resp.answer):
                legal_failures.append((q, resp.answer))

    cosing_failures: list[tuple[str, str]] = []
    if not args.legal_only:
        # CoSIng: ưu tiên chạy nền để không bật cửa sổ browser khi batch test.
        if not os.getenv("COSING_HEADLESS"):
            os.environ["COSING_HEADLESS"] = "true"
        service = _get_cosing_service()
        with ThreadPoolExecutor(max_workers=1) as ex:
            for i, q in enumerate(cosing_qs, 1):
                print(f"[COSING {i}/{len(cosing_qs)}] {q}", flush=True)
                payload = {
                    "query": q,
                    "query_type": "NAME_OR_INCI",
                    "request_id": f"batch-{uuid.uuid4().hex[:10]}",
                }
                fut = ex.submit(service.lookup_payload, payload)
                try:
                    if cosing_timeout is None:
                        out = fut.result()
                    else:
                        out = fut.result(timeout=cosing_timeout)
                    subs = out.substances or []
                    if out.status != "OK" or len(subs) == 0:
                        rr = out.rejection_reason or ""
                        cosing_failures.append(
                            (q, f"status={out.status}; substances={len(subs)}; reason={rr}")
                        )
                except TimeoutError:
                    cosing_failures.append((q, f"TIMEOUT (>{cosing_timeout}s)"))
                except Exception as e:
                    cosing_failures.append((q, f"ERROR: {e!s}"))

    print("\n=== SUMMARY LEGAL ===")
    print(f"Total: {len(legal_qs)}, Failures: {len(legal_failures)}")
    for q, ans in legal_failures:
        print(f"- Câu: {q}")
        print(f"  => Trả lời: {ans}")

    if not args.legal_only:
        print("\n=== SUMMARY COSING ===")
        print(f"Total: {len(cosing_qs)}, Failures: {len(cosing_failures)}")
        for q, ans in cosing_failures:
            print(f"- Câu: {q}")
            print(f"  => Trả lời/lỗi: {ans}")


if __name__ == "__main__":
    main()

