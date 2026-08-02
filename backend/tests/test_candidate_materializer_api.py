from __future__ import annotations

import json
import os
import shutil
import sqlite3
import stat
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from jsonschema import ValidationError, validate

from backend.app.governance.signer_provenance import SignerContext
from backend.app.main import create_app
from backend.app.ontology.candidate_materializer import (
    CandidateMaterializer,
    SkillPackageNotFoundError,
    SkillPackageUnavailableError,
)
from backend.app.storage import asset_candidates as candidate_store
from backend.app.storage import skill_packages as package_store
from backend.app.storage.db import get_conn
from backend.tests.conftest import (
    TEST_DISPLAY_NAME,
    TEST_PASSWORD,
    TEST_USERNAME,
    login,
    seed_and_login,
    seed_user,
)
from backend.tests.test_asset_candidates_api import (
    _create_candidate,
    _decision,
    _seed_task,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "contracts"


def _schema(name: str) -> dict[str, Any]:
    return json.loads((CONTRACTS_DIR / name).read_text(encoding="utf-8"))


def _package_counts(app) -> tuple[int, int]:
    conn = app.state.conn_factory()
    try:
        return (
            conn.execute("SELECT COUNT(*) FROM skill_packages").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM skill_package_events").fetchone()[0],
        )
    finally:
        conn.close()


def _accept(client, candidate: dict[str, Any]):
    return client.post(
        f"/api/asset-candidates/{candidate['id']}/decision",
        json=_decision(candidate),
    )


def _package_decision(package: dict[str, Any], action: str) -> dict[str, Any]:
    return {
        "schema_version": "skill_package_decision_request.v1",
        "action": action,
        "expected_package_digest": package["package_digest"],
    }


def _test_app(tmp_path: Path):
    return create_app(
        agents_dir=REPO_ROOT / "agents",
        tools_dir=REPO_ROOT / "tools_impl",
        contracts_dir=REPO_ROOT / "contracts",
        db_path=tmp_path / "flai_os.db",
        uploads_dir=tmp_path / "uploads",
        task_runs_dir=tmp_path / "task_runs",
        frontend_dist_dir=tmp_path / "frontend-dist-does-not-exist",
    )


def test_relative_db_path_derives_an_absolute_isolated_package_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The documented relative DB setting must still produce an absolute root."""

    monkeypatch.chdir(tmp_path)
    app = create_app(
        agents_dir=REPO_ROOT / "agents",
        tools_dir=REPO_ROOT / "tools_impl",
        contracts_dir=REPO_ROOT / "contracts",
        db_path=Path("data/flai_os.db"),
        uploads_dir=tmp_path / "uploads",
        task_runs_dir=tmp_path / "task_runs",
        frontend_dist_dir=tmp_path / "frontend-dist-does-not-exist",
    )

    with TestClient(app):
        expected_db = (tmp_path / "data/flai_os.db").resolve()
        assert app.state.db_path == expected_db
        assert (
            app.state.candidate_skill_packages_dir
            == (tmp_path / "data/candidate_skill_packages").resolve()
        )
        assert app.state.candidate_materializer.root.is_absolute()

        moved_cwd = tmp_path / "moved-cwd"
        moved_cwd.mkdir()
        monkeypatch.chdir(moved_cwd)
        conn = app.state.conn_factory()
        try:
            database_file = Path(
                conn.execute("PRAGMA database_list").fetchone()["file"]
            ).resolve()
        finally:
            conn.close()
        assert database_file == expected_db


def test_accepting_candidate_atomically_materializes_isolated_pending_skill_package(
    app_env,
) -> None:
    client, app = app_env
    candidate = _create_candidate(client, _seed_task(app)).json()
    registry_count = len(app.state.agent_registry.list())

    response = _accept(client, candidate)

    assert response.status_code == 200
    body = response.json()
    package = body["skill_package"]
    validate(package, _schema("candidate_skill_package.schema.json"))
    assert body["state"] == "accepted"
    assert package["state"] == "pending_review"
    assert package["source"] == {
        "candidate_id": candidate["id"],
        "candidate_digest": candidate["candidate_digest"],
        "bundle_digest": candidate["bundle_digest"],
        "skill_digest": candidate["bundle"]["skill"]["content_digest"],
        "acceptance_event_digest": package["source"]["acceptance_event_digest"],
        "task_id": candidate["source"]["task_id"],
        "agent_id": candidate["source"]["agent_id"],
        "initiated_by_username": TEST_USERNAME,
    }
    assert package["version"] == "0.1.0"
    assert package["review"] is None
    assert package["reuse_eligible"] is False
    assert package["isolation"] == {
        "zone": "candidate_quarantine",
        "registered": False,
        "executable": False,
    }
    assert {item["path"] for item in package["files"]} == {
        "SKILL.md",
        "references/provenance.json",
        "references/skill-revision.json",
        "references/task-pattern-revision.json",
    }

    package_dir = app.state.candidate_skill_packages_dir / package["storage_relpath"]
    skill_md = (package_dir / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = skill_md.split("---", 2)[1].strip().splitlines()
    assert [line.split(":", 1)[0] for line in frontmatter] == [
        "name",
        "description",
    ]
    assert package_dir.is_relative_to(app.state.candidate_skill_packages_dir)
    assert not package_dir.is_relative_to(app.state.agents_dir)
    assert len(app.state.agent_registry.list()) == registry_count
    assert _package_counts(app) == (1, 1)

    restored = client.get(f"/api/skill-packages/{package['id']}")
    assert restored.status_code == 200
    assert restored.json() == package


def test_asset_candidate_contract_requires_exact_package_only_after_acceptance(
    app_env,
) -> None:
    client, app = app_env
    candidate = _create_candidate(client, _seed_task(app)).json()
    accepted = _accept(client, candidate).json()
    schema = _schema("asset_candidate.schema.json")
    validate(accepted, schema)

    for invalid in (
        {**deepcopy(accepted), "skill_package": {}},
        {**deepcopy(accepted), "skill_package": None},
        {**deepcopy(accepted), "state": "rejected"},
    ):
        with pytest.raises(ValidationError):
            validate(invalid, schema)


def test_rejected_candidate_never_materializes_package(app_env) -> None:
    client, app = app_env
    candidate = _create_candidate(client, _seed_task(app)).json()

    response = client.post(
        f"/api/asset-candidates/{candidate['id']}/decision",
        json=_decision(candidate, "reject"),
    )

    assert response.status_code == 200
    assert response.json()["skill_package"] is None
    assert _package_counts(app) == (0, 0)
    assert not app.state.candidate_skill_packages_dir.exists()


def test_package_review_is_independent_session_bound_digest_cas(app_env) -> None:
    client, app = app_env
    candidate = _create_candidate(client, _seed_task(app)).json()
    package = _accept(client, candidate).json()["skill_package"]

    approved_response = client.post(
        f"/api/skill-packages/{package['id']}/decision",
        json=_package_decision(package, "approve"),
    )

    assert approved_response.status_code == 200
    approved = approved_response.json()
    validate(approved, _schema("candidate_skill_package.schema.json"))
    assert approved["state"] == "approved"
    assert approved["reuse_eligible"] is True
    assert approved["review"] == {
        "action": "approve",
        "reviewed_by": TEST_DISPLAY_NAME,
        "reviewed_by_username": TEST_USERNAME,
        "signer_source": "authenticated_session",
        "signer_session_bound": True,
        "created_at": approved["review"]["created_at"],
    }
    assert _package_counts(app) == (1, 2)

    second = client.post(
        f"/api/skill-packages/{package['id']}/decision",
        json=_package_decision(package, "reject"),
    )
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "skill_package_already_decided"
    assert _package_counts(app) == (1, 2)


def test_package_read_and_review_fail_closed_after_file_tamper(app_env) -> None:
    client, app = app_env
    candidate = _create_candidate(client, _seed_task(app)).json()
    package = _accept(client, candidate).json()["skill_package"]
    package_dir = app.state.candidate_skill_packages_dir / package["storage_relpath"]
    (package_dir / "SKILL.md").write_text("tampered", encoding="utf-8")

    assert client.get(f"/api/skill-packages/{package['id']}").status_code == 503
    review = client.post(
        f"/api/skill-packages/{package['id']}/decision",
        json=_package_decision(package, "approve"),
    )
    assert review.status_code == 503
    assert _package_counts(app) == (1, 1)


def test_startup_backfills_legacy_accepted_candidate_without_creating_a_new_decision(
    tmp_path,
) -> None:
    first = _test_app(tmp_path)
    with TestClient(first) as client:
        seed_and_login(client, first.state.db_path)
        candidate = _create_candidate(client, _seed_task(first)).json()
        accepted = _accept(client, candidate)
        assert accepted.status_code == 200
        original_package = accepted.json()["skill_package"]

    # Reproduce an ADR-0034-era accepted row: the exact human decision remains,
    # while the later ADR-0035 package projection is absent.
    conn = get_conn(first.state.db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM skill_package_events")
        conn.execute("DELETE FROM skill_packages")
        conn.execute("COMMIT")
    finally:
        conn.close()
    shutil.rmtree(first.state.candidate_skill_packages_dir)

    second = _test_app(tmp_path)
    with TestClient(second) as client:
        login(client)
        assert _package_counts(second) == (1, 1)
        restored = client.get(f"/api/skill-packages/{original_package['id']}")
        assert restored.status_code == 200
        assert restored.json()["package_digest"] == original_package["package_digest"]

        conn = second.state.conn_factory()
        try:
            decision_count = conn.execute(
                """
                SELECT COUNT(*) FROM asset_candidate_events
                WHERE candidate_id = ? AND event_type = 'candidate_accepted'
                """,
                (candidate["id"],),
            ).fetchone()[0]
        finally:
            conn.close()
        assert decision_count == 1


def test_backfill_rechecks_latest_revision_inside_each_write_transaction(
    app_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, app = app_env
    candidate = _create_candidate(client, _seed_task(app)).json()
    accepted = _accept(client, candidate)
    assert accepted.status_code == 200

    newer_id = f"asset_candidate_{'f' * 24}"
    conn = app.state.conn_factory()
    try:
        conn.execute("DELETE FROM skill_package_events")
        conn.execute("DELETE FROM skill_packages")
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
                2, candidate_digest, bundle_digest, lineage_digest, ?,
                bundle_json, lineage_json, proposal_provenance_json,
                'awaiting_human_review', data_classification,
                initiated_by_user_id, initiated_by_username, NULL,
                '2099-01-01T00:00:00Z', '2099-01-01T00:00:00Z'
            FROM asset_candidates WHERE id = ?
            """,
            (newer_id, f"sha256:{'f' * 64}", candidate["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    shutil.rmtree(app.state.candidate_skill_packages_dir)

    # Simulate revision 2 arriving after the read-only discovery snapshot but
    # before this candidate's BEGIN IMMEDIATE write transaction.
    monkeypatch.setattr(
        candidate_store,
        "list_accepted_without_package_ids",
        lambda _conn: [candidate["id"]],
    )

    assert (
        app.state.candidate_materializer.backfill_legacy_accepted(
            app.state.conn_factory
        )
        == 0
    )
    assert not app.state.candidate_skill_packages_dir.exists()


def test_rollback_retry_adopts_same_byte_orphan_for_same_human_attestation(
    app_env,
    monkeypatch,
) -> None:
    client, app = app_env
    candidate = _create_candidate(client, _seed_task(app)).json()
    real_insert = package_store.insert_package
    failed_once = False

    def crash_after_rename(conn, record):
        nonlocal failed_once
        if failed_once is False:
            failed_once = True
            raise sqlite3.OperationalError("injected crash after package rename")
        return real_insert(conn, record)

    monkeypatch.setattr(package_store, "insert_package", crash_after_rename)
    first = _accept(client, candidate)
    assert first.status_code == 503
    assert _package_counts(app) == (0, 0)
    orphan_dirs = sorted(
        path.name
        for path in (app.state.candidate_skill_packages_dir / "quarantine").iterdir()
    )
    assert len(orphan_dirs) == 1

    retry = _accept(client, candidate)
    assert retry.status_code == 200
    package = retry.json()["skill_package"]
    assert package["id"] == orphan_dirs[0]
    assert _package_counts(app) == (1, 1)


def test_parent_symlink_into_forbidden_agent_root_is_rejected(tmp_path) -> None:
    forbidden_agents = tmp_path / "agent-packages"
    forbidden_agents.mkdir()
    linked_parent = tmp_path / "data-link"
    linked_parent.symlink_to(forbidden_agents, target_is_directory=True)

    with pytest.raises(ValueError, match="forbidden"):
        CandidateMaterializer(
            linked_parent / "candidate_skill_packages",
            object(),
            forbidden_roots=(forbidden_agents,),
        )


@pytest.mark.skipif(
    os.name == "nt", reason="Windows does not support POSIX directory fsync"
)
def test_directory_fsync_failure_rolls_back_candidate_acceptance(
    app_env,
    monkeypatch,
) -> None:
    client, app = app_env
    candidate = _create_candidate(client, _seed_task(app)).json()
    real_fsync = os.fsync

    def fail_directory_fsync(fd: int) -> None:
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("injected directory fsync failure")
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_directory_fsync)
    response = _accept(client, candidate)

    assert response.status_code == 503
    assert _package_counts(app) == (0, 0)
    conn = app.state.conn_factory()
    try:
        stored = candidate_store.get_by_id(conn, candidate["id"])
    finally:
        conn.close()
    assert stored is not None
    assert stored["state"] == "awaiting_human_review"
    assert stored["decision_event_id"] is None


@pytest.mark.skipif(
    os.name == "nt", reason="Windows does not support POSIX directory fsync"
)
def test_first_materialization_fsyncs_new_isolation_root_parent(
    app_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Publishing a newly-created quarantine root must persist its dirent."""

    client, app = app_env
    candidate = _create_candidate(client, _seed_task(app)).json()
    from backend.app.ontology import candidate_materializer as materializer_mod

    real_fsync_directory = materializer_mod._fsync_directory
    fsynced: list[Path] = []

    def record_directory_fsync(path: Path) -> None:
        fsynced.append(path)
        real_fsync_directory(path)

    monkeypatch.setattr(
        materializer_mod,
        "_fsync_directory",
        record_directory_fsync,
    )

    response = _accept(client, candidate)

    assert response.status_code == 200
    assert app.state.candidate_skill_packages_dir.parent in fsynced


def test_materializer_mutations_require_caller_owned_transaction(app_env) -> None:
    client, app = app_env
    candidate = _create_candidate(client, _seed_task(app)).json()
    package = _accept(client, candidate).json()["skill_package"]
    conn = app.state.conn_factory()
    try:
        stored_candidate = candidate_store.get_by_id(conn, candidate["id"])
        assert stored_candidate is not None
        accepted_event = candidate_store.get_event(
            conn, stored_candidate["decision_event_id"]
        )
        assert accepted_event is not None
        with pytest.raises(SkillPackageUnavailableError, match="transaction"):
            app.state.candidate_materializer.materialize_accepted(
                conn,
                candidate_public=app.state.asset_candidate_ledger._public_projection(
                    conn, stored_candidate
                ),
                accepted_event=accepted_event,
            )
        with pytest.raises(SkillPackageUnavailableError, match="transaction"):
            app.state.candidate_materializer.decide(
                conn,
                package_id=package["id"],
                expected_package_digest=package["package_digest"],
                action="approve",
                signer_context=SignerContext.from_server_cli("test-operator"),
            )
    finally:
        conn.close()


def test_package_decision_owner_gate_is_404_before_digest_or_state_oracle(
    app_env,
) -> None:
    client, app = app_env
    candidate = _create_candidate(client, _seed_task(app)).json()
    package = _accept(client, candidate).json()["skill_package"]
    second_username = "another_engineer"
    seed_user(
        app.state.db_path,
        username=second_username,
        display_name="另一位工程师",
        password=TEST_PASSWORD,
    )
    client.post("/api/auth/logout")
    login(client, username=second_username, password=TEST_PASSWORD)

    response = client.post(
        f"/api/skill-packages/{package['id']}/decision",
        json={
            "schema_version": "skill_package_decision_request.v1",
            "action": "approve",
            "expected_package_digest": "sha256:" + "0" * 64,
        },
    )
    assert response.status_code == 404


def test_foreign_corrupt_package_is_404_before_manifest_decode_oracle(
    app_env,
) -> None:
    client, app = app_env
    candidate = _create_candidate(client, _seed_task(app)).json()
    package = _accept(client, candidate).json()["skill_package"]

    conn = app.state.conn_factory()
    try:
        conn.execute(
            "UPDATE skill_packages SET file_manifest_json = ? WHERE id = ?",
            ("{", package["id"]),
        )
        conn.commit()
    finally:
        conn.close()

    second_username = "another_engineer"
    seed_user(
        app.state.db_path,
        username=second_username,
        display_name="另一位工程师",
        password=TEST_PASSWORD,
    )
    client.post("/api/auth/logout")
    login(client, username=second_username, password=TEST_PASSWORD)

    responses = [
        client.get(f"/api/skill-packages/{package['id']}"),
        client.get(f"/api/skill-packages/{package['id']}/review-content"),
        client.post(
            f"/api/skill-packages/{package['id']}/decision",
            json=_package_decision(package, "approve"),
        ),
    ]

    assert [response.status_code for response in responses] == [404, 404, 404]


def test_candidate_digest_lookup_owner_gate_precedes_corrupt_manifest_decode(
    app_env,
) -> None:
    client, app = app_env
    candidate = _create_candidate(client, _seed_task(app)).json()
    package = _accept(client, candidate).json()["skill_package"]
    conn = app.state.conn_factory()
    try:
        conn.execute(
            "UPDATE skill_packages SET file_manifest_json = ? WHERE id = ?",
            ("{", package["id"]),
        )
        conn.commit()

        assert (
            app.state.candidate_materializer.get_for_candidate_digest(
                conn,
                candidate_digest=candidate["candidate_digest"],
                username="not-the-owner",
            )
            is None
        )
        with pytest.raises(SkillPackageUnavailableError):
            app.state.candidate_materializer.get_for_candidate_digest(
                conn,
                candidate_digest=candidate["candidate_digest"],
                username=TEST_USERNAME,
            )
    finally:
        conn.close()


def test_review_content_cold_verifies_pending_bytes_owner_and_fixed_order(
    app_env,
) -> None:
    client, app = app_env
    candidate = _create_candidate(client, _seed_task(app)).json()
    package = _accept(client, candidate).json()["skill_package"]
    conn = app.state.conn_factory()
    try:
        content = app.state.candidate_materializer.get_review_content(
            conn,
            package_id=package["id"],
            username=TEST_USERNAME,
        )
        assert content["schema_version"] == "skill_package_review_content.v1"
        assert content["package_id"] == package["id"]
        assert content["package_digest"] == package["package_digest"]
        assert [item["path"] for item in content["files"]] == [
            "SKILL.md",
            "references/provenance.json",
            "references/skill-revision.json",
            "references/task-pattern-revision.json",
        ]
        assert all(isinstance(item["text"], str) for item in content["files"])

        with pytest.raises(SkillPackageNotFoundError):
            app.state.candidate_materializer.get_review_content(
                conn,
                package_id=package["id"],
                username="not-the-owner",
            )

        package_dir = (
            app.state.candidate_skill_packages_dir / package["storage_relpath"]
        )
        (package_dir / "SKILL.md").write_text("tampered", encoding="utf-8")
        with pytest.raises(SkillPackageUnavailableError):
            app.state.candidate_materializer.get_review_content(
                conn,
                package_id=package["id"],
                username=TEST_USERNAME,
            )
    finally:
        conn.close()


def test_reuse_listing_accepts_bounded_sentinel_only(app_env) -> None:
    _, app = app_env
    conn = app.state.conn_factory()
    try:
        assert (
            app.state.candidate_materializer.list_reuse_eligible(
                conn,
                username=TEST_USERNAME,
                limit=101,
            )
            == []
        )
        with pytest.raises(ValueError):
            app.state.candidate_materializer.list_reuse_eligible(
                conn,
                username=TEST_USERNAME,
                limit=102,
            )
    finally:
        conn.close()


def test_reuse_listing_rejects_raw_101_sentinel_before_corrupt_row_filtering(
    app_env,
) -> None:
    client, app = app_env
    candidate = _create_candidate(client, _seed_task(app)).json()
    package = _accept(client, candidate).json()["skill_package"]
    approved = client.post(
        f"/api/skill-packages/{package['id']}/decision",
        json=_package_decision(package, "approve"),
    )
    assert approved.status_code == 200

    conn = app.state.conn_factory()
    try:
        for index in range(1, 101):
            clone_id = f"skill_package_{index:024x}"
            conn.execute(
                """
                INSERT INTO skill_packages (
                    id, schema_version, name, version, package_digest, state,
                    source_candidate_id, source_candidate_digest,
                    source_bundle_digest, source_skill_digest,
                    source_acceptance_event_digest, source_task_id,
                    source_agent_id, owner_username, storage_relpath,
                    file_manifest_json, review_event_id, created_at, updated_at
                )
                SELECT ?, schema_version, name, version, ?, 'approved',
                    source_candidate_id, ?, source_bundle_digest,
                    source_skill_digest, source_acceptance_event_digest,
                    source_task_id, source_agent_id, owner_username, ?, '{',
                    review_event_id, created_at, '2099-01-01T00:00:00Z'
                FROM skill_packages WHERE id = ?
                """,
                (
                    clone_id,
                    f"sha256:{index + 1000:064x}",
                    f"sha256:{index + 2000:064x}",
                    f"quarantine/{clone_id}",
                    package["id"],
                ),
            )
        conn.commit()

        with pytest.raises(SkillPackageUnavailableError, match="bounded"):
            app.state.candidate_materializer.list_reuse_eligible(
                conn,
                username=TEST_USERNAME,
                limit=101,
            )
    finally:
        conn.close()
