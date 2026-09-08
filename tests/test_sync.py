import httpx
import pytest

from erp_bridge_kit import ModuleClient, OmborBridgeClient

from app.config import Config
from app.state import StateStore
from app.sync import sync_once
from tests.conftest import insert_task


PRODUCTS = [
    {"id": "prod-1", "name": "Behi murabbosi 0.5L", "external_code": "BEHI_MURABBO_05L",
     "warehouse_type": "FINISHED", "unit": "banka", "is_active": True},
    {"id": "prod-2", "name": "Shirin murabbo 0.5L", "external_code": "SHIRIN_MURABBO_05L",
     "warehouse_type": "FINISHED", "unit": "banka", "is_active": True},
    {"id": "prod-3", "name": "Banka 0.5L", "external_code": "BANKA_05L",
     "warehouse_type": "RAW", "unit": "dona", "is_active": True},  # RAW - moslashtirish uchun ishlatilmaydi
]


def make_config(hr_db_path, state_db_path, threshold=0.72):
    return Config(
        hr_database_path=hr_db_path,
        state_database_path=state_db_path,
        ombor_api_base_url="http://ombor.test",
        ombor_actor_name="production-sync-test",
        match_threshold=threshold,
        poll_interval_seconds=1,
    )


def make_ombor(handler):
    client = ModuleClient("http://ombor.test", transport=httpx.MockTransport(handler))
    return OmborBridgeClient(client)


def default_handler_factory(pushed: list):
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


@pytest.mark.asyncio
async def test_matched_task_gets_pushed_and_marked_synced(hr_db_path, state_db_path):
    task_id = insert_task(hr_db_path, task_text="Behi murabbosi qadoqlash", completed_qty=4)
    pushed = []
    ombor = make_ombor(default_handler_factory(pushed))
    state = StateStore(state_db_path)
    config = make_config(hr_db_path, state_db_path)

    summary = await sync_once(config, ombor, state)

    assert summary.checked == 1
    assert summary.synced == 1
    assert summary.needs_review == 0
    assert pushed[0]["finished_product_id"] == "prod-1"
    assert pushed[0]["batch_count"] == 4
    assert pushed[0]["source_id"] == f"hr-task:{task_id}"
    assert state.get_processed_task_ids() == {task_id}
    state.close()


@pytest.mark.asyncio
async def test_ambiguous_task_goes_to_review_not_pushed(hr_db_path, state_db_path):
    insert_task(hr_db_path, task_text="mutlaqo aloqasiz ish haqida gap", completed_qty=2)
    pushed = []
    ombor = make_ombor(default_handler_factory(pushed))
    state = StateStore(state_db_path)
    config = make_config(hr_db_path, state_db_path)

    summary = await sync_once(config, ombor, state)

    assert summary.synced == 0
    assert summary.needs_review == 1
    assert pushed == []
    assert len(state.list_needs_review()) == 1
    state.close()


@pytest.mark.asyncio
async def test_raw_product_never_matched(hr_db_path, state_db_path):
    # "Banka 0.5L" RAW omborga tegishli - ishlab chiqarish (FINISHED) sifatida hech qachon tanlanmasligi kerak
    insert_task(hr_db_path, task_text="Banka 0.5L", completed_qty=10)
    pushed = []
    ombor = make_ombor(default_handler_factory(pushed))
    state = StateStore(state_db_path)
    config = make_config(hr_db_path, state_db_path)

    await sync_once(config, ombor, state)

    assert pushed == []
    assert len(state.list_needs_review()) == 1
    state.close()


@pytest.mark.asyncio
async def test_ombor_failure_marks_failed_and_retries_next_time(hr_db_path, state_db_path):
    def failing_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/products":
            return httpx.Response(200, json=PRODUCTS)
        return httpx.Response(500, text="internal error")

    task_id = insert_task(hr_db_path, task_text="Behi murabbosi qadoqlash", completed_qty=1)
    ombor = make_ombor(failing_handler)
    state = StateStore(state_db_path)
    config = make_config(hr_db_path, state_db_path)

    summary = await sync_once(config, ombor, state)
    assert summary.failed == 1
    assert state.get_processed_task_ids() == set()  # qayta urinish uchun chetlanmagan

    # Ombor tuzatildi deb faraz qilamiz — keyingi tsikl xuddi shu taskni qayta ko'radi
    pushed = []
    ombor2 = make_ombor(default_handler_factory(pushed))
    summary2 = await sync_once(config, ombor2, state)
    assert summary2.checked == 1
    assert summary2.synced == 1
    assert pushed[0]["source_id"] == f"hr-task:{task_id}"
    state.close()


@pytest.mark.asyncio
async def test_already_synced_task_not_reprocessed(hr_db_path, state_db_path):
    insert_task(hr_db_path, task_text="Behi murabbosi qadoqlash", completed_qty=1)
    pushed = []
    ombor = make_ombor(default_handler_factory(pushed))
    state = StateStore(state_db_path)
    config = make_config(hr_db_path, state_db_path)

    summary1 = await sync_once(config, ombor, state)
    assert summary1.synced == 1

    summary2 = await sync_once(config, ombor, state)
    assert summary2.checked == 0
    assert len(pushed) == 1  # ikkinchi marta push qilinmadi
    state.close()


@pytest.mark.asyncio
async def test_skips_when_ombor_not_configured(hr_db_path, state_db_path):
    insert_task(hr_db_path, task_text="Behi murabbosi qadoqlash", completed_qty=1)
    ombor = OmborBridgeClient(ModuleClient(None))
    state = StateStore(state_db_path)
    config = make_config(hr_db_path, state_db_path)

    summary = await sync_once(config, ombor, state)
    assert summary.skipped_ombor_not_configured is True
    assert summary.checked == 0
    state.close()


@pytest.mark.asyncio
async def test_no_completed_tasks_is_a_noop(hr_db_path, state_db_path):
    ombor = make_ombor(default_handler_factory([]))
    state = StateStore(state_db_path)
    config = make_config(hr_db_path, state_db_path)

    summary = await sync_once(config, ombor, state)
    assert summary.checked == 0
    assert summary.synced == 0
    state.close()
