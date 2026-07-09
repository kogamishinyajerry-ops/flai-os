"""storage/repos.py 仓储函数测试：全部用 tmp_path 的 db，绝不碰真实 data/。

覆盖：建任务、非法转移抛错、claim 原子性（两次 claim 拿不到同一任务）、
append_event 对非法 event_type/level 必抛（反例 witness）、文件 CRUD、
tool_run/model_call/sample 落库回读、九表全建成（sqlite_master 对账）。
"""

from __future__ import annotations

import sqlite3
import uuid

import pytest

from backend.app.core.errors import IllegalTransitionError, TaskNotFoundError
from backend.app.storage import db as db_mod
from backend.app.storage import repos


@pytest.fixture()
def conn(tmp_path) -> sqlite3.Connection:
    db_path = tmp_path / "flai_os_test.db"
    db_mod.init_db(db_path)
    c = db_mod.get_conn(db_path)
    yield c
    c.close()


def _new_task(conn, **overrides):
    fields = dict(
        task_id=f"task_{uuid.uuid4().hex[:8]}",
        agent_id="hello_agent",
        agent_version="0.1.0",
        name="测试任务",
        created_by="tester",
        inputs={"name": "张三"},
        input_file_ids=[],
        metadata={},
    )
    fields.update(overrides)
    return repos.create_task(conn, **fields)


# ── init_db 九表全建成 ───────────────────────────────────────────────

def test_init_db_creates_all_nine_tables(conn) -> None:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    names = {r["name"] for r in rows}
    expected = {
        "agents", "agent_versions", "tasks", "task_events", "files",
        "feedback", "tool_runs", "model_calls", "samples",
    }
    assert expected <= names, f"缺表：{expected - names}"


def test_init_db_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "idempotent.db"
    db_mod.init_db(db_path)
    db_mod.init_db(db_path)  # 第二次调用不应报错


# ── tasks ──────────────────────────────────────────────────────────────

def test_create_task_defaults_to_created_status(conn) -> None:
    task = _new_task(conn)
    assert task["status"] == "created"
    assert task["input_file_ids"] == []
    assert task["output_file_ids"] == []
    assert task["inputs"] == {"name": "张三"}
    assert task["metadata"] == {}
    assert task["started_at"] is None
    assert task["finished_at"] is None


def test_get_task_missing_returns_none(conn) -> None:
    assert repos.get_task(conn, "no_such_task") is None


def test_list_tasks_filters_by_agent_and_status(conn) -> None:
    t1 = _new_task(conn, agent_id="agent_a")
    t2 = _new_task(conn, agent_id="agent_b")
    repos.set_task_status(conn, t1["id"], "queued")

    only_a = repos.list_tasks(conn, agent_id="agent_a")
    assert {t["id"] for t in only_a} == {t1["id"]}

    only_queued = repos.list_tasks(conn, status="queued")
    assert {t["id"] for t in only_queued} == {t1["id"]}

    both = repos.list_tasks(conn)
    assert {t["id"] for t in both} == {t1["id"], t2["id"]}


def test_set_task_status_legal_chain_fills_timestamps(conn) -> None:
    task = _new_task(conn)
    task = repos.set_task_status(conn, task["id"], "queued")
    assert task["started_at"] is None

    task = repos.set_task_status(conn, task["id"], "validating")
    task = repos.set_task_status(conn, task["id"], "running")
    assert task["started_at"] is not None
    assert task["finished_at"] is None

    task = repos.set_task_status(conn, task["id"], "analyzing")
    task = repos.set_task_status(conn, task["id"], "completed", )
    assert task["status"] == "completed"
    assert task["finished_at"] is not None


def test_set_task_status_illegal_transition_raises(conn) -> None:
    task = _new_task(conn)  # created
    with pytest.raises(IllegalTransitionError):
        repos.set_task_status(conn, task["id"], "running")


def test_set_task_status_missing_task_raises(conn) -> None:
    with pytest.raises(TaskNotFoundError):
        repos.set_task_status(conn, "ghost_task", "queued")


def test_set_task_status_records_error_message_on_failure(conn) -> None:
    task = _new_task(conn)
    task = repos.set_task_status(conn, task["id"], "queued")
    task = repos.set_task_status(conn, task["id"], "validating")
    task = repos.set_task_status(conn, task["id"], "failed", error_message="输入校验失败：缺 name 字段")
    assert task["status"] == "failed"
    assert task["error_message"] == "输入校验失败：缺 name 字段"
    assert task["finished_at"] is not None


def test_set_task_outputs(conn) -> None:
    task = _new_task(conn)
    updated = repos.set_task_outputs(conn, task["id"], ["file_001", "file_002"])
    assert updated["output_file_ids"] == ["file_001", "file_002"]


# ── claim_next_queued 原子性 ─────────────────────────────────────────

def test_claim_next_queued_returns_none_when_empty(conn) -> None:
    assert repos.claim_next_queued(conn) is None


def test_claim_next_queued_picks_fifo_and_transitions_to_validating(conn) -> None:
    t1 = _new_task(conn)
    repos.set_task_status(conn, t1["id"], "queued")

    claimed = repos.claim_next_queued(conn)
    assert claimed is not None
    assert claimed["id"] == t1["id"]
    assert claimed["status"] == "validating"


def test_second_claim_does_not_get_same_task(conn) -> None:
    """claim 原子性核心断言：单个 queued 任务被拾取后，第二次 claim 拿不到它。"""
    t1 = _new_task(conn)
    repos.set_task_status(conn, t1["id"], "queued")

    first = repos.claim_next_queued(conn)
    second = repos.claim_next_queued(conn)

    assert first is not None
    assert first["id"] == t1["id"]
    assert second is None  # 没有别的 queued 任务了，且不会重复拾取同一条


def test_two_queued_tasks_claimed_are_distinct(conn) -> None:
    t1 = _new_task(conn)
    t2 = _new_task(conn)
    repos.set_task_status(conn, t1["id"], "queued")
    repos.set_task_status(conn, t2["id"], "queued")

    first = repos.claim_next_queued(conn)
    second = repos.claim_next_queued(conn)
    third = repos.claim_next_queued(conn)

    assert first is not None and second is not None
    assert first["id"] != second["id"]
    assert {first["id"], second["id"]} == {t1["id"], t2["id"]}
    assert third is None


# ── task_events ──────────────────────────────────────────────────────

def test_append_event_and_list_events_roundtrip(conn) -> None:
    task = _new_task(conn)
    e1 = repos.append_event(
        conn, task_id=task["id"], agent_id="hello_agent",
        event_type="task_created", level="info", message="任务已创建",
        payload={"foo": "bar"},
    )
    e2 = repos.append_event(
        conn, task_id=task["id"],
        event_type="task_failed", level="error", message="失败了",
    )
    assert e1["event_type"] == "task_created"
    assert e1["payload"] == {"foo": "bar"}
    assert e1["agent_id"] == "hello_agent"

    events = repos.list_events(conn, task["id"])
    assert [e["event_type"] for e in events] == ["task_created", "task_failed"]
    assert events[1]["payload"] == {}  # 未传 payload 默认为空 dict


def test_append_event_response_does_not_leak_sqlite_autoincrement_id(conn) -> None:
    """P1-2/P1-3：对外唯一键=event_id，sqlite 自增主键 id 是内部实现细节，
    append_event/list_events 的返回 dict 都不应带出 id 键（event.schema.json
    additionalProperties=false 也不认识这个字段）。
    """
    task = _new_task(conn)
    created = repos.append_event(
        conn, task_id=task["id"], event_type="task_created", level="info", message="任务已创建",
    )
    assert "id" not in created
    assert created["event_id"]

    listed = repos.list_events(conn, task["id"])
    assert all("id" not in e for e in listed)


def test_append_event_invalid_event_type_raises_value_error(conn) -> None:
    """反例 witness：event_type 不在 event.schema.json 枚举内必须炸。"""
    task = _new_task(conn)
    with pytest.raises(ValueError):
        repos.append_event(
            conn, task_id=task["id"], event_type="not_a_real_event_type",
            level="info", message="不应该写进去",
        )
    assert repos.list_events(conn, task["id"]) == []  # 校验失败不应留下脏事件


def test_append_event_invalid_level_raises_value_error(conn) -> None:
    """反例 witness：level 不在 info/warning/error 枚举内必须炸。"""
    task = _new_task(conn)
    with pytest.raises(ValueError):
        repos.append_event(
            conn, task_id=task["id"], event_type="task_created",
            level="fatal", message="不合法的 level",
        )
    assert repos.list_events(conn, task["id"]) == []


def test_append_event_empty_message_rejected(conn) -> None:
    """message 是 minLength=1，空字符串必须被契约咬住。"""
    task = _new_task(conn)
    with pytest.raises(ValueError):
        repos.append_event(
            conn, task_id=task["id"], event_type="task_created",
            level="info", message="",
        )


# ── files ──────────────────────────────────────────────────────────────

def test_create_file_and_get_file_roundtrip(conn) -> None:
    task = _new_task(conn)
    file_id = f"file_{uuid.uuid4().hex[:8]}"
    created = repos.create_file(
        conn, file_id=file_id, task_id=task["id"], kind="input",
        filename="a.csv", path="/data/uploads/a.csv", size_bytes=123, sha256="deadbeef",
    )
    assert created["id"] == file_id
    fetched = repos.get_file(conn, file_id)
    assert fetched == created


def test_get_file_missing_returns_none(conn) -> None:
    assert repos.get_file(conn, "no_such_file") is None


# ── tool_runs / model_calls / samples ───────────────────────────────

def test_record_and_list_tool_run(conn) -> None:
    task = _new_task(conn)
    run = repos.record_tool_run(
        conn, task_id=task["id"], tool_id="mock_echo", tool_version="0.1.0",
        mock=True, status="success", input_json={"x": 1}, output_json={"y": 2},
        started_at="2026-07-08T00:00:00+00:00", finished_at="2026-07-08T00:00:01+00:00",
    )
    assert run["mock"] is True
    assert run["input"] == {"x": 1}
    assert run["output"] == {"y": 2}

    runs = repos.list_tool_runs(conn, task["id"])
    assert len(runs) == 1
    assert runs[0]["tool_id"] == "mock_echo"


def test_record_and_list_model_call(conn) -> None:
    task = _new_task(conn)
    call = repos.record_model_call(
        conn, task_id=task["id"], agent_id="hello_agent", model_profile="reasoning",
        status="failed", error_message="缺少 env FLAI_LLM_API_KEY",
    )
    assert call["status"] == "failed"
    assert call["token_usage"] is None

    calls = repos.list_model_calls(conn, task["id"])
    assert len(calls) == 1
    assert calls[0]["model_profile"] == "reasoning"


def test_record_and_list_sample(conn) -> None:
    task = _new_task(conn)
    sample = repos.record_sample(
        conn, task_id=task["id"], agent_id="hello_agent", agent_version="0.1.0",
        input_json={"name": "张三"}, output_json={"greeting": "你好，张三"},
        accepted_by_engineer=True,
    )
    assert sample["input"] == {"name": "张三"}
    assert sample["accepted_by_engineer"] is True

    samples = repos.list_samples(conn, task["id"])
    assert len(samples) == 1
