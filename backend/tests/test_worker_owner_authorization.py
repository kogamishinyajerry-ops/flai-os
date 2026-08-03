"""Worker/runtime authorization regression tests for legacy poisoned tasks."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pytest

from backend.app.config import AGENTS_DIR, CONTRACTS_DIR
from backend.app.jobs.runner import JobRunner
from backend.app.runtime import runtime as runtime_module
from backend.app.runtime.registry import AgentRegistry
from backend.app.runtime.runtime import AgentRuntime
from backend.app.storage import repos
from backend.app.storage.db import get_conn, init_db


class _RecordingRuntime:
    def __init__(self) -> None:
        self.executed_task_ids: list[str] = []

    def execute(self, task_id: str) -> None:
        self.executed_task_ids.append(task_id)


class _PackageSnapshotTrapRegistry:
    def __init__(self) -> None:
        self.requested_agent_ids: list[str] = []

    def package_snapshot(self, agent_id: str):
        self.requested_agent_ids.append(agent_id)
        raise AssertionError("package snapshot must remain unopened")


class _PostAuthorizationInputSwapSnapshot:
    """Test seam that mutates the task while its package is materialized."""

    def __init__(
        self,
        snapshot: Any,
        conn_factory,
        *,
        task_id: str,
        foreign_file_id: str,
    ) -> None:
        self._snapshot = snapshot
        self._conn_factory = conn_factory
        self._task_id = task_id
        self._foreign_file_id = foreign_file_id
        self.mutation_count = 0

    @property
    def digest(self) -> str:
        return self._snapshot.digest

    @property
    def manifest(self) -> dict[str, Any]:
        return self._snapshot.manifest

    @contextmanager
    def materialized(self, *, parent: Path | None = None) -> Iterator[Path]:
        with self._snapshot.materialized(parent=parent) as package_dir:
            conn = self._conn_factory()
            try:
                conn.execute(
                    "UPDATE tasks SET input_file_ids = ? WHERE id = ?",
                    (json.dumps([self._foreign_file_id]), self._task_id),
                )
                self.mutation_count += 1
            finally:
                conn.close()
            yield package_dir


class _PostAuthorizationInputSwapRegistry:
    def __init__(
        self,
        source_registry: AgentRegistry,
        conn_factory,
        *,
        task_id: str,
        foreign_file_id: str,
    ) -> None:
        snapshot = source_registry.package_snapshot("hello_agent")
        assert snapshot is not None
        self.snapshot = _PostAuthorizationInputSwapSnapshot(
            snapshot,
            conn_factory,
            task_id=task_id,
            foreign_file_id=foreign_file_id,
        )
        self.requested_agent_ids: list[str] = []

    def package_snapshot(self, agent_id: str) -> _PostAuthorizationInputSwapSnapshot:
        self.requested_agent_ids.append(agent_id)
        return self.snapshot


class _RuntimeToolTrap:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get(self, tool_id: str) -> dict[str, str]:
        return {"output_classification": "internal"}

    def call(self, tool_id: str, *_args, **_kwargs):
        self.calls.append(tool_id)
        raise AssertionError("tool must remain uncalled after owner-lineage rejection")


class _RuntimeModelTrap:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def _record(self, kind: str) -> None:
        self.calls.append(kind)
        raise AssertionError("model must remain uncalled after owner-lineage rejection")

    def chat(self, *_args, **_kwargs) -> None:
        self._record("chat")

    def embed(self, *_args, **_kwargs) -> None:
        self._record("embed")

    def vision(self, *_args, **_kwargs) -> None:
        self._record("vision")


@pytest.fixture()
def conn_factory(tmp_path: Path):
    db_path = tmp_path / "flai_os.db"
    init_db(db_path)

    def factory():
        return get_conn(db_path)

    return factory


def _create_input(
    conn,
    tmp_path: Path,
    *,
    file_id: str,
    owner_username: str,
) -> None:
    path = tmp_path / f"{file_id}.txt"
    path.write_text(f"private bytes for {owner_username}", encoding="utf-8")
    repos.create_file(
        conn,
        file_id=file_id,
        kind="input",
        filename=path.name,
        path=str(path),
        size_bytes=path.stat().st_size,
        sha256="0" * 64,
        classification="internal",
        uploaded_by=owner_username.title(),
        owner_username=owner_username,
    )


def _side_effect_counts(conn, task_id: str) -> tuple[int, int, int]:
    model_calls = conn.execute(
        "SELECT COUNT(*) FROM model_calls WHERE task_id = ?", (task_id,)
    ).fetchone()[0]
    tool_runs = conn.execute(
        "SELECT COUNT(*) FROM tool_runs WHERE task_id = ?", (task_id,)
    ).fetchone()[0]
    outputs = conn.execute(
        "SELECT COUNT(*) FROM files WHERE task_id = ? AND kind = 'output'",
        (task_id,),
    ).fetchone()[0]
    return int(model_calls), int(tool_runs), int(outputs)


def test_worker_quarantines_foreign_direct_input_before_runtime(
    conn_factory,
    tmp_path: Path,
) -> None:
    task_id = "task_alice_with_bob_input"
    conn = conn_factory()
    try:
        _create_input(
            conn,
            tmp_path,
            file_id="file_alice_owned",
            owner_username="alice",
        )
        _create_input(
            conn,
            tmp_path,
            file_id="file_bob_private",
            owner_username="bob",
        )
        task = repos.create_task(
            conn,
            task_id=task_id,
            agent_id="hello_agent",
            agent_version="0.1.0",
            name="legacy poisoned owner lineage",
            created_by="Alice",
            created_by_username="alice",
            inputs={"name": "must not execute"},
            input_file_ids=["file_bob_private"],
            metadata={},
        )
        repos.set_task_status(conn, task["id"], "queued")
    finally:
        conn.close()

    runtime = _RecordingRuntime()
    assert JobRunner(runtime, conn_factory).run_once() is True

    conn = conn_factory()
    try:
        failed = repos.get_task(conn, task_id)
        events = repos.list_events(conn, task_id)
        side_effect_counts = _side_effect_counts(conn, task_id)
    finally:
        conn.close()

    assert runtime.executed_task_ids == []
    assert side_effect_counts == (0, 0, 0)
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["error_message"] == (
        "worker_authorization_failed: task owner lineage is unavailable"
    )
    assert "bob" not in failed["error_message"].lower()
    failures = [event for event in events if event["event_type"] == "task_failed"]
    assert len(failures) == 1
    assert failures[0]["message"] == "任务运行前授权校验失败，已拒绝执行"
    assert failures[0]["payload"] == {
        "authorization_gate": "task_owner_lineage_v1",
        "reason": "invalid_owner_lineage",
    }


def test_worker_quarantines_foreign_historical_conversation_attachment(
    conn_factory,
    tmp_path: Path,
) -> None:
    task_id = "task_alice_with_poisoned_history"
    conn = conn_factory()
    try:
        _create_input(
            conn,
            tmp_path,
            file_id="file_alice_history",
            owner_username="alice",
        )
        _create_input(
            conn,
            tmp_path,
            file_id="file_bob_history",
            owner_username="bob",
        )
        repos.create_conversation(
            conn,
            conversation_id="conversation_alice_poisoned",
            agent_id="guide_agent",
            created_by="Alice",
            created_by_username="alice",
        )
        repos.append_message(
            conn,
            conversation_id="conversation_alice_poisoned",
            role="user",
            content="legacy history",
            file_ids=["file_bob_history"],
        )
        task = repos.create_task(
            conn,
            task_id=task_id,
            agent_id="hello_agent",
            agent_version="0.1.0",
            name="conversation lineage poison",
            created_by="Alice",
            created_by_username="alice",
            inputs={"name": "must not execute"},
            input_file_ids=["file_alice_history"],
            metadata={},
            conversation_id="conversation_alice_poisoned",
        )
        repos.set_task_status(conn, task["id"], "queued")
    finally:
        conn.close()

    runtime = _RecordingRuntime()
    assert JobRunner(runtime, conn_factory).run_once() is True

    conn = conn_factory()
    try:
        failed = repos.get_task(conn, task_id)
        events = repos.list_events(conn, task_id)
        side_effect_counts = _side_effect_counts(conn, task_id)
    finally:
        conn.close()

    assert runtime.executed_task_ids == []
    assert side_effect_counts == (0, 0, 0)
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["error_message"] == (
        "worker_authorization_failed: task owner lineage is unavailable"
    )
    assert "bob" not in failed["error_message"].lower()
    failures = [event for event in events if event["event_type"] == "task_failed"]
    assert len(failures) == 1
    assert failures[0]["message"] == "任务运行前授权校验失败，已拒绝执行"
    assert failures[0]["payload"] == {
        "authorization_gate": "task_owner_lineage_v1",
        "reason": "invalid_owner_lineage",
    }


def test_worker_quarantines_foreign_retry_lineage_before_runtime(
    conn_factory,
) -> None:
    conn = conn_factory()
    try:
        repos.create_task(
            conn,
            task_id="task_bob_retry_source",
            agent_id="hello_agent",
            agent_version="0.1.0",
            name="Bob private source",
            created_by="Bob",
            created_by_username="bob",
            inputs={"name": "private"},
            input_file_ids=[],
            metadata={},
        )
        task = repos.create_task(
            conn,
            task_id="task_alice_retry_poison",
            agent_id="hello_agent",
            agent_version="0.1.0",
            name="Alice poisoned retry",
            created_by="Alice",
            created_by_username="alice",
            inputs={"name": "must not execute"},
            input_file_ids=[],
            metadata={},
            retry_of="task_bob_retry_source",
        )
        repos.set_task_status(conn, task["id"], "queued")
    finally:
        conn.close()

    runtime = _RecordingRuntime()
    assert JobRunner(runtime, conn_factory).run_once() is True

    conn = conn_factory()
    try:
        failed = repos.get_task(conn, "task_alice_retry_poison")
        side_effect_counts = _side_effect_counts(
            conn,
            "task_alice_retry_poison",
        )
    finally:
        conn.close()

    assert runtime.executed_task_ids == []
    assert side_effect_counts == (0, 0, 0)
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["error_message"] == (
        "worker_authorization_failed: task owner lineage is unavailable"
    )


def test_runtime_revalidates_owner_lineage_before_package_snapshot(
    conn_factory,
    tmp_path: Path,
) -> None:
    task_id = "task_runtime_owner_revalidation"
    conn = conn_factory()
    try:
        _create_input(
            conn,
            tmp_path,
            file_id="file_runtime_bob_private",
            owner_username="bob",
        )
        task = repos.create_task(
            conn,
            task_id=task_id,
            agent_id="hello_agent",
            agent_version="0.1.0",
            name="runtime defense in depth",
            created_by="Alice",
            created_by_username="alice",
            inputs={"name": "must not execute"},
            input_file_ids=["file_runtime_bob_private"],
            metadata={},
        )
        repos.set_task_status(conn, task["id"], "queued")
        repos.set_task_status(conn, task["id"], "validating")
    finally:
        conn.close()

    registry = _PackageSnapshotTrapRegistry()
    task_runs_dir = tmp_path / "task_runs"
    runtime = AgentRuntime(
        registry,
        object(),
        object(),
        conn_factory,
        task_runs_dir,
    )
    result = runtime.execute(task_id)

    conn = conn_factory()
    try:
        failed = repos.get_task(conn, task_id)
        side_effect_counts = _side_effect_counts(conn, task_id)
    finally:
        conn.close()

    assert registry.requested_agent_ids == []
    assert not task_runs_dir.exists()
    assert side_effect_counts == (0, 0, 0)
    assert failed is not None
    assert failed["status"] == "failed"
    assert result["status"] == "failed"
    assert result["task"]["error_message"] == (
        "worker_authorization_failed: task owner lineage is unavailable"
    )


def test_runtime_reauthorizes_latest_task_after_package_materialization(
    conn_factory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_id = "task_runtime_post_materialization_reauthorization"
    owned_file_id = "file_runtime_alice_owned"
    foreign_file_id = "file_runtime_bob_swapped"
    conn = conn_factory()
    try:
        _create_input(
            conn,
            tmp_path,
            file_id=owned_file_id,
            owner_username="alice",
        )
        _create_input(
            conn,
            tmp_path,
            file_id=foreign_file_id,
            owner_username="bob",
        )
        task = repos.create_task(
            conn,
            task_id=task_id,
            agent_id="hello_agent",
            agent_version="0.1.0",
            name="runtime post-materialization authorization window",
            created_by="Alice",
            created_by_username="alice",
            inputs={"name": "must not execute"},
            input_file_ids=[owned_file_id],
            metadata={},
        )
        repos.set_task_status(conn, task["id"], "queued")
        repos.set_task_status(conn, task["id"], "validating")
    finally:
        conn.close()

    source_registry = AgentRegistry(
        AGENTS_DIR,
        CONTRACTS_DIR / "agent.schema.json",
    )
    source_registry.scan()
    assert source_registry.errors == []
    registry = _PostAuthorizationInputSwapRegistry(
        source_registry,
        conn_factory,
        task_id=task_id,
        foreign_file_id=foreign_file_id,
    )
    tool_registry = _RuntimeToolTrap()
    model_gateway = _RuntimeModelTrap()
    opened_paths: list[str] = []

    def trap_input_open(path, **_kwargs):
        opened_paths.append(str(path))
        raise AssertionError("foreign input must remain unopened")

    monkeypatch.setattr(runtime_module, "open_verified_file", trap_input_open)
    task_runs_dir = tmp_path / "task_runs"
    runtime = AgentRuntime(
        registry,
        tool_registry,
        model_gateway,
        conn_factory,
        task_runs_dir,
        uploads_dir=tmp_path,
    )

    result = runtime.execute(task_id)

    conn = conn_factory()
    try:
        failed = repos.get_task(conn, task_id)
        events = repos.list_events(conn, task_id)
        side_effect_counts = _side_effect_counts(conn, task_id)
    finally:
        conn.close()

    assert registry.requested_agent_ids == ["hello_agent"]
    assert registry.snapshot.mutation_count == 1
    assert opened_paths == []
    assert tool_registry.calls == []
    assert model_gateway.calls == []
    assert not (task_runs_dir / task_id / "output").exists()
    assert side_effect_counts == (0, 0, 0)
    assert failed is not None
    assert failed["input_file_ids"] == [foreign_file_id]
    assert failed["status"] == "failed"
    assert failed["error_message"] == (
        "worker_authorization_failed: task owner lineage is unavailable"
    )
    assert result["status"] == "failed"
    assert result["task"]["error_message"] == failed["error_message"]
    assert [event["event_type"] for event in events] == ["task_failed"]
    assert events[0]["message"] == "任务运行前授权校验失败，已拒绝执行"
    assert events[0]["payload"] == {
        "authorization_gate": "task_owner_lineage_v1",
        "reason": "invalid_owner_lineage",
    }


def test_worker_quarantines_malformed_root_then_claims_valid_owned_task(
    conn_factory,
) -> None:
    conn = conn_factory()
    try:
        poisoned = repos.create_task(
            conn,
            task_id="task_malformed_owner_lineage",
            agent_id="hello_agent",
            agent_version="0.1.0",
            name="malformed legacy root",
            created_by="Alice",
            created_by_username="alice",
            inputs={"name": "must not execute"},
            input_file_ids=[],
            metadata={},
        )
        repos.set_task_status(conn, poisoned["id"], "queued")
        conn.execute(
            "UPDATE tasks SET input_file_ids = ? WHERE id = ?",
            ("{malformed-json", poisoned["id"]),
        )

        valid = repos.create_task(
            conn,
            task_id="task_valid_owned_after_poison",
            agent_id="hello_agent",
            agent_version="0.1.0",
            name="valid owned task",
            created_by="Alice",
            created_by_username="alice",
            inputs={"name": "allowed"},
            input_file_ids=[],
            metadata={},
        )
        repos.set_task_status(conn, valid["id"], "queued")
    finally:
        conn.close()

    runtime = _RecordingRuntime()
    runner = JobRunner(runtime, conn_factory)
    assert runner.run_once() is True
    assert runtime.executed_task_ids == []
    assert runner.run_once() is True
    assert runtime.executed_task_ids == ["task_valid_owned_after_poison"]

    conn = conn_factory()
    try:
        poisoned_projection = conn.execute(
            "SELECT status, error_message FROM tasks WHERE id = ?",
            ("task_malformed_owner_lineage",),
        ).fetchone()
        poison_events = repos.list_events(
            conn,
            "task_malformed_owner_lineage",
        )
        valid_projection = repos.get_task(
            conn,
            "task_valid_owned_after_poison",
        )
    finally:
        conn.close()

    assert poisoned_projection["status"] == "failed"
    assert poisoned_projection["error_message"] == (
        "worker_authorization_failed: task owner lineage is unavailable"
    )
    assert [event["event_type"] for event in poison_events] == ["task_failed"]
    assert valid_projection is not None
    assert valid_projection["status"] == "validating"
