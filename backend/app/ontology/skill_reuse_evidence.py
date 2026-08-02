"""Task-level evidence binding for approved Skill Package reuse.

The Guide match is only a recommendation-time fact.  This ledger turns it into
an insert-once task binding, re-verifies the package at runtime, and counts only
completed executions whose validation and terminal events carry the same
binding digest.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import unicodedata
import copy
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from ..core.canonical_digest import canonical_digest
from ..runtime.package_snapshot import SNAPSHOT_CONTRACT
from ..runtime.skill_reuse_application import SkillReuseApplication
from ..runtime.task_evidence import input_files_evidence, work_case_fingerprint
from ..storage import repos
from ..storage import skill_reuse_bindings as binding_store


SCHEMA_VERSION = "skill_reuse_binding.v1"
MATCH_POLICY_VERSION = "skill_reuse_match.v1"
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_SEMVER = re.compile(
    r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_REF_KEYS = frozenset(
    {
        "schema_version",
        "package_id",
        "package_version",
        "package_digest",
        "candidate_digest",
        "skill_digest",
        "skill_name",
        "matched_agent_id",
        "review_state",
        "match_policy_version",
        "match_basis_digest",
    }
)
_RESOLVED_CONTEXT_KEYS = frozenset(
    {"ref", "package", "skill_revision", "skill_markdown"}
)
_PACKAGE_KEYS = frozenset(
    {
        "schema_version",
        "id",
        "name",
        "version",
        "package_digest",
        "state",
        "source",
        "files",
        "storage_relpath",
        "review",
        "reuse_eligible",
        "isolation",
        "formation_evidence",
        "created_at",
        "updated_at",
    }
)
_PACKAGE_SOURCE_KEYS = frozenset(
    {
        "candidate_id",
        "candidate_digest",
        "bundle_digest",
        "skill_digest",
        "acceptance_event_digest",
        "task_id",
        "agent_id",
        "initiated_by_username",
    }
)
_SKILL_REVISION_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "operationalizes_task_pattern_digest",
        "name",
        "description",
        "when_to_use",
        "when_not_to_use",
        "inputs",
        "outputs",
        "instructions",
        "verification",
        "human_boundaries",
        "suggested_id",
        "content_digest",
    }
)


class SkillReuseInvalidError(RuntimeError):
    """A planned or persisted reuse reference cannot be trusted."""


def normalize_reuse_ref(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _REF_KEYS:
        raise SkillReuseInvalidError("Skill 复用引用字段不完整或含未授权字段")
    normalized: dict[str, str] = {}
    for key in _REF_KEYS:
        item = value.get(key)
        if not isinstance(item, str) or not item.strip():
            raise SkillReuseInvalidError(f"Skill 复用引用 {key} 必须是非空文本")
        normalized[key] = unicodedata.normalize("NFC", item.strip())
    if normalized["schema_version"] != "skill_reuse_ref.v1":
        raise SkillReuseInvalidError("Skill 复用引用版本不受支持")
    if normalized["review_state"] != "approved":
        raise SkillReuseInvalidError("只有已审核 Skill Package 可以复用")
    if normalized["match_policy_version"] != MATCH_POLICY_VERSION:
        raise SkillReuseInvalidError("Skill 自动匹配策略版本不受支持")
    for key in (
        "package_digest",
        "candidate_digest",
        "skill_digest",
        "match_basis_digest",
    ):
        if _DIGEST.fullmatch(normalized[key]) is None:
            raise SkillReuseInvalidError(f"Skill 复用引用 {key} 不是规范摘要")
    if re.fullmatch(r"^skill_package_[0-9a-f]{24}$", normalized["package_id"]) is None:
        raise SkillReuseInvalidError("Skill Package id 不合法")
    if _SEMVER.fullmatch(normalized["package_version"]) is None:
        raise SkillReuseInvalidError("Skill Package 版本不合法")
    if re.fullmatch(r"^[a-z][a-z0-9_]{2,63}$", normalized["matched_agent_id"]) is None:
        raise SkillReuseInvalidError("复用目标 Agent id 不合法")
    return normalized


class SkillReuseEvidenceLedger:
    def __init__(self, materializer: Any) -> None:
        self._materializer = materializer
        self._formation_state = threading.local()

    def resolve_for_task(
        self,
        conn: sqlite3.Connection,
        *,
        ref: Any,
        username: str,
        agent_id: str,
    ) -> dict[str, Any]:
        normalized = normalize_reuse_ref(ref)
        if normalized["matched_agent_id"] != agent_id:
            raise SkillReuseInvalidError("Skill 复用引用与目标 Agent 不一致")
        resolved = self._materializer.resolve_reuse_eligible(
            conn,
            ref=normalized,
            username=username,
            agent_id=agent_id,
        )
        if not isinstance(resolved, Mapping):
            raise SkillReuseInvalidError("Skill Package 无法形成可执行复用上下文")
        return self.validate_resolved_context(
            {
                "ref": normalized,
                "package": resolved["package"],
                "skill_revision": resolved["skill_revision"],
                "skill_markdown": resolved["skill_markdown"],
            },
            expected_ref=normalized,
            agent_id=agent_id,
            owner_username=username,
        )

    @staticmethod
    def validate_resolved_context(
        resolved: Any,
        *,
        expected_ref: Any,
        agent_id: str,
        owner_username: str | None = None,
    ) -> dict[str, Any]:
        """Validate the exact cold-resolved object before any task write.

        The materializer is an external trust seam from the batch transaction's
        perspective.  A loose ``isinstance(dict)`` check must not let a partial,
        widened or cross-Agent package become an immutable task binding.
        """

        if not isinstance(resolved, Mapping) or set(resolved) != _RESOLVED_CONTEXT_KEYS:
            raise SkillReuseInvalidError("已解析 Skill 上下文字段不完整或含未授权字段")
        ref = normalize_reuse_ref(resolved.get("ref"))
        expected = normalize_reuse_ref(expected_ref)
        if ref != expected or ref["matched_agent_id"] != agent_id:
            raise SkillReuseInvalidError("已解析 Skill 引用与预期引用或 Agent 不一致")

        package = resolved.get("package")
        revision = resolved.get("skill_revision")
        markdown = resolved.get("skill_markdown")
        if not isinstance(package, Mapping) or set(package) != _PACKAGE_KEYS:
            raise SkillReuseInvalidError("已解析 Skill Package 形状不精确")
        source = package.get("source")
        review = package.get("review")
        if (
            not isinstance(source, Mapping)
            or set(source) != _PACKAGE_SOURCE_KEYS
            or not isinstance(review, Mapping)
            or review.get("action") != "approve"
            or package.get("schema_version") != "skill_package_revision.v1"
            or package.get("id") != ref["package_id"]
            or package.get("version") != ref["package_version"]
            or package.get("package_digest") != ref["package_digest"]
            or package.get("state") != "approved"
            or package.get("reuse_eligible") is not True
            or source.get("candidate_digest") != ref["candidate_digest"]
            or source.get("skill_digest") != ref["skill_digest"]
            or source.get("agent_id") != agent_id
            or (
                owner_username is not None
                and source.get("initiated_by_username") != owner_username
            )
        ):
            raise SkillReuseInvalidError("已解析 Skill Package 来源或审核态不一致")
        if (
            not isinstance(revision, Mapping)
            or set(revision) != _SKILL_REVISION_KEYS
            or revision.get("schema_version") != "skill_draft.v1"
            or revision.get("status") != "draft"
            or revision.get("content_digest") != ref["skill_digest"]
            or revision.get("name") != ref["skill_name"]
            or not isinstance(markdown, str)
            or not markdown
        ):
            raise SkillReuseInvalidError("已解析 Skill 方法修订或正文不一致")
        return copy.deepcopy(
            {
                "ref": ref,
                "package": dict(package),
                "skill_revision": dict(revision),
                "skill_markdown": markdown,
            }
        )

    def bind_task(
        self,
        conn: sqlite3.Connection,
        *,
        task_id: str,
        conversation_id: str,
        username: str,
        agent_id: str,
        resolved: Mapping[str, Any],
    ) -> dict[str, Any]:
        record = self.build_binding(
            task_id=task_id,
            conversation_id=conversation_id,
            username=username,
            agent_id=agent_id,
            resolved=resolved,
        )
        self.insert_binding(conn, record)
        return record

    def build_binding(
        self,
        *,
        task_id: str,
        conversation_id: str,
        username: str,
        agent_id: str,
        resolved: Mapping[str, Any],
    ) -> dict[str, Any]:
        resolved = self.validate_resolved_context(
            resolved,
            expected_ref=(
                resolved.get("ref") if isinstance(resolved, Mapping) else None
            ),
            agent_id=agent_id,
            owner_username=username,
        )
        ref = normalize_reuse_ref(resolved.get("ref"))
        basis = {
            "schema_version": SCHEMA_VERSION,
            "task_id": task_id,
            "conversation_id": conversation_id,
            "package_id": ref["package_id"],
            "package_digest": ref["package_digest"],
            "source_candidate_digest": ref["candidate_digest"],
            "source_skill_digest": ref["skill_digest"],
            "matched_agent_id": agent_id,
            "owner_username": username,
            "match_policy_version": ref["match_policy_version"],
            "match_basis_digest": ref["match_basis_digest"],
        }
        binding_digest = canonical_digest(basis)
        record = {
            **basis,
            "id": f"skill_reuse_binding_{binding_digest.removeprefix('sha256:')[:24]}",
            "binding_digest": binding_digest,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return record

    @staticmethod
    def insert_binding(conn: sqlite3.Connection, record: Mapping[str, Any]) -> None:
        binding_store.insert_binding(conn, record)

    def verify_runtime(
        self,
        conn: sqlite3.Connection,
        *,
        task: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        metadata = task.get("metadata")
        if not isinstance(metadata, Mapping) or "skill_package_ref" not in metadata:
            return None
        ref = normalize_reuse_ref(metadata.get("skill_package_ref"))
        username = task.get("created_by_username")
        if not isinstance(username, str) or not username:
            raise SkillReuseInvalidError("复用任务缺少可验证的发起工程师身份")
        binding = binding_store.get_by_task(conn, str(task.get("id") or ""))
        if binding is None:
            raise SkillReuseInvalidError("复用任务缺少 insert-once Skill binding")
        basis = {
            key: binding[key]
            for key in (
                "schema_version",
                "task_id",
                "conversation_id",
                "package_id",
                "package_digest",
                "source_candidate_digest",
                "source_skill_digest",
                "matched_agent_id",
                "owner_username",
                "match_policy_version",
                "match_basis_digest",
            )
        }
        expected_digest = canonical_digest(basis)
        if (
            binding.get("schema_version") != SCHEMA_VERSION
            or binding.get("binding_digest") != expected_digest
            or metadata.get("skill_reuse_binding_digest") != expected_digest
            or binding.get("task_id") != task.get("id")
            or binding.get("conversation_id") != task.get("conversation_id")
            or binding.get("owner_username") != username
            or binding.get("matched_agent_id") != task.get("agent_id")
            or binding.get("package_id") != ref["package_id"]
            or binding.get("package_digest") != ref["package_digest"]
            or binding.get("source_candidate_digest") != ref["candidate_digest"]
            or binding.get("source_skill_digest") != ref["skill_digest"]
            or binding.get("match_policy_version") != ref["match_policy_version"]
            or binding.get("match_basis_digest") != ref["match_basis_digest"]
        ):
            raise SkillReuseInvalidError("Skill 复用任务 binding 摘要或来源漂移")
        resolved = self.resolve_for_task(
            conn,
            ref=ref,
            username=username,
            agent_id=str(task.get("agent_id") or ""),
        )
        return {
            "package_ref": ref,
            "binding_digest": expected_digest,
            "skill_revision": resolved["skill_revision"],
            "skill_markdown": resolved["skill_markdown"],
        }

    def formation_evidence(
        self,
        conn: sqlite3.Connection,
        *,
        package_id: str,
        owner_username: str,
    ) -> dict[str, Any]:
        # Runtime verification cold-loads the approved package, whose public
        # projection also asks this provider for its formation count.  The
        # nested projection is not itself evidence discovery; return the
        # conservative zero view so the outer cold verification can complete.
        if getattr(self._formation_state, "active", False) is True:
            return self._composition_eligibility(0)
        self._formation_state.active = True
        try:
            return self._formation_evidence(
                conn,
                package_id=package_id,
                owner_username=owner_username,
            )
        finally:
            self._formation_state.active = False

    def _formation_evidence(
        self,
        conn: sqlite3.Connection,
        *,
        package_id: str,
        owner_username: str,
    ) -> dict[str, Any]:
        independent_count = 0
        seen_source_tasks: set[str] = set()
        seen_work_segments: set[str] = set()
        seen_task_families: set[str] = set()
        seen_execution_evidence: set[str] = set()
        seen_terminal_events: set[str] = set()
        seen_work_case_fingerprints: set[str] = set()
        for binding in binding_store.list_for_package(
            conn,
            package_id=package_id,
            owner_username=owner_username,
        ):
            task = repos.get_task(conn, binding["task_id"])
            verified = self._completed_binding_evidence(conn, binding, task)
            if verified is None or task is None:
                continue
            root_task_id = self._retry_family_root(
                conn,
                task=task,
                owner_username=owner_username,
            )
            if root_task_id is None:
                continue
            source_task_id = verified["task_id"]
            work_segment = verified["match_basis_digest"]
            execution_digest = verified["execution_evidence_digest"]
            terminal_event_digest = verified["terminal_event_digest"]
            case_fingerprint = verified["work_case_fingerprint"]
            if (
                source_task_id in seen_source_tasks
                or work_segment in seen_work_segments
                or root_task_id in seen_task_families
                or execution_digest in seen_execution_evidence
                or terminal_event_digest in seen_terminal_events
                or case_fingerprint in seen_work_case_fingerprints
            ):
                continue
            seen_source_tasks.add(source_task_id)
            seen_work_segments.add(work_segment)
            seen_task_families.add(root_task_id)
            seen_execution_evidence.add(execution_digest)
            seen_terminal_events.add(terminal_event_digest)
            seen_work_case_fingerprints.add(case_fingerprint)
            independent_count += 1
        return self._composition_eligibility(independent_count)

    @staticmethod
    def _composition_eligibility(independent_count: int) -> dict[str, Any]:
        workflow_reason = (
            "requires_stable_multi_skill_composition_evidence"
            if independent_count >= 2
            else "requires_independent_composition_evidence"
        )
        return {
            "schema_version": "composition_eligibility.v1",
            "independent_work_case_count": independent_count,
            "required_independent_work_cases": 2,
            "workflow_candidate": {
                "state": "not_formed",
                "eligible": False,
                "reason": workflow_reason,
            },
            "agent_candidate": {
                "state": "not_formed",
                "eligible": False,
                "reason": "requires_approved_workflow_revision",
            },
        }

    def _completed_binding_evidence(
        self,
        conn: sqlite3.Connection,
        binding: Mapping[str, Any],
        task: Mapping[str, Any] | None,
    ) -> dict[str, str] | None:
        if (
            task is None
            or task.get("status") != "completed"
            or task.get("origin") != "user"
            or task.get("created_by_username") != binding.get("owner_username")
            or task.get("agent_id") != binding.get("matched_agent_id")
            or task.get("conversation_id") != binding.get("conversation_id")
        ):
            return None
        try:
            runtime_verified = self.verify_runtime(conn, task=task)
        except Exception:  # noqa: BLE001 -- read-only eligibility must fail closed
            return None
        if not isinstance(runtime_verified, Mapping):
            return None
        verified_ref = runtime_verified.get("package_ref")
        if not isinstance(verified_ref, Mapping):
            return None
        binding_digest = runtime_verified.get("binding_digest")
        if (
            not isinstance(binding_digest, str)
            or _DIGEST.fullmatch(binding_digest) is None
            or binding_digest != binding.get("binding_digest")
        ):
            return None

        rows = conn.execute(
            """
            SELECT id, event_id, task_id, agent_id, event_type, level, message,
                   payload_json, created_at
            FROM task_events
            WHERE task_id = ? AND event_type IN (
                'validation_started', 'agent_log', 'model_call', 'task_completed',
                'review_approved'
            )
            ORDER BY id ASC
            """,
            (task["id"],),
        ).fetchall()
        parsed: list[tuple[dict[str, Any], dict[str, Any]]] = []
        try:
            for row in rows:
                payload = json.loads(row["payload_json"])
                if not isinstance(payload, dict):
                    return None
                parsed.append((dict(row), payload))
        except (TypeError, json.JSONDecodeError, UnicodeError):
            return None

        validations = [
            item for item in parsed if item[0]["event_type"] == "validation_started"
        ]
        terminals = [
            item
            for item in parsed
            if item[0]["event_type"] in {"task_completed", "review_approved"}
        ]
        bound_events = [
            item
            for item in parsed
            if item[0]["event_type"] == "agent_log"
            and item[1].get("workflow_event_type") == "skill_reuse_bound"
        ]
        applied_events = [
            item
            for item in parsed
            if item[0]["event_type"] == "agent_log"
            and item[1].get("workflow_event_type") == "skill_reuse_applied"
        ]
        if (
            len(validations) != 1
            or len(terminals) != 1
            or len(bound_events) != 1
            or len(applied_events) != 1
        ):
            return None
        validation_row, validation_payload = validations[0]
        terminal_row, terminal_payload = terminals[0]
        bound_row, bound_payload = bound_events[0]
        applied_row, applied_payload = applied_events[0]
        if not (
            validation_row["id"]
            < bound_row["id"]
            < applied_row["id"]
            < terminal_row["id"]
            and validation_row.get("agent_id") == task.get("agent_id")
            and bound_row.get("agent_id") == task.get("agent_id")
            and applied_row.get("agent_id") == task.get("agent_id")
            and terminal_row.get("agent_id") == task.get("agent_id")
        ):
            return None

        execution_digest = validation_payload.get("execution_evidence_digest")
        input_file_ids = validation_payload.get("input_file_ids")
        input_files_digest = validation_payload.get("input_files_digest")
        task_inputs_digest = validation_payload.get("task_inputs_digest")
        package_snapshot_digest = validation_payload.get("package_snapshot_digest")
        metadata = task.get("metadata")
        if not isinstance(metadata, Mapping):
            return None
        try:
            live_input_evidence = input_files_evidence(
                conn, list(task.get("input_file_ids") or [])
            )
            expected_task_inputs_digest = canonical_digest(task.get("inputs"))
            application_mode = applied_payload.get("application_mode")
            application = SkillReuseApplication(
                package_ref=verified_ref,
                binding_digest=binding_digest,
                skill_revision=runtime_verified["skill_revision"],
                skill_markdown=runtime_verified["skill_markdown"],
                application_mode=application_mode,
            )
            expected_work_case_fingerprint = work_case_fingerprint(
                task_inputs=task.get("inputs"),
                input_file_evidence=live_input_evidence,
                agent_id=str(task.get("agent_id") or ""),
                package_id=str(verified_ref.get("package_id") or ""),
                package_digest=str(verified_ref.get("package_digest") or ""),
            )
            expected_execution_digest = canonical_digest(
                {
                    "package_snapshot_digest": package_snapshot_digest,
                    "task_inputs_digest": task_inputs_digest,
                    "input_file_ids": input_file_ids,
                    "input_files_digest": input_files_digest,
                }
            )
        except Exception:  # noqa: BLE001 -- malformed/tampered evidence is ineligible
            return None

        expected_bound_payload = {
            "workflow_event_type": "skill_reuse_bound",
            "skill_package_id": verified_ref.get("package_id"),
            "skill_package_digest": verified_ref.get("package_digest"),
            "skill_reuse_binding_digest": binding_digest,
            "skill_method_digest": application.method_digest,
            "skill_reuse_application_digest": application.application_digest,
            "work_case_fingerprint": expected_work_case_fingerprint,
        }
        model_invocation_kinds: set[str] | None = None
        if application_mode == "model_gateway":
            successful_model_events = [
                item
                for item in parsed
                if item[0]["event_type"] == "model_call"
                and bound_row["id"] < item[0]["id"] < applied_row["id"]
                and item[0].get("agent_id") == task.get("agent_id")
                and item[0].get("level") == "info"
                and item[1].get("kind") in {"chat", "vision"}
                and item[1].get("skill_reuse_application_digest")
                == application.application_digest
            ]
            if not successful_model_events:
                return None
            model_invocation_kinds = {
                str(item[1]["kind"]) for item in successful_model_events
            }
        expected_applied_payload = application.event_payload(
            work_case_fingerprint=expected_work_case_fingerprint,
            model_invocation_kinds=model_invocation_kinds,
        )
        if (
            bound_payload != expected_bound_payload
            or applied_payload != expected_applied_payload
        ):
            return None
        if not (
            validation_payload.get("package_snapshot_contract") == SNAPSHOT_CONTRACT
            and package_snapshot_digest == metadata.get("package_snapshot_digest")
            and input_file_ids == list(task.get("input_file_ids") or [])
            and input_files_digest == live_input_evidence.get("digest")
            and task_inputs_digest == expected_task_inputs_digest
            and isinstance(execution_digest, str)
            and _DIGEST.fullmatch(execution_digest) is not None
            and execution_digest == expected_execution_digest
            and validation_payload.get("skill_reuse_binding_digest") == binding_digest
            and validation_payload.get("skill_reuse_application_digest")
            == application.application_digest
            and validation_payload.get("work_case_fingerprint")
            == expected_work_case_fingerprint
            and terminal_payload.get("skill_reuse_binding_digest") == binding_digest
            and terminal_payload.get("skill_reuse_application_digest")
            == application.application_digest
            and terminal_payload.get("execution_evidence_digest") == execution_digest
        ):
            return None

        terminal_event_id = terminal_row.get("event_id")
        terminal_created_at = terminal_row.get("created_at")
        if (
            not isinstance(terminal_event_id, str)
            or not terminal_event_id
            or not isinstance(terminal_created_at, str)
            or not terminal_created_at
        ):
            return None
        signer_username: str | None = None
        if terminal_row["event_type"] == "review_approved":
            signer = terminal_payload.get("reviewer_username")
            if not isinstance(signer, str) or not signer.strip():
                return None
            signer_username = signer
        terminal_event_digest = canonical_digest(
            {
                "schema_version": "skill_reuse_terminal_event.v1",
                "event_id": terminal_event_id,
                "event_type": terminal_row["event_type"],
                "created_at": terminal_created_at,
                "execution_evidence_digest": execution_digest,
                "skill_reuse_binding_digest": binding_digest,
                "skill_reuse_application_digest": application.application_digest,
                "work_case_fingerprint": expected_work_case_fingerprint,
                "signer_username": signer_username,
            }
        )
        return {
            "task_id": str(task["id"]),
            "match_basis_digest": str(verified_ref["match_basis_digest"]),
            "execution_evidence_digest": execution_digest,
            "terminal_event_digest": terminal_event_digest,
            "work_case_fingerprint": expected_work_case_fingerprint,
        }

    @staticmethod
    def _retry_family_root(
        conn: sqlite3.Connection,
        *,
        task: Mapping[str, Any],
        owner_username: str,
    ) -> str | None:
        """Resolve the complete retry lineage, rejecting gaps, cycles and owners."""

        current: Mapping[str, Any] = task
        seen: set[str] = set()
        while True:
            task_id = current.get("id")
            if not isinstance(task_id, str) or not task_id or task_id in seen:
                return None
            seen.add(task_id)
            if (
                current.get("origin") != "user"
                or current.get("created_by_username") != owner_username
            ):
                return None
            retry_of = current.get("retry_of")
            if retry_of is None:
                return task_id
            if not isinstance(retry_of, str) or not retry_of.strip():
                return None
            parent = repos.get_task(conn, retry_of)
            if parent is None or parent.get("status") != "failed":
                return None
            current = parent
