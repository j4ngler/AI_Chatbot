from __future__ import annotations

"""
Gọi trực tiếp API để test toàn bộ câu trong demo_questions.md.
- Pháp luật: POST /chat
- CoSIng:   POST /api/cosing/lookup
Yêu cầu: server đang chạy ở http://127.0.0.1:8000.
"""

import asyncio
import os
import re
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_BASE = "http://127.0.0.1:8000"


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
    section = "ignore"
    for line in text.splitlines():
        s = line.strip().lower()
        if re.match(r"^##\s+[1-8]\)", s):
            section = "legal"
            continue
        if s.startswith("## 9) câu hỏi mẫu cho tab cosing"):
            section = "cosing"
            continue
        m = re.match(r"^\s*-\s+(.+?)\s*$", line)
        if m:
            q = m.group(1).strip()
            if section == "legal":
                legal_questions.append(q)
            elif section == "cosing":
                cosing_questions.append(q)
    return legal_questions, cosing_questions


def is_insufficient(text: str | None) -> bool:
    if not text:
        return True
    t = text.strip().lower()
    markers = (
        "không đủ dữ liệu trong các văn bản đã cung cấp",
        "không đủ căn cứ trong các văn bản đã index",
        "not enough data in provided documents",
    )
    return any(m in t for m in markers)


async def main() -> None:
    legal_qs, cosing_qs = load_questions()
    print(f"Loaded {len(legal_qs)} legal questions + {len(cosing_qs)} CoSIng questions.", flush=True)

    legal_failures: list[tuple[str, str]] = []
    cosing_failures: list[tuple[str, str]] = []

    connect_timeout = _read_timeout("BATCH_HTTP_CONNECT_TIMEOUT_SECONDS")
    read_timeout = _read_timeout("BATCH_HTTP_READ_TIMEOUT_SECONDS")
    write_timeout = _read_timeout("BATCH_HTTP_WRITE_TIMEOUT_SECONDS")
    pool_timeout = _read_timeout("BATCH_HTTP_POOL_TIMEOUT_SECONDS")
    if connect_timeout is None and read_timeout is None and write_timeout is None and pool_timeout is None:
        timeout: httpx.Timeout | None = None
    else:
        timeout = httpx.Timeout(
            connect=connect_timeout,
            read=read_timeout,
            write=write_timeout,
            pool=pool_timeout,
        )
    async with httpx.AsyncClient(timeout=timeout) as client:
        print("\n=== TEST LEGAL (/chat) ===", flush=True)
        for i, q in enumerate(legal_qs, 1):
            print(f"[LEGAL {i}/{len(legal_qs)}] {q}", flush=True)
            try:
                r = await client.post(f"{API_BASE}/chat", json={"question": q, "top_k": 3})
            except Exception as e:
                legal_failures.append((q, f"HTTP ERROR: {e!s}"))
                continue
            if r.status_code != 200:
                legal_failures.append((q, f"HTTP {r.status_code}: {r.text[:200]}"))
                continue
            data = r.json()
            ans = data.get("answer", "")
            if is_insufficient(ans):
                legal_failures.append((q, ans))

        print("\n=== TEST COSING (/api/cosing/lookup) ===", flush=True)
        for i, q in enumerate(cosing_qs, 1):
            print(f"[COSING {i}/{len(cosing_qs)}] {q}", flush=True)
            try:
                r = await client.post(
                    f"{API_BASE}/api/cosing/lookup",
                    json={"query": q, "query_type": "NAME_OR_INCI"},
                )
            except Exception as e:
                cosing_failures.append((q, f"HTTP ERROR: {e!s}"))
                continue
            if r.status_code != 200:
                cosing_failures.append((q, f"HTTP {r.status_code}: {r.text[:200]}"))
                continue
            data = r.json()
            status = str(data.get("status", ""))
            subs = data.get("substances") or []
            if status != "OK" or len(subs) == 0:
                rr = data.get("rejection_reason", "")
                cosing_failures.append((q, f"status={status}; substances={len(subs)}; reason={rr}"))

    print("\n=== SUMMARY LEGAL ===", flush=True)
    print(f"Total: {len(legal_qs)}, Failures: {len(legal_failures)}", flush=True)
    for q, ans in legal_failures:
        print(f"- Câu: {q}", flush=True)
        print(f"  => {ans}", flush=True)

    print("\n=== SUMMARY COSING ===", flush=True)
    print(f"Total: {len(cosing_qs)}, Failures: {len(cosing_failures)}", flush=True)
    for q, ans in cosing_failures:
        print(f"- Câu: {q}", flush=True)
        print(f"  => {ans}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())

