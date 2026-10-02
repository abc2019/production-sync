"""Muammolar haqida Ombor'ning /system-alerts endpointiga yozish - Ombor
Telegram boti OWNER'larga yuboradi (takrorlarni Ombor o'zi to'xtatadi).
Ogohlantirish yuborilmasa (Ombor ishlamasa) - faqat log; sinxronizatsiya
hech qachon shu sababli to'xtamaydi."""
from erp_bridge_kit import OmborBridgeClient

SOURCE = "production-sync"


async def send_alert(ombor: OmborBridgeClient | None, key: str, level: str, message: str) -> bool:
    """erp-bridge-kit'ning umumiy usuli (v0.8.0+): hech qachon istisno ko'tarmaydi."""
    if ombor is None:
        return False
    return await ombor.send_system_alert(source=SOURCE, key=key, level=level, message=message)


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
