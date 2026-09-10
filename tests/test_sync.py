import httpx
import pytest

from erp_bridge_kit import ModuleClient, OmborBridgeClient

from app.config import Config
from app.state import StateStore
from app.sync import sync_once


def make_config():
    return Config(
        hr_internal_api_base_url="http://hr.test",
        hr_internal_api_token="secret",
        state_database_path=":memory:",
        ombor_api_base_url="http://ombor.test",
        ombor_actor_name="production-sync-test",
        poll_interval_seconds=1,
    )


def hr_transport_with_events(events: list[dict]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        since_id = int(dict(request.url.params).get("since_id", "0"))
        page = [e for e in events if e["id"] > since_id][:200]
        return httpx.Response(200, json=page)
    return httpx.MockTransport(handler)


def event(id, operation_key, ombor_external_code, completed_units, event_type="PRODUCED"):
    return {
        "id": id,
        "operation_key": operation_key,
        "event_type": event_type,
        "ombor_external_code": ombor_external_code,
        "completed_units": completed_units,
        "created_at": "2026-09-11T06:21:00+00:00",
        "source_task_id": 100 + id,
    }


def default_ombor_handler_factory(pushed: list, *, known_codes=None):
    known_codes = known_codes or {"DIMLAMA": "prod-dimlama", "SPAGETTI": "prod-spagetti"}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/products/by-code/"):
            code = request.url.path.rsplit("/", 1)[-1]
            if code in known_codes:
                return httpx.Response(200, json={"id": known_codes[code], "external_code": code})
            return httpx.Response(404, json={"detail": "topilmadi"})
        if request.url.path == "/production-batches":
            import json
            body = json.loads(request.content)
            pushed.append(body)
            return httpx.Response(201, json={"id": f"event-{len(pushed)}", "duplicate": False})
        return httpx.Response(404, json={"detail": "not found"})

    return handler


def make_ombor(handler):
    client = ModuleClient("http://ombor.test", transport=httpx.MockTransport(handler))
    return OmborBridgeClient(client)


@pytest.mark.asyncio
async def test_produced_event_pushed_with_resolved_product_id(state_db_path):
    events = [event(1, "produced:plan_task:166", "DIMLAMA", 600)]
    pushed = []
    ombor = make_ombor(default_ombor_handler_factory(pushed))
    state = StateStore(state_db_path)
    config = make_config()

    summary = await sync_once(config, ombor, state, hr_transport=hr_transport_with_events(events))

    assert summary.checked == 1
    assert summary.synced == 1
    assert summary.failed == 0
    assert pushed[0]["finished_product_id"] == "prod-dimlama"
    assert pushed[0]["completed_units"] == "600"
    assert pushed[0]["event_type"] == "PRODUCED"
    assert pushed[0]["source_id"] == "hr-event:produced:plan_task:166"
    assert state.get_synced_keys() == {"produced:plan_task:166"}
    state.close()


@pytest.mark.asyncio
async def test_defect_event_forwarded_with_defect_type(state_db_path):
    events = [event(1, "defect:plan_task:166:1", "DIMLAMA", 10, event_type="DEFECT")]
    pushed = []
    ombor = make_ombor(default_ombor_handler_factory(pushed))
    state = StateStore(state_db_path)
    config = make_config()

    summary = await sync_once(config, ombor, state, hr_transport=hr_transport_with_events(events))

    assert summary.synced == 1
    assert pushed[0]["event_type"] == "DEFECT"
    assert pushed[0]["completed_units"] == "10"
    state.close()


@pytest.mark.asyncio
async def test_unknown_external_code_marked_failed_and_retried(state_db_path):
    events = [event(1, "produced:plan_task:999", "NOMALUM_KOD", 300)]
    pushed = []
    ombor = make_ombor(default_ombor_handler_factory(pushed))
    state = StateStore(state_db_path)
    config = make_config()

    summary = await sync_once(config, ombor, state, hr_transport=hr_transport_with_events(events))
    assert summary.failed == 1
    assert pushed == []
    assert state.get_synced_keys() == set()  # keyingi safar qayta uriniladi
    state.close()


@pytest.mark.asyncio
async def test_ombor_push_failure_marks_failed_and_retries(state_db_path):
    events = [event(1, "produced:plan_task:1", "DIMLAMA", 300)]

    def failing_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/products/by-code/"):
            return httpx.Response(200, json={"id": "prod-dimlama", "external_code": "DIMLAMA"})
        return httpx.Response(500, text="internal error")

    ombor = make_ombor(failing_handler)
    state = StateStore(state_db_path)
    config = make_config()

    summary = await sync_once(config, ombor, state, hr_transport=hr_transport_with_events(events))
    assert summary.failed == 1
    assert state.get_synced_keys() == set()

    pushed = []
    ombor2 = make_ombor(default_ombor_handler_factory(pushed))
    summary2 = await sync_once(config, ombor2, state, hr_transport=hr_transport_with_events(events))
    assert summary2.checked == 1
    assert summary2.synced == 1
    state.close()


@pytest.mark.asyncio
async def test_already_synced_event_not_reprocessed(state_db_path):
    events = [event(1, "produced:plan_task:1", "DIMLAMA", 300)]
    pushed = []
    ombor = make_ombor(default_ombor_handler_factory(pushed))
    state = StateStore(state_db_path)
    config = make_config()

    summary1 = await sync_once(config, ombor, state, hr_transport=hr_transport_with_events(events))
    assert summary1.synced == 1

    summary2 = await sync_once(config, ombor, state, hr_transport=hr_transport_with_events(events))
    assert summary2.checked == 0
    assert len(pushed) == 1
    state.close()


@pytest.mark.asyncio
async def test_multiple_events_same_code_resolved_once(state_db_path):
    events = [
        event(1, "produced:plan_task:1", "DIMLAMA", 300),
        event(2, "produced:plan_task:2", "DIMLAMA", 150),
    ]
    lookups = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/products/by-code/"):
            lookups.append(request.url.path)
            return httpx.Response(200, json={"id": "prod-dimlama", "external_code": "DIMLAMA"})
        if request.url.path == "/production-batches":
            return httpx.Response(201, json={"id": "e", "duplicate": False})
        return httpx.Response(404)

    ombor = make_ombor(handler)
    state = StateStore(state_db_path)
    config = make_config()

    summary = await sync_once(config, ombor, state, hr_transport=hr_transport_with_events(events))
    assert summary.synced == 2
    assert len(lookups) == 1  # faqat bir marta so'ralgan (keш orqali)
    state.close()


@pytest.mark.asyncio
async def test_pagination_across_multiple_events(state_db_path):
    events = [event(i, f"produced:plan_task:{i}", "DIMLAMA", 10) for i in range(1, 6)]
    pushed = []
    ombor = make_ombor(default_ombor_handler_factory(pushed))
    state = StateStore(state_db_path)
    config = make_config()

    summary = await sync_once(config, ombor, state, hr_transport=hr_transport_with_events(events))
    assert summary.synced == 5
    state.close()


@pytest.mark.asyncio
async def test_skips_when_ombor_not_configured(state_db_path):
    events = [event(1, "produced:plan_task:1", "DIMLAMA", 300)]
    ombor = OmborBridgeClient(ModuleClient(None))
    state = StateStore(state_db_path)
    config = make_config()

    summary = await sync_once(config, ombor, state, hr_transport=hr_transport_with_events(events))
    assert summary.skipped_ombor_not_configured is True
    assert summary.checked == 0
    state.close()


@pytest.mark.asyncio
async def test_no_events_is_a_noop(state_db_path):
    ombor = make_ombor(default_ombor_handler_factory([]))
    state = StateStore(state_db_path)
    config = make_config()

    summary = await sync_once(config, ombor, state, hr_transport=hr_transport_with_events([]))
    assert summary.checked == 0
    assert summary.synced == 0
    state.close()
