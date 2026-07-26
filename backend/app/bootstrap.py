"""共享装配路径：API 进程（main.py lifespan）与 Job Runner 进程唯一的注册表装配函数。

loop-auditor Mode A Finding 1（ADR-0015）：此前两进程各自手写 scan+sync 代码块，
结构性漂移温床——knowledge 对账（reconcile）若只加在一处，另一进程的门就是
半扇。本模块把「agent scan → tool scan → scope scan → knowledge reconcile →
promotion attestation → sync_to_db」的顺序钉死在唯一一处；顺序本身是契约：
两个 reconcile/attestation 内部的 deregister 必须先于 sync_to_db，否则被拒
Agent 仍会 upsert 进 agents 表（见 registry.deregister docstring）。任何新增
装配步骤只改这里，不得回到两处手写。
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .governance.promotion import reconcile_promotion_attestations
from .knowledge.scopes import ScopeRegistry, reconcile_agent_scopes
from .knowledge.service import KnowledgeService
from .model_gateway.gateway import ModelGateway
from .runtime.registry import AgentRegistry
from .storage import repos
from .tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

_DEFAULT_PROFILES_PATH = Path(__file__).resolve().parent / "model_gateway" / "profiles.yaml"


@dataclass
class Assembly:
    """assemble() 的产物包：两进程从这里取共享对象，不再各自构造。"""

    agent_registry: AgentRegistry
    tool_registry: ToolRegistry
    scope_registry: ScopeRegistry
    knowledge_service: KnowledgeService
    model_gateway: ModelGateway
    reconcile_records: list[dict[str, str]] = field(default_factory=list)
    promotion_attestation_records: list[dict[str, str]] = field(default_factory=list)


def assemble(
    *,
    agents_dir: Path,
    tools_dir: Path,
    contracts_dir: Path,
    knowledge_dir: Path,
    conn_factory: Callable[[], sqlite3.Connection],
    profiles_path: Path | None = None,
) -> Assembly:
    """唯一装配函数：扫描 → knowledge 对账 → promotion attestation → DB 同步。

    调用前置：DB 已 init（init_db），目录已存在。两类拒载记录除返回外逐条
    warning/audit 留痕（agent_registry.errors 里也有同内容，可诊断）。
    """
    agent_registry = AgentRegistry(agents_dir, contracts_dir / "agent.schema.json")
    agent_registry.scan()
    tool_registry = ToolRegistry(tools_dir, contracts_dir / "tool.schema.json")
    tool_registry.scan()
    scope_registry = ScopeRegistry(knowledge_dir, contracts_dir / "knowledge_scope.schema.json")
    scope_registry.scan()

    # knowledge reconcile（内部 deregister）必须先于 attestation 与 sync_to_db。
    reconcile_records = reconcile_agent_scopes(agent_registry, scope_registry)
    for rec in reconcile_records:
        logger.warning("knowledge 启动对账拒绝注册 Agent %s：%s", rec["agent_id"], rec["reason"])

    conn = conn_factory()
    try:
        # GH #3：scope reconcile 后、首次 DB sync 前核对 L1↔promotions。晋升重扫
        # 复用同一门，但只豁免已过五门、尚待同事务落审计的唯一 in-flight agent。
        promotion_attestation_records = reconcile_promotion_attestations(
            agent_registry, conn, actor="bootstrap"
        )
        persistent_fault = repos.get_promotion_attestation_fault(conn)
        if persistent_fault is not None:
            try:
                fault_detail = json.loads(persistent_fault.get("detail"))
            except (json.JSONDecodeError, TypeError, RecursionError):
                fault_detail = {}
            if isinstance(fault_detail, dict) is not True:
                fault_detail = {}
            promotion_attestation_records.append(
                {
                    "agent_id": str(
                        fault_detail.get("agent_id")
                        or "<promotion-attestation-fault>"
                    ),
                    "agent_version": str(
                        fault_detail.get("agent_version") or "<unknown>"
                    ),
                    "maturity": str(
                        fault_detail.get("maturity") or "<unknown>"
                    ),
                    "reason": str(
                        fault_detail.get("reason")
                        or "persistent-promotion-attestation-fault"
                    ),
                }
            )
        agent_registry.sync_to_db(conn)
        # ADR-0025 D4：存量任务不可变分级回填。放此处（registry 已载、conn 可用），
        # 迁移只加列不回填（init_db 无注册表算不出 sensitive 工具集）。sensitive 工具集
        # = 当前注册表里 output_classification 非显式 internal 的工具（fail-closed 过近似，
        # 与 runtime._tool_taint_classification 同口径）。幂等、锁内，双进程启动安全。
        all_tools = tool_registry.list()
        sensitive_tool_ids = [
            tool["id"] for tool in all_tools if tool.get("output_classification") != "internal"
        ]
        # 全部已注册工具 id（sensitive+internal）：回填据此把「引用了当前不认识工具」的
        # 历史任务 fail-closed 判 sensitive（卸载/改名工具分级不可考，Codex R0 P1-3）。
        known_tool_ids = [tool["id"] for tool in all_tools]
        backfilled = repos.backfill_task_data_classification(
            conn, sensitive_tool_ids, known_tool_ids
        )
        if backfilled:
            logger.info(
                "ADR-0025 存量任务分级回填：%d 个终态任务（sensitive 工具集=%s）",
                backfilled, sensitive_tool_ids or "空",
            )
    finally:
        conn.close()

    model_gateway = ModelGateway(
        profiles_path if profiles_path is not None else _DEFAULT_PROFILES_PATH,
        conn_factory=conn_factory,
    )
    knowledge_service = KnowledgeService(scope_registry)
    return Assembly(
        agent_registry=agent_registry,
        tool_registry=tool_registry,
        scope_registry=scope_registry,
        knowledge_service=knowledge_service,
        model_gateway=model_gateway,
        reconcile_records=reconcile_records,
        promotion_attestation_records=promotion_attestation_records,
    )
