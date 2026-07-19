"""scripts/usage_report.py 测试：夹具 DB 计数正确 + eval 隔离 + 缺列诚实「未知」+ 缺库 fail-closed。

独立可跑（纯 stdlib+pytest，不依赖 fastapi 栈）：
    uv run --no-project --with pytest python -m pytest backend/tests/test_usage_report.py -q
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO / "scripts" / "usage_report.py"

spec = importlib.util.spec_from_file_location("usage_report", SCRIPT)
usage_report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(usage_report)

NOW = dt.datetime(2026, 7, 18, 12, 0, 0, tzinfo=dt.timezone.utc)
RECENT = "2026-07-17T10:00:00+00:00"
OLD = "2026-05-01T10:00:00+00:00"


def make_db(tmp_path: Path) -> Path:
    db = tmp_path / "fixture.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, display_name TEXT,
                            password_hash TEXT, is_active INTEGER, created_at TEXT);
        CREATE TABLE tasks (id TEXT PRIMARY KEY, agent_id TEXT, status TEXT, created_by TEXT,
                            created_by_username TEXT, created_at TEXT, updated_at TEXT,
                            finished_at TEXT, conversation_id TEXT, origin TEXT);
        CREATE TABLE task_events (id INTEGER PRIMARY KEY, task_id TEXT,
                                  event_type TEXT, created_at TEXT);
        CREATE TABLE task_human_decisions (id TEXT PRIMARY KEY, task_id TEXT,
                                           reason_code TEXT, created_at TEXT);
        CREATE TABLE conversations (id TEXT PRIMARY KEY, created_by TEXT, created_at TEXT);
        CREATE TABLE model_calls (id INTEGER PRIMARY KEY, status TEXT, created_at TEXT);
        CREATE TABLE feedback (id INTEGER PRIMARY KEY, created_at TEXT);
        """
    )
    conn.executemany(
        "INSERT INTO users (username, display_name, password_hash, is_active, created_at) VALUES (?,?,?,?,?)",
        [("u1", "用户一", "x", 1, OLD), ("u2", "用户二", "x", 0, OLD)],
    )
    rows = [
        # (id, agent, status, creator, username, created, updated, finished, conv, origin)
        ("t1", "a1", "completed", "用户一", "u1", RECENT, RECENT, "2026-07-17T10:05:00", "c1", "user"),
        ("t2", "a1", "waiting_review", "用户一", "u1", RECENT, "2026-07-14T10:00:00", None, None, "user"),
        ("t3", "a2", "failed", "用户二", "u2", RECENT, RECENT, None, None, "user"),
        ("t4", "a1", "completed", "用户一", "u1", OLD, OLD, OLD, None, "user"),          # 窗口外
        ("t5", "a1", "completed", "评测", None, RECENT, RECENT, RECENT, None, "eval"),   # eval 必须被隔离
    ]
    conn.executemany("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    conn.executemany(
        "INSERT INTO task_events (task_id, event_type, created_at) VALUES (?,?,?)",
        [
            ("t1", "review_approved", RECENT),
            ("t3", "review_rejected", RECENT),
            ("t4", "review_approved", OLD),
            ("t5", "review_approved", RECENT),
        ],
    )
    conn.execute(
        "INSERT INTO task_human_decisions VALUES ('d1', 't1', NULL, ?)",
        (RECENT,),
    )
    conn.execute("INSERT INTO conversations VALUES ('c1', '用户一', ?)", (RECENT,))
    conn.executemany(
        "INSERT INTO model_calls (status, created_at) VALUES (?,?)",
        [("success", RECENT), ("failed", RECENT)],
    )
    conn.execute("INSERT INTO feedback (created_at) VALUES (?)", (RECENT,))
    conn.commit()
    conn.close()
    return db


def test_counts_window_and_eval_isolation(tmp_path):
    report = usage_report.build_report(make_db(tmp_path), days=14, now=NOW)
    tasks = report["tasks"]
    assert tasks["created"] == 3                      # t4 窗口外、t5 eval 均排除
    assert tasks["by_status"] == {"completed": 1, "waiting_review": 1, "failed": 1}
    assert tasks["distinct_creators"] == 2
    assert tasks["by_creator"] == {"u1": 2, "u2": 1}
    assert tasks["completed_median_s"] == 300.0
    assert tasks["stalled_waiting_review"] == 1       # t2 updated 超 48h
    assert report["reviews"]["approved"] == 1
    assert report["reviews"]["rejected"] == 1
    assert report["reviews"]["judgment_coverage"] == {
        "status": "measured",
        "structured": 1,
        "legacy_unstructured": 1,
        "structured_ratio": 0.5,
        "by_reject_reason": {},
        "note": "legacy_unstructured 仅计无结构化 decision 的既有 review event；不反推 reason",
    }
    assert report["funnel"]["conversations"] == 1
    assert report["funnel"]["conversations_with_tasks"] == 1
    assert report["funnel"]["completed"] == 1
    assert report["model_calls"]["total"] == 2
    assert report["model_calls"]["failed"] == 1
    assert report["model_calls"]["tokens"] == "未知（model_calls 无总 token 列）"  # 缺列=未知绝不记 0
    assert report["feedback_count"] == 1
    assert report["accounts"] == {"total": 2, "active_flag": 1}


def test_missing_columns_honest_unknown(tmp_path):
    db = tmp_path / "bare.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE tasks (id TEXT)")  # 缺关键列
    conn.commit()
    conn.close()
    report = usage_report.build_report(db, days=14, now=NOW)
    assert isinstance(report["tasks"], str) and "未知" in report["tasks"]
    assert isinstance(report["reviews"], str) and "未知" in report["reviews"]


def test_naive_injected_clock_is_interpreted_as_utc_not_local_time(tmp_path):
    naive_now = dt.datetime(2026, 7, 18, 12, 0, 0)
    report = usage_report.build_report(make_db(tmp_path), days=14, now=naive_now)

    assert report["generated_at"] == "2026-07-18T12:00:00+00:00"
    assert report["tasks"]["created"] == 3


def test_missing_db_fails_closed(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(tmp_path / "nope.db")],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 2
    assert "fail-closed" in proc.stderr


def test_cli_markdown_renders(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(make_db(tmp_path)), "--days", "9999"],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0
    assert "FLAi-OS 使用遥测" in proc.stdout
    assert "绝不以 0 充数" in proc.stdout
