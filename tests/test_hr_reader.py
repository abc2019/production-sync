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


def event_row(**overrides):
    row = {
        "id": 1,
        "operation_key": "produced:plan_task:166",
        "event_type": "PRODUCED",
        "ombor_external_code": "DIMLAMA",
        "completed_units": 600,
        "created_at": "2026-09-11T06:21:00+00:00",
        "source_task_id": 166,
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_fetch_basic():
    rows = {0: [event_row()]}
    events = await hr_reader.fetch_production_sync_events(
        "http://hr.test", "secret", transport=make_transport(rows)
    )
    assert len(events) == 1
    assert events[0].ombor_external_code == "DIMLAMA"
    assert events[0].completed_units == 600
    assert events[0].event_type == "PRODUCED"
    assert events[0].operation_key == "produced:plan_task:166"
    assert events[0].source_task_id == 166


@pytest.mark.asyncio
async def test_defect_event_parsed():
    rows = {0: [event_row(id=2, operation_key="defect:plan_task:166:1", event_type="DEFECT", completed_units=10)]}
    events = await hr_reader.fetch_production_sync_events(
        "http://hr.test", "secret", transport=make_transport(rows)
    )
    assert events[0].event_type == "DEFECT"
    assert events[0].completed_units == 10


@pytest.mark.asyncio
async def test_sends_auth_header_and_params():
    captured = {}
    rows = {0: []}
    await hr_reader.fetch_production_sync_events(
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
        await hr_reader.fetch_production_sync_events(
            "http://hr.test", "wrong-token", transport=httpx.MockTransport(handler)
        )


@pytest.mark.asyncio
async def test_connection_error_wrapped():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(hr_reader.HRClientError):
        await hr_reader.fetch_production_sync_events(
            "http://hr.test", "token", transport=httpx.MockTransport(handler)
        )


@pytest.mark.asyncio
async def test_empty_response():
    events = await hr_reader.fetch_production_sync_events(
        "http://hr.test", "token", transport=make_transport({0: []})
    )
    assert events == []
