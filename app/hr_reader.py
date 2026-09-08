"""
HR botining bazasidan (FAQAT O'QISH) ishlab chiqarish hisobotlarini o'qiydi.
HR'ning kodiga yoki bazasiga hech qanday YOZUV qilinmaydi — bu modul
chegarasi qat'iy saqlanadi.

MANBA: `task_quantity_logs` — HR botining o'zi ishlatadigan O'ZGARMAS
(faqat qo'shiladigan) hisobot jurnali (`plan_tasks`/`task_quantities`
esa joriy holatning YIG'INDISI, o'zgaruvchan — shuning uchun ular emas,
aynan shu jurnal o'qiladi).

Har bir qatorning `operation_key`i — HR botining o'zi ishlatadigan
idempotentlik kaliti (Telegram callback ikki marta bosilishidan himoya
uchun). Biz ham xuddi shu kalitni ishlatamiz — eng barqaror va HR'ning
o'z semantikasiga mos identifikator.

MUHIM: HR kodida `unit` maydoni qattiq "box" (quti) deb belgilangan —
bu Ombor'ning "banka"/"partiya (300)" birligi bilan bir xil emas. Bitta
"box" nechta Ombor birligiga (yoki nechta partiyaga) tengligi HR/CEO
tomonidan tasdiqlanishi kerak — kodda bu konvertatsiya HALI YO'Q, faqat
xom completed_qty qaytariladi (`app/sync.py`da ishlatishdan oldin
ko'rib chiqing).
"""
import sqlite3
from dataclasses import dataclass


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


def _connect_read_only(db_path: str) -> sqlite3.Connection:
    # SQLite'ning "immutable=1" rejimi — hatto tasodifiy yozishga urinish
    # bo'lsa ham xato beradi, HR bazasi himoyalangan bo'ladi.
    conn = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_production_log_entries(
    db_path: str, *, exclude_sync_keys: set[str] | None = None
) -> list[ProductionLogEntry]:
    exclude_sync_keys = exclude_sync_keys or set()
    conn = _connect_read_only(db_path)
    try:
        rows = conn.execute(
            """
            SELECT l.id AS log_id, l.operation_key AS operation_key,
                   l.task_id AS task_id, p.task_text AS task_text,
                   l.completed_qty AS completed_qty, l.unit AS unit,
                   l.created_at AS created_at
            FROM task_quantity_logs l
            JOIN plan_tasks p ON p.id = l.task_id
            WHERE l.completed_qty > 0
              AND p.cancelled = 0
            ORDER BY l.id ASC
            """
        ).fetchall()
    finally:
        conn.close()

    entries = [
        ProductionLogEntry(
            log_id=row["log_id"],
            operation_key=row["operation_key"],
            task_id=row["task_id"],
            task_text=row["task_text"],
            completed_qty=row["completed_qty"],
            unit=row["unit"],
            created_at=row["created_at"],
        )
        for row in rows
    ]
    return [e for e in entries if e.sync_key not in exclude_sync_keys]
