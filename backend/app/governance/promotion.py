"""L0→L1 晋升门（M10 治理闭环，ADR-0018）。

maturity 从「手改 yaml 即晋升的声明」变为「必须引用评测证据的可审计事实」。
docs/02 §L0-L3 准入条件表的 L1 行分解为五条判定——机器可判的机器判，机器
不可判的显式人工确认记名，绝不冒充（loop-auditor 设计审 D1/D2/D4/D6 落地）：

  1. 最小评测覆盖：approved case ≥ 3 且至少 1 个含 status_is failed 的失败
     路径 case（全 happy-path 的"全绿"不构成回归能力证明；八类全覆盖校验
     不在本批，已声明限制）；
  2. eval 证据：run 存在/属本 agent/agent_version 与当前注册版本一致/全绿
     （total>0 且 failed==0 且 skipped==0）/eval_cases_digest 与现存 approved
     case 重算值一致（内容变了=证据过期，无论版本号动没动）；
  3. changelog.md 存在且非空（空文件同缺失）；
  4. 反馈入口：平台级 POST /api/feedback 提供——如实标注"平台级提供"，
     不冒充 per-agent 验证；
  5. 异常路径处理：机器难判 → confirmations.exception_paths_handled **is True**
     （字符串 "true"/整数 1 等 truthy 非 bool 一律拒——本仓 requires_human_review
     truthiness fail-open 事故的同族防御）+ confirmed_by 记名。

全部通过才写回 agent.yaml（行级手术，byte 级保持其余内容）→ registry 重扫
→ promotions 表落审计记录。任何一条不过 → PromotionRejected 携逐条判定结果。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ..knowledge.scopes import reconcile_agent_scopes
from ..logging_setup import audit_event
from ..storage import repos
from .eval_runner import (
    compute_digest,
    inspect_snapshot_evidence,
    load_eval_cases,
)

logger = logging.getLogger(__name__)

_SUPPORTED = {("L0", "L1")}
_PROMOTION_GATE_CHECKS = frozenset(
    {
        "transition_supported",
        "min_eval_coverage",
        "eval_evidence",
        "changelog_nonempty",
        "feedback_channel",
        "manual_confirmation",
    }
)

# 晋升串行化（异源审 P1-6）：两个并发 promote 同一进程内串行——后到者在锁内
# 重读 registry 看到 L1 即被 transition_supported 拒绝。多进程部署下的跨进程
# 锁是 V0.1 已声明限制（与同步 eval 的 single-flight 同边界）。
_PROMOTION_LOCK = threading.Lock()


class PromotionRejected(Exception):
    """晋升被拒：携带逐条判定结果（API 层映射 422，工程师能看到差哪条）。"""

    def __init__(self, checks: dict[str, Any]) -> None:
        self.checks = checks
        failed_names = [k for k, v in checks.items() if v.get("ok") is not True]
        super().__init__(f"晋升条件未全部满足：{failed_names}")


def _pre_promotion_digest(
    approved: list[dict[str, Any]],
    package_dir: Path,
    agent: dict[str, Any],
    *,
    from_maturity: str,
    to_maturity: str,
) -> str | None:
    """逆转唯一 maturity 行，复算评测真正见过的晋升前包指纹。"""

    yaml_path = package_dir / "agent.yaml"
    raw = yaml_path.read_bytes()
    pattern = re.compile(
        rb"^(maturity:[ \t]*)"
        + re.escape(to_maturity.encode("utf-8"))
        + rb"([ \t]*\r?)$",
        flags=re.MULTILINE,
    )
    matches = list(pattern.finditer(raw))
    if len(matches) != 1:
        return None
    pre_promotion_yaml = pattern.sub(
        lambda match: (
            match.group(1)
            + from_maturity.encode("utf-8")
            + match.group(2)
        ),
        raw,
        count=1,
    )
    return compute_digest(
        approved,
        package_dir,
        agent,
        package_file_overrides={"agent.yaml": pre_promotion_yaml},
    )


def _coverage_is_sufficient(
    approved: list[dict[str, Any]], broken: list[dict[str, Any]]
) -> bool:
    return (
        len(broken) == 0
        and len(approved) >= 3
        and _has_failure_path_case(approved) is True
    )


def _changelog_is_nonempty(package_dir: Path) -> bool:
    changelog = package_dir / "changelog.md"
    return changelog.is_file() and changelog.read_text(encoding="utf-8").strip() != ""


def _parse_evidence_timestamp(value: Any) -> datetime | None:
    if isinstance(value, str) is not True or value.strip() == "":
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _eval_evidence_conditions(
    run: dict[str, Any],
    *,
    agent_id: str,
    agent_version: str,
    expected_digest: str | None,
    snapshot: dict[str, Any] | None,
) -> dict[str, bool]:
    """晋升与重启 attestation 共用同一组全绿且不可变的证据谓词。"""

    total = run.get("total")
    passed = run.get("passed")
    failed = run.get("failed")
    skipped = run.get("skipped")
    case_results = run.get("case_results")
    verdict_counts = {"passed": 0, "failed": 0, "skipped": 0}
    case_result_files: list[str] = []
    case_results_shape_ok = isinstance(case_results, list)
    if case_results_shape_ok is True:
        for result in case_results:
            if isinstance(result, dict) is not True:
                case_results_shape_ok = False
                break
            verdict = result.get("verdict")
            if verdict not in verdict_counts:
                case_results_shape_ok = False
                break
            case_file = result.get("case_file")
            if isinstance(case_file, str) is not True or case_file.strip() == "":
                case_results_shape_ok = False
                break
            case_result_files.append(case_file)
            verdict_counts[verdict] += 1
    case_results_match = (
        case_results_shape_ok is True
        and type(total) is int
        and type(passed) is int
        and type(failed) is int
        and type(skipped) is int
        and len(case_results) == total
        and verdict_counts["passed"] == passed
        and verdict_counts["failed"] == failed
        and verdict_counts["skipped"] == skipped
        and total == passed + failed + skipped
    )

    snapshot_handle = run.get("snapshot_handle")
    snapshot_exists = (
        isinstance(snapshot_handle, str)
        and snapshot_handle.strip() != ""
        and isinstance(snapshot, dict)
    )
    content_json = snapshot.get("content_json") if snapshot_exists is True else None
    snapshot_handle_matches = (
        isinstance(content_json, str)
        and snapshot_handle
        == "snap_" + hashlib.sha256(content_json.encode("utf-8")).hexdigest()
    )
    try:
        snapshot_content = (
            json.loads(content_json) if isinstance(content_json, str) else None
        )
    except (json.JSONDecodeError, RecursionError):
        snapshot_content = None
    snapshot_evidence = (
        inspect_snapshot_evidence(snapshot_content)
        if isinstance(snapshot_content, dict)
        else None
    )
    snapshot_recomputed_digest = (
        snapshot_evidence[0] if snapshot_evidence is not None else None
    )
    snapshot_approved_case_files = (
        snapshot_evidence[1] if snapshot_evidence is not None else None
    )
    case_files_match_snapshot = (
        case_results_shape_ok is True
        and snapshot_approved_case_files is not None
        and len(case_result_files) == len(set(case_result_files))
        and frozenset(case_result_files) == snapshot_approved_case_files
    )
    snapshot_identity_matches = (
        isinstance(snapshot_content, dict)
        and snapshot.get("agent_id") == agent_id
        and snapshot.get("agent_version") == agent_version
        and snapshot_content.get("agent_id") == agent_id
        and snapshot_content.get("agent_version") == agent_version
    )
    snapshot_digest_matches = (
        expected_digest is not None
        and isinstance(snapshot_content, dict)
        and snapshot.get("eval_cases_digest") == expected_digest
        and snapshot_content.get("eval_cases_digest") == expected_digest
        and snapshot_recomputed_digest == expected_digest
        and run.get("eval_cases_digest") == expected_digest
    )
    snapshot_created = _parse_evidence_timestamp(
        snapshot.get("created_at") if isinstance(snapshot, dict) else None
    )
    run_started = _parse_evidence_timestamp(run.get("started_at"))
    run_finished = _parse_evidence_timestamp(run.get("finished_at"))
    evidence_timeline_ok = (
        snapshot_created is not None
        and run_started is not None
        and run_finished is not None
        and snapshot_created <= run_started <= run_finished
    )

    return {
        "属于本 agent": run.get("agent_id") == agent_id,
        "run 已完成": run.get("status") == "completed",
        "版本一致": str(run.get("agent_version")) == agent_version,
        "total>0": type(total) is int and total > 0,
        "passed==total": (
            type(passed) is int and type(total) is int and passed == total
        ),
        "failed==0": type(run.get("failed")) is int and run.get("failed") == 0,
        "skipped==0": type(run.get("skipped")) is int and run.get("skipped") == 0,
        "digest 一致（内容自评测以来未变）": (
            expected_digest is not None
            and run.get("eval_cases_digest") == expected_digest
        ),
        "case_results 与四计数一致": case_results_match is True,
        "case_results 与 snapshot approved case 一一对应": (
            case_files_match_snapshot is True
        ),
        "snapshot 存在且 handle 绑定不可变内容": (
            snapshot_exists is True and snapshot_handle_matches is True
        ),
        "snapshot 身份一致": snapshot_identity_matches is True,
        "snapshot digest 与 run/当前包一致": snapshot_digest_matches is True,
        "snapshot<=run start<=finished 时间线有效": evidence_timeline_ok is True,
    }


def _snapshot_for_run(
    conn: sqlite3.Connection, run: dict[str, Any] | None
) -> dict[str, Any] | None:
    if run is None:
        return None
    handle = run.get("snapshot_handle")
    if isinstance(handle, str) is not True or handle.strip() == "":
        return None
    return repos.get_eval_snapshot(conn, handle)


def _promotion_record_attests(
    agent_registry: Any,
    agent: dict[str, Any],
    promotion: dict[str, Any],
    conn: sqlite3.Connection,
) -> bool:
    """严格核对一条 promotion 是否足以证明当前包的 L1 投影。"""

    checks = promotion.get("checks")
    checks_ok = (
        isinstance(checks, dict)
        and _PROMOTION_GATE_CHECKS.issubset(checks.keys())
        and all(
            isinstance(check, dict) and check.get("ok") is True
            for check in checks.values()
        )
    )
    confirmations = promotion.get("confirmations")
    confirmed_by = promotion.get("confirmed_by")
    eval_run_id = promotion.get("eval_run_id")
    record_ok = (
        promotion.get("agent_id") == agent.get("id")
        and promotion.get("agent_version") == agent.get("version")
        and promotion.get("from_maturity") == "L0"
        and promotion.get("to_maturity") == "L1"
        and checks_ok is True
        and isinstance(eval_run_id, str)
        and eval_run_id.strip() != ""
        and isinstance(confirmations, dict)
        and confirmations.get("exception_paths_handled") is True
        and isinstance(confirmed_by, str)
        and confirmed_by.strip() != ""
    )
    if record_ok is not True:
        return False

    try:
        run = repos.get_eval_run(conn, eval_run_id)
        if run is None:
            return False
        promotion_created = _parse_evidence_timestamp(promotion.get("created_at"))
        run_finished = _parse_evidence_timestamp(run.get("finished_at"))
        if (
            promotion_created is None
            or run_finished is None
            or (run_finished <= promotion_created) is not True
        ):
            return False
        snapshot = _snapshot_for_run(conn, run)
        package_dir = agent_registry.package_dir(str(agent.get("id")))
        approved, _drafts, broken = load_eval_cases(package_dir)
        current_digest = _pre_promotion_digest(
            approved,
            package_dir,
            agent,
            from_maturity="L0",
            to_maturity="L1",
        )
        evidence_conditions = _eval_evidence_conditions(
            run,
            agent_id=str(agent.get("id")),
            agent_version=str(agent.get("version")),
            expected_digest=current_digest,
            snapshot=snapshot,
        )
        changelog_ok = _changelog_is_nonempty(package_dir)
    except (sqlite3.Error, OSError, ValueError, TypeError, RecursionError):
        return False
    return (
        _coverage_is_sufficient(approved, broken) is True
        and changelog_ok is True
        and all(value is True for value in evidence_conditions.values())
    )


def reconcile_promotion_attestations(
    agent_registry: Any,
    conn: sqlite3.Connection,
    *,
    actor: str,
    exempt_agent_id: str | None = None,
) -> list[dict[str, str]]:
    """把无严格 promotion 证据的 L1 移出影子表；仅容许单个在途晋升例外。"""

    rejected: list[dict[str, str]] = []
    for agent in agent_registry.list():
        if agent.get("maturity") != "L1":
            continue
        agent_id = str(agent.get("id"))
        if exempt_agent_id is not None and agent_id == exempt_agent_id:
            continue
        try:
            promotions = repos.list_promotions(conn, agent_id)
        except (sqlite3.Error, ValueError, TypeError, RecursionError):
            promotions = []
        matched = any(
            _promotion_record_attests(agent_registry, agent, promotion, conn) is True
            for promotion in promotions
        )
        if matched is True:
            continue
        agent_version = str(agent.get("version"))
        reason = (
            f"Agent {agent_id}@{agent_version} maturity=L1 但无严格匹配的 "
            "promotion 审计记录，fail-closed 拒绝发布"
        )
        agent_registry.deregister(agent_id, reason)
        record = {
            "agent_id": agent_id,
            "agent_version": agent_version,
            "maturity": "L1",
            "reason": "missing-or-invalid-promotion",
        }
        rejected.append(record)
        logger.warning("promotion attestation 拒绝注册 Agent %s：%s", agent_id, reason)
        audit_event(
            "promotion_attestation",
            actor=actor,
            outcome="rejected",
            **record,
        )
    return rejected


def _has_failure_path_case(approved: list[dict[str, Any]]) -> bool:
    for case in approved:
        checks = case.get("checks")
        if not isinstance(checks, list):
            continue
        for check in checks:
            if (
                isinstance(check, dict)
                and check.get("kind") == "status_is"
                and check.get("value") == "failed"
            ):
                return True
    return False


def promote_agent(
    *,
    conn_factory: Callable[[], Any],
    agent_registry: Any,
    scope_registry: Any,
    agent_id: str,
    to_maturity: str,
    eval_run_id: str,
    confirmations: Any,
    confirmed_by: Any,
    attestation_records: list[dict[str, str]],
) -> dict[str, Any]:
    """执行 L0→L1 晋升；全部条件 is True 才生效，否则 PromotionRejected。

    调用方保证 agent 已注册（API 层 404 前置）。全程持进程内晋升锁。
    """
    with _PROMOTION_LOCK:
        return _promote_agent_locked(
            conn_factory=conn_factory,
            agent_registry=agent_registry,
            scope_registry=scope_registry,
            agent_id=agent_id,
            to_maturity=to_maturity,
            eval_run_id=eval_run_id,
            confirmations=confirmations,
            confirmed_by=confirmed_by,
            attestation_records=attestation_records,
        )


def _build_reconciled_shadow(
    agent_registry: Any,
    scope_registry: Any,
    conn_factory: Callable[[], Any],
    *,
    exempt_agent_id: str | None = None,
) -> tuple[Any, list[dict[str, str]]]:
    """重扫必须复刻装配路径的对账顺序（异源审 P1-2）：scan 会把启动期因
    knowledge scope 违规被注销的 Agent 重新载入，reconcile 不跟上=静态安全门
    被晋升动作复活绕过。顺序契约同 bootstrap.assemble：reconcile 先于 sync。

    scan/reconcile/attestation 全程发生在影子上；调用方必须等 DB 投影与 promotion
    审计事务提交后才能 adopt，避免并发读者观察到无 durable 证明的 L1。
    """
    shadow = type(agent_registry)(agent_registry.agents_dir, agent_registry.schema_path)
    shadow.scan()
    for rec in reconcile_agent_scopes(shadow, scope_registry):
        logger.warning(
            "晋升重扫对账拒绝注册 Agent %s：%s", rec["agent_id"], rec["reason"]
        )
    conn = conn_factory()
    try:
        rejected = reconcile_promotion_attestations(
            shadow,
            conn,
            actor="promotion-rescan",
            exempt_agent_id=exempt_agent_id,
        )
    finally:
        conn.close()
    return shadow, rejected


def _promote_agent_locked(
    *,
    conn_factory: Callable[[], Any],
    agent_registry: Any,
    scope_registry: Any,
    agent_id: str,
    to_maturity: str,
    eval_run_id: str,
    confirmations: Any,
    confirmed_by: Any,
    attestation_records: list[dict[str, str]],
) -> dict[str, Any]:
    agent = agent_registry.get(agent_id)
    if agent is None:
        raise ValueError(f"agent 不存在：{agent_id}")
    pkg_dir = agent_registry.package_dir(agent_id)
    current_maturity = str(agent.get("maturity"))
    current_version = str(agent.get("version"))

    checks: dict[str, Any] = {}

    # 0) 支持的晋升轴（本批仅 L0→L1；降级与 L2+ 属人工域，范围外）
    transition_ok = (current_maturity, to_maturity) in _SUPPORTED
    checks["transition_supported"] = {
        "ok": transition_ok is True,
        "detail": f"{current_maturity} → {to_maturity}（本批仅支持 L0→L1）",
    }

    # 1) 最小评测覆盖（D1）
    approved, _drafts, broken = load_eval_cases(pkg_dir)
    coverage_ok = _coverage_is_sufficient(approved, broken)
    checks["min_eval_coverage"] = {
        "ok": coverage_ok is True,
        "detail": (
            f"approved case={len(approved)}（需 ≥3）；失败路径 case="
            f"{_has_failure_path_case(approved)}（需含 status_is failed）；"
            f"损坏 case={len(broken)}（需 0）。八类全覆盖校验不在本批（已声明限制）"
        ),
    }

    # 2) eval 证据（含 D2 digest 咬合）
    conn = conn_factory()
    try:
        run = repos.get_eval_run(conn, str(eval_run_id)) if eval_run_id else None
        snapshot = _snapshot_for_run(conn, run)
    finally:
        conn.close()
    current_digest = compute_digest(approved, pkg_dir, agent)
    if run is None:
        evidence_ok = False
        evidence_detail = f"eval_run 不存在：{eval_run_id!r}"
    else:
        conditions = _eval_evidence_conditions(
            run,
            agent_id=agent_id,
            agent_version=current_version,
            expected_digest=current_digest,
            snapshot=snapshot,
        )
        evidence_ok = all(v is True for v in conditions.values())
        evidence_detail = "; ".join(f"{k}={v}" for k, v in conditions.items())
    checks["eval_evidence"] = {"ok": evidence_ok is True, "detail": evidence_detail}

    # 3) changelog 非空
    changelog_ok = _changelog_is_nonempty(pkg_dir)
    checks["changelog_nonempty"] = {
        "ok": changelog_ok is True,
        "detail": "changelog.md 存在且非空" if changelog_ok else "changelog.md 缺失或为空文件",
    }

    # 4) 反馈入口（如实标注：平台级提供，非 per-agent 验证）
    checks["feedback_channel"] = {
        "ok": True,
        "detail": "POST /api/feedback 平台级提供（不冒充 per-agent 验证）",
    }

    # 5) 人工确认项（D6：缺失/false/非 bool 一律拒）
    confirm_value = confirmations.get("exception_paths_handled") if isinstance(confirmations, dict) else None
    confirm_ok = confirm_value is True and isinstance(confirmed_by, str) and confirmed_by.strip() != ""
    checks["manual_confirmation"] = {
        "ok": confirm_ok is True,
        "detail": (
            f"exception_paths_handled={confirm_value!r}（必须是布尔 true）；"
            f"confirmed_by={confirmed_by!r}（必须记名）"
        ),
    }

    if not all(v["ok"] is True for v in checks.values()):
        raise PromotionRejected(checks)

    # 全部通过：agent.yaml 行级手术。newline 保真（异源审 P3-15）：open(newline="")
    # 读写原样字节级换行，正则用 [ \t] 不吞空行、\r? 兼容 CRLF；恰好一行才动刀。
    yaml_path = pkg_dir / "agent.yaml"
    with open(yaml_path, encoding="utf-8", newline="") as fh:
        text = fh.read()
    pattern = re.compile(
        rf"^(maturity:[ \t]*){re.escape(current_maturity)}([ \t]*\r?)$", flags=re.MULTILINE
    )
    matches = pattern.findall(text)
    if len(matches) != 1:
        raise PromotionRejected({
            **checks,
            "yaml_surgery": {
                "ok": False,
                "detail": f"agent.yaml 中 maturity 行匹配数={len(matches)}（需恰好 1），拒绝手术",
            },
        })
    new_text = pattern.sub(rf"\g<1>{to_maturity}\g<2>", text, count=1)

    # changelog 追加（异源审 P2-13：docs/02 要求 maturity 变更留版本化轨迹）
    changelog_path = pkg_dir / "changelog.md"
    with open(changelog_path, encoding="utf-8", newline="") as fh:
        changelog_original = fh.read()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    changelog_entry = (
        f"\n- {stamp} maturity {current_maturity}→{to_maturity}"
        f"（晋升门放行，eval_run={eval_run_id}，confirmed_by={confirmed_by.strip()}）\n"
    )
    operation_token = uuid.uuid4().hex
    pending_fault = {
        "agent_id": agent_id,
        "agent_version": current_version,
        "maturity": to_maturity,
        "operation_token": operation_token,
        "reason": "promotion-operation-pending",
    }
    pending_detail = json.dumps(
        pending_fault,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    preserve_operation_latch_on_failure = False
    baseline_conn = conn_factory()
    try:
        baseline_promotion_count = int(
            baseline_conn.execute(
                """
                SELECT COUNT(*) AS n
                FROM promotions
                WHERE agent_id = ? AND agent_version = ?
                  AND from_maturity = ? AND to_maturity = ?
                """,
                (
                    agent_id,
                    current_version,
                    current_maturity,
                    to_maturity,
                ),
            ).fetchone()["n"]
        )
    finally:
        baseline_conn.close()

    def _persist_new_runtime_rejections(
        records: list[dict[str, str]],
    ) -> bool:
        """把本次新发现的拒载升级为跨进程故障；返回是否存在新拒载。"""

        nonlocal preserve_operation_latch_on_failure
        new_rejections = [
            record for record in records if record not in attestation_records
        ]
        for record in new_rejections:
            attestation_records.append(record)
        if not new_rejections:
            return False

        # 独立 worker 只认共享 DB。先把本次 write-ahead pending latch CAS
        # 升级为持久故障；CAS 失败/写库异常时也保留原 pending latch。
        preserve_operation_latch_on_failure = True
        runtime_fault = {
            "agent_id": agent_id,
            "agent_version": current_version,
            "maturity": to_maturity,
            "operation_token": operation_token,
            "reason": "promotion-runtime-attestation-rejected",
            "rejections": new_rejections,
        }
        runtime_fault_detail = json.dumps(
            runtime_fault,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        fault_conn = None
        persistent_fault_updated = False
        try:
            fault_conn = conn_factory()
            persistent_fault_updated = (
                repos.update_promotion_attestation_fault(
                    fault_conn,
                    expected_detail=pending_detail,
                    detail=runtime_fault_detail,
                )
                is True
            )
        except Exception:
            logger.critical(
                "运行期 promotion attestation 拒载无法升级持久 latch；"
                "保留 operation pending latch，拒绝继续晋升",
                exc_info=True,
            )
        finally:
            if fault_conn is not None:
                fault_conn.close()
        checks["runtime_attestation"] = {
            "ok": False,
            "detail": (
                f"运行期重扫新拒载 {len(new_rejections)} 个 L1；"
                f"persistent_fault_updated={persistent_fault_updated}；"
                "拒绝晋升并保留持久 latch"
            ),
        }
        return True

    # 提交序（异源审 P1-3/F2 补偿式回滚）：磁盘写入 → 重扫+对账 → 单事务内
    # DB 投影+审计记录。任何异常都恢复磁盘原文、重扫并把 DB 投影同步回原状
    # ——绝不留下「yaml 已 L1 但无 promotions 审计记录」或「DB 已 L1 而 yaml
    # 已回滚」的半提交状态。进程在磁盘写入与 DB 提交之间崩溃的窗口无法在
    # 单机无日志架构下消除，属 ADR 已声明限制（重启后以 yaml SSOT 重新装配，
    # 但审计记录可能缺失——发现 L1 无对应 promotions 记录须人工核查）。
    def _restore_disk_and_projection() -> None:
        with open(yaml_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        with open(changelog_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(changelog_original)
        restored_shadow, restored_rejections = _build_reconciled_shadow(
            agent_registry, scope_registry, conn_factory
        )
        _persist_new_runtime_rejections(restored_rejections)
        conn = conn_factory()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                restored_shadow.sync_to_db(conn)
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()
        agent_registry.adopt(restored_shadow)

    def _clear_operation_latch() -> bool:
        latch_conn = None
        try:
            latch_conn = conn_factory()
            return repos.clear_promotion_attestation_fault(
                latch_conn,
                expected_detail=pending_detail,
            )
        except Exception:
            logger.critical(
                "promotion operation latch 无法 CAS 清除；保持治理轴红态",
                exc_info=True,
            )
            return False
        finally:
            if latch_conn is not None:
                latch_conn.close()

    # write-ahead fault latch：必须在首次磁盘手术前 durable。若共享 DB 已只读/
    # 不可写，此处直接失败且 YAML 尚未触碰；不能等提交/回滚失败后才 best-effort
    # 写故障，因为导致提交失败的同一 DB 故障也会让迟到的 latch 写不进去。
    latch_conn = conn_factory()
    try:
        if repos.record_promotion_attestation_fault(
            latch_conn,
            detail=pending_detail,
        ) is not True:
            raise PromotionRejected(
                {
                    **checks,
                    "promotion_operation_latch": {
                        "ok": False,
                        "detail": (
                            "已有未解除的 promotion operation/fault latch；"
                            "拒绝触碰磁盘，须先人工核查"
                        ),
                    },
                }
            )
        # 跨进程 stale-registry ABA：另一进程可能在本调用完成初始五门后先拿
        # latch、完成 L0→L1 并清 latch；本调用随后重新拿到空 latch，内存仍是
        # 旧 L0。故 latch 获取只是互斥，不是新鲜性证明。首次触盘前在同一 latch
        # 持有期把磁盘原文、DB 投影及成功审计记录与本次早先捕获做 CAS 式核对。
        with open(yaml_path, encoding="utf-8", newline="") as fh:
            fresh_yaml = fh.read()
        with open(changelog_path, encoding="utf-8", newline="") as fh:
            fresh_changelog = fh.read()
        db_agent = latch_conn.execute(
            "SELECT version, maturity FROM agents WHERE id = ?",
            (agent_id,),
        ).fetchone()
        current_promotion_count = int(latch_conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM promotions
            WHERE agent_id = ? AND agent_version = ?
              AND from_maturity = ? AND to_maturity = ?
            """,
            (
                agent_id,
                current_version,
                current_maturity,
                to_maturity,
            ),
        ).fetchone()["n"])
        disk_fresh = (
            fresh_yaml == text and fresh_changelog == changelog_original
        )
        db_fresh = (
            db_agent is not None
            and str(db_agent["version"]) == current_version
            and str(db_agent["maturity"]) == current_maturity
            and current_promotion_count == baseline_promotion_count
        )
        if disk_fresh is not True or db_fresh is not True:
            latch_cleared = repos.clear_promotion_attestation_fault(
                latch_conn,
                expected_detail=pending_detail,
            )
            if latch_cleared is not True:
                latch_fault = {
                    "agent_id": agent_id,
                    "agent_version": current_version,
                    "maturity": current_maturity,
                    "reason": "promotion-operation-latch-clear-failed",
                }
                if latch_fault not in attestation_records:
                    attestation_records.append(latch_fault)
            raise PromotionRejected(
                {
                    **checks,
                    "promotion_freshness": {
                        "ok": False,
                        "detail": (
                            "获取 operation latch 后新鲜性复核失败，拒绝触盘："
                            f"disk_fresh={disk_fresh}; db_fresh={db_fresh}; "
                            "promotion_count="
                            f"{baseline_promotion_count}→{current_promotion_count}"
                        ),
                    },
                }
            )
    finally:
        latch_conn.close()

    try:
        with open(yaml_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(new_text)
        with open(changelog_path, "a", encoding="utf-8", newline="") as fh:
            fh.write(changelog_entry)
        promoted_shadow, runtime_rejections = _build_reconciled_shadow(
            agent_registry,
            scope_registry,
            conn_factory,
            exempt_agent_id=agent_id,
        )
        # 新拒载必须在本次晋升继续前持久闭锁；启动时已知且已在内存轴红色的
        # 同一拒载不重复升级，保持既有“其他合法 Agent 可晋升但拒载者不复活”契约。
        if _persist_new_runtime_rejections(runtime_rejections):
            raise PromotionRejected(checks)
        refreshed = promoted_shadow.get(agent_id)
        if refreshed is None or str(refreshed.get("maturity")) != to_maturity:
            raise RuntimeError(
                f"晋升重扫后 agent {agent_id} 状态异常（不存在或 maturity 未落 {to_maturity}），回滚"
            )
        # 初次五门判定与磁盘手术之间仍存在并发改包窗口。按目标 id 豁免只是允许
        # “刚写入 L1、审计尚待同事务提交”的 shadow 被扫描，绝不等于豁免证据。
        # 发布前从 shadow 对应的当前磁盘包重载 case/manifest，并只把唯一
        # maturity L1 行逆变换回 L0 后重算 eval digest；prompt/workflow/schema/
        # case 任一额外字节变化都会令旧证据失效，随后走既有补偿回滚。
        refreshed_approved, _refreshed_drafts, refreshed_broken = load_eval_cases(
            pkg_dir
        )
        refreshed_coverage_ok = _coverage_is_sufficient(
            refreshed_approved, refreshed_broken
        )
        checks["min_eval_coverage"] = {
            "ok": refreshed_coverage_ok is True,
            "detail": (
                f"approved case={len(refreshed_approved)}（需 ≥3）；失败路径 case="
                f"{_has_failure_path_case(refreshed_approved)}（需含 status_is failed）；"
                f"损坏 case={len(refreshed_broken)}（需 0）。"
                "发布前已重载当前包复核"
            ),
        }
        refreshed_digest = _pre_promotion_digest(
            refreshed_approved,
            pkg_dir,
            refreshed,
            from_maturity=current_maturity,
            to_maturity=to_maturity,
        )
        evidence_conn = conn_factory()
        try:
            refreshed_run = repos.get_eval_run(
                evidence_conn, str(eval_run_id)
            )
            refreshed_snapshot = _snapshot_for_run(
                evidence_conn, refreshed_run
            )
        finally:
            evidence_conn.close()
        refreshed_conditions = _eval_evidence_conditions(
            refreshed_run or {},
            agent_id=agent_id,
            agent_version=str(refreshed.get("version")),
            expected_digest=refreshed_digest,
            snapshot=refreshed_snapshot,
        )
        refreshed_evidence_ok = all(
            value is True for value in refreshed_conditions.values()
        )
        checks["eval_evidence"] = {
            "ok": refreshed_evidence_ok is True,
            "detail": "; ".join(
                f"{key}={value}" for key, value in refreshed_conditions.items()
            )
            + "; 发布前已重载当前包复核",
        }
        refreshed_changelog_ok = _changelog_is_nonempty(pkg_dir)
        checks["changelog_nonempty"] = {
            "ok": refreshed_changelog_ok is True,
            "detail": (
                "changelog.md 存在且非空（发布前复核）"
                if refreshed_changelog_ok
                else "changelog.md 缺失或为空文件（发布前复核）"
            ),
        }
        if (
            refreshed_coverage_ok is not True
            or refreshed_evidence_ok is not True
            or refreshed_changelog_ok is not True
        ):
            raise PromotionRejected(checks)
        conn = conn_factory()
        try:
            # 投影与审计记录同一显式事务（F2）：sync 已提交而 record 失败的
            # 「有 L1 投影无审计」分叉在事务边界上被消除。
            conn.execute("BEGIN IMMEDIATE")
            try:
                promoted_shadow.sync_to_db(conn)
                promotion = repos.record_promotion(
                    conn,
                    agent_id=agent_id,
                    agent_version=current_version,
                    from_maturity=current_maturity,
                    to_maturity=to_maturity,
                    eval_run_id=str(eval_run_id),
                    checks=checks,
                    confirmations={"exception_paths_handled": True},
                    confirmed_by=confirmed_by.strip(),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()
        # DB 投影与 promotion 审计已 durable 后才一次性公开 L1；commit→adopt
        # 窗口只会保守地继续呈现 L0，不会产生假绿。
        agent_registry.adopt(promoted_shadow)
    except Exception as commit_exc:
        logger.exception("晋升提交段异常，恢复磁盘与投影原状（agent=%s）", agent_id)
        restored = False
        try:
            _restore_disk_and_projection()
            restored = True
        except Exception:
            # 恢复自身失败=磁盘/内存/DB 可能不一致——critical 留痕但绝不遮蔽
            # 原始异常（原异常才是根因，恢复失败是它的连带）。同时把故障写入
            # 进程内 sticky attestation 轴：即使 live registry 仍保守显示 L0，
            # health/deploy_selfcheck 也必须红，直到人工核查并重启重建事实。
            rollback_fault = {
                "agent_id": agent_id,
                "agent_version": current_version,
                "maturity": to_maturity,
                "operation_token": operation_token,
                "reason": "promotion-rollback-failed",
            }
            if rollback_fault not in attestation_records:
                attestation_records.append(rollback_fault)
            # CLI 与 API/worker 是不同进程，单写调用方内存列表会在 CLI 退出后
            # 消失。复用 worker_heartbeats 的独立保留行持久锁存；default 周期
            # 心跳不会覆盖它，后续 health/readyz/selfcheck/worker 装配均可见。
            fault_conn = None
            try:
                fault_conn = conn_factory()
                rollback_detail = json.dumps(
                    rollback_fault,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                if repos.update_promotion_attestation_fault(
                    fault_conn,
                    expected_detail=pending_detail,
                    detail=rollback_detail,
                ) is not True:
                    repos.record_promotion_attestation_fault(
                        fault_conn,
                        detail=rollback_detail,
                    )
            except Exception:
                logger.critical(
                    "promotion 回滚故障无法写入跨进程持久 latch；"
                    "当前进程仍保持内存红态",
                    exc_info=True,
                )
            finally:
                if fault_conn is not None:
                    fault_conn.close()
            logger.critical(
                "晋升回滚失败，agent %s 状态可能不一致，需人工核查（yaml SSOT 为准）",
                agent_id, exc_info=True,
            )
        if (
            restored is True
            and preserve_operation_latch_on_failure is not True
            and _clear_operation_latch() is not True
        ):
            latch_fault = {
                "agent_id": agent_id,
                "agent_version": current_version,
                "maturity": current_maturity,
                "reason": "promotion-operation-latch-clear-failed",
            }
            if latch_fault not in attestation_records:
                attestation_records.append(latch_fault)
        raise commit_exc
    if _clear_operation_latch() is not True:
        latch_fault = {
            "agent_id": agent_id,
            "agent_version": current_version,
            "maturity": to_maturity,
            "reason": "promotion-operation-latch-clear-failed",
        }
        if latch_fault not in attestation_records:
            attestation_records.append(latch_fault)
        raise RuntimeError(
            "promotion 已提交但 operation latch 清除失败；"
            "治理健康保持红态，须人工核查"
        )
    return promotion
