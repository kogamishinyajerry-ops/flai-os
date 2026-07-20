from __future__ import annotations

import base64
import hashlib
import json
import struct
import zlib
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

from backend.app.config import AGENTS_DIR, CONTRACTS_DIR, TOOLS_DIR
from backend.app.runtime.registry import AgentRegistry
from backend.app.tools.registry import ToolRegistry
from tools_impl.open_design_daemon.client import canonical_json_bytes
from tools_impl.open_design_daemon.service import (
    COMPARISON_SLOTS,
    failed_tool_output,
    response_payload_sha256,
    validate_tool_response,
)
from tools_impl.open_design_fixture.design_reference import (
    SOURCE_PATHS,
    TOKEN_ALLOWLIST,
    TRUST_COLOR_CONSTRAINTS,
    design_reference_package_sha256,
)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _rgb_png(width: int, height: int) -> bytes:
    rows = b"".join(b"\x00" + (b"\x11\x22\x33" * width) for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(rows))
        + _png_chunk(b"IEND", b"")
    )


def _design_reference() -> dict[str, Any]:
    return {
        "schema_version": "flai-design-reference-package/v1",
        "sources": {
            source_id: {"path": path, "sha256": str(index + 1) * 64}
            for index, (source_id, path) in enumerate(SOURCE_PATHS.items())
        },
        "theme": "light",
        "token_allowlist": list(TOKEN_ALLOWLIST),
        "tokens": {token: f"value-{index}" for index, token in enumerate(TOKEN_ALLOWLIST)},
        "trust_color_constraints": dict(TRUST_COLOR_CONSTRAINTS),
    }


def _valid_tool_output() -> dict[str, Any]:
    html = b"<main>safe candidate</main>"
    png = _rgb_png(1440, 900)
    files = [
        {
            "path": "candidate.html",
            "media_type": "text/html",
            "size_bytes": len(html),
            "sha256": _sha256(html),
            "content_base64": base64.b64encode(html).decode("ascii"),
        },
        {
            "path": "previews/default_desktop_light.png",
            "media_type": "image/png",
            "size_bytes": len(png),
            "sha256": _sha256(png),
            "content_base64": base64.b64encode(png).decode("ascii"),
        },
    ]
    file_set_sha256 = _sha256(
        canonical_json_bytes(
            [
                {key: item[key] for key in ("path", "media_type", "size_bytes", "sha256")}
                for item in files
            ]
        )
    )
    project_id = "flai-" + "1" * 32
    run_id = "run-001"
    candidate_id = "odc-" + _sha256(
        f"{project_id}\x00{run_id}\x00{file_set_sha256}".encode()
    )[:32]
    package = _design_reference()
    slot = COMPARISON_SLOTS["default_desktop_light"]
    output: dict[str, Any] = {
        "schema_version": "open-design-daemon-result/v1",
        "status": "success",
        "generator_mode": "loopback_daemon_trial",
        "mock": False,
        "untrusted_generated": True,
        "execution_trust": "untrusted_generated",
        "real_daemon_candidate_captured": True,
        "failure_stage": None,
        "unreconciled_upstream_side_effects_may_exist": False,
        "production_readiness": "trial_not_attested",
        "candidate_only": True,
        "release_effect": "none",
        "human_review_required": True,
        "classification": "sensitive",
        "candidate_id": candidate_id,
        "asset_slot": "agent_activity_indicator",
        "project_id": project_id,
        "run_id": run_id,
        "daemon_binding": {
            "version": "0.9.4",
            "channel": "stable",
            "packaged": True,
            "platform": "darwin",
            "arch": "arm64",
            "agent_id": "claude-code",
            "requested_model_id": "claude-opus-4-1",
            "design_system_id": "flai-os-v1",
            "design_system_sha256": "a" * 64,
            "sandbox_reported": True,
            "design_system_execution_sha256": "d" * 64,
            "model_execution_attested": False,
        },
        "design_reference_package": package,
        "design_reference_package_sha256": design_reference_package_sha256(package),
        "result_package_sha256": "b" * 64,
        "storage": {"kind": "od-owned", "base_dir": None},
        "file_set_sha256": file_set_sha256,
        "files": files,
        "passive_previews": [
            {
                "slot_id": "default_desktop_light",
                "viewport": slot["viewport"],
                "state": slot["state"],
                "theme": slot["theme"],
                "locale": slot["locale"],
                "source": {"path": "candidate.html", "sha256": files[0]["sha256"]},
                "image": {
                    "path": files[1]["path"],
                    "sha256": files[1]["sha256"],
                    "size_bytes": files[1]["size_bytes"],
                    "media_type": "image/png",
                    "width": 1440,
                    "height": 900,
                },
                "passive_preview_scan": {
                    "policy": "flai-passive-png/v1",
                    "passed": True,
                    "active_content_executed": False,
                },
            }
        ],
        "safety_scan": {
            "policy": "flai-open-design-passive-candidate/v1",
            "passed": True,
            "file_count": 2,
            "total_bytes": len(html) + len(png),
            "double_fetch_verified": True,
            "file_list_stable": True,
            "static_policy_screened": True,
            "png_structural_validation": True,
        },
        "response_sha256": "",
        "error_message": None,
    }
    output["response_sha256"] = response_payload_sha256(output)
    validate_tool_response(output)
    return output


class _ToolRegistry:
    def __init__(self, output: dict[str, Any]) -> None:
        self.output = output
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, tool_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((tool_id, inputs))
        return self.output


def _request() -> dict[str, Any]:
    return {
        "schema_version": "open-design-daemon-request/v1",
        "asset_slot": "agent_activity_indicator",
        "comparison_slots": ["default_desktop_light"],
        "interaction_contract": {
            "candidate_only": True,
            "human_review_required": True,
            "release_effect": "none",
            "rendering": "passive_png_only",
        },
    }


def test_tool_and_agent_manifests_register_as_sensitive_mock_false_disabled() -> None:
    tools = ToolRegistry(TOOLS_DIR, CONTRACTS_DIR / "tool.schema.json")
    tools.scan()
    tool = tools.get("open_design_daemon_generate")
    assert tool is not None
    assert tool["mock"] is False
    assert tool["output_classification"] == "sensitive"
    assert tool["runtime"]["retry"] == 0

    agents = AgentRegistry(AGENTS_DIR, CONTRACTS_DIR / "agent.schema.json")
    agents.scan()
    agent = agents.get("open_design_daemon_candidate_agent")
    assert agent is not None
    assert agent["status"] == "disabled"
    assert agent["maturity"] == "L0"
    assert agent["tools"] == ["open_design_daemon_generate"]
    assert agent["workflow"]["requires_human_review"] is True
    assert agent["permissions"]["visibility"] == "admin_only"


def test_failed_progress_witnesses_match_the_published_tool_schema() -> None:
    manifest = yaml.safe_load((TOOLS_DIR / "open_design_daemon" / "tool.yaml").read_text())
    validator = Draft202012Validator(manifest["output_schema"])

    validator.validate(failed_tool_output("disabled", failure_stage="adapter_disabled"))
    validator.validate(
        failed_tool_output(
            "capture failed",
            asset_slot="agent_activity_indicator",
            failure_stage="capture_files",
            project_id="flai-" + "1" * 32,
            run_id="run-001",
            unreconciled_upstream_side_effects_may_exist=True,
        )
    )


def test_disabled_trial_agent_cannot_be_created_through_task_api(app_env) -> None:
    client, _app = app_env
    before = len(client.get("/api/tasks").json())

    response = client.post(
        "/api/tasks",
        json={
            "agent_id": "open_design_daemon_candidate_agent",
            "inputs": _request(),
        },
    )

    assert response.status_code == 409
    assert len(client.get("/api/tasks").json()) == before


def test_agent_input_schema_has_no_free_form_brief_file_or_knowledge_field() -> None:
    schema = json.loads(
        (AGENTS_DIR / "open_design_daemon_candidate_agent/input_schema.json").read_text("utf-8")
    )
    validator = Draft202012Validator(schema)
    validator.validate(_request())

    for forbidden in ("brief", "prompt", "files", "knowledge", "attachments"):
        invalid = {**_request(), forbidden: "not allowed"}
        assert list(validator.iter_errors(invalid)), forbidden


def test_agent_writes_rehashed_candidate_bundle_atomically(tmp_path: Path) -> None:
    from backend.app.design_promotion.contracts import OpenDesignCandidateManifest
    from agents.open_design_daemon_candidate_agent.workflow import run

    registry = _ToolRegistry(_valid_tool_output())
    result = run(
        {
            "tool_registry": registry,
            "inputs": _request(),
            "output_dir": str(tmp_path),
            "event_logger": None,
        }
    )

    assert result["status"] == "success"
    assert registry.calls == [("open_design_daemon_generate", _request())]
    bundle = tmp_path / "open_design_daemon_candidate_bundle"
    assert bundle.is_dir()
    assert (bundle / "captured/candidate.html").read_bytes() == b"<main>safe candidate</main>"
    assert (bundle / "captured/previews/default_desktop_light.png").read_bytes().startswith(
        b"\x89PNG\r\n\x1a\n"
    )

    manifest_path = bundle / "open_design_daemon_candidates.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    assert manifest["schema_version"] == "open-design-daemon-candidate-manifest/v1"
    assert manifest["review_contract"] == "open-design-candidate/v1"
    assert manifest["generator_kind"] == "open_design_daemon"
    assert manifest["candidate_id"] == result["outputs"][0]["candidate_id"]
    assert manifest["project_id"] == "flai-" + "1" * 32
    assert manifest["run_id"] == "run-001"
    assert manifest["result_package_sha256"] == "b" * 64
    assert manifest["classification"] == "sensitive"
    assert manifest["promotable_asset"] == {
        "slot_id": "default_desktop_light",
        "source_path": "previews/default_desktop_light.png",
        "bundle_relpath": "captured/previews/default_desktop_light.png",
        "media_type": "image/png",
        "size_bytes": _valid_tool_output()["files"][1]["size_bytes"],
        "sha256": _valid_tool_output()["files"][1]["sha256"],
    }
    assert result["outputs"][0]["candidate_manifest_sha256"] == _sha256(
        manifest_path.read_bytes()
    )
    assert result["outputs"][0]["project_id"] == manifest["project_id"]
    assert result["outputs"][0]["run_id"] == manifest["run_id"]
    assert (
        result["outputs"][0]["result_package_sha256"]
        == manifest["result_package_sha256"]
    )
    assert result["outputs"][0]["execution_trust"] == "untrusted_generated"
    assert result["outputs"][0]["candidate_only"] is True
    assert result["outputs"][0]["release_effect"] == "none"
    assert result["outputs"][0]["mock"] is False
    assert result["outputs"][0]["classification"] == "sensitive"
    assert result["outputs"][0]["promotable_asset"] == manifest["promotable_asset"]
    parsed_manifest = OpenDesignCandidateManifest.model_validate(manifest)
    assert parsed_manifest.classification == "sensitive"
    assert parsed_manifest.promotable_asset.sha256 == manifest["promotable_asset"]["sha256"]

    provenance = json.loads((bundle / "open_design_daemon_provenance.json").read_text("utf-8"))
    assert set(provenance) == {
        "schema_version",
        "review_contract",
        "generator_kind",
        "candidate_manifest_sha256",
        "candidate_id",
        "asset_slot",
        "classification",
        "execution_trust",
        "production_readiness",
        "candidate_only",
        "release_effect",
        "mock",
        "project_id",
        "run_id",
        "daemon_binding",
        "storage",
        "design_reference_package_sha256",
        "result_package_sha256",
        "file_set_sha256",
        "response_sha256",
        "safety_scan",
    }
    assert provenance["candidate_manifest_sha256"] == _sha256(manifest_path.read_bytes())
    assert provenance["project_id"] == manifest["project_id"]
    assert provenance["run_id"] == manifest["run_id"]
    assert provenance["result_package_sha256"] == manifest["result_package_sha256"]

    for artifact in result["outputs"][0]["artifacts"]:
        path = bundle / artifact["bundle_relpath"]
        assert path.is_file()
        assert _sha256(path.read_bytes()) == artifact["sha256"]


def test_agent_rejects_self_rehashed_tampering_before_any_write(tmp_path: Path) -> None:
    from agents.open_design_daemon_candidate_agent.workflow import run

    output = _valid_tool_output()
    output["files"][0]["content_base64"] = base64.b64encode(b"different").decode("ascii")
    output["response_sha256"] = response_payload_sha256(output)
    result = run(
        {
            "tool_registry": _ToolRegistry(output),
            "inputs": _request(),
            "output_dir": str(tmp_path),
            "event_logger": None,
        }
    )

    assert result["status"] == "failed"
    assert result["outputs"] == []
    assert list(tmp_path.iterdir()) == []


def test_agent_failure_surfaces_upstream_reconciliation_witness(tmp_path: Path) -> None:
    from agents.open_design_daemon_candidate_agent.workflow import run

    output = failed_tool_output(
        "capture failed",
        asset_slot="agent_activity_indicator",
        failure_stage="capture_files",
        project_id="flai-" + "1" * 32,
        run_id="run-001",
        unreconciled_upstream_side_effects_may_exist=True,
    )
    result = run(
        {
            "tool_registry": _ToolRegistry(output),
            "inputs": _request(),
            "output_dir": str(tmp_path),
            "event_logger": None,
        }
    )

    assert result["status"] == "failed"
    assert "failure_stage=capture_files" in result["error_message"]
    assert "project_id=flai-" + "1" * 32 in result["error_message"]
    assert "run_id=run-001" in result["error_message"]
    assert "upstream_reconciliation_required=true" in result["error_message"]
    assert list(tmp_path.iterdir()) == []


def test_post_publish_event_failure_does_not_split_task_from_complete_bundle(
    tmp_path: Path,
) -> None:
    from agents.open_design_daemon_candidate_agent.workflow import run

    class _EventLogger:
        def __init__(self) -> None:
            self.calls = 0

        def log(self, _event_type: str, _payload: dict[str, Any]) -> None:
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("audit sink failed after durable publication")

    logger = _EventLogger()
    result = run(
        {
            "tool_registry": _ToolRegistry(_valid_tool_output()),
            "inputs": _request(),
            "output_dir": str(tmp_path),
            "event_logger": logger,
        }
    )

    assert result["status"] == "success"
    assert logger.calls == 2
    assert (tmp_path / "open_design_daemon_candidate_bundle").is_dir()
