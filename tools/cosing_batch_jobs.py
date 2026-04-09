"""Job CoSIng batch chạy nền + poll tiến độ (cập nhật từng dòng)."""
from __future__ import annotations

import threading
import uuid
from typing import Any, Callable

_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def get_job(job_id: str) -> dict[str, Any] | None:
    with _lock:
        j = _jobs.get(job_id)
        if not j:
            return None
        return {
            "job_id": job_id,
            "status": j["status"],
            "total": j["total"],
            "done": j["done"],
            "current_query": j.get("current_query"),
            "error": j.get("error"),
            "summary": j.get("summary"),
            "rows": j.get("rows"),
            "result": j.get("result"),
        }


def start_batch_job_incremental(
    queries: list[str],
    lookup_one: Callable[[str, str], dict[str, Any]],
    base_request_id: str,
) -> str:
    job_id = uuid.uuid4().hex[:20]
    with _lock:
        _jobs[job_id] = {
            "status": "queued",
            "total": len(queries),
            "done": 0,
            "current_query": None,
            "error": None,
            "result": None,
            "rows": [],
            "summary": None,
        }

    def worker() -> None:
        with _lock:
            _jobs[job_id]["status"] = "running"
        ok_c = empty_c = err_c = 0
        rows: list[dict[str, Any]] = []
        try:
            for i, q in enumerate(queries):
                with _lock:
                    _jobs[job_id]["current_query"] = q
                    _jobs[job_id]["done"] = i
                rid = f"{base_request_id}-{i+1:03d}"
                try:
                    row = lookup_one(q, rid)
                except Exception as e:
                    err_c += 1
                    row = {
                        "query": q,
                        "status": "error",
                        "error": str(e),
                        "substances": [],
                        "result_count": 0,
                    }
                st = row.get("status")
                if st == "ok":
                    ok_c += 1
                elif st == "empty":
                    empty_c += 1
                else:
                    err_c += 1
                rows.append(row)
                with _lock:
                    _jobs[job_id]["rows"] = list(rows)
                    _jobs[job_id]["done"] = i + 1
            result = {
                "request_id": base_request_id,
                "source": "EU_COSING",
                "summary": {"total": len(queries), "ok": ok_c, "empty": empty_c, "error": err_c},
                "rows": rows,
            }
            with _lock:
                _jobs[job_id]["result"] = result
                _jobs[job_id]["summary"] = result["summary"]
                _jobs[job_id]["current_query"] = None
                _jobs[job_id]["status"] = "completed"
        except Exception as e:
            with _lock:
                _jobs[job_id]["status"] = "failed"
                _jobs[job_id]["error"] = str(e)
                _jobs[job_id]["current_query"] = None

    threading.Thread(target=worker, daemon=True, name=f"cosing-job-{job_id}").start()
    return job_id
