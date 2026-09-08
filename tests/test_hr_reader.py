from app import hr_reader
from tests.conftest import insert_task
import sqlite3

import pytest


def test_fetch_completed_tasks_basic(hr_db_path):
    insert_task(hr_db_path, task_text="Behi murabbosi qadoqlash", completed_qty=5)
    tasks = hr_reader.fetch_completed_tasks(hr_db_path)
    assert len(tasks) == 1
    assert tasks[0].task_text == "Behi murabbosi qadoqlash"
    assert tasks[0].completed_qty == 5


def test_excludes_tasks_without_quantity(hr_db_path):
    insert_task(hr_db_path, task_text="Idishlarni tozalash", completed_qty=None)
    tasks = hr_reader.fetch_completed_tasks(hr_db_path)
    assert tasks == []


def test_excludes_zero_quantity(hr_db_path):
    insert_task(hr_db_path, task_text="X", completed_qty=0)
    tasks = hr_reader.fetch_completed_tasks(hr_db_path)
    assert tasks == []


def test_excludes_cancelled_tasks(hr_db_path):
    insert_task(hr_db_path, task_text="Bekor qilingan", completed_qty=10, cancelled=1)
    tasks = hr_reader.fetch_completed_tasks(hr_db_path)
    assert tasks == []


def test_exclude_ids_filters_already_processed(hr_db_path):
    task_id = insert_task(hr_db_path, task_text="A", completed_qty=3)
    tasks = hr_reader.fetch_completed_tasks(hr_db_path, exclude_ids={task_id})
    assert tasks == []


def test_ordered_by_submitted_at(hr_db_path):
    insert_task(hr_db_path, task_text="Ikkinchi", completed_qty=1, submitted_at="2026-01-02T00:00:00")
    insert_task(hr_db_path, task_text="Birinchi", completed_qty=1, submitted_at="2026-01-01T00:00:00")
    tasks = hr_reader.fetch_completed_tasks(hr_db_path)
    assert [t.task_text for t in tasks] == ["Birinchi", "Ikkinchi"]


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
