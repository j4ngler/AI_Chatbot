from __future__ import annotations

import os
from typing import Any

import requests
from dotenv import load_dotenv
from openai import OpenAI
import google.generativeai as genai


def _load_env() -> None:
    # load once
    base = os.getenv("PROJECT_ROOT")
    if base:
        load_dotenv(os.path.join(base, ".env"))


def ask_llm_openai(api_key: str, model: str, system_prompt: str, user_prompt: str) -> str:
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return resp.choices[0].message.content.strip()


def ask_llm_ollama(base_url: str, model: str, system_prompt: str, user_prompt: str) -> str:
    # Ollama /api/chat expects messages with role/content
    url = base_url.rstrip("/") + "/api/chat"
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
    }
    r = requests.post(url, json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    # Typical: {"message":{"role":"assistant","content":"..."}, ...}
    if "message" in data and "content" in data["message"]:
        return str(data["message"]["content"]).strip()
    # Fallback
    if "response" in data:
        return str(data["response"]).strip()
    raise RuntimeError("Ollama trả response không theo format mong đợi.")


def ask_llm_gemini(api_key: str, model: str, system_prompt: str, user_prompt: str) -> str:
    """
    Gọi Gemini bằng SDK `google-generativeai`.
    Mặc dù library đã được thông báo deprecated, nhưng vẫn hoạt động ổn
    và đơn giản hơn trong bối cảnh demo nội bộ hiện tại.
    """
    genai.configure(api_key=api_key)
    full_prompt = f"{system_prompt}\n\n{user_prompt}"
    model_obj = genai.GenerativeModel(model)
    resp = model_obj.generate_content(full_prompt)
    return (resp.text or "").strip()

