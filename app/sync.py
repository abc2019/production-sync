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

    tasks = hr_reader.fetch_completed_tasks(
        config.hr_database_path, exclude_ids=state.get_processed_task_ids()
    )
    summary.checked = len(tasks)
    if not tasks:
        return summary

    products = await ombor.list_products(only_active=True)
    candidates = catalog.build_candidates(products)
    products_by_code = catalog.index_by_code(products)

    for task in tasks:
        match = best_name_match(task.task_text, candidates, threshold=config.match_threshold)
        if not match.ready:
            state.mark_needs_review(task.id, reason=match.reason or "Noaniq moslik")
            summary.needs_review += 1
            logger.info("Task %s needs review: %s", task.id, match.reason)
            continue

        product = products_by_code[match.matched_code]
        source_id = build_source_id("hr-task", str(task.id))
        try:
            result = await ombor.push_production_batch(
                source_id=source_id,
                finished_product_id=product["id"],
                batch_count=task.completed_qty,
            )
            state.mark_synced(
                task.id,
                product_id=product["id"],
                ombor_event_id=result.get("id"),
                batch_count=task.completed_qty,
            )
            summary.synced += 1
        except BridgeError as e:
            state.mark_failed(task.id, reason=str(e))
            summary.failed += 1
            logger.warning("Task %s push failed: %s", task.id, e)

    return summary
