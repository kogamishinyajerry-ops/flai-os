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

from backend.app.storage.db import init_db

REPO = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO / "scripts" / "usage_report.py"

spec = importlib.util.spec_from_file_location("usage_report", SCRIPT)
usage_report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(usage_report)

NOW = dt.datetime(2026, 7, 18, 12, 0, 0, tzinfo=dt.timezone.utc)
RECENT = "2026-07-17T10:00:00+00:00"
OLD = "2026-05-01T10:00:00+00:00"


def make_db(tmp_path: Path, *, include_outcomes: bool = True) -> Path:
    db = tmp_path / "fixture.db"
    init_db(db)
    conn = sqlite3.connect(db)
    conn.executemany(
        "INSERT INTO users (username, display_name, password_hash, is_active, created_at) VALUES (?,?,?,?,?)",
        [("u1", "用户一", "x", 1, OLD), ("u2", "用户二", "x", 0, OLD)],
    )
    rows = [
        # t1 starts waiting_review so the canonical human-decision witness accepts d1;
        # it is moved to completed below after the decision row is persisted.
        ("t1", "a1", "0.1.0", "waiting_review", "用户一", "u1", RECENT, RECENT,
         "2026-07-17T10:05:00", "c1", "user", "[]", '["f1", "f2"]', None),
        ("t2", "a1", "0.1.0", "waiting_review", "用户一", "u1", RECENT,
         "2026-07-14T10:00:00", None, None, "user", '["f2"]', "[]", '["t1"]'),
        ("t3", "a2", "0.1.0", "failed", "用户二", "u2", RECENT, RECENT,
         None, None, "user", "[]", "[]", None),
        ("t4", "a1", "0.1.0", "completed", "用户一", "u1", OLD, OLD,
         OLD, None, "user", "[]", "[]", None),
        ("t5", "a1", "0.1.0", "completed", "评测", None, RECENT, RECENT,
         RECENT, None, "eval", "[]", '["ef1"]', None),
    ]
    conn.executemany(
        "INSERT INTO tasks "
        "(id, agent_id, agent_version, status, created_by, created_by_username, "
        " created_at, updated_at, finished_at, conversation_id, origin, "
        " input_file_ids, output_file_ids, depends_on) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.executemany(
        "INSERT INTO files "
        "(id, task_id, kind, filename, path, size_bytes, sha256, created_at, "
        " classification, uploaded_by) VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            ("f1", "t1", "output", "f1.txt", "/tmp/f1", 10, "a" * 64, RECENT, "internal", None),
            ("f2", "t1", "output", "f2.txt", "/tmp/f2", 10, "b" * 64, RECENT, "internal", None),
            ("ef1", "t5", "output", "ef1.txt", "/tmp/ef1", 10, "c" * 64, RECENT, "internal", None),
        ],
    )
    conn.executemany(
        "INSERT INTO task_events "
        "(event_id, task_id, agent_id, event_type, level, message, payload_json, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        [
            ("e1", "t1", "a1", "review_approved", "info", "approved", "{}", RECENT),
            ("e3", "t3", "a2", "review_rejected", "warning", "rejected", "{}", RECENT),
            ("e4", "t4", "a1", "review_approved", "info", "approved", "{}", OLD),
            ("ee1", "t5", "a1", "review_approved", "info", "approved", "{}", RECENT),
        ],
    )
    conn.execute(
        "INSERT INTO task_human_decisions "
        "(id, task_id, paired_advice_id, action, reason_code, comment, "
        " reviewer_username, reviewer_display_name, schema_version, created_at) "
        "VALUES ('d1', 't1', NULL, 'approve', NULL, NULL, 'u1', '用户一', 1, ?)",
        (RECENT,),
    )
    conn.execute(
        "UPDATE tasks SET status = 'completed' WHERE id = 't1'"
    )
    conn.execute(
        "INSERT INTO conversations "
        "(id, agent_id, status, created_by, created_by_username, created_at, updated_at) "
        "VALUES ('c1', 'a1', 'active', '用户一', 'u1', ?, ?)",
        (RECENT, RECENT),
    )
    conn.executemany(
        "INSERT INTO model_calls (model_profile, status, created_at) VALUES (?,?,?)",
        [("reasoning", "success", RECENT), ("reasoning", "failed", RECENT)],
    )
    conn.execute(
        "INSERT INTO feedback (task_id, created_at) VALUES ('t1', ?)", (RECENT,)
    )
    if include_outcomes:
        conn.executemany(
            "INSERT INTO artifact_outcome_events VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                ("o1", "capture_started", "t1", "f1", "e1", None, None, None, 1, RECENT),
                ("o2", "capture_started", "t1", "f2", "e1", None, None, None, 1, RECENT),
                # 同一产物两次真实完整交付必须保留为两个 event，distinct artifact 仍为 1。
                ("o3", "full_download", "t1", "f1", "e1", "u1", None, 10, 1, RECENT),
                ("o4", "full_download", "t1", "f1", "e1", "u1", None, 10, 1, RECENT),
                ("o5", "pipeline_handoff", "t1", "f2", "e1", None, "t2", None, 1, RECENT),
            ],
        )
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
    assert report["artifact_outcomes"] == {
        "status": "measured",
        "schema_witnesses": {
            "outcome_table_shape": True,
            "required_indexes": True,
            "required_triggers": True,
        },
        "observation_started_at": RECENT,
        "requested_window_start": "2026-07-04T12:00:00+00:00",
        "effective_window_start": RECENT,
        "requested_window_fully_covered": False,
        "capture_started": {
            "events": 2,
            "distinct_artifacts": 2,
            "distinct_source_tasks": 1,
        },
        "full_download": {
            "delivered_events_lower_bound": 2,
            "distinct_artifacts": 1,
            "distinct_source_tasks": 1,
            "distinct_actors": 1,
        },
        "pipeline_handoff": {
            "flowed_events_lower_bound": 1,
            "distinct_artifacts": 1,
            "distinct_source_tasks": 1,
            "distinct_downstream_tasks": 1,
        },
        "note": (
            "仅统计逐权威产物 capture_started 之后的 user-origin 事件；"
            "full_download=完整正文已交付，不代表采用（仅 200 GET）；"
            "pipeline_handoff=产物已流入下游任务，不代表被读取或采用"
        ),
    }


def test_missing_columns_honest_unknown(tmp_path):
    db = tmp_path / "bare.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE tasks (id TEXT)")  # 缺关键列
    conn.commit()
    conn.close()
    report = usage_report.build_report(db, days=14, now=NOW)
    assert isinstance(report["tasks"], str) and "未知" in report["tasks"]
    assert isinstance(report["reviews"], str) and "未知" in report["reviews"]
    assert isinstance(report["artifact_outcomes"], str) and "未知" in report["artifact_outcomes"]


def test_outcome_table_without_capture_is_unknown_not_fake_zero(tmp_path):
    db = make_db(tmp_path, include_outcomes=False)

    report = usage_report.build_report(db, days=14, now=NOW)

    assert report["artifact_outcomes"]["status"] == "unknown_no_instrumented_artifacts"
    assert "未知" in report["artifact_outcomes"]["full_download"]
    assert "未知" in report["artifact_outcomes"]["pipeline_handoff"]


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
    assert "完整正文已交付，不代表采用" in proc.stdout
    assert "已流入下游任务，不代表被读取或采用" in proc.stdout
