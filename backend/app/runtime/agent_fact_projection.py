"""One privacy-bounded, full Agent fact snapshot for a conversation.

FLAi owns task dependencies and human decisions.  JerryAgent can only add
sanitized internal runtime observations; it can never approve or sign a task.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from time import monotonic as _monotonic
from typing import Any

from .jerryagent_adapter import JerryAgentFactsUnavailable
from ..storage import repos

SCHEMA_VERSION = "agent_fact_projection.v1"
TASK_LIMIT = 100
EVENT_QUERY_LIMIT = 4096
JERRY_SNAPSHOT_BUDGET_S = 2.0
_MALFORMED_BINDING = object()
_RUNTIME_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_JERRY_RUNTIME_STATUSES = frozenset(
    {"queued", "running", "awaiting_approval", "completed", "failed", "cancelled"}
)
_SAFE_INTEGER_MAX = 9_007_199_254_740_991

_PHASE_BY_STATUS = {
    "created": "queued",
    "queued": "queued",
    "validating": "working",
    "running": "working",
    "parsing": "working",
    "analyzing": "working",
    "waiting_review": "awaiting_signoff",
    "completed": "settled",
    "failed": "failed",
    "cancelled": "cancelled",
}


class AgentFactProjectionUnavailable(RuntimeError):
    """The authoritative snapshot cannot be projected without leaking or lying."""


def _utc_z(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Agent fact timestamps must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _chunks(values: list[str], size: int = 400) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _load_tasks(conn: sqlite3.Connection, task_ids: list[str]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for chunk in _chunks(list(dict.fromkeys(task_ids))):
        marks = ",".join("?" for _ in chunk)
        for row in conn.execute(f"SELECT * FROM tasks WHERE id IN ({marks})", chunk):
            decoded = repos.get_task(conn, str(row["id"]))
            if decoded is not None:
                result[str(row["id"])] = decoded
    return result


def _frozen_dependency_ids(tasks: list[dict[str, Any]]) -> list[str]:
    dependency_ids: list[str] = []
    for task in tasks:
        frozen = task.get("depends_on")
        if not isinstance(frozen, list) or any(
            not isinstance(task_id, str) or not task_id for task_id in frozen
        ):
            raise AgentFactProjectionUnavailable("corrupt frozen dependency set")
        if len(frozen) != len(set(frozen)):
            raise AgentFactProjectionUnavailable("corrupt frozen dependency set")
        dependency_ids.extend(frozen)
    return dependency_ids


def _validate_dependency_scope(
    *,
    dependency_ids: list[str],
    dependencies_by_id: dict[str, dict[str, Any]],
    conversation_id: str,
) -> None:
    expected = set(dependency_ids)
    if set(dependencies_by_id) != expected or any(
        dependency.get("conversation_id") != conversation_id
        for dependency in dependencies_by_id.values()
    ):
        raise AgentFactProjectionUnavailable("corrupt frozen dependency scope")


def _load_decisions(
    conn: sqlite3.Connection, task_ids: list[str]
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for chunk in _chunks(list(dict.fromkeys(task_ids))):
        marks = ",".join("?" for _ in chunk)
        rows = conn.execute(
            """
            SELECT decision.*,
                   task.id AS _task_id,
                   task.agent_id AS _task_agent_id,
                   task.status AS _task_status,
                   task.updated_at AS _task_updated_at,
                   task.finished_at AS _task_finished_at,
                   task.error_message AS _task_error_message,
                   CASE
                     WHEN decision.paired_advice_id IS NULL THEN 1
                     WHEN EXISTS (
                       SELECT 1 FROM task_review_advice AS paired
                       WHERE paired.id = decision.paired_advice_id
                         AND paired.task_id = decision.task_id
                     ) THEN 1 ELSE 0
                   END AS _paired_advice_valid,
                   witness.event_id AS _witness_event_id,
                   witness.event_internal_id AS _witness_internal_id,
                   witness.task_id AS _witness_task_id,
                   witness.agent_id AS _witness_agent_id,
                   witness.event_type AS _witness_event_type,
                   witness.level AS _witness_level,
                   witness.message AS _witness_message,
                   witness.payload_json AS _witness_payload_json,
                   witness.created_at AS _witness_created_at,
                   witness.decision_id AS _witness_decision_id,
                   witness.witness_kind AS _witness_kind,
                   witness.schema_version AS _witness_schema_version,
                   review.id AS _review_internal_id,
                   review.event_id AS _review_event_id,
                   review.task_id AS _review_task_id,
                   review.agent_id AS _review_agent_id,
                   review.event_type AS _review_event_type,
                   review.level AS _review_level,
                   review.message AS _review_message,
                   review.payload_json AS _review_payload_json,
                   review.created_at AS _review_created_at
            FROM task_human_decisions AS decision
            JOIN tasks AS task ON task.id = decision.task_id
            LEFT JOIN task_review_event_witnesses AS witness
              ON witness.decision_id = decision.id
             AND witness.witness_kind = 'structured_v1'
            LEFT JOIN task_events AS review
              ON review.event_id = witness.event_id
            """
            f"WHERE decision.task_id IN ({marks})",
            chunk,
        ).fetchall()
        for row in rows:
            decoded = dict(row)
            decoded["_projection_trusted"] = _decision_is_projection_trusted(decoded)
            result[str(row["task_id"])] = decoded
    return result


def _strict_json_object(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, str):
        return None

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = item
        return result

    try:
        decoded = json.loads(value, object_pairs_hook=unique_object)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return decoded if isinstance(decoded, dict) else None


def _decision_is_projection_trusted(decision: dict[str, Any]) -> bool:
    action = decision.get("action")
    if action not in {"approve", "reject"}:
        return False
    expected_status = "completed" if action == "approve" else "failed"
    expected_event_type = "review_approved" if action == "approve" else "review_rejected"
    expected_level = "info" if action == "approve" else "warning"
    expected_error = None
    if action == "reject":
        reason = decision.get("reason_code")
        if reason not in {
            "source_doubt",
            "method_error",
            "conclusion_overreach",
            "insufficient_evidence",
            "classification_issue",
            "other",
        }:
            return False
        expected_error = (
            f"人工拒绝（reviewer={decision.get('reviewer_display_name')}；"
            f"reason={reason}）"
        ) + (f"：{decision['comment']}" if decision.get("comment") is not None else "")
    elif decision.get("reason_code") is not None:
        return False

    exact_snapshot = (
        type(decision.get("schema_version")) is int
        and decision["schema_version"] == 1
        and decision.get("task_id") == decision.get("_task_id")
        and decision.get("_task_status") == expected_status
        and decision.get("_task_updated_at") == decision.get("created_at")
        and decision.get("_task_finished_at") == decision.get("created_at")
        and decision.get("_task_error_message") == expected_error
        and decision.get("_paired_advice_valid") == 1
        and decision.get("_witness_event_id") == decision.get("_review_event_id")
        and type(decision.get("_witness_internal_id")) is int
        and decision["_witness_internal_id"] > 0
        and decision.get("_witness_internal_id")
        == decision.get("_review_internal_id")
        and decision.get("_witness_task_id") == decision.get("task_id")
        and decision.get("_witness_task_id") == decision.get("_review_task_id")
        and decision.get("_witness_agent_id") == decision.get("_task_agent_id")
        and decision.get("_witness_agent_id") == decision.get("_review_agent_id")
        and decision.get("_witness_event_type") == expected_event_type
        and decision.get("_witness_event_type") == decision.get("_review_event_type")
        and decision.get("_witness_level") == expected_level
        and decision.get("_witness_level") == decision.get("_review_level")
        and decision.get("_witness_message") == decision.get("_review_message")
        and decision.get("_witness_payload_json")
        == decision.get("_review_payload_json")
        and decision.get("_witness_created_at") == decision.get("_review_created_at")
        and decision.get("_witness_decision_id") == decision.get("id")
        and decision.get("_witness_kind") == "structured_v1"
        and type(decision.get("_witness_schema_version")) is int
        and decision["_witness_schema_version"] == 1
    )
    if not exact_snapshot:
        return False
    try:
        _utc_z(str(decision["created_at"]))
        _utc_z(str(decision["_witness_created_at"]))
    except (TypeError, ValueError):
        return False

    payload = _strict_json_object(decision.get("_review_payload_json"))
    return payload == {
        "reviewer": decision.get("reviewer_display_name"),
        "reviewer_username": decision.get("reviewer_username"),
        "comment": decision.get("comment"),
        "decision_id": decision.get("id"),
        "reason_code": decision.get("reason_code"),
        "paired_advice_id": decision.get("paired_advice_id"),
    }


def _load_handoffs(
    conn: sqlite3.Connection,
    tasks: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    result = {str(task["id"]): [] for task in tasks}
    tasks_by_id = {str(task["id"]): task for task in tasks}
    ids = list(result)
    for chunk in _chunks(ids):
        marks = ",".join("?" for _ in chunk)
        rows = conn.execute(
            "SELECT task_id, payload_json, created_at FROM task_events "
            f"WHERE task_id IN ({marks}) "
            "AND event_type = 'agent_log' "
            "AND CASE WHEN json_valid(payload_json) = 1 "
            "THEN json_extract(payload_json, '$.workflow_event_type') "
            "ELSE NULL END = ? "
            "ORDER BY id ASC LIMIT ?",
            [*chunk, "dependency_resolved", EVENT_QUERY_LIMIT + 1],
        ).fetchall()
        if len(rows) > EVENT_QUERY_LIMIT:
            raise AgentFactProjectionUnavailable("handoff event projection limit exceeded")
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            if (
                not isinstance(payload, dict)
                or payload.get("workflow_event_type") != "dependency_resolved"
                or not isinstance(payload.get("upstream_task_ids"), list)
            ):
                continue
            to_task_id = str(row["task_id"])
            task = tasks_by_id.get(to_task_id)
            if task is None:
                continue
            declared = set(task.get("depends_on") or [])
            seen: set[str] = set()
            for from_task_id in payload["upstream_task_ids"]:
                if (
                    isinstance(from_task_id, str)
                    and from_task_id in declared
                    and from_task_id not in seen
                ):
                    result[to_task_id].append(
                        {
                            "fromTaskId": from_task_id,
                            "toTaskId": to_task_id,
                            "at": _utc_z(str(row["created_at"])),
                        }
                    )
                    seen.add(from_task_id)
    return result


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_runtime_id(value: Any) -> bool:
    return isinstance(value, str) and _RUNTIME_ID_RE.fullmatch(value) is not None


def _is_safe_integer(value: Any) -> bool:
    return type(value) is int and 0 <= value <= _SAFE_INTEGER_MAX


def _is_runtime_identity(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value)
        == {
            "product",
            "schema",
            "runtimeEventSchemaVersion",
            "instanceId",
            "sessionId",
            "runtimeKind",
        }
        and value.get("product") == "JerryAgent"
        and value.get("schema") == "flai.agent-layer.v1"
        and type(value.get("runtimeEventSchemaVersion")) is int
        and value["runtimeEventSchemaVersion"] == 1
        and value.get("runtimeKind") in {"external", "native-owned"}
        and _is_runtime_id(value.get("instanceId"))
        and _is_runtime_id(value.get("sessionId"))
    )


def _load_jerry_bindings(
    conn: sqlite3.Connection,
    tasks: list[dict[str, Any]],
) -> dict[str, dict[str, Any] | object]:
    jerry_tasks = {
        str(task["id"]): task
        for task in tasks
        if task.get("execution_adapter") == "jerryagent_sidecar"
    }
    states: dict[str, dict[str, Any]] = {
        task_id: {
            "started": None,
            "submitted": None,
            "identity_bound": None,
            "receipt": None,
            "observed_revision": None,
            "bad": False,
        }
        for task_id in jerry_tasks
    }
    for chunk in _chunks(list(jerry_tasks)):
        marks = ",".join("?" for _ in chunk)
        rows = conn.execute(
            "SELECT task_id, agent_id, payload_json FROM task_events "
            f"WHERE task_id IN ({marks}) "
            "AND event_type = 'agent_log' "
            "AND CASE WHEN json_valid(payload_json) = 1 "
            "THEN json_extract(payload_json, '$.workflow_event_type') "
            "ELSE NULL END IN (?, ?, ?, ?, ?) "
            "ORDER BY id ASC LIMIT ?",
            [
                *chunk,
                "agent_layer_started",
                "agent_layer_submitted",
                "agent_layer_identity_bound",
                "agent_layer_observed",
                "agent_layer_receipt",
                EVENT_QUERY_LIMIT + 1,
            ],
        ).fetchall()
        if len(rows) > EVENT_QUERY_LIMIT:
            raise AgentFactProjectionUnavailable(
                "JerryAgent binding event projection limit exceeded"
            )
        for row in rows:
            task_id = str(row["task_id"])
            state = states[task_id]
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            event_type = payload.get("workflow_event_type")
            if row["agent_id"] != jerry_tasks[task_id].get("agent_id"):
                state["bad"] = True
                continue
            if event_type == "agent_layer_started":
                valid = (
                    state["started"] is None
                    and payload.get("adapter") == "jerryagent_sidecar"
                    and payload.get("contract_version") == "flai.agent-layer.v1"
                    and payload.get("execution_id") == task_id
                    and _is_sha256(payload.get("request_sha256"))
                    and isinstance(payload.get("runtime_instance_id"), str)
                    and bool(payload["runtime_instance_id"])
                    and isinstance(payload.get("runtime_session_id"), str)
                    and bool(payload["runtime_session_id"])
                    and payload.get("model_calls_attested_by_flai") is False
                )
                if not valid:
                    state["bad"] = True
                else:
                    state["started"] = dict(payload)
            elif event_type == "agent_layer_submitted":
                replayed = payload.get("replayed")
                receipt_recovered = payload.get("receipt_recovered")
                valid = (
                    state["started"] is not None
                    and state["submitted"] is None
                    and payload.get("execution_id") == task_id
                    and _is_runtime_id(payload.get("runtime_task_id"))
                    and type(receipt_recovered) is bool
                    and _is_safe_integer(payload.get("submission_attempts"))
                    and 1 <= payload["submission_attempts"] <= 2
                    and (
                        type(replayed) is bool
                        or (replayed is None and receipt_recovered is True)
                    )
                )
                if not valid:
                    state["bad"] = True
                else:
                    state["submitted"] = dict(payload)
            elif event_type == "agent_layer_identity_bound":
                identity = payload.get("runtime_identity")
                valid = (
                    state["submitted"] is not None
                    and state["identity_bound"] is None
                    and state["observed_revision"] is None
                    and state["receipt"] is None
                    and set(payload)
                    == {
                        "workflow_event_type",
                        "execution_id",
                        "runtime_task_id",
                        "request_sha256",
                        "runtime_identity",
                    }
                    and payload.get("execution_id") == task_id
                    and payload.get("runtime_task_id")
                    == state["submitted"]["runtime_task_id"]
                    and payload.get("request_sha256")
                    == state["started"]["request_sha256"]
                    and _is_runtime_identity(identity)
                    and (
                        state["submitted"]["replayed"] is not False
                        or (
                            identity["instanceId"]
                            == state["started"]["runtime_instance_id"]
                            and identity["sessionId"]
                            == state["started"]["runtime_session_id"]
                        )
                    )
                )
                if not valid:
                    state["bad"] = True
                else:
                    state["identity_bound"] = dict(payload)
            elif event_type == "agent_layer_observed":
                valid = (
                    state["identity_bound"] is not None
                    and payload.get("execution_id") == task_id
                    and payload.get("runtime_task_id")
                    == state["submitted"]["runtime_task_id"]
                    and payload.get("status") in _JERRY_RUNTIME_STATUSES
                    and _is_safe_integer(payload.get("revision"))
                )
                if not valid:
                    state["bad"] = True
                else:
                    prior = state["observed_revision"]
                    state["observed_revision"] = (
                        payload["revision"]
                        if prior is None
                        else max(prior, payload["revision"])
                    )
            elif event_type == "agent_layer_receipt":
                identity = payload.get("runtime_identity")
                valid = (
                    state["started"] is not None
                    and state["submitted"] is not None
                    and state["identity_bound"] is not None
                    and state["receipt"] is None
                    and payload.get("execution_adapter") == "jerryagent_sidecar"
                    and payload.get("execution_contract_version")
                    == "flai.agent-layer.v1"
                    and payload.get("execution_id") == task_id
                    and _is_sha256(payload.get("request_sha256"))
                    and _is_runtime_identity(identity)
                    and _is_safe_integer(payload.get("final_revision"))
                    and payload.get("model_calls_attested_by_flai") is False
                )
                if not valid:
                    state["bad"] = True
                else:
                    state["receipt"] = dict(payload)

    result: dict[str, dict[str, Any] | object] = {}
    for task_id, state in states.items():
        started = state["started"]
        submitted = state["submitted"]
        identity_bound = state["identity_bound"]
        receipt = state["receipt"]
        observed_revision = state["observed_revision"]
        if (
            state["bad"]
            or (started is None and (submitted is not None or receipt is not None))
            or (started is not None and submitted is None)
            or (submitted is not None and identity_bound is None)
        ):
            result[task_id] = _MALFORMED_BINDING
            continue
        if started is None:
            continue
        identity = identity_bound["runtime_identity"]
        if receipt is not None:
            if (
                receipt["request_sha256"] != started["request_sha256"]
                or receipt["runtime_identity"] != identity
                or (
                    observed_revision is not None
                    and receipt["final_revision"] < observed_revision
                )
            ):
                result[task_id] = _MALFORMED_BINDING
                continue
            result[task_id] = {
                "requestSha256": receipt["request_sha256"],
                "runtimeTaskId": submitted["runtime_task_id"],
                "instanceId": identity["instanceId"],
                "sessionId": identity["sessionId"],
                "runtimeKind": identity["runtimeKind"],
                "minimumRevision": max(
                    receipt["final_revision"], observed_revision or 0
                ),
            }
            continue
        if jerry_tasks[task_id].get("status") in {"waiting_review", "completed"}:
            result[task_id] = _MALFORMED_BINDING
            continue
        result[task_id] = {
            "requestSha256": started["request_sha256"],
            "runtimeTaskId": submitted["runtime_task_id"],
            "instanceId": identity["instanceId"],
            "sessionId": identity["sessionId"],
            "runtimeKind": identity["runtimeKind"],
            "minimumRevision": observed_revision,
        }
    return result


def _requires_human_review(
    conn: sqlite3.Connection, task: dict[str, Any]
) -> bool | None:
    manifest = repos.get_agent_version_manifest(
        conn, str(task["agent_id"]), str(task["agent_version"])
    )
    if not isinstance(manifest, dict):
        return None
    workflow = manifest.get("workflow")
    if not isinstance(workflow, dict) or type(workflow.get("requires_human_review")) is not bool:
        return None
    return workflow["requires_human_review"]


def _has_deterministic_provenance(
    conn: sqlite3.Connection, task: dict[str, Any]
) -> bool:
    """Project only the non-human K1 branch after the human decision was checked.

    ``repos.task_output_is_signed_off`` intentionally accepts either an exact
    review witness or an explicit deterministic manifest.  This projection has
    already validated the structured review decision above, so reusing that
    union here would let an intact but stale review event mask a tampered
    decision.  Keep the deterministic branch exact and version-frozen.
    """
    manifest = repos.get_agent_version_manifest(
        conn, str(task["agent_id"]), str(task["agent_version"])
    )
    if not isinstance(manifest, dict):
        return False
    model = manifest.get("model")
    workflow = manifest.get("workflow")
    return (
        isinstance(model, dict)
        and model.get("profile") == "none"
        and isinstance(workflow, dict)
        and workflow.get("requires_human_review") is False
    )


def _dependency_gate(
    conn: sqlite3.Connection,
    task: dict[str, Any],
    decision: dict[str, Any] | None,
) -> str:
    if task.get("status") in {"failed", "cancelled"}:
        return "failed"
    if decision is not None:
        if decision.get("_projection_trusted") is not True:
            return "unknown"
        return "human_signed" if decision.get("action") == "approve" else "failed"
    if task.get("status") != "completed":
        return "pending"
    # Historical deterministic release is keyed to the frozen agent_version,
    # never the mutable registry or a weak/stale human-review event.
    if _has_deterministic_provenance(conn, task):
        return "deterministic_provenance"
    return "unknown"


def _signoff(
    conn: sqlite3.Connection,
    task: dict[str, Any],
    decision: dict[str, Any] | None,
) -> dict[str, Any]:
    if decision is not None and decision.get("_projection_trusted") is True:
        return {
            "state": "approved" if decision["action"] == "approve" else "rejected",
            "requestedFrom": task.get("review_requested_from_username"),
            "reviewer": decision.get("reviewer_display_name"),
            "decidedAt": _utc_z(str(decision["created_at"])),
        }
    if decision is not None:
        return {
            "state": "unknown",
            "requestedFrom": task.get("review_requested_from_username"),
            "reviewer": None,
            "decidedAt": None,
        }
    requires_review = _requires_human_review(conn, task)
    if requires_review is True:
        state = "awaiting_human" if task.get("status") == "waiting_review" else "pending_result"
    elif requires_review is False:
        state = "not_required"
    else:
        state = "unknown"
    return {
        "state": state,
        "requestedFrom": task.get("review_requested_from_username"),
        "reviewer": None,
        "decidedAt": None,
    }


def _empty_runtime(adapter: str, reason: str) -> dict[str, Any]:
    return {
        "adapter": adapter,
        "reported": False,
        "reason": reason,
        "sourceEpoch": None,
        "revision": None,
        "status": None,
        "wait": None,
        "delegationHold": None,
        "subagentCount": 0,
        "subagentsTruncated": False,
        "subagents": [],
    }


def _runtime(
    task: dict[str, Any],
    reader: Any,
    binding: dict[str, Any] | object | None,
    *,
    skip_unreachable: bool = False,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    adapter = str(task.get("execution_adapter") or "native_python")
    if adapter != "jerryagent_sidecar":
        return _empty_runtime("native_python", "not_applicable")
    if skip_unreachable:
        return _empty_runtime(adapter, "unreachable")
    if reader is None or getattr(reader, "enabled", True) is not True:
        return _empty_runtime(adapter, "disabled")
    if binding is _MALFORMED_BINDING:
        return _empty_runtime(adapter, "malformed")
    if binding is None:
        return _empty_runtime(adapter, "not_found")
    try:
        fact = reader.read(
            str(task["id"]),
            expected_binding=binding,
            timeout_s=timeout_s,
        )
    except JerryAgentFactsUnavailable as exc:
        return _empty_runtime(adapter, exc.reason)
    except Exception:
        return _empty_runtime(adapter, "malformed")
    return {
        "adapter": adapter,
        "reported": True,
        "reason": "reported",
        "sourceEpoch": fact["sourceEpoch"],
        "revision": fact["revision"],
        "status": fact["status"],
        "wait": fact["wait"],
        "delegationHold": fact["delegationHold"],
        "subagentCount": fact["subagentCount"],
        "subagentsTruncated": fact["subagentsTruncated"],
        "subagents": fact["subagents"],
    }


def _task_wait(
    task: dict[str, Any],
    dependencies: list[dict[str, Any]],
    runtime: dict[str, Any],
) -> dict[str, Any] | None:
    if task.get("status") == "created" and task.get("depends_on"):
        unsettled = [
            item
            for item in dependencies
            if item["gate"] not in {"human_signed", "deterministic_provenance"}
        ]
        if not unsettled:
            return None
        subject = unsettled[0] if unsettled else None
        return {
            "kind": "dependency",
            "since": _utc_z(str(task["created_at"])),
            "subjectTaskId": subject["taskId"] if subject else None,
            "subjectAgentId": subject["agentId"] if subject else None,
            "subjectOrdinal": None,
            "pendingCount": len(unsettled),
            "continueWhen": "dependency_gate_satisfied",
        }
    if task.get("status") == "waiting_review":
        return {
            "kind": "human_signoff",
            "since": _utc_z(str(task["updated_at"])),
            "subjectTaskId": None,
            "subjectAgentId": None,
            "subjectOrdinal": None,
            "pendingCount": 1,
            "continueWhen": "human_decision_recorded",
        }
    runtime_wait = runtime.get("wait")
    if runtime.get("reported") is True and isinstance(runtime_wait, dict):
        return {
            "kind": runtime_wait["kind"],
            "since": runtime_wait["since"],
            "subjectTaskId": None,
            "subjectAgentId": None,
            "subjectOrdinal": runtime_wait["subjectOrdinal"],
            "pendingCount": runtime_wait["pendingCount"],
            "continueWhen": runtime_wait["continueWhen"],
        }
    return None


def project_agent_facts(
    conn: sqlite3.Connection,
    *,
    conversation_id: str,
    jerryagent_facts_reader: Any,
) -> dict[str, Any]:
    owns_transaction = not conn.in_transaction
    if owns_transaction:
        conn.execute("BEGIN")
    try:
        count = int(
            conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()[0]
        )
        tasks = repos.list_tasks(
            conn,
            conversation_id=conversation_id,
            limit=TASK_LIMIT,
            offset=0,
        )
        dependency_ids = _frozen_dependency_ids(tasks)
        dependencies_by_id = _load_tasks(conn, dependency_ids)
        _validate_dependency_scope(
            dependency_ids=dependency_ids,
            dependencies_by_id=dependencies_by_id,
            conversation_id=conversation_id,
        )
        decisions = _load_decisions(
            conn, [str(task["id"]) for task in tasks] + dependency_ids
        )
        handoffs = _load_handoffs(conn, tasks)
        jerry_bindings = _load_jerry_bindings(conn, tasks)
        flai_facts: list[tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]] = []
        for task in tasks:
            dependency_facts: list[dict[str, Any]] = []
            for dependency_id in task.get("depends_on") or []:
                dependency = dependencies_by_id[dependency_id]
                dependency_facts.append(
                    {
                        "taskId": str(dependency["id"]),
                        "agentId": str(dependency["agent_id"]),
                        "status": str(dependency["status"]),
                        "gate": _dependency_gate(
                            conn,
                            dependency,
                            decisions.get(str(dependency["id"])),
                        ),
                    }
                )
            flai_facts.append(
                (
                    task,
                    dependency_facts,
                    _signoff(
                        conn,
                        task,
                        decisions.get(str(task["id"])),
                    ),
                )
            )
        if owns_transaction:
            conn.execute("COMMIT")
    except Exception:
        if owns_transaction and conn.in_transaction:
            conn.execute("ROLLBACK")
        raise

    projected: list[dict[str, Any]] = []
    jerry_unreachable = False
    jerry_deadline = _monotonic() + JERRY_SNAPSHOT_BUDGET_S
    for task, dependency_facts, signoff in flai_facts:
        remaining_runtime_budget = jerry_deadline - _monotonic()
        runtime = _runtime(
            task,
            jerryagent_facts_reader,
            jerry_bindings.get(str(task["id"])),
            skip_unreachable=(
                jerry_unreachable or remaining_runtime_budget <= 0
            ),
            timeout_s=min(1.0, max(remaining_runtime_budget, 0.0)),
        )
        # One loopback transport failure is enough evidence for this full
        # snapshot.  Do not multiply a one-second timeout across up to 100
        # Jerry tasks; later tasks truthfully share the closed reason.
        if runtime["reason"] == "unreachable":
            jerry_unreachable = True
        status = str(task["status"])
        phase = (
            "waiting_upstream"
            if status == "created" and task.get("depends_on")
            else _PHASE_BY_STATUS.get(status, "failed")
        )
        projected.append(
            {
                "taskId": str(task["id"]),
                "agentId": str(task["agent_id"]),
                "status": status,
                "createdAt": _utc_z(str(task["created_at"])),
                "updatedAt": _utc_z(str(task["updated_at"])),
                "phase": phase,
                "dependencies": dependency_facts,
                "wait": _task_wait(task, dependency_facts, runtime),
                "handoffs": handoffs[str(task["id"])],
                "signoff": signoff,
                "runtime": runtime,
            }
        )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "conversationId": conversation_id,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "taskCount": count,
        "tasksTruncated": count > len(tasks),
        "tasks": projected,
    }
