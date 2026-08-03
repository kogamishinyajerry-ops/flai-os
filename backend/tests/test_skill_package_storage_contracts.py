from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError, validate

from backend.app.storage import db as db_mod


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "contracts"


def _schema(name: str) -> dict[str, Any]:
    return json.loads((CONTRACTS_DIR / name).read_text(encoding="utf-8"))


def _package() -> dict[str, Any]:
    return {
        "schema_version": "skill_package_revision.v1",
        "id": f"skill_package_{'1' * 24}",
        "name": "review-completed-work",
        "version": "0.1.0",
        "package_digest": f"sha256:{'2' * 64}",
        "state": "pending_review",
        "source": {
            "candidate_id": f"asset_candidate_{'3' * 24}",
            "candidate_digest": f"sha256:{'4' * 64}",
            "bundle_digest": f"sha256:{'5' * 64}",
            "skill_digest": f"sha256:{'6' * 64}",
            "acceptance_event_digest": f"sha256:{'7' * 64}",
            "task_id": "task_source",
            "agent_id": "report_agent",
            "initiated_by_username": "test.engineer",
        },
        "files": [
            {
                "path": "SKILL.md",
                "sha256": "8" * 64,
                "size_bytes": 128,
            },
            {
                "path": "references/provenance.json",
                "sha256": "9" * 64,
                "size_bytes": 256,
            },
            {
                "path": "references/skill-revision.json",
                "sha256": "a" * 64,
                "size_bytes": 384,
            },
            {
                "path": "references/task-pattern-revision.json",
                "sha256": "b" * 64,
                "size_bytes": 512,
            },
        ],
        "storage_relpath": f"quarantine/skill_package_{'1' * 24}",
        "review": None,
        "reuse_eligible": False,
        "isolation": {
            "zone": "candidate_quarantine",
            "registered": False,
            "executable": False,
        },
        "formation_evidence": {
            "schema_version": "composition_eligibility.v1",
            "independent_work_case_count": 0,
            "required_independent_work_cases": 2,
            "workflow_candidate": {
                "state": "not_formed",
                "eligible": False,
                "reason": "requires_independent_composition_evidence",
            },
            "agent_candidate": {
                "state": "not_formed",
                "eligible": False,
                "reason": "requires_approved_workflow_revision",
            },
        },
        "created_at": "2026-08-02T12:00:00Z",
        "updated_at": "2026-08-02T12:00:00Z",
    }


def _event(event_type: str) -> dict[str, Any]:
    event: dict[str, Any] = {
        "event_id": f"skill_package_event_{'9' * 32}",
        "package_id": f"skill_package_{'1' * 24}",
        "package_digest": f"sha256:{'2' * 64}",
        "event_type": event_type,
        "from_state": "pending_review",
        "to_state": "approved",
        "actor_source": "authenticated_session",
        "signer_display_name": "Test Engineer",
        "signer_user_id": 7,
        "signer_username": "test.engineer",
        "signer_session_hash": "a" * 64,
        "message": "Exact package revision approved.",
        "payload": {},
        "created_at": "2026-08-02T12:05:00Z",
    }
    if event_type == "materialized":
        event.update(
            {
                "from_state": None,
                "to_state": "pending_review",
                "actor_source": "candidate_materializer",
                "signer_display_name": None,
                "signer_user_id": None,
                "signer_username": None,
                "signer_session_hash": None,
                "message": "Accepted Candidate deterministically materialized.",
                "payload": {
                    "source_candidate_digest": f"sha256:{'4' * 64}",
                    "source_acceptance_event_digest": f"sha256:{'7' * 64}",
                },
            }
        )
    elif event_type == "rejected":
        event.update(
            {
                "to_state": "rejected",
                "message": "Exact package revision rejected.",
            }
        )
    return event


def test_candidate_skill_package_schema_accepts_pending_review_revision() -> None:
    schema = _schema("candidate_skill_package.schema.json")
    Draft202012Validator.check_schema(schema)
    validate(_package(), schema)


def test_candidate_skill_package_schema_locks_review_and_higher_asset_gates() -> None:
    schema = _schema("candidate_skill_package.schema.json")

    for field, invalid in (
        ("review", {"action": "approve"}),
        ("reuse_eligible", True),
    ):
        package = _package()
        package[field] = invalid
        with pytest.raises(ValidationError):
            validate(package, schema)

    for candidate_kind in ("workflow_candidate", "agent_candidate"):
        package = _package()
        package["formation_evidence"][candidate_kind]["state"] = "formed"
        package["formation_evidence"][candidate_kind]["eligible"] = True
        with pytest.raises(ValidationError):
            validate(package, schema)


def test_candidate_skill_package_schema_locks_exact_manifest_and_quarantine_path() -> (
    None
):
    schema = _schema("candidate_skill_package.schema.json")

    missing_file = _package()
    missing_file["files"] = missing_file["files"][:-1]
    with pytest.raises(ValidationError):
        validate(missing_file, schema)

    reordered = _package()
    reordered["files"][0], reordered["files"][1] = (
        reordered["files"][1],
        reordered["files"][0],
    )
    with pytest.raises(ValidationError):
        validate(reordered, schema)

    executable_path = _package()
    executable_path["storage_relpath"] = "agents/production_agent"
    with pytest.raises(ValidationError):
        validate(executable_path, schema)


def test_embedded_asset_candidate_package_contract_stays_in_strict_parity() -> None:
    standalone = Draft202012Validator(_schema("candidate_skill_package.schema.json"))
    asset_schema = _schema("asset_candidate.schema.json")
    embedded = Draft202012Validator(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$ref": "#/$defs/skillPackage",
            "$defs": asset_schema["$defs"],
        }
    )

    cases: list[tuple[dict[str, Any], bool]] = [(_package(), True)]
    missing_file = _package()
    missing_file["files"] = missing_file["files"][:-1]
    cases.append((missing_file, False))
    reordered = _package()
    reordered["files"] = list(reversed(reordered["files"]))
    cases.append((reordered, False))
    executable_path = _package()
    executable_path["storage_relpath"] = "agents/production_agent"
    cases.append((executable_path, False))
    false_green = _package()
    false_green["state"] = "approved"
    false_green["reuse_eligible"] = True
    cases.append((false_green, False))

    for package, expected in cases:
        assert standalone.is_valid(package) is expected
        assert embedded.is_valid(package) is expected


@pytest.mark.parametrize("event_type", ["materialized", "approved", "rejected"])
def test_skill_package_event_schema_accepts_only_canonical_authority(
    event_type: str,
) -> None:
    schema = _schema("skill_package_event.schema.json")
    Draft202012Validator.check_schema(schema)
    validate(_event(event_type), schema)


@pytest.mark.parametrize(
    ("event_type", "field", "invalid_value"),
    [
        ("materialized", "actor_source", "authenticated_session"),
        ("materialized", "signer_username", "test.engineer"),
        ("approved", "actor_source", "candidate_materializer"),
        ("approved", "signer_session_hash", None),
        ("rejected", "to_state", "approved"),
    ],
)
def test_skill_package_event_schema_rejects_authority_or_state_drift(
    event_type: str,
    field: str,
    invalid_value: Any,
) -> None:
    event = _event(event_type)
    event[field] = invalid_value
    with pytest.raises(ValidationError):
        validate(event, _schema("skill_package_event.schema.json"))


def test_skill_package_decision_request_contains_no_client_authority_fields() -> None:
    schema = _schema("skill_package_decision_request.schema.json")
    Draft202012Validator.check_schema(schema)
    request = {
        "schema_version": "skill_package_decision_request.v1",
        "action": "approve",
        "expected_package_digest": f"sha256:{'2' * 64}",
    }
    validate(request, schema)

    request["reviewed_by_username"] = "client.claimed.identity"
    with pytest.raises(ValidationError):
        validate(request, schema)


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "skill_packages.db"
    db_mod.init_db(db_path)
    value = db_mod.get_conn(db_path)
    yield value
    value.close()


def _seed_candidate(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO conversations (
            id, agent_id, status, created_by, recommendation_json,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, NULL, ?, ?)
        """,
        (
            "conv_source",
            "guide_agent",
            "active",
            "Test Engineer",
            "2026-08-02T11:00:00Z",
            "2026-08-02T11:00:00Z",
        ),
    )
    conn.execute(
        """
        INSERT INTO tasks (
            id, agent_id, agent_version, name, status, created_by,
            created_at, updated_at, input_file_ids, output_file_ids,
            inputs_json, metadata_json, conversation_id, origin,
            data_classification, created_by_username
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '[]', '[]', '{}', '{}', ?, ?, ?, ?)
        """,
        (
            "task_source",
            "report_agent",
            "0.1.0",
            "Source task",
            "completed",
            "Test Engineer",
            "2026-08-02T11:00:00Z",
            "2026-08-02T11:30:00Z",
            "conv_source",
            "user",
            "internal",
            "test.engineer",
        ),
    )
    conn.execute(
        """
        INSERT INTO asset_candidates (
            id, schema_version, source_task_id, source_conversation_id,
            revision, supersedes_candidate_digest, bundle_digest,
            lineage_digest, candidate_digest, bundle_json, lineage_json,
            proposal_provenance_json, state, data_classification,
            initiated_by_user_id, initiated_by_username, decision_event_id,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, '{}', '{}', '{}', ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"asset_candidate_{'3' * 24}",
            "asset_candidate.v1",
            "task_source",
            "conv_source",
            1,
            f"sha256:{'5' * 64}",
            f"sha256:{'b' * 64}",
            f"sha256:{'4' * 64}",
            "accepted",
            "internal",
            7,
            "test.engineer",
            f"asset_candidate_event_{'c' * 32}",
            "2026-08-02T11:35:00Z",
            "2026-08-02T11:40:00Z",
        ),
    )


def _package_record() -> dict[str, Any]:
    package = _package()
    source = package["source"]
    return {
        "id": package["id"],
        "schema_version": package["schema_version"],
        "name": package["name"],
        "version": package["version"],
        "package_digest": package["package_digest"],
        "state": package["state"],
        "source_candidate_id": source["candidate_id"],
        "source_candidate_digest": source["candidate_digest"],
        "source_bundle_digest": source["bundle_digest"],
        "source_skill_digest": source["skill_digest"],
        "source_acceptance_event_digest": source["acceptance_event_digest"],
        "source_task_id": source["task_id"],
        "source_agent_id": source["agent_id"],
        "owner_username": source["initiated_by_username"],
        "storage_relpath": package["storage_relpath"],
        "file_manifest_json": json.dumps(package["files"], sort_keys=True),
        "created_at": package["created_at"],
        "updated_at": package["updated_at"],
    }


def test_skill_package_repository_inserts_once_and_decodes_manifest(
    conn: sqlite3.Connection,
) -> None:
    from backend.app.storage import skill_packages

    _seed_candidate(conn)
    record = _package_record()
    skill_packages.insert_package(conn, record)

    restored = skill_packages.get_by_id(conn, record["id"])
    assert restored is not None
    assert restored["files"] == _package()["files"]
    assert "file_manifest_json" not in restored
    assert (
        skill_packages.get_by_candidate_digest(conn, record["source_candidate_digest"])
        == restored
    )
    assert skill_packages.list_approved_for_owner(conn, "test.engineer") == []

    duplicate = {**record, "id": f"skill_package_{'d' * 24}"}
    with pytest.raises(sqlite3.IntegrityError):
        skill_packages.insert_package(conn, duplicate)


def test_legacy_backfill_discovery_only_selects_latest_accepted_revision(
    conn: sqlite3.Connection,
) -> None:
    from backend.app.storage import asset_candidates

    _seed_candidate(conn)
    first_id = f"asset_candidate_{'3' * 24}"
    second_id = f"asset_candidate_{'d' * 24}"
    conn.execute(
        """
        INSERT INTO asset_candidates (
            id, schema_version, source_task_id, source_conversation_id,
            revision, supersedes_candidate_digest, bundle_digest,
            lineage_digest, candidate_digest, bundle_json, lineage_json,
            proposal_provenance_json, state, data_classification,
            initiated_by_user_id, initiated_by_username, decision_event_id,
            created_at, updated_at
        )
        SELECT ?, schema_version, source_task_id, source_conversation_id,
            2, candidate_digest, ?, ?, ?, bundle_json, lineage_json,
            proposal_provenance_json, 'accepted', data_classification,
            initiated_by_user_id, initiated_by_username, ?, ?, ?
        FROM asset_candidates WHERE id = ?
        """,
        (
            second_id,
            f"sha256:{'e' * 64}",
            f"sha256:{'f' * 64}",
            f"sha256:{'1' * 64}",
            f"asset_candidate_event_{'2' * 32}",
            "2026-08-02T11:45:00Z",
            "2026-08-02T11:50:00Z",
            first_id,
        ),
    )

    assert asset_candidates.list_accepted_without_package_ids(conn) == [second_id]


def test_skill_package_repository_appends_events_and_decides_with_cas(
    conn: sqlite3.Connection,
) -> None:
    from backend.app.storage import skill_packages

    _seed_candidate(conn)
    record = _package_record()
    skill_packages.insert_package(conn, record)
    materialized = _event("materialized")
    skill_packages.append_event(conn, materialized)

    approved = _event("approved")
    approved["event_id"] = f"skill_package_event_{'e' * 32}"
    skill_packages.append_event(conn, approved)
    assert (
        skill_packages.cas_decision(
            conn,
            package_id=record["id"],
            expected_package_digest=record["package_digest"],
            event_id=approved["event_id"],
            state="approved",
            updated_at=approved["created_at"],
        )
        == 1
    )
    assert (
        skill_packages.cas_decision(
            conn,
            package_id=record["id"],
            expected_package_digest=record["package_digest"],
            event_id=f"skill_package_event_{'f' * 32}",
            state="rejected",
            updated_at="2026-08-02T12:06:00Z",
        )
        == 0
    )

    restored = skill_packages.get_by_id(conn, record["id"])
    assert restored is not None
    assert restored["state"] == "approved"
    assert restored["review_event_id"] == approved["event_id"]
    assert skill_packages.list_approved_for_owner(conn, "test.engineer") == [restored]
    assert skill_packages.list_approved_for_owner(conn, "other.engineer") == []
    assert skill_packages.get_event(conn, materialized["event_id"]) == materialized
    assert skill_packages.get_event_by_id(conn, approved["event_id"]) == approved
    assert skill_packages.list_events(conn, record["id"]) == [
        materialized,
        approved,
    ]


def test_approved_package_id_listing_does_not_decode_malformed_manifest(
    conn: sqlite3.Connection,
) -> None:
    from backend.app.storage import skill_packages

    _seed_candidate(conn)
    record = _package_record()
    skill_packages.insert_package(conn, record)
    approved = _event("approved")
    skill_packages.append_event(conn, approved)
    assert (
        skill_packages.cas_decision(
            conn,
            package_id=record["id"],
            expected_package_digest=record["package_digest"],
            event_id=approved["event_id"],
            state="approved",
            updated_at=approved["created_at"],
        )
        == 1
    )
    conn.execute(
        "UPDATE skill_packages SET file_manifest_json = ? WHERE id = ?",
        ("not-json", record["id"]),
    )

    assert skill_packages.list_approved_ids_for_owner(
        conn, "test.engineer", limit=20
    ) == [record["id"]]
