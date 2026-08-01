from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import Barrier, Lock
from time import sleep
from typing import Any

import pytest
from jsonschema import validate

from backend.app.ontology.agent_shell import AgentShellCatalog, AgentShellProjectionError
from backend.app.runtime.package_snapshot import AgentPackageSnapshot


def _package_snapshot(
    manifest: dict[str, Any],
    *,
    files: dict[str, bytes] | None = None,
    digest: str = "a" * 64,
) -> AgentPackageSnapshot:
    payloads = {
        "agent.yaml": b"id: ignored-by-catalog\n",
        **(files or {}),
    }
    return AgentPackageSnapshot(
        digest=digest,
        manifest_json=json.dumps(manifest, ensure_ascii=False, sort_keys=True),
        directories=(),
        files=tuple(sorted(payloads.items())),
    )


class _SnapshotView:
    def __init__(self, snapshots: dict[str, AgentPackageSnapshot]) -> None:
        self._snapshots = dict(snapshots)

    def __enter__(self) -> _SnapshotView:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def list(self) -> list[dict[str, Any]]:
        return [snapshot.manifest for snapshot in self._snapshots.values()]

    def package_snapshot(self, agent_id: str) -> AgentPackageSnapshot | None:
        return self._snapshots.get(agent_id)


class _AgentRegistry:
    def __init__(self, snapshots: dict[str, AgentPackageSnapshot]) -> None:
        self._snapshots = dict(snapshots)
        self.snapshot_view_calls = 0

    def snapshot_view(self) -> _SnapshotView:
        self.snapshot_view_calls += 1
        return _SnapshotView(self._snapshots)


@dataclass
class _ListRegistry:
    items: list[dict[str, Any]]

    def list(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self.items)


def _manifest(**overrides: Any) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "id": "alpha_agent",
        "name": "Alpha Agent",
        "version": "1.2.3",
        "status": "trial",
        "maturity": "L2",
        "category": "reasoning_assist",
        "summary": "用于测试的 Agent",
        "expertise": {
            "domain": "generic",
            "specialty": "结构化决策辅助",
            "usefulness_level": "L2",
        },
        "input": {"type": "params", "schema": "schemas/custom-input.json"},
        "output": {"formats": [".json"], "schema": "output_schema.json"},
        "tools": ["known_tool", "missing_tool"],
        "knowledge": {"enabled": True, "scopes": ["known_scope", "missing_scope"]},
        "workflow": {"mode": "job", "requires_human_review": True},
        "permissions": {
            "visibility": "department_trial",
            "allowed_roles": ["agent_developer", "business_user"],
        },
        "clearance": {"max_data_classification": "sensitive"},
        "evidence_policy": {"required": True, "kinds": ["calculation"]},
        "limitations": ["必须由工程师复核"],
    }
    manifest.update(overrides)
    return manifest


def _catalog(
    manifest: dict[str, Any],
    *,
    files: dict[str, bytes] | None = None,
    tools: list[dict[str, Any]] | None = None,
    scopes: list[dict[str, Any]] | None = None,
) -> tuple[AgentShellCatalog, _AgentRegistry]:
    registry = _AgentRegistry({manifest["id"]: _package_snapshot(manifest, files=files)})
    catalog = AgentShellCatalog(
        registry,
        _ListRegistry(tools or []),
        _ListRegistry(scopes or []),
    )
    return catalog, registry


def _diagnostic_states(snapshot: dict[str, Any]) -> set[tuple[str, str, str]]:
    return {
        (item["agent_id"], item["field"], item["state"])
        for item in snapshot["diagnostics"]
    }


def test_snapshot_projects_resolved_and_unresolved_refs_without_authority_claims() -> None:
    manifest = _manifest()
    catalog, registry = _catalog(
        manifest,
        files={
            "schemas/custom-input.json": json.dumps(
                {
                    "type": "object",
                    "properties": {"question": {"type": "string"}, "limit": {"type": "integer"}},
                    "required": ["question"],
                }
            ).encode(),
            "output_schema.json": json.dumps(
                {"type": "object", "properties": {"answer": {"type": "string"}}}
            ).encode(),
        },
        tools=[
            {
                "id": "known_tool",
                "name": "Known Tool",
                "version": "2.0.0",
                "mock": True,
                "output_classification": "internal",
            }
        ],
        scopes=[
            {
                "scope_id": "known_scope",
                "name": "Known Scope",
                "kind": "document",
                "confidentiality": "department",
            }
        ],
    )

    snapshot = catalog.snapshot()

    assert registry.snapshot_view_calls == 1
    assert snapshot["schema_version"] == "agent_shell.v1"
    assert snapshot["source"] == {"kind": "registry_snapshot", "read_only": True}
    assert snapshot["summary"] == {
        "agent_count": 1,
        "work_type_count": 1,
        "domain_count": 1,
        "unresolved_reference_count": 2,
        "defaulted_clearance_count": 0,
        "mock_tool_reference_count": 1,
    }
    agent = snapshot["agents"][0]
    assert agent["identity"] == {
        "agent_id": "alpha_agent",
        "name": "Alpha Agent",
        "version": "1.2.3",
        "summary": "用于测试的 Agent",
    }
    assert agent["launch"] == {"kind": "task"}
    assert agent["capability"]["input"]["schema"] == {
        "state": "available",
        "reason": None,
        "filename": "schemas/custom-input.json",
        "property_count": 2,
        "required_count": 1,
    }
    assert agent["capability"]["tools"] == [
        {
            "id": "known_tool",
            "name": "Known Tool",
            "version": "2.0.0",
            "state": "resolved",
            "mock": True,
            "output_classification": "internal",
        },
        {
            "id": "missing_tool",
            "name": None,
            "version": None,
            "state": "unresolved",
            "mock": None,
            "output_classification": None,
        },
    ]
    assert agent["capability"]["knowledge_scopes"][1] == {
        "id": "missing_scope",
        "name": None,
        "kind": None,
        "confidentiality": None,
        "state": "unresolved",
    }
    states = _diagnostic_states(snapshot)
    assert ("alpha_agent", "capability.tools.missing_tool", "unresolved") in states
    assert ("alpha_agent", "capability.knowledge_scopes.missing_scope", "unresolved") in states
    assert "can_launch" not in json.dumps(snapshot)
    assert "available" not in agent["launch"]


def test_unknown_values_default_clearance_and_preserve_literal_boolean_semantics() -> None:
    manifest = _manifest(
        workflow={"mode": "future_mode", "requires_human_review": "yes"},
        clearance={"max_data_classification": "secret"},
        evidence_policy={"required": 1, "kinds": ["calculation"]},
        tools=["bad_mock_tool"],
    )
    catalog, _ = _catalog(
        manifest,
        tools=[
            {
                "id": "bad_mock_tool",
                "name": "Bad Mock",
                "version": "1.0.0",
                "mock": "true",
                "output_classification": "internal",
            }
        ],
    )

    snapshot = catalog.snapshot()
    agent = snapshot["agents"][0]

    assert agent["launch"]["kind"] == "unknown"
    assert agent["trust"]["clearance"] == {
        "effective": "internal",
        "source": "invalid_defaulted",
    }
    assert agent["trust"]["requires_human_review"] is None
    assert agent["trust"]["evidence"]["required"] is None
    assert agent["capability"]["tools"][0]["mock"] is None
    states = _diagnostic_states(snapshot)
    assert ("alpha_agent", "launch.kind", "invalid") in states
    assert ("alpha_agent", "trust.clearance", "invalid_defaulted") in states
    assert ("alpha_agent", "trust.requires_human_review", "invalid_boolean") in states
    assert ("alpha_agent", "trust.evidence.required", "invalid_boolean") in states
    assert ("alpha_agent", "capability.tools.bad_mock_tool.mock", "invalid_boolean") in states
    assert snapshot["summary"]["defaulted_clearance_count"] == 1
    assert snapshot["summary"]["mock_tool_reference_count"] == 0


def test_literal_false_review_evidence_and_mock_values_remain_false() -> None:
    manifest = _manifest(
        workflow={"mode": "job", "requires_human_review": False},
        evidence_policy={"required": False},
        tools=["real_tool"],
    )
    catalog, _ = _catalog(
        manifest,
        tools=[
            {
                "id": "real_tool",
                "name": "Real Tool",
                "version": "1.0.0",
                "mock": False,
                "output_classification": "internal",
            }
        ],
    )

    snapshot = catalog.snapshot()
    agent = snapshot["agents"][0]

    assert agent["trust"]["requires_human_review"] is False
    assert agent["trust"]["evidence"]["required"] is False
    assert agent["capability"]["tools"][0]["mock"] is False
    assert snapshot["summary"]["mock_tool_reference_count"] == 0


def test_missing_clearance_defaults_internal_and_missing_schema_is_explicit() -> None:
    manifest = _manifest()
    manifest.pop("clearance")
    manifest["input"] = {"type": "none"}
    manifest["output"] = {}
    catalog, _ = _catalog(manifest)

    snapshot = catalog.snapshot()
    agent = snapshot["agents"][0]

    assert agent["trust"]["clearance"] == {
        "effective": "internal",
        "source": "defaulted",
    }
    assert agent["capability"]["input"]["schema"] == {
        "state": "unavailable",
        "reason": "file_missing",
        "filename": "input_schema.json",
        "property_count": 0,
        "required_count": 0,
    }
    assert ("alpha_agent", "trust.clearance", "defaulted") in _diagnostic_states(snapshot)


def test_schema_filename_is_read_only_from_snapshot_and_unsafe_path_is_not_read() -> None:
    manifest = _manifest(input={"type": "params", "schema": "../secret.json"})
    catalog, _ = _catalog(
        manifest,
        files={
            "secret.json": b'{"type":"object","properties":{"leak":{"type":"string"}}}',
            "output_schema.json": b'{"type":"object"}',
        },
    )

    snapshot = catalog.snapshot()
    schema = snapshot["agents"][0]["capability"]["input"]["schema"]

    assert schema == {
        "state": "unavailable",
        "reason": "unsafe_filename",
        "filename": "../secret.json",
        "property_count": 0,
        "required_count": 0,
    }
    assert (
        "alpha_agent",
        "capability.input.schema",
        "unsafe_filename",
    ) in _diagnostic_states(snapshot)


def test_schema_projection_is_bounded_and_cached_diagnostics_remain_deterministic(
    monkeypatch,
) -> None:
    invalid_schema = b'{"type":"object","properties":{"value":{}},"required":[]}'
    original_loads = json.loads

    def loads_with_plain_value_error(value: Any, *args: Any, **kwargs: Any) -> Any:
        if value == invalid_schema.decode("utf-8"):
            raise ValueError("deterministic non-JSONDecodeError parser failure")
        return original_loads(value, *args, **kwargs)

    monkeypatch.setattr(json, "loads", loads_with_plain_value_error)
    manifest = _manifest()
    catalog, _ = _catalog(
        manifest,
        files={
            "schemas/custom-input.json": invalid_schema,
            "output_schema.json": b"{}" + (b" " * (512 * 1024)),
        },
    )

    first = catalog.snapshot()
    second = catalog.snapshot()

    assert second == first
    agent = first["agents"][0]
    assert agent["capability"]["input"]["schema"]["reason"] == "invalid_json"
    assert agent["capability"]["output"]["schema"]["reason"] == "file_too_large"
    states = _diagnostic_states(first)
    assert ("alpha_agent", "capability.input.schema", "invalid_json") in states
    assert ("alpha_agent", "capability.output.schema", "file_too_large") in states


def test_schema_cache_single_flights_concurrent_cold_reads(monkeypatch) -> None:
    schema_text = '{"type":"object","properties":{"value":{}},"required":[]}'
    original_loads = json.loads
    counter_lock = Lock()
    parse_count = 0

    def counted_loads(value: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal parse_count
        if value == schema_text:
            with counter_lock:
                parse_count += 1
            sleep(0.02)
        return original_loads(value, *args, **kwargs)

    monkeypatch.setattr(json, "loads", counted_loads)
    manifest = _manifest(output={"formats": [".json"], "schema": "missing.json"})
    catalog, _ = _catalog(
        manifest,
        files={"schemas/custom-input.json": schema_text.encode("utf-8")},
    )
    barrier = Barrier(8)

    def take_snapshot() -> dict[str, Any]:
        barrier.wait()
        return catalog.snapshot()

    with ThreadPoolExecutor(max_workers=8) as executor:
        snapshots = list(executor.map(lambda _index: take_snapshot(), range(8)))

    assert all(snapshot == snapshots[0] for snapshot in snapshots)
    assert parse_count == 1


def test_schema_cache_keeps_normal_multi_agent_catalog_hot(monkeypatch) -> None:
    schema_text = '{"type":"object","properties":{"value":{}},"required":[]}'
    original_loads = json.loads
    parse_count = 0

    def counted_loads(value: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal parse_count
        if value == schema_text:
            parse_count += 1
        return original_loads(value, *args, **kwargs)

    monkeypatch.setattr(json, "loads", counted_loads)
    snapshots: dict[str, AgentPackageSnapshot] = {}
    for index in range(129):
        agent_id = f"agent_{index:03d}"
        manifest = _manifest(
            id=agent_id,
            tools=[],
            knowledge={"enabled": False, "scopes": []},
        )
        snapshots[agent_id] = _package_snapshot(
            manifest,
            digest=f"{index + 1:064x}",
            files={
                "schemas/custom-input.json": schema_text.encode("utf-8"),
                "output_schema.json": schema_text.encode("utf-8"),
            },
        )
    catalog = AgentShellCatalog(_AgentRegistry(snapshots), _ListRegistry([]), _ListRegistry([]))

    first = catalog.snapshot()
    first_parse_count = parse_count
    second = catalog.snapshot()

    assert second == first
    assert first_parse_count == 258
    assert parse_count == first_parse_count


@pytest.mark.parametrize("enabled", [False, "true", 1])
def test_disabled_knowledge_never_projects_declared_scope_references(enabled: Any) -> None:
    manifest = _manifest(knowledge={"enabled": enabled, "scopes": ["known_scope"]})
    catalog, _ = _catalog(
        manifest,
        scopes=[
            {
                "scope_id": "known_scope",
                "name": "Known Scope",
                "kind": "document",
                "confidentiality": "department",
            }
        ],
    )

    snapshot = catalog.snapshot()

    assert snapshot["agents"][0]["capability"]["knowledge_scopes"] == []
    assert (
        "alpha_agent",
        "capability.knowledge_scopes",
        "disabled_not_projected",
    ) in _diagnostic_states(snapshot)


def test_invalid_utf8_registry_text_is_redacted_before_json_serialization() -> None:
    manifest = _manifest(tools=["known_tool"])
    catalog, _ = _catalog(
        manifest,
        tools=[
            {
                "id": "known_tool",
                "name": "\ud800",
                "version": "1.0.0",
                "mock": False,
                "output_classification": "internal",
            }
        ],
    )

    snapshot = catalog.snapshot()

    assert snapshot["agents"][0]["capability"]["tools"][0]["name"] is None
    assert (
        "alpha_agent",
        "capability.tools.known_tool.name",
        "invalid_utf8",
    ) in _diagnostic_states(snapshot)
    json.dumps(snapshot, ensure_ascii=False).encode("utf-8")


def test_invalid_utf8_schema_filename_is_redacted_before_json_serialization() -> None:
    manifest = _manifest(input={"type": "params", "schema": "\ud800"})
    catalog, _ = _catalog(manifest)

    snapshot = catalog.snapshot()

    assert snapshot["agents"][0]["capability"]["input"]["schema"] == {
        "state": "unavailable",
        "reason": "invalid_utf8",
        "filename": None,
        "property_count": 0,
        "required_count": 0,
    }
    json.dumps(snapshot, ensure_ascii=False).encode("utf-8")


def test_registry_access_failure_is_fail_closed() -> None:
    class BrokenAgentRegistry:
        def snapshot_view(self) -> Any:
            raise RuntimeError("registry offline")

    catalog = AgentShellCatalog(BrokenAgentRegistry(), _ListRegistry([]), _ListRegistry([]))

    with pytest.raises(AgentShellProjectionError, match="Agent Registry snapshot"):
        catalog.snapshot()


@pytest.mark.parametrize("raw_agents", [[None], ["bad"]])
def test_malformed_agent_registry_item_returns_generic_503(
    app_env: tuple[Any, Any], raw_agents: list[Any]
) -> None:
    client, app = app_env

    class MalformedSnapshotView:
        def __enter__(self) -> MalformedSnapshotView:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def list(self) -> list[Any]:
            return copy.deepcopy(raw_agents)

        def package_snapshot(self, _agent_id: str) -> AgentPackageSnapshot | None:
            raise AssertionError("malformed registry items must fail before package lookup")

    class MalformedAgentRegistry:
        def snapshot_view(self) -> MalformedSnapshotView:
            return MalformedSnapshotView()

    app.state.agent_shell_catalog = AgentShellCatalog(
        MalformedAgentRegistry(),
        _ListRegistry([]),
        _ListRegistry([]),
    )

    response = client.get("/api/agent-shell")

    assert response.status_code == 503
    assert response.json() == {"detail": "Agent 本体投影不可用"}


def test_related_registry_access_failure_is_fail_closed() -> None:
    class BrokenListRegistry:
        def list(self) -> list[dict[str, Any]]:
            raise RuntimeError("tool registry offline")

    manifest = _manifest()
    agent_registry = _AgentRegistry({manifest["id"]: _package_snapshot(manifest)})
    catalog = AgentShellCatalog(agent_registry, BrokenListRegistry(), _ListRegistry([]))

    with pytest.raises(AgentShellProjectionError, match="Registry 'id' is unavailable"):
        catalog.snapshot()


def test_snapshot_is_deterministic_and_detached_from_registry_mutation() -> None:
    zeta = _manifest(id="zeta_agent", name="Zeta")
    alpha = _manifest(
        id="alpha_agent",
        name="Alpha",
        workflow={"mode": "interactive", "requires_human_review": False},
    )
    registry = _AgentRegistry(
        {
            "zeta_agent": _package_snapshot(zeta),
            "alpha_agent": _package_snapshot(alpha),
        }
    )
    tools = _ListRegistry([])
    scopes = _ListRegistry([])
    catalog = AgentShellCatalog(registry, tools, scopes)

    first = catalog.snapshot()
    first["agents"][0]["identity"]["name"] = "mutated response"
    registry._snapshots["alpha_agent"] = _package_snapshot(
        _manifest(
            id="alpha_agent",
            name="Later",
            workflow={"mode": "interactive", "requires_human_review": False},
        )
    )
    second = catalog.snapshot()

    assert [a["identity"]["agent_id"] for a in second["agents"]] == ["alpha_agent", "zeta_agent"]
    assert second["agents"][0]["identity"]["name"] == "Later"
    assert registry.snapshot_view_calls == 2
    assert second["facets"]["launch_kinds"] == [
        {
            "id": "task",
            "total_count": 1,
            "task_count": 1,
            "conversation_count": 0,
            "unknown_launch_count": 0,
        },
        {
            "id": "conversation",
            "total_count": 1,
            "task_count": 0,
            "conversation_count": 1,
            "unknown_launch_count": 0,
        },
        {
            "id": "unknown",
            "total_count": 0,
            "task_count": 0,
            "conversation_count": 0,
            "unknown_launch_count": 0,
        },
    ]


def test_snapshot_never_exposes_filesystem_paths_or_full_schema_documents() -> None:
    manifest = _manifest()
    manifest["description"] = "/private/authoring/path must never be projected"
    catalog, _ = _catalog(
        manifest,
        files={
            "schemas/custom-input.json": (
                b'{"type":"object","properties":{"x":{"type":"string",'
                b'"description":"secret full document"}}}'
            ),
            "output_schema.json": b'{"type":"object"}',
        },
    )

    serialized = json.dumps(catalog.snapshot(), ensure_ascii=False)

    assert "/private/authoring/path" not in serialized
    assert "secret full document" not in serialized
    assert "package_dir" not in serialized
    assert "digest" not in serialized


def test_authenticated_api_response_matches_agent_shell_contract(app_env) -> None:
    client, _app = app_env
    response = client.get("/api/agent-shell")

    assert response.status_code == 200
    schema = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "contracts"
            / "agent_shell.schema.json"
        ).read_text(encoding="utf-8")
    )
    validate(response.json(), schema)


def test_agent_shell_api_is_not_anonymous(app_env) -> None:
    client, _app = app_env
    client.cookies.clear()
    response = client.get("/api/agent-shell")

    assert response.status_code == 401


def test_agent_shell_api_returns_503_when_projection_source_is_unavailable(app_env) -> None:
    client, app = app_env

    class BrokenCatalog:
        def snapshot(self) -> dict[str, Any]:
            raise AgentShellProjectionError("registry offline")

    app.state.agent_shell_catalog = BrokenCatalog()

    response = client.get("/api/agent-shell")

    assert response.status_code == 503
    assert response.json() == {"detail": "Agent 本体投影不可用"}
