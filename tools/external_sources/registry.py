"""
Nguồn ngoài khai báo qua env, bật/tắt từng nguồn, có nhãn hiển thị.

Mỗi nguồn (tối đa 8): EXTERNAL_SOURCE_<ID>_ENABLED, _LABEL, _URL_TEMPLATE
<ID> viết hoa, ví dụ DEMO_HTTP.

URL_TEMPLATE hỗ trợ {query} (URL-encoded khi gọi).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlparse

import requests


@dataclass(frozen=True)
class ExternalSourceSpec:
    source_id: str
    label: str
    enabled: bool
    url_template: str


def _truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in ("1", "true", "yes", "on")


def _discover_source_ids() -> list[str]:
    ids: set[str] = set()
    for key in os.environ:
        if key.startswith("EXTERNAL_SOURCE_") and key.endswith("_ENABLED"):
            # EXTERNAL_SOURCE_DEMO_HTTP_ENABLED -> DEMO_HTTP
            mid = key[len("EXTERNAL_SOURCE_") : -len("_ENABLED")]
            if mid:
                ids.add(mid)
    return sorted(ids)


def list_external_sources() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sid in _discover_source_ids():
        en = _truthy(os.getenv(f"EXTERNAL_SOURCE_{sid}_ENABLED"))
        label = (os.getenv(f"EXTERNAL_SOURCE_{sid}_LABEL") or sid).strip() or sid
        url_t = (os.getenv(f"EXTERNAL_SOURCE_{sid}_URL_TEMPLATE") or "").strip()
        out.append(
            {
                "id": sid.lower(),
                "label": label,
                "enabled": en,
                "configured": bool(url_t),
            }
        )
    return out


def _get_spec(source_id: str) -> ExternalSourceSpec | None:
    sid = source_id.strip().upper().replace("-", "_").replace(".", "_")
    if not sid:
        return None
    prefix = f"EXTERNAL_SOURCE_{sid}_"
    if not _truthy(os.getenv(prefix + "ENABLED")):
        return None
    label = (os.getenv(prefix + "LABEL") or sid).strip() or sid
    url_t = (os.getenv(prefix + "URL_TEMPLATE") or "").strip()
    if not url_t:
        return None
    return ExternalSourceSpec(source_id=sid.lower(), label=label, enabled=True, url_template=url_t)


def fetch_external(source_id: str, query: str, *, timeout_sec: float = 20.0) -> dict[str, Any]:
    q = (query or "").strip()
    if not q:
        return {
            "ok": False,
            "source_id": source_id,
            "source_label": "",
            "error": "query rỗng",
            "data": None,
        }
    spec = _get_spec(source_id)
    if spec is None:
        return {
            "ok": False,
            "source_id": source_id,
            "source_label": "",
            "error": "Nguồn không tồn tại hoặc đang tắt / thiếu URL_TEMPLATE.",
            "data": None,
        }
    try:
        tpl = spec.url_template
        if "{query}" in tpl:
            url = tpl.replace("{query}", quote(q, safe=""))
        else:
            sep = "&" if "?" in tpl else "?"
            url = f"{tpl.rstrip('?&')}{sep}q={quote(q)}"
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Chỉ cho phép http/https")
        r = requests.get(url, timeout=timeout_sec)
        r.raise_for_status()
        ct = (r.headers.get("content-type") or "").lower()
        if "application/json" in ct or url.endswith("format=json"):
            try:
                data: Any = r.json()
            except Exception:
                data = {"raw": r.text[:8000]}
        else:
            data = {"text": r.text[:8000]}
        return {
            "ok": True,
            "source_id": spec.source_id,
            "source_label": spec.label,
            "error": None,
            "data": data,
            "fetched_url": url.split("?")[0] + ("" if "?" not in url else "?…"),
        }
    except Exception as e:
        return {
            "ok": False,
            "source_id": source_id,
            "source_label": spec.label,
            "error": str(e),
            "data": None,
        }
