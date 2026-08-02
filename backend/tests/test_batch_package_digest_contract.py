"""Batch creation package-snapshot pinning and stable conflict codes."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app.api.tasks import (
    BatchTaskItem,
    _snapshot_input_validation_error,
    run_batch_creation,
)
from backend.app.runtime.registry import AgentRegistry
from backend.app.storage import repos


def _task_count(conn) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0])


def _pins(app) -> tuple[str, str]:
    snapshot = app.state.agent_registry.package_snapshot("hello_agent")
    assert snapshot is not None
    return snapshot.manifest["version"], snapshot.digest


def _agent_pins(app, agent_id: str) -> tuple[str, str]:
    snapshot = app.state.agent_registry.package_snapshot(agent_id)
    assert snapshot is not None
    return snapshot.manifest["version"], snapshot.digest


def _batch_payload(*, version: str, digest: str, operation_id: str) -> dict:
    return {
        "operation_id": operation_id,
        "pinned_versions": {"hello_agent": version},
        "pinned_package_digests": {"hello_agent": digest},
        "items": [
            {
                "agent_id": "hello_agent",
                "name": "不可变包开工",
                "inputs": {"name": "固定输入"},
            }
        ],
    }


def _shadow_registry(app, tmp_path: Path) -> tuple[AgentRegistry, Path]:
    source_snapshot = app.state.agent_registry.package_snapshot("hello_agent")
    assert source_snapshot is not None
    agents_dir = tmp_path / "agents"
    package_dir = agents_dir / "hello_agent"
    agents_dir.mkdir()
    with source_snapshot.materialized(parent=tmp_path) as materialized:
        shutil.copytree(materialized, package_dir)
    registry = AgentRegistry(agents_dir, app.state.agent_registry.schema_path)
    registry.scan()
    assert registry.errors == []
    return registry, package_dir


def test_snapshot_input_validation_respects_explicit_none_mode() -> None:
    snapshot = SimpleNamespace(files=(), manifest={"input": {"type": "none"}})

    assert _snapshot_input_validation_error(
        snapshot=snapshot,
        inputs={},
    ) is None
    assert "不接受 inputs" in (
        _snapshot_input_validation_error(
            snapshot=snapshot,
            inputs={"unexpected": True},
        )
        or ""
    )
    assert "不接受附件" in (
        _snapshot_input_validation_error(
            snapshot=snapshot,
            inputs={},
            input_file_ids=["file_1"],
        )
        or ""
    )


def test_public_batch_api_derives_pin_when_client_omits_pin_envelope(app_env):
    client, app = app_env
    before = len(client.get("/api/tasks").json())
    snapshot = app.state.agent_registry.package_snapshot("hello_agent")
    assert snapshot is not None

    response = client.post(
        "/api/tasks/batch",
        json={"items": [{"agent_id": "hello_agent", "inputs": {"name": "x"}}]},
    )

    assert response.status_code == 200, response.text
    task = response.json()["tasks"][0]
    assert task["agent_version"] == snapshot.manifest["version"]
    assert task["metadata"]["package_snapshot_digest"] == snapshot.digest
    assert len(client.get("/api/tasks").json()) == before + 1


def test_api_digest_pin_map_requires_full_agent_coverage_with_zero_writes(app_env):
    client, app = app_env
    version, _digest = _pins(app)
    before = len(client.get("/api/tasks").json())

    response = client.post(
        "/api/tasks/batch",
        json={
            "operation_id": "digest_coverage_001",
            "pinned_versions": {"hello_agent": version},
            "pinned_package_digests": {},
            "items": [{"agent_id": "hello_agent", "inputs": {"name": "x"}}],
        },
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "batch_pin_contract_incomplete"
    assert "缺少创建时包摘要钉" in response.text
    assert len(client.get("/api/tasks").json()) == before


def test_api_operation_and_versions_without_digest_rejected_with_zero_writes(app_env):
    client, app = app_env
    version, _digest = _pins(app)
    before = len(client.get("/api/tasks").json())

    response = client.post(
        "/api/tasks/batch",
        json={
            "operation_id": "digest_omitted_001",
            "pinned_versions": {"hello_agent": version},
            "items": [{"agent_id": "hello_agent", "inputs": {"name": "x"}}],
        },
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "batch_pin_contract_incomplete"
    assert "pinned_package_digests" in response.text
    assert len(client.get("/api/tasks").json()) == before


def test_api_digest_only_rejected_with_zero_writes(app_env):
    client, app = app_env
    _version, digest = _pins(app)
    before = len(client.get("/api/tasks").json())

    response = client.post(
        "/api/tasks/batch",
        json={
            "pinned_package_digests": {"hello_agent": digest},
            "items": [{"agent_id": "hello_agent", "inputs": {"name": "x"}}],
        },
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "batch_pin_contract_incomplete"
    assert "operation_id" in response.text
    assert "pinned_versions" in response.text
    assert len(client.get("/api/tasks").json()) == before


def test_public_batch_api_rejects_pin_maps_with_extra_agents(app_env):
    client, app = app_env
    version, digest = _pins(app)
    extra_version, extra_digest = _agent_pins(app, "performance_disk_agent")
    before = len(client.get("/api/tasks").json())

    response = client.post(
        "/api/tasks/batch",
        json={
            "operation_id": "pin_extra_agent_001",
            "pinned_versions": {
                "hello_agent": version,
                "performance_disk_agent": extra_version,
            },
            "pinned_package_digests": {
                "hello_agent": digest,
                "performance_disk_agent": extra_digest,
            },
            "items": [{"agent_id": "hello_agent", "inputs": {"name": "x"}}],
        },
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "batch_pin_contract_incomplete"
    assert detail["unexpected_agents"] == {
        "pinned_versions": ["performance_disk_agent"],
        "pinned_package_digests": ["performance_disk_agent"],
    }
    assert len(client.get("/api/tasks").json()) == before


def test_api_pinned_batch_validates_inputs_from_snapshot_before_any_write(app_env):
    client, app = app_env
    version, digest = _pins(app)
    before = len(client.get("/api/tasks").json())

    invalid = client.post(
        "/api/tasks/batch",
        json=_batch_payload(
            version=version,
            digest=digest,
            operation_id="snapshot_schema_invalid_001",
        )
        | {"items": [{"agent_id": "hello_agent", "inputs": {}}]},
    )

    assert invalid.status_code == 422, invalid.text
    assert invalid.json()["detail"]["code"] == "batch_inputs_invalid"
    assert "input_schema.json" in invalid.text
    assert len(client.get("/api/tasks").json()) == before

    valid = client.post(
        "/api/tasks/batch",
        json=_batch_payload(
            version=version,
            digest=digest,
            operation_id="snapshot_schema_valid_001",
        ),
    )
    assert valid.status_code == 200, valid.text
    assert valid.json()["tasks"][0]["status"] == "queued"
    assert len(client.get("/api/tasks").json()) == before + 1


def test_one_invalid_item_rejects_mixed_batch_without_partial_rows(app_env):
    client, app = app_env
    version, digest = _pins(app)
    before = len(client.get("/api/tasks").json())

    response = client.post(
        "/api/tasks/batch",
        json={
            "operation_id": "snapshot_schema_mixed_001",
            "pinned_versions": {"hello_agent": version},
            "pinned_package_digests": {"hello_agent": digest},
            "items": [
                {"agent_id": "hello_agent", "inputs": {"name": "valid"}},
                {"agent_id": "hello_agent", "inputs": {}, "after": [0]},
            ],
        },
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "batch_inputs_invalid"
    assert [error["index"] for error in detail["batch_errors"]] == [1]
    assert len(client.get("/api/tasks").json()) == before


def test_file_upload_batch_requires_exactly_one_attachment_with_zero_writes(app_env):
    client, app = app_env
    version, digest = _agent_pins(app, "performance_disk_agent")
    before = len(client.get("/api/tasks").json())

    response = client.post(
        "/api/tasks/batch",
        json={
            "operation_id": "file_upload_missing_attachment_001",
            "pinned_versions": {"performance_disk_agent": version},
            "pinned_package_digests": {"performance_disk_agent": digest},
            "items": [{"agent_id": "performance_disk_agent", "inputs": {}}],
        },
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "batch_inputs_invalid"
    assert "恰好 1 个" in response.text
    assert len(client.get("/api/tasks").json()) == before


def test_downstream_file_upload_may_defer_attachment_to_dependency_resolver(app_env):
    client, app = app_env
    hello_version, hello_digest = _pins(app)
    upload_version, upload_digest = _agent_pins(app, "performance_disk_agent")
    before = len(client.get("/api/tasks").json())

    response = client.post(
        "/api/tasks/batch",
        json={
            "operation_id": "file_upload_deferred_from_dependency_001",
            "pinned_versions": {
                "hello_agent": hello_version,
                "performance_disk_agent": upload_version,
            },
            "pinned_package_digests": {
                "hello_agent": hello_digest,
                "performance_disk_agent": upload_digest,
            },
            "items": [
                {"agent_id": "hello_agent", "inputs": {"name": "upstream"}},
                {
                    "agent_id": "performance_disk_agent",
                    "inputs": {},
                    "after": [0],
                },
            ],
        },
    )

    assert response.status_code == 200, response.text
    tasks = response.json()["tasks"]
    assert [task["status"] for task in tasks] == ["queued", "created"]
    assert tasks[1]["input_file_ids"] == []
    assert len(client.get("/api/tasks").json()) == before + 2


def test_file_upload_batch_rejects_extension_outside_pinned_manifest(app_env):
    client, app = app_env
    version, digest = _agent_pins(app, "performance_disk_agent")
    uploaded = client.post(
        "/api/files/upload",
        files={"file": ("cases.csv", b"not-an-xlsx")},
    )
    assert uploaded.status_code == 200, uploaded.text
    file_id = uploaded.json()["id"]
    before = len(client.get("/api/tasks").json())

    response = client.post(
        "/api/tasks/batch",
        json={
            "operation_id": "file_upload_wrong_extension_001",
            "pinned_versions": {"performance_disk_agent": version},
            "pinned_package_digests": {"performance_disk_agent": digest},
            "items": [
                {
                    "agent_id": "performance_disk_agent",
                    "inputs": {},
                    "input_file_ids": [file_id],
                }
            ],
        },
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "batch_inputs_invalid"
    assert ".xlsx" in response.text
    assert len(client.get("/api/tasks").json()) == before


def test_file_upload_batch_requires_existing_input_file_with_zero_writes(app_env):
    client, app = app_env
    version, digest = _agent_pins(app, "performance_disk_agent")
    before = len(client.get("/api/tasks").json())

    response = client.post(
        "/api/tasks/batch",
        json={
            "operation_id": "file_upload_missing_record_001",
            "pinned_versions": {"performance_disk_agent": version},
            "pinned_package_digests": {"performance_disk_agent": digest},
            "items": [
                {
                    "agent_id": "performance_disk_agent",
                    "inputs": {},
                    "input_file_ids": ["missing_file_record"],
                }
            ],
        },
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "batch_inputs_invalid"
    assert "附件不存在" in response.text
    assert len(client.get("/api/tasks").json()) == before


def test_file_upload_batch_rejects_non_input_file_kind_with_zero_writes(app_env):
    client, app = app_env
    version, digest = _agent_pins(app, "performance_disk_agent")
    conn = app.state.conn_factory()
    try:
        output_file = repos.create_file(
            conn,
            file_id="output_disguised_as_upload",
            task_id=None,
            kind="output",
            filename="cases.xlsx",
            path="/nonexistent/cases.xlsx",
            size_bytes=1,
            sha256="0" * 64,
            classification="internal",
        )
    finally:
        conn.close()
    before = len(client.get("/api/tasks").json())

    response = client.post(
        "/api/tasks/batch",
        json={
            "operation_id": "file_upload_wrong_kind_001",
            "pinned_versions": {"performance_disk_agent": version},
            "pinned_package_digests": {"performance_disk_agent": digest},
            "items": [
                {
                    "agent_id": "performance_disk_agent",
                    "inputs": {},
                    "input_file_ids": [output_file["id"]],
                }
            ],
        },
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "batch_inputs_invalid"
    assert "kind=input" in response.text
    assert len(client.get("/api/tasks").json()) == before


def test_attachment_violation_rejects_entire_mixed_batch_before_any_write(app_env):
    client, app = app_env
    version, digest = _agent_pins(app, "performance_disk_agent")
    accepted_upload = client.post(
        "/api/files/upload",
        files={"file": ("accepted.xlsx", b"placeholder")},
    )
    rejected_upload = client.post(
        "/api/files/upload",
        files={"file": ("rejected.csv", b"placeholder")},
    )
    assert accepted_upload.status_code == 200, accepted_upload.text
    assert rejected_upload.status_code == 200, rejected_upload.text
    before = len(client.get("/api/tasks").json())

    response = client.post(
        "/api/tasks/batch",
        json={
            "operation_id": "file_upload_mixed_atomic_001",
            "pinned_versions": {"performance_disk_agent": version},
            "pinned_package_digests": {"performance_disk_agent": digest},
            "items": [
                {
                    "agent_id": "performance_disk_agent",
                    "inputs": {},
                    "input_file_ids": [accepted_upload.json()["id"]],
                },
                {
                    "agent_id": "performance_disk_agent",
                    "inputs": {},
                    "input_file_ids": [rejected_upload.json()["id"]],
                },
            ],
        },
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "batch_inputs_invalid"
    assert [error["index"] for error in detail["batch_errors"]] == [1]
    assert len(client.get("/api/tasks").json()) == before


def test_same_version_package_rescan_rejects_old_digest_before_any_write(
    app_env, tmp_path: Path
):
    client, app = app_env
    registry, package_dir = _shadow_registry(app, tmp_path)
    old_snapshot = registry.package_snapshot("hello_agent")
    assert old_snapshot is not None

    schema_path = package_dir / "input_schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["description"] = "same-version package mutation"
    schema_path.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    registry.scan()
    assert registry.errors == []
    new_snapshot = registry.package_snapshot("hello_agent")
    assert new_snapshot is not None
    assert new_snapshot.manifest["version"] == old_snapshot.manifest["version"]
    assert new_snapshot.digest != old_snapshot.digest

    class CountingRegistry:
        def __init__(self, delegate):
            self.delegate = delegate
            self.package_snapshot_calls = 0

        def get(self, agent_id):
            return self.delegate.get(agent_id)

        def package_snapshot(self, agent_id):
            self.package_snapshot_calls += 1
            return self.delegate.package_snapshot(agent_id)

    counting_registry = CountingRegistry(registry)

    conn = app.state.conn_factory()
    try:
        before = _task_count(conn)
        with pytest.raises(HTTPException) as exc_info:
            run_batch_creation(
                conn=conn,
                agent_registry=counting_registry,
                items=[BatchTaskItem(agent_id="hello_agent", inputs={"name": "x"})],
                conversation_id=None,
                created_by="测试工程师",
                created_by_username="test_engineer",
                pinned_versions={"hello_agent": old_snapshot.manifest["version"]},
                pinned_package_digests={"hello_agent": old_snapshot.digest},
                operation_id="same_version_old_digest_001",
            )
        assert exc_info.value.status_code == 422
        assert "包摘要" in str(exc_info.value.detail)
        assert counting_registry.package_snapshot_calls == 1
        assert _task_count(conn) == before

        created = run_batch_creation(
            conn=conn,
            agent_registry=counting_registry,
            items=[BatchTaskItem(agent_id="hello_agent", inputs={"name": "x"})],
            conversation_id=None,
            created_by="测试工程师",
            created_by_username="test_engineer",
            pinned_versions={"hello_agent": new_snapshot.manifest["version"]},
            pinned_package_digests={"hello_agent": new_snapshot.digest},
            operation_id="same_version_new_digest_001",
        )["tasks"][0]
        assert counting_registry.package_snapshot_calls == 2
    finally:
        conn.close()

    assert created["agent_version"] == new_snapshot.manifest["version"]
    assert created["metadata"]["package_snapshot_digest"] == new_snapshot.digest
    assert len(client.get("/api/tasks").json()) == before + 1


def test_digest_is_part_of_operation_fingerprint_and_conflict_has_stable_code(app_env):
    client, app = app_env
    version, digest = _pins(app)
    payload = _batch_payload(
        version=version,
        digest=digest,
        operation_id="digest_fingerprint_001",
    )
    committed = client.post("/api/tasks/batch", json=payload)
    assert committed.status_code == 200, committed.text
    assert committed.json()["tasks"][0]["metadata"]["package_snapshot_digest"] == digest
    count_after_commit = len(client.get("/api/tasks").json())

    changed = json.loads(json.dumps(payload))
    changed["pinned_package_digests"]["hello_agent"] = "0" * 64
    conflict = client.post("/api/tasks/batch", json=changed)

    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["detail"]["code"] == "batch_operation_conflict"
    assert len(client.get("/api/tasks").json()) == count_after_commit


def test_run_batch_concluded_conversation_has_distinct_code_and_zero_writes(app_env):
    _client, app = app_env
    version, digest = _pins(app)
    conn = app.state.conn_factory()
    try:
        repos.create_conversation(
            conn,
            conversation_id="conv_digest_concluded",
            agent_id="guide_agent",
            created_by="测试工程师",
        )
        repos.set_conversation_status(conn, "conv_digest_concluded", "concluded")
        before = _task_count(conn)

        with pytest.raises(HTTPException) as exc_info:
            run_batch_creation(
                conn=conn,
                agent_registry=app.state.agent_registry,
                items=[BatchTaskItem(agent_id="hello_agent", inputs={"name": "x"})],
                conversation_id="conv_digest_concluded",
                created_by="测试工程师",
                created_by_username="test_engineer",
                pinned_versions={"hello_agent": version},
                pinned_package_digests={"hello_agent": digest},
                operation_id="digest_concluded_001",
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "conversation_not_active"
        assert _task_count(conn) == before
    finally:
        conn.close()
