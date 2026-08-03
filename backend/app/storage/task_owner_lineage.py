"""Pure owner-lineage authorization for persisted user tasks.

This module deliberately has no FastAPI dependency.  HTTP callers collapse
``TaskOwnerLineageViolation`` to their generic 404, while worker/runtime callers
use the same bounded policy before opening package or input bytes.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from typing import Any, NoReturn


class TaskOwnerLineageViolation(RuntimeError):
    """Persisted task lineage cannot be proven to one exact owner."""


_MAX_TASK_LINEAGE_NODES = 128
_MAX_TASK_LINEAGE_DEPTH = 32
_MAX_TASK_INPUT_FILE_IDS = 512
MAX_TASK_OUTPUT_FILE_IDS = 512
CONVERSATION_LINEAGE_MAX_MESSAGES = 4096
CONVERSATION_LINEAGE_MAX_FILE_IDS = 4096


class _TaskLineageState:
    """Bounded traversal state; a fresh instance is required per decision."""

    def __init__(self, principal: str) -> None:
        self.principal = principal
        self.active: set[str] = set()
        self.discovered: set[str] = set()
        self.validated: dict[str, dict[str, Any]] = {}
        self.validated_depths: dict[str, int] = {}
        self.validated_conversations: set[str] = set()
        self.conversation_messages = 0
        self.file_ids = 0


def _reject() -> NoReturn:
    raise TaskOwnerLineageViolation("task owner lineage is unavailable")


def _canonical_username(value: object) -> str | None:
    if isinstance(value, str) and value and value == value.strip():
        return value
    return None


def _canonical_resource_id(value: object, *, max_length: int = 64) -> str | None:
    if (
        isinstance(value, str)
        and value
        and value == value.strip()
        and len(value) <= max_length
    ):
        return value
    return None


def _canonical_id_list(
    value: object,
    *,
    max_items: int,
    max_id_length: int = 64,
) -> list[str]:
    if not isinstance(value, list) or len(value) > max_items:
        _reject()
    result: list[str] = []
    seen: set[str] = set()
    for raw_id in value:
        resource_id = _canonical_resource_id(raw_id, max_length=max_id_length)
        if resource_id is None or resource_id in seen:
            _reject()
        seen.add(resource_id)
        result.append(resource_id)
    return result


def _decode_json(raw: object, *, default: Any) -> Any:
    if raw is None:
        return default
    if not isinstance(raw, str):
        _reject()
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        _reject()


def _decode_task_row(row: sqlite3.Row) -> dict[str, Any]:
    task = dict(row)
    task["input_file_ids"] = _decode_json(
        task.get("input_file_ids"),
        default=[],
    )
    task["output_file_ids"] = _decode_json(
        task.get("output_file_ids"),
        default=[],
    )
    task["inputs"] = _decode_json(task.pop("inputs_json", None), default={})
    task["metadata"] = _decode_json(
        task.pop("metadata_json", None),
        default={},
    )
    task["depends_on"] = (
        _decode_json(task.get("depends_on"), default=[])
        if task.get("depends_on")
        else []
    )
    task["input_binding"] = (
        _decode_json(task.get("input_binding"), default=None)
        if task.get("input_binding")
        else None
    )
    task["retry_of"] = task.get("retry_of")
    return task


def _load_task(conn: sqlite3.Connection, task_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        _reject()
    return _decode_task_row(row)


def _load_file(
    conn: sqlite3.Connection,
    file_id: str,
) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    if row is None:
        _reject()
    return dict(row)


def require_exact_owner(
    owner_username: object,
    authenticated_username: object,
) -> None:
    principal = _canonical_username(authenticated_username)
    owner = _canonical_username(owner_username)
    if principal is None or owner is None or owner != principal:
        _reject()


def _task_output_file_ids(task: Mapping[str, Any]) -> list[str]:
    return _canonical_id_list(
        task.get("output_file_ids"),
        max_items=MAX_TASK_OUTPUT_FILE_IDS,
    )


def _require_output_file_relation(
    record: Mapping[str, Any],
    task: Mapping[str, Any],
) -> None:
    file_id = _canonical_resource_id(record.get("id"))
    task_id = _canonical_resource_id(task.get("id"))
    if (
        file_id is None
        or task_id is None
        or record.get("kind") != "output"
        or record.get("task_id") != task_id
        or file_id not in _task_output_file_ids(task)
    ):
        _reject()


def _require_task_output_relations(
    conn: sqlite3.Connection,
    task: Mapping[str, Any],
) -> None:
    for file_id in _task_output_file_ids(task):
        _require_output_file_relation(_load_file(conn, file_id), task)


def _require_conversation_lineage(
    conn: sqlite3.Connection,
    conversation_id: str,
    state: _TaskLineageState,
) -> None:
    if conversation_id in state.validated_conversations:
        return

    row = conn.execute(
        "SELECT created_by_username FROM conversations WHERE id = ?",
        (conversation_id,),
    ).fetchone()
    if row is None:
        _reject()
    require_exact_owner(row["created_by_username"], state.principal)

    remaining_messages = (
        CONVERSATION_LINEAGE_MAX_MESSAGES - state.conversation_messages
    )
    remaining_file_ids = CONVERSATION_LINEAGE_MAX_FILE_IDS - state.file_ids
    if remaining_messages < 0 or remaining_file_ids < 0:
        _reject()
    messages = conn.execute(
        "SELECT file_ids FROM conversation_messages "
        "WHERE conversation_id = ? ORDER BY id ASC LIMIT ?",
        (conversation_id, remaining_messages + 1),
    ).fetchall()
    if len(messages) > remaining_messages:
        _reject()

    historical_file_ids: list[str] = []
    for message in messages:
        decoded = _decode_json(message["file_ids"], default=[])
        if not isinstance(decoded, list):
            _reject()
        if len(historical_file_ids) + len(decoded) > remaining_file_ids:
            _reject()
        historical_file_ids.extend(decoded)

    for raw_file_id in historical_file_ids:
        file_id = _canonical_resource_id(raw_file_id)
        if file_id is None:
            _reject()
        record = _load_file(conn, file_id)
        if record.get("kind") != "input":
            _reject()
        require_exact_owner(record.get("owner_username"), state.principal)

    state.conversation_messages += len(messages)
    state.file_ids += len(historical_file_ids)
    state.validated_conversations.add(conversation_id)


def _require_user_task_lineage(
    conn: sqlite3.Connection,
    task: dict[str, Any],
    state: _TaskLineageState,
    *,
    depth: int,
    prospective_tasks: Mapping[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    task_id = _canonical_resource_id(task.get("id"))
    if task_id is None or depth > _MAX_TASK_LINEAGE_DEPTH:
        _reject()
    if task_id in state.active:
        _reject()

    validated_depth = state.validated_depths.get(task_id)
    if validated_depth is not None and validated_depth >= depth:
        return state.validated[task_id]

    newly_discovered = task_id not in state.discovered
    if newly_discovered:
        if len(state.discovered) >= _MAX_TASK_LINEAGE_NODES:
            _reject()
        state.discovered.add(task_id)

    if task.get("origin") != "user":
        _reject()
    require_exact_owner(task.get("created_by_username"), state.principal)
    _require_task_output_relations(conn, task)
    state.active.add(task_id)

    conversation_id = task.get("conversation_id")
    if conversation_id is not None:
        canonical_conversation_id = _canonical_resource_id(
            conversation_id,
            max_length=100,
        )
        if canonical_conversation_id is None:
            _reject()
        _require_conversation_lineage(conn, canonical_conversation_id, state)

    input_file_ids = _canonical_id_list(
        task.get("input_file_ids"),
        max_items=_MAX_TASK_INPUT_FILE_IDS,
    )
    if newly_discovered:
        if state.file_ids + len(input_file_ids) > CONVERSATION_LINEAGE_MAX_FILE_IDS:
            _reject()
        state.file_ids += len(input_file_ids)

    output_sources: dict[str, list[dict[str, Any]]] = {}
    for file_id in input_file_ids:
        record = _load_file(conn, file_id)
        if record.get("kind") == "input":
            require_exact_owner(record.get("owner_username"), state.principal)
            continue
        if record.get("kind") != "output":
            _reject()
        source_task_id = _canonical_resource_id(record.get("task_id"))
        if source_task_id is None:
            _reject()
        output_sources.setdefault(source_task_id, []).append(record)

    depends_on = _canonical_id_list(task.get("depends_on"), max_items=32)
    input_binding = task.get("input_binding")
    binding_refs: list[str] = []
    if input_binding is not None:
        if not isinstance(input_binding, Mapping):
            _reject()
        if set(input_binding) - {"from_tasks"}:
            _reject()
        binding_refs = _canonical_id_list(
            input_binding.get("from_tasks", []),
            max_items=32,
        )
        if any(ref not in depends_on for ref in binding_refs):
            _reject()

    retry_of = task.get("retry_of")
    retry_refs: list[str] = []
    if retry_of is not None:
        canonical_retry = _canonical_resource_id(retry_of)
        if canonical_retry is None:
            _reject()
        retry_refs.append(canonical_retry)

    upstream_ids = list(
        dict.fromkeys(
            [*depends_on, *binding_refs, *retry_refs, *output_sources]
        )
    )
    validated_upstreams: dict[str, dict[str, Any]] = {}
    for upstream_id in upstream_ids:
        upstream = (
            prospective_tasks.get(upstream_id)
            if prospective_tasks is not None
            else None
        )
        if upstream is None:
            upstream = _load_task(conn, upstream_id)
        validated_upstreams[upstream_id] = _require_user_task_lineage(
            conn,
            upstream,
            state,
            depth=depth + 1,
            prospective_tasks=prospective_tasks,
        )

    for source_task_id, records in output_sources.items():
        source_task = validated_upstreams[source_task_id]
        for record in records:
            _require_output_file_relation(record, source_task)

    state.active.remove(task_id)
    state.validated[task_id] = task
    state.validated_depths[task_id] = max(
        depth,
        validated_depth if validated_depth is not None else -1,
    )
    return task


def require_worker_task_owner_lineage(
    conn: sqlite3.Connection,
    task: Mapping[str, Any],
) -> dict[str, Any]:
    """Authorize one claimed user task using its immutable root owner."""

    root = dict(task)
    principal = _canonical_username(root.get("created_by_username"))
    if principal is None:
        _reject()
    return _require_user_task_lineage(
        conn,
        root,
        _TaskLineageState(principal),
        depth=0,
    )


def require_owned_user_task(
    conn: sqlite3.Connection,
    task_id: str,
    username: object,
) -> dict[str, Any]:
    """Authorize a persisted user task for an explicit principal."""

    principal = _canonical_username(username)
    canonical_task_id = _canonical_resource_id(task_id)
    if principal is None or canonical_task_id is None:
        _reject()
    return _require_user_task_lineage(
        conn,
        _load_task(conn, canonical_task_id),
        _TaskLineageState(principal),
        depth=0,
    )


def require_prospective_user_task_lineage(
    conn: sqlite3.Connection,
    tasks: list[Mapping[str, Any]],
    username: object,
) -> None:
    """Validate virtual roots with the same traversal and aggregate bounds."""

    principal = _canonical_username(username)
    if principal is None or not isinstance(tasks, list) or not tasks:
        _reject()

    prospective: dict[str, dict[str, Any]] = {}
    ordered_ids: list[str] = []
    for raw_task in tasks:
        if not isinstance(raw_task, Mapping):
            _reject()
        task = dict(raw_task)
        task_id = _canonical_resource_id(task.get("id"))
        if task_id is None or task_id in prospective:
            _reject()
        prospective[task_id] = task
        ordered_ids.append(task_id)

    state = _TaskLineageState(principal)
    for task_id in ordered_ids:
        _require_user_task_lineage(
            conn,
            prospective[task_id],
            state,
            depth=0,
            prospective_tasks=prospective,
        )
