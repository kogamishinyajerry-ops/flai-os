"""Insert-once repository primitives for ADR-0035 Candidate Skill Packages."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Mapping

from jsonschema import validate

from ..config import CONTRACTS_DIR


_EVENT_SCHEMA_PATH = CONTRACTS_DIR / "skill_package_event.schema.json"
_event_schema_cache: dict[str, Any] | None = None


def _event_schema() -> dict[str, Any]:
    global _event_schema_cache
    if _event_schema_cache is None:
        loaded = json.loads(_EVENT_SCHEMA_PATH.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("skill package event schema must be an object")
        _event_schema_cache = loaded
    return _event_schema_cache


def _decode_package(row: sqlite3.Row) -> dict[str, Any]:
    value = dict(row)
    raw_manifest = value.pop("file_manifest_json")
    files = json.loads(raw_manifest)
    if not isinstance(files, list) or any(not isinstance(item, dict) for item in files):
        raise ValueError("file_manifest_json must decode to an array of objects")
    value["files"] = files
    return value


def _decode_event(row: sqlite3.Row) -> dict[str, Any]:
    value = dict(row)
    value.pop("id", None)
    raw_payload = value.pop("payload_json")
    payload = json.loads(raw_payload)
    if not isinstance(payload, dict):
        raise ValueError("skill package event payload must be an object")
    value["payload"] = payload
    return value


def get_by_id(conn: sqlite3.Connection, package_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM skill_packages WHERE id = ?", (package_id,)
    ).fetchone()
    return _decode_package(row) if row is not None else None


def get_owner_by_id(conn: sqlite3.Connection, package_id: str) -> str | None:
    """Read only the immutable owner without decoding untrusted JSON columns."""

    row = conn.execute(
        "SELECT owner_username FROM skill_packages WHERE id = ?", (package_id,)
    ).fetchone()
    if row is None:
        return None
    owner = row["owner_username"]
    return owner if isinstance(owner, str) else None


def get_by_candidate_digest(
    conn: sqlite3.Connection,
    candidate_digest: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM skill_packages WHERE source_candidate_digest = ?",
        (candidate_digest,),
    ).fetchone()
    return _decode_package(row) if row is not None else None


def get_owner_by_candidate_digest(
    conn: sqlite3.Connection,
    candidate_digest: str,
) -> str | None:
    """Read package owner by immutable Candidate address without JSON decode."""

    row = conn.execute(
        """
        SELECT owner_username FROM skill_packages
        WHERE source_candidate_digest = ?
        """,
        (candidate_digest,),
    ).fetchone()
    if row is None:
        return None
    owner = row["owner_username"]
    return owner if isinstance(owner, str) else None


def list_approved_for_owner(
    conn: sqlite3.Connection,
    owner_username: str,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM skill_packages
        WHERE owner_username = ? AND state = 'approved'
        ORDER BY updated_at DESC, id ASC
        """,
        (owner_username,),
    ).fetchall()
    return [_decode_package(row) for row in rows]


def list_approved_ids_for_owner(
    conn: sqlite3.Connection,
    owner_username: str,
    limit: int,
) -> list[str]:
    """List candidates without decoding manifests so callers can verify per row."""

    rows = conn.execute(
        """
        SELECT id FROM skill_packages
        WHERE owner_username = ? AND state = 'approved'
        ORDER BY updated_at DESC, id ASC
        LIMIT ?
        """,
        (owner_username, limit),
    ).fetchall()
    return [str(row["id"]) for row in rows]


def insert_package(conn: sqlite3.Connection, record: Mapping[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO skill_packages (
            id, schema_version, name, version, package_digest, state,
            source_candidate_id, source_candidate_digest,
            source_bundle_digest, source_skill_digest,
            source_acceptance_event_digest, source_task_id, source_agent_id,
            owner_username, storage_relpath, file_manifest_json,
            review_event_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
        """,
        (
            record["id"],
            record["schema_version"],
            record["name"],
            record["version"],
            record["package_digest"],
            record["state"],
            record["source_candidate_id"],
            record["source_candidate_digest"],
            record["source_bundle_digest"],
            record["source_skill_digest"],
            record["source_acceptance_event_digest"],
            record["source_task_id"],
            record["source_agent_id"],
            record["owner_username"],
            record["storage_relpath"],
            record["file_manifest_json"],
            record["created_at"],
            record["updated_at"],
        ),
    )


def append_event(
    conn: sqlite3.Connection,
    event: Mapping[str, Any],
    *,
    schema: Mapping[str, Any] | None = None,
) -> None:
    document = dict(event)
    validate(document, dict(schema) if schema is not None else _event_schema())
    conn.execute(
        """
        INSERT INTO skill_package_events (
            event_id, package_id, package_digest, event_type,
            from_state, to_state, actor_source, signer_display_name,
            signer_user_id, signer_username, signer_session_hash,
            message, payload_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            document["event_id"],
            document["package_id"],
            document["package_digest"],
            document["event_type"],
            document["from_state"],
            document["to_state"],
            document["actor_source"],
            document["signer_display_name"],
            document["signer_user_id"],
            document["signer_username"],
            document["signer_session_hash"],
            document["message"],
            json.dumps(document["payload"], ensure_ascii=False, sort_keys=True),
            document["created_at"],
        ),
    )


def get_event(conn: sqlite3.Connection, event_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM skill_package_events WHERE event_id = ?", (event_id,)
    ).fetchone()
    return _decode_event(row) if row is not None else None


def list_events(
    conn: sqlite3.Connection,
    package_id: str,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM skill_package_events
        WHERE package_id = ?
        ORDER BY id ASC
        """,
        (package_id,),
    ).fetchall()
    return [_decode_event(row) for row in rows]


def cas_decision(
    conn: sqlite3.Connection,
    *,
    package_id: str,
    expected_package_digest: str,
    event_id: str,
    state: str,
    updated_at: str,
) -> int:
    if state not in {"approved", "rejected"}:
        raise ValueError("skill package decision state must be approved or rejected")
    cursor = conn.execute(
        """
        UPDATE skill_packages
        SET state = ?, review_event_id = ?, updated_at = ?
        WHERE id = ?
          AND package_digest = ?
          AND state = 'pending_review'
          AND review_event_id IS NULL
        """,
        (
            state,
            event_id,
            updated_at,
            package_id,
            expected_package_digest,
        ),
    )
    return int(cursor.rowcount)


# Compatibility aliases for callers that use review-specific wording.
get_event_by_id = get_event
cas_review = cas_decision
