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

import logging
import re
import threading
from datetime import datetime, timezone
from typing import Any, Callable

from ..knowledge.scopes import reconcile_agent_scopes
from ..storage import repos
from .eval_runner import compute_digest, load_eval_cases

logger = logging.getLogger(__name__)

_SUPPORTED = {("L0", "L1")}

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
        )


def _rescan_with_reconcile(agent_registry: Any, scope_registry: Any) -> None:
    """重扫必须复刻装配路径的对账顺序（异源审 P1-2）：scan 会把启动期因
    knowledge scope 违规被注销的 Agent 重新载入，reconcile 不跟上=静态安全门
    被晋升动作复活绕过。顺序契约同 bootstrap.assemble：reconcile 先于 sync。

    影子实例+原子发布（异源审 F1）：scan/reconcile 全程发生在影子上，活注册表
    经 adopt 一次性切换——其他请求线程绝不会读到「已重载未对账」的中间态。
    """
    shadow = type(agent_registry)(agent_registry.agents_dir, agent_registry.schema_path)
    shadow.scan()
    for rec in reconcile_agent_scopes(shadow, scope_registry):
        logger.warning(
            "晋升重扫对账拒绝注册 Agent %s：%s", rec["agent_id"], rec["reason"]
        )
    agent_registry.adopt(shadow)


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
    coverage_ok = (
        len(broken) == 0 and len(approved) >= 3 and _has_failure_path_case(approved) is True
    )
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
    finally:
        conn.close()
    current_digest = compute_digest(approved, pkg_dir, agent)
    if run is None:
        evidence_ok = False
        evidence_detail = f"eval_run 不存在：{eval_run_id!r}"
    else:
        conditions = {
            "属于本 agent": run["agent_id"] == agent_id,
            "run 已完成": run["status"] == "completed",
            "版本一致": str(run["agent_version"]) == current_version,
            "total>0": run["total"] > 0,
            "failed==0": run["failed"] == 0,
            "skipped==0": run["skipped"] == 0,
            "digest 一致（内容自评测以来未变）": (
                run.get("eval_cases_digest") is not None
                and run.get("eval_cases_digest") == current_digest
            ),
        }
        evidence_ok = all(v is True for v in conditions.values())
        evidence_detail = "; ".join(f"{k}={v}" for k, v in conditions.items())
    checks["eval_evidence"] = {"ok": evidence_ok is True, "detail": evidence_detail}

    # 3) changelog 非空
    changelog = pkg_dir / "changelog.md"
    changelog_ok = changelog.is_file() and changelog.read_text(encoding="utf-8").strip() != ""
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
        _rescan_with_reconcile(agent_registry, scope_registry)
        conn = conn_factory()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                agent_registry.sync_to_db(conn)
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()

    try:
        with open(yaml_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(new_text)
        with open(changelog_path, "a", encoding="utf-8", newline="") as fh:
            fh.write(changelog_entry)
        _rescan_with_reconcile(agent_registry, scope_registry)
        refreshed = agent_registry.get(agent_id)
        if refreshed is None or str(refreshed.get("maturity")) != to_maturity:
            raise RuntimeError(
                f"晋升重扫后 agent {agent_id} 状态异常（不存在或 maturity 未落 {to_maturity}），回滚"
            )
        conn = conn_factory()
        try:
            # 投影与审计记录同一显式事务（F2）：sync 已提交而 record 失败的
            # 「有 L1 投影无审计」分叉在事务边界上被消除。
            conn.execute("BEGIN IMMEDIATE")
            try:
                agent_registry.sync_to_db(conn)
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
    except Exception as commit_exc:
        logger.exception("晋升提交段异常，恢复磁盘与投影原状（agent=%s）", agent_id)
        try:
            _restore_disk_and_projection()
        except Exception:
            # 恢复自身失败=磁盘/内存/DB 可能不一致——critical 留痕但绝不遮蔽
            # 原始异常（原异常才是根因，恢复失败是它的连带）。
            logger.critical(
                "晋升回滚失败，agent %s 状态可能不一致，需人工核查（yaml SSOT 为准）",
                agent_id, exc_info=True,
            )
        raise commit_exc
    return promotion
