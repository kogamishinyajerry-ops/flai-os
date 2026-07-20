"""Closed candidate generation sequence over a preflighted daemon port."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from typing import Any, Callable, Mapping, Protocol

from tools_impl.open_design_fixture.design_reference import (
    canonical_json_bytes,
    design_reference_package_sha256,
    validate_design_reference_package,
)

from .client import canonical_json_bytes as canonical_response_bytes
from .policy import (
    MAX_FILES,
    MAX_FILE_BYTES,
    MAX_TOTAL_BYTES,
    CandidatePolicyError,
    validate_candidate_bundle,
    validate_safe_path,
)


class DaemonGenerationError(RuntimeError):
    """The generation sequence could not prove a closed candidate bundle."""

    def __init__(
        self,
        message: str,
        *,
        failure_stage: str | None = None,
        project_id: str | None = None,
        run_id: str | None = None,
        unreconciled_upstream_side_effects_may_exist: bool = False,
    ) -> None:
        super().__init__(message)
        self.failure_stage = failure_stage
        self.project_id = project_id
        self.run_id = run_id
        self.unreconciled_upstream_side_effects_may_exist = (
            unreconciled_upstream_side_effects_may_exist
        )


class OpenDesignDaemonPort(Protocol):
    def preflight(self) -> dict[str, Any]: ...
    def create_project(self, project_id: str, name: str) -> dict[str, Any]: ...
    def start_run(self, project_id: str, conversation_id: str, prompt: str) -> dict[str, Any]: ...
    def get_run(self, run_id: str) -> dict[str, Any]: ...
    def get_result_package(self, run_id: str) -> dict[str, Any]: ...
    def list_files(self, project_id: str) -> dict[str, Any]: ...
    def get_file(self, project_id: str, path: str) -> tuple[str, bytes]: ...


ASSET_INTENTS = {
    "task_review_summary": (
        "Create a static FLAi-OS task review summary that makes provenance, "
        "human review state, and next action immediately legible."
    ),
    "agent_activity_indicator": (
        "Create a static FLAi-OS agent activity indicator with calm, low-anxiety "
        "progress signaling and a clear stalled/degraded distinction."
    ),
    "workflow_monitor_sidebar": (
        "Create a static FLAi-OS workflow monitor sidebar that progressively discloses "
        "sub-agent state, handoffs, and exceptions without dashboard overload."
    ),
}

COMPARISON_SLOTS: dict[str, dict[str, Any]] = {
    "default_desktop_light": {
        "viewport": {"width": 1440, "height": 900, "dpr": 1},
        "state": "default",
        "theme": "light",
        "locale": "zh-CN",
    },
    "default_mobile_light": {
        "viewport": {"width": 390, "height": 844, "dpr": 1},
        "state": "default",
        "theme": "light",
        "locale": "zh-CN",
    },
    "focus_desktop_light": {
        "viewport": {"width": 1440, "height": 900, "dpr": 1},
        "state": "focus",
        "theme": "light",
        "locale": "zh-CN",
    },
    "reduced_motion_desktop_light": {
        "viewport": {"width": 1440, "height": 900, "dpr": 1},
        "state": "reduced_motion",
        "theme": "light",
        "locale": "zh-CN",
    },
    "error_desktop_light": {
        "viewport": {"width": 1440, "height": 900, "dpr": 1},
        "state": "error",
        "theme": "light",
        "locale": "zh-CN",
    },
    "default_desktop_dark": {
        "viewport": {"width": 1440, "height": 900, "dpr": 1},
        "state": "default",
        "theme": "dark",
        "locale": "zh-CN",
    },
    "default_mobile_dark": {
        "viewport": {"width": 390, "height": 844, "dpr": 1},
        "state": "default",
        "theme": "dark",
        "locale": "zh-CN",
    },
}

_REQUEST_FIELDS = {
    "schema_version",
    "task_id",
    "asset_slot",
    "comparison_slots",
    "interaction_contract",
}
_INTERACTION_CONTRACT = {
    "candidate_only": True,
    "human_review_required": True,
    "release_effect": "none",
    "rendering": "passive_png_only",
}
_TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_PREFLIGHT_BINDING_FIELDS = {
    "version",
    "channel",
    "packaged",
    "platform",
    "arch",
    "agent_id",
    "requested_model_id",
    "design_system_id",
    "design_system_sha256",
    "sandbox_reported",
}
_OUTPUT_BINDING_FIELDS = _PREFLIGHT_BINDING_FIELDS | {
    "design_system_execution_sha256",
    "model_execution_attested",
}
_OUTPUT_FIELDS = {
    "schema_version",
    "status",
    "generator_mode",
    "mock",
    "untrusted_generated",
    "execution_trust",
    "real_daemon_candidate_captured",
    "failure_stage",
    "unreconciled_upstream_side_effects_may_exist",
    "production_readiness",
    "candidate_only",
    "release_effect",
    "human_review_required",
    "classification",
    "candidate_id",
    "asset_slot",
    "project_id",
    "run_id",
    "daemon_binding",
    "design_reference_package",
    "design_reference_package_sha256",
    "result_package_sha256",
    "storage",
    "file_set_sha256",
    "files",
    "passive_previews",
    "safety_scan",
    "response_sha256",
    "error_message",
}


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def response_payload_sha256(output: Mapping[str, Any]) -> str:
    return _sha256(
        canonical_response_bytes({**dict(output), "response_sha256": ""})
    )


def failed_tool_output(
    message: str,
    *,
    asset_slot: Any = None,
    failure_stage: str = "adapter_boundary",
    project_id: Any = None,
    run_id: Any = None,
    unreconciled_upstream_side_effects_may_exist: bool = False,
) -> dict[str, Any]:
    safe_message = " ".join(str(message).split())[:1000] or "Open Design daemon adapter failed"
    safe_project_id = (
        project_id
        if isinstance(project_id, str) and re.fullmatch(r"flai-[a-f0-9]{32}", project_id)
        else None
    )
    safe_run_id = run_id if isinstance(run_id, str) and run_id else None
    output: dict[str, Any] = {
        "schema_version": "open-design-daemon-result/v1",
        "status": "failed",
        "generator_mode": "loopback_daemon_trial",
        "mock": False,
        "untrusted_generated": True,
        "execution_trust": "untrusted_generated",
        "real_daemon_candidate_captured": False,
        "failure_stage": failure_stage,
        "unreconciled_upstream_side_effects_may_exist": (
            unreconciled_upstream_side_effects_may_exist is True
        ),
        "production_readiness": "trial_not_attested",
        "candidate_only": True,
        "release_effect": "none",
        "human_review_required": True,
        "classification": "sensitive",
        "candidate_id": None,
        "asset_slot": asset_slot if asset_slot in ASSET_INTENTS else None,
        "project_id": safe_project_id,
        "run_id": safe_run_id,
        "daemon_binding": {},
        "design_reference_package": {},
        "design_reference_package_sha256": "",
        "result_package_sha256": "",
        "storage": {"kind": "od-owned", "base_dir": None},
        "file_set_sha256": "",
        "files": [],
        "passive_previews": [],
        "safety_scan": {
            "policy": "flai-open-design-passive-candidate/v1",
            "passed": False,
        },
        "response_sha256": "",
        "error_message": safe_message,
    }
    output["response_sha256"] = response_payload_sha256(output)
    return output


def validate_tool_response(output: Mapping[str, Any]) -> None:
    """Re-validate captured bytes and every binding without trusting the adapter."""

    if set(output) != _OUTPUT_FIELDS:
        raise DaemonGenerationError("tool response fields do not match the closed contract")
    if output.get("response_sha256") != response_payload_sha256(output):
        raise DaemonGenerationError("tool response_sha256 mismatch")
    expected_scalars = {
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
        "error_message": None,
    }
    if any(output.get(key) != expected for key, expected in expected_scalars.items()):
        raise DaemonGenerationError("tool response lost its candidate-only trial identity")
    asset_slot = output.get("asset_slot")
    if asset_slot not in ASSET_INTENTS:
        raise DaemonGenerationError("tool response asset_slot is not allowlisted")
    project_id = output.get("project_id")
    run_id = output.get("run_id")
    if (
        not isinstance(project_id, str)
        or re.fullmatch(r"flai-[a-f0-9]{32}", project_id) is None
        or not isinstance(run_id, str)
        or not run_id
    ):
        raise DaemonGenerationError("tool response project/run identity is invalid")
    _validate_output_binding(output.get("daemon_binding"))
    package = output.get("design_reference_package")
    if not isinstance(package, dict):
        raise DaemonGenerationError("tool response design reference package is invalid")
    validate_design_reference_package(package)
    design_digest = design_reference_package_sha256(package)
    if output.get("design_reference_package_sha256") != design_digest:
        raise DaemonGenerationError("tool response design reference digest mismatch")
    if output.get("storage") != {"kind": "od-owned", "base_dir": None}:
        raise DaemonGenerationError("tool response storage is not od-owned")
    if re.fullmatch(r"[a-f0-9]{64}", str(output.get("result_package_sha256", ""))) is None:
        raise DaemonGenerationError("tool response result-package digest is invalid")

    raw_files = output.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise DaemonGenerationError("tool response files are empty or invalid")
    files: list[dict[str, Any]] = []
    contents: dict[str, bytes] = {}
    for item in raw_files:
        if not isinstance(item, dict) or set(item) != {
            "path",
            "media_type",
            "size_bytes",
            "sha256",
            "content_base64",
        }:
            raise DaemonGenerationError("tool response file fields mismatch")
        path = item.get("path")
        if not isinstance(path, str):
            raise DaemonGenerationError("tool response file path is invalid")
        try:
            validate_safe_path(path)
            content = base64.b64decode(str(item.get("content_base64", "")), validate=True)
        except (CandidatePolicyError, ValueError) as exc:
            raise DaemonGenerationError(f"tool response file encoding is invalid: {path}") from exc
        if item.get("size_bytes") != len(content) or item.get("sha256") != _sha256(content):
            raise DaemonGenerationError(f"tool response file sha256/size mismatch: {path}")
        files.append(dict(item))
        contents[path] = content
    if [item["path"] for item in files] != sorted(contents):
        raise DaemonGenerationError("tool response files must be uniquely path-sorted")
    try:
        png_info = validate_candidate_bundle(
            (item["path"], item["media_type"], contents[item["path"]]) for item in files
        )
    except CandidatePolicyError as exc:
        raise DaemonGenerationError(f"tool response candidate policy mismatch: {exc}") from exc
    file_set_sha256 = _sha256(
        canonical_response_bytes(
            [
                {key: item[key] for key in ("path", "media_type", "size_bytes", "sha256")}
                for item in files
            ]
        )
    )
    if output.get("file_set_sha256") != file_set_sha256:
        raise DaemonGenerationError("tool response file-set digest mismatch")
    expected_candidate_id = "odc-" + _sha256(
        f"{project_id}\x00{run_id}\x00{file_set_sha256}".encode("utf-8")
    )[:32]
    if output.get("candidate_id") != expected_candidate_id:
        raise DaemonGenerationError("tool response candidate_id binding mismatch")

    previews = output.get("passive_previews")
    if not isinstance(previews, list) or not previews:
        raise DaemonGenerationError("tool response has no passive preview descriptors")
    preview_slots: set[str] = set()
    source_file = next((item for item in files if item["path"] == "candidate.html"), None)
    if source_file is None:
        raise DaemonGenerationError("tool response is missing candidate.html")
    for preview in previews:
        if not isinstance(preview, dict) or set(preview) != {
            "slot_id",
            "viewport",
            "state",
            "theme",
            "locale",
            "source",
            "image",
            "passive_preview_scan",
        }:
            raise DaemonGenerationError("passive preview fields mismatch")
        slot_id = preview.get("slot_id")
        if not isinstance(slot_id, str) or slot_id not in COMPARISON_SLOTS or slot_id in preview_slots:
            raise DaemonGenerationError("passive preview slot is invalid or duplicated")
        preview_slots.add(slot_id)
        contract = COMPARISON_SLOTS[slot_id]
        if any(preview.get(field) != contract[field] for field in ("viewport", "state", "theme", "locale")):
            raise DaemonGenerationError("passive preview matrix binding mismatch")
        source = preview.get("source")
        image = preview.get("image")
        if not isinstance(source, dict) or source != {
            "path": "candidate.html",
            "sha256": source_file["sha256"],
        }:
            raise DaemonGenerationError("passive preview source binding mismatch")
        expected_image_path = f"previews/{slot_id}.png"
        image_file = next((item for item in files if item["path"] == expected_image_path), None)
        dimensions = png_info.get(expected_image_path)
        if image_file is None or dimensions is None or not isinstance(image, dict):
            raise DaemonGenerationError("passive preview PNG binding is missing")
        expected_image = {
            "path": expected_image_path,
            "sha256": image_file["sha256"],
            "size_bytes": image_file["size_bytes"],
            "media_type": "image/png",
            **dimensions,
        }
        if image != expected_image:
            raise DaemonGenerationError("passive preview PNG descriptor mismatch")
        if preview.get("passive_preview_scan") != {
            "policy": "flai-passive-png/v1",
            "passed": True,
            "active_content_executed": False,
        }:
            raise DaemonGenerationError("passive preview scan witness mismatch")
    if "default_desktop_light" not in preview_slots:
        raise DaemonGenerationError("tool response is missing the fixed promotable preview")
    safety_scan = output.get("safety_scan")
    if safety_scan != {
        "policy": "flai-open-design-passive-candidate/v1",
        "passed": True,
        "file_count": len(files),
        "total_bytes": sum(item["size_bytes"] for item in files),
        "double_fetch_verified": True,
        "file_list_stable": True,
        "static_policy_screened": True,
        "png_structural_validation": True,
    }:
        raise DaemonGenerationError("tool response safety-scan witness mismatch")


def _validate_request(request: Mapping[str, Any]) -> tuple[str, str, list[str]]:
    if set(request) != _REQUEST_FIELDS:
        raise DaemonGenerationError("daemon request fields do not match the closed contract")
    if request.get("schema_version") != "open-design-daemon-request/v1":
        raise DaemonGenerationError("daemon request schema_version mismatch")
    task_id = request.get("task_id")
    if not isinstance(task_id, str) or _TASK_ID.fullmatch(task_id) is None:
        raise DaemonGenerationError("task_id is not a safe isolation identity")
    asset_slot = request.get("asset_slot")
    if not isinstance(asset_slot, str) or asset_slot not in ASSET_INTENTS:
        raise DaemonGenerationError("asset_slot is not allowlisted")
    slots = request.get("comparison_slots")
    if (
        not isinstance(slots, list)
        or not 1 <= len(slots) <= 7
        or not all(isinstance(slot, str) and slot in COMPARISON_SLOTS for slot in slots)
        or len(set(slots)) != len(slots)
    ):
        raise DaemonGenerationError("comparison_slots are not a unique allowlisted set")
    if request.get("interaction_contract") != _INTERACTION_CONTRACT:
        raise DaemonGenerationError("interaction contract mismatch")
    if "default_desktop_light" not in slots:
        raise DaemonGenerationError(
            "comparison_slots must include default_desktop_light as the fixed promotable slot"
        )
    return task_id, asset_slot, slots


def _project_id(task_id: str, asset_slot: str) -> str:
    identity = hashlib.sha256(f"{task_id}\x00{asset_slot}".encode("utf-8")).hexdigest()[:32]
    return f"flai-{identity}"


def _prompt(
    asset_slot: str,
    slots: list[str],
    design_package: Mapping[str, Any],
) -> str:
    slot_contract = [
        {
            "slot_id": slot,
            **COMPARISON_SLOTS[slot],
            "source_path": "candidate.html",
            "image_path": f"previews/{slot}.png",
        }
        for slot in slots
    ]
    return "\n".join(
        [
            "FLAi-OS closed fixed-slot sensitive design-candidate commission.",
            f"Fixed asset intent: {ASSET_INTENTS[asset_slot]}",
            "Produce candidate.html as static UTF-8 HTML with no script, iframe, event handler, external URL, data/blob URL, or active content.",
            "Only HTML, SVG, CSS, JSON, Markdown, and the required passive PNG files are allowed.",
            "For every comparison slot, write the exact PNG path and exact pixel dimensions in this contract:",
            json.dumps(slot_contract, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            "Use this FLAi design reference exactly; do not invent trust colors or change signing semantics:",
            canonical_json_bytes(design_package).decode("utf-8"),
            "This run is candidate-only. Do not publish, promote, write FLAi source, or claim human approval.",
        ]
    )


def _validate_binding(binding: Any) -> dict[str, Any]:
    if not isinstance(binding, dict) or set(binding) != _PREFLIGHT_BINDING_FIELDS:
        raise DaemonGenerationError("daemon preflight binding fields mismatch")
    if (
        binding.get("sandbox_reported") is not True
        or type(binding.get("packaged")) is not bool
        or any(
            not isinstance(binding.get(field), str) or not binding[field]
            for field in _PREFLIGHT_BINDING_FIELDS - {"sandbox_reported", "packaged"}
        )
        or re.fullmatch(r"[a-f0-9]{64}", binding["design_system_sha256"]) is None
    ):
        raise DaemonGenerationError("daemon preflight binding is invalid")
    return binding


def _validate_output_binding(binding: Any) -> dict[str, Any]:
    if not isinstance(binding, dict) or set(binding) != _OUTPUT_BINDING_FIELDS:
        raise DaemonGenerationError("daemon output binding fields mismatch")
    preflight = {key: binding[key] for key in _PREFLIGHT_BINDING_FIELDS}
    _validate_binding(preflight)
    if (
        binding.get("model_execution_attested") is not False
        or re.fullmatch(
            r"[a-f0-9]{64}",
            str(binding.get("design_system_execution_sha256", "")),
        )
        is None
    ):
        raise DaemonGenerationError("daemon execution binding is invalid")
    return binding


def _validate_project_result(
    value: Any,
    *,
    project_id: str,
    project_name: str,
    design_system_id: str,
) -> str:
    if not isinstance(value, dict) or set(value) != {"project", "conversationId"}:
        raise DaemonGenerationError("create-project result fields mismatch")
    project = value.get("project")
    conversation_id = value.get("conversationId")
    if (
        not isinstance(project, dict)
        or project.get("id") != project_id
        or project.get("name") != project_name
        or project.get("designSystemId") != design_system_id
        or not isinstance(conversation_id, str)
        or not conversation_id
    ):
        raise DaemonGenerationError("create-project exact binding mismatch")
    return conversation_id


def _validate_started(value: Any, conversation_id: str) -> tuple[str, str]:
    expected = {"runId", "conversationId", "assistantMessageId"}
    if not isinstance(value, dict) or set(value) != expected:
        raise DaemonGenerationError("start-run result fields mismatch")
    if value.get("conversationId") != conversation_id:
        raise DaemonGenerationError("start-run conversation binding mismatch")
    run_id = value.get("runId")
    assistant_id = value.get("assistantMessageId")
    if not isinstance(run_id, str) or not run_id or not isinstance(assistant_id, str) or not assistant_id:
        raise DaemonGenerationError("start-run identifiers are invalid")
    return run_id, assistant_id


def _validate_run(
    value: Any,
    *,
    run_id: str,
    project_id: str,
    conversation_id: str,
    assistant_id: str,
    binding: Mapping[str, Any],
) -> tuple[str, str | None]:
    if not isinstance(value, dict):
        raise DaemonGenerationError("run status is not an object")
    status = value.get("status")
    if status not in {"queued", "running", "succeeded", "failed", "canceled"}:
        raise DaemonGenerationError("run returned an unknown status")
    if (
        value.get("id") != run_id
        or value.get("projectId") != project_id
        or value.get("conversationId") != conversation_id
        or value.get("assistantMessageId") != assistant_id
        or value.get("agentId") != binding["agent_id"]
        or value.get("designSystemId") != binding["design_system_id"]
    ):
        raise DaemonGenerationError("run status lost its exact result binding")
    execution_digest: str | None = None
    if status == "succeeded":
        execution_digest = value.get("designSystemDigest")
        if (
            value.get("designSystemRequestedId") != binding["design_system_id"]
            or value.get("designSystemSelectionSource") != "request"
            or not isinstance(execution_digest, str)
            or re.fullmatch(r"[a-f0-9]{64}", execution_digest) is None
        ):
            raise DaemonGenerationError("run status lost its design-system execution binding")
    return status, execution_digest


def _validate_result_package(
    value: Any,
    *,
    run_id: str,
    project_id: str,
    conversation_id: str,
    assistant_id: str,
    agent_id: str,
) -> None:
    if not isinstance(value, dict) or value.get("schema") != "open-design.run-result-package.v1":
        raise DaemonGenerationError("run result-package schema mismatch")
    run = value.get("run")
    workspace = value.get("workspace")
    project = value.get("project")
    if (
        not isinstance(run, dict)
        or run.get("id") != run_id
        or run.get("status") != "succeeded"
        or run.get("projectId") != project_id
        or run.get("conversationId") != conversation_id
        or run.get("assistantMessageId") != assistant_id
        or run.get("agentId") != agent_id
    ):
        raise DaemonGenerationError("result-package run binding mismatch")
    if (
        not isinstance(workspace, dict)
        or workspace.get("storage") != {"kind": "od-owned", "baseDir": None}
    ):
        raise DaemonGenerationError("result-package storage must be exactly od-owned")
    if (
        not isinstance(project, dict)
        or project.get("id") != project_id
        or type(project.get("fileCount")) is not int
        or project["fileCount"] < 0
    ):
        raise DaemonGenerationError("result-package project binding mismatch")


def _file_snapshot(value: Any) -> tuple[list[dict[str, Any]], bytes]:
    if not isinstance(value, dict) or set(value) != {"files"} or not isinstance(value["files"], list):
        raise DaemonGenerationError("project file-list envelope mismatch")
    files = value["files"]
    if not 1 <= len(files) <= MAX_FILES:
        raise DaemonGenerationError("project file metadata exceeds resource bounds")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    total_bytes = 0
    for item in files:
        if not isinstance(item, dict):
            raise DaemonGenerationError("project file-list entry is invalid")
        name = item.get("name")
        if not isinstance(name, str):
            raise DaemonGenerationError("project file-list entry has no name")
        try:
            validate_safe_path(name)
        except CandidatePolicyError as exc:
            raise DaemonGenerationError(str(exc)) from exc
        if item.get("path", name) != name or item.get("type", "file") != "file":
            raise DaemonGenerationError("project file-list path/type mismatch")
        if name.casefold() in seen:
            raise DaemonGenerationError("project file-list contains a casefold collision")
        seen.add(name.casefold())
        if (
            type(item.get("size")) is not int
            or item["size"] < 1
            or not isinstance(item.get("mime"), str)
            or not item["mime"]
        ):
            raise DaemonGenerationError("project file-list size/mime is invalid")
        if item["size"] > MAX_FILE_BYTES:
            raise DaemonGenerationError("project file metadata exceeds resource bounds")
        total_bytes += item["size"]
        if total_bytes > MAX_TOTAL_BYTES:
            raise DaemonGenerationError("project file metadata exceeds resource bounds")
        normalized.append(dict(item))
    normalized.sort(key=lambda item: item["name"])
    return normalized, canonical_response_bytes(normalized)


def _captured_files(
    daemon: OpenDesignDaemonPort,
    project_id: str,
    snapshot: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    manifest: list[dict[str, Any]] = []
    contents: dict[str, bytes] = {}
    for item in snapshot:
        path = item["name"]
        first_type, first = daemon.get_file(project_id, path)
        second_type, second = daemon.get_file(project_id, path)
        if first_type != second_type or first != second:
            raise DaemonGenerationError(f"project file changed across double fetch: {path}")
        if first_type != item["mime"] or len(first) != item["size"]:
            raise DaemonGenerationError(f"project file bytes do not match listed metadata: {path}")
        digest = _sha256(first)
        contents[path] = first
        manifest.append(
            {
                "path": path,
                "media_type": first_type,
                "size_bytes": len(first),
                "sha256": digest,
                "content_base64": base64.b64encode(first).decode("ascii"),
            }
        )
    return manifest, contents


def _run_generation_sequence_inner(
    daemon: OpenDesignDaemonPort,
    request: Mapping[str, Any],
    design_package: Mapping[str, Any],
    *,
    sleeper: Callable[[float], None] = time.sleep,
    max_polls: int = 120,
    progress: dict[str, Any],
) -> dict[str, Any]:
    """Generate and capture one closed, candidate-only Open Design bundle."""

    progress["failure_stage"] = "request_validation"
    task_id, asset_slot, slots = _validate_request(request)
    project_id = _project_id(task_id, asset_slot)
    progress["project_id"] = project_id
    progress["failure_stage"] = "design_reference"
    validate_design_reference_package(design_package)
    design_digest = design_reference_package_sha256(design_package)
    progress["failure_stage"] = "preflight"
    binding = _validate_binding(daemon.preflight())
    project_name = "FLAi candidate"
    progress["failure_stage"] = "create_project"
    progress["unreconciled_upstream_side_effects_may_exist"] = True
    created = daemon.create_project(project_id, project_name)
    conversation_id = _validate_project_result(
        created,
        project_id=project_id,
        project_name=project_name,
        design_system_id=binding["design_system_id"],
    )
    progress["failure_stage"] = "start_run"
    started = daemon.start_run(
        project_id,
        conversation_id,
        _prompt(asset_slot, slots, design_package),
    )
    run_id, assistant_id = _validate_started(started, conversation_id)
    progress["run_id"] = run_id

    terminal = False
    execution_design_digest: str | None = None
    progress["failure_stage"] = "poll_run"
    for poll_index in range(max_polls):
        status_payload = daemon.get_run(run_id)
        status, observed_execution_digest = _validate_run(
            status_payload,
            run_id=run_id,
            project_id=project_id,
            conversation_id=conversation_id,
            assistant_id=assistant_id,
            binding=binding,
        )
        if status == "succeeded":
            terminal = True
            execution_design_digest = observed_execution_digest
            break
        if status in {"failed", "canceled"}:
            raise DaemonGenerationError(f"Open Design run ended with status={status}")
        if poll_index + 1 < max_polls:
            sleeper(15.0)
    if not terminal:
        raise DaemonGenerationError("Open Design run polling limit reached")
    if execution_design_digest is None:
        raise DaemonGenerationError("Open Design run has no design-system execution digest")

    progress["failure_stage"] = "result_package"
    result_package = daemon.get_result_package(run_id)
    _validate_result_package(
        result_package,
        run_id=run_id,
        project_id=project_id,
        conversation_id=conversation_id,
        assistant_id=assistant_id,
        agent_id=binding["agent_id"],
    )
    progress["failure_stage"] = "list_files_before"
    before, before_bytes = _file_snapshot(daemon.list_files(project_id))
    if result_package["project"]["fileCount"] != len(before):
        raise DaemonGenerationError("result-package fileCount does not match exact file list")
    progress["failure_stage"] = "capture_files"
    files, contents = _captured_files(daemon, project_id, before)
    progress["failure_stage"] = "candidate_policy"
    try:
        png_info = validate_candidate_bundle(
            (item["path"], item["media_type"], contents[item["path"]]) for item in files
        )
    except CandidatePolicyError as exc:
        raise DaemonGenerationError(f"candidate safety policy rejected the bundle: {exc}") from exc
    progress["failure_stage"] = "list_files_after"
    after, after_bytes = _file_snapshot(daemon.list_files(project_id))
    if before_bytes != after_bytes or before != after:
        raise DaemonGenerationError("project file list changed during exact capture")

    progress["failure_stage"] = "finalize_candidate"
    by_path = {item["path"]: item for item in files}
    source = by_path.get("candidate.html")
    if source is None:
        raise DaemonGenerationError("candidate.html is required as the passive preview source")
    passive_previews: list[dict[str, Any]] = []
    for slot_id in slots:
        contract = COMPARISON_SLOTS[slot_id]
        image_path = f"previews/{slot_id}.png"
        image = by_path.get(image_path)
        dimensions = png_info.get(image_path)
        if image is None or dimensions is None:
            raise DaemonGenerationError(f"required passive PNG is missing: {slot_id}")
        viewport = contract["viewport"]
        if dimensions != {
            "width": viewport["width"] * viewport["dpr"],
            "height": viewport["height"] * viewport["dpr"],
        }:
            raise DaemonGenerationError(f"passive PNG dimensions mismatch: {slot_id}")
        passive_previews.append(
            {
                "slot_id": slot_id,
                "viewport": dict(viewport),
                "state": contract["state"],
                "theme": contract["theme"],
                "locale": contract["locale"],
                "source": {"path": source["path"], "sha256": source["sha256"]},
                "image": {
                    "path": image["path"],
                    "sha256": image["sha256"],
                    "size_bytes": image["size_bytes"],
                    "media_type": "image/png",
                    **dimensions,
                },
                "passive_preview_scan": {
                    "policy": "flai-passive-png/v1",
                    "passed": True,
                    "active_content_executed": False,
                },
            }
        )

    file_set_sha256 = _sha256(
        canonical_response_bytes(
            [
                {key: item[key] for key in ("path", "media_type", "size_bytes", "sha256")}
                for item in files
            ]
        )
    )
    candidate_id = "odc-" + _sha256(
        f"{project_id}\x00{run_id}\x00{file_set_sha256}".encode("utf-8")
    )[:32]
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
        "asset_slot": asset_slot,
        "project_id": project_id,
        "run_id": run_id,
        "daemon_binding": {
            **binding,
            "design_system_execution_sha256": execution_design_digest,
            "model_execution_attested": False,
        },
        "design_reference_package": dict(design_package),
        "design_reference_package_sha256": design_digest,
        "result_package_sha256": _sha256(canonical_response_bytes(result_package)),
        "storage": {"kind": "od-owned", "base_dir": None},
        "file_set_sha256": file_set_sha256,
        "files": files,
        "passive_previews": passive_previews,
        "safety_scan": {
            "policy": "flai-open-design-passive-candidate/v1",
            "passed": True,
            "file_count": len(files),
            "total_bytes": sum(item["size_bytes"] for item in files),
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


def run_generation_sequence(
    daemon: OpenDesignDaemonPort,
    request: Mapping[str, Any],
    design_package: Mapping[str, Any],
    *,
    sleeper: Callable[[float], None] = time.sleep,
    max_polls: int = 120,
) -> dict[str, Any]:
    """Generate one candidate while retaining a fail-closed upstream progress witness."""

    progress: dict[str, Any] = {
        "failure_stage": "request_validation",
        "project_id": None,
        "run_id": None,
        "unreconciled_upstream_side_effects_may_exist": False,
    }
    try:
        return _run_generation_sequence_inner(
            daemon,
            request,
            design_package,
            sleeper=sleeper,
            max_polls=max_polls,
            progress=progress,
        )
    except Exception as exc:
        if isinstance(exc, DaemonGenerationError) and exc.failure_stage is not None:
            raise
        raise DaemonGenerationError(
            str(exc),
            failure_stage=progress["failure_stage"],
            project_id=progress["project_id"],
            run_id=progress["run_id"],
            unreconciled_upstream_side_effects_may_exist=progress[
                "unreconciled_upstream_side_effects_may_exist"
            ],
        ) from exc
