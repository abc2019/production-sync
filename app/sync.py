import logging
from dataclasses import dataclass

from erp_bridge_kit import BridgeError, OmborBridgeClient, build_source_id

from app import hr_reader
from app.config import Config
from app.state import StateStore

logger = logging.getLogger(__name__)


@dataclass
class SyncSummary:
    checked: int = 0
    synced: int = 0
    failed: int = 0
    skipped_ombor_not_configured: bool = False


async def _fetch_all_events(
    config: Config, transport=None
) -> list[hr_reader.ProductionSyncEvent]:
    """HR'ning ichki API'sidan barcha sahifalarni (pagination) yig'ib oladi."""
    events: list[hr_reader.ProductionSyncEvent] = []
    since_id = 0
    page_size = 200
    while True:
        page = await hr_reader.fetch_production_sync_events(
            config.hr_internal_api_base_url,
            config.hr_internal_api_token,
            since_id=since_id,
            limit=page_size,
            transport=transport,
        )
        if not page:
            break
        events.extend(page)
        since_id = page[-1].id
        if len(page) < page_size:
            break
    return events


async def sync_once(
    config: Config, ombor: OmborBridgeClient, state: StateStore, *, hr_transport=None
) -> SyncSummary:
    summary = SyncSummary()

    if not ombor.is_configured:
        summary.skipped_ombor_not_configured = True
        return summary

    all_events = await _fetch_all_events(config, transport=hr_transport)
    synced_keys = state.get_synced_keys()
    events = [e for e in all_events if e.operation_key not in synced_keys]

    summary.checked = len(events)
    if not events:
        return summary

    # Bir xil external_code uchun takroriy GET /products/by-code so'rovlarini
    # oldini olish uchun kichik keш (bitta tsikl davomida faqat).
    code_cache: dict[str, dict] = {}

    for event in events:
        product = code_cache.get(event.ombor_external_code)
        if product is None:
            try:
                product = await ombor.get_product_by_code(event.ombor_external_code)
                code_cache[event.ombor_external_code] = product
            except BridgeError as e:
                reason = f"Ombor'da '{event.ombor_external_code}' kodi topilmadi: {e}"
                state.mark_failed(event.operation_key, reason=reason)
                summary.failed += 1
                logger.warning("Event %s: %s", event.operation_key, reason)
                continue

        source_id = build_source_id("hr-event", event.operation_key)
        try:
            await ombor.push_production_batch(
                source_id=source_id,
                finished_product_id=product["id"],
                completed_units=event.completed_units,
                event_type=event.event_type,
            )
            state.mark_synced(event.operation_key)
            summary.synced += 1
        except BridgeError as e:
            state.mark_failed(event.operation_key, reason=str(e))
            summary.failed += 1
            logger.warning("Event %s push failed: %s", event.operation_key, e)

    return summary
