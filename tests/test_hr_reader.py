import httpx
import pytest

from app import hr_reader


def make_transport(rows_by_since_id: dict[int, list[dict]], captured: dict | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        since_id = int(params.get("since_id", "0"))
        if captured is not None:
            captured["last_headers"] = dict(request.headers)
            captured["last_params"] = params
        rows = rows_by_since_id.get(since_id, [])
        return httpx.Response(200, json=rows)
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_fetch_basic():
    rows = {0: [{"log_id": 1, "operation_key": "op-1", "task_id": 1,
                 "task_text": "Behi murabbosi qadoqlash", "completed_qty": 5,
                 "unit": "box", "created_at": "2026-01-01T10:00:00"}]}
    entries = await hr_reader.fetch_production_log_entries(
        "http://hr.test", "secret", transport=make_transport(rows)
    )
    assert len(entries) == 1
    assert entries[0].task_text == "Behi murabbosi qadoqlash"
    assert entries[0].completed_qty == 5
    assert entries[0].sync_key == "op-1"


@pytest.mark.asyncio
async def test_sync_key_falls_back_to_log_id_when_no_operation_key():
    rows = {0: [{"log_id": 7, "operation_key": None, "task_id": 1,
                 "task_text": "X", "completed_qty": 3, "unit": "box",
                 "created_at": "2026-01-01T10:00:00"}]}
    entries = await hr_reader.fetch_production_log_entries(
        "http://hr.test", "secret", transport=make_transport(rows)
    )
    assert entries[0].sync_key == "log-7"


@pytest.mark.asyncio
async def test_sends_auth_header_and_params():
    captured = {}
    rows = {0: []}
    await hr_reader.fetch_production_log_entries(
        "http://hr.test", "my-secret-token", since_id=0, limit=50,
        transport=make_transport(rows, captured),
    )
    assert captured["last_headers"]["x-internal-token"] == "my-secret-token"
    assert captured["last_params"]["since_id"] == "0"
    assert captured["last_params"]["limit"] == "50"


@pytest.mark.asyncio
async def test_http_error_wrapped():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    with pytest.raises(hr_reader.HRClientError):
        await hr_reader.fetch_production_log_entries(
            "http://hr.test", "wrong-token", transport=httpx.MockTransport(handler)
        )


@pytest.mark.asyncio
async def test_connection_error_wrapped():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(hr_reader.HRClientError):
        await hr_reader.fetch_production_log_entries(
            "http://hr.test", "token", transport=httpx.MockTransport(handler)
        )


@pytest.mark.asyncio
async def test_empty_response():
    entries = await hr_reader.fetch_production_log_entries(
        "http://hr.test", "token", transport=make_transport({0: []})
    )
    assert entries == []
