import sqlite3

import pytest


HR_SCHEMA = """
CREATE TABLE plan_tasks(
  id INTEGER PRIMARY KEY AUTOINCREMENT, week_start TEXT NOT NULL, weekday INTEGER NOT NULL,
  task_order INTEGER NOT NULL, task_text TEXT NOT NULL, task_type TEXT NOT NULL DEFAULT 'planned',
  special_type TEXT, status TEXT NOT NULL DEFAULT 'pending', marked_by INTEGER, marked_at TEXT,
  cancelled INTEGER NOT NULL DEFAULT 0, created_by INTEGER NOT NULL, created_at TEXT NOT NULL,
  updated_by INTEGER, updated_at TEXT
);
CREATE TABLE task_quantities(
  task_id INTEGER PRIMARY KEY, completed_qty INTEGER NOT NULL DEFAULT 0,
  remaining_qty INTEGER NOT NULL DEFAULT 0, target_qty INTEGER,
  submitted_by INTEGER, submitted_at TEXT
);
CREATE TABLE task_quantity_logs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL,
  employee_id INTEGER NOT NULL,
  work_date TEXT NOT NULL,
  completed_qty INTEGER NOT NULL DEFAULT 0,
  remaining_qty INTEGER NOT NULL DEFAULT 0,
  unit TEXT NOT NULL,
  created_at TEXT NOT NULL,
  raw_input TEXT,
  normalized_status TEXT,
  quantity INTEGER,
  shift_no INTEGER,
  prior_completed_qty INTEGER,
  prior_remaining_qty INTEGER,
  operation_key TEXT
);
"""


@pytest.fixture()
def hr_db_path(tmp_path):
    db_path = tmp_path / "hr_test.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(HR_SCHEMA)
    conn.commit()
    conn.close()
    return str(db_path)


def insert_task(hr_db_path, *, task_text, cancelled=0, week_start="2026-01-01", weekday=1,
                 task_order=1, created_by=1, created_at="2026-01-01T09:00:00"):
    conn = sqlite3.connect(hr_db_path)
    cur = conn.execute(
        "INSERT INTO plan_tasks (week_start, weekday, task_order, task_text, cancelled, created_by, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (week_start, weekday, task_order, task_text, cancelled, created_by, created_at),
    )
    task_id = cur.lastrowid
    conn.commit()
    conn.close()
    return task_id


def insert_log_entry(hr_db_path, *, task_id, completed_qty, unit="box", operation_key=None,
                      employee_id=1, work_date="2026-01-01", created_at="2026-01-01T10:00:00"):
    conn = sqlite3.connect(hr_db_path)
    cur = conn.execute(
        "INSERT INTO task_quantity_logs (task_id, employee_id, work_date, completed_qty, "
        "remaining_qty, unit, created_at, operation_key) VALUES (?, ?, ?, ?, 0, ?, ?, ?)",
        (task_id, employee_id, work_date, completed_qty, unit, created_at, operation_key),
    )
    log_id = cur.lastrowid
    conn.commit()
    conn.close()
    return log_id


@pytest.fixture()
def state_db_path(tmp_path):
    return str(tmp_path / "state_test.db")
