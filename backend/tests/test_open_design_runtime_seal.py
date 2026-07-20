from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.runtime import runtime as runtime_mod
from backend.app.config import AGENTS_DIR, CONTRACTS_DIR
from backend.app.runtime.registry import AgentRegistry
from backend.app.runtime.runtime import AgentRuntime
from backend.app.storage import repos
from backend.app.storage.db import get_conn, init_db


def _running_task(
    conn,
    *,
    task_id: str = "task_open_design",
    agent_id: str = "open_design_daemon_candidate_agent",
    classification: str = "sensitive",
) -> dict:
    task = repos.create_task(
        conn,
        task_id=task_id,
        agent_id=agent_id,
        agent_version="0.1.0",
        name="Open Design candidate",
        created_by="Reviewer",
        created_by_username="reviewer",
        inputs={},
        metadata={"preserved": {"value": 1}},
    )
    repos.set_task_data_classification(conn, task_id, classification)
    repos.set_task_status(conn, task_id, "queued")
    repos.set_task_status(conn, task_id, "validating")
    return repos.set_task_status(conn, task_id, "running")


def test_open_design_metadata_seal_is_exact_cas_and_preserves_unrelated_metadata(tmp_path) -> None:
    db_path = tmp_path / "flai.db"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        before = _running_task(conn)
        sealed = repos.seal_open_design_candidate_metadata(
            conn,
            "task_open_design",
            review_contract="open-design-candidate/v1",
            generator_kind="open_design_daemon",
            candidate_manifest_sha256="a" * 64,
        )
        assert sealed["status"] == "running"
        assert sealed["updated_at"] == before["updated_at"]
        assert sealed["metadata"] == {
            "preserved": {"value": 1},
            "review_contract": "open-design-candidate/v1",
            "generator_kind": "open_design_daemon",
            "candidate_manifest_sha256": "a" * 64,
        }

        with pytest.raises(repos.InvalidOpenDesignCandidateError, match="already sealed"):
            repos.seal_open_design_candidate_metadata(
                conn,
                "task_open_design",
                review_contract="open-design-candidate/v1",
                generator_kind="open_design_daemon",
                candidate_manifest_sha256="b" * 64,
            )
        assert repos.get_task(conn, "task_open_design")["metadata"] == sealed["metadata"]
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("agent_id", "manifest_sha", "expected"),
    [
        ("hello_agent", "a" * 64, "agent"),
        ("open_design_daemon_candidate_agent", "A" * 64, "sha256"),
        ("open_design_daemon_candidate_agent", "a" * 63, "sha256"),
    ],
)
def test_open_design_metadata_seal_rejects_wrong_identity_before_write(
    tmp_path, agent_id: str, manifest_sha: str, expected: str
) -> None:
    db_path = tmp_path / "flai.db"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        before = _running_task(conn, agent_id=agent_id)
        with pytest.raises(repos.InvalidOpenDesignCandidateError, match=expected):
            repos.seal_open_design_candidate_metadata(
                conn,
                "task_open_design",
                review_contract="open-design-candidate/v1",
                generator_kind="open_design_daemon",
                candidate_manifest_sha256=manifest_sha,
            )
        assert repos.get_task(conn, "task_open_design")["metadata"] == before["metadata"]
    finally:
        conn.close()


def test_open_design_metadata_seal_requires_running_state_and_rolls_back(tmp_path) -> None:
    db_path = tmp_path / "flai.db"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        _running_task(conn)
        repos.set_task_status(conn, "task_open_design", "failed", error_message="stopped")
        before = repos.get_task(conn, "task_open_design")
        with pytest.raises(repos.InvalidOpenDesignCandidateError, match="running"):
            repos.seal_open_design_candidate_metadata(
                conn,
                "task_open_design",
                review_contract="open-design-candidate/v1",
                generator_kind="open_design_daemon",
                candidate_manifest_sha256="a" * 64,
            )
        assert repos.get_task(conn, "task_open_design") == before
    finally:
        conn.close()


def test_open_design_metadata_seal_refuses_unattested_internal_classification(tmp_path) -> None:
    db_path = tmp_path / "flai.db"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        before = _running_task(conn, classification="internal")
        with pytest.raises(repos.InvalidOpenDesignCandidateError, match="sensitive"):
            repos.seal_open_design_candidate_metadata(
                conn,
                "task_open_design",
                review_contract="open-design-candidate/v1",
                generator_kind="open_design_daemon",
                candidate_manifest_sha256="a" * 64,
            )
        assert repos.get_task(conn, "task_open_design")["metadata"] == before["metadata"]
    finally:
        conn.close()


def _register_candidate_files(conn, tmp_path) -> list[str]:
    records = [
        ("file_manifest", "open_design_daemon_candidates.json", "a" * 64),
        ("file_preview", "default_desktop_light.png", "b" * 64),
    ]
    for file_id, filename, sha256 in records:
        repos.create_file(
            conn,
            file_id=file_id,
            task_id="task_open_design",
            kind="output",
            filename=filename,
            path=str(tmp_path / filename),
            size_bytes=128,
            sha256=sha256,
            classification="sensitive",
        )
    return [item[0] for item in records]


def test_open_design_review_seal_commits_metadata_outputs_status_and_event_together(tmp_path) -> None:
    db_path = tmp_path / "flai.db"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        _running_task(conn)
        output_ids = _register_candidate_files(conn, tmp_path)
        sealed = repos.seal_open_design_candidate_for_review(
            conn,
            "task_open_design",
            output_file_ids=output_ids,
            review_contract="open-design-candidate/v1",
            generator_kind="open_design_daemon",
            candidate_manifest_sha256="a" * 64,
        )
        assert sealed["status"] == "waiting_review"
        assert sealed["output_file_ids"] == output_ids
        assert sealed["metadata"]["candidate_manifest_sha256"] == "a" * 64
        assert [event["event_type"] for event in repos.list_events(conn, "task_open_design")][-1] == "review_requested"
    finally:
        conn.close()


def test_open_design_review_seal_rolls_back_all_task_projection_when_event_fails(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "flai.db"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        before = _running_task(conn)
        output_ids = _register_candidate_files(conn, tmp_path)

        def fail_event(*args, **kwargs):
            raise ValueError("event contract failed")

        monkeypatch.setattr(repos, "append_event", fail_event)
        with pytest.raises(ValueError, match="event contract failed"):
            repos.seal_open_design_candidate_for_review(
                conn,
                "task_open_design",
                output_file_ids=output_ids,
                review_contract="open-design-candidate/v1",
                generator_kind="open_design_daemon",
                candidate_manifest_sha256="a" * 64,
            )
        after = repos.get_task(conn, "task_open_design")
        assert after["status"] == "running"
        assert after["metadata"] == before["metadata"]
        assert after["output_file_ids"] == []
    finally:
        conn.close()


def _candidate_result(package_dir, output_dir) -> tuple[dict, dict]:
    promotable_asset = {
        "slot_id": "default_desktop_light",
        "source_path": "previews/default.png",
        "bundle_relpath": "captured/previews/default.png",
        "media_type": "image/png",
        "size_bytes": 128,
        "sha256": "b" * 64,
    }
    manifest = {
        "schema_version": "open-design-daemon-candidate-manifest/v1",
        "review_contract": "open-design-candidate/v1",
        "generator_kind": "open_design_daemon",
        "candidate_id": "odc-" + "c" * 32,
        "asset_slot": "task_review_summary",
        "classification": "sensitive",
        "project_id": "flai-" + "d" * 32,
        "run_id": "run-1",
        "result_package_sha256": "e" * 64,
        "execution_trust": "untrusted_generated",
        "production_readiness": "trial_not_attested",
        "candidate_only": True,
        "release_effect": "none",
        "mock": False,
        "design_reference_package_sha256": "f" * 64,
        "file_set_sha256": "1" * 64,
        "promotable_asset": promotable_asset,
        "captured_files": [
            {
                "source_path": promotable_asset["source_path"],
                "bundle_relpath": promotable_asset["bundle_relpath"],
                "media_type": "image/png",
                "size_bytes": promotable_asset["size_bytes"],
                "sha256": promotable_asset["sha256"],
                "role": "passive_preview",
            }
        ],
        "passive_previews": [],
    }
    manifest_bytes = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    bundle = output_dir / "open_design_daemon_candidate_bundle"
    bundle.mkdir(parents=True)
    (bundle / "open_design_daemon_candidates.json").write_bytes(manifest_bytes)
    output = {
        "schema_version": "open-design-daemon-candidate-output/v1",
        "review_contract": "open-design-candidate/v1",
        "generator_kind": "open_design_daemon",
        "candidate_manifest_sha256": manifest_sha,
        "candidate_id": manifest["candidate_id"],
        "asset_slot": manifest["asset_slot"],
        "classification": "sensitive",
        "project_id": manifest["project_id"],
        "run_id": manifest["run_id"],
        "result_package_sha256": manifest["result_package_sha256"],
        "generator_mode": "loopback_daemon_trial",
        "execution_trust": "untrusted_generated",
        "production_readiness": "trial_not_attested",
        "candidate_only": True,
        "release_effect": "none",
        "human_review_required": True,
        "mock": False,
        "promotable_asset": promotable_asset,
        "passive_previews": [],
        "artifacts": [
            {
                "filename": "open_design_daemon_candidates.json",
                "bundle_relpath": "open_design_daemon_candidates.json",
                "media_type": "application/json",
                "role": "candidate_manifest",
                "sha256": manifest_sha,
                "source_path": None,
            }
        ],
    }
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": list(output),
        "properties": {key: {} for key in output},
    }
    (package_dir / "output_schema.json").write_text(json.dumps(schema), encoding="utf-8")
    return {"status": "success", "outputs": [output]}, manifest


def test_runtime_preseal_binds_exact_manifest_bytes_before_review(tmp_path) -> None:
    db_path = tmp_path / "flai.db"
    init_db(db_path)
    conn = get_conn(db_path)
    package_dir = tmp_path / "agent"
    output_dir = tmp_path / "output"
    package_dir.mkdir()
    output_dir.mkdir()
    try:
        _running_task(conn)
        result, manifest = _candidate_result(package_dir, output_dir)
        sealed = runtime_mod._validate_open_design_candidate_result(
            conn,
            task_id="task_open_design",
            agent={"output": {"schema": "output_schema.json"}},
            package_dir=package_dir,
            output_dir=output_dir,
            result=result,
        )
        assert sealed["candidate_manifest_sha256"] == hashlib.sha256(
            (output_dir / "open_design_daemon_candidate_bundle" / "open_design_daemon_candidates.json").read_bytes()
        ).hexdigest()
        assert repos.get_task(conn, "task_open_design")["metadata"] == {
            "preserved": {"value": 1}
        }
        assert manifest["candidate_id"] == result["outputs"][0]["candidate_id"]
    finally:
        conn.close()


def test_runtime_preseal_rejects_manifest_byte_drift_without_metadata_write(tmp_path) -> None:
    db_path = tmp_path / "flai.db"
    init_db(db_path)
    conn = get_conn(db_path)
    package_dir = tmp_path / "agent"
    output_dir = tmp_path / "output"
    package_dir.mkdir()
    output_dir.mkdir()
    try:
        before = _running_task(conn)
        result, _manifest = _candidate_result(package_dir, output_dir)
        manifest_path = output_dir / "open_design_daemon_candidate_bundle" / "open_design_daemon_candidates.json"
        manifest_path.write_bytes(manifest_path.read_bytes() + b" ")
        with pytest.raises(repos.InvalidOpenDesignCandidateError, match="manifest"):
            runtime_mod._validate_open_design_candidate_result(
                conn,
                task_id="task_open_design",
                agent={"output": {"schema": "output_schema.json"}},
                package_dir=package_dir,
                output_dir=output_dir,
                result=result,
            )
        assert repos.get_task(conn, "task_open_design")["metadata"] == before["metadata"]
    finally:
        conn.close()


class _SensitiveOpenDesignToolRegistry:
    def get(self, tool_id: str) -> dict | None:
        if tool_id != "open_design_daemon_generate":
            return None
        return {
            "id": tool_id,
            "version": "0.1.0",
            "mock": False,
            "output_classification": "sensitive",
        }

    def call(self, *args, **kwargs):
        raise AssertionError("fake workflow must not cross the tool boundary")


def test_agent_runtime_seals_manifest_before_waiting_review(tmp_path, monkeypatch) -> None:
    agents_dir = tmp_path / "agents"
    package_dir = agents_dir / "open_design_daemon_candidate_agent"
    shutil.copytree(AGENTS_DIR / "open_design_daemon_candidate_agent", package_dir)
    yaml_path = package_dir / "agent.yaml"
    yaml_path.write_text(
        yaml_path.read_text(encoding="utf-8").replace("status: disabled", "status: draft"),
        encoding="utf-8",
    )
    registry = AgentRegistry(agents_dir, CONTRACTS_DIR / "agent.schema.json")
    registry.scan()
    assert registry.errors == []

    db_path = tmp_path / "flai.db"
    init_db(db_path)
    runtime = AgentRuntime(
        agent_registry=registry,
        tool_registry=_SensitiveOpenDesignToolRegistry(),
        model_gateway=object(),
        conn_factory=lambda: get_conn(db_path),
        task_runs_dir=tmp_path / "task_runs",
        uploads_dir=tmp_path / "uploads",
    )

    def fake_run(context: dict) -> dict:
        result, _manifest = _candidate_result(package_dir, Path(context["output_dir"]))
        return result

    monkeypatch.setattr(
        runtime_mod,
        "_load_workflow_module",
        lambda _agent_id, _workflow_path: SimpleNamespace(run=fake_run),
    )
    conn = get_conn(db_path)
    try:
        repos.create_task(
            conn,
            task_id="task_open_design",
            agent_id="open_design_daemon_candidate_agent",
            agent_version="0.1.0",
            name="candidate",
            created_by="Reviewer",
            created_by_username="reviewer",
            inputs={
                "schema_version": "open-design-daemon-request/v1",
                "asset_slot": "task_review_summary",
                "comparison_slots": ["default_desktop_light"],
                "interaction_contract": {
                    "candidate_only": True,
                    "human_review_required": True,
                    "release_effect": "none",
                    "rendering": "passive_png_only",
                },
            },
            metadata={},
        )
        repos.set_task_status(conn, "task_open_design", "queued")
        repos.set_task_status(conn, "task_open_design", "validating")
    finally:
        conn.close()

    result = runtime.execute("task_open_design")

    assert result["status"] == "waiting_review", result["task"]["error_message"]
    assert result["task"]["data_classification"] == "sensitive"
    assert result["task"]["metadata"]["review_contract"] == "open-design-candidate/v1"
    assert result["task"]["metadata"]["generator_kind"] == "open_design_daemon"
    assert len(result["task"]["metadata"]["candidate_manifest_sha256"]) == 64
    conn = get_conn(db_path)
    try:
        event_types = [
            item["event_type"]
            for item in repos.list_events(conn, "task_open_design")
        ]
        assert event_types[-1] == "review_requested"
    finally:
        conn.close()
