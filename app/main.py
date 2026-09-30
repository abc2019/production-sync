import asyncio
import logging

from erp_bridge_kit import ModuleClient, OmborBridgeClient

from app.config import load_config
from app.state import StateStore
from app.alerts import events_message, send_alert
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
        await run_forever(config, ombor, state)
    finally:
        state.close()


MAX_BACKOFF_SECONDS = 900


ALERT_AFTER_FAILURES = 3  # ketma-ket shuncha tsikl yiqilsa - OWNER'ga xabar


async def run_forever(config, ombor, state, *, sleep=asyncio.sleep, max_cycles: int | None = None) -> None:
    """Asosiy sikl. Bitta tsikldagi xato (HR yoki Ombor vaqtincha ishlamasa,
    tarmoq uzilsa) jarayonni YIQITMAYDI: xato logga yoziladi va keyingi
    tsiklda qayta uriniladi (ketma-ket xatolarda kutish ikki barobar,
    MAX_BACKOFF_SECONDS gacha). Hodisalar yo'qolmaydi - holat (state)
    qayerda to'xtaganini eslaydi.

    OWNER'ga ogohlantirish (Ombor /system-alerts orqali, Telegram):
    - ALERT_AFTER_FAILURES ta ketma-ket tsikl yiqilsa - bir marta; tiklanganda - bir marta;
    - hodisalar Ombor'ga yozilmayotgan bo'lsa - ro'yxat (to'plam o'zgarsa yangilanadi);
      hammasi o'tgach - tiklandi."""
    failures = 0
    cycle_alerted = False
    events_alerted = False
    cycles = 0
    while max_cycles is None or cycles < max_cycles:
        cycles += 1
        try:
            summary = await sync_once(config, ombor, state)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - bitta tsikl xatosi butun servisni to'xtatmasin
            failures += 1
            delay = min(config.poll_interval_seconds * (2 ** (failures - 1)), MAX_BACKOFF_SECONDS)
            delay = max(delay, config.poll_interval_seconds)
            logger.exception(
                "Tsikl xatosi (ketma-ket %d-marta) - %ss dan keyin qayta urinish", failures, delay,
            )
            if failures >= ALERT_AFTER_FAILURES and not cycle_alerted:
                cycle_alerted = await send_alert(
                    ombor, "production-sync:cycle", "error",
                    f"Sinxronizatsiya {failures} marta ketma-ket muvaffaqiyatsiz - ishlab chiqarish "
                    f"Ombor'ga yozilmayapti.\nOxirgi xato: {type(exc).__name__}: {str(exc)[:500]}",
                )
            await sleep(delay)
            continue
        if failures:
            logger.info("Ulanish tiklandi (%d ta xatodan keyin)", failures)
            if cycle_alerted:
                await send_alert(ombor, "production-sync:cycle", "recovered",
                                 f"Sinxronizatsiya tiklandi ({failures} ta xatodan keyin).")
        failures = 0
        cycle_alerted = False

        if summary.failures:
            events_alerted = await send_alert(
                ombor, "production-sync:events", "warning", events_message(summary.failures),
            ) or events_alerted
        elif events_alerted and summary.checked == 0:
            await send_alert(ombor, "production-sync:events", "recovered",
                             "Barcha ishlab chiqarish hodisalari Ombor'ga yozildi.")
            events_alerted = False

        logger.info(
            "Tsikl yakunlandi: tekshirildi=%d, yuborildi=%d, xato=%d",
            summary.checked, summary.synced, summary.failed,
        )
        await sleep(config.poll_interval_seconds)

if __name__ == "__main__":
    asyncio.run(main())
