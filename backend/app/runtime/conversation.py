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

import logging
import sqlite3
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from ..core.errors import (
    ConversationClosedError,
    ConversationConflictError,
    ConversationNotFoundError,
    FileNotFoundInStoreError,
    InteractiveToolAdmissionError,
    KnowledgeScopeDeniedError,
    NotInteractiveAgentError,
    ToolNotAllowedError,
)
from ..storage import repos
from .attachments import render_attachment_blocks
from .runtime import _load_workflow_module

logger = logging.getLogger(__name__)

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


class _ConvToolRegistryContext:
    """context["tool_registry"] 的会话变体（T3-a / ADR-0028）：与 job 路径
    runtime._ToolRegistryContext 同款 P1-A default-deny——构造时锁定 agent.yaml.tools
    白名单（frozenset），call() 第一步查白名单：工具即使已在 Tool Registry 注册，
    不在本 Agent 白名单内一律拒绝（新注册工具绝不自动扩大存量 Agent 的权限面）。

    与 job 包装的唯一差异是**审计出口**（安全逻辑逐字节相同）：job 侧经
    repos.append_event(task_id=…) 发 tool_started/finished 事件，但会话无 task_id
    （task_events.task_id NOT NULL、tool_runs 无 conversation_id 列——设计事实，见
    ADR-0028），故不能 verbatim 复用 job 包装；会话逐调用 tool 留痕**降级**走 logger
    （会话逐调用 tool 事件流 = V0.2+ 债）。default-deny 白名单校验与 job 路径同一行
    （DRY option A：复制那 1 行，绝不改 job 包装 _ToolRegistryContext）。

    副作用边界（ADR-0028）：交互工具注入仅对**数据类**（纯读/纯算、无外部副作用）
    工具安全——副作用型工具进交互面须另设 review gate（LLM 可在会话中途驱动调用，
    无逐轮人签闸）。现役工具清单副作用属性核对为 Codex 命中即审具名项；T3-b 用
    tools=[] 规避，注入本身 default-deny。
    """

    def __init__(
        self,
        tool_registry: Any,
        conversation_id: str,
        agent_id: str,
        allowed_tools: frozenset[str],
    ) -> None:
        self._tool_registry = tool_registry
        self._conversation_id = conversation_id
        self._agent_id = agent_id
        self._allowed_tools = allowed_tools

    def call(self, tool_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if tool_id not in self._allowed_tools:
            message = (
                f"工具 {tool_id} 不在 Agent {self._agent_id} 的 agent.yaml.tools 白名单内，"
                "default-deny 拒绝调用"
            )
            logger.warning("会话 %s：%s", self._conversation_id, message)
            raise ToolNotAllowedError(message)
        # 审计降级（ADR-0028 option b）：会话无 task_events 出口，逐调用留痕走 logger；
        # conn 不传 → 不落无归属列的孤儿 tool_runs 行。工具自身 input/output 契约校验、
        # 超时执行仍由 ToolRegistry.call 内部照常完成（未注册工具→ToolNotRegisteredError，
        # backend/app/tools/registry.py:108-109，与 job 路径同一诚实失败出口）。
        # 留痕成对（T3-fix B3-P2-2，Codex C3-P2-2）：before/成功/失败三态各一条——此前只
        # before-log，工具异常无失败留痕（"调了但没结果"在日志里看不出）。fail-closed：失败
        # 留痕后原样冒泡，绝不吞异常降级为绿。
        logger.info(
            "会话 %s（agent=%s）工具 %s 调用开始（V0.2 审计：logger 留痕，无 task_events）",
            self._conversation_id, self._agent_id, tool_id,
        )
        try:
            result = self._tool_registry.call(tool_id, payload)
        except Exception as exc:
            logger.warning(
                "会话 %s（agent=%s）工具 %s 调用失败：%s: %s",
                self._conversation_id, self._agent_id, tool_id, type(exc).__name__, exc,
            )
            raise
        # 留痕成对（T3-fix B3-P2-2 + Codex R1-P2）：工具以 {"status":"failed"} 返回**预期失败**
        # （缺输入文件/契约不满足等）而非 raise——交互路径无 tool_runs 行、审计只靠此 logger，无条件
        # 记「成功」会把失败态当成功记录，令告警/审计失真。镜像 job wrapper 显式 status=='failed' 分支：
        # failed 记 warning（含 error_message），其余记 success。判定 == 显式。
        _status = result.get("status") if isinstance(result, dict) else None
        if _status == "failed":
            logger.warning(
                "会话 %s（agent=%s）工具 %s 返回失败态（status=failed，非异常）：%s",
                self._conversation_id, self._agent_id, tool_id,
                result.get("error_message") if isinstance(result, dict) else None,
            )
        else:
            logger.info(
                "会话 %s（agent=%s）工具 %s 调用成功（status=%s）",
                self._conversation_id, self._agent_id, tool_id, _status,
            )
        return result


class _ConvKnowledgeContext:
    """context["knowledge"] 的会话变体（T3-a / ADR-0028）：agent.yaml
    knowledge.enabled is True 时唯一的会话检索入口，与 job 路径
    runtime._KnowledgeContext 同款 default-deny——scope 不在 agent.yaml
    knowledge.scopes 白名单内一律拒绝（即使该 scope 已在 Scope Registry 注册；
    新注册 scope 绝不自动扩大存量 Agent 的可见面）。KnowledgeService 自身不做
    授权判定（信任边界见 service.py），绕过本层直调无白名单保护。

    审计出口同 _ConvToolRegistryContext：会话无 task_id，逐调用检索留痕降级走
    logger（V0.2+ 债）。default-deny 白名单校验与 job 路径同一行（DRY option A）。
    """

    def __init__(
        self,
        knowledge_service: Any,
        conversation_id: str,
        agent_id: str,
        allowed_scopes: frozenset[str],
    ) -> None:
        self._knowledge_service = knowledge_service
        self._conversation_id = conversation_id
        self._agent_id = agent_id
        self._allowed_scopes = allowed_scopes

    def search(self, scope_id: str, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        if scope_id not in self._allowed_scopes:
            message = (
                f"scope {scope_id} 不在 Agent {self._agent_id} 的 agent.yaml "
                "knowledge.scopes 白名单内，default-deny 拒绝检索"
            )
            logger.warning("会话 %s：%s", self._conversation_id, message)
            raise KnowledgeScopeDeniedError(message)
        # 留痕成对（T3-fix B3-P2-2，Codex C3-P2-2）：此前只 after-success-log，检索异常
        # （scope 源不可用/空语料/空查询等）无失败留痕。包一层结构化 success/failure outcome，
        # 失败留痕后原样冒泡（fail-closed：装配缺陷/空语料冒泡 → ConversationService 诚实失败）。
        try:
            hits = self._knowledge_service.search(scope_id, query, top_k=top_k)
        except Exception as exc:
            logger.warning(
                "会话 %s（agent=%s）知识检索失败（scope=%s）：%s: %s",
                self._conversation_id, self._agent_id, scope_id, type(exc).__name__, exc,
            )
            raise
        logger.info(
            "会话 %s（agent=%s）知识检索完成（scope=%s，命中 %d；V0.2 审计：logger 留痕）",
            self._conversation_id, self._agent_id, scope_id, len(hits),
        )
        # 与 job 路径同款：KnowledgeHit(frozen dataclass) → dict，出处字段
        # （source/fingerprint）随行携带，展示层必须透出（docs/06 §4）。
        return [asdict(h) for h in hits]


class ConversationService:
    def __init__(
        self,
        agent_registry: Any,
        model_gateway: Any,
        conn_factory: Callable[[], sqlite3.Connection],
        *,
        tool_registry: Any,
        uploads_dir: str | Path,
        knowledge_service: Any | None = None,
    ) -> None:
        self.agent_registry = agent_registry
        self.model_gateway = model_gateway
        self.conn_factory = conn_factory
        # T3-a/ADR-0028：内核一次性扩展——交互运行时注入 tool_registry（default-deny
        # 白名单=agent.yaml.tools）+ knowledge（仅 knowledge.enabled is True 时，白名单
        # =agent.yaml.knowledge.scopes），镜像 job 路径 ADR-0015。tool_registry 必传
        # （与 AgentRuntime 对称）；knowledge_service 可为 None（纯 chat/工具型交互 Agent
        # 不需要），但 Agent 声明 knowledge.enabled 而此处 None 时 post_message 诚实失败
        # （镜像 runtime._execute 1b，见 post_message）。
        self.tool_registry = tool_registry
        self.knowledge_service = knowledge_service
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
        """把在窗消息的附件渲染进各自 content（M7）——返回 {role, content, user_text, attachments_block}。

        content=用户原文 + 渲染附件块（拼接版）。**post_message 会把 messages 重投影成纯
        {role, content}** 再进 context——user_text/attachments_block 绝不进 messages（否则
        guide_agent `*messages` splat → gateway 逐字节透传 payload 会外泄多余键，破坏
        test_m7 `set(keys)=={role,content}` 不变量）。二者**分开**携带仅经 post_message 的
        独立 context 键给需要「只中和用户原文、保留 runtime 造的可信 <<ATTACHMENT>> fence」的
        workflow（interactive_doc_qa，T3-fix B3-P2-1 / Codex C3-P2-1）——避免从拼接串里靠脆弱
        串匹配切分（会被用户伪造附件规则行绕过成注入面）。预算 _ATTACHMENT_BUDGET_CHARS 跨整个
        窗口共享、**从最新往旧**分配；存量 content 从不改写（渲染只发生在喂模型的内存副本上）。
        file_ids 键在此剥离——workflow 收到的消息形状与 M6 完全一致，附件对 Agent 透明。
        """
        rendered: list[dict[str, Any]] = []
        remaining = _ATTACHMENT_BUDGET_CHARS
        for msg in reversed(history):
            user_text = msg["content"]
            ids = msg.get("file_ids") or []
            block = ""
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
            content = f"{user_text}\n\n{block}" if block else user_text
            rendered.append({
                "role": msg["role"],
                "content": content,
                "user_text": user_text,
                "attachments_block": block,
            })
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

            # T3-a/ADR-0028（镜像 runtime._execute 1b）：Agent 声明 knowledge.enabled 而
            # ConversationService 未装配 KnowledgeService = 装配缺陷，诚实失败——绝不静默
            # 给一个"查不到任何东西"的假 knowledge 入口。抛在任何落库前（本轮零消息落库，
            # 与 LLM 失败路径同款事务性）。生产装配（main.py）恒传 knowledge_service，本闸
            # 为 fail-closed 兜底。安全 gate 判定 is True/is None，绝不 truthiness。
            if (agent.get("knowledge") or {}).get("enabled") is True and self.knowledge_service is None:
                raise RuntimeError(
                    f"会话所属 agent {agent_id} 声明 knowledge.enabled 但 ConversationService "
                    "未装配 KnowledgeService（装配缺陷，fail-closed 拒绝本轮）"
                )

            # T3-fix B1（★核心安全 fail-closed，Codex C3-P1-2/P1-3；ADR-0028 §6 从「文档声明」
            # 升格为「代码强制」——Codex 逮的正是"ADR 只写文档没在代码强制"）：交互面把「LLM 可在
            # 会话中途、无逐轮人签驱动」的工具收敛到**纯数据类**。交互 Agent 声明的**每个**工具必须
            # 在工具注册表元数据里 interactive_safe is True **且** output_classification == "internal"
            # ——任一不满足（含未注册取不到元数据 / 副作用工具 / sensitive 输出）**落库前** fail-closed
            # 拒本轮（零消息落库、workflow 从未被调、工具零执行），错误点名工具 + 原因。副作用工具
            # （cfd_solve_launch 起 Docker）会被 LLM 无人签触发；sensitive 输出工具（monitor_adapter_recon）
            # 原样落会话消息泄漏（job 路径靠 taint+读时 gate，交互层无此出口）——两者均被此闸拒。
            # 判定用 is True / == 显式，绝不 truthiness（缺省/None/False/"true" 字面均 → 拒）。
            # 安全门统一抛 InteractiveToolAdmissionError（Codex R3-P2 verbatim）：typed FlaiError 令
            # api/conversations.post_message 按「永久性资源配置错」映射 503——此前裸 RuntimeError 逃逸
            # 成 HTTP 500（"服务器 bug"语义掩盖真实配置问题，且未注册工具从不落到 ToolRegistry.call
            # 的 ToolNotRegisteredError 映射路径）。
            for _tool_id in (agent.get("tools") or []):
                _tool_meta = self.tool_registry.get(_tool_id)
                if _tool_meta is None:
                    raise InteractiveToolAdmissionError(
                        f"交互面工具安全门 fail-closed：agent {agent_id} 声明的工具 {_tool_id} "
                        "未在工具注册表登记，无法核对 interactive_safe（交互面只放已登记的纯数据类工具）"
                    )
                if _tool_meta.get("interactive_safe") is not True:
                    raise InteractiveToolAdmissionError(
                        f"交互面工具安全门 fail-closed：agent {agent_id} 声明的工具 {_tool_id} "
                        "未标记 interactive_safe=true（交互面 default-deny，只放纯读/纯算·无外部副作用·"
                        "internal 的数据类工具；副作用/敏感工具进交互面须另设 review gate，ADR-0028 §6）"
                    )
                if _tool_meta.get("output_classification") != "internal":
                    raise InteractiveToolAdmissionError(
                        f"交互面工具安全门 fail-closed：agent {agent_id} 声明的工具 {_tool_id} "
                        f"输出分级 {_tool_meta.get('output_classification')!r} 非 internal"
                        "（sensitive 输出会原样落会话消息泄漏——job 路径靠 taint+读时 gate，交互层无此出口）"
                    )
                # ★跨字段拒（Codex R1-P1-3 shell + R3-P1 verbatim 扩 save_raw_files/require_workspace_
                # isolation）：仅查 interactive_safe + output_classification 会放行 safety 旗标与「交互面
                # 纯数据类」构造上矛盾的工具——三旗标任一显式 True 即拒，不论 interactive_safe 如何标
                # （tool.yaml 误标的纵深防御）：
                #   allow_shell_command=true：LLM 会话中途可无人签触发 shell 执行；
                #   save_raw_files=true：原始文件留痕审计需 DB conn+task 归属——交互 wrapper 调
                #     ToolRegistry 不传 conn（审计降级 logger），声明的留痕义务无从兑现=写盘工具裸跑；
                #   require_workspace_isolation=true：声明需隔离工作区——交互路径无 per-task 隔离
                #     workspace，隔离义务无从兑现。
                # 判定 is True 显式绝不 truthiness（缺省/None/False/"true" 字面均按未声明处理——旗标
                # 本身缺省即 False）。
                _safety = _tool_meta.get("safety") or {}
                for _flag, _why in (
                    ("allow_shell_command",
                     "shell 能力工具绝不得进交互面（即便误标 interactive_safe=true）：LLM 会话中途可"
                     "无人签触发 shell 执行"),
                    ("save_raw_files",
                     "声明原始文件留痕义务的工具不得进交互面：交互 wrapper 调 ToolRegistry 不传 DB "
                     "conn、无 task 归属，留痕审计无从兑现（写盘工具将无审计裸跑）"),
                    ("require_workspace_isolation",
                     "声明需隔离工作区的工具不得进交互面：交互路径无 per-task 隔离 workspace，隔离"
                     "义务无从兑现"),
                ):
                    if _safety.get(_flag) is True:
                        raise InteractiveToolAdmissionError(
                            f"交互面工具安全门 fail-closed：agent {agent_id} 声明的工具 {_tool_id} "
                            f"safety.{_flag}=true——{_why}（ADR-0028 §6）"
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
            rendered = self._render_history_attachments(conn, history)
            # messages 保持纯 {role, content}（test_m7 不外泄内部键：guide_agent `*messages`
            # splat → gateway payload 逐字节透传，多余键会污染上游 chat 请求）——重投影丢弃
            # user_text/attachments_block，仅经**独立 context 键**交给需要分离的 workflow。
            messages = [{"role": m["role"], "content": m["content"]} for m in rendered]
            current = rendered[-1] if rendered else {"user_text": content, "attachments_block": ""}

            pkg_dir = self.agent_registry.package_dir(agent_id)
            workflow = _load_workflow_module(agent_id, pkg_dir / "workflow.py")
            context: dict[str, Any] = {
                "messages": messages,
                "model_gateway": _ConversationGatewayContext(
                    self.model_gateway, conversation_id, agent_id
                ),
                "agent_registry": self.agent_registry,
                "agent_config": agent,
                # T3-a/ADR-0028：交互运行时注入 tool_registry（default-deny 白名单=
                # agent.yaml.tools；未声明工具即空白名单，call 一律 ToolNotAllowedError）。
                # 镜像 job 路径 runtime._build_context——无条件注入（工具是纯读/纯算数据类，
                # 副作用边界见 ADR-0028）；不读它的交互 Agent（如 guide_agent）零行为变化。
                "tool_registry": _ConvToolRegistryContext(
                    self.tool_registry, conversation_id, agent_id,
                    frozenset(agent.get("tools") or []),
                ),
                # T3-fix B3-P2-1（Codex C3-P2-1）：当前轮（末条=本轮 user）用户原文与 runtime
                # 渲染的可信附件块**分离**传——workflow 只中和用户原文（防伪造 <<KNOWLEDGE>> fence），
                # 可信附件块（正文已中和、fence 受信）原样保留，不二次中和毁 <<ATTACHMENT>> 定界符。
                # 不读它的 workflow（guide_agent 用拼接版 messages content）零行为变化。
                "current_user_text": current["user_text"],
                "current_attachments_block": current["attachments_block"],
                # T3-fix R1（Codex R1-P1 多轮 replay 中和）：prior 轮用户原文（ConversationService
                # 持久化的原始 content）在 messages 里已被 _render_history_attachments 拼进渲染附件块，
                # 但**用户原文部分未中和**——workflow 若原样 extend(prior_turns) 会让首轮伪造的
                # <<KNOWLEDGE>>/<<ATTACHMENT>> 块第二轮起裸露冒充语料/附件（首轮只中和当前 user）。故把
                # 全轮**分离结构**（每轮 user_text/attachments_block 分开）也经独立 context 键传入，供
                # workflow 逐 prior user 轮只中和原文、保留 runtime 造的可信 <<ATTACHMENT>> fence。投影
                # 掉 content（不入 messages/gateway，避免 test_m7 多余键）；不读它的 workflow 零影响。
                "history_separated": [
                    {"role": m["role"], "user_text": m["user_text"],
                     "attachments_block": m["attachments_block"]}
                    for m in rendered
                ],
            }
            # ADR-0015/ADR-0028：knowledge 键仅在 enabled is True 时存在（default-deny 于
            # 注入门：未声明的 Agent 连入口都拿不到、访问即 KeyError，而不是拿到一个"空"入口
            # ——镜像 job 路径 runtime._build_context:908）。服务未装配已在上方 fail-closed。
            if (agent.get("knowledge") or {}).get("enabled") is True:
                context["knowledge"] = _ConvKnowledgeContext(
                    self.knowledge_service, conversation_id, agent_id,
                    frozenset((agent.get("knowledge") or {}).get("scopes") or []),
                )
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
