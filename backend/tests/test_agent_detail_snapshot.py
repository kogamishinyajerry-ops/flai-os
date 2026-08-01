"""Agent detail responses must come from one immutable package generation."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from backend.app import config
from backend.app.runtime.registry import AgentRegistry


def test_agent_detail_publishes_schema_and_digest_from_one_snapshot(
    app_env,
    tmp_path: Path,
) -> None:
    client, app = app_env
    agents_dir = tmp_path / "snapshot-agents"
    agents_dir.mkdir()
    package_dir = agents_dir / "hello_agent"
    shutil.copytree(config.AGENTS_DIR / "hello_agent", package_dir)

    registry = AgentRegistry(agents_dir, config.CONTRACTS_DIR / "agent.schema.json")
    registry.scan()
    first_snapshot = registry.package_snapshot("hello_agent")
    assert first_snapshot is not None
    app.state.agent_registry = registry

    first_response = client.get("/api/agents/hello_agent")
    assert first_response.status_code == 200, first_response.text
    first = first_response.json()
    first_schema = first["input_schema"]

    schema_path = package_dir / "input_schema.json"
    changed_schema = json.loads(schema_path.read_text(encoding="utf-8"))
    changed_schema["properties"]["generation_marker"] = {"type": "string"}
    changed_schema["required"].append("generation_marker")
    schema_path.write_text(
        json.dumps(changed_schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    unpublished_response = client.get("/api/agents/hello_agent")
    assert unpublished_response.status_code == 200, unpublished_response.text
    unpublished = unpublished_response.json()
    assert unpublished["version"] == first["version"]
    assert unpublished["input_schema"] == first_schema
    assert unpublished["package_snapshot_digest"] == first_snapshot.digest

    registry.scan()
    second_snapshot = registry.package_snapshot("hello_agent")
    assert second_snapshot is not None
    assert second_snapshot.digest != first_snapshot.digest

    published_response = client.get("/api/agents/hello_agent")
    assert published_response.status_code == 200, published_response.text
    published = published_response.json()
    assert published["version"] == second_snapshot.manifest["version"] == first["version"]
    assert published["input_schema"] == changed_schema
    assert published["package_snapshot_digest"] == second_snapshot.digest
    assert published["package_snapshot_digest"] != unpublished["package_snapshot_digest"]


def test_agent_detail_uses_manifest_named_input_schema_from_one_snapshot(
    app_env,
    tmp_path: Path,
) -> None:
    client, app = app_env
    agents_dir = tmp_path / "custom-schema-agents"
    agents_dir.mkdir()
    package_dir = agents_dir / "hello_agent"
    shutil.copytree(config.AGENTS_DIR / "hello_agent", package_dir)

    default_schema_path = package_dir / "input_schema.json"
    custom_schema_path = package_dir / "custom_input.json"
    custom_schema = json.loads(default_schema_path.read_text(encoding="utf-8"))
    custom_schema["description"] = "custom schema generation one"
    custom_schema_path.write_text(
        json.dumps(custom_schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest_path = package_dir / "agent.yaml"
    manifest_text = manifest_path.read_text(encoding="utf-8").replace(
        "schema: input_schema.json",
        "schema: custom_input.json",
        1,
    )
    assert "schema: custom_input.json" in manifest_text
    manifest_path.write_text(manifest_text, encoding="utf-8")

    registry = AgentRegistry(agents_dir, config.CONTRACTS_DIR / "agent.schema.json")
    registry.scan()
    first_snapshot = registry.package_snapshot("hello_agent")
    assert first_snapshot is not None
    app.state.agent_registry = registry

    first_response = client.get("/api/agents/hello_agent")
    assert first_response.status_code == 200, first_response.text
    first = first_response.json()
    assert first["input_schema"] == custom_schema
    assert first["package_snapshot_digest"] == first_snapshot.digest

    changed_schema = {**custom_schema, "description": "custom schema generation two"}
    custom_schema_path.write_text(
        json.dumps(changed_schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    unpublished_response = client.get("/api/agents/hello_agent")
    assert unpublished_response.status_code == 200, unpublished_response.text
    unpublished = unpublished_response.json()
    assert unpublished["input_schema"] == custom_schema
    assert unpublished["package_snapshot_digest"] == first_snapshot.digest

    registry.scan()
    second_snapshot = registry.package_snapshot("hello_agent")
    assert second_snapshot is not None
    assert second_snapshot.digest != first_snapshot.digest

    published_response = client.get("/api/agents/hello_agent")
    assert published_response.status_code == 200, published_response.text
    published = published_response.json()
    assert published["input_schema"] == changed_schema
    assert published["package_snapshot_digest"] == second_snapshot.digest
