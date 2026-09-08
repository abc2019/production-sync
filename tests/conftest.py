import pytest


@pytest.fixture()
def state_db_path(tmp_path):
    return str(tmp_path / "state_test.db")


class FakeHRLogStore:
    """Testlarda HR'ning ichki API'sini almashtiradigan sodda in-memory do'kon."""

    def __init__(self):
        self._entries: list[dict] = []
        self._next_id = 1

    def insert(self, *, task_text, completed_qty, unit="box", operation_key=None):
        entry = {
            "log_id": self._next_id,
            "operation_key": operation_key,
            "task_id": self._next_id,  # soddalashtirish uchun log_id bilan bir xil
            "task_text": task_text,
            "completed_qty": completed_qty,
            "unit": unit,
            "created_at": "2026-01-01T10:00:00",
        }
        self._entries.append(entry)
        self._next_id += 1
        return entry["log_id"]

    def page(self, since_id: int, limit: int) -> list[dict]:
        matching = [e for e in self._entries if e["log_id"] > since_id]
        return matching[:limit]


@pytest.fixture()
def hr_store():
    return FakeHRLogStore()
