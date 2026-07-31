"""guide_agent workflow：interactive 型导引 Agent（M6 起，编排官化 M8/ADR-0012）。

ConversationService 每轮调用 `run(context)`（统一入口，interactive 型 context）：
1. 把包内 prompt.md（系统提示，唯一版本化来源）拼上**运行时从 Registry 生成的
   候选 Agent 清单**作为 system content；
2. 经 Model Gateway（profile=reasoning）发起对话，得到本轮 assistant 回复；
3. 若回复含计划块（`<<PLAN>>...<<END>>`），对其做**确定性校验**后才作为结构化
   计划返回。计划有两种裁决（decision）：
   - `orchestrate`：平台有合适 Agent。含最终分析、待用户确认的目标、以及一组
     **每个都经确定性对账**的 Agent（含各自分工 role + 预填草案）与协作方式。
   - `refuse`：没有合适 Agent（甚至不值得为此建专用 Agent）。含拒绝理由、仍未
     解决的问题、以及如何重述/拆解才可接——**显式拒绝，不硬凑**。

LLM 边界（宪法铁律六 + §11.2）：LLM 只负责对话与**提议**，它说"召集 X、预填 Y"
不构成结构真值——本文件对 orchestrate 的**每个** Agent 确定性对账 Registry
（agent_id 必须真实存在、非 disabled、非 interactive、非导引自身）与目标
input_schema.json（逐字段校验，非法字段剥离并如实记名），任一 Agent 不过即剥离；
orchestrate 若无任何合法 Agent 存活 → 整份计划作废（fail-closed，不外露幻觉召集）。
导引**绝不创建/召集/签发任务**：计划只是草案，人在下游 tasks 端点逐个签发。
上游失败/空内容一律诚实抛错，绝不伪造对话或计划。
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable

from jsonschema import validate

_PLAN_START = "<<PLAN>>"
_PLAN_END = "<<END>>"
_SELF_ID = "guide_agent"

_MAX_PLAN_AGENTS = 5          # 单份计划召集 Agent 数上限（超出截断并记 capped）
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
    system_content = _load_system_prompt() + "\n\n" + _render_candidates(candidates)
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
    plan = _validate_plan(raw_plan, registry, candidates) if raw_plan else None
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
    """可召集面 = 非 disabled、非 interactive、非导引自身的 specialist Agent
    （与 create_task 门一致：可运行即可召集，ADR-0012 决策 4/7）。"""
    out: list[dict[str, Any]] = []
    for agent in registry.list():
        agent_id = agent.get("id")
        if agent_id == _SELF_ID:
            continue
        if agent.get("status") == "disabled":
            continue
        if (agent.get("workflow", {}) or {}).get("mode") == "interactive":
            continue
        out.append(
            {
                "id": agent_id,
                "name": agent.get("name", ""),
                "category": agent.get("category", ""),
                "status": agent.get("status", ""),
                "maturity": agent.get("maturity", ""),
                "summary": agent.get("summary", ""),
                "input_fields": _input_fields(registry, agent_id),
            }
        )
    return out


def _input_fields(registry: Any, agent_id: str) -> dict[str, str]:
    """从目标 Agent 的 input_schema.json 抽 {字段名: 描述}，供 LLM 预填参考。
    读不到 schema（无 params 输入等）返回空 dict——不报错，只是没有可填字段。"""
    schema = _load_input_schema(registry, agent_id)
    if not schema:
        return {}
    props = schema.get("properties", {})
    if not isinstance(props, dict):
        return {}
    return {name: (spec or {}).get("description", "") for name, spec in props.items()}


def _load_input_schema(registry: Any, agent_id: str) -> dict[str, Any] | None:
    pkg_dir = registry.package_dir(agent_id)
    if pkg_dir is None:
        return None
    schema_path = Path(pkg_dir) / "input_schema.json"
    if not schema_path.is_file():
        return None
    try:
        return json.loads(schema_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _render_candidates(candidates: list[dict[str, Any]]) -> str:
    if not candidates:
        return "## 当前可召集的 Agent\n\n（平台暂无可召集的 Agent，请如实告知用户。）"
    lines = ["## 当前可召集的 Agent", ""]
    for c in candidates:
        lines.append(
            f"- id=`{c['id']}` 名称={c['name']} 类型={c['category']} "
            f"成熟度={c['maturity']}/{c['status']}"
        )
        lines.append(f"  简介：{c['summary']}")
        if c["input_fields"]:
            fields = "、".join(
                f"{name}（{desc}）" if desc else name for name, desc in c["input_fields"].items()
            )
            lines.append(f"  输入字段：{fields}")
        else:
            lines.append("  输入字段：（无结构化输入字段）")
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
    raw: str, registry: Any, candidates: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """对 LLM 提议的计划做确定性对账；不合法 → 返回 None（fail-closed，不外露非法计划）。

    - decision 必须是 orchestrate | refuse；
    - refuse：纯文本裁决（拒绝理由 + 残留问题 + 重述建议），无 Agent 可召集，形状
      合法即产出（导引显式拒绝本身不构成任何副作用）；
    - orchestrate：逐个 Agent 对账 Registry + 目标 input_schema；幻觉/disabled/
      interactive/自身/重复的 agent_id 一律剥离并记入 dropped_agents；无任何合法
      Agent 存活 → 整份计划作废（None），不把「召集了但一个都不真」的空壳交给用户。
    """
    try:
        # 按 **UTF-8 字节** 而非字符判上限（异源 Codex R1-#2 复审：CJK 计划 17K 字符
        # ≈51K 字节会绕过字符顶；编码异常同样 fail-closed）。此闸先于 json.loads、不落库。
        if len(raw.encode("utf-8")) > _MAX_PLAN_BYTES:
            return None
        proposed = json.loads(raw)
    except (json.JSONDecodeError, RecursionError, ValueError):
        # JSON 非法 / **深嵌套 RecursionError** / 编码异常一律作废（异源 Codex R1-#2 复审：
        # 限额内的深嵌套 JSON 会抛未捕获 RecursionError 逃逸成 500）。ValueError 覆盖
        # JSONDecodeError 与 UnicodeEncodeError。
        return None
    if not isinstance(proposed, dict):
        return None

    decision = proposed.get("decision")
    if decision == "refuse":
        return _validate_refuse(proposed)
    if decision == "orchestrate":
        return _validate_orchestrate(proposed, registry, candidates)
    return None  # 未知/缺失 decision → 作废


def _validate_refuse(proposed: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision": "refuse",
        "reason": _text(proposed.get("reason")),
        "residual_problems": _text_list(proposed.get("residual_problems")),
        "reframe": _text_list(proposed.get("reframe")),
    }


def _validate_orchestrate(
    proposed: dict[str, Any], registry: Any, candidates: list[dict[str, Any]]
) -> dict[str, Any] | None:
    candidate_map = {c["id"]: c for c in candidates}
    raw_agents = proposed.get("agents")
    raw_agents = raw_agents if isinstance(raw_agents, list) else []

    agents: list[dict[str, Any]] = []
    dropped: list[str] = []
    seen: set[str] = set()
    capped = False
    raw_to_final: dict[int, int] = {}
    raw_afters: list[Any] = []
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
        raw_to_final[raw_idx] = len(agents)
        raw_afters.append(entry.get("after"))
        agents.append(
            {
                "agent_id": agent_id,
                "agent_name": target["name"],
                "category": target["category"],
                "status": target["status"],
                "maturity": target["maturity"],
                "role": _text(entry.get("role")),
                "rationale": _text(entry.get("rationale")),
                "prefilled_inputs": prefilled,
                "stripped_fields": stripped,
            }
        )

    if not agents:
        # orchestrate 却无任何真实 Agent 存活 = 幻觉召集，整份作废（fail-closed）。
        return None

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

    return {
        "decision": "orchestrate",
        "analysis": _text(proposed.get("analysis")),
        "goal": _text(proposed.get("goal")),
        "workflow": _text(proposed.get("workflow")),
        "agents": agents,
        # 审计列表收成有界：条数 ≤ _MAX_DROPPED、单条 ≤ _MAX_ID_CHARS（异源 Codex R1-#2）。
        "dropped_agents": [d[:_MAX_ID_CHARS] for d in dropped[:_MAX_DROPPED]],
        "capped": capped,
    }


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

    注意：草案是**部分**输入（用户还要补全），因此不做整对象 required 校验——
    只保证「留下的每个字段都合法」，不保证「字段齐全」。齐全性由人在创建页负责。
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
    # （预填是部分输入，不查齐全性）；失败即保守清空全部预填并记入 stripped（fail-closed，
    # 剥离方向即安全方向；人在创建页仍会补全并经 Runtime 对完整 schema 再校验一次）。
    if kept and not _partial_object_valid(schema, kept):
        stripped.extend(kept.keys())
        kept = {}
    return kept, _bounded_stripped(stripped)


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
