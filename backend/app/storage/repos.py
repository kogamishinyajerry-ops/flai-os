"""任务/事件/文件/工具运行/模型调用/样本的仓储函数层（stdlib sqlite3，ADR-0008）。

约定：
- 每个函数第一参数是已打开的 `sqlite3.Connection`（调用方负责生命周期）。
- 返回值一律是 dict，且把 `_json` 后缀的存储列解码为去掉后缀的 Python 对象
  （如 `inputs_json` 列 -> 返回 dict 里的 `inputs` 键），方便上层直接消费。
- 所有时间戳字段一律 `datetime.now(timezone.utc).isoformat()`（UTC ISO 8601）。
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from jsonschema import ValidationError, validate

from ..config import CONTRACTS_DIR
from ..core.errors import TaskNotFoundError
from ..core.statemachine import assert_transition, is_terminal

_EVENT_SCHEMA_PATH = CONTRACTS_DIR / "event.schema.json"
_event_schema_cache: dict[str, Any] | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_event_schema() -> dict[str, Any]:
    global _event_schema_cache
    if _event_schema_cache is None:
        _event_schema_cache = json.loads(_EVENT_SCHEMA_PATH.read_text(encoding="utf-8"))
    return _event_schema_cache


def _decode_json(d: dict[str, Any], json_key: str, out_key: str | None = None, default: Any = None) -> None:
    """把 d[json_key]（JSON 文本或 None）原地解码进 d[out_key]，并弹出原始列。"""
    out_key = out_key or json_key.removesuffix("_json")
    raw = d.pop(json_key, None)
    if raw is None:
        d[out_key] = default
    else:
        d[out_key] = json.loads(raw)


# ── tasks ──────────────────────────────────────────────────────────────

def _decode_task(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    _decode_json(d, "input_file_ids", default=[])
    _decode_json(d, "output_file_ids", default=[])
    _decode_json(d, "inputs_json", "inputs", default={})
    _decode_json(d, "metadata_json", "metadata", default={})
    return d


def create_task(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    agent_id: str,
    agent_version: str,
    name: str | None,
    created_by: str,
    inputs: dict[str, Any] | None = None,
    input_file_ids: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """建任务：初始态永远是 created（未入队）。"""
    now = _now_iso()
    conn.execute(
        """
        INSERT INTO tasks
            (id, agent_id, agent_version, name, status, created_by,
             created_at, updated_at, started_at, finished_at,
             input_file_ids, output_file_ids, inputs_json, error_message, metadata_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            task_id, agent_id, agent_version, name, "created", created_by,
            now, now, None, None,
            json.dumps(input_file_ids or [], ensure_ascii=False),
            json.dumps([], ensure_ascii=False),
            json.dumps(inputs or {}, ensure_ascii=False),
            None,
            json.dumps(metadata or {}, ensure_ascii=False),
        ),
    )
    return get_task(conn, task_id)  # type: ignore[return-value]


def get_task(conn: sqlite3.Connection, task_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return _decode_task(row) if row is not None else None


def list_tasks(
    conn: sqlite3.Connection,
    *,
    agent_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if agent_id is not None:
        clauses.append("agent_id = ?")
        params.append(agent_id)
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    rows = conn.execute(
        f"SELECT * FROM tasks {where} ORDER BY created_at DESC LIMIT ?", params
    ).fetchall()
    return [_decode_task(r) for r in rows]


def set_task_status(
    conn: sqlite3.Connection,
    task_id: str,
    new_status: str,
    *,
    error_message: str | None = None,
) -> dict[str, Any]:
    """状态迁移入口：读-验-写整体包进 BEGIN IMMEDIATE 事务（P2-5：与 claim_next_queued
    同一防 TOCTOU 手法）——否则两个调用方可能并发读到同一 current 状态、都通过
    assert_transition、都写入，产生非法的"双写"竞态。据新态自动填 started_at/finished_at。
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        task = get_task(conn, task_id)
        if task is None:
            raise TaskNotFoundError(f"任务不存在：{task_id}")
        assert_transition(task["status"], new_status)

        now = _now_iso()
        updates: dict[str, Any] = {"status": new_status, "updated_at": now}
        if new_status == "running" and task.get("started_at") is None:
            updates["started_at"] = now
        if is_terminal(new_status):
            updates["finished_at"] = now
        if error_message is not None:
            updates["error_message"] = error_message

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE tasks SET {set_clause} WHERE id = ?",
            (*updates.values(), task_id),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return get_task(conn, task_id)  # type: ignore[return-value]


def claim_next_queued(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """原子拾取一条 queued 任务并转 validating（BEGIN IMMEDIATE 独占写锁，先来先服务）。

    无 queued 任务返回 None。两个调用方并发调用本函数时，sqlite 的
    IMMEDIATE 锁保证同一行只会被其中一次调用拾取（另一次要么看不到该行
    已被更新前的状态，要么被阻塞到第一次提交后重新读到 validating 而非
    queued，从而拿不到同一任务）。
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            "SELECT id FROM tasks WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        if row is None:
            conn.execute("COMMIT")
            return None
        task_id = row["id"]
        assert_transition("queued", "validating")
        now = _now_iso()
        conn.execute(
            "UPDATE tasks SET status = 'validating', updated_at = ? WHERE id = ? AND status = 'queued'",
            (now, task_id),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return get_task(conn, task_id)


def set_task_outputs(conn: sqlite3.Connection, task_id: str, output_file_ids: list[str]) -> dict[str, Any]:
    now = _now_iso()
    conn.execute(
        "UPDATE tasks SET output_file_ids = ?, updated_at = ? WHERE id = ?",
        (json.dumps(output_file_ids, ensure_ascii=False), now, task_id),
    )
    return get_task(conn, task_id)  # type: ignore[return-value]


# ── task_events ────────────────────────────────────────────────────────

def _decode_event(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d.pop("id", None)  # sqlite 自增主键仅内部用；对外唯一键=event_id（P1-2/P1-3 契约对账）。
    _decode_json(d, "payload_json", "payload", default={})
    return d


def append_event(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    agent_id: str | None = None,
    event_type: str,
    level: str,
    message: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """写事件：先对 contracts/event.schema.json 做整对象校验，非法即抛 ValueError。

    这是「事件枚举在写入口强制」的咬合点——event_type/level 若不在契约枚举内，
    jsonschema 校验必炸，不允许绕过 API 层校验直接写库产生脏事件。
    """
    payload = payload or {}
    event_id = str(uuid.uuid4())
    created_at = _now_iso()
    event_obj: dict[str, Any] = {
        "event_id": event_id,
        "task_id": task_id,
        "event_type": event_type,
        "level": level,
        "message": message,
        "payload": payload,
        "created_at": created_at,
    }
    if agent_id is not None:
        event_obj["agent_id"] = agent_id

    try:
        validate(event_obj, _load_event_schema())
    except ValidationError as exc:
        raise ValueError(f"事件契约校验失败：{exc.message}") from exc

    cur = conn.execute(
        """
        INSERT INTO task_events (event_id, task_id, agent_id, event_type, level, message, payload_json, created_at)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (event_id, task_id, agent_id, event_type, level, message,
         json.dumps(payload, ensure_ascii=False), created_at),
    )
    row = conn.execute("SELECT * FROM task_events WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _decode_event(row)


def list_events(conn: sqlite3.Connection, task_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM task_events WHERE task_id = ? ORDER BY id ASC", (task_id,)
    ).fetchall()
    return [_decode_event(r) for r in rows]


# ── files ──────────────────────────────────────────────────────────────

def create_file(
    conn: sqlite3.Connection,
    *,
    file_id: str,
    task_id: str | None = None,
    kind: str,
    filename: str,
    path: str,
    size_bytes: int,
    sha256: str,
) -> dict[str, Any]:
    now = _now_iso()
    conn.execute(
        """
        INSERT INTO files (id, task_id, kind, filename, path, size_bytes, sha256, created_at)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (file_id, task_id, kind, filename, path, size_bytes, sha256, now),
    )
    return get_file(conn, file_id)  # type: ignore[return-value]


def get_file(conn: sqlite3.Connection, file_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    return dict(row) if row is not None else None


# ── feedback ───────────────────────────────────────────────────────────

def create_feedback(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    agent_id: str | None,
    agent_version: str | None,
    rating: str,
    category: str,
    message: str | None,
    created_by: str,
) -> dict[str, Any]:
    """插一条任务反馈（任务书 §7.8）。rating/category 枚举由 API 层 Literal 锁定，
    本层不重复校验（与 tasks 层"状态枚举在 statemachine 锁、repos 只执行"同一分层）。
    """
    now = _now_iso()
    cur = conn.execute(
        """
        INSERT INTO feedback
            (task_id, agent_id, agent_version, rating, category, message, created_by, created_at)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (task_id, agent_id, agent_version, rating, category, message, created_by, now),
    )
    row = conn.execute("SELECT * FROM feedback WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


def list_feedback(conn: sqlite3.Connection, task_id: str) -> list[dict[str, Any]]:
    """按 created_at 升序返回任务的全部反馈；同刻并列以自增 id 升序稳定去歧
    （id 单调递增与写入顺序一致，排序语义不变，只是消除同一微秒内的不确定序）。
    """
    rows = conn.execute(
        "SELECT * FROM feedback WHERE task_id = ? ORDER BY created_at ASC, id ASC", (task_id,)
    ).fetchall()
    return [dict(r) for r in rows]


# ── tool_runs ──────────────────────────────────────────────────────────

def _decode_tool_run(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["mock"] = bool(d["mock"])
    _decode_json(d, "input_json", "input", default=None)
    _decode_json(d, "output_json", "output", default=None)
    return d


def record_tool_run(
    conn: sqlite3.Connection,
    *,
    task_id: str | None = None,
    tool_id: str,
    tool_version: str,
    mock: bool,
    status: str,
    input_json: dict[str, Any],
    output_json: dict[str, Any] | None = None,
    raw_input_path: str | None = None,
    raw_output_path: str | None = None,
    error_message: str | None = None,
    started_at: str,
    finished_at: str | None = None,
) -> dict[str, Any]:
    cur = conn.execute(
        """
        INSERT INTO tool_runs
            (task_id, tool_id, tool_version, mock, status, input_json, output_json,
             raw_input_path, raw_output_path, error_message, started_at, finished_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            task_id, tool_id, tool_version, int(bool(mock)), status,
            json.dumps(input_json, ensure_ascii=False),
            json.dumps(output_json, ensure_ascii=False) if output_json is not None else None,
            raw_input_path, raw_output_path, error_message, started_at, finished_at,
        ),
    )
    row = conn.execute("SELECT * FROM tool_runs WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _decode_tool_run(row)


def list_tool_runs(conn: sqlite3.Connection, task_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM tool_runs WHERE task_id = ? ORDER BY id ASC", (task_id,)
    ).fetchall()
    return [_decode_tool_run(r) for r in rows]


# ── model_calls ────────────────────────────────────────────────────────

def _decode_model_call(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    _decode_json(d, "token_usage_json", "token_usage", default=None)
    return d


def record_model_call(
    conn: sqlite3.Connection,
    *,
    task_id: str | None = None,
    agent_id: str | None = None,
    model_profile: str,
    model_name: str | None = None,
    status: str,
    request_summary: str | None = None,
    response_summary: str | None = None,
    error_message: str | None = None,
    token_usage_json: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    created_at = created_at or _now_iso()
    cur = conn.execute(
        """
        INSERT INTO model_calls
            (task_id, agent_id, model_profile, model_name, status,
             request_summary, response_summary, error_message, token_usage_json, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            task_id, agent_id, model_profile, model_name, status,
            request_summary, response_summary, error_message,
            json.dumps(token_usage_json, ensure_ascii=False) if token_usage_json is not None else None,
            created_at,
        ),
    )
    row = conn.execute("SELECT * FROM model_calls WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _decode_model_call(row)


def list_model_calls(conn: sqlite3.Connection, task_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM model_calls WHERE task_id = ? ORDER BY id ASC", (task_id,)
    ).fetchall()
    return [_decode_model_call(r) for r in rows]


# ── samples ────────────────────────────────────────────────────────────

def _decode_sample(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    _decode_json(d, "input_json", "input", default=None)
    _decode_json(d, "output_json", "output", default=None)
    if d.get("accepted_by_engineer") is not None:
        d["accepted_by_engineer"] = bool(d["accepted_by_engineer"])
    return d


def record_sample(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    agent_id: str,
    agent_version: str,
    tool_id: str | None = None,
    tool_version: str | None = None,
    case_id: str | None = None,
    input_json: dict[str, Any],
    output_json: dict[str, Any] | None = None,
    raw_input_path: str | None = None,
    raw_output_path: str | None = None,
    validation_status: str | None = None,
    accepted_by_engineer: bool | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    created_at = created_at or _now_iso()
    accepted_int = None if accepted_by_engineer is None else int(bool(accepted_by_engineer))
    cur = conn.execute(
        """
        INSERT INTO samples
            (task_id, agent_id, agent_version, tool_id, tool_version, case_id,
             input_json, output_json, raw_input_path, raw_output_path,
             validation_status, accepted_by_engineer, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            task_id, agent_id, agent_version, tool_id, tool_version, case_id,
            json.dumps(input_json, ensure_ascii=False),
            json.dumps(output_json, ensure_ascii=False) if output_json is not None else None,
            raw_input_path, raw_output_path, validation_status, accepted_int, created_at,
        ),
    )
    row = conn.execute("SELECT * FROM samples WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _decode_sample(row)


def list_samples(conn: sqlite3.Connection, task_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM samples WHERE task_id = ? ORDER BY id ASC", (task_id,)
    ).fetchall()
    return [_decode_sample(r) for r in rows]
