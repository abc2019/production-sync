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


def default_ombor_handler_factory(pushed: list, *, known_codes=None, mapping=None):
    """Soxta Ombor POST /production-batches/by-mapping: xaritadagi kod ->
    qismlar; xaritada yo'q, lekin known_codes'da bor -> o'sha mahsulot;
    aks holda 422 unmapped_codes. pushed'ga har qism bitta yozuv."""
    known_codes = known_codes or {"DIMLAMA": "prod-dimlama", "SPAGETTI": "prod-spagetti"}
    mapping = mapping or {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/production-batches/by-mapping":
            import json
            body = json.loads(request.content)
            assert body["system"] == "hr"
            parts = mapping.get(body["code"]) or ([body["code"]] if body["code"] in known_codes else [])
            if not parts:
                return httpx.Response(422, json={"detail": {"message": "m", "unmapped_codes": [body["code"]]}})
            for i, code in enumerate(parts):
                sid = body["source_id"] if len(parts) == 1 else f"{body['source_id']}#{i}"
                pushed.append({**body, "source_id": sid, "finished_product_id": known_codes.get(code, f"prod-{code}")})
            return httpx.Response(201, json={"code": body["code"], "events": [], "duplicate": False})
        return httpx.Response(404, json={"detail": "not found"})

    return handler


def make_ombor(handler):
    client = ModuleClient("http://ombor.test", transport=httpx.MockTransport(handler))
    return OmborBridgeClient(client)


@pytest.mark.asyncio
async def test_produced_event_pushed_by_code_ombor_resolves(state_db_path):
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
async def test_composite_code_sent_once_ombor_splits(state_db_path):
    """QOZON_KABOB = go'sht + fri - production-sync kodni o'zicha yuboradi, Ombor ajratadi."""
    events = [event(1, "produced:plan_task:7", "QOZON_KABOB", 300)]
    pushed = []
    ombor = make_ombor(default_ombor_handler_factory(
        pushed, mapping={"QOZON_KABOB": ["QOZON_KABOB_GOSHT", "QOZON_KABOB_FRI"]}))
    state = StateStore(state_db_path)
    summary = await sync_once(make_config(), ombor, state, hr_transport=hr_transport_with_events(events))
    assert summary.synced == 1 and summary.failed == 0
    assert [p["finished_product_id"] for p in pushed] == ["prod-QOZON_KABOB_GOSHT", "prod-QOZON_KABOB_FRI"]
    assert all(p["completed_units"] == "300" for p in pushed)
    state.close()


@pytest.mark.asyncio
async def test_unmapped_code_reason_points_to_ombor_bot(state_db_path):
    events = [event(1, "produced:plan_task:8", "UYGUR_LAGMON", 300)]
    ombor = make_ombor(default_ombor_handler_factory([]))
    state = StateStore(state_db_path)
    summary = await sync_once(make_config(), ombor, state, hr_transport=hr_transport_with_events(events))
    assert summary.failed == 1
    assert "UYGUR_LAGMON" in summary.failures[0][1] and "🔗 Mahsulot kodlari" in summary.failures[0][1]
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
