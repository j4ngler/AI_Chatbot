from __future__ import annotations

import os
from typing import Any

import requests
from dotenv import load_dotenv


def _load_env() -> None:
    base = os.getenv("PROJECT_ROOT")
    if base:
        load_dotenv(os.path.join(base, ".env"))


def ask_llm_ollama(base_url: str, model: str, system_prompt: str, user_prompt: str) -> str:
    # Ollama /api/chat expects messages with role/content
    url = base_url.rstrip("/") + "/api/chat"
    _load_env()
    try:
        temp = float(os.getenv("OLLAMA_TEMPERATURE", "0.15"))
    except ValueError:
        temp = 0.15
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": temp},
    }
    r = requests.post(url, json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    if "message" in data and "content" in data["message"]:
        return str(data["message"]["content"]).strip()
    if "response" in data:
        return str(data["response"]).strip()
    raise RuntimeError("Ollama trả response không theo format mong đợi.")


_REFLECT_SYSTEM = (
    "Chỉ trả lời một từ: YES hoặc NO (tiếng Anh in hoa). "
    "YES nếu câu trả lời (Answer) được hỗ trợ rõ ràng bởi phần Context (các nguồn SOURCE). "
    "NO nếu câu trả lời chủ yếu không bám Context hoặc có dấu hiệu bịa thông tin không có trong Context."
)


def reflect_answer_grounded(
    context_excerpt: str,
    answer: str,
    *,
    ollama_base: str,
    ollama_model: str,
) -> bool:
    """
    True = coi la bam context; False = khong bam.
    Neu khong goi duoc Ollama, tra True (khong chan user).
    """
    user = (
        f"Context (rut gon):\n{context_excerpt[:3500]}\n\n"
        f"Answer:\n{answer[:1500]}"
    )
    try:
        raw = ask_llm_ollama(ollama_base, ollama_model, _REFLECT_SYSTEM, user).upper()
    except Exception:
        return True

    if "NO" in raw and "YES" not in raw:
        return False
    if "YES" in raw:
        return True
    return True
