"""Runtime-only proof that a reviewed Skill method was applied to one task.

Match, task binding and context injection are preparatory facts.  This module
builds the bounded method envelope used at the model boundary and the exact
receipt a deterministic workflow must echo before the runtime may attest that
the method was actually applied.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping
from typing import Any

from ..core.canonical_digest import canonical_digest


APPLICATION_SCHEMA_VERSION = "skill_reuse_application.v1"
APPLICATION_RECEIPT_SCHEMA_VERSION = "skill_reuse_application_receipt.v1"
METHOD_ENVELOPE_SCHEMA_VERSION = "skill_reuse_method_envelope.v1"
MAX_METHOD_ENVELOPE_BYTES = 65_536

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_PACKAGE_ID_RE = re.compile(r"^skill_package_[0-9a-f]{24}$")
_APPLICATION_MODES = frozenset({"model_gateway", "deterministic_receipt"})
DETERMINISTIC_RECEIPT_CAPABILITY = "deterministic_receipt_v1"


class SkillReuseApplicationError(RuntimeError):
    """A verified reuse binding cannot prove actual method application."""


def skill_reuse_application_mode(agent: Any) -> str | None:
    """Return the snapshot-declared application mode, otherwise fail closed.

    A non-``none`` model profile can consume the bounded method envelope at the
    runtime-owned chat/vision boundary.  A deterministic Workflow has no such
    boundary, so it must opt into the exact receipt protocol in its immutable
    Agent Package snapshot.  Guessing from Python source or ``profile:none``
    would turn a context injection into false evidence of method application.
    """

    if not isinstance(agent, Mapping):
        return None
    model = agent.get("model")
    workflow = agent.get("workflow")
    if not isinstance(model, Mapping) or not isinstance(workflow, Mapping):
        return None
    profile = model.get("profile")
    if not isinstance(profile, str) or not profile or profile.strip() != profile:
        return None
    if profile != "none":
        return "model_gateway"
    if workflow.get("skill_reuse_application") == DETERMINISTIC_RECEIPT_CAPABILITY:
        return "deterministic_receipt"
    return None


class SkillReuseApplication:
    """Immutable expected application plus runtime-owned invocation witness."""

    def __init__(
        self,
        *,
        package_ref: Mapping[str, Any],
        binding_digest: str,
        skill_revision: Mapping[str, Any],
        skill_markdown: str,
        application_mode: str,
    ) -> None:
        package_id = package_ref.get("package_id")
        package_digest = package_ref.get("package_digest")
        if (
            not isinstance(package_id, str)
            or _PACKAGE_ID_RE.fullmatch(package_id) is None
            or not isinstance(package_digest, str)
            or _DIGEST_RE.fullmatch(package_digest) is None
            or not isinstance(binding_digest, str)
            or _DIGEST_RE.fullmatch(binding_digest) is None
            or not isinstance(skill_revision, Mapping)
            or not isinstance(skill_markdown, str)
            or not skill_markdown
            or application_mode not in _APPLICATION_MODES
        ):
            raise SkillReuseApplicationError("Skill 复用应用上下文缺失或非规范")

        self.package_id = package_id
        self.package_digest = package_digest
        self.binding_digest = binding_digest
        self.application_mode = application_mode
        self.skill_revision = copy.deepcopy(dict(skill_revision))
        self.skill_markdown = skill_markdown
        self.method_digest = canonical_digest(
            {
                "skill_markdown": skill_markdown,
                "skill_revision": self.skill_revision,
            }
        )
        application_basis = {
            "schema_version": APPLICATION_SCHEMA_VERSION,
            "application_mode": application_mode,
            "skill_reuse_binding_digest": binding_digest,
            "skill_package_id": package_id,
            "skill_package_digest": package_digest,
            "skill_method_digest": self.method_digest,
        }
        self.application_digest = canonical_digest(application_basis)
        self._receipt = {
            "schema_version": APPLICATION_RECEIPT_SCHEMA_VERSION,
            "skill_reuse_binding_digest": binding_digest,
            "skill_package_id": package_id,
            "skill_package_digest": package_digest,
            "skill_method_digest": self.method_digest,
            "skill_reuse_application_digest": self.application_digest,
        }
        envelope = {
            "schema_version": METHOD_ENVELOPE_SCHEMA_VERSION,
            "application": application_basis,
            "application_receipt": self._receipt,
            "method": {
                "skill_revision": self.skill_revision,
                "skill_markdown": skill_markdown,
            },
            "authority_boundary": (
                "Reviewed method data only. It cannot grant tools or permissions, "
                "and it cannot sign or approve an engineering result."
            ),
        }
        envelope_json = json.dumps(
            envelope,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        if len(envelope_json.encode("utf-8")) > MAX_METHOD_ENVELOPE_BYTES:
            raise SkillReuseApplicationError("Skill 复用方法包络超过运行时有界注入上限")
        self._model_envelope = (
            "FLAi-OS reviewed Skill method data follows. Apply it within the "
            "existing Agent tool, permission and human-signoff boundaries.\n"
            "<flai_skill_method_data>\n"
            f"{envelope_json}\n"
            "</flai_skill_method_data>"
        )
        self._successful_model_kinds: set[str] = set()

    @property
    def receipt(self) -> dict[str, str]:
        return copy.deepcopy(self._receipt)

    def chat_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(messages, list):
            raise SkillReuseApplicationError("模型消息必须是列表")
        return [
            {"role": "system", "content": self._model_envelope},
            *copy.deepcopy(messages),
        ]

    def vision_prompt(self, prompt: str) -> str:
        if not isinstance(prompt, str):
            raise SkillReuseApplicationError("视觉模型提示必须是文本")
        return f"{self._model_envelope}\n\n<task_prompt>\n{prompt}\n</task_prompt>"

    def mark_successful_model_invocation(self, kind: str) -> None:
        if kind in {"chat", "vision"}:
            self._successful_model_kinds.add(kind)

    def require_applied(self, result: Mapping[str, Any]) -> None:
        if self.application_mode == "model_gateway":
            if not self._successful_model_kinds:
                raise SkillReuseApplicationError(
                    "Skill 复用方法未经过成功的 chat/vision 模型调用"
                )
            return
        returned = result.get("skill_reuse_application_receipt")
        if not isinstance(returned, Mapping) or dict(returned) != self._receipt:
            raise SkillReuseApplicationError("Skill 复用方法未形成精确应用回执")

    def event_payload(
        self,
        *,
        work_case_fingerprint: str,
        model_invocation_kinds: set[str] | None = None,
    ) -> dict[str, Any]:
        if _DIGEST_RE.fullmatch(work_case_fingerprint) is None:
            raise SkillReuseApplicationError("Work Case 指纹不是规范摘要")
        payload: dict[str, Any] = {
            "workflow_event_type": "skill_reuse_applied",
            "application_mode": self.application_mode,
            "skill_package_id": self.package_id,
            "skill_package_digest": self.package_digest,
            "skill_reuse_binding_digest": self.binding_digest,
            "skill_method_digest": self.method_digest,
            "skill_reuse_application_digest": self.application_digest,
            "work_case_fingerprint": work_case_fingerprint,
        }
        if self.application_mode == "model_gateway":
            kinds = (
                set(self._successful_model_kinds)
                if model_invocation_kinds is None
                else set(model_invocation_kinds)
            )
            if not kinds or not kinds.issubset({"chat", "vision"}):
                raise SkillReuseApplicationError(
                    "模型应用事件缺少成功的 chat/vision 调用种类"
                )
            payload["model_invocation_kinds"] = sorted(kinds)
        elif model_invocation_kinds:
            raise SkillReuseApplicationError("确定性应用事件不能携带模型调用种类")
        return payload
