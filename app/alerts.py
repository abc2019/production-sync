"""Muammolar haqida Ombor'ning /system-alerts endpointiga yozish - Ombor
Telegram boti OWNER'larga yuboradi (takrorlarni Ombor o'zi to'xtatadi).
Ogohlantirish yuborilmasa (Ombor ishlamasa) - faqat log; sinxronizatsiya
hech qachon shu sababli to'xtamaydi."""
import logging

from erp_bridge_kit import OmborBridgeClient

logger = logging.getLogger(__name__)

SOURCE = "production-sync"
MAX_MESSAGE = 1900


async def send_alert(ombor: OmborBridgeClient | None, key: str, level: str, message: str) -> bool:
    if ombor is None or not ombor.is_configured:
        return False
    try:
        await ombor._client.post("/system-alerts", json={
            "source": SOURCE, "key": key, "level": level, "message": message[:MAX_MESSAGE],
        })
        return True
    except Exception:  # noqa: BLE001
        logger.warning("Ogohlantirishni Ombor'ga yuborib bo'lmadi (%s): %s", key, message[:200], exc_info=True)
        return False


def events_message(failures: list[tuple[str, str]], limit: int = 10) -> str:
    """Barqaror matn (bir xil xatolar to'plami - bir xil matn): Ombor takrorni
    shu bo'yicha aniqlaydi."""
    items = sorted(failures)
    lines = [f"{len(items)} ta ishlab chiqarish hodisasi Ombor'ga yozilmayapti:"]
    for key, reason in items[:limit]:
        lines.append(f"• {key}: {reason[:160]}")
    if len(items) > limit:
        lines.append(f"… va yana {len(items) - limit} ta")
    lines.append("Har 5 daqiqada qayta urinilyapti.")
    return "\n".join(lines)
