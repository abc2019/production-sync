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


async def sync_once(config: Config, ombor: OmborBridgeClient, state: StateStore) -> SyncSummary:
    summary = SyncSummary()

    if not ombor.is_configured:
        summary.skipped_ombor_not_configured = True
        return summary

    entries = hr_reader.fetch_production_log_entries(
        config.hr_database_path, exclude_sync_keys=state.get_synced_keys()
    )
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
            logger.info("Entry %s needs review: %s", entry.sync_key, match.reason)
            continue

        product = products_by_code[match.matched_code]
        source_id = build_source_id("hr-op", entry.sync_key)
        try:
            result = await ombor.push_production_batch(
                source_id=source_id,
                finished_product_id=product["id"],
                batch_count=entry.completed_qty,
            )
            state.mark_synced(
                entry.sync_key,
                product_id=product["id"],
                ombor_event_id=result.get("id"),
                batch_count=entry.completed_qty,
            )
            summary.synced += 1
        except BridgeError as e:
            state.mark_failed(entry.sync_key, reason=str(e))
            summary.failed += 1
            logger.warning("Entry %s push failed: %s", entry.sync_key, e)

    return summary
