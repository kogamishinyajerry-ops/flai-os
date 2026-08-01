"""Runtime package digest pin regression tests."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

from backend.app.config import AGENTS_DIR, CONTRACTS_DIR, TOOLS_DIR
from backend.app.runtime.registry import AgentRegistry
from backend.app.runtime.runtime import AgentRuntime
from backend.app.storage import repos
from backend.app.storage.db import get_conn, init_db
from backend.app.tools.registry import ToolRegistry


class _UnusedModelGateway:
    """hello_agent is a zero-model package; any model call is a test failure."""

    def chat(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("hello_agent must not call the model gateway")

    def embed(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("hello_agent must not call the model gateway")

    def vision(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("hello_agent must not call the model gateway")


def _runtime_with_mutable_authoring_package(
    tmp_path: Path,
    *,
    file_upload_allowed_extensions: tuple[str, ...] | None = None,
) -> tuple[AgentRuntime, AgentRegistry, Path, Path]:
    agents_dir = tmp_path / "agents"
    package_dir = agents_dir / "hello_agent"
    shutil.copytree(AGENTS_DIR / "hello_agent", package_dir)
    if file_upload_allowed_extensions is not None:
        manifest_path = package_dir / "agent.yaml"
        manifest_text = manifest_path.read_text(encoding="utf-8")
        params_contract = "input:\n  type: params\n  schema: input_schema.json"
        assert params_contract in manifest_text
        extension_lines = "".join(
            f"    - {extension}\n" for extension in file_upload_allowed_extensions
        )
        file_contract = (
            "input:\n"
            "  type: file_upload\n"
            "  allowed_extensions:\n"
            f"{extension_lines}"
            "  schema: input_schema.json"
        )
        manifest_path.write_text(
            manifest_text.replace(params_contract, file_contract),
            encoding="utf-8",
        )

    registry = AgentRegistry(agents_dir, CONTRACTS_DIR / "agent.schema.json")
    registry.scan()
    assert registry.errors == []

    tool_registry = ToolRegistry(TOOLS_DIR, CONTRACTS_DIR / "tool.schema.json")
    tool_registry.scan()
    assert tool_registry.errors == []

    db_path = tmp_path / "flai_os.db"
    init_db(db_path)
    runtime = AgentRuntime(
        agent_registry=registry,
        tool_registry=tool_registry,
        model_gateway=_UnusedModelGateway(),
        conn_factory=lambda: get_conn(db_path),
        task_runs_dir=tmp_path / "task_runs",
        uploads_dir=tmp_path / "uploads",
    )
    return runtime, registry, package_dir, db_path


def _create_validating_task(
    db_path: Path,
    *,
    task_id: str,
    package_snapshot_digest: str,
) -> None:
    conn = get_conn(db_path)
    try:
        repos.create_task(
            conn,
            task_id=task_id,
            agent_id="hello_agent",
            agent_version="0.1.0",
            name="package digest pin test",
            created_by="tester",
            inputs={"name": "世界"},
            input_file_ids=[],
            metadata={"package_snapshot_digest": package_snapshot_digest},
        )
        repos.set_task_status(conn, task_id, "queued")
        repos.set_task_status(conn, task_id, "validating")
    finally:
        conn.close()


def _create_piped_output_and_validating_task(
    db_path: Path,
    task_runs_dir: Path,
    *,
    task_id: str,
    filename: str,
    package_snapshot_digest: str,
) -> None:
    upstream_task_id = f"{task_id}_upstream"
    file_id = f"{task_id}_file"
    payload = b"verified resolver output fixture"
    file_path = task_runs_dir / upstream_task_id / "output" / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(payload)

    conn = get_conn(db_path)
    try:
        repos.create_task(
            conn,
            task_id=upstream_task_id,
            agent_id="hello_agent",
            agent_version="0.1.0",
            name="reviewed upstream",
            created_by="tester",
            inputs={"name": "upstream"},
            input_file_ids=[],
            metadata={},
        )
        repos.create_file(
            conn,
            file_id=file_id,
            task_id=upstream_task_id,
            kind="output",
            filename=filename,
            path=str(file_path),
            size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            classification="internal",
        )
        repos.set_task_outputs(conn, upstream_task_id, [file_id])
        for status in ("queued", "validating", "running", "analyzing", "completed"):
            repos.set_task_status(conn, upstream_task_id, status)
        repos.append_event(
            conn,
            task_id=upstream_task_id,
            agent_id="hello_agent",
            event_type="review_approved",
            level="info",
            message="reviewed upstream output fixture",
        )

        repos.create_task(
            conn,
            task_id=task_id,
            agent_id="hello_agent",
            agent_version="0.1.0",
            name="runtime final file contract test",
            created_by="tester",
            inputs={"name": "downstream"},
            input_file_ids=[file_id],
            metadata={"package_snapshot_digest": package_snapshot_digest},
            depends_on=[upstream_task_id],
            input_binding={"from_tasks": [upstream_task_id]},
        )
        repos.set_task_status(conn, task_id, "queued")
        repos.set_task_status(conn, task_id, "validating")
    finally:
        conn.close()


def test_execute_rejects_same_version_package_drift_before_workflow_side_effects(
    tmp_path: Path,
) -> None:
    runtime, registry, package_dir, db_path = _runtime_with_mutable_authoring_package(
        tmp_path
    )
    original_snapshot = registry.package_snapshot("hello_agent")
    assert original_snapshot is not None
    _create_validating_task(
        db_path,
        task_id="task_pinned_old_package",
        package_snapshot_digest=original_snapshot.digest,
    )

    workflow_path = package_dir / "workflow.py"
    workflow_path.write_text(
        workflow_path.read_text(encoding="utf-8")
        + "\n# same manifest version, different package generation\n",
        encoding="utf-8",
    )
    registry.scan()
    assert registry.errors == []
    current_snapshot = registry.package_snapshot("hello_agent")
    assert current_snapshot is not None
    assert current_snapshot.manifest["version"] == original_snapshot.manifest["version"]
    assert current_snapshot.digest != original_snapshot.digest

    result = runtime.execute("task_pinned_old_package")

    assert result["status"] == "failed"
    assert result["task"]["data_classification"] == "internal"
    assert "包快照摘要" in result["task"]["error_message"]
    assert result["task"]["output_file_ids"] == []

    conn = get_conn(db_path)
    try:
        assert repos.list_tool_runs(conn, "task_pinned_old_package") == []
        assert [
            event["event_type"]
            for event in repos.list_events(conn, "task_pinned_old_package")
        ] == ["task_failed"]
    finally:
        conn.close()


def test_execute_accepts_matching_package_snapshot_digest(tmp_path: Path) -> None:
    runtime, registry, _package_dir, db_path = _runtime_with_mutable_authoring_package(
        tmp_path
    )
    snapshot = registry.package_snapshot("hello_agent")
    assert snapshot is not None
    _create_validating_task(
        db_path,
        task_id="task_pinned_current_package",
        package_snapshot_digest=snapshot.digest,
    )

    result = runtime.execute("task_pinned_current_package")

    assert result["status"] == "completed"
    assert len(result["task"]["output_file_ids"]) == 1
    conn = get_conn(db_path)
    try:
        tool_runs = repos.list_tool_runs(conn, "task_pinned_current_package")
        assert len(tool_runs) == 1
        assert tool_runs[0]["status"] == "success"
    finally:
        conn.close()


def test_execute_rejects_piped_wrong_extension_before_workflow(
    tmp_path: Path,
) -> None:
    runtime, registry, _package_dir, db_path = _runtime_with_mutable_authoring_package(
        tmp_path,
        file_upload_allowed_extensions=(".xlsx",),
    )
    snapshot = registry.package_snapshot("hello_agent")
    assert snapshot is not None
    task_id = "task_piped_json_into_xlsx_agent"
    _create_piped_output_and_validating_task(
        db_path,
        runtime.task_runs_dir,
        task_id=task_id,
        filename="resolver_output.json",
        package_snapshot_digest=snapshot.digest,
    )

    result = runtime.execute(task_id)

    assert result["status"] == "failed"
    assert "扩展名" in result["task"]["error_message"]
    assert ".xlsx" in result["task"]["error_message"]
    assert result["task"]["output_file_ids"] == []
    conn = get_conn(db_path)
    try:
        assert repos.list_tool_runs(conn, task_id) == []
        assert [event["event_type"] for event in repos.list_events(conn, task_id)] == [
            "validation_started",
            "validation_failed",
            "task_failed",
        ]
    finally:
        conn.close()


def test_execute_accepts_one_verified_piped_file_with_allowed_extension(
    tmp_path: Path,
) -> None:
    runtime, registry, _package_dir, db_path = _runtime_with_mutable_authoring_package(
        tmp_path,
        file_upload_allowed_extensions=(".xlsx",),
    )
    snapshot = registry.package_snapshot("hello_agent")
    assert snapshot is not None
    task_id = "task_piped_xlsx_into_xlsx_agent"
    _create_piped_output_and_validating_task(
        db_path,
        runtime.task_runs_dir,
        task_id=task_id,
        filename="resolver_output.xlsx",
        package_snapshot_digest=snapshot.digest,
    )

    result = runtime.execute(task_id)

    assert result["status"] == "completed"
    assert len(result["task"]["output_file_ids"]) == 1
    conn = get_conn(db_path)
    try:
        tool_runs = repos.list_tool_runs(conn, task_id)
        assert len(tool_runs) == 1
        assert tool_runs[0]["status"] == "success"
    finally:
        conn.close()


def test_execute_rejects_file_upload_without_final_attachment(tmp_path: Path) -> None:
    runtime, registry, _package_dir, db_path = _runtime_with_mutable_authoring_package(
        tmp_path,
        file_upload_allowed_extensions=(".xlsx",),
    )
    snapshot = registry.package_snapshot("hello_agent")
    assert snapshot is not None
    task_id = "task_file_upload_without_attachment"
    _create_validating_task(
        db_path,
        task_id=task_id,
        package_snapshot_digest=snapshot.digest,
    )

    result = runtime.execute(task_id)

    assert result["status"] == "failed"
    assert "必须且只能有 1 个附件，实际 0 个" in result["task"]["error_message"]
    conn = get_conn(db_path)
    try:
        assert repos.list_tool_runs(conn, task_id) == []
    finally:
        conn.close()


def test_execute_rejects_final_attachment_for_none_input_contract(
    tmp_path: Path,
) -> None:
    runtime, registry, package_dir, db_path = _runtime_with_mutable_authoring_package(
        tmp_path
    )
    manifest_path = package_dir / "agent.yaml"
    manifest_text = manifest_path.read_text(encoding="utf-8")
    assert "input:\n  type: params" in manifest_text
    manifest_path.write_text(
        manifest_text.replace("input:\n  type: params", "input:\n  type: none"),
        encoding="utf-8",
    )
    registry.scan()
    assert registry.errors == []
    snapshot = registry.package_snapshot("hello_agent")
    assert snapshot is not None
    task_id = "task_none_with_piped_attachment"
    _create_piped_output_and_validating_task(
        db_path,
        runtime.task_runs_dir,
        task_id=task_id,
        filename="resolver_output.json",
        package_snapshot_digest=snapshot.digest,
    )

    result = runtime.execute(task_id)

    assert result["status"] == "failed"
    assert "input.type=none 必须有 0 个附件" in result["task"]["error_message"]
    conn = get_conn(db_path)
    try:
        assert repos.list_tool_runs(conn, task_id) == []
    finally:
        conn.close()
