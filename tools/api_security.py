"""Audit log + helper kiểm tra API key (tùy chọn qua env)."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

_audit_lock = threading.Lock()


def api_key_configured() -> bool:
    return bool((os.getenv("API_KEY") or "").strip())


def get_expected_api_key() -> str:
    return (os.getenv("API_KEY") or "").strip()


def extract_provided_key(x_api_key: str | None, authorization: str | None) -> str | None:
    if x_api_key and x_api_key.strip():
        return x_api_key.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def audit_enabled() -> bool:
    return (os.getenv("AUDIT_LOG_ENABLED", "false") or "").strip().lower() in ("1", "true", "yes", "on")


def audit_log(project_root: Path, event: dict[str, Any]) -> None:
    if not audit_enabled():
        return
    rel = (os.getenv("AUDIT_LOG_PATH") or "logs/audit.jsonl").strip()
    path = project_root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **event}
    line = json.dumps(row, ensure_ascii=False) + "\n"
    with _audit_lock:
        with path.open("a", encoding="utf-8") as fp:
            fp.write(line)
