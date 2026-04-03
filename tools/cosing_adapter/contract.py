from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

from .schemas import ChemicalLookupInput, QueryType


def normalize_query(query: str) -> str:
    return " ".join((query or "").strip().split())


def validate_input_contract(payload: Dict[str, Any]) -> ChemicalLookupInput:
    """
    Validate Input contract from spec:
    {
      "query": "Salicylic Acid",
      "query_type": "NAME_OR_INCI",
      "request_id": "REQ-2026-0001"
    }
    """
    if not isinstance(payload, dict):
        raise ValueError("Input contract phai la object JSON.")

    query = payload.get("query")
    query_type = payload.get("query_type")
    request_id = payload.get("request_id")

    if not isinstance(query, str) or not query.strip():
        raise ValueError("Truong 'query' bat buoc la string khong rong.")
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("Truong 'request_id' bat buoc la string khong rong.")
    if query_type not in ("NAME_OR_INCI",):
        raise ValueError("Truong 'query_type' chi ho tro gia tri: NAME_OR_INCI.")

    qt: QueryType = "NAME_OR_INCI"
    return ChemicalLookupInput(
        query=normalize_query(query),
        query_type=qt,
        request_id=request_id.strip(),
    )

