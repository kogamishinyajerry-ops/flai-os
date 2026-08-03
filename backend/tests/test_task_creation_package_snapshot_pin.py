"""Real task creation paths pin one authoritative Agent Package snapshot."""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any

from backend.app.storage import repos
from backend.tests.conftest import TEST_USERNAME


class _SplitReadRegistry:
    """Expose a stale manifest read while keeping the authoritative snapshot intact."""

    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate

    def get(self, agent_id: str) -> dict[str, Any] | None:
        agent = self._delegate.get(agent_id)
        if agent is None:
            return None
        stale = copy.deepcopy(agent)
        stale["version"] = "9.9.9"
        return stale

    def package_snapshot(self, agent_id: str) -> Any:
        return self._delegate.package_snapshot(agent_id)


class _SnapshotUnavailableRegistry:
    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate

    def get(self, agent_id: str) -> dict[str, Any] | None:
        return self._delegate.get(agent_id)

    def package_snapshot(self, agent_id: str) -> None:
        return None


class _InvalidSnapshotRegistry(_SnapshotUnavailableRegistry):
    def package_snapshot(self, agent_id: str) -> Any:
        snapshot = self._delegate.package_snapshot(agent_id)
        return SimpleNamespace(manifest=snapshot.manifest, digest="not-a-digest")


class _StaleHighClearanceRegistry(_SnapshotUnavailableRegistry):
    """The mutable projection is permissive; the authoritative snapshot is not."""

    def get(self, agent_id: str) -> dict[str, Any] | None:
        agent = self._delegate.get(agent_id)
        if agent is None:
            return None
        stale = copy.deepcopy(agent)
        stale["clearance"] = {"max_data_classification": "sensitive"}
        return stale

    def package_snapshot(self, agent_id: str) -> Any:
        return self._delegate.package_snapshot(agent_id)


class _StaleDisabledRegistry(_SnapshotUnavailableRegistry):
    def get(self, agent_id: str) -> dict[str, Any] | None:
        agent = self._delegate.get(agent_id)
        if agent is None:
            return None
        stale = copy.deepcopy(agent)
        stale["status"] = "disabled"
        return stale

    def package_snapshot(self, agent_id: str) -> Any:
        return self._delegate.package_snapshot(agent_id)


class _CountingSnapshot:
    def __init__(self, snapshot: Any) -> None:
        self._snapshot = snapshot
        self._digest = snapshot.digest
        self.files = snapshot.files
        self.manifest_reads = 0
        self.digest_reads = 0

    @property
    def digest(self) -> str:
        self.digest_reads += 1
        return self._digest

    @property
    def manifest(self) -> dict[str, Any]:
        self.manifest_reads += 1
        return self._snapshot.manifest


class _CountingSnapshotRegistry(_SnapshotUnavailableRegistry):
    def __init__(self, delegate: Any, agent_id: str) -> None:
        super().__init__(delegate)
        self.snapshot = _CountingSnapshot(delegate.package_snapshot(agent_id))

    def package_snapshot(self, agent_id: str) -> Any:
        return self.snapshot


def test_single_task_pins_digest_and_version_from_one_registry_snapshot(
    app_env,
) -> None:
    client, app = app_env
    registry = app.state.agent_registry
    snapshot = registry.package_snapshot("hello_agent")
    assert snapshot is not None
    app.state.agent_registry = _SplitReadRegistry(registry)
    try:
        response = client.post(
            "/api/tasks",
            json={"agent_id": "hello_agent", "inputs": {"name": "snapshot pinned"}},
        )
    finally:
        app.state.agent_registry = registry

    assert response.status_code == 200, response.text
    task = response.json()
    assert task["agent_version"] == snapshot.manifest["version"]
    assert task["metadata"]["package_snapshot_digest"] == snapshot.digest


def test_single_task_without_name_uses_server_snapshot_display_name(app_env) -> None:
    client, app = app_env
    snapshot = app.state.agent_registry.package_snapshot("hello_agent")
    assert snapshot is not None

    response = client.post(
        "/api/tasks",
        json={"agent_id": "hello_agent", "inputs": {"name": "auto named"}},
    )

    assert response.status_code == 200, response.text
    assert response.json()["name"] == snapshot.manifest["name"]


def test_single_task_fails_closed_when_registry_snapshot_is_unavailable(
    app_env,
) -> None:
    client, app = app_env
    registry = app.state.agent_registry
    before = len(client.get("/api/tasks").json())
    app.state.agent_registry = _SnapshotUnavailableRegistry(registry)
    try:
        response = client.post(
            "/api/tasks",
            json={"agent_id": "hello_agent", "inputs": {"name": "must not write"}},
        )
    finally:
        app.state.agent_registry = registry

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "agent_package_snapshot_unavailable"
    assert len(client.get("/api/tasks").json()) == before


def test_single_task_fails_closed_when_registry_snapshot_digest_is_invalid(
    app_env,
) -> None:
    client, app = app_env
    registry = app.state.agent_registry
    before = len(client.get("/api/tasks").json())
    app.state.agent_registry = _InvalidSnapshotRegistry(registry)
    try:
        response = client.post(
            "/api/tasks",
            json={"agent_id": "hello_agent", "inputs": {"name": "must not write"}},
        )
    finally:
        app.state.agent_registry = registry

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "agent_package_snapshot_invalid"
    assert len(client.get("/api/tasks").json()) == before


def test_batch_auto_pins_registry_snapshot_and_preserves_operation_metadata(
    app_env,
) -> None:
    client, app = app_env
    registry = app.state.agent_registry
    snapshot = registry.package_snapshot("hello_agent")
    assert snapshot is not None
    app.state.agent_registry = _SplitReadRegistry(registry)
    try:
        response = client.post(
            "/api/tasks/batch",
            json={
                "operation_id": "auto_pin_batch_001",
                "items": [
                    {
                        "agent_id": "hello_agent",
                        "name": "自动钉包",
                        "inputs": {"name": "batch snapshot pinned"},
                    }
                ],
            },
        )
    finally:
        app.state.agent_registry = registry

    assert response.status_code == 200, response.text
    task = response.json()["tasks"][0]
    assert task["agent_version"] == snapshot.manifest["version"]
    assert task["metadata"]["package_snapshot_digest"] == snapshot.digest
    assert (
        task["metadata"]["guide_batch_operation"]["operation_id"]
        == "auto_pin_batch_001"
    )


def test_batch_without_name_uses_server_snapshot_display_name(app_env) -> None:
    client, app = app_env
    snapshot = app.state.agent_registry.package_snapshot("hello_agent")
    assert snapshot is not None

    response = client.post(
        "/api/tasks/batch",
        json={"items": [{"agent_id": "hello_agent", "inputs": {"name": "x"}}]},
    )

    assert response.status_code == 200, response.text
    assert response.json()["tasks"][0]["name"] == snapshot.manifest["name"]


def test_batch_parses_one_snapshot_manifest_once_per_agent(app_env) -> None:
    client, app = app_env
    registry = app.state.agent_registry
    counting = _CountingSnapshotRegistry(registry, "hello_agent")
    app.state.agent_registry = counting
    try:
        response = client.post(
            "/api/tasks/batch",
            json={
                "items": [
                    {"agent_id": "hello_agent", "inputs": {"name": f"item-{idx}"}}
                    for idx in range(3)
                ]
            },
        )
    finally:
        app.state.agent_registry = registry

    assert response.status_code == 200, response.text
    assert counting.snapshot.manifest_reads == 1
    assert counting.snapshot.digest_reads == 1


def test_batch_status_gate_uses_authoritative_snapshot_not_stale_projection(
    app_env,
) -> None:
    client, app = app_env
    registry = app.state.agent_registry
    snapshot = registry.package_snapshot("hello_agent")
    assert snapshot is not None
    app.state.agent_registry = _StaleDisabledRegistry(registry)
    try:
        response = client.post(
            "/api/tasks/batch",
            json={"items": [{"agent_id": "hello_agent", "inputs": {"name": "x"}}]},
        )
    finally:
        app.state.agent_registry = registry

    assert response.status_code == 200, response.text
    task = response.json()["tasks"][0]
    assert task["agent_version"] == snapshot.manifest["version"]
    assert task["metadata"]["package_snapshot_digest"] == snapshot.digest


def _save_single_member_team(client: Any, app: Any) -> dict[str, Any]:
    conn = app.state.conn_factory()
    try:
        repos.create_conversation(
            conn,
            conversation_id="conv_team_snapshot_pin",
            agent_id="guide_agent",
            created_by="tester",
            created_by_username=TEST_USERNAME,
        )
        repos.set_conversation_recommendation(
            conn,
            "conv_team_snapshot_pin",
            {
                "decision": "orchestrate",
                "goal": "验证团队自动钉包",
                "agents": [{"agent_id": "hello_agent", "role": "执行"}],
            },
        )
    finally:
        conn.close()
    response = client.post(
        "/api/teams",
        json={"name": "自动钉包团队", "conversation_id": "conv_team_snapshot_pin"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_team_summon_gates_and_pins_from_registry_snapshot(app_env) -> None:
    client, app = app_env
    registry = app.state.agent_registry
    snapshot = registry.package_snapshot("hello_agent")
    assert snapshot is not None
    team = _save_single_member_team(client, app)
    app.state.agent_registry = _SplitReadRegistry(registry)
    try:
        response = client.post(
            f"/api/teams/{team['id']}/summon",
            json={"items": [{"seq": 0, "inputs": {"name": "team snapshot pinned"}}]},
        )
    finally:
        app.state.agent_registry = registry

    assert response.status_code == 200, response.text
    task = response.json()["tasks"][0]
    assert task["agent_version"] == snapshot.manifest["version"]
    assert task["metadata"]["package_snapshot_digest"] == snapshot.digest


def test_batch_fails_closed_when_registry_snapshot_is_unavailable(app_env) -> None:
    client, app = app_env
    registry = app.state.agent_registry
    before = len(client.get("/api/tasks").json())
    app.state.agent_registry = _SnapshotUnavailableRegistry(registry)
    try:
        response = client.post(
            "/api/tasks/batch",
            json={
                "items": [
                    {"agent_id": "hello_agent", "inputs": {"name": "must not write"}}
                ]
            },
        )
    finally:
        app.state.agent_registry = registry

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "agent_package_snapshot_unavailable"
    assert len(client.get("/api/tasks").json()) == before


def test_batch_fails_closed_when_registry_snapshot_digest_is_invalid(app_env) -> None:
    client, app = app_env
    registry = app.state.agent_registry
    before = len(client.get("/api/tasks").json())
    app.state.agent_registry = _InvalidSnapshotRegistry(registry)
    try:
        response = client.post(
            "/api/tasks/batch",
            json={
                "items": [
                    {"agent_id": "hello_agent", "inputs": {"name": "must not write"}}
                ]
            },
        )
    finally:
        app.state.agent_registry = registry

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "agent_package_snapshot_invalid"
    assert len(client.get("/api/tasks").json()) == before


def test_batch_rechecks_clearance_from_the_same_snapshot_it_persists(app_env) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        file_row = repos.create_file(
            conn,
            file_id="file_snapshot_clearance_race",
            task_id=None,
            kind="input",
            filename="sensitive-cases.xlsx",
            path="/nonexistent/sensitive-cases.xlsx",
            size_bytes=10,
            sha256="0" * 64,
            classification="sensitive",
            owner_username=TEST_USERNAME,
        )
    finally:
        conn.close()

    registry = app.state.agent_registry
    before = len(client.get("/api/tasks").json())
    app.state.agent_registry = _StaleHighClearanceRegistry(registry)
    try:
        response = client.post(
            "/api/tasks/batch",
            json={
                "items": [
                    {
                        "agent_id": "performance_disk_agent",
                        "inputs": {},
                        "input_file_ids": [file_row["id"]],
                    }
                ]
            },
        )
    finally:
        app.state.agent_registry = registry

    assert response.status_code == 422, response.text
    assert "密级准入上限" in response.text
    assert len(client.get("/api/tasks").json()) == before


def test_team_summon_fails_closed_when_registry_snapshot_is_unavailable(
    app_env,
) -> None:
    client, app = app_env
    registry = app.state.agent_registry
    team = _save_single_member_team(client, app)
    before = len(client.get("/api/tasks").json())
    app.state.agent_registry = _SnapshotUnavailableRegistry(registry)
    try:
        response = client.post(
            f"/api/teams/{team['id']}/summon",
            json={"items": [{"seq": 0, "inputs": {"name": "must not write"}}]},
        )
    finally:
        app.state.agent_registry = registry

    assert response.status_code == 422, response.text
    assert "不可变包快照不可用" in response.text
    assert len(client.get("/api/tasks").json()) == before


def test_team_summon_fails_closed_when_registry_snapshot_digest_is_invalid(
    app_env,
) -> None:
    client, app = app_env
    registry = app.state.agent_registry
    team = _save_single_member_team(client, app)
    before = len(client.get("/api/tasks").json())
    app.state.agent_registry = _InvalidSnapshotRegistry(registry)
    try:
        response = client.post(
            f"/api/teams/{team['id']}/summon",
            json={"items": [{"seq": 0, "inputs": {"name": "must not write"}}]},
        )
    finally:
        app.state.agent_registry = registry

    assert response.status_code == 422, response.text
    assert "快照结构或摘要无效" in response.text
    assert len(client.get("/api/tasks").json()) == before
