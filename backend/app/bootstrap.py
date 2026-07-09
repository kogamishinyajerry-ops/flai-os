"""共享装配路径：API 进程（main.py lifespan）与 Job Runner 进程唯一的注册表装配函数。

loop-auditor Mode A Finding 1（ADR-0015）：此前两进程各自手写 scan+sync 代码块，
结构性漂移温床——knowledge 对账（reconcile）若只加在一处，另一进程的门就是
半扇。本模块把「agent scan → tool scan → scope scan → reconcile → sync_to_db」
的顺序钉死在唯一一处；顺序本身是契约：reconcile 内部 deregister 必须先于
sync_to_db，否则被拒 Agent 仍会 upsert 进 agents 表（见 registry.deregister
docstring）。任何新增装配步骤只改这里，不得回到两处手写。
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .knowledge.scopes import ScopeRegistry, reconcile_agent_scopes
from .knowledge.service import KnowledgeService
from .model_gateway.gateway import ModelGateway
from .runtime.registry import AgentRegistry
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


def assemble(
    *,
    agents_dir: Path,
    tools_dir: Path,
    contracts_dir: Path,
    knowledge_dir: Path,
    conn_factory: Callable[[], sqlite3.Connection],
    profiles_path: Path | None = None,
) -> Assembly:
    """唯一装配函数：扫描三注册表 → knowledge 对账 → 同步 DB → 网关/服务构造。

    调用前置：DB 已 init（init_db），目录已存在。对账违规记录除返回外逐条
    warning 日志留痕（agent_registry.errors 里也有同内容，双处可见）。
    """
    agent_registry = AgentRegistry(agents_dir, contracts_dir / "agent.schema.json")
    agent_registry.scan()
    tool_registry = ToolRegistry(tools_dir, contracts_dir / "tool.schema.json")
    tool_registry.scan()
    scope_registry = ScopeRegistry(knowledge_dir, contracts_dir / "knowledge_scope.schema.json")
    scope_registry.scan()

    # reconcile（内部 deregister）必须先于 sync_to_db —— 顺序契约，勿动。
    reconcile_records = reconcile_agent_scopes(agent_registry, scope_registry)
    for rec in reconcile_records:
        logger.warning("knowledge 启动对账拒绝注册 Agent %s：%s", rec["agent_id"], rec["reason"])

    conn = conn_factory()
    try:
        agent_registry.sync_to_db(conn)
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
    )
