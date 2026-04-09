"""Smoke tests cho endpoint mở rộng (không bật API_KEY trong môi trường test mặc định)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> TestClient:
    # Import sau khi cwd là project root (pytest thường chạy từ đó).
    from api.main import app

    return TestClient(app)


def test_api_health(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_external_sources_list(client: TestClient) -> None:
    r = client.get("/api/external-sources")
    assert r.status_code == 200
    data = r.json()
    assert "sources" in data
    assert isinstance(data["sources"], list)


def test_external_fetch_unknown_source(client: TestClient) -> None:
    r = client.post("/api/external/fetch", json={"source_id": "definitely_missing_xyz", "query": "test"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is False


def test_cosing_batch_job_not_found(client: TestClient) -> None:
    r = client.get("/api/cosing/lookup/batch/jobs/does-not-exist-000")
    assert r.status_code == 404


def test_ingest_get_missing(client: TestClient) -> None:
    r = client.get("/api/ingest/nonexistentid000000")
    assert r.status_code == 404


def test_tools_translate_schema(client: TestClient) -> None:
    r = client.post("/api/tools/translate", json={"text": "hello world", "target_lang": "vi"})
    if r.status_code == 401:
        pytest.skip("Đang bật API_KEY — thêm X-API-Key hoặc tắt key trong .env để test tự động.")
    assert r.status_code == 200
    j = r.json()
    assert "ok" in j
    assert "target_lang" in j


def test_tools_summarize_schema(client: TestClient) -> None:
    r = client.post("/api/tools/summarize", json={"text": "Một đoạn văn ngắn để tóm tắt."})
    if r.status_code == 401:
        pytest.skip("Đang bật API_KEY — thêm X-API-Key hoặc tắt key trong .env để test tự động.")
    assert r.status_code == 200
    j = r.json()
    assert "ok" in j


def test_batch_empty_sync_summary() -> None:
    """Logic đếm status đồng bộ giữa job incremental và batch sync (không gọi Selenium)."""
    from api.main import _cosing_lookup_batch_sync

    out = _cosing_lookup_batch_sync([], "empty-sync-test")
    assert out["summary"]["total"] == 0
    assert out["rows"] == []
