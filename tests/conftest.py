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
"""


@pytest.fixture()
def hr_db_path(tmp_path):
    db_path = tmp_path / "hr_test.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(HR_SCHEMA)
    conn.commit()
    conn.close()
    return str(db_path)


def insert_task(hr_db_path, *, task_text, completed_qty, submitted_at="2026-01-01T10:00:00",
                 cancelled=0, week_start="2026-01-01", weekday=1, task_order=1, created_by=1,
                 created_at="2026-01-01T09:00:00"):
    conn = sqlite3.connect(hr_db_path)
    cur = conn.execute(
        "INSERT INTO plan_tasks (week_start, weekday, task_order, task_text, cancelled, created_by, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (week_start, weekday, task_order, task_text, cancelled, created_by, created_at),
    )
    task_id = cur.lastrowid
    if completed_qty is not None:
        conn.execute(
            "INSERT INTO task_quantities (task_id, completed_qty, submitted_at) VALUES (?, ?, ?)",
            (task_id, completed_qty, submitted_at),
        )
    conn.commit()
    conn.close()
    return task_id


@pytest.fixture()
def state_db_path(tmp_path):
    return str(tmp_path / "state_test.db")
