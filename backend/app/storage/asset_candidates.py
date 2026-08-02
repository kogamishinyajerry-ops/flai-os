"""Append-only repository primitives for ADR-0034 Asset Candidates."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Mapping

from jsonschema import validate

from ..config import CONTRACTS_DIR


_EVENT_SCHEMA_PATH = CONTRACTS_DIR / "asset_candidate_event.schema.json"
_event_schema_cache: dict[str, Any] | None = None


def _event_schema() -> dict[str, Any]:
    global _event_schema_cache
    if _event_schema_cache is None:
        loaded = json.loads(_EVENT_SCHEMA_PATH.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("asset candidate event schema must be an object")
        _event_schema_cache = loaded
    return _event_schema_cache


def _decode_candidate(row: sqlite3.Row) -> dict[str, Any]:
    value = dict(row)
    for stored, public in (
        ("bundle_json", "bundle"),
        ("lineage_json", "lineage"),
        ("proposal_provenance_json", "proposal_provenance"),
    ):
        raw = value.pop(stored)
        decoded = json.loads(raw)
        if not isinstance(decoded, dict):
            raise ValueError(f"{stored} must decode to an object")
        value[public] = decoded
    return value


def _decode_event(row: sqlite3.Row) -> dict[str, Any]:
    value = dict(row)
    value.pop("id", None)
    raw_payload = value.pop("payload_json")
    payload = json.loads(raw_payload)
    if not isinstance(payload, dict):
        raise ValueError("asset candidate event payload must be an object")
    value["payload"] = payload
    return value


def get_by_id(conn: sqlite3.Connection, candidate_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM asset_candidates WHERE id = ?", (candidate_id,)
    ).fetchone()
    return _decode_candidate(row) if row is not None else None


def get_by_task(conn: sqlite3.Connection, task_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT * FROM asset_candidates
        WHERE source_task_id = ?
        ORDER BY revision DESC
        LIMIT 1
        """,
        (task_id,),
    ).fetchone()
    return _decode_candidate(row) if row is not None else None


def get_latest_id_for_task(conn: sqlite3.Connection, task_id: str) -> str | None:
    """Read the latest revision identity without decoding candidate JSON."""

    row = conn.execute(
        """
        SELECT id FROM asset_candidates
        WHERE source_task_id = ?
        ORDER BY revision DESC
        LIMIT 1
        """,
        (task_id,),
    ).fetchone()
    return str(row["id"]) if row is not None else None


def list_latest_task_ids_for_owner(
    conn: sqlite3.Connection,
    owner_username: str,
    limit: int,
) -> list[str]:
    """List owner-attributed tasks with a latest Candidate, without JSON decode.

    Ownership comes from the immutable task row.  The caller must cold-verify
    each Candidate so a drifted Candidate owner cannot be silently filtered
    into a false empty projection.
    """

    rows = conn.execute(
        """
        SELECT candidate.source_task_id
        FROM asset_candidates AS candidate
        LEFT JOIN tasks AS task ON task.id = candidate.source_task_id
        WHERE (
            task.created_by_username = ?
            OR candidate.initiated_by_username = ?
        )
          AND NOT EXISTS (
            SELECT 1
            FROM asset_candidates AS newer
            WHERE newer.source_task_id = candidate.source_task_id
              AND newer.revision > candidate.revision
          )
        ORDER BY candidate.updated_at DESC, candidate.id ASC
        LIMIT ?
        """,
        (owner_username, owner_username, limit),
    ).fetchall()
    return [str(row["source_task_id"]) for row in rows]


def get_event(conn: sqlite3.Connection, event_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM asset_candidate_events WHERE event_id = ?", (event_id,)
    ).fetchone()
    return _decode_event(row) if row is not None else None


def list_accepted_without_package_ids(conn: sqlite3.Connection) -> list[str]:
    """Return deterministic ADR-0034 legacy rows needing ADR-0035 materialization."""

    rows = conn.execute(
        """
        SELECT candidate.id
        FROM asset_candidates AS candidate
        LEFT JOIN skill_packages AS package
          ON package.source_candidate_digest = candidate.candidate_digest
        WHERE candidate.state = 'accepted'
          AND candidate.decision_event_id IS NOT NULL
          AND package.id IS NULL
          AND NOT EXISTS (
            SELECT 1
            FROM asset_candidates AS newer
            WHERE newer.source_task_id = candidate.source_task_id
              AND newer.revision > candidate.revision
          )
        ORDER BY candidate.created_at ASC, candidate.id ASC
        """
    ).fetchall()
    return [str(row["id"]) for row in rows]


def insert_candidate(conn: sqlite3.Connection, record: Mapping[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO asset_candidates (
            id, schema_version, source_task_id, source_conversation_id,
            revision, supersedes_candidate_digest,
            bundle_digest, lineage_digest, candidate_digest,
            bundle_json, lineage_json, proposal_provenance_json,
            state, data_classification, initiated_by_user_id,
            initiated_by_username, decision_event_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
        """,
        (
            record["id"],
            record["schema_version"],
            record["source_task_id"],
            record["source_conversation_id"],
            record["revision"],
            record["supersedes_candidate_digest"],
            record["bundle_digest"],
            record["lineage_digest"],
            record["candidate_digest"],
            record["bundle_json"],
            record["lineage_json"],
            record["proposal_provenance_json"],
            record["state"],
            record["data_classification"],
            record["initiated_by_user_id"],
            record["initiated_by_username"],
            record["created_at"],
            record["updated_at"],
        ),
    )


def append_event(conn: sqlite3.Connection, event: Mapping[str, Any]) -> None:
    document = dict(event)
    validate(document, _event_schema())
    conn.execute(
        """
        INSERT INTO asset_candidate_events (
            event_id, candidate_id, candidate_digest, bundle_digest,
            event_type, from_state, to_state, actor_source,
            signer_display_name, signer_user_id, signer_username,
            signer_session_hash, message, payload_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            document["event_id"],
            document["candidate_id"],
            document["candidate_digest"],
            document["bundle_digest"],
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


def cas_decision(
    conn: sqlite3.Connection,
    *,
    candidate_id: str,
    expected_candidate_digest: str,
    event_id: str,
    state: str,
    updated_at: str,
) -> int:
    cursor = conn.execute(
        """
        UPDATE asset_candidates
        SET state = ?, decision_event_id = ?, updated_at = ?
        WHERE id = ?
          AND candidate_digest = ?
          AND state = 'awaiting_human_review'
          AND decision_event_id IS NULL
        """,
        (
            state,
            event_id,
            updated_at,
            candidate_id,
            expected_candidate_digest,
        ),
    )
    return int(cursor.rowcount)


def cas_supersede(
    conn: sqlite3.Connection,
    *,
    candidate_id: str,
    expected_candidate_digest: str,
    event_id: str,
    updated_at: str,
) -> int:
    """Terminally retire an undecided revision before inserting its successor."""

    cursor = conn.execute(
        """
        UPDATE asset_candidates
        SET state = 'superseded', decision_event_id = ?, updated_at = ?
        WHERE id = ?
          AND candidate_digest = ?
          AND state = 'awaiting_human_review'
          AND decision_event_id IS NULL
        """,
        (event_id, updated_at, candidate_id, expected_candidate_digest),
    )
    return int(cursor.rowcount)
