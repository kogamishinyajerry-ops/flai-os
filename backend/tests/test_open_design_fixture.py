"""Open Design fixture seam: fail-closed provenance and human-review gating.

The checked-in fixture is deliberately a mock design generator.  These tests keep
four trust boundaries explicit: request/fixture bytes are immutable, generated
HTML/SVG stay candidate-only, the workflow validates its own output contract, and
runtime success stops at ``waiting_review`` until a named human acts.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from backend.app.config import AGENTS_DIR, CONTRACTS_DIR, TOOLS_DIR
from backend.app.jobs.runner import JobRunner
from backend.app.runtime.registry import AgentRegistry
from backend.app.storage import repos
from backend.app.tools.registry import ToolRegistry
from tools_impl.open_design_fixture.client import (
    DEFAULT_EXPECTED_FILE_SHA256,
    FIXED_REQUEST_SHA256,
    FixtureValidationError,
    FixtureOpenDesignClient,
    PINNED_DESIGN_REFERENCE_PACKAGE_SHA256,
    bundle_sha256,
    failed_tool_output,
    response_payload_sha256,
    run_generation_sequence,
)
from tools_impl.open_design_fixture.design_reference import (
    DesignReferenceError,
    EXPECTED_SOURCE_SHA256,
    SCHEMA_VERSION,
    build_design_reference_package,
    canonical_json_bytes,
    design_reference_package_sha256,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "tools_impl" / "open_design_fixture" / "fixtures"
FIXED_REQUEST = json.loads((FIXTURE_DIR / "request.json").read_text(encoding="utf-8"))


def _copy_fixture(tmp_path: Path) -> Path:
    destination = tmp_path / "fixtures"
    shutil.copytree(FIXTURE_DIR, destination)
    return destination


def _generate_with_rehashed_candidate(
    tmp_path: Path,
    filename: str,
    replacement: str,
    *,
    before: str | None = None,
) -> dict[str, Any]:
    """Exercise validators behind an explicitly recalculated test integrity gate."""

    fixture_dir = _copy_fixture(tmp_path)
    candidate_path = fixture_dir / filename
    original = candidate_path.read_text(encoding="utf-8")
    marker = before or ("</style>" if filename.endswith(".html") else "</svg>")
    mutated = original.replace(marker, f"  {replacement}\n{marker}", 1)
    assert mutated != original
    candidate_path.write_text(mutated, encoding="utf-8")
    candidate_sha256 = _sha256(candidate_path)

    response_path = fixture_dir / "response.json"
    response = json.loads(response_path.read_text(encoding="utf-8"))
    descriptor = next(item for item in response["candidates"] if item["filename"] == filename)
    descriptor["content_sha256"] = candidate_sha256
    response_path.write_text(json.dumps(response, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    expected = dict(DEFAULT_EXPECTED_FILE_SHA256)
    expected[filename] = candidate_sha256
    expected["response.json"] = _sha256(response_path)
    return FixtureOpenDesignClient._unsafe_with_test_integrity_manifest(
        fixture_dir=fixture_dir,
        expected_file_sha256=expected,
        expected_bundle_sha256=bundle_sha256(expected),
    ).generate(FIXED_REQUEST)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_design_sources(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for relative_path in EXPECTED_SOURCE_SHA256:
        destination = root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / relative_path, destination)
    return root


def test_design_reference_package_is_ssot_grounded_and_byte_stable() -> None:
    first = build_design_reference_package()
    second = build_design_reference_package()

    assert first == second
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert first["schema_version"] == SCHEMA_VERSION == "flai-design-reference-package/v1"
    assert design_reference_package_sha256(first) == PINNED_DESIGN_REFERENCE_PACKAGE_SHA256
    assert FIXED_REQUEST["design_reference_package"]["package_sha256"] == PINNED_DESIGN_REFERENCE_PACKAGE_SHA256
    assert first["tokens"]["--clay"] == "#c15f3c"
    assert first["tokens"]["--trust-signed"] == "#167d8b"
    assert first["trust_color_constraints"]["human_is_only_signer"] is True
    assert first["sources"]["app_tokens"]["sha256"] == EXPECTED_SOURCE_SHA256["frontend/src/App.vue"]


def test_design_reference_source_drift_fails_closed(tmp_path: Path) -> None:
    repo_root = _copy_design_sources(tmp_path)
    motion = repo_root / "docs/design/MOTION-SYSTEM.md"
    motion.write_text(motion.read_text(encoding="utf-8") + "\nsource drift\n", encoding="utf-8")

    with pytest.raises(DesignReferenceError, match="sha256 drift"):
        build_design_reference_package(repo_root=repo_root)


def test_design_reference_missing_source_fails_closed(tmp_path: Path) -> None:
    repo_root = _copy_design_sources(tmp_path)
    (repo_root / "docs/design/UI-PARADIGM.md").unlink()

    with pytest.raises(DesignReferenceError, match="SSOT missing"):
        build_design_reference_package(repo_root=repo_root)


def test_design_reference_missing_allowlisted_token_fails_closed(tmp_path: Path) -> None:
    repo_root = _copy_design_sources(tmp_path)
    app_vue = repo_root / "frontend/src/App.vue"
    source = app_vue.read_text(encoding="utf-8")
    app_vue.write_text(source.replace("  --clay: #c15f3c;", "  --removed-clay: #c15f3c;", 1), encoding="utf-8")
    expected = dict(EXPECTED_SOURCE_SHA256)
    expected["frontend/src/App.vue"] = _sha256(app_vue)

    with pytest.raises(DesignReferenceError, match="token --clay"):
        build_design_reference_package(repo_root=repo_root, expected_source_sha256=expected)


def test_missing_fixture_file_fails_closed(tmp_path: Path) -> None:
    fixture_dir = _copy_fixture(tmp_path)
    (fixture_dir / "flai-task-review-candidate.svg").unlink()

    result = FixtureOpenDesignClient(fixture_dir=fixture_dir).generate(FIXED_REQUEST)

    assert result["status"] == "failed"
    assert result["candidates"] == []
    assert result["fixture_sha256"] == ""
    assert "missing" in result["error_message"].lower()


def test_fixture_byte_hash_drift_fails_closed(tmp_path: Path) -> None:
    fixture_dir = _copy_fixture(tmp_path)
    candidate = fixture_dir / "flai-task-review-candidate.html"
    candidate.write_text(candidate.read_text(encoding="utf-8") + "\n<!-- drift -->\n", encoding="utf-8")

    result = FixtureOpenDesignClient(fixture_dir=fixture_dir).generate(FIXED_REQUEST)

    assert result["status"] == "failed"
    assert result["candidates"] == []
    assert result["fixture_sha256"] == ""
    assert "sha256" in result["error_message"].lower()


def test_canonical_request_hash_drift_fails_closed() -> None:
    request = json.loads(json.dumps(FIXED_REQUEST, ensure_ascii=False))
    request["asset_request"]["locale"] = "en-US"

    result = FixtureOpenDesignClient().generate(request)

    assert result["status"] == "failed"
    assert result["request_sha256"] != FIXED_REQUEST_SHA256
    assert result["candidates"] == []
    assert "request sha256" in result["error_message"].lower()


def test_previous_design_reference_snapshot_binding_fails_closed() -> None:
    request = json.loads(json.dumps(FIXED_REQUEST, ensure_ascii=False))
    request["design_reference_package"]["package_sha256"] = (
        "38f682356f8a7e2b13ec95fec5c6b3e6354928129bc7b61d6634141a6c2efc94"
    )

    result = FixtureOpenDesignClient().generate(request)

    assert result["status"] == "failed"
    assert result["request_sha256"] != FIXED_REQUEST_SHA256
    assert result["candidates"] == []
    assert "request sha256" in result["error_message"].lower()


def test_agent_and_tool_input_schemas_accept_only_the_fixed_request() -> None:
    agent_schema = json.loads(
        (REPO_ROOT / "agents/open_design_candidate_agent/input_schema.json").read_text(encoding="utf-8")
    )
    tools = ToolRegistry(TOOLS_DIR, CONTRACTS_DIR / "tool.schema.json")
    tools.scan()
    tool_schema = tools.get("open_design_fixture_generate")["input_schema"]
    drifted = json.loads(json.dumps(FIXED_REQUEST, ensure_ascii=False))
    drifted["asset_request"]["intent"] += " 任意变化"

    Draft202012Validator(agent_schema).validate(FIXED_REQUEST)
    Draft202012Validator(tool_schema).validate(FIXED_REQUEST)
    assert not Draft202012Validator(agent_schema).is_valid(drifted)
    assert not Draft202012Validator(tool_schema).is_valid(drifted)


def test_malformed_candidate_fails_closed_after_integrity_checkpoint(tmp_path: Path) -> None:
    """Schema validation is independently witnessed after the byte gate.

    Tests may inject a recalculated integrity manifest; production adapter code
    never accepts such an override and always uses the hardcoded constants.
    """

    fixture_dir = _copy_fixture(tmp_path)
    response_path = fixture_dir / "response.json"
    response = json.loads(response_path.read_text(encoding="utf-8"))
    response["candidates"][0]["kind"] = "javascript"
    response_path.write_text(json.dumps(response, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    expected = dict(DEFAULT_EXPECTED_FILE_SHA256)
    expected["response.json"] = _sha256(response_path)
    result = FixtureOpenDesignClient._unsafe_with_test_integrity_manifest(
        fixture_dir=fixture_dir,
        expected_file_sha256=expected,
        expected_bundle_sha256=bundle_sha256(expected),
    ).generate(FIXED_REQUEST)

    assert result["status"] == "failed"
    assert result["candidates"] == []
    assert "response schema" in result["error_message"].lower()


def test_candidate_token_drift_fails_after_integrity_checkpoint(tmp_path: Path) -> None:
    """Even an internally re-hashed fixture cannot detach from App.vue token values."""

    fixture_dir = _copy_fixture(tmp_path)
    candidate_path = fixture_dir / "flai-task-review-candidate.html"
    candidate_path.write_text(
        candidate_path.read_text(encoding="utf-8").replace("--clay: #c15f3c", "--clay: #ffffff", 1),
        encoding="utf-8",
    )
    candidate_sha256 = _sha256(candidate_path)

    response_path = fixture_dir / "response.json"
    response = json.loads(response_path.read_text(encoding="utf-8"))
    response["candidates"][0]["content_sha256"] = candidate_sha256
    response_path.write_text(json.dumps(response, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    expected = dict(DEFAULT_EXPECTED_FILE_SHA256)
    expected["flai-task-review-candidate.html"] = candidate_sha256
    expected["response.json"] = _sha256(response_path)
    result = FixtureOpenDesignClient._unsafe_with_test_integrity_manifest(
        fixture_dir=fixture_dir,
        expected_file_sha256=expected,
        expected_bundle_sha256=bundle_sha256(expected),
    ).generate(FIXED_REQUEST)

    assert result["status"] == "failed"
    assert result["candidates"] == []
    assert "design token mismatch" in result["error_message"].lower()


def test_public_client_rejects_self_rehashed_semantic_schema_override(tmp_path: Path) -> None:
    fixture_dir = _copy_fixture(tmp_path)
    schema_path = fixture_dir / "response.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
    expected = dict(DEFAULT_EXPECTED_FILE_SHA256)
    expected["response.schema.json"] = _sha256(schema_path)

    with pytest.raises(TypeError):
        FixtureOpenDesignClient(
            fixture_dir=fixture_dir,
            expected_file_sha256=expected,
            expected_bundle_sha256=bundle_sha256(expected),
        )

    result = FixtureOpenDesignClient(fixture_dir=fixture_dir).generate(FIXED_REQUEST)
    assert result["status"] == "failed"
    assert result["fixture_sha256"] == ""
    assert "fixture byte sha256 mismatch" in result["error_message"]


def test_unsafe_integrity_seam_cannot_bypass_generate_via_public_sequence(tmp_path: Path) -> None:
    fixture_dir = _copy_fixture(tmp_path)
    schema_path = fixture_dir / "response.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
    expected = dict(DEFAULT_EXPECTED_FILE_SHA256)
    expected["response.schema.json"] = _sha256(schema_path)
    unsafe_client = FixtureOpenDesignClient._unsafe_with_test_integrity_manifest(
        fixture_dir=fixture_dir,
        expected_file_sha256=expected,
        expected_bundle_sha256=bundle_sha256(expected),
    )
    unsafe_client._verify_and_load(FIXED_REQUEST)

    with pytest.raises(FixtureValidationError, match="unsafe test integrity override"):
        run_generation_sequence(
            unsafe_client,
            FIXED_REQUEST,
            build_design_reference_package(),
        )


@pytest.mark.parametrize("reserved_color", ["#2e8f50", "#167d8b", "#be3a3a"])
def test_rehashed_html_cannot_use_reserved_trust_color(
    tmp_path: Path,
    reserved_color: str,
) -> None:
    result = _generate_with_rehashed_candidate(
        tmp_path,
        "flai-task-review-candidate.html",
        f".forged-trust {{ color: {reserved_color}; }}",
    )

    assert result["status"] == "failed"
    assert result["candidates"] == []
    assert "reserved trust color" in result["error_message"]


@pytest.mark.parametrize(
    "functional_color",
    ["rgb(46 143 80)", "hsl(136 51% 37%)"],
)
def test_rehashed_svg_cannot_bypass_trust_lock_with_color_functions(
    tmp_path: Path,
    functional_color: str,
) -> None:
    result = _generate_with_rehashed_candidate(
        tmp_path,
        "flai-task-review-candidate.svg",
        f'<rect width="1" height="1" fill="{functional_color}"/>',
    )

    assert result["status"] == "failed"
    assert result["candidates"] == []
    assert "rgb/rgba/hsl/hsla" in result["error_message"]


@pytest.mark.parametrize(
    "untrusted_declaration",
    [
        ".witness { color: red; }",
        ".witness { background: green; }",
        ".witness { border-color: teal; }",
        ".witness { color: currentColor; }",
        ".witness { color: CanvasText; }",
        ".witness { color: oklch(62% 0.2 25); }",
        ".witness { text-decoration: underline red; }",
        ".witness { -webkit-text-fill-color: green; }",
        ".witness { color: red }",
        ".witness { --ink: red; color: var(--ink); }",
        ".witness { co/**/lor: red; }",
        r".witness { c\6flor: red; }",
    ],
)
def test_rehashed_html_rejects_non_token_color_expressions(
    tmp_path: Path,
    untrusted_declaration: str,
) -> None:
    result = _generate_with_rehashed_candidate(
        tmp_path,
        "flai-task-review-candidate.html",
        untrusted_declaration,
    )

    assert result["status"] == "failed"
    assert result["candidates"] == []
    assert "color" in result["error_message"].lower()


@pytest.mark.parametrize(
    "untrusted_markup",
    [
        '<span style="color:red">inline</span>',
        '<font color="green">legacy</font>',
        '<table bgcolor="teal"><tr><td>legacy</td></tr></table>',
        '<table bordercolor="red"><tr><td>legacy</td></tr></table>',
        '<body text="red" link="green" vlink="teal" alink="red">legacy</body>',
    ],
)
def test_rehashed_html_rejects_inline_and_legacy_color_attributes(
    tmp_path: Path,
    untrusted_markup: str,
) -> None:
    result = _generate_with_rehashed_candidate(
        tmp_path,
        "flai-task-review-candidate.html",
        untrusted_markup,
        before="</body>",
    )

    assert result["status"] == "failed"
    assert result["candidates"] == []
    assert "inline style or legacy color" in result["error_message"]


def test_rehashed_html_rejects_embedded_svg_color_attributes(tmp_path: Path) -> None:
    result = _generate_with_rehashed_candidate(
        tmp_path,
        "flai-task-review-candidate.html",
        '<svg><rect fill="red" stroke="CanvasText" width="1" height="1"/></svg>',
        before="</body>",
    )

    assert result["status"] == "failed"
    assert result["candidates"] == []
    assert "active content" in result["error_message"]


@pytest.mark.parametrize(
    "untrusted_svg",
    [
        '<set attributeName="fill" to="red"/>',
        '<rect width="1" height="1" filter="drop-shadow(0 0 1px red)"/>',
        '<text text-decoration="underline red">bad</text>',
        '<solidColor solid-color="red"/>',
    ],
)
def test_rehashed_svg_rejects_active_or_unpinned_color_surfaces(
    tmp_path: Path,
    untrusted_svg: str,
) -> None:
    result = _generate_with_rehashed_candidate(
        tmp_path,
        "flai-task-review-candidate.svg",
        untrusted_svg,
    )

    assert result["status"] == "failed"
    assert result["candidates"] == []
    assert "unsafe test integrity override" not in result["error_message"]


def test_fixture_client_returns_checked_html_and_svg_candidates() -> None:
    result = FixtureOpenDesignClient().generate(FIXED_REQUEST)

    assert result["status"] == "success"
    assert result["generator_mode"] == "fixture"
    assert result["mock"] is True
    assert result["production_daemon_used"] is False
    assert result["request_sha256"] == FIXED_REQUEST_SHA256
    assert result["design_reference_package_sha256"] == PINNED_DESIGN_REFERENCE_PACKAGE_SHA256
    assert result["design_reference_package"]["schema_version"] == "flai-design-reference-package/v1"
    assert len(result["fixture_sha256"]) == 64
    assert len(result["response_sha256"]) == 64
    assert result["error_message"] is None
    assert {candidate["kind"] for candidate in result["candidates"]} == {"html", "svg"}
    assert [step["operation"] for step in result["protocol_trace"]] == [
        "create_project",
        "start_run",
        "get_run",
        "get_artifact",
    ]
    assert all(candidate["content"] for candidate in result["candidates"])
    assert all("<iframe" not in candidate["content"].lower() for candidate in result["candidates"])
    assert all("<script" not in candidate["content"].lower() for candidate in result["candidates"])
    assert all("machine-only" in candidate["content"] for candidate in result["candidates"])


class _ForgedToolRegistry:
    def __init__(self, output: dict[str, Any]) -> None:
        self.output = output

    def call(self, tool_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        assert tool_id == "open_design_fixture_generate"
        assert payload == FIXED_REQUEST
        return self.output


class _NullEventLogger:
    def log(self, event_type: str, payload: dict[str, Any]) -> None:
        del event_type, payload


class _ProtocolOnlyOpenDesignClient:
    """Implements the public protocol without FixtureOpenDesignClient internals."""

    def __init__(self, candidates: list[dict[str, Any]]) -> None:
        self.candidates = candidates
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def create_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("create_project", payload))
        return {
            "project": {
                "id": "flai-task-review-fixture",
                "name": "FLAi-OS task review candidate",
            },
            "conversationId": "flai-task-review-fixture-conversation",
        }

    def start_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("start_run", payload))
        return {
            "runId": "flai-task-review-fixture-run",
            "projectId": "flai-task-review-fixture",
            "status": "queued",
        }

    def get_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("get_run", payload))
        return {
            "id": "flai-task-review-fixture-run",
            "projectId": "flai-task-review-fixture",
            "status": "succeeded",
            "entryFile": "flai-task-review-candidate.html",
        }

    def get_artifact(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("get_artifact", payload))
        return {
            "project": {
                "id": "flai-task-review-fixture",
                "name": "FLAi-OS task review candidate",
            },
            "entry": "flai-task-review-candidate.html",
            "truncated": False,
            "files": self.candidates,
        }


class _ProtocolAttackClient(_ProtocolOnlyOpenDesignClient):
    def __init__(self, candidates: list[dict[str, Any]], attack: str) -> None:
        super().__init__(candidates)
        self.attack = attack

    def create_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = super().create_project(payload)
        if self.attack == "create_status":
            result["status"] = "failed"
        elif self.attack == "create_name":
            result["project"]["name"] = "wrong project name"
        return result

    def start_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = super().start_run(payload)
        if self.attack == "start_status":
            result["status"] = "failed"
        elif self.attack == "start_project":
            result["projectId"] = "wrong-project"
        return result

    def get_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = super().get_run(payload)
        if self.attack == "run_id":
            result["id"] = "wrong-run"
        elif self.attack == "run_project":
            result["projectId"] = "wrong-project"
        elif self.attack == "run_entry":
            result["entryFile"] = "wrong-entry.html"
        return result

    def get_artifact(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = super().get_artifact(payload)
        if self.attack == "artifact_project":
            result["project"]["id"] = "wrong-project"
        elif self.attack == "artifact_entry":
            result["entry"] = "wrong-entry.html"
        elif self.attack == "artifact_status":
            result["status"] = "failed"
        return result


def test_generation_sequence_accepts_protocol_only_client_with_explicit_verified_package() -> None:
    fixture_output = FixtureOpenDesignClient().generate(FIXED_REQUEST)
    assert fixture_output["status"] == "success"
    package = build_design_reference_package()
    protocol_client = _ProtocolOnlyOpenDesignClient(fixture_output["candidates"])

    result = run_generation_sequence(protocol_client, FIXED_REQUEST, package)

    assert result["status"] == "success"
    assert [operation for operation, _payload in protocol_client.calls] == [
        "create_project",
        "start_run",
        "get_run",
        "get_artifact",
    ]
    assert protocol_client.calls[0][1] == {
        "name": "FLAi-OS task review candidate",
        "id": "flai-task-review-fixture",
    }
    assert protocol_client.calls[1][1]["inputs"] == {
        "candidate_only": True,
        "design_reference_package": package,
        "design_reference_package_sha256": PINNED_DESIGN_REFERENCE_PACKAGE_SHA256,
    }
    assert protocol_client.calls[2][1] == {"runId": "flai-task-review-fixture-run"}
    assert protocol_client.calls[3][1] == {
        "project": "flai-task-review-fixture",
        "entry": "flai-task-review-candidate.html",
        "include": "all",
    }


@pytest.mark.parametrize(
    "attack",
    [
        "start_status",
        "start_project",
        "create_status",
        "create_name",
        "run_id",
        "run_project",
        "run_entry",
        "artifact_project",
        "artifact_entry",
        "artifact_status",
    ],
)
def test_generation_sequence_rejects_cross_run_or_failed_protocol_results(attack: str) -> None:
    fixture_output = FixtureOpenDesignClient().generate(FIXED_REQUEST)
    assert fixture_output["status"] == "success"
    client = _ProtocolAttackClient(fixture_output["candidates"], attack)

    with pytest.raises(FixtureValidationError):
        run_generation_sequence(client, FIXED_REQUEST, build_design_reference_package())


def test_workflow_rejects_forged_tool_response_before_writing(tmp_path: Path) -> None:
    from agents.open_design_candidate_agent.workflow import run

    forged = FixtureOpenDesignClient().generate(FIXED_REQUEST)
    assert forged["status"] == "success"
    forged["response_sha256"] = "0" * 64

    result = run(
        {
            "inputs": FIXED_REQUEST,
            "tool_registry": _ForgedToolRegistry(forged),
            "event_logger": _NullEventLogger(),
            "output_dir": str(tmp_path),
        }
    )

    assert result["status"] == "failed"
    assert "response_sha256" in result["error_message"]
    assert list(tmp_path.iterdir()) == [], "unvalidated candidate bytes must never be written"


def test_workflow_rejects_self_rehashed_candidate_bytes_before_writing(tmp_path: Path) -> None:
    """Self-consistent response hashes cannot detach bytes from the pinned fixture."""

    from agents.open_design_candidate_agent.workflow import run

    forged = FixtureOpenDesignClient().generate(FIXED_REQUEST)
    assert forged["status"] == "success"
    candidate = next(item for item in forged["candidates"] if item["kind"] == "html")
    candidate["content"] = candidate["content"].replace(
        "这是手工编写的 machine-only 协议测试夹具",
        "这是攻击者重写并自重算哈希的 machine-only 协议测试夹具",
        1,
    )
    forged_bytes = candidate["content"].encode("utf-8")
    candidate["content_sha256"] = hashlib.sha256(forged_bytes).hexdigest()
    candidate["size_bytes"] = len(forged_bytes)
    forged["response_sha256"] = response_payload_sha256(forged)

    result = run(
        {
            "inputs": FIXED_REQUEST,
            "tool_registry": _ForgedToolRegistry(forged),
            "event_logger": _NullEventLogger(),
            "output_dir": str(tmp_path),
        }
    )

    assert result["status"] == "failed"
    assert "pinned fixture bytes" in result["error_message"]
    assert list(tmp_path.iterdir()) == [], "self-rehashed forged bytes must never be written"


def test_workflow_rejects_self_rehashed_failed_protocol_trace_before_writing(tmp_path: Path) -> None:
    from agents.open_design_candidate_agent.workflow import run

    forged = FixtureOpenDesignClient().generate(FIXED_REQUEST)
    assert forged["status"] == "success"
    forged["protocol_trace"][2]["status"] = "failed"
    forged["response_sha256"] = response_payload_sha256(forged)

    result = run(
        {
            "inputs": FIXED_REQUEST,
            "tool_registry": _ForgedToolRegistry(forged),
            "event_logger": _NullEventLogger(),
            "output_dir": str(tmp_path),
        }
    )

    assert result["status"] == "failed"
    assert "protocol trace mismatch" in result["error_message"]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("forgery", ["title", "order"])
def test_workflow_rejects_self_rehashed_candidate_descriptor_forgery(
    tmp_path: Path,
    forgery: str,
) -> None:
    from agents.open_design_candidate_agent.workflow import run

    forged = FixtureOpenDesignClient().generate(FIXED_REQUEST)
    assert forged["status"] == "success"
    if forgery == "title":
        forged["candidates"][0]["title"] = "攻击者伪造且自重算的候选标题"
    else:
        forged["candidates"].reverse()
    forged["response_sha256"] = response_payload_sha256(forged)

    result = run(
        {
            "inputs": FIXED_REQUEST,
            "tool_registry": _ForgedToolRegistry(forged),
            "event_logger": _NullEventLogger(),
            "output_dir": str(tmp_path),
        }
    )

    assert result["status"] == "failed"
    assert "candidate descriptor mismatch" in result["error_message"]
    assert list(tmp_path.iterdir()) == []


def test_workflow_requires_explicit_empty_non_symlink_output_dir(tmp_path: Path) -> None:
    from agents.open_design_candidate_agent.workflow import run

    tool_output = FixtureOpenDesignClient().generate(FIXED_REQUEST)
    missing = run(
        {
            "inputs": FIXED_REQUEST,
            "tool_registry": _ForgedToolRegistry(tool_output),
            "event_logger": _NullEventLogger(),
        }
    )
    assert missing["status"] == "failed"
    assert "显式注入" in missing["error_message"]

    target = tmp_path / "target"
    target.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(target, target_is_directory=True)
    symlinked = run(
        {
            "inputs": FIXED_REQUEST,
            "tool_registry": _ForgedToolRegistry(tool_output),
            "event_logger": _NullEventLogger(),
            "output_dir": str(linked),
        }
    )
    assert symlinked["status"] == "failed"
    assert "符号链接" in symlinked["error_message"]
    assert list(target.iterdir()) == []

    occupied = tmp_path / "occupied"
    occupied.mkdir()
    sentinel = occupied / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    nonempty = run(
        {
            "inputs": FIXED_REQUEST,
            "tool_registry": _ForgedToolRegistry(tool_output),
            "event_logger": _NullEventLogger(),
            "output_dir": str(occupied),
        }
    )
    assert nonempty["status"] == "failed"
    assert "必须为空" in nonempty["error_message"]
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_workflow_atomic_publish_uses_nonexistent_windows_compatible_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Model Win32's refusal to replace an already-existing directory."""

    from agents.open_design_candidate_agent import workflow

    real_replace = workflow.os.replace
    destination_existed: list[bool] = []

    def windows_directory_replace(source: str | Path, destination: str | Path) -> None:
        destination_path = Path(destination)
        existed = destination_path.exists() or destination_path.is_symlink()
        destination_existed.append(existed)
        if existed:
            raise OSError("[WinError 183] Cannot replace an existing directory")
        real_replace(source, destination)

    monkeypatch.setattr(workflow.os, "replace", windows_directory_replace)
    tool_output = FixtureOpenDesignClient().generate(FIXED_REQUEST)
    result = workflow.run(
        {
            "inputs": FIXED_REQUEST,
            "tool_registry": _ForgedToolRegistry(tool_output),
            "event_logger": _NullEventLogger(),
            "output_dir": str(tmp_path),
        }
    )

    assert result["status"] == "success"
    assert destination_existed == [False]
    bundle_dir = tmp_path / "open_design_candidate_bundle"
    assert [entry.name for entry in tmp_path.iterdir()] == ["open_design_candidate_bundle"]
    assert {path.name for path in bundle_dir.iterdir()} == {
        "OPEN_DESIGN_REVIEW.md",
        "flai-task-review-candidate.html",
        "flai-task-review-candidate.svg",
        "flai_design_reference_package.json",
        "open_design_candidates.json",
        "open_design_provenance.json",
    }


def test_manifests_are_registered_with_mock_and_human_review_locked() -> None:
    agents = AgentRegistry(AGENTS_DIR, CONTRACTS_DIR / "agent.schema.json")
    agents.scan()
    agent = agents.get("open_design_candidate_agent")
    assert agent is not None, agents.errors
    assert agent["status"] == "draft"
    assert agent["model"]["profile"] == "none"
    assert agent["tools"] == ["open_design_fixture_generate"]
    assert agent["workflow"] == {
        "entrypoint": "workflow.py",
        "mode": "job",
        "requires_human_review": True,
    }
    assert agent["data_asset"]["collect_samples"] is False

    tools = ToolRegistry(TOOLS_DIR, CONTRACTS_DIR / "tool.schema.json")
    tools.scan()
    tool = tools.get("open_design_fixture_generate")
    assert tool is not None, tools.errors
    assert tool["mock"] is True
    assert "fixture" in tool["id"]
    assert "daemon" not in tool["id"]


@pytest.mark.parametrize(
    "forgery",
    [
        "trace_status",
        "trace_order",
        "candidate_title",
        "candidate_order",
        "candidate_content",
        "design_package",
    ],
)
def test_tool_output_schema_rejects_forged_success_contract(forgery: str) -> None:
    tools = ToolRegistry(TOOLS_DIR, CONTRACTS_DIR / "tool.schema.json")
    tools.scan()
    schema = tools.get("open_design_fixture_generate")["output_schema"]
    forged = FixtureOpenDesignClient().generate(FIXED_REQUEST)
    assert Draft202012Validator(schema).is_valid(forged)

    if forgery == "trace_status":
        forged["protocol_trace"][2]["status"] = "failed"
    elif forgery == "trace_order":
        forged["protocol_trace"].reverse()
    elif forgery == "candidate_title":
        forged["candidates"][0]["title"] = "schema-valid forged title"
    elif forgery == "candidate_order":
        forged["candidates"].reverse()
    elif forgery == "candidate_content":
        forged["candidates"][0]["content"] = forged["candidates"][0]["content"].replace(
            "machine-only",
            "machine-onlx",
            1,
        )
    else:
        forged["design_reference_package"] = {}
    if forgery not in {"candidate_content", "design_package"}:
        forged["response_sha256"] = response_payload_sha256(forged)

    assert not Draft202012Validator(schema).is_valid(forged)


def test_tool_output_schema_accepts_honest_failed_contract() -> None:
    tools = ToolRegistry(TOOLS_DIR, CONTRACTS_DIR / "tool.schema.json")
    tools.scan()
    schema = tools.get("open_design_fixture_generate")["output_schema"]

    assert Draft202012Validator(schema).is_valid(
        failed_tool_output("fixture validation failed honestly")
    )


@pytest.mark.parametrize(
    "forgery",
    [
        "trace_status",
        "trace_order",
        "artifact_filename",
        "artifact_order",
        "artifact_role",
        "artifact_sha",
        "fixture_sha",
        "request_sha",
        "response_sha",
        "design_package_sha",
    ],
)
def test_agent_output_schema_rejects_forged_success_contract(
    tmp_path: Path,
    forgery: str,
) -> None:
    from agents.open_design_candidate_agent.workflow import run

    tool_output = FixtureOpenDesignClient().generate(FIXED_REQUEST)
    result = run(
        {
            "inputs": FIXED_REQUEST,
            "tool_registry": _ForgedToolRegistry(tool_output),
            "event_logger": _NullEventLogger(),
            "output_dir": str(tmp_path),
        }
    )
    output = result["outputs"][0]
    schema = json.loads(
        (REPO_ROOT / "agents/open_design_candidate_agent/output_schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert Draft202012Validator(schema).is_valid(output)

    if forgery == "trace_status":
        output["protocol_trace"][2]["status"] = "failed"
    elif forgery == "trace_order":
        output["protocol_trace"].reverse()
    elif forgery == "artifact_filename":
        output["artifacts"][0]["filename"] = "forged.md"
    elif forgery == "artifact_order":
        output["artifacts"].reverse()
    elif forgery == "artifact_role":
        output["artifacts"][0]["role"] = "candidate"
    elif forgery == "artifact_sha":
        output["artifacts"][0]["sha256"] = "0" * 64
    elif forgery == "fixture_sha":
        output["fixture_sha256"] = "0" * 64
    elif forgery == "request_sha":
        output["request_sha256"] = "0" * 64
    elif forgery == "response_sha":
        output["response_sha256"] = "0" * 64
    else:
        output["design_reference_package_sha256"] = "0" * 64

    assert not Draft202012Validator(schema).is_valid(output)


def test_runtime_success_stops_at_waiting_review_and_registers_candidates(app_env) -> None:
    client, app = app_env
    response = client.post(
        "/api/tasks",
        json={"agent_id": "open_design_candidate_agent", "inputs": FIXED_REQUEST},
    )
    assert response.status_code == 200, response.text
    task_id = response.json()["id"]

    assert JobRunner(app.state.runtime, app.state.conn_factory).run_once() is True
    task = client.get(f"/api/tasks/{task_id}").json()

    assert task["status"] == "waiting_review"
    assert task["error_message"] is None
    conn = app.state.conn_factory()
    try:
        files = [repos.get_file(conn, file_id) for file_id in task["output_file_ids"]]
        filenames = {record["filename"] for record in files if record is not None}
        assert filenames == {
            "OPEN_DESIGN_REVIEW.md",
            "flai-task-review-candidate.html",
            "flai-task-review-candidate.svg",
            "flai_design_reference_package.json",
            "open_design_candidates.json",
            "open_design_provenance.json",
        }
        by_name = {record["filename"]: Path(record["path"]) for record in files if record is not None}
        package_bytes = by_name["flai_design_reference_package.json"].read_bytes()
        assert hashlib.sha256(package_bytes).hexdigest() == PINNED_DESIGN_REFERENCE_PACKAGE_SHA256
        provenance = json.loads(by_name["open_design_provenance.json"].read_text(encoding="utf-8"))
        assert provenance["candidate_only"] is True
        assert provenance["fixture_origin"] == "handcrafted_machine_only_protocol_contract"
        assert provenance["product_asset"] is False
        assert provenance["visual_qa_conclusion"] is False
        assert provenance["render_or_publish_allowed"] is False
        assert provenance["release_effect"] == "none"
        assert provenance["design_reference_package_sha256"] == PINNED_DESIGN_REFERENCE_PACKAGE_SHA256
        assert provenance["design_sources"]["app_tokens"]["sha256"] == EXPECTED_SOURCE_SHA256[
            "frontend/src/App.vue"
        ]
        assert provenance["open_design_protocol"]["upstream_revision"] == "e06bff69"
        review = by_name["OPEN_DESIGN_REVIEW.md"].read_text(encoding="utf-8")
        assert "machine-only" in review
        assert "不是生产 daemon 真跑结果" in review
        assert "不是" in review and "视觉 QA 结论" in review
        runs = repos.list_tool_runs(conn, task_id)
        assert len(runs) == 1
        assert runs[0]["tool_id"] == "open_design_fixture_generate"
        assert runs[0]["mock"] is True
        assert runs[0]["status"] == "success"
        event_types = [event["event_type"] for event in repos.list_events(conn, task_id)]
        assert "review_requested" in event_types
        assert "task_completed" not in event_types
    finally:
        conn.close()
