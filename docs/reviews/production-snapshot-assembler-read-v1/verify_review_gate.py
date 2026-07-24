#!/usr/bin/env python3
"""Fail-closed checker for the Production Snapshot Assembler review pack.

The checker validates local structure and digest bindings. External identity,
role-assignment, signature, audit, revocation, and trust-policy authenticity
must be established by the organization-approved verifier named in the plan.
This utility never grants implementation authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


CONTRACT_ID = "flai.production-snapshot-assembler.read.v1"
REVIEW_PACKAGE_ID = (
    "flai.production-snapshot-assembler.read.v1.named-review.round-1"
)
FROZEN_SHA256 = "8f791b5c9a5c5e3c9d18ef0168d23fe0ec5c9cc24f024f4e374c82de15357f24"
FROZEN_BYTE_LENGTH = 74_878
FROZEN_RELATIVE_PATH = (
    "../../product/FLAi-OS_V0.2_Design_Package/"
    "16_Production_Snapshot_Assembler_Read_Contract.md"
)
REVIEW_ROUND_ID = "psa-read-v1-r1"
CORE_VERSION = "flai.review-decision-core.v1"
SEAL_VERSION = "flai.review-decision-seal.v1"
MANIFEST_VERSION = "flai.named-contract-review-manifest.v1"
EXPECTED_DOMAIN_IDS = (
    "control-kernel-architecture",
    "identity-authorization",
    "data-sqlite",
    "security-cryptography",
    "executionbroker-sandbox",
    "knowledge",
    "workbench-observer",
)
EXPECTED_REVIEW_SPECS: dict[str, dict[str, Any]] = {
    "control-kernel-architecture": {
        "owner_role": "Control Kernel / 架构 owner",
        "responsibility_scope": (
            "ProductionSnapshotAssembler Module ownership, public seam, "
            "dependency direction, read-only boundary, and prohibition of a "
            "second state machine or control plane."
        ),
        "required_question_ids": (
            "COMMON-01",
            "module_ownership",
            "public_seam",
            "no_second_state_machine",
        ),
        "decision_core_path": (
            "records/01-control-kernel-architecture.review.json"
        ),
        "decision_seal_path": (
            "seals/01-control-kernel-architecture.seal.json"
        ),
    },
    "identity-authorization": {
        "owner_role": "Identity / Authorization owner",
        "responsibility_scope": (
            "Trusted authenticated context, object authorization, "
            "ACL/classification/existence handling, and release-time "
            "authorization fences."
        ),
        "required_question_ids": (
            "COMMON-01",
            "authenticated_opaque_context",
            "acl_classification_existence",
            "release_fence",
        ),
        "decision_core_path": "records/02-identity-authorization.review.json",
        "decision_seal_path": "seals/02-identity-authorization.seal.json",
    },
    "data-sqlite": {
        "owner_role": "数据 / SQLite owner",
        "responsibility_scope": (
            "SQLite point-in-time read boundary, event tail window, "
            "query-only behavior, locking, limits, and performance bounds."
        ),
        "required_question_ids": (
            "COMMON-01",
            "single_read_transaction",
            "tail_window",
            "query_only",
            "performance_bounds",
        ),
        "decision_core_path": "records/03-data-sqlite.review.json",
        "decision_seal_path": "seals/03-data-sqlite.seal.json",
    },
    "security-cryptography": {
        "owner_role": "安全 / 密码 owner",
        "responsibility_scope": (
            "Strict receipt schemas, issuer authorization, signature and "
            "digest rules, algorithm policy, key lifecycle, revocation, and "
            "verification-policy fences."
        ),
        "required_question_ids": (
            "COMMON-01",
            "strict_receipt_schema",
            "issuer_authority",
            "algorithm_policy",
            "key_rotation_revocation",
        ),
        "decision_core_path": (
            "records/04-security-cryptography.review.json"
        ),
        "decision_seal_path": (
            "seals/04-security-cryptography.seal.json"
        ),
    },
    "executionbroker-sandbox": {
        "owner_role": "ExecutionBroker / Sandbox owner",
        "responsibility_scope": (
            "Composite backend identity, Broker and Sandbox witness "
            "independence, execution binding, and phase-specific "
            "REAL/MOCK/TEST evidence."
        ),
        "required_question_ids": (
            "COMMON-01",
            "composite_backend_identity",
            "broker_sandbox_independence",
            "phase_witness_binding",
        ),
        "decision_core_path": (
            "records/05-executionbroker-sandbox.review.json"
        ),
        "decision_seal_path": (
            "seals/05-executionbroker-sandbox.seal.json"
        ),
    },
    "knowledge": {
        "owner_role": "Knowledge owner",
        "responsibility_scope": (
            "Knowledge four-key provenance projection, "
            "authorization-preserving evidence handling, and the unresolved "
            "authority/applicability boundary."
        ),
        "required_question_ids": (
            "COMMON-01",
            "four_key_provenance",
            "authority_unresolved_boundary",
        ),
        "decision_core_path": "records/06-knowledge.review.json",
        "decision_seal_path": "seals/06-knowledge.seal.json",
    },
    "workbench-observer": {
        "owner_role": "工作台 / Observer owner",
        "responsibility_scope": (
            "Stage C Runtime Observer Adapter v3 compatibility, "
            "diagnostic-only projection, failure semantics, and honest user "
            "experience."
        ),
        "required_question_ids": (
            "COMMON-01",
            "adapter_v3_compatibility",
            "diagnostic_only",
            "failure_experience",
        ),
        "decision_core_path": "records/07-workbench-observer.review.json",
        "decision_seal_path": "seals/07-workbench-observer.seal.json",
    },
}
EXPECTED_QUESTION_CATALOG = {
    "COMMON-01": (
        "确认评审对象是合同 flai.production-snapshot-assembler.read.v1 的冻结 "
        "SHA-256；本决定只评审只读设计合同，不声明 production-ready，不授权实现，"
        "也不授权生产 Schema、API 或状态机变更。"
    ),
    "module_ownership": (
        "Assembler 是否只属于 Control Kernel，且没有吸收 Identity、Authorization、"
        "ExecutionBroker、Knowledge 或 Observer 的裁决权？"
    ),
    "public_seam": (
        "唯一公开调用面、内部 WitnessResolver seam 和依赖方向是否明确并保持深 "
        "Module？"
    ),
    "no_second_state_machine": (
        "合同是否保证只读、无业务写入，且不创建第二任务状态机或第二控制面？"
    ),
    "authenticated_opaque_context": (
        "认证上下文是否只能由受信通道铸造，且调用方无法伪造 actor、role、ACL 或 "
        "reality？"
    ),
    "acl_classification_existence": (
        "对象存在性、ACL、clearance、classification 与字段投影是否在释放前 "
        "fail-closed？"
    ),
    "release_fence": (
        "actor/session、credential epoch、ResourceEnvelope、AuthorizationDecision "
        "与 verification-policy 的二次 fence 是否覆盖撤权和竞态？"
    ),
    "single_read_transaction": (
        "业务事实是否在一个 SQLite read transaction 中冻结，且外部验签和 release "
        "fence 不会混入新旧事实？"
    ),
    "tail_window": (
        "event tail window、总数、current event 与重复/冲突检查是否确定且不静默"
        "截断？"
    ),
    "query_only": (
        "连接、仓储与失败路径是否保证 read-only/query-only，无隐式迁移或写副作用？"
    ),
    "performance_bounds": (
        "读取规模、超时、锁占用和大对象策略是否有可实施的硬边界，未知时是否拒绝而非"
        "退化放行？"
    ),
    "strict_receipt_schema": (
        "receipt、admission core/seal、签名输入与 digest 绑定是否严格、无歧义且支持 "
        "invalid-first 验证？"
    ),
    "issuer_authority": (
        "issuer kind、key usage、工作负载身份与 Broker/Sandbox 独立作证是否由 Trust "
        "Policy 精确授权？"
    ),
    "algorithm_policy": (
        "算法、canonicalization、签名编码、时间与重放规则是否避免降级、混淆和摘要"
        "回环？"
    ),
    "key_rotation_revocation": (
        "历史签发策略与当前验证策略、轮换、吊销、retrospective compromise 和 "
        "release-time policy fence 是否闭合？"
    ),
    "composite_backend_identity": (
        "backend 是否表示 ExecutionBroker 组合身份，而不会把 AgentRuntime、"
        "SandboxProvider 或 Tool Adapter 任一方冒充整体？"
    ),
    "broker_sandbox_independence": (
        "Broker receipt 与 Sandbox witness 是否在 workload、leaf key material、key "
        "usage 和绑定对象上独立？"
    ),
    "phase_witness_binding": (
        "REAL/MOCK/TEST 及各阶段是否只能由对应受信证据产生，不能从 status 或日志自报"
        "推导？"
    ),
    "four_key_provenance": (
        "Observer 投影是否只携带 scope_id、chunk_id、source、fingerprint，并保持可"
        "追溯且不泄漏正文或未授权元数据？"
    ),
    "authority_unresolved_boundary": (
        "只有检索 provenance、缺少 KnowledgeVersion 权威、有效或适用证明时，是否保持 "
        "unresolved 而不伪装成权威依据？"
    ),
    "adapter_v3_compatibility": (
        "FactSet 与 readSnapshot 是否和冻结的 Stage C Runtime Observer Adapter v3 "
        "一致且没有隐式 UI 数据源？"
    ),
    "diagnostic_only": (
        "DIAGNOSTIC_ONLY 是否只支持受限诊断体验，不显示为 REAL、completed 绿色、交付"
        "成功或人签？"
    ),
    "failure_experience": (
        "稳定失败码、隐藏存在性、证据缺失、部分可见与重试语义是否支持诚实、低焦虑且"
        "不泄密的界面？"
    ),
}
ALLOWED_PLAN_STATUSES = {
    "DRAFT-PENDING-ASSIGNMENT",
    "FROZEN-FOR-REVIEW",
}
ALLOWED_DECISIONS = {"pending", "approve", "changes_required", "reject"}
ALLOWED_ANSWERS = {"pending", "satisfied", "unsatisfied"}
ALLOWED_EVIDENCE_KINDS = {
    "pending",
    "digital_signature",
    "immutable_audit_receipt",
}
EXTERNAL_TRUST_BLOCKER = (
    "EXTERNAL_TRUST_VERIFICATION_UNSUPPORTED: the local checker does not "
    "resolve or cryptographically verify actor, role, signature/audit, "
    "revocation, finding, SoD evidence, or append-only decision history"
)
PLACEHOLDER_VALUES = {
    "",
    "-",
    "N/A",
    "NA",
    "NONE",
    "NULL",
    "PENDING",
    "TBD",
    "TODO",
    "UNASSIGNED",
    "UNKNOWN",
    "UNRESOLVED",
}
RFC3339_WITH_OFFSET = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$"
)


class DuplicateJsonKeyError(ValueError):
    """Raised when signed JSON contains an ambiguous duplicate object key."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKeyError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


@dataclass(frozen=True)
class LoadedReview:
    manifest_entry: dict[str, Any]
    core: dict[str, Any]
    core_path: Path
    core_digest: str
    seal: dict[str, Any]
    seal_path: Path


@dataclass(frozen=True)
class FrozenJsonSnapshot:
    value: Any
    digest: str
    byte_length: int


@dataclass(frozen=True)
class GateEvaluation:
    structure_errors: tuple[str, ...]
    approval_blockers: tuple[str, ...]
    contract_review: str
    local_review_records_complete: bool
    eligible_for_separate_implementation_slice: bool
    implementation_authorized: bool


def _load_json_snapshot(path: Path) -> FrozenJsonSnapshot:
    raw_bytes = path.read_bytes()
    value = json.loads(
        raw_bytes.decode("utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
    )
    return FrozenJsonSnapshot(
        value=value,
        digest=f"sha256:{hashlib.sha256(raw_bytes).hexdigest()}",
        byte_length=len(raw_bytes),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_ref(path: Path) -> str:
    return f"sha256:{_sha256(path)}"


def _is_non_placeholder(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.strip().upper() not in PLACEHOLDER_VALUES
    )


def _is_rfc3339_with_offset(value: Any) -> bool:
    return _parse_rfc3339(value) is not None


def _parse_rfc3339(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    if RFC3339_WITH_OFFSET.fullmatch(candidate) is None:
        return None
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _validate_string_or_null(
    value: Any,
    field_path: str,
    errors: list[str],
) -> None:
    if value is not None and not isinstance(value, str):
        errors.append(f"{field_path} must be a string or null")


def _validate_exact_keys(
    value: dict[str, Any],
    expected_keys: set[str],
    field_path: str,
    errors: list[str],
) -> None:
    actual_keys = set(value)
    if actual_keys != expected_keys:
        missing = sorted(expected_keys - actual_keys)
        extra = sorted(actual_keys - expected_keys)
        details: list[str] = []
        if missing:
            details.append(f"missing={missing!r}")
        if extra:
            details.append(f"extra={extra!r}")
        errors.append(
            f"{field_path} must use the frozen key set ({', '.join(details)})"
        )


def _validate_string_list(
    value: Any,
    field_path: str,
    errors: list[str],
) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        errors.append(f"{field_path} must be an array of strings")


def _read_manifest(
    package_dir: Path,
    errors: list[str],
) -> tuple[dict[str, Any], str | None]:
    path = package_dir / "review-manifest.json"
    if not path.is_file():
        errors.append("review-manifest.json is missing")
        return {}, None
    if path.is_symlink():
        errors.append("review-manifest.json must not be a symlink")
        return {}, None
    try:
        snapshot = _load_json_snapshot(path)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        DuplicateJsonKeyError,
    ) as exc:
        errors.append(f"review-manifest.json is unreadable: {exc}")
        return {}, None
    manifest = snapshot.value
    if not isinstance(manifest, dict):
        errors.append("review-manifest.json must contain an object")
        return {}, None
    return manifest, snapshot.digest


def _validate_target(
    package_dir: Path,
    manifest: dict[str, Any],
    errors: list[str],
) -> None:
    target = manifest.get("target")
    if not isinstance(target, dict):
        errors.append("manifest.target must be an object")
        return
    _validate_exact_keys(
        target,
        {
            "contract_id",
            "relative_path",
            "sha256",
            "byte_length",
            "freeze_status",
            "implementation_status",
        },
        "manifest.target",
        errors,
    )
    if target.get("contract_id") != CONTRACT_ID:
        errors.append("manifest.target.contract_id does not match the frozen contract")
    if target.get("sha256") != FROZEN_SHA256:
        errors.append("manifest.target.sha256 does not match the frozen SHA-256")
    if (
        type(target.get("byte_length")) is not int
        or target.get("byte_length") != FROZEN_BYTE_LENGTH
    ):
        errors.append("manifest.target.byte_length does not match the frozen bytes")
    if target.get("freeze_status") != "FROZEN-FOR-REVIEW":
        errors.append("manifest.target.freeze_status must be FROZEN-FOR-REVIEW")
    if target.get("implementation_status") != "ACCEPTED-NOT-IMPLEMENTED":
        errors.append(
            "manifest.target.implementation_status must be "
            "ACCEPTED-NOT-IMPLEMENTED"
        )
    relative_path = target.get("relative_path")
    if relative_path != FROZEN_RELATIVE_PATH:
        errors.append("manifest.target.relative_path does not match the frozen path")
        return
    contract_candidate = package_dir / relative_path
    if contract_candidate.is_symlink():
        errors.append("frozen contract path must not be a symlink")
        return
    contract_path = contract_candidate.resolve()
    if not contract_path.is_file():
        errors.append(f"frozen contract is missing: {contract_path}")
        return
    try:
        contract_bytes = contract_path.read_bytes()
    except OSError as exc:
        errors.append(f"frozen contract is unreadable: {exc}")
        return
    actual_size = len(contract_bytes)
    if actual_size != FROZEN_BYTE_LENGTH:
        errors.append(
            "frozen contract byte length mismatch: "
            f"expected {FROZEN_BYTE_LENGTH}, got {actual_size}"
        )
    actual_sha256 = hashlib.sha256(contract_bytes).hexdigest()
    if actual_sha256 != FROZEN_SHA256:
        errors.append(
            "frozen contract SHA-256 mismatch: "
            f"expected {FROZEN_SHA256}, got {actual_sha256}"
        )


def _validate_manifest_policy(
    manifest: dict[str, Any],
    errors: list[str],
) -> None:
    _validate_exact_keys(
        manifest,
        {
            "manifest_version",
            "review_package_id",
            "review_round_id",
            "review_plan_status",
            "target",
            "question_catalog",
            "gate_policy",
            "implementation_authorization",
            "external_trust_verifier",
            "reviews",
        },
        "manifest",
        errors,
    )
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        errors.append(f"manifest_version must be {MANIFEST_VERSION}")
    if manifest.get("review_package_id") != REVIEW_PACKAGE_ID:
        errors.append(f"review_package_id must be {REVIEW_PACKAGE_ID}")
    if manifest.get("review_round_id") != REVIEW_ROUND_ID:
        errors.append(f"review_round_id must be {REVIEW_ROUND_ID}")
    if manifest.get("review_plan_status") not in ALLOWED_PLAN_STATUSES:
        errors.append("review_plan_status is invalid")
    if manifest.get("question_catalog") != EXPECTED_QUESTION_CATALOG:
        errors.append("manifest.question_catalog does not match the frozen prompts")

    gate_policy = manifest.get("gate_policy")
    if not isinstance(gate_policy, dict):
        errors.append("manifest.gate_policy must be an object")
    else:
        expected_values = {
            "required_domain_count": 7,
            "required_decision": "approve",
            "all_domains_required": True,
            "digest_change_invalidates_all_reviews": True,
            "ai_review_is_advisory_only": True,
            "contract_review_does_not_authorize_implementation": True,
            "principal_type_must_be_human": True,
            "same_actor_multiple_domains_requires_sod_exception": True,
            "decision_evidence_must_bind_decision_core_digest": True,
            "trust_roots_are_external_to_this_package": True,
        }
        _validate_exact_keys(
            gate_policy,
            set(expected_values),
            "manifest.gate_policy",
            errors,
        )
        for key, expected in expected_values.items():
            actual = gate_policy.get(key)
            if type(actual) is not type(expected) or actual != expected:
                errors.append(f"manifest.gate_policy.{key} must be {expected!r}")

    authorization = manifest.get("implementation_authorization")
    if not isinstance(authorization, dict):
        errors.append("manifest.implementation_authorization must be an object")
    else:
        _validate_exact_keys(
            authorization,
            {"authorized", "authorization_ref", "note"},
            "manifest.implementation_authorization",
            errors,
        )
        if authorization.get("authorized") is not False:
            errors.append(
                "this review package must keep "
                "implementation_authorization.authorized=false"
            )
        if authorization.get("authorization_ref") is not None:
            errors.append(
                "this review package cannot carry an implementation "
                "authorization reference"
            )

    verifier = manifest.get("external_trust_verifier")
    if not isinstance(verifier, dict):
        errors.append("manifest.external_trust_verifier must be an object")
        return
    _validate_exact_keys(
        verifier,
        {
            "status",
            "verifier_binding_ref",
            "trusted_actor_registry_ref",
            "trusted_role_assignment_registry_ref",
            "trusted_signature_or_audit_policy_ref",
            "trusted_finding_registry_ref",
            "append_only_decision_ledger_ref",
            "note",
        },
        "manifest.external_trust_verifier",
        errors,
    )
    if verifier.get("status") not in {
        "UNCONFIGURED",
        "REFERENCED-NOT-VERIFIED",
    }:
        errors.append("manifest.external_trust_verifier.status is invalid")
    for field in (
        "verifier_binding_ref",
        "trusted_actor_registry_ref",
        "trusted_role_assignment_registry_ref",
        "trusted_signature_or_audit_policy_ref",
        "trusted_finding_registry_ref",
        "append_only_decision_ledger_ref",
    ):
        _validate_string_or_null(
            verifier.get(field),
            f"manifest.external_trust_verifier.{field}",
            errors,
        )


def _validate_assignment(
    assignment: Any,
    prefix: str,
    errors: list[str],
) -> None:
    if not isinstance(assignment, dict):
        errors.append(f"{prefix}.reviewer_assignment must be an object")
        return
    _validate_exact_keys(
        assignment,
        {
            "reviewer_display_name",
            "reviewer_actor_id",
            "reviewer_principal_type",
            "reviewer_role_assignment_ref",
            "segregation_of_duties_exception_ref",
        },
        f"{prefix}.reviewer_assignment",
        errors,
    )
    for field in (
        "reviewer_display_name",
        "reviewer_actor_id",
        "reviewer_role_assignment_ref",
        "segregation_of_duties_exception_ref",
    ):
        _validate_string_or_null(
            assignment.get(field),
            f"{prefix}.reviewer_assignment.{field}",
            errors,
        )
    if assignment.get("reviewer_principal_type") != "human":
        errors.append(
            f"{prefix}.reviewer_assignment.reviewer_principal_type must be human"
        )


def _validate_core(
    core: Any,
    entry: dict[str, Any],
    path_label: str,
    errors: list[str],
) -> None:
    prefix = f"{path_label}:"
    if not isinstance(core, dict):
        errors.append(f"{prefix} decision core must be an object")
        return
    _validate_exact_keys(
        core,
        {
            "record_version",
            "review_round_id",
            "decision_id",
            "decision_revision",
            "previous_decision_core_digest",
            "review_plan_digest",
            "review_domain_id",
            "owner_role",
            "reviewer_display_name",
            "reviewer_actor_id",
            "reviewer_principal_type",
            "reviewer_role_assignment_ref",
            "responsibility_scope",
            "decision",
            "reviewed_contract_id",
            "reviewed_contract_digest",
            "reviewed_at",
            "review_answers",
            "open_blocking_findings_count",
            "findings_refs",
        },
        prefix,
        errors,
    )
    expected_pairs = {
        "record_version": CORE_VERSION,
        "review_round_id": REVIEW_ROUND_ID,
        "review_domain_id": entry.get("domain_id"),
        "owner_role": entry.get("owner_role"),
        "responsibility_scope": entry.get("responsibility_scope"),
        "reviewed_contract_id": CONTRACT_ID,
        "reviewed_contract_digest": f"sha256:{FROZEN_SHA256}",
        "reviewer_principal_type": "human",
    }
    for field, expected in expected_pairs.items():
        if core.get(field) != expected:
            errors.append(f"{prefix} {field} must be {expected!r}")
    for field in (
        "decision_id",
        "previous_decision_core_digest",
        "review_plan_digest",
        "reviewer_display_name",
        "reviewer_actor_id",
        "reviewer_role_assignment_ref",
        "reviewed_at",
    ):
        _validate_string_or_null(core.get(field), f"{prefix} {field}", errors)
    if type(core.get("decision_revision")) is not int or core.get(
        "decision_revision"
    ) != 1:
        errors.append(f"{prefix} decision_revision must be 1 for this review round")
    if core.get("previous_decision_core_digest") is not None:
        errors.append(
            f"{prefix} previous_decision_core_digest must be null in round 1"
        )
    if core.get("decision") not in ALLOWED_DECISIONS:
        errors.append(f"{prefix} decision is invalid")
    blocker_count = core.get("open_blocking_findings_count")
    if blocker_count is not None and (
        not isinstance(blocker_count, int)
        or isinstance(blocker_count, bool)
        or blocker_count < 0
    ):
        errors.append(
            f"{prefix} open_blocking_findings_count must be a non-negative "
            "integer or null"
        )
    _validate_string_list(core.get("findings_refs"), f"{prefix} findings_refs", errors)

    answers = core.get("review_answers")
    if not isinstance(answers, list):
        errors.append(f"{prefix} review_answers must be an array")
        return
    actual_question_ids: list[Any] = []
    for index, answer in enumerate(answers):
        answer_prefix = f"{prefix} review_answers[{index}]"
        if not isinstance(answer, dict):
            errors.append(f"{answer_prefix} must be an object")
            continue
        _validate_exact_keys(
            answer,
            {"question_id", "answer", "rationale", "finding_refs"},
            answer_prefix,
            errors,
        )
        actual_question_ids.append(answer.get("question_id"))
        if answer.get("answer") not in ALLOWED_ANSWERS:
            errors.append(f"{answer_prefix}.answer is invalid")
        _validate_string_or_null(
            answer.get("rationale"),
            f"{answer_prefix}.rationale",
            errors,
        )
        _validate_string_list(
            answer.get("finding_refs"),
            f"{answer_prefix}.finding_refs",
            errors,
        )
    if actual_question_ids != entry.get("required_question_ids"):
        errors.append(
            f"{prefix} question ids/order must equal "
            f"{entry.get('required_question_ids')!r}"
        )


def _validate_seal(
    seal: Any,
    entry: dict[str, Any],
    path_label: str,
    errors: list[str],
) -> None:
    prefix = f"{path_label}:"
    if not isinstance(seal, dict):
        errors.append(f"{prefix} decision seal must be an object")
        return
    _validate_exact_keys(
        seal,
        {
            "seal_version",
            "review_round_id",
            "review_domain_id",
            "decision_core_digest",
            "reviewer_actor_id",
            "credential_or_audit_actor_id",
            "actor_credential_binding_ref",
            "evidence_kind",
            "key_usage_or_audit_event_type",
            "signature_or_audit_evidence_ref",
            "trusted_timestamp",
            "trust_policy_ref",
            "trust_verification_receipt_ref",
        },
        prefix,
        errors,
    )
    expected_pairs = {
        "seal_version": SEAL_VERSION,
        "review_round_id": REVIEW_ROUND_ID,
        "review_domain_id": entry.get("domain_id"),
    }
    for field, expected in expected_pairs.items():
        if seal.get(field) != expected:
            errors.append(f"{prefix} {field} must be {expected!r}")
    if seal.get("evidence_kind") not in ALLOWED_EVIDENCE_KINDS:
        errors.append(f"{prefix} evidence_kind is invalid")
    for field in (
        "decision_core_digest",
        "reviewer_actor_id",
        "credential_or_audit_actor_id",
        "actor_credential_binding_ref",
        "key_usage_or_audit_event_type",
        "signature_or_audit_evidence_ref",
        "trusted_timestamp",
        "trust_policy_ref",
        "trust_verification_receipt_ref",
    ):
        _validate_string_or_null(seal.get(field), f"{prefix} {field}", errors)


def _load_reviews(
    package_dir: Path,
    manifest: dict[str, Any],
    errors: list[str],
) -> list[LoadedReview]:
    reviews = manifest.get("reviews")
    if not isinstance(reviews, list):
        errors.append("manifest.reviews must be an array")
        return []
    domain_ids = [
        entry.get("domain_id") if isinstance(entry, dict) else None
        for entry in reviews
    ]
    if tuple(domain_ids) != EXPECTED_DOMAIN_IDS:
        errors.append(
            "manifest.reviews must contain the seven frozen domains in "
            "canonical order"
        )

    loaded: list[LoadedReview] = []
    seen_paths: set[str] = set()
    for index, entry in enumerate(reviews):
        prefix = f"manifest.reviews[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{prefix} must be an object")
            continue
        _validate_exact_keys(
            entry,
            {
                "domain_id",
                "owner_role",
                "responsibility_scope",
                "required_question_ids",
                "reviewer_assignment",
                "decision_core_path",
                "decision_seal_path",
            },
            prefix,
            errors,
        )
        domain_id = entry.get("domain_id")
        expected_spec = EXPECTED_REVIEW_SPECS.get(domain_id)
        if expected_spec is None:
            errors.append(f"{prefix}.domain_id is not a frozen review domain")
        else:
            for field in (
                "owner_role",
                "responsibility_scope",
                "decision_core_path",
                "decision_seal_path",
            ):
                if entry.get(field) != expected_spec[field]:
                    errors.append(
                        f"{prefix}.{field} does not match the frozen review plan"
                    )
            if entry.get("required_question_ids") != list(
                expected_spec["required_question_ids"]
            ):
                errors.append(
                    f"{prefix}.required_question_ids does not match the frozen "
                    "review plan"
                )
        _validate_assignment(entry.get("reviewer_assignment"), prefix, errors)
        core_label = entry.get("decision_core_path")
        seal_label = entry.get("decision_seal_path")
        if not isinstance(core_label, str) or not core_label:
            errors.append(f"{prefix}.decision_core_path is missing")
            continue
        if not isinstance(seal_label, str) or not seal_label:
            errors.append(f"{prefix}.decision_seal_path is missing")
            continue
        for label in (core_label, seal_label):
            if label in seen_paths:
                errors.append(f"duplicate review artifact path: {label}")
            seen_paths.add(label)
        core_candidate = package_dir / core_label
        seal_candidate = package_dir / seal_label
        if core_candidate.is_symlink() or seal_candidate.is_symlink():
            errors.append(f"{prefix} decision core/seal must not be symlinks")
            continue
        core_path = core_candidate.resolve()
        seal_path = seal_candidate.resolve()
        try:
            core_path.relative_to(package_dir.resolve())
            seal_path.relative_to(package_dir.resolve())
        except ValueError:
            errors.append(
                f"{prefix} decision core/seal paths must stay inside the review package"
            )
            continue
        if not core_path.is_file():
            errors.append(f"decision core is missing: {core_label}")
            continue
        if not seal_path.is_file():
            errors.append(f"decision seal is missing: {seal_label}")
            continue
        try:
            core_snapshot = _load_json_snapshot(core_path)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            DuplicateJsonKeyError,
        ) as exc:
            errors.append(f"{core_label} is unreadable: {exc}")
            continue
        try:
            seal_snapshot = _load_json_snapshot(seal_path)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            DuplicateJsonKeyError,
        ) as exc:
            errors.append(f"{seal_label} is unreadable: {exc}")
            continue
        core = core_snapshot.value
        seal = seal_snapshot.value
        _validate_core(core, entry, core_label, errors)
        _validate_seal(seal, entry, seal_label, errors)
        if isinstance(core, dict) and isinstance(seal, dict):
            loaded.append(
                LoadedReview(
                    manifest_entry=entry,
                    core=core,
                    core_path=core_path,
                    core_digest=core_snapshot.digest,
                    seal=seal,
                    seal_path=seal_path,
                )
            )
    return loaded


def _assignment_blockers(
    manifest: dict[str, Any],
    reviews: list[LoadedReview],
) -> list[str]:
    blockers: list[str] = []
    if manifest.get("review_plan_status") != "FROZEN-FOR-REVIEW":
        blockers.append("review plan is not FROZEN-FOR-REVIEW")

    verifier = manifest["external_trust_verifier"]
    if verifier.get("status") != "REFERENCED-NOT-VERIFIED":
        blockers.append("organization-approved external trust verifier is unconfigured")
    missing_verifier_fields: list[str] = []
    for field in (
        "verifier_binding_ref",
        "trusted_actor_registry_ref",
        "trusted_role_assignment_registry_ref",
        "trusted_signature_or_audit_policy_ref",
        "trusted_finding_registry_ref",
        "append_only_decision_ledger_ref",
    ):
        if not _is_non_placeholder(verifier.get(field)):
            missing_verifier_fields.append(field)
    if missing_verifier_fields:
        blockers.append(
            "external trust verifier is missing: "
            + ", ".join(missing_verifier_fields)
        )

    actors_to_reviews: dict[str, list[LoadedReview]] = {}
    for review in reviews:
        domain_id = review.manifest_entry["domain_id"]
        assignment = review.manifest_entry["reviewer_assignment"]
        missing_assignment_fields: list[str] = []
        for field in (
            "reviewer_display_name",
            "reviewer_actor_id",
            "reviewer_role_assignment_ref",
        ):
            if not _is_non_placeholder(assignment.get(field)):
                missing_assignment_fields.append(field)
        if missing_assignment_fields:
            blockers.append(
                f"{domain_id}: assignment is missing "
                + ", ".join(missing_assignment_fields)
            )
        actor_id = assignment.get("reviewer_actor_id")
        if _is_non_placeholder(actor_id):
            actors_to_reviews.setdefault(actor_id, []).append(review)

    for actor_id, actor_reviews in actors_to_reviews.items():
        if len(actor_reviews) < 2:
            continue
        for review in actor_reviews:
            exception_ref = review.manifest_entry["reviewer_assignment"].get(
                "segregation_of_duties_exception_ref"
            )
            if not _is_non_placeholder(exception_ref):
                blockers.append(
                    f"{review.manifest_entry['domain_id']}: actor {actor_id!r} "
                    "covers multiple domains without a segregation-of-duties "
                    "exception"
                )
    return blockers


def _review_blockers(
    manifest: dict[str, Any],
    plan_digest: str,
    reviews: list[LoadedReview],
) -> list[str]:
    blockers = _assignment_blockers(manifest, reviews)
    if blockers:
        return blockers
    trust_policy_ref = manifest["external_trust_verifier"].get(
        "trusted_signature_or_audit_policy_ref"
    )
    decision_ids: dict[str, str] = {}

    for review in reviews:
        entry = review.manifest_entry
        core = review.core
        seal = review.seal
        assignment = entry["reviewer_assignment"]
        domain_id = entry["domain_id"]

        if core.get("review_plan_digest") != plan_digest:
            blockers.append(f"{domain_id}: review_plan_digest does not match plan")
        decision_id = core.get("decision_id")
        if not _is_non_placeholder(decision_id):
            blockers.append(f"{domain_id}: decision_id is missing")
        elif decision_id in decision_ids:
            blockers.append(
                f"{domain_id}: decision_id duplicates "
                f"{decision_ids[decision_id]}"
            )
        else:
            decision_ids[decision_id] = domain_id
        for field in (
            "reviewer_display_name",
            "reviewer_actor_id",
            "reviewer_role_assignment_ref",
        ):
            if core.get(field) != assignment.get(field):
                blockers.append(
                    f"{domain_id}: decision core {field} does not match assignment"
                )
        if core.get("decision") != "approve":
            blockers.append(
                f"{domain_id}: decision must be approve, got "
                f"{core.get('decision')!r}"
            )
        if not _is_rfc3339_with_offset(core.get("reviewed_at")):
            blockers.append(f"{domain_id}: reviewed_at must be RFC 3339 with offset")
        if core.get("open_blocking_findings_count") != 0:
            blockers.append(
                f"{domain_id}: open_blocking_findings_count must be exactly 0"
            )
        for answer in core.get("review_answers", []):
            if not isinstance(answer, dict):
                continue
            question_id = answer.get("question_id")
            if answer.get("answer") != "satisfied":
                blockers.append(f"{domain_id}/{question_id}: must be satisfied")
            if not _is_non_placeholder(answer.get("rationale")):
                blockers.append(
                    f"{domain_id}/{question_id}: concrete rationale is missing"
                )

        expected_core_digest = review.core_digest
        if seal.get("decision_core_digest") != expected_core_digest:
            blockers.append(
                f"{domain_id}: seal does not bind the exact decision core bytes"
            )
        if seal.get("reviewer_actor_id") != core.get("reviewer_actor_id"):
            blockers.append(f"{domain_id}: seal reviewer_actor_id does not match core")
        for field in (
            "credential_or_audit_actor_id",
            "actor_credential_binding_ref",
            "signature_or_audit_evidence_ref",
            "trusted_timestamp",
            "trust_verification_receipt_ref",
        ):
            if not _is_non_placeholder(seal.get(field)):
                blockers.append(f"{domain_id}: seal {field} is missing")
        if seal.get("evidence_kind") not in {
            "digital_signature",
            "immutable_audit_receipt",
        }:
            blockers.append(f"{domain_id}: seal evidence_kind is not final")
        if seal.get("key_usage_or_audit_event_type") != "contract-review":
            blockers.append(
                f"{domain_id}: seal key_usage_or_audit_event_type must be "
                "contract-review"
            )
        if seal.get("trust_policy_ref") != trust_policy_ref:
            blockers.append(
                f"{domain_id}: seal trust_policy_ref does not match review plan"
            )
        reviewed_at = _parse_rfc3339(core.get("reviewed_at"))
        trusted_timestamp = _parse_rfc3339(seal.get("trusted_timestamp"))
        if trusted_timestamp is None:
            blockers.append(
                f"{domain_id}: seal trusted_timestamp must be RFC 3339 with offset"
            )
        elif reviewed_at is not None and trusted_timestamp < reviewed_at:
            blockers.append(
                f"{domain_id}: seal trusted_timestamp predates reviewed_at"
            )
    blockers.append(EXTERNAL_TRUST_BLOCKER)
    return blockers


def _decision_status(reviews: list[LoadedReview]) -> str:
    decisions = [review.core.get("decision") for review in reviews]
    if "reject" in decisions:
        return "REJECTED"
    if "changes_required" in decisions:
        return "CHANGES_REQUIRED"
    return "PENDING"


def evaluate(package_dir: Path) -> GateEvaluation:
    package_dir = package_dir.resolve()
    errors: list[str] = []
    manifest, plan_digest = _read_manifest(package_dir, errors)
    reviews: list[LoadedReview] = []
    if manifest and plan_digest is not None:
        _validate_target(package_dir, manifest, errors)
        _validate_manifest_policy(manifest, errors)
        reviews = _load_reviews(package_dir, manifest, errors)

    if errors:
        return GateEvaluation(
            structure_errors=tuple(errors),
            approval_blockers=(),
            contract_review="INVALID",
            local_review_records_complete=False,
            eligible_for_separate_implementation_slice=False,
            implementation_authorized=False,
        )

    assert plan_digest is not None
    blockers = _review_blockers(manifest, plan_digest, reviews)
    status = _decision_status(reviews)
    local_complete = blockers == [EXTERNAL_TRUST_BLOCKER]
    if local_complete:
        status = "PENDING_EXTERNAL_VERIFICATION"
    return GateEvaluation(
        structure_errors=(),
        approval_blockers=tuple(blockers),
        contract_review=status,
        local_review_records_complete=local_complete,
        eligible_for_separate_implementation_slice=False,
        implementation_authorized=False,
    )


def _print_common(result: GateEvaluation) -> None:
    print(f"contract_review={result.contract_review}")
    print(
        "local_review_records_complete="
        f"{str(result.local_review_records_complete).lower()}"
    )
    print(
        "eligible_for_separate_implementation_slice="
        f"{str(result.eligible_for_separate_implementation_slice).lower()}"
    )
    print("implementation_authorized=false")
    print("production_schema_change=false")
    print("production_ready=false")


def _print_result(result: GateEvaluation, structure_only: bool) -> int:
    if result.structure_errors:
        print("REVIEW_PACK_STRUCTURE=INVALID")
        for error in result.structure_errors:
            print(f"- {error}")
        _print_common(result)
        return 1

    print("REVIEW_PACK_STRUCTURE=VALID")
    if structure_only:
        _print_common(result)
        return 0

    if result.approval_blockers:
        print("NAMED_REVIEW_GATE=FAIL_CLOSED")
        for blocker in result.approval_blockers:
            print(f"- {blocker}")
        _print_common(result)
        return 2

    print("NAMED_REVIEW_GATE=PASSED")
    _print_common(result)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--structure-only",
        action="store_true",
        help="Validate frozen bytes and review-pack structure only.",
    )
    mode.add_argument(
        "--require-approvals",
        action="store_true",
        help="Require all seven named, externally verified approvals (default).",
    )
    parser.add_argument(
        "--package-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Review package directory; defaults to this script's directory.",
    )
    args = parser.parse_args(argv)
    return _print_result(
        evaluate(args.package_dir),
        structure_only=args.structure_only,
    )


if __name__ == "__main__":
    sys.exit(main())
