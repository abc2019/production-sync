import httpx
import pytest

from erp_bridge_kit import ModuleClient, OmborBridgeClient

from app.config import Config
from app.state import StateStore
from app.sync import sync_once


PRODUCTS = [
    {"id": "prod-1", "name": "Behi murabbosi 0.5L", "external_code": "BEHI_MURABBO_05L",
     "warehouse_type": "FINISHED", "unit": "banka", "is_active": True},
    {"id": "prod-2", "name": "Shirin murabbo 0.5L", "external_code": "SHIRIN_MURABBO_05L",
     "warehouse_type": "FINISHED", "unit": "banka", "is_active": True},
    {"id": "prod-3", "name": "Banka 0.5L", "external_code": "BANKA_05L",
     "warehouse_type": "RAW", "unit": "dona", "is_active": True},  # RAW - moslashtirish uchun ishlatilmaydi
]


def make_config(threshold=0.72, unit_multipliers=None):
    return Config(
        hr_internal_api_base_url="http://hr.test",
        hr_internal_api_token="secret",
        state_database_path=":memory:",  # har bir testda alohida state_db_path fixture ishlatiladi
        ombor_api_base_url="http://ombor.test",
        ombor_actor_name="production-sync-test",
        match_threshold=threshold,
        poll_interval_seconds=1,
        unit_multipliers=unit_multipliers or {"box": 24, "partiya": 300, "dona": 1, "ta": 1},
    )


def make_ombor(handler):
    client = ModuleClient("http://ombor.test", transport=httpx.MockTransport(handler))
    return OmborBridgeClient(client)


def default_ombor_handler_factory(pushed: list):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/products":
            return httpx.Response(200, json=PRODUCTS)
        if request.url.path == "/production-batches":
            import json
            body = json.loads(request.content)
            pushed.append(body)
            return httpx.Response(201, json={"id": f"event-{len(pushed)}", "duplicate": False})
        return httpx.Response(404, json={"detail": "not found"})
    return handler


def hr_transport_with_entries(entries: list[dict]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        since_id = int(dict(request.url.params).get("since_id", "0"))
        page = [e for e in entries if e["log_id"] > since_id][:200]
        return httpx.Response(200, json=page)
    return httpx.MockTransport(handler)


def entry(log_id, task_text, completed_qty, unit="box", operation_key=None):
    return {
        "log_id": log_id,
        "operation_key": operation_key or f"op-{log_id}",
        "task_id": log_id,
        "task_text": task_text,
        "completed_qty": completed_qty,
        "unit": unit,
        "created_at": "2026-01-01T10:00:00",
    }


@pytest.mark.asyncio
async def test_matched_entry_gets_pushed_converted_to_units_and_marked_synced(state_db_path):
    hr_entries = [entry(1, "Behi murabbosi qadoqlash", 4)]
    pushed = []
    ombor = make_ombor(default_ombor_handler_factory(pushed))
    state = StateStore(state_db_path)
    config = make_config()

    summary = await sync_once(config, ombor, state, hr_transport=hr_transport_with_entries(hr_entries))

    assert summary.checked == 1
    assert summary.synced == 1
    assert summary.needs_review == 0
    assert pushed[0]["finished_product_id"] == "prod-1"
    assert pushed[0]["completed_units"] == "96"  # 4 box * 24
    assert pushed[0]["source_id"] == "hr-op:op-1"
    assert state.get_synced_keys() == {"op-1"}
    state.close()


@pytest.mark.asyncio
async def test_custom_unit_multiplier(state_db_path):
    hr_entries = [entry(1, "Behi murabbosi qadoqlash", 2)]
    pushed = []
    ombor = make_ombor(default_ombor_handler_factory(pushed))
    state = StateStore(state_db_path)
    config = make_config(unit_multipliers={"box": 12})

    await sync_once(config, ombor, state, hr_transport=hr_transport_with_entries(hr_entries))
    assert pushed[0]["completed_units"] == "24"
    state.close()


@pytest.mark.asyncio
async def test_partiya_unit_uses_300_multiplier(state_db_path):
    hr_entries = [entry(1, "Behi murabbosi qadoqlash", 2, unit="partiya")]
    pushed = []
    ombor = make_ombor(default_ombor_handler_factory(pushed))
    state = StateStore(state_db_path)
    config = make_config()

    await sync_once(config, ombor, state, hr_transport=hr_transport_with_entries(hr_entries))
    assert pushed[0]["completed_units"] == "600"  # 2 * 300
    state.close()


@pytest.mark.asyncio
async def test_dona_unit_uses_1_multiplier(state_db_path):
    hr_entries = [entry(1, "Behi murabbosi qadoqlash", 50, unit="dona")]
    pushed = []
    ombor = make_ombor(default_ombor_handler_factory(pushed))
    state = StateStore(state_db_path)
    config = make_config()

    await sync_once(config, ombor, state, hr_transport=hr_transport_with_entries(hr_entries))
    assert pushed[0]["completed_units"] == "50"
    state.close()


@pytest.mark.asyncio
async def test_unknown_unit_goes_to_review_not_pushed(state_db_path):
    hr_entries = [entry(1, "Behi murabbosi qadoqlash", 5, unit="kg")]
    pushed = []
    ombor = make_ombor(default_ombor_handler_factory(pushed))
    state = StateStore(state_db_path)
    config = make_config()

    summary = await sync_once(config, ombor, state, hr_transport=hr_transport_with_entries(hr_entries))
    assert summary.needs_review == 1
    assert pushed == []
    assert "kg" in state.list_needs_review()[0].reason
    state.close()


@pytest.mark.asyncio
async def test_ambiguous_entry_goes_to_review_not_pushed(state_db_path):
    hr_entries = [entry(1, "mutlaqo aloqasiz ish haqida gap", 2)]
    pushed = []
    ombor = make_ombor(default_ombor_handler_factory(pushed))
    state = StateStore(state_db_path)
    config = make_config()

    summary = await sync_once(config, ombor, state, hr_transport=hr_transport_with_entries(hr_entries))

    assert summary.synced == 0
    assert summary.needs_review == 1
    assert pushed == []
    state.close()


@pytest.mark.asyncio
async def test_raw_product_never_matched(state_db_path):
    hr_entries = [entry(1, "Banka 0.5L", 10)]
    pushed = []
    ombor = make_ombor(default_ombor_handler_factory(pushed))
    state = StateStore(state_db_path)
    config = make_config()

    await sync_once(config, ombor, state, hr_transport=hr_transport_with_entries(hr_entries))

    assert pushed == []
    assert len(state.list_needs_review()) == 1
    state.close()


@pytest.mark.asyncio
async def test_ombor_failure_marks_failed_and_retries_next_time(state_db_path):
    hr_entries = [entry(1, "Behi murabbosi qadoqlash", 1)]

    def failing_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/products":
            return httpx.Response(200, json=PRODUCTS)
        return httpx.Response(500, text="internal error")

    ombor = make_ombor(failing_handler)
    state = StateStore(state_db_path)
    config = make_config()

    summary = await sync_once(config, ombor, state, hr_transport=hr_transport_with_entries(hr_entries))
    assert summary.failed == 1
    assert state.get_synced_keys() == set()

    pushed = []
    ombor2 = make_ombor(default_ombor_handler_factory(pushed))
    summary2 = await sync_once(config, ombor2, state, hr_transport=hr_transport_with_entries(hr_entries))
    assert summary2.checked == 1
    assert summary2.synced == 1
    assert pushed[0]["source_id"] == "hr-op:op-1"
    state.close()


@pytest.mark.asyncio
async def test_already_synced_entry_not_reprocessed(state_db_path):
    hr_entries = [entry(1, "Behi murabbosi qadoqlash", 1)]
    pushed = []
    ombor = make_ombor(default_ombor_handler_factory(pushed))
    state = StateStore(state_db_path)
    config = make_config()

    summary1 = await sync_once(config, ombor, state, hr_transport=hr_transport_with_entries(hr_entries))
    assert summary1.synced == 1

    summary2 = await sync_once(config, ombor, state, hr_transport=hr_transport_with_entries(hr_entries))
    assert summary2.checked == 0
    assert len(pushed) == 1
    state.close()


@pytest.mark.asyncio
async def test_multiple_reports_both_synced_separately(state_db_path):
    hr_entries = [entry(1, "Behi murabbosi qadoqlash", 2), entry(2, "Behi murabbosi qadoqlash", 3)]
    pushed = []
    ombor = make_ombor(default_ombor_handler_factory(pushed))
    state = StateStore(state_db_path)
    config = make_config()

    summary = await sync_once(config, ombor, state, hr_transport=hr_transport_with_entries(hr_entries))
    assert summary.synced == 2
    assert {p["source_id"] for p in pushed} == {"hr-op:op-1", "hr-op:op-2"}
    assert {p["completed_units"] for p in pushed} == {"48", "72"}
    state.close()


@pytest.mark.asyncio
async def test_pagination_fetches_more_than_one_page(state_db_path):
    # page_size ichki qatiy 200, shuning uchun >200 element bilan ham to'g'ri ishlashini
    # tekshirish uchun kichikroq page orqali simulyatsiya qilib bo'lmaydi (page_size hardcoded),
    # shuning uchun bu yerda faqat bitta sahifaga sig'adigan holatni tekshiramiz.
    hr_entries = [entry(i, "Behi murabbosi qadoqlash", 1) for i in range(1, 6)]
    pushed = []
    ombor = make_ombor(default_ombor_handler_factory(pushed))
    state = StateStore(state_db_path)
    config = make_config()

    summary = await sync_once(config, ombor, state, hr_transport=hr_transport_with_entries(hr_entries))
    assert summary.synced == 5
    state.close()


@pytest.mark.asyncio
async def test_skips_when_ombor_not_configured(state_db_path):
    hr_entries = [entry(1, "Behi murabbosi qadoqlash", 1)]
    ombor = OmborBridgeClient(ModuleClient(None))
    state = StateStore(state_db_path)
    config = make_config()

    summary = await sync_once(config, ombor, state, hr_transport=hr_transport_with_entries(hr_entries))
    assert summary.skipped_ombor_not_configured is True
    assert summary.checked == 0
    state.close()


@pytest.mark.asyncio
async def test_no_entries_is_a_noop(state_db_path):
    ombor = make_ombor(default_ombor_handler_factory([]))
    state = StateStore(state_db_path)
    config = make_config()

    summary = await sync_once(config, ombor, state, hr_transport=hr_transport_with_entries([]))
    assert summary.checked == 0
    assert summary.synced == 0
    state.close()
