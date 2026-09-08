"""
HR botining ICHKI, FAQAT-O'QISH HTTP API'sidan (`internal_api.py`,
`abc2019/ShohonaWorkBot`) ishlab chiqarish hisobotlarini o'qiydi.

MUHIM: bu tarmoq orqali (HTTP) o'qiydi, fayl orqali EMAS — Railway'da har
bir xizmat alohida konteynerda ishlagani uchun, production-sync HR'ning
SQLite fayliga to'g'ridan-to'g'ri kira olmaydi. HR'ning kodiga yoki
bazasiga hech qanday YOZUV qilinmaydi — HR faqat `GET
/internal/production-logs` orqali o'qishga ruxsat beradi.

Manba: `task_quantity_logs` — HR botining o'zi ishlatadigan O'ZGARMAS
(faqat qo'shiladigan) hisobot jurnali. Har bir qatorning `operation_key`i
— HR botining o'z idempotentlik kaliti; biz ham xuddi shuni ishlatamiz.
"""
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class ProductionLogEntry:
    log_id: int
    operation_key: str | None
    task_id: int
    task_text: str
    completed_qty: int
    unit: str
    created_at: str

    @property
    def sync_key(self) -> str:
        """Idempotentlik uchun barqaror kalit — operation_key mavjud bo'lsa
        o'shani, aks holda (eski qatorlar uchun) log_id'ni ishlatadi."""
        return self.operation_key or f"log-{self.log_id}"


class HRClientError(Exception):
    pass


async def fetch_production_log_entries(
    base_url: str,
    token: str,
    *,
    since_id: int = 0,
    limit: int = 200,
    transport: httpx.BaseTransport | None = None,
) -> list[ProductionLogEntry]:
    try:
        async with httpx.AsyncClient(timeout=15, transport=transport) as client:
            resp = await client.get(
                f"{base_url.rstrip('/')}/internal/production-logs",
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
        ProductionLogEntry(
            log_id=row["log_id"],
            operation_key=row.get("operation_key"),
            task_id=row["task_id"],
            task_text=row["task_text"],
            completed_qty=row["completed_qty"],
            unit=row["unit"],
            created_at=row["created_at"],
        )
        for row in rows
    ]
