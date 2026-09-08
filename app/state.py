"""
production-sync'ning O'Z, kichik holat bazasi — HR yoki Ombor bazasiga
hech qanday aloqasi yo'q. Ikki maqsad uchun:

1. Qaysi HR hisobot hodisalari allaqachon ko'rib chiqilganini eslab qolish
   (Ombor'ning source_id-asosidagi idempotentligi ustiga qo'shimcha himoya
   qatlami — ikkalasi ham ishlasa, hech qachon takroriy qayta ishlanmaydi).
2. Noaniq (owner tasdig'ini kutayotgan) hodisalarni saqlash — kelajakda
   buni ko'rib chiquvchi kichik interfeys/hisobot qurish mumkin.
"""
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_entries (
    sync_key TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('SYNCED', 'FAILED', 'NEEDS_REVIEW')),
    matched_product_id TEXT,
    ombor_event_id TEXT,
    completed_units NUMERIC,
    reason TEXT,
    processed_at TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class ReviewItem:
    sync_key: str
    reason: str
    processed_at: str


class StateStore:
    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def get_synced_keys(self) -> set[str]:
        """
        Faqat SYNCED (muvaffaqiyatli yakunlangan) yozuvlar butunlay chetlab
        o'tiladi. FAILED/NEEDS_REVIEW har safar qayta tekshiriladi — vaqtinchalik
        muammo (masalan Ombor vaqtincha ishlamay qolgan, yoki owner endi
        moslashtirgan) tuzatilgach, o'zi tuzalib ketishi uchun.
        """
        rows = self._conn.execute(
            "SELECT sync_key FROM processed_entries WHERE status = 'SYNCED'"
        ).fetchall()
        return {row["sync_key"] for row in rows}

    def mark_synced(self, sync_key: str, *, product_id: str, ombor_event_id: str | None, completed_units) -> None:
        self._upsert(sync_key, status="SYNCED", matched_product_id=product_id,
                     ombor_event_id=ombor_event_id, completed_units=completed_units, reason=None)

    def mark_failed(self, sync_key: str, *, reason: str) -> None:
        self._upsert(sync_key, status="FAILED", matched_product_id=None,
                     ombor_event_id=None, completed_units=None, reason=reason)

    def mark_needs_review(self, sync_key: str, *, reason: str) -> None:
        self._upsert(sync_key, status="NEEDS_REVIEW", matched_product_id=None,
                     ombor_event_id=None, completed_units=None, reason=reason)

    def list_needs_review(self) -> list[ReviewItem]:
        rows = self._conn.execute(
            "SELECT sync_key, reason, processed_at FROM processed_entries "
            "WHERE status = 'NEEDS_REVIEW' ORDER BY processed_at"
        ).fetchall()
        return [ReviewItem(sync_key=r["sync_key"], reason=r["reason"], processed_at=r["processed_at"]) for r in rows]

    def _upsert(self, sync_key, *, status, matched_product_id, ombor_event_id, completed_units, reason) -> None:
        self._conn.execute(
            """
            INSERT INTO processed_entries
                (sync_key, status, matched_product_id, ombor_event_id, completed_units, reason, processed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sync_key) DO UPDATE SET
                status=excluded.status, matched_product_id=excluded.matched_product_id,
                ombor_event_id=excluded.ombor_event_id, completed_units=excluded.completed_units,
                reason=excluded.reason, processed_at=excluded.processed_at
            """,
            (sync_key, status, matched_product_id, ombor_event_id, completed_units, reason,
             datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()
