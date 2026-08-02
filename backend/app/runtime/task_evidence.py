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


def work_case_fingerprint(
    *,
    task_inputs: Mapping[str, Any],
    input_file_evidence: Mapping[str, Any],
    agent_id: str,
    package_id: str,
    package_digest: str,
) -> str:
    """Return a content-stable, conservative Work Case de-duplication key.

    File-store ids, filenames, upload paths and task ids intentionally do not
    participate.  Re-uploading the same bytes (or omitting ``retry_of``) must
    therefore not manufacture another independent case.  Stable file metadata
    is sorted so attachment reordering is conservative too.
    """

    raw_files = input_file_evidence.get("files")
    if not isinstance(raw_files, list):
        raise ValueError("input file evidence is malformed")
    stable_files_by_content: dict[str, dict[str, Any]] = {}
    for raw in raw_files:
        if not isinstance(raw, Mapping) or raw.get("missing") is not False:
            raise ValueError("input file evidence contains a missing file")
        stable = {
            "sha256": raw.get("sha256"),
            "size_bytes": raw.get("size_bytes"),
            "kind": raw.get("kind"),
            "classification": raw.get("classification"),
        }
        stable_key = json.dumps(
            stable,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        stable_files_by_content[stable_key] = stable
    stable_files = [
        stable_files_by_content[key] for key in sorted(stable_files_by_content)
    ]
    return _digest(
        {
            "schema_version": "work_case_fingerprint.v1",
            "task_inputs": dict(task_inputs),
            "input_files": stable_files,
            "agent_id": agent_id,
            "skill_package_id": package_id,
            "skill_package_digest": package_digest,
        }
    )


def _digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"
