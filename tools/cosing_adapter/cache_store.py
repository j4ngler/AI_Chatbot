from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional

from .schemas import ChemicalLookupOutput, Substance


class ChemicalCacheStore:
    def __init__(self, cache_dir: Path, ttl_hours: int = 24) -> None:
        self.cache_dir = cache_dir
        self.ttl_seconds = ttl_hours * 3600
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key(self, query: str, query_type: str) -> str:
        raw = f"{query.strip().lower()}|{query_type.strip().upper()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def get(self, query: str, query_type: str) -> Optional[Dict[str, Any]]:
        key = self._key(query, query_type)
        p = self._path(key)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

        cached_at = data.get("cached_at", 0)
        if not isinstance(cached_at, (int, float)):
            cached_at = 0

        if time.time() - float(cached_at) > self.ttl_seconds:
            return None
        return data.get("payload")

    def set(
        self,
        query: str,
        query_type: str,
        output: ChemicalLookupOutput,
    ) -> None:
        key = self._key(query, query_type)
        p = self._path(key)
        payload = output.to_dict()
        wrapper = {"cached_at": time.time(), "payload": payload}
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(wrapper, ensure_ascii=False, indent=2), encoding="utf-8")
        # Atomic replace on most file systems
        tmp.replace(p)

