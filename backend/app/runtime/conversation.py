"""ConversationService：interactive 型 Agent 的会话运行时（M6，ADR-0012）。

与 JobRunner 对称——JobRunner 驱动 job 模型的一次性任务，ConversationService
驱动 interactive 模型的多轮会话。轻内核纪律：无 Redis/Celery，纯 SQLite 两表
（conversations / conversation_messages）+ 同步请求-响应（对话本就是同步交互，
不需后台轮询）。

职责边界（只做通用会话编排，不含任何导引业务逻辑）：
- 维护会话生命周期与消息持久化；
- 逐轮把会话历史转发到 Agent 包的 `run(context)`（统一入口，interactive 型
  context 形态见 ADR-0012 决策 3）；
- 落回 assistant 回复与其可能携带的推荐（预填任务草案）快照。

导引「如何组织追问、如何结构化并校验推荐」全在其 workflow.py（插件模型，
宪法：Agent=插件）。ConversationService 绝不解析对话内容、绝不据 LLM 输出下
结论、更绝不代替人创建/签发下游任务——推荐只是草案，人在 tasks 端点签发。
"""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any, Callable

from ..core.errors import (
    ConversationClosedError,
    ConversationNotFoundError,
    NotInteractiveAgentError,
)
from ..storage import repos
from .runtime import _load_workflow_module


def is_interactive(agent: dict[str, Any]) -> bool:
    """agent.yaml.workflow.mode == 'interactive'（ADR-0012 唯一判据）。"""
    return (agent.get("workflow", {}) or {}).get("mode") == "interactive"


class ConversationService:
    def __init__(
        self,
        agent_registry: Any,
        model_gateway: Any,
        conn_factory: Callable[[], sqlite3.Connection],
    ) -> None:
        self.agent_registry = agent_registry
        self.model_gateway = model_gateway
        self.conn_factory = conn_factory

    # ── 会话生命周期 ─────────────────────────────────────────────────────

    def create(self, *, agent_id: str, created_by: str) -> dict[str, Any]:
        """建会话：Agent 必须存在且为 interactive 型，否则如实拒绝。"""
        agent = self.agent_registry.get(agent_id)
        if agent is None:
            raise ConversationNotFoundError(f"agent 不存在：{agent_id}")
        if not is_interactive(agent):
            raise NotInteractiveAgentError(
                f"agent {agent_id} 非 interactive 型，不能发起会话（请走 /api/tasks 一次性任务）"
            )
        conn = self.conn_factory()
        try:
            conversation_id = f"conv_{uuid.uuid4().hex}"
            return repos.create_conversation(
                conn, conversation_id=conversation_id, agent_id=agent_id, created_by=created_by
            )
        finally:
            conn.close()

    def get(self, conversation_id: str) -> dict[str, Any]:
        conn = self.conn_factory()
        try:
            conv = repos.get_conversation(conn, conversation_id)
            if conv is None:
                raise ConversationNotFoundError(f"会话不存在：{conversation_id}")
            conv["messages"] = repos.list_messages(conn, conversation_id)
            return conv
        finally:
            conn.close()

    # ── 单轮对话推进 ─────────────────────────────────────────────────────

    def post_message(self, *, conversation_id: str, content: str) -> dict[str, Any]:
        """推进一轮：落用户消息 → 调导引 workflow → 落 assistant 回复(+推荐草案)。

        LLM 上游失败时，`run()` 抛异常原样冒泡（诚实失败，不伪造 assistant 回复）；
        此时用户消息已落库（对话历史如实保留「问过但这轮失败」），可重试。
        """
        conn = self.conn_factory()
        try:
            conv = repos.get_conversation(conn, conversation_id)
            if conv is None:
                raise ConversationNotFoundError(f"会话不存在：{conversation_id}")
            if conv["status"] != "active":
                raise ConversationClosedError(
                    f"会话已 {conv['status']}，不再接受新消息：{conversation_id}"
                )

            agent_id = conv["agent_id"]
            agent = self.agent_registry.get(agent_id)
            if agent is None:
                # 会话存续期间 Agent 被下架/删除——诚实拒绝，不硬跑
                raise ConversationNotFoundError(f"会话所属 agent 已不可用：{agent_id}")
            # 反方 P3-4：会话存续期间 Agent 若被 disabled 或改成非 interactive（重扫
            # registry），不再以 interactive 形态硬跑——诚实拒绝，语义不错位。
            if agent.get("status") == "disabled" or not is_interactive(agent):
                raise ConversationClosedError(
                    f"会话所属 agent {agent_id} 已不可用于对话（已下线或非 interactive）"
                )

            # Codex P2：一轮对话是**事务性**的——先在内存里拼「历史 + 本轮用户消息」
            # 喂给 workflow，只有成功才把 user + assistant 一起落库；失败则一条都不落。
            # 否则「用户消息先落库、workflow 502」会让重试必须重发同一句 → 历史里堆出
            # 重复 user 行，恰在端点声称「可重试」的瞬态失败场景下把历史弄脏。
            history = [
                {"role": m["role"], "content": m["content"]}
                for m in repos.list_messages(conn, conversation_id)
            ]
            history.append({"role": "user", "content": content})

            pkg_dir = self.agent_registry.package_dir(agent_id)
            workflow = _load_workflow_module(agent_id, pkg_dir / "workflow.py")
            context = {
                "messages": history,
                "model_gateway": self.model_gateway,
                "agent_registry": self.agent_registry,
                "agent_config": agent,
            }
            result = workflow.run(context)  # 抛异常即冒泡（不吞）；此前尚未落任何消息

            if not isinstance(result, dict):
                raise ValueError("interactive workflow.run() 返回值必须是 dict")
            assistant_message = result.get("assistant_message")
            if not isinstance(assistant_message, str) or not assistant_message.strip():
                raise ValueError("interactive workflow 未返回非空 assistant_message")
            recommendation = result.get("recommendation")  # 可能为 None

            # 成功：user + assistant 按序原子落库（失败路径永不到达这里）。
            repos.append_message(
                conn, conversation_id=conversation_id, role="user", content=content
            )
            msg = repos.append_message(
                conn,
                conversation_id=conversation_id,
                role="assistant",
                content=assistant_message,
                recommendation=recommendation,
            )
            # 会话级 recommendation 反映**最后一轮**结果（反方 P3-1：含推荐被撤回
            # 的轮——无推荐即写回 None，不留陈旧草案；会话保持 active 供继续细化）。
            repos.set_conversation_recommendation(conn, conversation_id, recommendation)

            return {"message": msg, "conversation": repos.get_conversation(conn, conversation_id)}
        finally:
            conn.close()
