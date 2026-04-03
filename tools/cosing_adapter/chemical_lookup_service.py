from __future__ import annotations

from typing import Any, Dict

from .cache_store import ChemicalCacheStore
from .cosing_worker_selenium import CosingSeleniumWorker
from .schemas import ChemicalLookupOutput, QueryType
from .contract import normalize_query, validate_input_contract


class ChemicalLookupService:
    def __init__(self, cache_store: ChemicalCacheStore, worker: CosingSeleniumWorker) -> None:
        self.cache_store = cache_store
        self.worker = worker

    def lookup(self, query: str, query_type: QueryType, request_id: str) -> ChemicalLookupOutput:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id bat buoc khong rong.")
        if query_type != "NAME_OR_INCI":
            raise ValueError("query_type chi ho tro NAME_OR_INCI.")

        q = normalize_query(query)
        if not q:
            raise ValueError("query khong duoc rong.")

        cached = self.cache_store.get(q, str(query_type))
        if cached:
            # cached is payload dict for ChemicalLookupOutput.to_dict()
            out = ChemicalLookupOutput(
                request_id=request_id,
                source=cached.get("source", "EU_COSING"),
                substances=[],  # we will hydrate below
                status=cached.get("status", "OK"),
            )
            out_dict = cached
            out.rejection_reason = out_dict.get("rejection_reason")
            # We don't need Substance objects here strictly for output correctness,
            # but we keep consistent type usage by leaving raw dicts -> convert.
            substances = out_dict.get("substances", []) or []
            from .schemas import Substance

            out.substances = [Substance(**s) for s in substances]
            return out

        output = self.worker.fetch(query=q, query_type=query_type, request_id=request_id)
        self.cache_store.set(q, str(query_type), output)

        return output

    def lookup_payload(self, payload: Dict[str, Any]) -> ChemicalLookupOutput:
        """
        Convenience wrapper for Input contract dict (spec).
        """
        validated = validate_input_contract(payload)
        return self.lookup(
            query=validated.query,
            query_type=validated.query_type,
            request_id=validated.request_id,
        )

