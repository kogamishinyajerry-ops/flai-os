"""Repository primitives for the P2.8 append-only ledgers."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from ..design_promotion.contracts import canonical_json_bytes


class IdempotencyConflict(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def public_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def get_idempotent_response(
    conn: sqlite3.Connection,
    *,
    operation: str,
    actor_username: str,
    request_id: str,
    request_sha256: str,
) -> tuple[int, dict[str, Any]] | None:
    row = conn.execute(
        """
        SELECT request_sha256, response_status, response_json, response_sha256
        FROM design_idempotency
        WHERE operation=? AND actor_username=? AND request_id=?
        """,
        (operation, actor_username, request_id),
    ).fetchone()
    if row is None:
        return None
    if str(row[0]) != request_sha256:
        raise IdempotencyConflict("request_id was already used with different bytes")
    raw = row[2]
    if not isinstance(raw, bytes):
        raise RuntimeError("idempotency response is not canonical bytes")
    if hashlib.sha256(raw).hexdigest() != str(row[3]):
        raise RuntimeError("idempotency response hash drifted")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("idempotency response is not an object")
    if canonical_json_bytes(value) != raw:
        raise RuntimeError("idempotency response is not canonical JSON")
    return int(row[1]), value


def insert_idempotent_response(
    conn: sqlite3.Connection,
    *,
    operation: str,
    actor_username: str,
    request_id: str,
    request_sha256: str,
    response_status: int,
    response: dict[str, Any],
    response_sha256: str,
    resource_id: str,
    created_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO design_idempotency
            (id, operation, actor_username, request_id, request_sha256,
             response_status, response_json, response_sha256, resource_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            public_id("idempotency"),
            operation,
            actor_username,
            request_id,
            request_sha256,
            response_status,
            sqlite3.Binary(canonical_json_bytes(response)),
            response_sha256,
            resource_id,
            created_at,
        ),
    )


def insert_comparison(
    conn: sqlite3.Connection,
    *,
    comparison_id: str,
    task_id: str,
    candidate_id: str,
    asset_slot: str,
    candidate_asset_file_id: str,
    candidate_asset_sha256: str,
    candidate_manifest_sha256: str,
    comparison: dict[str, Any],
    comparison_sha256: str,
    target_id: str,
    target_relative_path: str,
    target_preimage_kind: str,
    target_preimage_sha256: str | None,
    actor_username: str,
    actor_display_name: str,
    created_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO design_comparisons
            (id, task_id, candidate_id, asset_slot, candidate_asset_file_id,
             candidate_asset_sha256, candidate_manifest_sha256,
             comparison_json, comparison_sha256, target_id,
             target_relative_path, target_preimage_kind,
             target_preimage_sha256, created_by_username,
             created_by_display_name, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            comparison_id,
            task_id,
            candidate_id,
            asset_slot,
            candidate_asset_file_id,
            candidate_asset_sha256,
            candidate_manifest_sha256,
            sqlite3.Binary(canonical_json_bytes(comparison)),
            comparison_sha256,
            target_id,
            target_relative_path,
            target_preimage_kind,
            target_preimage_sha256,
            actor_username,
            actor_display_name,
            created_at,
        ),
    )


def get_comparison(conn: sqlite3.Connection, comparison_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM design_comparisons WHERE id=?", (comparison_id,)
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    raw = result.pop("comparison_json")
    if not isinstance(raw, bytes):
        raise RuntimeError("comparison evidence is not canonical bytes")
    comparison = json.loads(raw.decode("utf-8"))
    if not isinstance(comparison, dict):
        raise RuntimeError("comparison evidence is not an object")
    result["comparison"] = comparison
    return result


def get_comparisons_for_task(
    conn: sqlite3.Connection, task_id: str
) -> list[dict[str, Any]]:
    ids = conn.execute(
        "SELECT id FROM design_comparisons WHERE task_id=? ORDER BY rowid DESC",
        (task_id,),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in ids:
        comparison = get_comparison(conn, str(row[0]))
        if comparison is None:
            raise RuntimeError("comparison disappeared during one transaction")
        result.append(comparison)
    return result


def insert_selection(
    conn: sqlite3.Connection,
    *,
    selection_id: str,
    comparison_id: str,
    task_id: str,
    action: str,
    candidate_id: str | None,
    candidate_asset_sha256: str | None,
    comparison_sha256: str,
    task_decision_id: str,
    actor_username: str,
    actor_display_name: str,
    reason_code: str | None,
    comment: str | None,
    created_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO design_candidate_selections
            (id, comparison_id, task_id, action, candidate_id,
             candidate_asset_sha256, comparison_sha256, task_decision_id,
             decided_by_username, decided_by_display_name, reason_code,
             comment, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            selection_id,
            comparison_id,
            task_id,
            action,
            candidate_id,
            candidate_asset_sha256,
            comparison_sha256,
            task_decision_id,
            actor_username,
            actor_display_name,
            reason_code,
            comment,
            created_at,
        ),
    )


def get_selection(
    conn: sqlite3.Connection, *, comparison_id: str | None = None, selection_id: str | None = None
) -> dict[str, Any] | None:
    if (comparison_id is None) == (selection_id is None):
        raise ValueError("exactly one selection lookup key is required")
    if comparison_id is not None:
        row = conn.execute(
            "SELECT * FROM design_candidate_selections WHERE comparison_id=?",
            (comparison_id,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM design_candidate_selections WHERE id=?", (selection_id,)
        ).fetchone()
    return dict(row) if row is not None else None


def insert_release_request(
    conn: sqlite3.Connection,
    *,
    release_request_id: str,
    selection_id: str,
    comparison_id: str,
    candidate_asset_file_id: str,
    candidate_asset_sha256: str,
    comparison_sha256: str,
    target_id: str,
    target_relative_path: str,
    target_preimage_kind: str,
    target_preimage_sha256: str | None,
    summary: dict[str, Any],
    summary_sha256: str,
    actor_username: str,
    actor_display_name: str,
    created_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO design_release_requests
            (id, selection_id, comparison_id, candidate_asset_file_id,
             candidate_asset_sha256, comparison_sha256, target_id,
             target_relative_path, target_preimage_kind,
             target_preimage_sha256, summary_json, summary_sha256,
             requested_by_username, requested_by_display_name, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            release_request_id,
            selection_id,
            comparison_id,
            candidate_asset_file_id,
            candidate_asset_sha256,
            comparison_sha256,
            target_id,
            target_relative_path,
            target_preimage_kind,
            target_preimage_sha256,
            sqlite3.Binary(canonical_json_bytes(summary)),
            summary_sha256,
            actor_username,
            actor_display_name,
            created_at,
        ),
    )


def get_release_request(
    conn: sqlite3.Connection,
    *,
    release_request_id: str | None = None,
    selection_id: str | None = None,
) -> dict[str, Any] | None:
    if (release_request_id is None) == (selection_id is None):
        raise ValueError("exactly one release request lookup key is required")
    if release_request_id is not None:
        row = conn.execute(
            "SELECT * FROM design_release_requests WHERE id=?", (release_request_id,)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM design_release_requests WHERE selection_id=?", (selection_id,)
        ).fetchone()
    if row is None:
        return None
    result = dict(row)
    raw = result.pop("summary_json")
    if not isinstance(raw, bytes):
        raise RuntimeError("release summary is not canonical bytes")
    summary = json.loads(raw.decode("utf-8"))
    if not isinstance(summary, dict):
        raise RuntimeError("release summary is not an object")
    result["summary"] = summary
    return result


def insert_release_decision(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    release_request_id: str,
    action: str,
    summary_sha256: str,
    reason_code: str | None,
    comment: str | None,
    actor_username: str,
    actor_display_name: str,
    release_package: dict[str, Any] | None,
    release_package_sha256: str | None,
    created_at: str,
) -> None:
    stored_package = release_package
    if release_package is not None:
        stored_package = dict(release_package)
        embedded_sha = stored_package.pop("release_package_sha256", None)
        if embedded_sha != release_package_sha256:
            raise ValueError("release package embedded hash is not exact")
    conn.execute(
        """
        INSERT INTO design_release_decisions
            (id, release_request_id, action, summary_sha256, reason_code,
             comment, decided_by_username, decided_by_display_name,
             release_package_json, release_package_sha256, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            decision_id,
            release_request_id,
            action,
            summary_sha256,
            reason_code,
            comment,
            actor_username,
            actor_display_name,
            (
                sqlite3.Binary(canonical_json_bytes(stored_package))
                if stored_package is not None
                else None
            ),
            release_package_sha256,
            created_at,
        ),
    )


def get_release_decision(
    conn: sqlite3.Connection, release_request_id: str
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM design_release_decisions WHERE release_request_id=?",
        (release_request_id,),
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    raw = result.pop("release_package_json")
    if raw is None:
        result["release_package"] = None
    else:
        if not isinstance(raw, bytes):
            raise RuntimeError("release package is not canonical bytes")
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise RuntimeError("release package is not an object")
        value["release_package_sha256"] = result["release_package_sha256"]
        result["release_package"] = value
    return result


def insert_publish_event(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    attempt_id: str,
    release_request_id: str,
    release_decision_id: str,
    event_type: str,
    actor_username: str,
    actor_display_name: str,
    release_package_sha256: str,
    target_id: str,
    target_relative_path: str,
    before_kind: str,
    before_sha256: str | None,
    after_kind: str,
    after_sha256: str | None,
    backup_relative_path: str | None,
    backup_sha256: str | None,
    details: dict[str, Any],
    details_sha256: str,
    created_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO design_publish_events
            (id, attempt_id, release_request_id, release_decision_id,
             event_type, actor_username, actor_display_name,
             release_package_sha256, target_id, target_relative_path,
             before_kind, before_sha256, after_kind, after_sha256,
             backup_relative_path, backup_sha256, details_json,
             details_sha256, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            attempt_id,
            release_request_id,
            release_decision_id,
            event_type,
            actor_username,
            actor_display_name,
            release_package_sha256,
            target_id,
            target_relative_path,
            before_kind,
            before_sha256,
            after_kind,
            after_sha256,
            backup_relative_path,
            backup_sha256,
            sqlite3.Binary(canonical_json_bytes(details)),
            details_sha256,
            created_at,
        ),
    )


def get_publish_events(
    conn: sqlite3.Connection, release_request_id: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM design_publish_events
        WHERE release_request_id=? ORDER BY rowid ASC
        """,
        (release_request_id,),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        raw = item.pop("details_json")
        if not isinstance(raw, bytes):
            raise RuntimeError("publish event details are not canonical bytes")
        details = json.loads(raw.decode("utf-8"))
        if not isinstance(details, dict):
            raise RuntimeError("publish event details are not an object")
        item["details"] = details
        result.append(item)
    return result
