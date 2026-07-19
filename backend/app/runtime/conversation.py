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
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from ..core.errors import (
    ClearanceDeniedError,
    ConversationClosedError,
    ConversationConflictError,
    ConversationNotFoundError,
    ConversationAnswerInvalidError,
    ConversationQuestionConflictError,
    ConversationQuestionNotFoundError,
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
_QUESTION_TTL = timedelta(hours=24)
_MAX_QUESTION_TEXT = 4_000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _expiry_from(created_at: str) -> str:
    return (datetime.fromisoformat(created_at) + _QUESTION_TTL).isoformat()


def _normalize_question_spec(value: Any) -> dict[str, Any] | None:
    """纵深复核 interactive workflow 的 Question 提议。"""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {
        "kind", "prompt", "description", "options"
    }:
        raise ValueError("interactive workflow 返回了非法 Question 字段")
    kind = value.get("kind")
    prompt = value.get("prompt")
    description = value.get("description")
    options = value.get("options")
    if kind not in ("single_choice", "free_text"):
        raise ValueError("interactive workflow 返回了未知 Question kind")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 500:
        raise ValueError("interactive workflow 返回了非法 Question prompt")
    if description is not None and (
        not isinstance(description, str)
        or not description.strip()
        or len(description) > 1_000
    ):
        raise ValueError("interactive workflow 返回了非法 Question description")
    if not isinstance(options, list):
        raise ValueError("interactive workflow 返回了非法 Question options")
    if kind == "free_text" and options:
        raise ValueError("free_text Question 不得携带 options")
    if kind == "single_choice" and not (2 <= len(options) <= 6):
        raise ValueError("single_choice Question 选项数必须为 2..6")

    normalized_options: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    for index, option in enumerate(options, start=1):
        if not isinstance(option, dict) or set(option) != {"id", "label", "description"}:
            raise ValueError("interactive workflow 返回了非法 Question option 字段")
        expected_id = f"option_{index}"
        label = option.get("label")
        option_description = option.get("description")
        if option.get("id") != expected_id:
            raise ValueError("Question option id 必须由平台按顺序生成")
        if not isinstance(label, str) or not label.strip() or len(label) > 200:
            raise ValueError("Question option label 非法")
        folded = label.strip().casefold()
        if folded in seen_labels:
            raise ValueError("Question option label 重复")
        if option_description is not None and (
            not isinstance(option_description, str)
            or not option_description.strip()
            or len(option_description) > 500
        ):
            raise ValueError("Question option description 非法")
        seen_labels.add(folded)
        normalized_options.append({
            "id": expected_id,
            "label": label.strip(),
            "description": option_description.strip()
            if isinstance(option_description, str)
            else None,
        })
    return {
        "kind": kind,
        "prompt": prompt.strip(),
        "description": description.strip() if isinstance(description, str) else None,
        "options": normalized_options,
    }


def _validate_answer_payload(
    question: Mapping[str, Any], payload: Mapping[str, Any]
) -> dict[str, str]:
    """按冻结 Question 精确验证 Answer；不依赖 SQLite JSON1。"""
    kind = payload.get("kind")
    if kind == "option":
        if question.get("kind") != "single_choice":
            raise ConversationAnswerInvalidError("自由文本问题不接受选项回答")
        option_id = payload.get("option_id")
        if not isinstance(option_id, str) or not any(
            isinstance(option, dict) and option.get("id") == option_id
            for option in (question.get("options") or [])
        ):
            raise ConversationAnswerInvalidError("回答选项不在该问题冻结选项中")
        return {"kind": "option", "option_id": option_id}
    if kind == "text":
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ConversationAnswerInvalidError("回答文本不得为空")
        text = text.strip()
        if len(text) > _MAX_QUESTION_TEXT:
            raise ConversationAnswerInvalidError(
                f"回答文本不得超过 {_MAX_QUESTION_TEXT} 字"
            )
        return {"kind": "text", "text": text}
    raise ConversationAnswerInvalidError("未知的回答类型")


def _answer_history_text(
    question: Mapping[str, Any], payload: Mapping[str, str]
) -> str:
    """写入对话史的 canonical 用户事实，choice 使用冻结 label 而不是裸 id。"""
    if payload["kind"] == "option":
        option_id = payload["option_id"]
        label = next(
            option["label"]
            for option in question.get("options") or []
            if option.get("id") == option_id
        )
        answer_text = label
    else:
        answer_text = payload["text"]
    return f"回答「{question['prompt']}」：{answer_text}"


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


def _principal_username(principal: Mapping[str, Any]) -> str:
    """取认证 principal 的 exact username；畸形 principal fail-closed。

    HTTP 中间件保证正常请求一定带该字段。本层仍自守门，防内部调用者绕过 API
    只按 conversation_id 取会话。缺失身份统一按“会话不可见”处理，不泄漏存在性。
    """
    username = principal.get("username")
    if not isinstance(username, str) or not username:
        raise ConversationNotFoundError("会话不存在或不属于当前用户")
    return username


def _principal_display_name(principal: Mapping[str, Any]) -> str:
    display_name = principal.get("display_name")
    if not isinstance(display_name, str) or not display_name:
        raise ValueError("认证 principal 缺少 display_name")
    return display_name


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

    def create(
        self, *, agent_id: str, principal: Mapping[str, Any]
    ) -> dict[str, Any]:
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
                conn,
                conversation_id=conversation_id,
                agent_id=agent_id,
                created_by=_principal_display_name(principal),
                created_by_username=_principal_username(principal),
            )
        finally:
            conn.close()

    def get(
        self, conversation_id: str, *, principal: Mapping[str, Any]
    ) -> dict[str, Any]:
        conn = self.conn_factory()
        try:
            conv = repos.get_conversation_for_owner(
                conn, conversation_id, _principal_username(principal)
            )
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
            # P2.3：Question 是 assistant message 的显式结构附件，按稳定
            # prompt_message_id 归位；绝不从正文问号或 recommendation=None 猜测。
            questions = repos.list_questions(
                conn, conversation_id, now=_now_iso()
            )
            question_by_prompt = {
                question["prompt_message_id"]: question for question in questions
            }
            for message in messages:
                question = question_by_prompt.get(message.get("message_id"))
                if question is not None:
                    message["question"] = question
            conv["messages"] = messages
            return conv
        finally:
            conn.close()

    def conclude(
        self, conversation_id: str, *, principal: Mapping[str, Any]
    ) -> dict[str, Any]:
        """人工结束会话：active → concluded（唯一合法转出，BEGIN IMMEDIATE 防并发双转）。

        「确认草案去创建任务」时前端调用本动作归档会话；已终态的会话如实 409，
        不做幂等吞掉——重复 conclude 说明调用方状态观有误，应当被看见。
        """
        conn = self.conn_factory()
        try:
            principal_username = _principal_username(principal)
            conn.execute("BEGIN IMMEDIATE")
            try:
                conv = repos.get_conversation_for_owner(
                    conn, conversation_id, principal_username
                )
                if conv is None:
                    raise ConversationNotFoundError(f"会话不存在：{conversation_id}")
                if conv["status"] != "active":
                    raise ConversationClosedError(
                        f"会话已 {conv['status']}，无法再次结束：{conversation_id}"
                    )
                repos.close_unresolved_questions(
                    conn,
                    conversation_id,
                    principal_username,
                    now=_now_iso(),
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

    def _answer_replay_response(
        self,
        conn: sqlite3.Connection,
        conversation_id: str,
        question: dict[str, Any],
    ) -> dict[str, Any]:
        """由已落库 answer 的稳定 message ids 重建幂等响应，不再调用模型/写库。"""
        answer = question.get("answer") or {}
        answer_message = repos.get_message_by_public_id(
            conn, conversation_id, answer.get("answer_message_id")
        )
        response_message = repos.get_message_by_public_id(
            conn, conversation_id, answer.get("response_message_id")
        )
        if answer_message is None or response_message is None:
            raise ConversationQuestionConflictError(
                "问题回答记录不完整，已停止重放并等待人工核查"
            )
        for candidate in repos.list_questions(conn, conversation_id, now=_now_iso()):
            if candidate["prompt_message_id"] == response_message["message_id"]:
                response_message["question"] = candidate
                break
        return {
            "answer_message": answer_message,
            "message": response_message,
            "question": question,
            "conversation": repos.get_conversation(conn, conversation_id),
            "replayed": True,
        }

    def post_message(
        self,
        *,
        conversation_id: str,
        content: str,
        principal: Mapping[str, Any],
        file_ids: list[str] | None = None,
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
            principal_username = _principal_username(principal)
            conv = repos.get_conversation_for_owner(
                conn, conversation_id, principal_username
            )
            if conv is None:
                raise ConversationNotFoundError(f"会话不存在：{conversation_id}")
            if conv["status"] != "active":
                raise ConversationClosedError(
                    f"会话已 {conv['status']}，不再接受新消息：{conversation_id}"
                )
            unresolved = repos.get_unresolved_question(
                conn, conversation_id, principal_username, now=_now_iso()
            )
            if unresolved is not None and unresolved["status"] == "pending":
                raise ConversationQuestionConflictError(
                    "当前结构化问题仍待回答；请通过专用回答入口提交，不能用普通消息绕过"
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
            question_spec = _normalize_question_spec(result.get("question"))
            if question_spec is not None and recommendation is not None:
                raise ValueError("interactive workflow 不得在同一轮同时返回 Question 与计划")

            # 成功：单事务原子落库（user + assistant + 会话级推荐快照），提交前
            # 复查「仍 active 且历史未被并发轮改动」——检查失败整轮回滚，绝不把
            # 基于过期历史的回复交错写进历史（审计 P2：会话路径此前完全无序列化）。
            conn.execute("BEGIN IMMEDIATE")
            try:
                current = repos.get_conversation_for_owner(
                    conn, conversation_id, principal_username
                )
                if current is None:
                    raise ConversationNotFoundError(f"会话不存在：{conversation_id}")
                if current["status"] != "active":
                    raise ConversationClosedError(
                        f"会话在本轮生成期间已结束（{current['status']}），本轮不落库"
                    )
                if repos.count_messages(conn, conversation_id) != baseline_count:
                    raise ConversationConflictError(
                        "会话在本轮生成期间被并发消息修改，本轮不落库——请基于最新历史重试"
                    )
                commit_at = _now_iso()
                unresolved = repos.get_unresolved_question(
                    conn, conversation_id, principal_username, now=commit_at
                )
                if unresolved is not None and unresolved["status"] == "pending":
                    raise ConversationQuestionConflictError(
                        "当前结构化问题在本轮生成期间出现，本轮不落库——请先回答该问题"
                    )
                repos.close_unresolved_questions(
                    conn,
                    conversation_id,
                    principal_username,
                    now=commit_at,
                )
                user_msg = repos.append_message(
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
                if question_spec is not None:
                    question = repos.create_question(
                        conn,
                        question_id=f"q_{uuid.uuid4().hex}",
                        conversation_id=conversation_id,
                        prompt_message_id=msg["message_id"],
                        asked_to_username=principal_username,
                        question_spec=question_spec,
                        created_at=commit_at,
                        expires_at=_expiry_from(commit_at),
                    )
                    msg["question"] = question
                # 会话级 recommendation 反映**最后一轮**结果（反方 P3-1：含推荐被
                # 撤回的轮——无推荐即写回 None，不留陈旧草案）。
                repos.set_conversation_recommendation(conn, conversation_id, recommendation)
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

            return {
                "user_message": user_msg,
                "message": msg,
                "conversation": repos.get_conversation(conn, conversation_id),
            }
        finally:
            conn.close()

    def answer_question(
        self,
        *,
        conversation_id: str,
        question_id: str,
        question_revision: int,
        submission_id: str,
        payload: Mapping[str, Any],
        principal: Mapping[str, Any],
    ) -> dict[str, Any]:
        """回答冻结 Question 并继续一轮对话；回答、两条消息及下一 Question 原子提交。"""
        conn = self.conn_factory()
        try:
            username = _principal_username(principal)
            conv = repos.get_conversation_for_owner(conn, conversation_id, username)
            if conv is None:
                raise ConversationNotFoundError(f"会话不存在：{conversation_id}")
            if conv["status"] != "active":
                raise ConversationQuestionConflictError(
                    f"会话已 {conv['status']}，不能再回答结构化问题"
                )
            question = repos.get_question(
                conn,
                question_id,
                conversation_id=conversation_id,
                asked_to_username=username,
                now=_now_iso(),
            )
            if question is None:
                raise ConversationQuestionNotFoundError(
                    f"结构化问题不存在：{question_id}"
                )
            if question_revision != question["revision"]:
                raise ConversationAnswerInvalidError("问题版本与冻结版本不一致")
            normalized_payload = _validate_answer_payload(question, payload)
            if question["status"] == "answered":
                answer = question.get("answer") or {}
                if (
                    answer.get("submission_id") == submission_id
                    and answer.get("payload") == normalized_payload
                ):
                    return self._answer_replay_response(conn, conversation_id, question)
                raise ConversationQuestionConflictError("这个问题已经回答，不能重复提交")
            if question["status"] != "pending":
                raise ConversationQuestionConflictError(
                    f"这个问题已 {question['status']}，不能提交回答"
                )

            answer_content = _answer_history_text(question, normalized_payload)
            agent_id = conv["agent_id"]
            agent = self.agent_registry.get(agent_id)
            if agent is None:
                raise ConversationNotFoundError(f"会话所属 agent 已不可用：{agent_id}")
            if agent.get("status") == "disabled" or not is_interactive(agent):
                raise ConversationClosedError(
                    f"会话所属 agent {agent_id} 已不可用于对话（已下线或非 interactive）"
                )

            persisted = repos.list_messages(conn, conversation_id)
            baseline_count = len(persisted)
            history = [
                {
                    "role": message["role"],
                    "content": message["content"],
                    "file_ids": message.get("file_ids") or [],
                }
                for message in persisted
            ]
            history.append({"role": "user", "content": answer_content, "file_ids": []})
            history = _window(history)

            # 回答轮会重放历史附件，必须与普通消息路径使用同一密级门。
            from ..api import classification_gate as cgate

            window_file_ids = [
                file_id
                for message in history
                for file_id in (message.get("file_ids") or [])
            ]
            if window_file_ids:
                present = {
                    row["id"] for row in repos.list_files_by_ids(conn, window_file_ids)
                }
                present_ids = [file_id for file_id in window_file_ids if file_id in present]
                allowed, material_level, agent_max = cgate.agent_clearance_allows(
                    conn, agent, present_ids
                )
                if allowed is False:
                    raise ClearanceDeniedError(
                        f"该专家的密级准入上限为「{agent_max}」，无法处理「{material_level}」"
                        "级附件——请改派密级上限足够的 Agent 或移除受控附件（ADR-0030）"
                    )
            history = self._render_history_attachments(conn, history)

            package_dir = self.agent_registry.package_dir(agent_id)
            workflow = _load_workflow_module(agent_id, package_dir / "workflow.py")
            result = workflow.run({
                "messages": history,
                "model_gateway": _ConversationGatewayContext(
                    self.model_gateway, conversation_id, agent_id
                ),
                "agent_registry": self.agent_registry,
                "agent_config": agent,
            })
            if not isinstance(result, dict):
                raise ValueError("interactive workflow.run() 返回值必须是 dict")
            assistant_message = result.get("assistant_message")
            if not isinstance(assistant_message, str) or not assistant_message.strip():
                raise ValueError("interactive workflow 未返回非空 assistant_message")
            recommendation = result.get("recommendation")
            next_question_spec = _normalize_question_spec(result.get("question"))
            if next_question_spec is not None and recommendation is not None:
                raise ValueError("interactive workflow 不得在同一轮同时返回 Question 与计划")

            return self._commit_question_answer(
                conn=conn,
                conversation_id=conversation_id,
                question_id=question_id,
                username=username,
                submission_id=submission_id,
                normalized_payload=normalized_payload,
                answer_content=answer_content,
                assistant_message=assistant_message.strip(),
                recommendation=recommendation,
                next_question_spec=next_question_spec,
                baseline_count=baseline_count,
            )
        finally:
            conn.close()

    def _commit_question_answer(
        self,
        *,
        conn: sqlite3.Connection,
        conversation_id: str,
        question_id: str,
        username: str,
        submission_id: str,
        normalized_payload: dict[str, str],
        answer_content: str,
        assistant_message: str,
        recommendation: dict[str, Any] | None,
        next_question_spec: dict[str, Any] | None,
        baseline_count: int,
    ) -> dict[str, Any]:
        conn.execute("BEGIN IMMEDIATE")
        try:
            current_conv = repos.get_conversation_for_owner(
                conn, conversation_id, username
            )
            if current_conv is None:
                raise ConversationNotFoundError(f"会话不存在：{conversation_id}")
            if current_conv["status"] != "active":
                raise ConversationQuestionConflictError(
                    f"会话在回答生成期间已 {current_conv['status']}，本轮不落库"
                )
            committed_at = _now_iso()
            current_question = repos.get_question(
                conn,
                question_id,
                conversation_id=conversation_id,
                asked_to_username=username,
                now=committed_at,
            )
            if current_question is None:
                raise ConversationQuestionNotFoundError(
                    f"结构化问题不存在：{question_id}"
                )
            if current_question["status"] == "answered":
                answer = current_question.get("answer") or {}
                if (
                    answer.get("submission_id") == submission_id
                    and answer.get("payload") == normalized_payload
                ):
                    conn.execute("ROLLBACK")
                    return self._answer_replay_response(
                        conn, conversation_id, current_question
                    )
                raise ConversationQuestionConflictError(
                    "这个问题已被另一提交回答，本轮不落库"
                )
            if current_question["status"] != "pending":
                raise ConversationQuestionConflictError(
                    f"这个问题在回答生成期间已 {current_question['status']}，本轮不落库"
                )
            if repos.count_messages(conn, conversation_id) != baseline_count:
                raise ConversationQuestionConflictError(
                    "会话在回答生成期间被并发消息修改，本轮不落库"
                )

            answer_message = repos.append_message(
                conn,
                conversation_id=conversation_id,
                role="user",
                content=answer_content,
            )
            response_message = repos.append_message(
                conn,
                conversation_id=conversation_id,
                role="assistant",
                content=assistant_message,
                recommendation=recommendation,
            )
            answered_question = repos.resolve_question(
                conn,
                question_id=question_id,
                conversation_id=conversation_id,
                asked_to_username=username,
                submission_id=submission_id,
                answer=normalized_payload,
                answered_at=committed_at,
                answer_message_id=answer_message["message_id"],
                response_message_id=response_message["message_id"],
            )
            if answered_question is None:
                raise ConversationQuestionConflictError(
                    "问题回答 CAS 未命中，本轮不落库"
                )
            if next_question_spec is not None:
                next_question = repos.create_question(
                    conn,
                    question_id=f"q_{uuid.uuid4().hex}",
                    conversation_id=conversation_id,
                    prompt_message_id=response_message["message_id"],
                    asked_to_username=username,
                    question_spec=next_question_spec,
                    created_at=committed_at,
                    expires_at=_expiry_from(committed_at),
                )
                response_message["question"] = next_question
            repos.set_conversation_recommendation(
                conn, conversation_id, recommendation
            )
            conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        return {
            "answer_message": answer_message,
            "message": response_message,
            "question": answered_question,
            "conversation": repos.get_conversation(conn, conversation_id),
            "replayed": False,
        }
