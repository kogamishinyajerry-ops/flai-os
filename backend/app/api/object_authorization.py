"""Exact-owner authorization helpers for user-owned API resources.

The authenticated username is the only authority axis.  Display names are not
stable identifiers, and legacy rows with a NULL owner are deliberately not
guessed.  Missing, legacy, and cross-owner resources all collapse to the same
404 response so callers cannot use status/detail differences as an object
existence oracle.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NoReturn

from fastapi import HTTPException, Request

from ..storage import asset_candidates as candidate_store
from ..storage import repos
from ..storage import skill_packages as skill_package_store
from ..storage import task_owner_lineage

RESOURCE_NOT_FOUND_DETAIL = "资源不存在或不可访问"

_MAX_TASK_OUTPUT_FILE_IDS = task_owner_lineage.MAX_TASK_OUTPUT_FILE_IDS
_MAX_LINEAGE_CONVERSATION_MESSAGES = repos.CONVERSATION_LINEAGE_MAX_MESSAGES
_MAX_LINEAGE_FILE_IDS = repos.CONVERSATION_LINEAGE_MAX_FILE_IDS


def raise_resource_not_found() -> NoReturn:
    raise HTTPException(status_code=404, detail=RESOURCE_NOT_FOUND_DETAIL)


def _canonical_username(value: object) -> str | None:
    if (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
    ):
        return value
    return None


def _canonical_resource_id(value: object, *, max_length: int = 64) -> str | None:
    if (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and len(value) <= max_length
    ):
        return value
    return None


def _load_task(conn: Any, task_id: str) -> dict[str, Any]:
    try:
        task = repos.get_task(conn, task_id)
    except (TypeError, ValueError):
        raise_resource_not_found()
    if not isinstance(task, dict):
        raise_resource_not_found()
    return task


def _canonical_id_list(
    value: object,
    *,
    max_items: int,
    max_id_length: int = 64,
) -> list[str]:
    if not isinstance(value, list) or len(value) > max_items:
        raise_resource_not_found()
    result: list[str] = []
    seen: set[str] = set()
    for raw_id in value:
        resource_id = _canonical_resource_id(raw_id, max_length=max_id_length)
        if resource_id is None or resource_id in seen:
            raise_resource_not_found()
        seen.add(resource_id)
        result.append(resource_id)
    return result


def _task_output_file_ids(task: Mapping[str, Any]) -> list[str]:
    return _canonical_id_list(
        task.get("output_file_ids"),
        max_items=_MAX_TASK_OUTPUT_FILE_IDS,
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
        raise_resource_not_found()


def _require_task_output_relations(
    conn: Any,
    task: Mapping[str, Any],
) -> list[str]:
    output_file_ids = _task_output_file_ids(task)
    for file_id in output_file_ids:
        record = repos.get_file(conn, file_id)
        if not isinstance(record, Mapping):
            raise_resource_not_found()
        _require_output_file_relation(record, task)
    return output_file_ids


def authenticated_username(request: Request) -> str:
    """Read the principal only from the verified server-side session context."""
    user = getattr(request.state, "user", None)
    username = user.get("username") if isinstance(user, Mapping) else None
    principal = _canonical_username(username)
    if principal is None:
        # The default-deny middleware normally makes this unreachable.  Keep the
        # resource seam fail-closed if a test/mis-mounted route bypasses it.
        raise_resource_not_found()
    return principal


def require_exact_owner(
    owner_username: object,
    authenticated_username: object,
) -> None:
    try:
        task_owner_lineage.require_exact_owner(
            owner_username,
            authenticated_username,
        )
    except task_owner_lineage.TaskOwnerLineageViolation:
        raise_resource_not_found()


def require_owned_task(
    conn: Any,
    task_id: str,
    username: object,
) -> dict[str, Any]:
    try:
        return task_owner_lineage.require_owned_user_task(
            conn,
            task_id,
            username,
        )
    except task_owner_lineage.TaskOwnerLineageViolation:
        raise_resource_not_found()


def require_readable_task(
    conn: Any,
    task_id: str,
    username: object,
) -> dict[str, Any]:
    """Read policy: tenant-wide eval evidence, exact-owner user work."""
    principal = _canonical_username(username)
    if principal is None:
        raise_resource_not_found()
    canonical_task_id = _canonical_resource_id(task_id)
    if canonical_task_id is None:
        raise_resource_not_found()
    task = _load_task(conn, canonical_task_id)
    origin = task.get("origin")
    if origin == "eval":
        _require_task_output_relations(conn, task)
        return task
    if origin != "user":
        raise_resource_not_found()
    try:
        return task_owner_lineage.require_owned_user_task(
            conn,
            canonical_task_id,
            principal,
        )
    except task_owner_lineage.TaskOwnerLineageViolation:
        raise_resource_not_found()


def require_prospective_user_task_lineage(
    conn: Any,
    tasks: list[Mapping[str, Any]],
    username: object,
) -> None:
    """Validate virtual user-task roots before their rows are written.

    The virtual rows use the same fields and traversal state as persisted task
    reads.  This makes the depth/node/file/conversation bounds include the new
    root and any batch-local ``depends_on`` edges, preventing a successful
    create from producing a task that immediately fails its own read gate.
    """
    try:
        task_owner_lineage.require_prospective_user_task_lineage(
            conn,
            tasks,
            username,
        )
    except task_owner_lineage.TaskOwnerLineageViolation:
        raise_resource_not_found()


def list_readable_tasks(
    conn: Any,
    *,
    username: object,
    agent_id: str | None,
    status: str | None,
    conversation_id: str | None,
    origin: str,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    """Apply task visibility in SQL before ORDER/LIMIT/OFFSET.

    Eval tasks are tenant-wide read-only governance evidence.  User tasks remain
    private to their exact immutable creator username.  ``origin=all`` is the
    SQL union of those cohorts, so another user's newer rows cannot distort the
    current user's pagination window.
    """
    principal = _canonical_username(username)
    if principal is None:
        raise_resource_not_found()

    try:
        rows = repos.list_tasks(
            conn,
            agent_id=agent_id,
            status=status,
            conversation_id=conversation_id,
            origin=None if origin == "all" else origin,
            visible_to_username=principal,
            limit=limit,
            offset=offset,
        )
    except (TypeError, ValueError):
        raise_resource_not_found()
    for task in rows:
        if task.get("origin") == "eval":
            _require_task_output_relations(conn, task)
            continue
        if task.get("origin") != "user":
            raise_resource_not_found()
        try:
            task_owner_lineage.require_owned_user_task(
                conn,
                task["id"],
                principal,
            )
        except task_owner_lineage.TaskOwnerLineageViolation:
            raise_resource_not_found()
    return rows


def require_owned_conversation(
    conn: Any,
    conversation_id: str,
    username: object,
) -> dict[str, Any]:
    canonical_conversation_id = _canonical_resource_id(
        conversation_id,
        max_length=100,
    )
    if canonical_conversation_id is None:
        raise_resource_not_found()
    owner_username = repos.get_conversation_owner_username(
        conn,
        canonical_conversation_id,
    )
    require_exact_owner(owner_username, username)
    try:
        conversation = repos.get_conversation(conn, canonical_conversation_id)
    except (TypeError, ValueError):
        raise_resource_not_found()
    if conversation is None:
        raise_resource_not_found()
    return conversation


def require_owned_conversation_inputs(
    conn: Any,
    conversation_id: str,
    username: object,
) -> dict[str, Any]:
    """Authorize a conversation and every direct input it has ever referenced.

    Asset derivation reads the complete conversation lineage, so checking only
    the latest request attachments would reopen older cross-owner inputs.  A
    malformed persisted ``file_ids`` projection is an integrity failure and is
    therefore indistinguishable from any other inaccessible resource.
    """
    conversation, _, _ = _require_owned_conversation_inputs_bounded(
        conn,
        conversation_id,
        username,
        max_messages=_MAX_LINEAGE_CONVERSATION_MESSAGES,
        max_file_ids=_MAX_LINEAGE_FILE_IDS,
    )
    return conversation


def require_owned_conversation_append_inputs(
    conn: Any,
    conversation_id: str,
    username: object,
    *,
    additional_messages: int,
    additional_file_ids: int,
) -> dict[str, Any]:
    """Authorize complete lineage while reserving one atomic round's delta."""

    if (
        type(additional_messages) is not int
        or type(additional_file_ids) is not int
        or additional_messages < 0
        or additional_file_ids < 0
        or additional_messages > _MAX_LINEAGE_CONVERSATION_MESSAGES
        or additional_file_ids > _MAX_LINEAGE_FILE_IDS
    ):
        raise_resource_not_found()
    conversation, _, _ = _require_owned_conversation_inputs_bounded(
        conn,
        conversation_id,
        username,
        max_messages=(
            _MAX_LINEAGE_CONVERSATION_MESSAGES - additional_messages
        ),
        max_file_ids=_MAX_LINEAGE_FILE_IDS - additional_file_ids,
    )
    return conversation


def _require_owned_conversation_inputs_bounded(
    conn: Any,
    conversation_id: str,
    username: object,
    *,
    max_messages: int,
    max_file_ids: int,
) -> tuple[dict[str, Any], int, int]:
    conversation = require_owned_conversation(conn, conversation_id, username)
    try:
        message_count, file_ids = (
            repos.get_bounded_conversation_attachment_lineage(
                conn,
                conversation_id,
                max_messages=max_messages,
                max_file_ids=max_file_ids,
            )
        )
    except (TypeError, ValueError):
        raise_resource_not_found()
    for file_id in file_ids:
        if _canonical_resource_id(file_id) is None:
            raise_resource_not_found()
        require_owned_input_file(conn, file_id, username)
    return conversation, message_count, len(file_ids)


def require_owned_input_file(
    conn: Any,
    file_id: str,
    username: object,
) -> dict[str, Any]:
    canonical_file_id = _canonical_resource_id(file_id)
    if canonical_file_id is None:
        raise_resource_not_found()
    record = repos.get_file(conn, canonical_file_id)
    if record is None or record.get("kind") != "input":
        raise_resource_not_found()
    require_exact_owner(record.get("owner_username"), username)
    return record


def require_owned_file(
    conn: Any,
    file_id: str,
    username: object,
) -> dict[str, Any]:
    """Authorize uploaded inputs directly and task outputs through their task owner."""
    canonical_file_id = _canonical_resource_id(file_id)
    if canonical_file_id is None:
        raise_resource_not_found()
    record = repos.get_file(conn, canonical_file_id)
    if not isinstance(record, dict):
        raise_resource_not_found()
    if record.get("kind") == "input":
        require_exact_owner(record.get("owner_username"), username)
        return record
    if record.get("kind") == "output":
        task_id = _canonical_resource_id(record.get("task_id"))
        if task_id is None:
            raise_resource_not_found()
        task = require_owned_task(conn, task_id, username)
        _require_output_file_relation(record, task)
        return record
    raise_resource_not_found()


def require_owned_task_conversation_inputs(
    conn: Any,
    task_id: str,
    username: object,
) -> dict[str, Any]:
    """Authorize a task and any conversation lineage it can later project.

    A task without a conversation remains an owner-visible invalid candidate;
    the domain layer retains its existing 409 admission semantics.  Once a
    conversation id exists, malformed, legacy-unowned, foreign, or tainted
    lineage is inaccessible.
    """

    return require_owned_task(conn, task_id, username)


def require_owned_asset_candidate_inputs(
    conn: Any,
    candidate_id: str,
    username: object,
) -> dict[str, Any]:
    """Authorize immutable Candidate owner, task, and conversation lineage."""

    try:
        context = candidate_store.get_owner_context_by_id(conn, candidate_id)
    except (TypeError, ValueError):
        raise_resource_not_found()
    if not isinstance(context, Mapping):
        raise_resource_not_found()
    require_exact_owner(context.get("initiated_by_username"), username)

    source_task_id = context.get("source_task_id")
    if (
        not isinstance(source_task_id, str)
        or not source_task_id
        or source_task_id != source_task_id.strip()
    ):
        raise_resource_not_found()
    task = require_owned_task_conversation_inputs(conn, source_task_id, username)

    source_conversation_id = context.get("source_conversation_id")
    if (
        not isinstance(source_conversation_id, str)
        or not source_conversation_id
        or source_conversation_id != source_conversation_id.strip()
    ):
        raise_resource_not_found()
    task_conversation_id = task.get("conversation_id")
    if task_conversation_id != source_conversation_id:
        # Candidate/task lineage drift is not an ownership oracle.  The owner
        # can form a fresh revision only after the source is made coherent.
        raise_resource_not_found()
    return dict(context)


def require_owned_asset_candidate_package_inputs(
    conn: Any,
    candidate_id: str,
    username: object,
) -> dict[str, Any]:
    """Authorize Candidate lineage and any materialized package source relation."""

    context = require_owned_asset_candidate_inputs(
        conn, candidate_id, username
    )
    candidate_digest = context.get("candidate_digest")
    if (
        not isinstance(candidate_digest, str)
        or len(candidate_digest) != 71
        or not candidate_digest.startswith("sha256:")
        or any(char not in "0123456789abcdef" for char in candidate_digest[7:])
    ):
        raise_resource_not_found()
    try:
        package_context = (
            skill_package_store.get_owner_context_by_candidate_digest(
                conn, candidate_digest
            )
        )
    except (TypeError, ValueError):
        raise_resource_not_found()
    if package_context is None:
        return context
    if not isinstance(package_context, Mapping):
        raise_resource_not_found()
    require_exact_owner(package_context.get("owner_username"), username)
    if (
        _canonical_resource_id(package_context.get("id")) is None
        or package_context.get("source_candidate_id") != candidate_id
        or package_context.get("source_candidate_digest") != candidate_digest
        or package_context.get("source_task_id") != context.get("source_task_id")
    ):
        raise_resource_not_found()
    return context


def require_owned_skill_package_inputs(
    conn: Any,
    package_id: str,
    username: object,
) -> dict[str, Any]:
    """Authorize Package -> Candidate -> task -> conversation/file lineage."""

    principal = _canonical_username(username)
    canonical_package_id = _canonical_resource_id(package_id)
    if principal is None or canonical_package_id is None:
        raise_resource_not_found()
    try:
        package_context = skill_package_store.get_owner_context_by_id(
            conn,
            canonical_package_id,
        )
    except (TypeError, ValueError):
        raise_resource_not_found()
    if not isinstance(package_context, Mapping):
        raise_resource_not_found()
    require_exact_owner(package_context.get("owner_username"), principal)

    candidate_id = _canonical_resource_id(
        package_context.get("source_candidate_id")
    )
    if candidate_id is None:
        raise_resource_not_found()
    candidate_context = require_owned_asset_candidate_package_inputs(
        conn,
        candidate_id,
        principal,
    )
    try:
        package_by_candidate = (
            skill_package_store.get_owner_context_by_candidate_digest(
                conn,
                candidate_context.get("candidate_digest"),
            )
        )
    except (TypeError, ValueError):
        raise_resource_not_found()
    if (
        not isinstance(package_by_candidate, Mapping)
        or dict(package_by_candidate) != dict(package_context)
        or package_context.get("id") != canonical_package_id
        or package_context.get("source_candidate_digest")
        != candidate_context.get("candidate_digest")
        or package_context.get("source_task_id")
        != candidate_context.get("source_task_id")
    ):
        raise_resource_not_found()
    return dict(package_context)


def require_readable_file(
    conn: Any,
    file_id: str,
    username: object,
) -> dict[str, Any]:
    """Read policy mirrors task cohorts for outputs; inputs remain exact-owner."""
    canonical_file_id = _canonical_resource_id(file_id)
    if canonical_file_id is None:
        raise_resource_not_found()
    record = repos.get_file(conn, canonical_file_id)
    if not isinstance(record, dict):
        raise_resource_not_found()
    if record.get("kind") == "input":
        require_exact_owner(record.get("owner_username"), username)
        return record
    if record.get("kind") == "output":
        task_id = _canonical_resource_id(record.get("task_id"))
        if task_id is None:
            raise_resource_not_found()
        task = require_readable_task(conn, task_id, username)
        _require_output_file_relation(record, task)
        return record
    raise_resource_not_found()
