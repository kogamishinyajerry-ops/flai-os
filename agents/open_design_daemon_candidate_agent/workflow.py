"""Atomic, candidate-only packaging for the Open Design daemon trial."""

from __future__ import annotations

import base64
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError as JsonSchemaSchemaError
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

from tools_impl.open_design_daemon.policy import validate_safe_path
from tools_impl.open_design_daemon.service import DaemonGenerationError, validate_tool_response
from tools_impl.open_design_fixture.design_reference import canonical_json_bytes, sha256_bytes

_TOOL_ID = "open_design_daemon_generate"
_OUTPUT_SCHEMA = Path(__file__).with_name("output_schema.json")
_BUNDLE_DIR = "open_design_daemon_candidate_bundle"
_CANDIDATE_MANIFEST = "open_design_daemon_candidates.json"
_PROVENANCE = "open_design_daemon_provenance.json"
_DESIGN_PACKAGE = "flai_design_reference_package.json"
_REVIEW = "OPEN_DESIGN_DAEMON_REVIEW.md"


def _fail(message: str) -> dict[str, Any]:
    return {"status": "failed", "outputs": [], "error_message": message}


def _stable_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"


def _render_review(tool_output: dict[str, Any]) -> bytes:
    lines = [
        "# Open Design daemon 候选 · 人工审核包",
        "",
        "> **AMBER / WAITING REVIEW · UNTRUSTED GENERATED**",
        "> 此包由 mock=false 的 loopback daemon trial 生成，但并未获得生产就绪、视觉质量或发布证明。",
        "> HTML/SVG 只作附件，禁止执行；可见比较只允许使用通过结构扫描的 PNG。",
        "> 人是唯一签发者；本次审核不等同于资产选择或发布批准。",
        "",
        "## 固定身份",
        "",
        f"- Candidate ID：`{tool_output['candidate_id']}`",
        f"- Asset slot：`{tool_output['asset_slot']}`",
        f"- Open Design project：`{tool_output['project_id']}`",
        f"- Open Design run：`{tool_output['run_id']}`",
        f"- File-set SHA256：`{tool_output['file_set_sha256']}`",
        f"- Design reference SHA256：`{tool_output['design_reference_package_sha256']}`",
        f"- Result-package SHA256：`{tool_output['result_package_sha256']}`",
        f"- Adapter response SHA256：`{tool_output['response_sha256']}`",
        "",
        "## 审核边界",
        "",
        "- [ ] daemon/version/channel/Agent/请求模型/published design-system digest 是否与 provenance 一致？",
        "- [ ] 是否明确 provenance 的 model_execution_attested=false，未把请求模型误写成实际执行模型证明？",
        "- [ ] 是否只通过 PNG 查看候选，且未执行 HTML/SVG？",
        "- [ ] trust color、focus、dark、mobile、reduced-motion 与状态语义是否符合 FLAi SSOT？",
        "- [ ] 是否明确这只是 candidate review，未选择资产、未批准发布、未写入源码？",
        "- [ ] 若拒绝，是否记录结构化原因供后续判断资产化？",
        "",
        "`release_effect=none`；本 workflow 不含任何 source write、promotion 或 publish 动作。",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _build_artifacts(
    tool_output: dict[str, Any],
) -> tuple[dict[str, tuple[bytes, str, str, str | None]], str, dict[str, Any]]:
    files = tool_output["files"]
    preview_paths = {item["image"]["path"] for item in tool_output["passive_previews"]}
    captured_files = [
        {
            "source_path": item["path"],
            "bundle_relpath": f"captured/{item['path']}",
            "media_type": item["media_type"],
            "size_bytes": item["size_bytes"],
            "sha256": item["sha256"],
            "role": "passive_preview" if item["path"] in preview_paths else "candidate_source",
        }
        for item in files
    ]
    promotable_file = next(
        item for item in files if item["path"] == "previews/default_desktop_light.png"
    )
    promotable_preview = next(
        item
        for item in tool_output["passive_previews"]
        if item["slot_id"] == "default_desktop_light"
    )
    if promotable_preview["image"] != {
        "path": promotable_file["path"],
        "sha256": promotable_file["sha256"],
        "size_bytes": promotable_file["size_bytes"],
        "media_type": "image/png",
        "width": 1440,
        "height": 900,
    }:
        raise ValueError("fixed promotable preview lost its exact PNG binding")
    promotable_asset = {
        "slot_id": "default_desktop_light",
        "source_path": promotable_file["path"],
        "bundle_relpath": f"captured/{promotable_file['path']}",
        "media_type": "image/png",
        "size_bytes": promotable_file["size_bytes"],
        "sha256": promotable_file["sha256"],
    }
    candidate_manifest = {
        "schema_version": "open-design-daemon-candidate-manifest/v1",
        "review_contract": "open-design-candidate/v1",
        "generator_kind": "open_design_daemon",
        "candidate_id": tool_output["candidate_id"],
        "asset_slot": tool_output["asset_slot"],
        "classification": "sensitive",
        "project_id": tool_output["project_id"],
        "run_id": tool_output["run_id"],
        "execution_trust": "untrusted_generated",
        "production_readiness": "trial_not_attested",
        "candidate_only": True,
        "release_effect": "none",
        "mock": False,
        "design_reference_package_sha256": tool_output["design_reference_package_sha256"],
        "result_package_sha256": tool_output["result_package_sha256"],
        "file_set_sha256": tool_output["file_set_sha256"],
        "promotable_asset": promotable_asset,
        "captured_files": captured_files,
        "passive_previews": tool_output["passive_previews"],
    }
    candidate_manifest_bytes = _stable_json(candidate_manifest)
    candidate_manifest_sha256 = sha256_bytes(candidate_manifest_bytes)
    provenance = {
        "schema_version": "open-design-daemon-provenance/v1",
        "review_contract": "open-design-candidate/v1",
        "generator_kind": "open_design_daemon",
        "candidate_manifest_sha256": candidate_manifest_sha256,
        "candidate_id": tool_output["candidate_id"],
        "asset_slot": tool_output["asset_slot"],
        "classification": "sensitive",
        "execution_trust": "untrusted_generated",
        "production_readiness": "trial_not_attested",
        "candidate_only": True,
        "release_effect": "none",
        "mock": False,
        "project_id": tool_output["project_id"],
        "run_id": tool_output["run_id"],
        "daemon_binding": tool_output["daemon_binding"],
        "storage": tool_output["storage"],
        "design_reference_package_sha256": tool_output["design_reference_package_sha256"],
        "result_package_sha256": tool_output["result_package_sha256"],
        "file_set_sha256": tool_output["file_set_sha256"],
        "response_sha256": tool_output["response_sha256"],
        "safety_scan": tool_output["safety_scan"],
    }
    package_bytes = canonical_json_bytes(tool_output["design_reference_package"])
    if sha256_bytes(package_bytes) != tool_output["design_reference_package_sha256"]:
        raise ValueError("design reference package bytes do not match its digest")
    artifacts: dict[str, tuple[bytes, str, str, str | None]] = {
        _CANDIDATE_MANIFEST: (
            candidate_manifest_bytes,
            "application/json",
            "candidate_manifest",
            None,
        ),
        _PROVENANCE: (_stable_json(provenance), "application/json", "provenance", None),
        _DESIGN_PACKAGE: (package_bytes, "application/json", "design_reference", None),
        _REVIEW: (_render_review(tool_output), "text/markdown", "review", None),
    }
    for item in files:
        try:
            content = base64.b64decode(item["content_base64"], validate=True)
        except ValueError as exc:
            raise ValueError(f"captured file base64 is invalid: {item['path']}") from exc
        relpath = f"captured/{item['path']}"
        artifacts[relpath] = (
            content,
            item["media_type"],
            "passive_preview" if item["path"] in preview_paths else "candidate_source",
            item["path"],
        )
    return artifacts, candidate_manifest_sha256, promotable_asset


def _validate_agent_output(output: dict[str, Any]) -> None:
    schema = json.loads(_OUTPUT_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(output)


def _validated_empty_output_dir(raw_output_dir: Any) -> Path:
    if not isinstance(raw_output_dir, str) or not raw_output_dir:
        raise ValueError("output_dir 必须由 runtime 显式注入")
    output_dir = Path(raw_output_dir)
    if not output_dir.is_absolute():
        raise ValueError("output_dir 必须是绝对路径")
    if output_dir.is_symlink() or not output_dir.is_dir():
        raise ValueError("output_dir 必须是 runtime 创建的常规目录")
    if output_dir.parent.is_symlink():
        raise ValueError("output_dir 父目录不得是符号链接")
    if any(output_dir.iterdir()):
        raise ValueError("output_dir 必须为空，拒绝覆盖")
    return output_dir


def _publish_atomically(
    output_dir: Path,
    artifacts: dict[str, tuple[bytes, str, str, str | None]],
) -> None:
    bundle_dir = output_dir / _BUNDLE_DIR
    if bundle_dir.exists() or bundle_dir.is_symlink():
        raise OSError("candidate bundle target already exists")
    staging = Path(tempfile.mkdtemp(prefix=".open-design-daemon-staging-", dir=output_dir))
    published = False
    try:
        for relpath, (content, _media_type, _role, _source_path) in artifacts.items():
            validate_safe_path(relpath)
            path = staging.joinpath(*relpath.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as handle:
                handle.write(content)
            if sha256_bytes(path.read_bytes()) != sha256_bytes(content):
                raise OSError(f"write-after-read digest mismatch: {relpath}")
        if (
            output_dir.is_symlink()
            or not output_dir.is_dir()
            or list(output_dir.iterdir()) != [staging]
            or bundle_dir.exists()
            or bundle_dir.is_symlink()
        ):
            raise OSError("output_dir drifted before atomic publication")
        os.replace(staging, bundle_dir)
        published = True
    finally:
        if not published:
            shutil.rmtree(staging, ignore_errors=True)


def run(context: dict[str, Any]) -> dict[str, Any]:
    tool_registry = context.get("tool_registry")
    inputs = context.get("inputs")
    event_logger = context.get("event_logger")
    if tool_registry is None or not isinstance(inputs, dict):
        return _fail("tool_registry/inputs 未注入，拒绝生成 Open Design daemon 候选")
    try:
        output_dir = _validated_empty_output_dir(context.get("output_dir"))
    except (ValueError, OSError) as exc:
        return _fail(f"Open Design daemon 输出目录校验失败，未调用工具：{exc}")
    if event_logger is not None:
        event_logger.log(
            "open_design_daemon_candidate_started",
            {
                "generator_mode": "loopback_daemon_trial",
                "mock": False,
                "execution_trust": "untrusted_generated",
                "candidate_only": True,
            },
        )
    try:
        tool_output = tool_registry.call(_TOOL_ID, inputs)
    except Exception as exc:  # noqa: BLE001 - tool boundary becomes honest task failure
        return _fail(f"Open Design daemon 工具调用失败：{exc.__class__.__name__}: {exc}")
    if not isinstance(tool_output, dict) or tool_output.get("status") != "success":
        message = tool_output.get("error_message") if isinstance(tool_output, dict) else "工具返回非法"
        if isinstance(tool_output, dict):
            def witness_token(value: Any) -> str:
                return " ".join(value.split())[:160] if isinstance(value, str) and value else "unknown"

            witness = "; ".join(
                [
                    f"failure_stage={witness_token(tool_output.get('failure_stage'))}",
                    f"project_id={witness_token(tool_output.get('project_id'))}",
                    f"run_id={witness_token(tool_output.get('run_id'))}",
                    "upstream_reconciliation_required="
                    + (
                        "true"
                        if tool_output.get(
                            "unreconciled_upstream_side_effects_may_exist"
                        )
                        is True
                        else "false"
                    ),
                ]
            )
            return _fail(f"Open Design daemon 未产出候选：{message}；{witness}")
        return _fail(f"Open Design daemon 未产出候选：{message}")
    try:
        validate_tool_response(tool_output)
        artifacts, candidate_manifest_sha256, promotable_asset = _build_artifacts(tool_output)
        artifact_manifest = [
            {
                "filename": Path(relpath).name,
                "bundle_relpath": relpath,
                "media_type": media_type,
                "role": role,
                "sha256": sha256_bytes(content),
                "source_path": source_path,
            }
            for relpath, (content, media_type, role, source_path) in sorted(artifacts.items())
        ]
        output = {
            "schema_version": "open-design-daemon-candidate-output/v1",
            "review_contract": "open-design-candidate/v1",
            "generator_kind": "open_design_daemon",
            "candidate_manifest_sha256": candidate_manifest_sha256,
            "candidate_id": tool_output["candidate_id"],
            "asset_slot": tool_output["asset_slot"],
            "classification": "sensitive",
            "project_id": tool_output["project_id"],
            "run_id": tool_output["run_id"],
            "result_package_sha256": tool_output["result_package_sha256"],
            "promotable_asset": promotable_asset,
            "generator_mode": "loopback_daemon_trial",
            "execution_trust": "untrusted_generated",
            "production_readiness": "trial_not_attested",
            "candidate_only": True,
            "release_effect": "none",
            "human_review_required": True,
            "mock": False,
            "passive_previews": tool_output["passive_previews"],
            "artifacts": artifact_manifest,
        }
        _validate_agent_output(output)
    except (
        ValueError,
        DaemonGenerationError,
        KeyError,
        TypeError,
        JsonSchemaValidationError,
        JsonSchemaSchemaError,
    ) as exc:
        return _fail(f"Open Design daemon 候选自校验失败，未落盘：{exc}")
    try:
        _publish_atomically(output_dir, artifacts)
    except (OSError, ValueError) as exc:
        return _fail(f"Open Design daemon 候选原子落盘失败：{exc}")
    if event_logger is not None:
        try:
            event_logger.log(
                "open_design_daemon_candidates_written",
                {
                    "candidate_id": tool_output["candidate_id"],
                    "asset_slot": tool_output["asset_slot"],
                    "candidate_manifest_sha256": candidate_manifest_sha256,
                    "classification": "sensitive",
                    "execution_trust": "untrusted_generated",
                    "candidate_only": True,
                    "human_review_required": True,
                    "mock": False,
                },
            )
        except Exception:
            # Publication is already durable. Let Runtime register the returned
            # artifact manifest and waiting_review state instead of splitting
            # task=failed from an orphaned complete bundle.
            pass
    return {"status": "success", "outputs": [output]}
