import asyncio
import logging

from erp_bridge_kit import ModuleClient, OmborBridgeClient

from app.config import load_config
from app.state import StateStore
from app.sync import sync_once

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_ombor_client(config) -> OmborBridgeClient:
    return OmborBridgeClient(
        ModuleClient(
            config.ombor_api_base_url,
            actor_name=config.ombor_actor_name,
            api_token=config.ombor_api_token,
        )
    )


async def main() -> None:
    config = load_config()
    state = StateStore(config.state_database_path)
    ombor = build_ombor_client(config)
    if config.ombor_api_token is None:
        logger.warning(
            "OMBOR_API_TOKEN sozlanmagan - Ombor'ga tokensiz (eski header) kiriladi; "
            "Ombor enforce rejimiga o'tganda rad etiladi."
        )

    if not ombor.is_configured:
        logger.warning(
            "OMBOR_API_BASE_URL sozlanmagan — production-sync hech narsa qilmaydi."
        )

    logger.info(
        "production-sync boshlandi (poll_interval=%ss)",
        config.poll_interval_seconds,
    )

    try:
        while True:
            summary = await sync_once(config, ombor, state)
            logger.info(
                "Tsikl yakunlandi: tekshirildi=%d, yuborildi=%d, xato=%d",
                summary.checked, summary.synced, summary.failed,
            )
            await asyncio.sleep(config.poll_interval_seconds)
    finally:
        state.close()


if __name__ == "__main__":
    asyncio.run(main())
