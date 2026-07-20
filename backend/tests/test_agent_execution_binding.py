"""Agent execution binding contract and frozen task projection.

The tests exercise the public seams named by the implementation contract:
AgentRegistry.scan(), init_db()/repos.create_task(), and the task HTTP endpoints.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import ValidationError, validate

from backend.app.config import AGENTS_DIR, CONTRACTS_DIR
from backend.app.runtime.registry import AgentRegistry
from backend.app.storage import db as db_mod
from backend.app.storage import repos


AGENT_SCHEMA = json.loads(
    (CONTRACTS_DIR / "agent.schema.json").read_text(encoding="utf-8")
)
TASK_SCHEMA = json.loads(
    (CONTRACTS_DIR / "task.schema.json").read_text(encoding="utf-8")
)


def _copy_agent(tmp_path: Path, agent_id: str = "fta_agent") -> tuple[Path, Path]:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    package_dir = agents_dir / agent_id
    shutil.copytree(AGENTS_DIR / agent_id, package_dir)
    return agents_dir, package_dir


def _manifest(package_dir: Path) -> dict[str, Any]:
    return yaml.safe_load((package_dir / "agent.yaml").read_text(encoding="utf-8"))


def _write_manifest(package_dir: Path, manifest: dict[str, Any]) -> None:
    (package_dir / "agent.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _scan(agents_dir: Path) -> AgentRegistry:
    registry = AgentRegistry(agents_dir, CONTRACTS_DIR / "agent.schema.json")
    registry.scan()
    return registry


class TestAgentExecutionManifestContract:
    def test_schema_keeps_execution_optional_but_closes_its_shape(self) -> None:
        legacy = yaml.safe_load(
            (AGENTS_DIR / "hello_agent" / "agent.yaml").read_text(encoding="utf-8")
        )
        validate(legacy, AGENT_SCHEMA)

        explicit = yaml.safe_load(
            (AGENTS_DIR / "fta_agent" / "agent.yaml").read_text(encoding="utf-8")
        )
        explicit["execution"] = {
            "adapter": "jerryagent_sidecar",
            "contract_version": "flai.agent-layer.v1",
        }
        validate(explicit, AGENT_SCHEMA)

        invalid_execution_blocks = (
            {"adapter": "jerryagent_sidecar"},
            {"contract_version": "flai.agent-layer.v1"},
            {
                "adapter": "unknown_adapter",
                "contract_version": "flai.agent-layer.v1",
            },
            {
                "adapter": "native_python",
                "contract_version": "unknown.contract.v1",
            },
            {
                "adapter": "jerryagent_sidecar",
                "contract_version": "flai.agent-layer.v1",
                "silent_fallback": True,
            },
        )
        for execution in invalid_execution_blocks:
            explicit["execution"] = execution
            with pytest.raises(ValidationError):
                validate(explicit, AGENT_SCHEMA)

    def test_registry_normalizes_absent_execution_to_native(self, tmp_path: Path) -> None:
        agents_dir, _ = _copy_agent(tmp_path, "hello_agent")

        registry = _scan(agents_dir)

        assert registry.errors == []
        assert registry.get("hello_agent")["execution"] == {
            "adapter": "native_python",
            "contract_version": "native.workflow.v1",
        }

    @pytest.mark.parametrize(
        ("adapter", "contract_version", "accepted"),
        [
            ("native_python", "native.workflow.v1", True),
            ("jerryagent_sidecar", "flai.agent-layer.v1", True),
            ("native_python", "flai.agent-layer.v1", False),
            ("jerryagent_sidecar", "native.workflow.v1", False),
        ],
    )
    def test_registry_requires_exact_adapter_contract_pair(
        self,
        tmp_path: Path,
        adapter: str,
        contract_version: str,
        accepted: bool,
    ) -> None:
        agents_dir, package_dir = _copy_agent(tmp_path)
        manifest = _manifest(package_dir)
        manifest["execution"] = {
            "adapter": adapter,
            "contract_version": contract_version,
        }
        manifest["logging"]["save_model_calls"] = False
        manifest["logging"]["save_tool_logs"] = False
        _write_manifest(package_dir, manifest)

        registry = _scan(agents_dir)

        assert (registry.get("fta_agent") is not None) is accepted
        if accepted:
            assert registry.errors == []
        else:
            assert len(registry.errors) == 1
            assert "execution." in registry.errors[0]["error"]

    @pytest.mark.parametrize(
        ("invalid_case", "expected_detail"),
        [
            ("interactive", "workflow.mode=job"),
            ("no_review", "requires_human_review=True"),
            ("no_model", "model.profile"),
            ("tools", "tools=[]"),
            ("knowledge", "knowledge.enabled"),
            ("released", "status"),
            ("model_call_ledger_claim", "logging.save_model_calls=False"),
            ("tool_log_ledger_claim", "logging.save_tool_logs=False"),
        ],
    )
    def test_registry_rejects_unsafe_jerry_combinations(
        self,
        tmp_path: Path,
        invalid_case: str,
        expected_detail: str,
    ) -> None:
        agents_dir, package_dir = _copy_agent(tmp_path)
        manifest = _manifest(package_dir)
        manifest["execution"] = {
            "adapter": "jerryagent_sidecar",
            "contract_version": "flai.agent-layer.v1",
        }
        manifest["logging"]["save_model_calls"] = False
        manifest["logging"]["save_tool_logs"] = False
        if invalid_case == "interactive":
            manifest["workflow"]["mode"] = "interactive"
        elif invalid_case == "no_review":
            manifest["workflow"]["requires_human_review"] = False
        elif invalid_case == "no_model":
            manifest["model"]["profile"] = "none"
        elif invalid_case == "tools":
            manifest["tools"] = ["mock_echo"]
        elif invalid_case == "knowledge":
            manifest["knowledge"] = {"enabled": True, "scopes": ["engineering"]}
        elif invalid_case == "released":
            manifest["status"] = "released"
            manifest["owner"]["maintainer"] = "maintainer"
            manifest["owner"]["business_reviewer"] = "reviewer"
        elif invalid_case == "model_call_ledger_claim":
            manifest["logging"]["save_model_calls"] = True
        elif invalid_case == "tool_log_ledger_claim":
            manifest["logging"]["save_tool_logs"] = True
        _write_manifest(package_dir, manifest)

        registry = _scan(agents_dir)

        assert registry.get("fta_agent") is None
        assert len(registry.errors) == 1
        assert expected_detail in registry.errors[0]["error"]


_LEGACY_TASKS_DDL = """
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    agent_version TEXT NOT NULL,
    name TEXT,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    input_file_ids TEXT NOT NULL DEFAULT '[]',
    output_file_ids TEXT NOT NULL DEFAULT '[]',
    inputs_json TEXT NOT NULL DEFAULT '{}',
    error_message TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    conversation_id TEXT,
    origin TEXT NOT NULL DEFAULT 'user',
    data_classification TEXT
)
"""


def _create_repo_task(
    conn: sqlite3.Connection,
    task_id: str,
    **overrides: Any,
) -> dict[str, Any]:
    values = {
        "task_id": task_id,
        "agent_id": "hello_agent",
        "agent_version": "0.1.0",
        "name": "execution binding",
        "created_by": "tester",
    }
    values.update(overrides)
    return repos.create_task(conn, **values)


def _assert_binding_columns_are_strict(conn: sqlite3.Connection) -> None:
    columns = {
        str(row[1]): row for row in conn.execute("PRAGMA table_info(tasks)")
    }
    assert columns["execution_adapter"][2:] == (
        "TEXT",
        1,
        "'native_python'",
        0,
    )
    assert columns["execution_contract_version"][2:] == (
        "TEXT",
        1,
        "'native.workflow.v1'",
        0,
    )


@pytest.mark.parametrize(
    "column",
    ["execution_adapter", "execution_contract_version"],
)
def test_fresh_task_execution_binding_is_persisted_and_immutable(
    tmp_path: Path,
    column: str,
) -> None:
    db_path = tmp_path / "fresh.db"
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        _assert_binding_columns_are_strict(conn)
        native = _create_repo_task(conn, "native-task")
        assert native["execution_adapter"] == "native_python"
        assert native["execution_contract_version"] == "native.workflow.v1"

        jerry = _create_repo_task(
            conn,
            "jerry-task",
            execution_adapter="jerryagent_sidecar",
            execution_contract_version="flai.agent-layer.v1",
        )
        assert jerry["execution_adapter"] == "jerryagent_sidecar"
        assert jerry["execution_contract_version"] == "flai.agent-layer.v1"

        with pytest.raises(sqlite3.IntegrityError, match="execution binding is immutable"):
            conn.execute(
                f"UPDATE tasks SET {column} = {column} WHERE id = ?",
                (jerry["id"],),
            )
        with pytest.raises(sqlite3.IntegrityError, match="must be an exact pair"):
            conn.execute(
                """
                INSERT INTO tasks (
                    id, agent_id, agent_version, name, status, created_by,
                    created_at, updated_at, execution_adapter,
                    execution_contract_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "invalid-binding",
                    "hello_agent",
                    "0.1.0",
                    "invalid",
                    "created",
                    "tester",
                    "2026-07-20T00:00:00+00:00",
                    "2026-07-20T00:00:00+00:00",
                    "native_python",
                    "flai.agent-layer.v1",
                ),
            )
    finally:
        conn.close()


def test_legacy_task_execution_binding_migrates_truthfully_to_native(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "legacy.db"
    legacy = db_mod.get_conn(db_path)
    try:
        legacy.execute(_LEGACY_TASKS_DDL)
        legacy.execute(
            "INSERT INTO tasks "
            "(id, agent_id, agent_version, name, status, created_by, created_at, updated_at) "
            "VALUES ('legacy-task', 'hello_agent', '0.1.0', 'legacy', 'queued', "
            "'historical-user', '2026-01-01T00:00:00+00:00', "
            "'2026-01-01T00:00:00+00:00')"
        )
    finally:
        legacy.close()

    db_mod.init_db(db_path)
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        _assert_binding_columns_are_strict(conn)
        task = repos.get_task(conn, "legacy-task")
        assert task["execution_adapter"] == "native_python"
        assert task["execution_contract_version"] == "native.workflow.v1"
        with pytest.raises(sqlite3.IntegrityError, match="execution binding is immutable"):
            conn.execute(
                "UPDATE tasks SET execution_adapter = 'jerryagent_sidecar' "
                "WHERE id = 'legacy-task'"
            )
    finally:
        conn.close()


def test_existing_execution_binding_evidence_refuses_missing_immutable_guard(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "missing-guard.db"
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        _create_repo_task(conn, "guarded-task")
        conn.execute("DROP TRIGGER trg_tasks_execution_binding_immutable")
    finally:
        conn.close()

    with pytest.raises(
        sqlite3.IntegrityError,
        match="execution binding schema witness failed",
    ):
        db_mod.init_db(db_path)


def test_execution_binding_migration_refuses_partial_column_residue(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "partial-binding.db"
    conn = db_mod.get_conn(db_path)
    try:
        conn.execute(_LEGACY_TASKS_DDL)
        conn.execute(
            "ALTER TABLE tasks ADD COLUMN execution_adapter "
            "TEXT NOT NULL DEFAULT 'native_python'"
        )
    finally:
        conn.close()

    with pytest.raises(sqlite3.IntegrityError, match="column residue"):
        db_mod.init_db(db_path)


def test_execution_binding_migration_refuses_persisted_null_binding(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "null-binding.db"
    conn = db_mod.get_conn(db_path)
    try:
        conn.execute(_LEGACY_TASKS_DDL)
        conn.execute("ALTER TABLE tasks ADD COLUMN execution_adapter TEXT")
        conn.execute("ALTER TABLE tasks ADD COLUMN execution_contract_version TEXT")
        conn.execute(
            "INSERT INTO tasks "
            "(id, agent_id, agent_version, status, created_by, created_at, updated_at) "
            "VALUES ('null-binding', 'hello_agent', '0.1.0', 'queued', 'tester', "
            "'2026-07-20T00:00:00+00:00', '2026-07-20T00:00:00+00:00')"
        )
    finally:
        conn.close()

    with pytest.raises(
        sqlite3.IntegrityError,
        match="execution binding schema witness failed",
    ):
        db_mod.init_db(db_path)


def test_task_schema_requires_an_exact_execution_binding_pair() -> None:
    base = {
        "id": "task-contract",
        "agent_id": "hello_agent",
        "agent_version": "0.1.0",
        "status": "queued",
        "created_by": "tester",
        "created_at": "2026-07-20T00:00:00+00:00",
    }
    native = {
        **base,
        "execution_adapter": "native_python",
        "execution_contract_version": "native.workflow.v1",
    }
    jerry = {
        **base,
        "execution_adapter": "jerryagent_sidecar",
        "execution_contract_version": "flai.agent-layer.v1",
    }
    validate(native, TASK_SCHEMA)
    validate(jerry, TASK_SCHEMA)

    invalid_bindings = (
        {key: value for key, value in native.items() if key != "execution_adapter"},
        {
            key: value
            for key, value in native.items()
            if key != "execution_contract_version"
        },
        {**native, "execution_contract_version": "flai.agent-layer.v1"},
        {**jerry, "execution_contract_version": "native.workflow.v1"},
    )
    for invalid in invalid_bindings:
        with pytest.raises(ValidationError):
            validate(invalid, TASK_SCHEMA)


@pytest.fixture()
def execution_binding_client(app_env, tmp_path: Path):
    client, app = app_env
    agents_dir = tmp_path / "execution-agents"
    agents_dir.mkdir()
    shutil.copytree(AGENTS_DIR / "hello_agent", agents_dir / "hello_agent")
    shutil.copytree(AGENTS_DIR / "fta_agent", agents_dir / "fta_agent")
    fta_package = agents_dir / "fta_agent"
    fta = _manifest(fta_package)
    fta["execution"] = {
        "adapter": "jerryagent_sidecar",
        "contract_version": "flai.agent-layer.v1",
    }
    fta["logging"]["save_model_calls"] = False
    fta["logging"]["save_tool_logs"] = False
    _write_manifest(fta_package, fta)
    registry = _scan(agents_dir)
    assert registry.errors == []

    original_registry = app.state.agent_registry
    app.state.agent_registry = registry
    try:
        yield client, app
    finally:
        app.state.agent_registry = original_registry


def _task_created_payload(client: TestClient, task_id: str) -> dict[str, Any]:
    response = client.get(f"/api/tasks/{task_id}/events")
    assert response.status_code == 200
    return next(
        event["payload"]
        for event in response.json()
        if event["event_type"] == "task_created"
    )


class TestTaskExecutionBindingAPI:
    def test_single_create_freezes_jerry_binding_and_emits_it(
        self,
        execution_binding_client,
    ) -> None:
        client, app = execution_binding_client

        response = client.post(
            "/api/tasks",
            json={"agent_id": "fta_agent", "inputs": {"top_event": "loss"}},
        )

        assert response.status_code == 200, response.text
        task = response.json()
        assert task["execution_adapter"] == "jerryagent_sidecar"
        assert task["execution_contract_version"] == "flai.agent-layer.v1"
        payload = _task_created_payload(client, task["id"])
        assert payload["execution_adapter"] == "jerryagent_sidecar"
        assert payload["execution_contract_version"] == "flai.agent-layer.v1"

        # Registry is live configuration; the persisted task remains frozen.
        app.state.agent_registry.get("fta_agent")["execution"] = {
            "adapter": "native_python",
            "contract_version": "native.workflow.v1",
        }
        readback = client.get(f"/api/tasks/{task['id']}")
        assert readback.status_code == 200
        assert readback.json()["execution_adapter"] == "jerryagent_sidecar"
        assert readback.json()["execution_contract_version"] == "flai.agent-layer.v1"

    def test_batch_create_freezes_each_manifest_binding_and_emits_it(
        self,
        execution_binding_client,
    ) -> None:
        client, _ = execution_binding_client

        response = client.post(
            "/api/tasks/batch",
            json={
                "items": [
                    {"agent_id": "hello_agent", "inputs": {"name": "native"}},
                    {"agent_id": "fta_agent", "inputs": {"top_event": "jerry"}},
                ]
            },
        )

        assert response.status_code == 200, response.text
        native, jerry = response.json()["tasks"]
        assert (
            native["execution_adapter"],
            native["execution_contract_version"],
        ) == ("native_python", "native.workflow.v1")
        assert (
            jerry["execution_adapter"],
            jerry["execution_contract_version"],
        ) == ("jerryagent_sidecar", "flai.agent-layer.v1")
        for task in (native, jerry):
            payload = _task_created_payload(client, task["id"])
            assert payload["execution_adapter"] == task["execution_adapter"]
            assert (
                payload["execution_contract_version"]
                == task["execution_contract_version"]
            )

    def test_execution_binding_is_read_only_response_projection(
        self,
        execution_binding_client,
    ) -> None:
        client, _ = execution_binding_client
        adapter_schema = TASK_SCHEMA["properties"]["execution_adapter"]
        contract_schema = TASK_SCHEMA["properties"]["execution_contract_version"]
        assert adapter_schema["readOnly"] is True
        assert contract_schema["readOnly"] is True

        response = client.post(
            "/api/tasks",
            json={"agent_id": "hello_agent", "execution_adapter": "jerryagent_sidecar"},
        )
        assert response.status_code == 422
        batch_response = client.post(
            "/api/tasks/batch",
            json={
                "items": [
                    {
                        "agent_id": "hello_agent",
                        "execution": {
                            "adapter": "jerryagent_sidecar",
                            "contract_version": "flai.agent-layer.v1",
                        },
                    }
                ]
            },
        )
        assert batch_response.status_code == 422

        valid_response = client.post(
            "/api/tasks",
            json={"agent_id": "hello_agent", "inputs": {"name": "contract"}},
        )
        assert valid_response.status_code == 200
        validate(valid_response.json(), TASK_SCHEMA)
