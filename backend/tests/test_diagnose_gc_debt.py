"""GC 债诊断脚本的只读口径与防假阳性回归测试。"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts import diagnose_gc_debt


def _create_db(path: Path, *, with_conversations: bool = True) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            input_file_ids TEXT NOT NULL,
            output_file_ids TEXT NOT NULL,
            conversation_id TEXT
        );
        CREATE TABLE files (
            id TEXT PRIMARY KEY,
            task_id TEXT,
            size_bytes INTEGER NOT NULL
        );
        """
    )
    if with_conversations:
        conn.execute(
            "CREATE TABLE conversations (id TEXT PRIMARY KEY, status TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE conversation_messages (id TEXT PRIMARY KEY, file_ids TEXT NOT NULL DEFAULT '[]')"
        )
    return conn


def test_orphan_files_use_task_json_arrays_not_files_task_id(tmp_path, capsys) -> None:
    db_path = tmp_path / "gc.db"
    conn = _create_db(db_path)
    conn.execute(
        "INSERT INTO tasks VALUES (?, ?, ?, ?)",
        ("task_1", '["input_ref"]', '["output_ref"]', None),
    )
    conn.execute("INSERT INTO conversation_messages VALUES (?, ?)", ("msg_1", '["conv_ref"]'))
    conn.executemany(
        "INSERT INTO files VALUES (?, ?, ?)",
        [
            ("input_ref", None, 10),
            ("output_ref", "task_1", 20),
            ("conv_ref", None, 40),
            ("false_link", "task_1", 30),
        ],
    )
    conn.commit()
    conn.close()

    assert diagnose_gc_debt.main(["--db", str(db_path)]) == 0
    output = capsys.readouterr().out
    # 会话附件（仅被 conversation_messages.file_ids 引用）绝不能被判孤儿（Codex 互审 P1）。
    assert "孤儿文件数量：1" in output
    assert "孤儿文件合计字节：30" in output
    assert "false_link" in output
    assert "conv_ref" not in output


def test_stale_conversations_require_active_old_and_zero_task_hits(tmp_path, capsys) -> None:
    db_path = tmp_path / "gc.db"
    conn = _create_db(db_path)
    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=10)).isoformat()
    recent = (now - timedelta(days=1)).isoformat()
    conn.executemany(
        "INSERT INTO conversations VALUES (?, ?, ?)",
        [
            ("stale", "active", old),
            ("has_task", "active", old),
            ("recent", "active", recent),
            ("concluded", "concluded", old),
        ],
    )
    conn.execute("INSERT INTO tasks VALUES (?, ?, ?, ?)", ("task_1", "[]", "[]", "has_task"))
    conn.commit()
    conn.close()

    assert diagnose_gc_debt.main(["--db", str(db_path), "--stale-days", "7"]) == 0
    output = capsys.readouterr().out
    assert "疑似弃置会话数量：1" in output
    assert "stale (updated_at=" in output
    assert "has_task (updated_at=" not in output


def test_missing_database_reports_without_traceback(tmp_path, capsys) -> None:
    missing = tmp_path / "missing.db"
    assert diagnose_gc_debt.main(["--db", str(missing)]) == 2
    output = capsys.readouterr().out
    assert f"数据库不存在：{missing}" in output
    assert "Traceback" not in output


def test_legacy_schema_reports_incomplete_conversation_diagnostic(tmp_path, capsys) -> None:
    db_path = tmp_path / "legacy.db"
    conn = _create_db(db_path, with_conversations=False)
    conn.commit()
    conn.close()

    assert diagnose_gc_debt.main(["--db", str(db_path)]) == 1
    output = capsys.readouterr().out
    assert "孤儿文件数量：0" in output
    assert "疑似弃置会话：无法统计（缺少表 conversations）" in output


def test_malformed_task_file_ids_do_not_produce_orphan_verdict(tmp_path, capsys) -> None:
    db_path = tmp_path / "malformed.db"
    conn = _create_db(db_path)
    conn.execute("INSERT INTO tasks VALUES (?, ?, ?, ?)", ("task_1", "not-json", "[]", None))
    conn.execute("INSERT INTO files VALUES (?, ?, ?)", ("maybe_referenced", None, 10))
    conn.commit()
    conn.close()

    assert diagnose_gc_debt.main(["--db", str(db_path)]) == 1
    output = capsys.readouterr().out
    assert "孤儿文件：无法统计" in output
    assert "孤儿文件数量：" not in output


def test_database_connection_is_query_only(tmp_path) -> None:
    db_path = tmp_path / "readonly.db"
    conn = _create_db(db_path)
    conn.commit()
    conn.close()

    readonly = diagnose_gc_debt._open_readonly(db_path)
    try:
        assert readonly.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError):
            readonly.execute("DELETE FROM files")
    finally:
        readonly.close()
