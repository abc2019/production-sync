import sqlite3

import pytest

from app import hr_reader
from tests.conftest import insert_log_entry, insert_task


def test_fetch_basic(hr_db_path):
    task_id = insert_task(hr_db_path, task_text="Behi murabbosi qadoqlash")
    insert_log_entry(hr_db_path, task_id=task_id, completed_qty=5, operation_key="op-1")

    entries = hr_reader.fetch_production_log_entries(hr_db_path)
    assert len(entries) == 1
    assert entries[0].task_text == "Behi murabbosi qadoqlash"
    assert entries[0].completed_qty == 5
    assert entries[0].unit == "box"
    assert entries[0].sync_key == "op-1"


def test_sync_key_falls_back_to_log_id_when_no_operation_key(hr_db_path):
    task_id = insert_task(hr_db_path, task_text="X")
    log_id = insert_log_entry(hr_db_path, task_id=task_id, completed_qty=3, operation_key=None)
    entries = hr_reader.fetch_production_log_entries(hr_db_path)
    assert entries[0].sync_key == f"log-{log_id}"


def test_excludes_zero_quantity(hr_db_path):
    task_id = insert_task(hr_db_path, task_text="X")
    insert_log_entry(hr_db_path, task_id=task_id, completed_qty=0, operation_key="op-1")
    entries = hr_reader.fetch_production_log_entries(hr_db_path)
    assert entries == []


def test_excludes_cancelled_task(hr_db_path):
    task_id = insert_task(hr_db_path, task_text="Bekor qilingan", cancelled=1)
    insert_log_entry(hr_db_path, task_id=task_id, completed_qty=10, operation_key="op-1")
    entries = hr_reader.fetch_production_log_entries(hr_db_path)
    assert entries == []


def test_exclude_sync_keys_filters_already_processed(hr_db_path):
    task_id = insert_task(hr_db_path, task_text="A")
    insert_log_entry(hr_db_path, task_id=task_id, completed_qty=3, operation_key="op-1")
    entries = hr_reader.fetch_production_log_entries(hr_db_path, exclude_sync_keys={"op-1"})
    assert entries == []


def test_multiple_reports_for_same_task_all_returned(hr_db_path):
    # Bitta task uchun bir necha alohida hisobot bo'lishi mumkin - hammasi qaytishi kerak
    task_id = insert_task(hr_db_path, task_text="Behi murabbosi qadoqlash")
    insert_log_entry(hr_db_path, task_id=task_id, completed_qty=2, operation_key="op-1",
                      created_at="2026-01-01T10:00:00")
    insert_log_entry(hr_db_path, task_id=task_id, completed_qty=3, operation_key="op-2",
                      created_at="2026-01-01T14:00:00")
    entries = hr_reader.fetch_production_log_entries(hr_db_path)
    assert len(entries) == 2
    assert {e.sync_key for e in entries} == {"op-1", "op-2"}


def test_ordered_by_log_id(hr_db_path):
    task_id = insert_task(hr_db_path, task_text="X")
    insert_log_entry(hr_db_path, task_id=task_id, completed_qty=1, operation_key="op-1")
    insert_log_entry(hr_db_path, task_id=task_id, completed_qty=1, operation_key="op-2")
    entries = hr_reader.fetch_production_log_entries(hr_db_path)
    assert [e.sync_key for e in entries] == ["op-1", "op-2"]


def test_read_only_connection_cannot_write(hr_db_path):
    conn = hr_reader._connect_read_only(hr_db_path)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute(
                "INSERT INTO plan_tasks (week_start, weekday, task_order, task_text, created_by, created_at) "
                "VALUES ('x',1,1,'x',1,'x')"
            )
    finally:
        conn.close()
