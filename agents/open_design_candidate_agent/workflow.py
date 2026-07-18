"""Candidate-only Open Design fixture workflow with self-validation."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError as JsonSchemaSchemaError
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

from tools_impl.open_design_fixture.client import validate_tool_response
from tools_impl.open_design_fixture.design_reference import (
    canonical_json_bytes,
    design_reference_package_sha256,
    sha256_bytes,
)

_TOOL_ID = "open_design_fixture_generate"
_OUTPUT_SCHEMA = Path(__file__).with_name("output_schema.json")
_DESIGN_PACKAGE = "flai_design_reference_package.json"
_CANDIDATES_INDEX = "open_design_candidates.json"
_PROVENANCE = "open_design_provenance.json"
_REVIEW = "OPEN_DESIGN_REVIEW.md"
_BUNDLE_DIR = "open_design_candidate_bundle"


def _fail(message: str) -> dict[str, Any]:
    return {"status": "failed", "outputs": [], "error_message": message}


def _stable_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"


def _render_review(tool_output: dict[str, Any]) -> bytes:
    lines = [
        "# Open Design 协议契约夹具 · 人工审核包",
        "",
        "> **AMBER / WAITING REVIEW · MOCK**：这些资产来自 `open_design_fixture_generate`",
        "> （`mock=true`）的手工 machine-only 协议契约夹具，不是生产 daemon 真跑结果、",
        "> 产品 UI 资产或本轮视觉 QA 结论。它们只供自动化咬合与协议证据复核，",
        "> `release_effect=none`，禁止产品渲染/采纳/发布，也不会替代工程师签发。",
        "",
        "## 可信来源",
        "",
        f"- Fixture：`{tool_output['fixture_id']}`",
        f"- Fixture SHA256：`{tool_output['fixture_sha256']}`",
        f"- 固定请求 SHA256：`{tool_output['request_sha256']}`",
        f"- 工具响应 SHA256：`{tool_output['response_sha256']}`",
        "- 设计引用包：`flai-design-reference-package/v1`",
        f"- 设计引用包 SHA256：`{tool_output['design_reference_package_sha256']}`",
        "- 设计 SSOT：`frontend/src/App.vue`、`docs/design/UI-PARADIGM.md`、",
        "  `docs/design/MOTION-SYSTEM.md`（精确源哈希见 provenance 与设计引用包）。",
        "",
        "## Open Design 生产形状",
        "",
        "本 fixture 按经核对的 MCP 顺序执行：",
    ]
    for index, step in enumerate(tool_output["protocol_trace"], 1):
        lines.append(
            f"{index}. `{step['operation']}` · {step['access']} · {step['status']}"
        )
    lines.extend(
        [
            "",
            "生产接入必须使用新的 `mock=false` tool id，并保持相同顺序；不得把当前 fixture",
            "原地翻牌，也不得把 Open Design 的私有 `.od` 工作目录当作发布真值。",
            "",
            "## 人工协议证据审核清单",
            "",
            "- [ ] 是否确认 HTML/SVG 是手工 machine-only contract fixture，而非真实生成或视觉 QA 结论？",
            "- [ ] SSOT 源哈希、token allowlist 与设计引用包 SHA256 是否机械对账？",
            "- [ ] amber 是否只用于待核/未核，clay 是否只用于动作，未借用 green/teal/red 作装饰？",
            "- [ ] 候选是否保持静态、无 script/iframe/外部资源？",
            "- [ ] 是否明确仍为 candidate only，且禁止进入产品 UI、发布或工程判决链？",
            "- [ ] 是否理解放行只表示协议证据复核，不表示手工 SVG/HTML 获得视觉采纳？",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def _build_artifact_bytes(tool_output: dict[str, Any]) -> dict[str, tuple[bytes, str, str]]:
    package = tool_output["design_reference_package"]
    package_bytes = canonical_json_bytes(package)
    if sha256_bytes(package_bytes) != tool_output["design_reference_package_sha256"]:
        raise ValueError("design reference package bytes do not match package sha256")

    candidate_index = {
        "schema_version": "open-design-candidates/v1",
        "candidate_only": True,
        "fixture_origin": "handcrafted_machine_only_protocol_contract",
        "product_asset": False,
        "visual_qa_conclusion": False,
        "render_or_publish_allowed": False,
        "release_effect": "none",
        "mock": True,
        "fixture_id": tool_output["fixture_id"],
        "design_reference_package_sha256": tool_output["design_reference_package_sha256"],
        "candidates": [
            {key: value for key, value in candidate.items() if key != "content"}
            for candidate in tool_output["candidates"]
        ],
    }
    provenance = {
        "schema_version": "open-design-provenance/v1",
        "candidate_only": True,
        "fixture_origin": "handcrafted_machine_only_protocol_contract",
        "product_asset": False,
        "visual_qa_conclusion": False,
        "render_or_publish_allowed": False,
        "release_effect": "none",
        "human_review_required": True,
        "generator_mode": "fixture",
        "mock": True,
        "production_daemon_used": False,
        "fixture_id": tool_output["fixture_id"],
        "fixture_sha256": tool_output["fixture_sha256"],
        "request_sha256": tool_output["request_sha256"],
        "response_sha256": tool_output["response_sha256"],
        "design_reference_package_sha256": tool_output["design_reference_package_sha256"],
        "design_sources": package["sources"],
        "trust_color_constraints": package["trust_color_constraints"],
        "open_design_protocol": {
            "source": "apps/daemon/src/mcp.ts",
            "source_sha256": "6f8f4a02984604418a829952114875a7ce364eb62abd36493dbd4c4e5b57341a",
            "upstream_revision": "e06bff69",
            "trace": tool_output["protocol_trace"],
        },
    }
    artifacts: dict[str, tuple[bytes, str, str]] = {
        _DESIGN_PACKAGE: (package_bytes, "application/json", "design_reference"),
        _CANDIDATES_INDEX: (_stable_json(candidate_index), "application/json", "candidate_index"),
        _PROVENANCE: (_stable_json(provenance), "application/json", "provenance"),
        _REVIEW: (_render_review(tool_output), "text/markdown", "review"),
    }
    for candidate in tool_output["candidates"]:
        artifacts[candidate["filename"]] = (
            candidate["content"].encode("utf-8"),
            candidate["media_type"],
            "candidate",
        )
    return artifacts


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
    if output_dir.is_symlink():
        raise ValueError("output_dir 不得是符号链接")
    if not output_dir.is_dir():
        raise ValueError("output_dir 必须是 runtime 已创建的目录")
    if output_dir.parent.is_symlink():
        raise ValueError("output_dir 父目录不得是符号链接")
    if any(output_dir.iterdir()):
        raise ValueError("output_dir 必须为空，拒绝覆盖既有产物")
    return output_dir


def _publish_artifacts_atomically(
    output_dir: Path,
    artifacts: dict[str, tuple[bytes, str, str]],
) -> None:
    """Write a complete package, then expose a new child directory atomically."""

    bundle_dir = output_dir / _BUNDLE_DIR
    if bundle_dir.exists() or bundle_dir.is_symlink():
        raise OSError(f"目标 bundle 已存在，拒绝覆盖：{_BUNDLE_DIR}")
    staging = Path(tempfile.mkdtemp(prefix=".open-design-staging-", dir=output_dir))
    published = False
    try:
        for filename, (content, _media_type, _role) in artifacts.items():
            if Path(filename).name != filename:
                raise OSError(f"产物文件名不是安全 basename：{filename}")
            path = staging / filename
            with path.open("xb") as handle:
                handle.write(content)
            if sha256_bytes(path.read_bytes()) != sha256_bytes(content):
                raise OSError(f"写后 SHA256 不一致：{filename}")

        # The runtime-created output root remains in place. The destination
        # child must not exist: replacing an existing directory is unsupported
        # by Win32 MoveFileEx, while a same-volume rename to a new child is
        # atomic on both target Windows and POSIX deployments.
        entries = list(output_dir.iterdir())
        if (
            output_dir.is_symlink()
            or not output_dir.is_dir()
            or entries != [staging]
            or bundle_dir.exists()
            or bundle_dir.is_symlink()
        ):
            raise OSError("output_dir 在发布前发生漂移，拒绝覆盖")
        os.replace(staging, bundle_dir)
        published = True
    finally:
        if not published:
            shutil.rmtree(staging, ignore_errors=True)


def run(context: dict[str, Any]) -> dict[str, Any]:
    tool_registry = context.get("tool_registry")
    event_logger = context.get("event_logger")
    inputs = context.get("inputs")
    if tool_registry is None or not isinstance(inputs, dict):
        return _fail("tool_registry/inputs 未注入，拒绝生成 Open Design 候选")
    try:
        output_dir = _validated_empty_output_dir(context.get("output_dir"))
    except (ValueError, OSError) as exc:
        return _fail(f"Open Design 输出目录校验失败，未调用工具：{exc}")

    if event_logger is not None:
        event_logger.log(
            "open_design_candidate_started",
            {"generator_mode": "fixture", "mock": True, "candidate_only": True},
        )
    try:
        tool_output = tool_registry.call(_TOOL_ID, inputs)
    except Exception as exc:  # noqa: BLE001 - tool boundary failure becomes honest task failure
        return _fail(f"Open Design fixture 工具调用失败：{exc.__class__.__name__}: {exc}")
    if not isinstance(tool_output, dict) or tool_output.get("status") != "success":
        message = tool_output.get("error_message") if isinstance(tool_output, dict) else "工具返回值非法"
        return _fail(f"Open Design fixture 未产出候选：{message}")

    try:
        validate_tool_response(tool_output)
        artifacts = _build_artifact_bytes(tool_output)
        artifact_manifest = [
            {
                "filename": filename,
                "media_type": media_type,
                "role": role,
                "sha256": sha256_bytes(content),
            }
            for filename, (content, media_type, role) in sorted(artifacts.items())
        ]
        output = {
            "schema_version": "open-design-candidate-output/v1",
            "candidate_only": True,
            "release_effect": "none",
            "human_review_required": True,
            "generator_mode": "fixture",
            "mock": True,
            "production_daemon_used": False,
            "fixture_id": tool_output["fixture_id"],
            "fixture_sha256": tool_output["fixture_sha256"],
            "request_sha256": tool_output["request_sha256"],
            "response_sha256": tool_output["response_sha256"],
            "design_reference_package_sha256": tool_output["design_reference_package_sha256"],
            "candidate_count": len(tool_output["candidates"]),
            "protocol_trace": tool_output["protocol_trace"],
            "artifacts": artifact_manifest,
        }
        _validate_agent_output(output)
    except (ValueError, KeyError, TypeError, JsonSchemaValidationError, JsonSchemaSchemaError) as exc:
        return _fail(f"Open Design 候选自校验失败，未落盘：{exc}")

    try:
        _publish_artifacts_atomically(output_dir, artifacts)
    except OSError as exc:
        return _fail(f"Open Design 候选落盘失败：{exc}")

    # The design package artifact uses canonical bytes with no trailing newline,
    # therefore its file SHA is exactly the package SHA carried in provenance.
    if design_reference_package_sha256(tool_output["design_reference_package"]) != tool_output[
        "design_reference_package_sha256"
    ]:
        return _fail("Open Design 设计引用包写后复核失败")

    if event_logger is not None:
        event_logger.log(
            "open_design_candidates_written",
            {
                "candidate_count": len(tool_output["candidates"]),
                "candidate_only": True,
                "human_review_required": True,
                "mock": True,
                "artifacts": [item["filename"] for item in artifact_manifest],
            },
        )
    return {"status": "success", "outputs": [output]}
