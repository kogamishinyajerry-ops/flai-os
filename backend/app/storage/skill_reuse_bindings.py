"""Insert-once task bindings for governed Skill Package reuse."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any


def insert_binding(conn: sqlite3.Connection, record: Mapping[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO skill_reuse_bindings (
            id, schema_version, task_id, conversation_id,
            package_id, package_digest, source_candidate_digest,
            source_skill_digest, matched_agent_id, owner_username,
            match_policy_version, match_basis_digest, binding_digest, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record["id"],
            record["schema_version"],
            record["task_id"],
            record["conversation_id"],
            record["package_id"],
            record["package_digest"],
            record["source_candidate_digest"],
            record["source_skill_digest"],
            record["matched_agent_id"],
            record["owner_username"],
            record["match_policy_version"],
            record["match_basis_digest"],
            record["binding_digest"],
            record["created_at"],
        ),
    )


def get_by_task(conn: sqlite3.Connection, task_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM skill_reuse_bindings WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def list_for_package(
    conn: sqlite3.Connection,
    *,
    package_id: str,
    owner_username: str,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM skill_reuse_bindings
        WHERE package_id = ? AND owner_username = ?
        ORDER BY created_at ASC, id ASC
        """,
        (package_id, owner_username),
    ).fetchall()
    return [dict(row) for row in rows]
