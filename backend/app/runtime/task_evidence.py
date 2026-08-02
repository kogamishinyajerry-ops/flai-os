"""Canonical, content-addressed execution evidence shared by runtime and ontology."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from typing import Any

from ..storage import repos


def input_files_evidence(
    conn: sqlite3.Connection, file_ids: list[str]
) -> dict[str, Any]:
    """Snapshot ordered input-file identities and immutable provenance fields."""

    files: list[dict[str, Any]] = []
    for file_id in file_ids:
        record = repos.get_file(conn, file_id)
        if record is None:
            files.append({"file_id": file_id, "missing": True})
            continue
        files.append(
            {
                "file_id": file_id,
                "missing": False,
                "task_id": record.get("task_id"),
                "kind": record.get("kind"),
                "sha256": record.get("sha256"),
                "size_bytes": record.get("size_bytes"),
                "classification": record.get("classification"),
            }
        )
    basis = {"file_ids": list(file_ids), "files": files}
    return {**basis, "digest": _digest(basis)}


def _digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"
