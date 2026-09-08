"""
HR botining bazasidan (FAQAT O'QISH) bajarilgan/miqdor kiritilgan
tasklarni o'qiydi. HR'ning kodiga yoki bazasiga hech qanday YOZUV
qilinmaydi — bu modul chegarasi qat'iy saqlanadi.

MUHIM: HR'ning `plan_tasks.status` maydonining aniq qiymatlari (masalan
"completed", "done", "bajarildi") shu loyihaning yozilish paytida
tasdiqlanmagan edi. Shuning uchun "bajarilgan" belgisi sifatida
`task_quantities.submitted_at IS NOT NULL AND completed_qty > 0`
ishlatilmoqda — bu HR UI'da miqdor kiritilgani va sonning musbat
ekanini bildiradi, status matnidan qat'i nazar. Productionga chiqarishdan
oldin HR jamoasi bilan bu taxminni tasdiqlash tavsiya etiladi.
"""
import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class CompletedTask:
    id: int
    task_text: str
    completed_qty: int
    submitted_at: str


def _connect_read_only(db_path: str) -> sqlite3.Connection:
    # SQLite'ning "immutable=1" rejimi — hatto tasodifiy yozishga urinish
    # bo'lsa ham xato beradi, HR bazasi himoyalangan bo'ladi.
    conn = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_completed_tasks(
    db_path: str, *, exclude_ids: set[int] | None = None
) -> list[CompletedTask]:
    exclude_ids = exclude_ids or set()
    conn = _connect_read_only(db_path)
    try:
        rows = conn.execute(
            """
            SELECT pt.id AS id, pt.task_text AS task_text,
                   tq.completed_qty AS completed_qty, tq.submitted_at AS submitted_at
            FROM plan_tasks pt
            JOIN task_quantities tq ON tq.task_id = pt.id
            WHERE pt.cancelled = 0
              AND tq.completed_qty > 0
              AND tq.submitted_at IS NOT NULL
            ORDER BY tq.submitted_at ASC
            """
        ).fetchall()
    finally:
        conn.close()

    return [
        CompletedTask(
            id=row["id"],
            task_text=row["task_text"],
            completed_qty=row["completed_qty"],
            submitted_at=row["submitted_at"],
        )
        for row in rows
        if row["id"] not in exclude_ids
    ]
