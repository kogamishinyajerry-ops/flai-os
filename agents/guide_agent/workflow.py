"""guide_agent workflow：interactive 型导引 Agent（M6 起，编排官化 M8/ADR-0012）。

ConversationService 每轮调用 `run(context)`（统一入口，interactive 型 context）：
1. 把包内 prompt.md（系统提示，唯一版本化来源）拼上**运行时从 Registry 生成的
   候选 Agent 清单**作为 system content；
2. 经 Model Gateway（profile=reasoning）发起对话，得到本轮 assistant 回复；
3. 若回复含计划块（`<<PLAN>>...<<END>>`），对其做**确定性校验**后才继续。裁决
   有三种（decision）：
   - `delegate`：问题匹配已审定的 interactive 垂类专家；运行时在同一主对话自动
     转交并返回该专家的最终结果，内部路由对象不持久化、不让工程师选择。
   - `orchestrate`：平台有合适 Agent。含最终分析、待用户确认的目标、以及一组
     **每个都经确定性对账**的 Agent（含各自分工 role + 预填草案）与协作方式。
   - `refuse`：没有合适 Agent（甚至不值得为此建专用 Agent）。含拒绝理由、仍未
     解决的问题、以及如何重述/拆解才可接——**显式拒绝，不硬凑**。

LLM 边界（宪法铁律六 + §11.2）：LLM 只负责对话与**提议**，它说"转交/召集 X、
预填 Y"不构成结构真值——delegate 只允许命中审定 interactive allowlist；本文件
对 orchestrate 的**每个** Agent 确定性对账 Registry
（agent_id 必须真实存在、非 disabled、非 interactive、非导引自身）与目标
input_schema.json。成员集合必须原子可执行：任一成员无效、重复或超过上限，整份计划
关闭并回主对话澄清，绝不静默删除可能承担复核/接力职责的环节。
导引**绝不创建/召集/签发任务**：计划只是建议，人在工作台确认完整方案是否开工；
关键工程判断与最终签发仍由人完成。
上游失败/空内容一律诚实抛错，绝不伪造对话或计划。
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable

from jsonschema import validate
from jsonschema.validators import validator_for

_PLAN_START = "<<PLAN>>"
_PLAN_END = "<<END>>"
_SELF_ID = "guide_agent"
# ConversationService 尚未携带当前 actor role，不能把 Registry 中未来新增的
# admin-only interactive 包自动暴露给所有工程师。V0.4 只开放这两个已审定且
# permissions.allowed_roles 含 business_user 的垂类问答；通用化须先补角色化授权。
_INTERACTIVE_HANDOFF_IDS = frozenset({"policy_qa_agent", "standards_qa_agent"})

_MAX_PLAN_AGENTS = 5          # 单份计划召集 Agent 数上限（出现第 6 个即关闭整份方案）
_MAX_TEXT_CHARS = 2_000      # 单个自由文本字段上限（analysis/goal/reason/role…）
_MAX_LIST_ITEMS = 8          # residual_problems / reframe 列表条数上限
# 异源 Codex R1-#2：此前只有 _text 字段（analysis/goal/role…）受 2K 约束，prefill 值、
# dropped_agents、stripped_fields 均只受"模型输出长度"隐式约束，无显式界——超长 prefill
# 值或海量幻觉 agent_id 可把 recommendation_json 撑大。下列三顶把计划总量收成有界：
_MAX_PLAN_BYTES = 50_000     # 计划块原始字节硬顶（先于 json.loads，兆级即判非法 fail-closed；
                             # 50K 对 5-Agent 含预填计划绰绰有余）。此顶一立，其内的 prefill/
                             # dropped/stripped 皆随之有界。
_MAX_DROPPED = 20            # dropped_agents 记录条数上限（防海量幻觉 id 撑审计列表）
_MAX_STRIPPED = 32           # 单 Agent stripped_fields 条数上限
_MAX_ID_CHARS = 64           # 审计列表里单个 id/字段名的展示长度上限
_INCOMPLETE_PLAN_MARKER_STEMS = ("dropped", "capped", "truncat")


class _DuplicatePlanKey(ValueError):
    """Model-authored plan JSON contains an ambiguous repeated object key."""


class _ClarificationNeeded:
    """确定性输入契约尚未满足；只在 workflow 内部传递，绝不持久化为计划。"""

    def __init__(self, gaps: list[tuple[str, list[str]]]) -> None:
        self.gaps = gaps


class _InteractiveHandoff:
    """已对账的对话型专家自动转交；内部态，不作为 recommendation 持久化。"""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id


class _VisibleReplyStream:
    """只把计划块之前的可见正文交给 UI，且能识别跨 chunk 的 sentinel。

    末尾可能是 ``<<PLAN>>`` 的一部分时先暂存；只有确认它不是 sentinel 后才发出。
    一旦命中计划块起始标记，本轮后续内容全部隐藏，最终持久化文本仍由
    ``_split_plan`` 的完整响应确定，控制 JSON 不会在流式阶段闪现。
    """

    def __init__(self, emit: Callable[[str], None]) -> None:
        self._emit = emit
        self._pending = ""
        self._hidden = False
        self._finished = False

    def feed(self, chunk: str) -> None:
        if self._finished:
            raise ValueError("可见回复流已结束，不能继续写入")
        if not isinstance(chunk, str):
            raise ValueError("可见回复流只接受文本 chunk")
        if not chunk or self._hidden:
            return

        self._pending += chunk
        marker_at = self._pending.find(_PLAN_START)
        if marker_at != -1:
            visible = self._pending[:marker_at]
            if visible:
                self._emit(visible)
            self._pending = ""
            self._hidden = True
            return

        # 保留「pending 末尾 == marker 前缀」的最长后缀，防止 <<PL / AN>>
        # 横跨上游 delta 时先把半截控制标记发到用户界面。
        held = 0
        for length in range(
            min(len(self._pending), len(_PLAN_START) - 1), 0, -1
        ):
            if self._pending.endswith(_PLAN_START[:length]):
                held = length
                break
        safe = self._pending[:-held] if held else self._pending
        if safe:
            self._emit(safe)
        self._pending = self._pending[-held:] if held else ""

    def finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        if not self._hidden and self._pending:
            self._emit(self._pending)
        self._pending = ""


def _load_system_prompt() -> str:
    return Path(__file__).with_name("prompt.md").read_text(encoding="utf-8").strip()


def run(context: dict[str, Any]) -> dict[str, Any]:
    messages: list[dict[str, Any]] = context["messages"]
    model_gateway = context["model_gateway"]
    registry = context["agent_registry"]
    agent_config = context["agent_config"]
    profile = agent_config["model"]["profile"]  # =reasoning（以 agent.yaml 为准）

    candidates = _candidates(registry)
    attachment_roster = context.get("attachment_roster")
    attachment_roster = attachment_roster if isinstance(attachment_roster, list) else []
    system_content = (
        _load_system_prompt()
        + "\n\n"
        + _render_candidates(candidates)
        + "\n\n"
        + _render_attachment_roster(attachment_roster)
    )
    chat_messages = [{"role": "system", "content": system_content}, *messages]

    # ModelUpstreamError 刻意不捕获：冒泡 → ConversationService 原样抛出，诚实失败。
    # conversation_id/agent_id 归因由运行时 _ConversationGatewayContext 自动注入
    # （ADR-0013）——workflow 不手工传身份，与 job 路径 _ModelGatewayContext 对称。
    stream_delta = context.get("stream_delta")
    visible_stream = (
        _VisibleReplyStream(stream_delta) if callable(stream_delta) else None
    )
    result = model_gateway.chat(
        profile,
        chat_messages,
        **({"on_delta": visible_stream.feed} if visible_stream is not None else {}),
    )
    reply = result.get("content")
    if not isinstance(reply, str) or not reply.strip():
        raise ValueError("导引模型返回空内容，无法继续对话（诚实失败，不伪造对话）")

    assistant_message, raw_plan = _split_plan(reply)
    # 附件存在性只能来自 ConversationService 对真实 file_id 的权威检查；绝不扫描
    # 用户可控文本里的 fence 字样，否则纯文本可伪造附件让后端产生假就绪方案。
    attachment_context_present = context.get("attachment_context_present") is True
    validated = (
        _validate_plan(
            raw_plan,
            registry,
            candidates,
            attachment_context_present=attachment_context_present,
            attachment_roster=attachment_roster,
        )
        if raw_plan
        else None
    )
    if isinstance(validated, _ClarificationNeeded):
        # 模型可能过早声称「可以编排」并输出半成品计划。以目标 Agent 的真实
        # input_schema 为准整份关闭计划，改在当前会话追问；不把字段墙转嫁给工程师。
        assistant_message = _render_clarification(validated)
        plan = None
    elif isinstance(validated, _InteractiveHandoff):
        # 对话型垂类专家不进入任务 batch，也不让工程师手工选择。运行时提供的
        # 自动转交闭包会复核目标快照、密级与模型归因，再在同一主对话完成回答。
        delegate = context.get("delegate_interactive")
        if callable(delegate) is not True:
            raise ValueError("导引已选择对话型专家，但运行时未提供安全转交能力")
        delegated = delegate(validated.agent_id)
        if not isinstance(delegated, dict):
            raise ValueError("对话型专家转交结果必须是 dict")
        if visible_stream is not None:
            visible_stream.finish()
        return delegated
    else:
        plan = validated
    # 仅在完整回复通过形状检查与计划校验后冲刷「可能是 sentinel 前缀」的尾部。
    # 任一异常都不 finish，避免失败轮把未确认控制片段继续展示。
    if visible_stream is not None:
        visible_stream.finish()
    # 传输键保持 `recommendation`（存储列 recommendation_json / API 字段皆不变，
    # 免迁移）——其形状自 M8 起是「导引计划」（orchestrate | refuse），前端按
    # decision 分支渲染。
    return {"assistant_message": assistant_message, "recommendation": plan}


# ── 候选 Agent 清单（注入系统提示，供 LLM 选择/预填）─────────────────────

def _candidates(registry: Any) -> list[dict[str, Any]]:
    """自动路由面 = 非 disabled、非导引自身的 specialist Agent。

    job 能力进入 orchestrate；interactive 能力只允许运行时同轴自动转交，绝不
    进入 task batch，也不暴露成工程师选择器。
    """
    out: list[dict[str, Any]] = []
    for agent in registry.list():
        agent_id = agent.get("id")
        if agent_id == _SELF_ID:
            continue
        if agent.get("status") == "disabled":
            continue
        mode = (agent.get("workflow", {}) or {}).get("mode")
        if mode not in {"job", "interactive"}:
            continue
        if mode == "interactive":
            allowed_roles = ((agent.get("permissions") or {}).get("allowed_roles") or [])
            if (
                agent_id not in _INTERACTIVE_HANDOFF_IDS
                or not isinstance(allowed_roles, list)
                or "business_user" not in allowed_roles
            ):
                continue
        input_config = agent.get("input") or {}
        raw_extensions = input_config.get("allowed_extensions") or []
        allowed_extensions = (
            [
                extension.strip().lower()
                for extension in raw_extensions
                if isinstance(extension, str) and extension.strip()
            ]
            if isinstance(raw_extensions, list)
            else []
        )
        out.append(
            {
                "id": agent_id,
                "name": agent.get("name", ""),
                "category": agent.get("category", ""),
                "status": agent.get("status", ""),
                "maturity": agent.get("maturity", ""),
                "summary": agent.get("summary", ""),
                "mode": mode,
                "input_type": (input_config.get("type") or ""),
                "allowed_extensions": allowed_extensions,
                "input_fields": _input_fields(registry, agent_id),
            }
        )
    return out


def _input_fields(registry: Any, agent_id: str) -> dict[str, str]:
    """从目标 Agent 快照声明的输入 schema 抽 {字段名: 描述}，供 LLM 预填参考。
    读不到 schema（无 params 输入等）返回空 dict——不报错，只是没有可填字段。"""
    schema = _load_input_schema(registry, agent_id)
    if not schema:
        return {}
    props = schema.get("properties", {})
    if not isinstance(props, dict):
        return {}
    return {name: (spec or {}).get("description", "") for name, spec in props.items()}


def _load_input_schema(registry: Any, agent_id: str) -> dict[str, Any] | None:
    try:
        # 一次取得 manifest 与完整文件字节的同代不可变视图。不能先从 live manifest
        # 取路径、再打开 package_dir；否则扫描/发布并发时会把 A 代路径和 B 代内容拼接。
        snapshot = registry.package_snapshot(agent_id)
        if snapshot is None:
            return None
        manifest = snapshot.manifest
        files = snapshot.files
        if not isinstance(manifest, dict) or not isinstance(files, tuple):
            return None
        input_config = manifest.get("input")
        if not isinstance(input_config, dict):
            return None
        schema_filename = input_config.get("schema")
        if not isinstance(schema_filename, str) or not schema_filename:
            return None

        schema_payload: bytes | None = None
        seen_paths: set[str] = set()
        for entry in files:
            if not isinstance(entry, tuple) or len(entry) != 2:
                return None
            relative_path, payload = entry
            if not isinstance(relative_path, str) or not isinstance(payload, bytes):
                return None
            if relative_path in seen_paths:
                return None
            seen_paths.add(relative_path)
            if relative_path == schema_filename:
                schema_payload = payload
        if schema_payload is None:
            return None

        loaded = json.loads(schema_payload.decode("utf-8"))
        return loaded if isinstance(loaded, dict) else None
    except Exception:
        # Registry/snapshot 属性异常、非 UTF-8、非法/深嵌套 JSON 均不能证明输入契约；
        # 调用方会按 input_type 决定继续澄清或（仅 none）接受无 schema。
        return None


def _render_candidates(candidates: list[dict[str, Any]]) -> str:
    if not candidates:
        return "## 当前可自动路由的能力\n\n（平台暂无可用能力，请如实告知用户。）"
    lines = ["## 当前可自动路由的能力", ""]
    for c in candidates:
        lines.append(
            f"- id=`{c['id']}` 名称={c['name']} 类型={c['category']} "
            f"成熟度={c['maturity']}/{c['status']} "
            f"运行方式={'当前对话自动转交' if c['mode'] == 'interactive' else '任务执行'}"
        )
        lines.append(f"  简介：{c['summary']}")
        if c["mode"] == "interactive":
            lines.append("  路由约束：只可用 delegate 自动转交，不得放进 orchestrate 任务列表")
            continue
        if c.get("input_type") == "file_upload":
            lines.append("  原始输入：必须有可供该执行环节读取的附件")
            extensions = c.get("allowed_extensions") or []
            if extensions:
                lines.append(f"  可读取文件后缀：{'、'.join(extensions)}")
        if c["input_fields"]:
            fields = "、".join(
                f"{name}（{desc}）" if desc else name for name, desc in c["input_fields"].items()
            )
            lines.append(f"  输入字段：{fields}")
        else:
            lines.append("  输入字段：（无结构化输入字段）")
    return "\n".join(lines)


def _render_attachment_roster(roster: list[dict[str, Any]]) -> str:
    """把运行时可信附件名册作为 JSON 行注入；文件名只作数据，不参与选 id。"""
    lines = ["## 当前工作附件名册（系统可信）", ""]
    if not roster:
        lines.append("（无当前工作附件。）")
        return "\n".join(lines)
    lines.append(
        "只能在计划中引用下列 label；不得用 filename/file_id 选择或直接输出 file_id。"
    )
    lines.append(
        "每个当前工作附件必须在 agents[].attachments 或 ignored_attachments 中恰好一次。"
    )
    lines.extend(
        json.dumps(item, ensure_ascii=False, sort_keys=True) for item in roster
    )
    return "\n".join(lines)


# ── 计划块解析 + 确定性校验（LLM 边界的咬合点）──────────────────────────

def _split_plan(reply: str) -> tuple[str, str | None]:
    """把 assistant 文本与计划块拆开。无块 → (原文, None)；有块 → (块外文本, 块内 JSON 串)。

    块前 + 块后的文本都原样保留展示（审计 P3：此前块后文本被静默丢弃）；块后若再
    出现计划块，只认第一块、后续整体丢弃（不把 sentinel 原文外露给用户当正文）。"""
    start = reply.find(_PLAN_START)
    if start == -1:
        return reply.strip(), None
    end = reply.find(_PLAN_END, start)
    if end == -1:
        # 有起始无结束意味着控制块被截断。若当纯文本保存，sentinel 与半截 JSON
        # 会经 done/历史永久外露；必须整轮失败，由会话事务保证零消息落库。
        raise ValueError(
            "导引模型计划块缺少 <<END>>，响应不完整——本轮不落库"
        )
    raw = reply[start + len(_PLAN_START):end].strip()
    tail = reply[end + len(_PLAN_END):]
    next_block = tail.find(_PLAN_START)
    if next_block != -1:
        tail = tail[:next_block]
    parts = [p for p in (reply[:start].strip(), tail.strip()) if p]
    message = "\n".join(parts) if parts else "已根据你的需求给出方案，请在下方确认。"
    return message, raw


def _validate_plan(
    raw: str,
    registry: Any,
    candidates: list[dict[str, Any]],
    *,
    attachment_context_present: bool = False,
    attachment_roster: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | _ClarificationNeeded | _InteractiveHandoff | None:
    """对 LLM 提议的计划做确定性对账；不合法 → 返回 None（fail-closed，不外露非法计划）。

    - decision 必须是 orchestrate | delegate | refuse；
    - delegate：只接受清单内真实、非 disabled、非自身的 interactive 专家，随后由
      ConversationService 在同一主对话自动转交；不生成任务、不让用户选择 Agent；
    - refuse：纯文本裁决（拒绝理由 + 残留问题 + 重述建议），无 Agent 可召集，形状
      合法即产出（导引显式拒绝本身不构成任何副作用）；
    - orchestrate：逐个 Agent 对账 Registry + 目标 input_schema；幻觉/disabled/
      interactive/自身/重复或超过成员上限，整份方案回主对话澄清。不可只删除异常
      成员后开放余下成员，因为被删项可能正是必需的复核/接力环节。
    """

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        # ``object_pairs_hook`` 会对每一层 JSON object 调用此函数。不能让标准
        # ``json.loads`` 的 last-key-wins 语义把前一个 dropped/capped/truncated
        # 证据或任意嵌套工程输入静默覆盖后，再进入 canonicalization。
        parsed: dict[str, Any] = {}
        for key, value in pairs:
            if key in parsed:
                raise _DuplicatePlanKey
            parsed[key] = value
        return parsed

    try:
        # 按 **UTF-8 字节** 而非字符判上限（异源 Codex R1-#2 复审：CJK 计划 17K 字符
        # ≈51K 字节会绕过字符顶；编码异常同样 fail-closed）。此闸先于 json.loads、不落库。
        if len(raw.encode("utf-8")) > _MAX_PLAN_BYTES:
            return None
        proposed = json.loads(raw, object_pairs_hook=reject_duplicate_keys)
    except _DuplicatePlanKey:
        # 重复键不是可确定解释的计划：整份关闭并回到同一主对话自然澄清，不能
        # 采用任一出现次序，更不能让 last-key-wins 伪造“完整”。
        return _plan_membership_clarification()
    except (json.JSONDecodeError, RecursionError, ValueError):
        # JSON 非法 / **深嵌套 RecursionError** / 编码异常一律作废（异源 Codex R1-#2 复审：
        # 限额内的深嵌套 JSON 会抛未捕获 RecursionError 逃逸成 500）。ValueError 覆盖
        # JSONDecodeError 与 UnicodeEncodeError。
        return None
    if not isinstance(proposed, dict):
        return None

    # 残缺控制标记是整份模型提议的单向否决信号，不只属于 orchestrate。
    # 即使 refuse/delegate 没有任务副作用，也不能把带截断/丢项证据的裁决持久化
    # 成完整结论；统一回到同一主对话澄清，保持三种 decision 的审计语义一致。
    if _raw_plan_has_active_incomplete_marker(proposed) is True:
        return _plan_membership_clarification()

    decision = proposed.get("decision")
    if decision == "refuse":
        return _validate_refuse(proposed)
    if decision == "delegate":
        return _validate_delegate(proposed, candidates)
    if decision == "orchestrate":
        return _validate_orchestrate(
            proposed,
            registry,
            candidates,
            attachment_context_present=attachment_context_present,
            attachment_roster=attachment_roster,
        )
    return None  # 未知/缺失 decision → 作废


def _validate_delegate(
    proposed: dict[str, Any], candidates: list[dict[str, Any]]
) -> _InteractiveHandoff | None:
    agent_id = proposed.get("agent_id")
    rationale = _text(proposed.get("rationale"))
    if not isinstance(agent_id, str) or not rationale:
        return None
    target = next(
        (
            candidate
            for candidate in candidates
            if candidate.get("id") == agent_id and candidate.get("mode") == "interactive"
        ),
        None,
    )
    return _InteractiveHandoff(agent_id) if target is not None else None


def _validate_refuse(
    proposed: dict[str, Any],
) -> dict[str, Any] | _ClarificationNeeded:
    reason = _text(proposed.get("reason"))
    residual_problems = _text_list(proposed.get("residual_problems"))
    reframe = _text_list(proposed.get("reframe"))
    missing = [
        label
        for present, label in (
            (bool(reason), "接不住的具体原因"),
            (bool(residual_problems), "仍未解决的问题"),
            (bool(reframe), "可继续推进的重述或拆解建议"),
        )
        if present is False
    ]
    if missing:
        # 空拒绝比诚实追问更糟：它既不给原因，也不给工程师下一步。继续在主对话
        # 澄清，不持久化“拒绝”死胡同。
        return _ClarificationNeeded([("拒绝判断", missing)])
    return {
        "decision": "refuse",
        "reason": reason,
        "residual_problems": residual_problems,
        "reframe": reframe,
    }


def _raw_plan_has_active_incomplete_marker(proposed: dict[str, Any]) -> bool:
    """把模型自报的残缺状态只当作单向否决信号。

    顶层 ``dropped/capped/truncated`` 及未来同词干字段（例如
    ``roster_truncated_count``）一旦处于活动态，整份方案必须重新澄清。空值只能表示
    “未自报异常”，不能证明方案完整；后续 Registry/schema 校验仍是唯一结构真值。
    只扫描计划控制层，避免 Agent 业务输入里的同名字段误触发。
    """

    for key, value in proposed.items():
        if isinstance(key, str) is False:
            continue
        normalized_key = key.casefold()
        marker_name = False
        for marker_stem in _INCOMPLETE_PLAN_MARKER_STEMS:
            if marker_stem in normalized_key:
                marker_name = True
                break
        if marker_name is False:
            continue

        # bool 必须先于 number：Python 的 bool 是 int 子类。这里逐类型显式判断，
        # 不用 truthiness，确保 false / 0 / [] 是非活动态，非零计数不会绕过。
        active = False
        if value is True:
            active = True
        elif value is False or value is None:
            active = False
        elif isinstance(value, (int, float)) and isinstance(value, bool) is False:
            active = value != 0
        elif isinstance(value, str):
            active = len(value.strip()) > 0
        elif isinstance(value, list):
            active = len(value) > 0
        elif isinstance(value, dict):
            active = len(value) > 0

        if active is True:
            return True
    return False


def _validate_orchestrate(
    proposed: dict[str, Any],
    registry: Any,
    candidates: list[dict[str, Any]],
    *,
    attachment_context_present: bool = False,
    attachment_roster: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | _ClarificationNeeded | None:
    candidate_map = {c["id"]: c for c in candidates if c.get("mode") == "job"}
    analysis = _text(proposed.get("analysis"))
    goal = _text(proposed.get("goal"))
    workflow = _text(proposed.get("workflow"))
    plan_gaps = [
        label
        for value, label in (
            (analysis, "任务分析"),
            (goal, "明确目标"),
            (workflow, "协作方式"),
        )
        if not value
    ]
    if plan_gaps:
        # 字段存在但为空同样不是完整方案；绝不让空目标/空分工穿过类型 schema
        # 变成可开工按钮。继续在对话里澄清，而不是显示内部字段名。
        return _ClarificationNeeded([("整体方案", plan_gaps)])
    raw_agents = proposed.get("agents")
    raw_agents = raw_agents if isinstance(raw_agents, list) else []
    attachment_binding_mode = (
        bool(attachment_roster)
        or "ignored_attachments" in proposed
        or any(
            isinstance(entry, dict) and "attachments" in entry
            for entry in raw_agents
        )
    )

    agents: list[dict[str, Any]] = []
    dropped: list[str] = []
    seen: set[str] = set()
    capped = False
    raw_to_final: dict[int, int] = {}
    raw_afters: list[Any] = []
    input_gaps: list[tuple[str, list[str]]] = []
    for raw_idx, entry in enumerate(raw_agents):
        if len(agents) >= _MAX_PLAN_AGENTS:
            capped = True
            break
        if not isinstance(entry, dict):
            dropped.append("(非对象条目)")
            continue
        agent_id = entry.get("agent_id")
        if not isinstance(agent_id, str) or agent_id not in candidate_map:
            # 幻觉/非法/不可召集的 agent_id
            dropped.append(agent_id if isinstance(agent_id, str) else "(缺 agent_id)")
            continue
        if agent_id in seen:
            dropped.append(agent_id)  # 同一 Agent 重复召集，只保留首个
            continue
        seen.add(agent_id)
        target = candidate_map[agent_id]
        raw_inputs = entry.get("prefilled_inputs")
        raw_inputs = raw_inputs if isinstance(raw_inputs, dict) else {}
        prefilled, stripped = _clean_prefilled_inputs(registry, agent_id, raw_inputs)
        role = _text(entry.get("role"))
        rationale = _text(entry.get("rationale"))
        inputs_complete, missing_labels = _required_inputs_complete(
            registry,
            agent_id,
            prefilled,
            input_type=target.get("input_type"),
            attachment_context_present=attachment_context_present,
        )
        member_gaps = list(missing_labels) if inputs_complete is False else []
        if not role:
            member_gaps.append("本环节的明确分工")
        if not rationale:
            member_gaps.append("选择这一能力的理由")
        if member_gaps:
            input_gaps.append((target["name"] or agent_id, member_gaps))
        raw_to_final[raw_idx] = len(agents)
        raw_afters.append(entry.get("after"))
        agents.append(
            {
                "agent_id": agent_id,
                "agent_name": target["name"],
                "category": target["category"],
                "status": target["status"],
                "maturity": target["maturity"],
                "role": role,
                "rationale": rationale,
                "prefilled_inputs": prefilled,
                "stripped_fields": stripped,
            }
        )

    if len(dropped) > 0 or capped is True:
        # 方案成员集合是原子语义：被剔除的条目可能正是“独立复核”或“接力验证”，
        # 静默保留 A、删除 B 会把模型提议改造成另一份工程方案。保守策略是不尝试
        # 判定重复项是否真正冗余；任何 unknown/disabled/self/duplicate/非对象或第六
        # 个成员都关闭整份 recommendation，回到同一对话按任务语义重新编排。
        return _plan_membership_clarification()

    if not agents:
        # 即便所有 Agent 都被 Registry 对账剥离，也先审计显式附件分配；否则模型
        # 把附件交给 ghost Agent 时会留下「已可编排」的矛盾成功话术，而不是自然
        # 澄清。绑定无异常才沿用零真实 Agent 的整份作废语义。
        if attachment_binding_mode:
            resolved = _resolve_attachment_bindings(
                proposed,
                raw_agents,
                raw_to_final,
                agents,
                candidate_map,
                attachment_roster if isinstance(attachment_roster, list) else [],
            )
            if isinstance(resolved, _ClarificationNeeded):
                return resolved
        # orchestrate 却无任何真实 Agent 存活 = 幻觉召集，整份作废（fail-closed）。
        return None

    if input_gaps:
        # 多 Agent 方案也必须整份就绪；任一成员缺输入，都不得留下可部分开工的计划。
        return _ClarificationNeeded(input_gaps)

    canonical_ignored: list[dict[str, str]] | None = None
    if attachment_binding_mode:
        resolved = _resolve_attachment_bindings(
            proposed,
            raw_agents,
            raw_to_final,
            agents,
            candidate_map,
            attachment_roster if isinstance(attachment_roster, list) else [],
        )
        if isinstance(resolved, _ClarificationNeeded):
            return resolved
        canonical_by_agent, canonical_ignored = resolved
        for final_idx, canonical_files in canonical_by_agent.items():
            agents[final_idx]["attachments"] = canonical_files

    # 批七 §S2-7：after 同批依赖（LLM 以其原始条目下标声明「本成员需要哪些更早
    # 成员的产物」）。剥离降级纪律（fail-safe，绝不静默）：任一非法引用——非整数/
    # 指向被剪条目/自引或前向引用（最终序）——则**整个 after 字段剥离为无依赖**
    # 并记入该成员 stripped_fields（宁可扁平并行召集，也不虚构/半保留依赖图；
    # 前端据 stripped_fields 显式口播降级）。合法引用经 raw→final 重映射，只许
    # 指向最终列表更早条目 ⟹ 按构造无环，零环检测代码。
    for final_idx, agent_entry in enumerate(agents):
        raw_after = raw_afters[final_idx]
        if raw_after is None:
            agent_entry["after"] = []
            continue
        refs = raw_after if isinstance(raw_after, list) else None
        mapped: list[int] = []
        valid = refs is not None
        for ref in refs or []:
            if not isinstance(ref, int) or isinstance(ref, bool):
                valid = False
                break
            tgt = raw_to_final.get(ref)
            if tgt is None or tgt >= final_idx:
                valid = False
                break
            mapped.append(tgt)
        if valid is True:
            # 显式空列表=合法「无依赖」声明，与缺省同义——绝不记 stripped（3-lens
            # P2：把合法空值当剥离会向用户口播虚假降级告警，违反如实记名）。
            agent_entry["after"] = sorted(set(mapped))
        else:
            agent_entry["after"] = []
            agent_entry["stripped_fields"] = list(agent_entry.get("stripped_fields") or []) + ["after"]

    canonical_plan = {
        "decision": "orchestrate",
        "analysis": analysis,
        "goal": goal,
        "workflow": workflow,
        "agents": agents,
        # 审计列表收成有界：条数 ≤ _MAX_DROPPED、单条 ≤ _MAX_ID_CHARS（异源 Codex R1-#2）。
        "dropped_agents": [d[:_MAX_ID_CHARS] for d in dropped[:_MAX_DROPPED]],
        "capped": capped,
    }
    # fresh 计划只要当前 roster 非空就必须输出绑定合同；roster 为空时允许省略，
    # 兼容无附件旧 shape。若模型主动输出空绑定字段，同样做完整确定性校验。
    if canonical_ignored is not None:
        canonical_plan["ignored_attachments"] = canonical_ignored
    return canonical_plan


def _resolve_attachment_bindings(
    proposed: dict[str, Any],
    raw_agents: list[Any],
    raw_to_final: dict[int, int],
    agents: list[dict[str, Any]],
    candidate_map: dict[str, dict[str, Any]],
    roster: list[dict[str, Any]],
) -> (
    tuple[dict[int, list[dict[str, str]]], list[dict[str, str]]]
    | _ClarificationNeeded
):
    """把 LLM 的稳定 label 提议解析为可信 file 对象，并验证完整分区。

    文件身份只取自 ConversationService 构造的 ``roster``。文件名允许重复，模型
    不能提交/猜测 ``file_id``；它只能把每个 ``附件N`` 恰好放进一个已存活 Agent，
    或放进顶层 ignored_attachments。任何未知、重复、遗漏或输入类型不匹配都回到
    主对话澄清，不做最近名称匹配等推断。
    """

    roster_map: dict[str, dict[str, str]] = {}
    roster_file_ids: set[str] = set()
    for index, raw_item in enumerate(roster, start=1):
        if not isinstance(raw_item, dict):
            return _attachment_clarification("当前附件名册无法安全识别")
        label = raw_item.get("label")
        file_id = raw_item.get("file_id")
        filename = raw_item.get("filename")
        if (
            not isinstance(label, str)
            or label != f"附件{index}"
            or not isinstance(file_id, str)
            or not file_id
            or not isinstance(filename, str)
            or not filename
            or label in roster_map
            or file_id in roster_file_ids
        ):
            return _attachment_clarification("当前附件名册无法安全识别")
        roster_map[label] = {"file_id": file_id, "filename": filename}
        roster_file_ids.add(file_id)

    def labels_from(value: Any) -> list[str] | None:
        if not isinstance(value, list):
            return None
        if any(not isinstance(item, str) or not item for item in value):
            return None
        return value

    ignored_labels = labels_from(proposed.get("ignored_attachments"))
    if ignored_labels is None:
        return _attachment_clarification("需要明确哪些当前附件不参与本次工作")

    seen_labels: set[str] = set()
    canonical_by_agent: dict[int, list[dict[str, str]]] = {}
    for raw_idx, final_idx in raw_to_final.items():
        entry = raw_agents[raw_idx]
        # raw_to_final 只会指向已校验 dict；此处仍守住公共 helper 的输入边界。
        if not isinstance(entry, dict) or "attachments" not in entry:
            return _attachment_clarification("需要明确每个执行环节读取哪些附件")
        labels = labels_from(entry.get("attachments"))
        if labels is None:
            return _attachment_clarification("执行环节的附件分配格式无法识别")
        if any(label not in roster_map for label in labels):
            return _attachment_clarification("计划引用了不在当前工作段的附件")
        if any(label in seen_labels for label in labels) or len(set(labels)) != len(labels):
            return _attachment_clarification("同一附件只能绑定或忽略一次")

        target_agent_id = agents[final_idx]["agent_id"]
        target = candidate_map[target_agent_id]
        input_type = target.get("input_type")
        if input_type == "none" and labels:
            return _attachment_clarification("不读取文件的执行环节不能绑定附件")
        if input_type == "file_upload":
            if len(labels) != 1:
                return _attachment_clarification("文件读取环节必须且只能绑定一个附件")
            allowed_extensions = target.get("allowed_extensions")
            allowed_extensions = (
                allowed_extensions if isinstance(allowed_extensions, list) else []
            )
            filename = roster_map[labels[0]]["filename"].casefold()
            if not allowed_extensions or not any(
                isinstance(extension, str)
                and extension.startswith(".")
                and filename.endswith(extension.casefold())
                for extension in allowed_extensions
            ):
                return _attachment_clarification("所选附件格式与执行能力不匹配")

        seen_labels.update(labels)
        canonical_by_agent[final_idx] = [dict(roster_map[label]) for label in labels]

    # 被幻觉、重复或上限剪除的 Agent 不得暗中“吃掉”附件。空列表可随该无效条目
    # 一并剥离；非空绑定必须关闭方案，交给下一轮重新分配。
    for raw_idx, entry in enumerate(raw_agents):
        if raw_idx in raw_to_final or not isinstance(entry, dict):
            continue
        if "attachments" not in entry:
            continue
        dropped_labels = labels_from(entry.get("attachments"))
        if dropped_labels is None or dropped_labels:
            return _attachment_clarification("附件被分配给了不可用的执行环节")

    if any(label not in roster_map for label in ignored_labels):
        return _attachment_clarification("计划忽略了不在当前工作段的附件")
    if (
        any(label in seen_labels for label in ignored_labels)
        or len(set(ignored_labels)) != len(ignored_labels)
    ):
        return _attachment_clarification("同一附件只能绑定或忽略一次")
    seen_labels.update(ignored_labels)

    if seen_labels != set(roster_map):
        return _attachment_clarification("每个当前附件都必须明确绑定或忽略")

    return (
        canonical_by_agent,
        [dict(roster_map[label]) for label in ignored_labels],
    )


def _attachment_clarification(_detail: str) -> _ClarificationNeeded:
    """绑定校验失败仍 fail-closed，但不把内部路由术语转嫁给工程师。

    ``_detail`` 只表达确定性校验原因；当前交互合同没有安全的内部诊断通道，故对外
    统一追问材料用途。工程师只需自然描述或继续上传，不会看到 label/file_id、绑定、
    忽略等编排字段。
    """
    return _ClarificationNeeded(
        [("当前材料", ["每份附件是否参与本次工作、以及准备用在哪个环节"])]
    )


def _plan_membership_clarification() -> _ClarificationNeeded:
    """不外露 Agent 选择器，只请工程师补充必须保留的任务语义。"""
    return _ClarificationNeeded(
        [("完整方案", ["每个必须保留的工作环节、预期结果和衔接关系"])]
    )


def _text(value: Any, cap: int = _MAX_TEXT_CHARS) -> str:
    """自由文本字段：非字符串一律归空串，超上限截断（防 LLM 巨量输出撑爆存储/UI）。"""
    if not isinstance(value, str):
        return ""
    value = value.strip()
    return value if len(value) <= cap else value[:cap] + "…（已截断）"


def _text_list(value: Any) -> list[str]:
    """字符串列表字段：过滤非串、去空、截条数与单条长度。"""
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if len(out) >= _MAX_LIST_ITEMS:
            break
        t = _text(item)
        if t:
            out.append(t)
    return out


def _clean_prefilled_inputs(
    registry: Any, agent_id: str, raw_inputs: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """只保留目标 input_schema 声明且逐字段校验通过的字段；其余剥离并记名。

    本函数是第一阶段净化，只保证「留下的每个字段都合法」；随后
    ``_required_inputs_complete`` 会对净化结果执行完整 schema 校验。任一必需输入
    不足时整份计划关闭并回到会话追问，不把补字段工作转嫁给工程师。
    """
    schema = _load_input_schema(registry, agent_id)
    if not schema or not isinstance(schema.get("properties"), dict):
        # 目标无结构化字段（如 file_upload/none 型）：不接受任何预填字段。
        # stripped 同样收成有界（异源 Codex R1-#2 复审：此早退路径此前绕过条数/长度顶，
        # 海量未知字段名可撑大审计列表）。
        return {}, _bounded_stripped(raw_inputs.keys())

    props: dict[str, Any] = schema["properties"]
    kept: dict[str, Any] = {}
    stripped: list[str] = []
    for name, value in raw_inputs.items():
        if name not in props:
            stripped.append(name)
            continue
        if _field_valid(schema, name, value):
            kept[name] = value
        else:
            stripped.append(name)
    # 交叉约束复验（异源 Codex R1-#1）：_field_valid 逐字段看，漏掉根层
    # allOf/if-then/not/dependentSchemas 等**跨字段**约束——单看每个字段合法、组合起来
    # 却违反根约束的预填会漏进草案。对已留字段整体按「完整 schema 去掉根 required」复验
    # （本阶段不查齐全性，下一阶段统一检查）；失败即保守清空全部预填并记入 stripped
    # （fail-closed，剥离方向即安全方向；随后完整性闸门会转成对话追问）。
    if kept and not _partial_object_valid(schema, kept):
        stripped.extend(kept.keys())
        kept = {}
    return kept, _bounded_stripped(stripped)


def _required_inputs_complete(
    registry: Any,
    agent_id: str,
    inputs: dict[str, Any],
    *,
    input_type: Any,
    attachment_context_present: bool,
) -> tuple[bool, list[str]]:
    """按目标 Agent 的完整 input_schema 确定性判断计划是否已经可执行。

    ``_clean_prefilled_inputs`` 只负责剥离不可信字段；这里再跑完整 schema（包含
    ``required``、条件分支、数组下限和跨字段约束）。任何 schema/解析异常都按
    fail-closed 处理。返回给追问层的是面向工程师的标题，不暴露 JSON 字段墙。
    """
    schema = _load_input_schema(registry, agent_id)
    if schema is None:
        # 只有显式 none 模式可以没有 schema。params/file_upload（以及未知模式）的
        # schema 缺失或损坏都意味着无法证明输入完整，必须 fail-closed 回到对话。
        if input_type == "none":
            return True, []
        return False, ["目标 Agent 的输入契约"]

    if input_type == "file_upload" and attachment_context_present is False:
        return False, ["可供该环节读取的附件"]

    try:
        validator_cls = validator_for(schema)
        validator_cls.check_schema(schema)
        errors = list(validator_cls(schema).iter_errors(inputs))
    except Exception:
        return False, ["可执行所需的工程信息"]
    if not errors:
        return True, []

    missing_names: list[str] = []

    def collect_required(error: Any) -> None:
        if (
            error.validator == "required"
            and isinstance(error.instance, dict)
            and isinstance(error.validator_value, list)
        ):
            for name in error.validator_value:
                if isinstance(name, str) and name not in error.instance:
                    missing_names.append(name)
        for child in error.context:
            collect_required(child)

    for error in errors:
        collect_required(error)

    props = schema.get("properties")
    props = props if isinstance(props, dict) else {}
    labels: list[str] = []
    for name in missing_names:
        spec = props.get(name)
        spec = spec if isinstance(spec, dict) else {}
        label = spec.get("title")
        if not isinstance(label, str) or not label.strip():
            label = spec.get("description")
        if not isinstance(label, str) or not label.strip():
            label = name
        label = label.strip().split("。", 1)[0][:120]
        if label and label not in labels:
            labels.append(label)
    return False, labels or ["可执行所需的工程信息"]


def _render_clarification(clarification: _ClarificationNeeded) -> str:
    """把 schema 缺口转成最多两个自然语言问题，保持文字/附件单入口。"""
    questions: list[str] = []
    for agent_name, labels in clarification.gaps:
        if len(questions) >= 2:
            break
        shown = labels[:2]
        detail = "、".join(shown) if shown else "可执行所需的工程信息"
        suffix = "等信息" if len(labels) > len(shown) else ""
        questions.append(f"“{agent_name}”这一段还需要确认{detail}{suffix}")
    if len(clarification.gaps) > len(questions):
        questions.append("其余协作环节也还有未确认的执行信息")
    joined = "；".join(questions)
    return (
        f"为了把这件事整理成一份可直接开工的完整方案，我还需要确认：{joined}。"
        "请直接用文字补充，或上传包含这些信息的附件。"
    )


def _bounded_stripped(names: Any) -> list[str]:
    """stripped_fields 统一收界口（异源 Codex R1-#2 复审：两条返回路径共用，杜绝早退
    路径绕过界）：单字段名 ≤ _MAX_ID_CHARS、去重排序、条数 ≤ _MAX_STRIPPED。"""
    return sorted({n[:_MAX_ID_CHARS] for n in names})[:_MAX_STRIPPED]


def _partial_object_valid(schema: dict[str, Any], obj: dict[str, Any]) -> bool:
    """把完整 input_schema 去掉根 `required` 后校验 obj 整体，使根层
    allOf/if-then/not/dependentSchemas 等**跨字段**约束真正生效（`_field_valid`
    只逐字段看，评估不到这些）。预填是部分输入，故移除 required 不查齐全性，只查
    「留下来这组字段的组合是否违反跨字段约束」。$ref 在完整 schema 内自然解析回根，
    任何异常（非法组合 / 无法评估的 schema）一律判不合法——fail-closed。"""
    probe = copy.deepcopy(schema)
    probe.pop("required", None)
    try:
        validate(obj, probe)
        return True
    except Exception:
        return False


def _field_valid(schema: dict[str, Any], name: str, value: Any) -> bool:
    """在「携带原 schema 的 $defs/definitions」的 mini-schema 上校验单个字段值。

    反方 P2：直接对孤立子 schema 校验，字段里的 `#/$defs/..`、`#/definitions/..`
    引用无法解析，jsonschema 抛的是引用错误（非 ValidationError 子类）而非校验失败，
    会逃逸成未处理 500。这里把 $defs/definitions 一并放进 mini-schema 根，使引用
    解析回文档根；且**任何**校验异常（非法值 / 无法评估的 schema）一律判不合法 →
    剥离。剥离方向即安全方向，且预填字段在人提交后还会经 Runtime 对完整 schema
    再校验一次（纵深防御），故此处保守剥离不放松边界。
    """
    mini: dict[str, Any] = {"type": "object", "properties": {name: schema["properties"][name]}}
    for defs_key in ("$defs", "definitions"):
        if defs_key in schema:
            mini[defs_key] = schema[defs_key]
    try:
        validate({name: value}, mini)
        return True
    except Exception:
        # ValidationError（非法值）或引用/schema 错误（无法评估）都判不合法——fail-closed。
        return False
