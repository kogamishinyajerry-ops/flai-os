"""Deterministic Work Case -> Task Pattern -> Skill draft projection.

The builder is intentionally pure.  It receives an already-resolved Guide
conversation plus an engineer-authored generalization and returns an immutable
preview document.  It has no repository, Registry, model, clock, or execution
dependency and therefore cannot save, register, promote, or run the draft.
"""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections.abc import Mapping
from typing import Any

SCHEMA_VERSION = "asset_draft_bundle.v1"
BUILDER_VERSION = "asset_draft_builder.v1"
VALIDATION_POLICY_VERSION = "core.v1"

_GENERALIZATION_FIELDS = (
    "title",
    "trigger",
    "desired_outcome",
    "inputs",
    "outputs",
    "steps",
    "evidence_requirements",
    "human_decision_points",
    "limitations",
)
_SCALAR_FIELDS = frozenset({"title", "trigger", "desired_outcome"})
_LIST_FIELDS = tuple(field for field in _GENERALIZATION_FIELDS if field not in _SCALAR_FIELDS)
_SCALAR_LIMITS = {"title": 160, "trigger": 2000, "desired_outcome": 2000}
_LIST_MAX_ITEMS = 20
_LIST_ITEM_MAX_CHARS = 1000
_REVIEW_REQUIREMENTS = [
    "核对草稿是否忠实对应原始 Work Case",
    "核对步骤、输入输出与不适用边界是否真的可复用",
    "核对人工判断点与证据要求是否充分",
]


class AssetDraftInputError(ValueError):
    """The caller supplied a structurally invalid generalization."""


class AssetDraftSourceError(ValueError):
    """The resolved source cannot honestly form a Work Case."""


class AssetDraftProjectionError(RuntimeError):
    """The source record is malformed and cannot be projected safely."""


class AssetDraftBuilder:
    """Build a content-addressed draft bundle behind one public entry point."""

    def preview(
        self,
        *,
        conversation: Mapping[str, Any],
        generalization: Mapping[str, Any],
    ) -> dict[str, Any]:
        work_case_basis, work_case = _project_work_case(conversation)
        normalized = _normalize_generalization(generalization)

        source_revision = _digest(work_case_basis)
        work_case["source_revision"] = source_revision

        task_pattern_content = {
            "schema_version": "task_pattern_draft.v1",
            "status": "draft",
            "derived_from_work_case_revision": source_revision,
            "title": normalized["title"],
            "trigger": normalized["trigger"],
            "desired_outcome": normalized["desired_outcome"],
            "inputs": normalized["inputs"],
            "outputs": normalized["outputs"],
            "steps": normalized["steps"],
            "evidence_requirements": normalized["evidence_requirements"],
            "human_decision_points": normalized["human_decision_points"],
            "limitations": normalized["limitations"],
        }
        task_pattern_digest = _digest(task_pattern_content)
        task_pattern = {
            **task_pattern_content,
            "suggested_id": f"task_pattern_candidate_{_digest_hex(task_pattern_content)[:12]}",
            "content_digest": task_pattern_digest,
        }

        description_parts = [normalized["desired_outcome"]]
        if normalized["trigger"]:
            description_parts.append(f"适用于：{normalized['trigger']}")
        skill_content = {
            "schema_version": "skill_draft.v1",
            "status": "draft",
            "operationalizes_task_pattern_digest": task_pattern_digest,
            "name": normalized["title"],
            "description": "；".join(part for part in description_parts if part),
            "when_to_use": normalized["trigger"],
            "when_not_to_use": normalized["limitations"],
            "inputs": normalized["inputs"],
            "outputs": normalized["outputs"],
            "instructions": normalized["steps"],
            "verification": normalized["evidence_requirements"],
            "human_boundaries": normalized["human_decision_points"],
        }
        skill_digest = _digest(skill_content)
        skill = {
            **skill_content,
            "suggested_id": f"skill_candidate_{_digest_hex(skill_content)[:12]}",
            "content_digest": skill_digest,
        }

        issues = _validate(normalized)
        blocking_count = sum(issue["severity"] == "blocking" for issue in issues)
        warning_count = sum(issue["severity"] == "warning" for issue in issues)
        ready = blocking_count == 0

        bundle_without_digest = {
            "schema_version": SCHEMA_VERSION,
            "builder_version": BUILDER_VERSION,
            "status": "draft",
            "work_case": work_case,
            "task_pattern": task_pattern,
            "skill": skill,
            "validation": {
                "schema_version": "asset_draft_validation.v1",
                "policy_version": VALIDATION_POLICY_VERSION,
                "state": "ready_for_human_review" if ready else "needs_revision",
                "blocking_count": blocking_count,
                "warning_count": warning_count,
                "issues": issues,
            },
            "review": {
                "required": True,
                "ready": ready,
                "state": "awaiting_human_review" if ready else "not_ready",
                "decision_state": "not_recorded",
                "requirements": list(_REVIEW_REQUIREMENTS),
            },
            "generation": {
                "kind": "deterministic_projection",
                "llm_used": False,
            },
            "effects": {
                "writes_database": False,
                "executes_work": False,
                "registers_asset": False,
                "promotes_asset": False,
            },
        }
        return {
            **bundle_without_digest,
            "draft_digest": _digest(bundle_without_digest),
        }


def _project_work_case(
    conversation: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(conversation, Mapping):
        raise AssetDraftProjectionError("conversation 必须是对象")

    conversation_id = _source_text(
        conversation.get("id"), "conversation.id", max_length=128
    )
    agent_id = _source_text(conversation.get("agent_id"), "conversation.agent_id")
    status = _source_text(conversation.get("status"), "conversation.status")
    if status not in {"active", "concluded", "abandoned"}:
        raise AssetDraftProjectionError("conversation.status 不受支持")
    raw_messages = conversation.get("messages")
    if not isinstance(raw_messages, list):
        raise AssetDraftProjectionError("conversation.messages 必须是数组")

    messages: list[dict[str, Any]] = []
    user_message_count = 0
    attachment_reference_count = 0
    for index, raw in enumerate(raw_messages):
        if not isinstance(raw, Mapping):
            raise AssetDraftProjectionError(f"conversation.messages[{index}] 必须是对象")
        role = _source_text(raw.get("role"), f"conversation.messages[{index}].role")
        if role not in {"user", "assistant"}:
            raise AssetDraftProjectionError(
                f"conversation.messages[{index}].role 不受支持"
            )
        content = _source_text(
            raw.get("content"), f"conversation.messages[{index}].content"
        )
        raw_file_ids = raw.get("file_ids")
        if raw_file_ids is None:
            raw_file_ids = []
        if not isinstance(raw_file_ids, list) or any(
            not isinstance(file_id, str) or not file_id.strip()
            for file_id in raw_file_ids
        ):
            raise AssetDraftProjectionError(
                f"conversation.messages[{index}].file_ids 必须是非空字符串数组"
            )
        message = {
            "id": _optional_source_text(raw.get("id")),
            "role": role,
            "content": content,
            "file_ids": [
                _source_text(
                    file_id,
                    f"conversation.messages[{index}].file_ids",
                )
                for file_id in raw_file_ids
            ],
        }
        if "recommendation" in raw:
            recommendation = raw.get("recommendation")
            if recommendation is not None and not isinstance(recommendation, Mapping):
                raise AssetDraftProjectionError(
                    f"conversation.messages[{index}].recommendation 必须是对象或 null"
                )
            message["recommendation"] = _stable_json_value(recommendation)
        messages.append(message)
        if role == "user":
            user_message_count += 1
        attachment_reference_count += len(raw_file_ids)

    if user_message_count == 0:
        raise AssetDraftSourceError("会话还没有已保存的用户消息，不能形成 Work Case")

    basis = {
        "kind": "conversation",
        "id": conversation_id,
        "agent_id": agent_id,
        "status": status,
        "messages": messages,
    }
    projected = {
        "source_kind": "conversation",
        "source_id": conversation_id,
        "source_state": "platform_resolved",
        "conversation_status": status,
        "message_count": len(messages),
        "user_message_count": user_message_count,
        "attachment_reference_count": attachment_reference_count,
    }
    return basis, projected


def _normalize_generalization(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AssetDraftInputError("generalization 必须是对象")
    if any(not isinstance(key, str) for key in value):
        raise AssetDraftInputError("generalization 字段名必须是字符串")
    unknown = sorted(set(value) - set(_GENERALIZATION_FIELDS))
    if unknown:
        raise AssetDraftInputError(f"generalization 含未知字段：{', '.join(unknown)}")
    missing = sorted(set(_GENERALIZATION_FIELDS) - set(value))
    if missing:
        raise AssetDraftInputError(f"generalization 缺少字段：{', '.join(missing)}")

    normalized: dict[str, Any] = {}
    for field in _GENERALIZATION_FIELDS:
        raw = value[field]
        if field in _SCALAR_FIELDS:
            if not isinstance(raw, str):
                raise AssetDraftInputError(f"generalization.{field} 必须是字符串")
            if len(raw) > _SCALAR_LIMITS[field]:
                raise AssetDraftInputError(
                    f"generalization.{field} 不得超过 {_SCALAR_LIMITS[field]} 字符"
                )
            normalized_text = _input_text(raw, f"generalization.{field}")
            if len(normalized_text) > _SCALAR_LIMITS[field]:
                raise AssetDraftInputError(
                    f"generalization.{field} 不得超过 {_SCALAR_LIMITS[field]} 字符"
                )
            normalized[field] = normalized_text
            continue
        if not isinstance(raw, list):
            raise AssetDraftInputError(f"generalization.{field} 必须是字符串数组")
        if len(raw) > _LIST_MAX_ITEMS:
            raise AssetDraftInputError(
                f"generalization.{field} 不得超过 {_LIST_MAX_ITEMS} 项"
            )
        if any(not isinstance(item, str) for item in raw):
            raise AssetDraftInputError(f"generalization.{field} 必须是字符串数组")
        if any(len(item) > _LIST_ITEM_MAX_CHARS for item in raw):
            raise AssetDraftInputError(
                f"generalization.{field} 的数组项不得超过 {_LIST_ITEM_MAX_CHARS} 字符"
            )
        normalized_items = [
            _input_text(item, f"generalization.{field}") for item in raw
        ]
        if any(not item for item in normalized_items):
            raise AssetDraftInputError(f"generalization.{field} 的数组项不得为空白")
        if any(len(item) > _LIST_ITEM_MAX_CHARS for item in normalized_items):
            raise AssetDraftInputError(
                f"generalization.{field} 的数组项不得超过 {_LIST_ITEM_MAX_CHARS} 字符"
            )
        normalized[field] = normalized_items
    return normalized


def _validate(value: Mapping[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []

    def blocking(code: str, path: str, message: str) -> None:
        issues.append(
            {"code": code, "severity": "blocking", "path": path, "message": message}
        )

    if not value["title"]:
        blocking("task_pattern.title.required", "/task_pattern/title", "请给这类工作一个可辨认的名称")
    if not value["trigger"]:
        blocking("task_pattern.trigger.required", "/task_pattern/trigger", "请说明什么情况下应再次使用这项方法")
    if not value["desired_outcome"]:
        blocking("task_pattern.outcome.required", "/task_pattern/desired_outcome", "请说明这类工作必须交付什么结果")
    if not value["inputs"]:
        blocking("task_pattern.inputs.required", "/task_pattern/inputs", "至少声明一项开始前必须取得的输入")
    if not value["outputs"]:
        blocking("task_pattern.outputs.required", "/task_pattern/outputs", "至少声明一项必须留下的输出")
    if len(value["steps"]) < 2:
        blocking("skill.instructions.minimum", "/skill/instructions", "至少写出两步稳定、可复用的方法")
    if not value["human_decision_points"]:
        blocking("skill.human_boundary.required", "/skill/human_boundaries", "至少声明一个必须停下来等待工程师判断的位置")
    if not value["evidence_requirements"]:
        blocking("skill.verification.required", "/skill/verification", "至少声明一项证明工作已做且可核的依据")
    if not value["limitations"]:
        blocking("skill.when_not_to_use.required", "/skill/when_not_to_use", "至少声明一种绝不能直接套用这项方法的情况")

    for field in _LIST_FIELDS:
        seen: set[str] = set()
        duplicate = False
        for item in value[field]:
            key = item.casefold()
            if key in seen:
                duplicate = True
            seen.add(key)
        if duplicate:
            issues.append(
                {
                    "code": f"generalization.{field}.duplicate",
                    "severity": "warning",
                    "path": f"/generalization/{field}",
                    "message": "存在规范化后重复项；草稿已原样保留，请人工判断是否合并",
                }
            )
    return issues


def _source_text(value: Any, field: str, *, max_length: int | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AssetDraftProjectionError(f"{field} 必须是非空字符串")
    normalized = _normalize_text(value)
    _ensure_utf8(normalized, AssetDraftProjectionError, f"{field} 包含无效 Unicode")
    if max_length is not None and len(normalized) > max_length:
        raise AssetDraftProjectionError(f"{field} 不得超过 {max_length} 字符")
    return normalized


def _optional_source_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise AssetDraftProjectionError("message.id 必须是非空字符串或 null")
    normalized = _normalize_text(value)
    _ensure_utf8(
        normalized,
        AssetDraftProjectionError,
        "message.id 包含无效 Unicode",
    )
    return normalized


def _input_text(value: str, field: str) -> str:
    normalized = _normalize_text(value)
    _ensure_utf8(normalized, AssetDraftInputError, f"{field} 包含无效 Unicode")
    return normalized


def _normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split())


def _ensure_utf8(value: str, error_type, message: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise error_type(message) from exc


def _stable_json_value(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        raise AssetDraftProjectionError("来源数字必须是有限数字")
    if isinstance(value, str):
        _ensure_utf8(
            value,
            AssetDraftProjectionError,
            "来源字符串包含无效 Unicode",
        )
        return value
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise AssetDraftProjectionError("来源对象的键必须是字符串")
        for key in value:
            _ensure_utf8(
                key,
                AssetDraftProjectionError,
                "来源对象的键包含无效 Unicode",
            )
        return {key: _stable_json_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_stable_json_value(item) for item in value]
    raise AssetDraftProjectionError("来源包含不可序列化值")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _digest_hex(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _digest(value: Any) -> str:
    return f"sha256:{_digest_hex(value)}"
