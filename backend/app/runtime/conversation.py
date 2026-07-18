"""ConversationService：interactive 型 Agent 的会话运行时（M6，ADR-0012/0013）。

与 JobRunner 对称——JobRunner 驱动 job 模型的一次性任务，ConversationService
驱动 interactive 模型的多轮会话。轻内核纪律：无 Redis/Celery，纯 SQLite 两表
（conversations / conversation_messages）+ 同步请求-响应（对话本就是同步交互，
不需后台轮询）。

职责边界（只做通用会话编排，不含任何导引业务逻辑）：
- 维护会话生命周期与消息持久化（active → concluded/abandoned，终态不可再收消息）；
- 逐轮把会话历史（截窗后）转发到 Agent 包的 `run(context)`；
- 落回 assistant 回复与其可能携带的推荐（预填任务草案）快照。

并发与一致性（ADR-0013，审计修复）：
- 单轮落库是**一个 BEGIN IMMEDIATE 事务**（user+assistant+推荐快照原子提交）；
- **乐观并发检查**：workflow（含 LLM 调用，秒级）刻意放在事务外——绝不持锁等
  模型；提交前重查「会话仍 active 且消息数未变」，被并发轮抢先则整轮回滚抛
  ConversationConflictError（409 可重试），绝不把基于过期历史的回复写进历史。

导引「如何组织追问、如何结构化并校验推荐」全在其 workflow.py（插件模型，
宪法：Agent=插件）。ConversationService 绝不解析对话内容、绝不据 LLM 输出下
结论、更绝不代替人创建/签发下游任务——推荐只是草案，人在 tasks 端点签发。
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any, Callable

from ..core.errors import (
    ClearanceDeniedError,
    ConversationClosedError,
    ConversationConflictError,
    ConversationNotFoundError,
    FileNotFoundInStoreError,
    NotInteractiveAgentError,
)
from ..storage import repos
from .attachments import render_attachment_blocks
from .runtime import _load_workflow_module

# 发给模型的历史窗口上限（条数 + 累计字符双限）：全量历史仍完整落库，只是
# 超窗后模型只看最近一段——防止长会话 token 成本单调上涨直至超上下文
# （审计 P2；V0.2 若需要「超窗摘要」再演进，V0.1 先诚实截窗）。
_HISTORY_MAX_MESSAGES = 40
_HISTORY_MAX_CHARS = 60_000
# 附件渲染总预算（M7/ADR-0014）：叠加在上面窗口之外、跨整个在窗历史共享，
# **从最新消息往旧分配**——新附件优先拿满，旧附件预算耗尽即退化为占位行
# （与截窗同哲学：诚实降级）。单消息附件数上限（防御纵深，API 层同限）。
_ATTACHMENT_BUDGET_CHARS = 24_000
_MAX_FILES_PER_MESSAGE = 5


def is_interactive(agent: dict[str, Any]) -> bool:
    """agent.yaml.workflow.mode == 'interactive'（ADR-0012 唯一判据）。"""
    return (agent.get("workflow", {}) or {}).get("mode") == "interactive"


def _window(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """取「最近 N 条且累计字符不超预算」的历史尾窗（保持时序，至少含最后一条）。"""
    tail: list[dict[str, Any]] = []
    chars = 0
    for m in reversed(messages[-_HISTORY_MAX_MESSAGES:]):
        chars += len(m.get("content") or "")
        if tail and chars > _HISTORY_MAX_CHARS:
            break
        tail.append(m)
    tail.reverse()
    return tail


class _ConversationGatewayContext:
    """会话侧的 Model Gateway 包装：自动注入 conversation_id/agent_id。

    与 job 路径的 _ModelGatewayContext 对称（那边注入 task_id/agent_id + 发事件）：
    workflow 只管 `model_gateway.chat(profile, messages)`，身份归因是运行时的事，
    不让 Agent 手工传（ADR-0013：会话模型调用必须可归因，Q5 追溯）。
    会话无任务事件流，留痕落 model_calls 表（含 conversation_id）。
    """

    def __init__(self, model_gateway: Any, conversation_id: str, agent_id: str) -> None:
        self._model_gateway = model_gateway
        self._conversation_id = conversation_id
        self._agent_id = agent_id

    # 归因键由 wrapper 钉死，workflow 不得经 kwargs 透传/覆写（与 job 侧
    # _ModelGatewayContext._sanitize 对称，兑现 task/conversation XOR，Codex R0 P1-5/R1）：
    # 尤其 task_id——会话模型调用只归因 conversation，若 workflow 塞 task_id 会造「同时带
    # conversation_id + task_id」双归因行。此前 setdefault 只在缺省时注入，workflow 传入的
    # task_id/覆写会漏过——改为**先剔除三归因键再权威注入**，杜绝任一方向的双归因。
    _FORBIDDEN_ATTR_KWARGS = ("task_id", "conversation_id", "agent_id")

    def _ids(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        safe = {k: v for k, v in kwargs.items() if k not in self._FORBIDDEN_ATTR_KWARGS}
        safe["conversation_id"] = self._conversation_id
        safe["agent_id"] = self._agent_id
        return safe

    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        return self._model_gateway.chat(profile, messages, **self._ids(kwargs))

    def embed(self, profile: str, text: str, **kwargs: Any) -> dict[str, Any]:
        return self._model_gateway.embed(profile, text, **self._ids(kwargs))

    def vision(self, profile: str, image_path: str, prompt: str, **kwargs: Any) -> dict[str, Any]:
        return self._model_gateway.vision(profile, image_path, prompt, **self._ids(kwargs))


class ConversationService:
    def __init__(
        self,
        agent_registry: Any,
        model_gateway: Any,
        conn_factory: Callable[[], sqlite3.Connection],
        *,
        uploads_dir: str | Path,
    ) -> None:
        self.agent_registry = agent_registry
        self.model_gateway = model_gateway
        self.conn_factory = conn_factory
        self.uploads_dir = Path(uploads_dir)

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
            messages = repos.list_messages(conn, conversation_id)
            # M7：给带附件的消息补元数据（文件名/大小），前端气泡直接可显——
            # 文件行已被清理的 id 如实给占位名，不隐藏「曾传过附件」的事实。
            all_ids = [fid for m in messages for fid in (m.get("file_ids") or [])]
            if all_ids:
                by_id = {r["id"]: r for r in repos.list_files_by_ids(conn, all_ids)}
                for m in messages:
                    ids = m.get("file_ids") or []
                    if ids:
                        m["attachments"] = [
                            {
                                "id": fid,
                                "filename": by_id[fid]["filename"] if fid in by_id else f"(已不存在 {fid})",
                                "size_bytes": by_id[fid]["size_bytes"] if fid in by_id else None,
                            }
                            for fid in ids
                        ]
            conv["messages"] = messages
            return conv
        finally:
            conn.close()

    def conclude(self, conversation_id: str) -> dict[str, Any]:
        """人工结束会话：active → concluded（唯一合法转出，BEGIN IMMEDIATE 防并发双转）。

        「确认草案去创建任务」时前端调用本动作归档会话；已终态的会话如实 409，
        不做幂等吞掉——重复 conclude 说明调用方状态观有误，应当被看见。
        """
        conn = self.conn_factory()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conv = repos.get_conversation(conn, conversation_id)
                if conv is None:
                    raise ConversationNotFoundError(f"会话不存在：{conversation_id}")
                if conv["status"] != "active":
                    raise ConversationClosedError(
                        f"会话已 {conv['status']}，无法再次结束：{conversation_id}"
                    )
                result = repos.set_conversation_status(conn, conversation_id, "concluded")
                conn.execute("COMMIT")
                return result
            except Exception:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()

    # ── 单轮对话推进 ─────────────────────────────────────────────────────

    def _render_history_attachments(
        self, conn: Any, history: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """把在窗消息的附件渲染进各自 content（M7）——返回纯 {role, content} 列表。

        预算 _ATTACHMENT_BUDGET_CHARS 跨整个窗口共享、**从最新往旧**分配；
        存量 content 从不改写（渲染只发生在喂模型的内存副本上）。file_ids 键
        在此剥离——workflow 收到的消息形状与 M6 完全一致，附件对 Agent 透明。
        """
        rendered: list[dict[str, Any]] = []
        remaining = _ATTACHMENT_BUDGET_CHARS
        for msg in reversed(history):
            body = msg["content"]
            ids = msg.get("file_ids") or []
            if ids:
                # 历史消息的文件可能已被清理——缺位的补显式占位行（保持入参顺序），
                # 由渲染器「读取失败」路径兜底，绝不静默当作没传过。
                by_id = {r["id"]: r for r in repos.list_files_by_ids(conn, ids)}
                rows = [
                    by_id.get(fid, {"id": fid, "filename": f"(已不存在 {fid})", "path": ""})
                    for fid in ids
                ]
                block = render_attachment_blocks(
                    rows,
                    budget_chars=max(0, remaining),
                    uploads_root=self.uploads_dir,
                )
                remaining -= len(block)
                body = f"{body}\n\n{block}" if block else body
            rendered.append({"role": msg["role"], "content": body})
        rendered.reverse()
        return rendered

    def post_message(
        self, *, conversation_id: str, content: str, file_ids: list[str] | None = None
    ) -> dict[str, Any]:
        """推进一轮：读历史（不落库）→ 调导引 workflow → 单事务原子落库。

        LLM 上游失败时 `run()` 抛异常原样冒泡（诚实失败，不伪造 assistant 回复），
        此时**零消息落库**——重试同一句不会堆出重复 user 行（幂等重试，Codex P2）。
        file_ids（M7 附件）：先校验存在性（缺文件在任何落库/LLM 调用前诚实失败），
        入库存 id 列表；附件**内容**只进模型上下文（窗口内按预算渲染），不进消息文本。
        """
        # 上限检查在**去重前**（M7 敌意审 P2）：pydantic max_length 查的也是去重前
        # 原始列表，若这里查去重后长度，HTTP 入口下运行时层因去重只减不增而永不
        # 触发——成死代码。查去重前即让「非 HTTP 直调 ConversationService」也受
        # 同一上限约束，纵深名副其实。
        raw_file_ids = file_ids or []
        if len(raw_file_ids) > _MAX_FILES_PER_MESSAGE:
            raise ValueError(f"单条消息附件数上限 {_MAX_FILES_PER_MESSAGE}，实收 {len(raw_file_ids)}")
        file_ids = list(dict.fromkeys(raw_file_ids))  # 去重保序
        conn = self.conn_factory()
        try:
            conv = repos.get_conversation(conn, conversation_id)
            if conv is None:
                raise ConversationNotFoundError(f"会话不存在：{conversation_id}")
            if conv["status"] != "active":
                raise ConversationClosedError(
                    f"会话已 {conv['status']}，不再接受新消息：{conversation_id}"
                )
            if file_ids:
                found = {f["id"] for f in repos.list_files_by_ids(conn, file_ids)}
                missing = [fid for fid in file_ids if fid not in found]
                if missing:
                    raise FileNotFoundInStoreError(
                        f"附件不存在（请先经 /api/files/upload 上传）：{missing}"
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

            # 事务性单轮（Codex P2 / ADR-0013）：内存拼「历史 + 本轮 user」喂 workflow，
            # 成功后才进事务落库。baseline 计数供提交前乐观并发检查。
            persisted = repos.list_messages(conn, conversation_id)
            baseline_count = len(persisted)
            history = [
                {"role": m["role"], "content": m["content"], "file_ids": m.get("file_ids") or []}
                for m in persisted
            ]
            history.append({"role": "user", "content": content, "file_ids": file_ids})
            history = _window(history)
            # 批七 Codex R2 P1（verbatim）：交互附件同受 ADR-0030 密级 gate——此前
            # 仅任务路径强制，internal 上限的交互 Agent（policy_qa/standards_qa）可被
            # 喂 sensitive 附件直进模型上下文。渲染前对**在窗全部附件**（本轮新提交
            # + 历史在窗）复核 Agent 密级上限；已被清理的缺位文件只渲占位行、无内容
            # 可越级，不参与判定（与 runtime 消费点复核同口径：只判在册记录，缺位
            # 交由渲染器「读取失败」路径诚实兜底）。局部 import 避免 api↔runtime
            # 模块环（runtime.py 消费点同款）。
            from ..api import classification_gate as cgate

            _window_ids = [fid for m in history for fid in (m.get("file_ids") or [])]
            if _window_ids:
                _present = {r["id"] for r in repos.list_files_by_ids(conn, _window_ids)}
                _present_ids = [fid for fid in _window_ids if fid in _present]
                _allowed, _material_level, _agent_max = cgate.agent_clearance_allows(
                    conn, agent, _present_ids
                )
                if _allowed is False:
                    raise ClearanceDeniedError(
                        f"该专家的密级准入上限为「{_agent_max}」，无法处理「{_material_level}」"
                        "级附件——请改派密级上限足够的 Agent 或移除受控附件（ADR-0030）"
                    )
            history = self._render_history_attachments(conn, history)

            pkg_dir = self.agent_registry.package_dir(agent_id)
            workflow = _load_workflow_module(agent_id, pkg_dir / "workflow.py")
            context = {
                "messages": history,
                "model_gateway": _ConversationGatewayContext(
                    self.model_gateway, conversation_id, agent_id
                ),
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

            # 成功：单事务原子落库（user + assistant + 会话级推荐快照），提交前
            # 复查「仍 active 且历史未被并发轮改动」——检查失败整轮回滚，绝不把
            # 基于过期历史的回复交错写进历史（审计 P2：会话路径此前完全无序列化）。
            conn.execute("BEGIN IMMEDIATE")
            try:
                current = repos.get_conversation(conn, conversation_id)
                if current is None or current["status"] != "active":
                    raise ConversationClosedError(
                        f"会话在本轮生成期间已结束（{None if current is None else current['status']}），本轮不落库"
                    )
                if repos.count_messages(conn, conversation_id) != baseline_count:
                    raise ConversationConflictError(
                        "会话在本轮生成期间被并发消息修改，本轮不落库——请基于最新历史重试"
                    )
                repos.append_message(
                    conn,
                    conversation_id=conversation_id,
                    role="user",
                    content=content,
                    file_ids=file_ids,
                )
                msg = repos.append_message(
                    conn,
                    conversation_id=conversation_id,
                    role="assistant",
                    content=assistant_message,
                    recommendation=recommendation,
                )
                # 会话级 recommendation 反映**最后一轮**结果（反方 P3-1：含推荐被
                # 撤回的轮——无推荐即写回 None，不留陈旧草案）。
                repos.set_conversation_recommendation(conn, conversation_id, recommendation)
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

            return {"message": msg, "conversation": repos.get_conversation(conn, conversation_id)}
        finally:
            conn.close()
