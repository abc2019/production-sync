"""
HR botining ICHKI, FAQAT-O'QISH HTTP API'sidan (`internal_api.py`,
`abc2019/ShohonaWorkBot`) tayyor, aniq ishlab chiqarish/brak hodisalarini
o'qiydi.

MUHIM: bu — HR'ning maxsus, BARQAROR eksport jadvali
(`production_sync_events`) asosida ishlaydi, HR'ning ichki
(`task_quantity_logs`, `special_type` va h.k.) jadvallariga UMUMAN
bog'liq emas. Matn moslashtirish (fuzzy matching) yoki birlik
konvertatsiyasi bu yerda YO'Q — HR o'zi allaqachon aniq
`ombor_external_code` va `completed_units` (dona) bilan beradi.
"""
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class ProductionSyncEvent:
    id: int
    operation_key: str  # HR'ning o'z idempotentlik kaliti
    event_type: str  # "PRODUCED" yoki "DEFECT"
    ombor_external_code: str
    completed_units: int
    created_at: str
    source_task_id: int


class HRClientError(Exception):
    pass


async def fetch_production_sync_events(
    base_url: str,
    token: str,
    *,
    since_id: int = 0,
    limit: int = 200,
    transport: httpx.BaseTransport | None = None,
) -> list[ProductionSyncEvent]:
    try:
        async with httpx.AsyncClient(timeout=15, transport=transport) as client:
            resp = await client.get(
                f"{base_url.rstrip('/')}/internal/production-sync-events",
                params={"since_id": since_id, "limit": limit},
                headers={"X-Internal-Token": token},
            )
            resp.raise_for_status()
            rows = resp.json()
    except httpx.HTTPStatusError as e:
        raise HRClientError(f"HR {e.response.status_code}: {e.response.text}")
    except httpx.HTTPError as e:
        raise HRClientError(f"HR'ga ulanib bo'lmadi: {e}")

    return [
        ProductionSyncEvent(
            id=row["id"],
            operation_key=row["operation_key"],
            event_type=row["event_type"],
            ombor_external_code=row["ombor_external_code"],
            completed_units=row["completed_units"],
            created_at=row["created_at"],
            source_task_id=row["source_task_id"],
        )
        for row in rows
    ]
