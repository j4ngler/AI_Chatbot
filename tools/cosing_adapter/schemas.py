from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore


QueryType = Literal["NAME_OR_INCI"]


@dataclass(frozen=True)
class ChemicalLookupInput:
    query: str
    query_type: QueryType
    request_id: str


@dataclass
class Substance:
    substance_name: str = ""
    inci_name: str = ""
    cas: str = ""
    ec: str = ""
    function: str = ""
    restrictions: str = ""
    reference_url: str = ""
    fetched_at: str = ""
    # Trang chi tiết (sau khi enrich — xem COSING_ENRICH_DETAIL)
    description: str = ""
    regulation: str = ""
    annex_ref: str = ""
    functions_detail: str = ""
    sccs_opinions: str = ""
    max_concentration: str = ""
    glossary_name: str = ""
    ingredient_detail_url: str = ""
    related_substance_detail_url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ChemicalLookupOutput:
    request_id: str
    source: Literal["EU_COSING"] = "EU_COSING"
    substances: List[Substance] = None  # type: ignore[assignment]
    status: str = "OK"
    rejection_reason: Optional[str] = None

    def __post_init__(self) -> None:
        if self.substances is None:
            self.substances = []

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "request_id": self.request_id,
            "source": self.source,
            "substances": [s.to_dict() for s in self.substances],
            "status": self.status,
        }
        if self.rejection_reason:
            payload["rejection_reason"] = self.rejection_reason
        return payload


def vietnam_now_iso() -> str:
    """Return ISO timestamp in Asia/Ho_Chi_Minh when zoneinfo is available."""
    if ZoneInfo is None:
        return datetime.now(timezone.utc).isoformat()
    try:
        tz = ZoneInfo("Asia/Ho_Chi_Minh")
        return datetime.now(tz).isoformat()
    except Exception:
        # Fallback when OS doesn't ship timezone database.
        return datetime.now(timezone.utc).isoformat()

