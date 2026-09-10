import logging
from dataclasses import dataclass

from erp_bridge_kit import BridgeError, OmborBridgeClient, best_name_match, build_source_id

from app import catalog, hr_reader
from app.config import Config
from app.state import StateStore

logger = logging.getLogger(__name__)


@dataclass
class SyncSummary:
    checked: int = 0
    synced: int = 0
    needs_review: int = 0
    failed: int = 0
    skipped_ombor_not_configured: bool = False


async def _fetch_all_entries(
    config: Config, transport=None
) -> list[hr_reader.ProductionLogEntry]:
    """HR'ning ichki API'sidan barcha sahifalarni (pagination) yig'ib oladi."""
    entries: list[hr_reader.ProductionLogEntry] = []
    since_id = 0
    page_size = 200
    while True:
        page = await hr_reader.fetch_production_log_entries(
            config.hr_internal_api_base_url,
            config.hr_internal_api_token,
            since_id=since_id,
            limit=page_size,
            transport=transport,
        )
        if not page:
            break
        entries.extend(page)
        since_id = page[-1].log_id
        if len(page) < page_size:
            break
    return entries


async def sync_once(
    config: Config, ombor: OmborBridgeClient, state: StateStore, *, hr_transport=None
) -> SyncSummary:
    summary = SyncSummary()

    if not ombor.is_configured:
        summary.skipped_ombor_not_configured = True
        return summary

    all_entries = await _fetch_all_entries(config, transport=hr_transport)
    synced_keys = state.get_synced_keys()
    entries = [e for e in all_entries if e.sync_key not in synced_keys]

    summary.checked = len(entries)
    if not entries:
        return summary

    products = await ombor.list_products(only_active=True)
    candidates = catalog.build_candidates(products)
    products_by_code = catalog.index_by_code(products)

    for entry in entries:
        match = best_name_match(entry.task_text, candidates, threshold=config.match_threshold)
        if not match.ready:
            state.mark_needs_review(entry.sync_key, reason=match.reason or "Noaniq moslik")
            summary.needs_review += 1
            logger.info(
                "Entry %s needs review: %s | task_text=%r",
                entry.sync_key, match.reason, entry.task_text,
            )
            continue

        # HR turli vazifalarda turli birlikda hisobot berishi mumkin
        # (masalan ba'zilari "box"da, ba'zilari to'g'ridan-to'g'ri
        # "partiya"da). config.unit_multipliers har bir birlik uchun
        # 1 dona (banka)ga necha marta ko'paytirishni bildiradi.
        multiplier = config.unit_multipliers.get(entry.unit.strip().lower())
        if multiplier is None:
            state.mark_needs_review(
                entry.sync_key,
                reason=f"Noma'lum birlik '{entry.unit}' — UNIT_MULTIPLIERS'da yo'q",
            )
            summary.needs_review += 1
            continue
        completed_units = entry.completed_qty * multiplier

        product = products_by_code[match.matched_code]
        source_id = build_source_id("hr-op", entry.sync_key)
        try:
            result = await ombor.push_production_batch(
                source_id=source_id,
                finished_product_id=product["id"],
                completed_units=completed_units,
            )
            state.mark_synced(
                entry.sync_key,
                product_id=product["id"],
                ombor_event_id=result.get("id"),
                completed_units=completed_units,
            )
            summary.synced += 1
        except BridgeError as e:
            state.mark_failed(entry.sync_key, reason=str(e))
            summary.failed += 1
            logger.warning("Entry %s push failed: %s", entry.sync_key, e)

    return summary
