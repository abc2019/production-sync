import asyncio
import logging

from erp_bridge_kit import ModuleClient, OmborBridgeClient

from app.config import load_config
from app.state import StateStore
from app.sync import sync_once

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    config = load_config()
    state = StateStore(config.state_database_path)
    ombor = OmborBridgeClient(
        ModuleClient(config.ombor_api_base_url, actor_name=config.ombor_actor_name)
    )

    if not ombor.is_configured:
        logger.warning(
            "OMBOR_API_BASE_URL sozlanmagan — production-sync hech narsa qilmaydi."
        )

    logger.info(
        "production-sync boshlandi (poll_interval=%ss, threshold=%s)",
        config.poll_interval_seconds, config.match_threshold,
    )

    try:
        while True:
            summary = await sync_once(config, ombor, state)
            logger.info(
                "Tsikl yakunlandi: tekshirildi=%d, yuborildi=%d, review=%d, xato=%d",
                summary.checked, summary.synced, summary.needs_review, summary.failed,
            )
            await asyncio.sleep(config.poll_interval_seconds)
    finally:
        state.close()


if __name__ == "__main__":
    asyncio.run(main())
