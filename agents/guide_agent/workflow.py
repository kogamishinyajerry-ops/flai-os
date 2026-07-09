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

import json
from pathlib import Path
from typing import Any

from jsonschema import validate

_PLAN_START = "<<PLAN>>"
_PLAN_END = "<<END>>"
_SELF_ID = "guide_agent"

_MAX_PLAN_AGENTS = 5          # 单份计划召集 Agent 数上限（超出截断并记 capped）
_MAX_TEXT_CHARS = 2_000      # 单个自由文本字段上限（analysis/goal/reason/role…）
_MAX_LIST_ITEMS = 8          # residual_problems / reframe 列表条数上限


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
    result = model_gateway.chat(profile, chat_messages)
    reply = result.get("content")
    if not isinstance(reply, str) or not reply.strip():
        raise ValueError("导引模型返回空内容，无法继续对话（诚实失败，不伪造对话）")

    assistant_message, raw_plan = _split_plan(reply)
    plan = _validate_plan(raw_plan, registry, candidates) if raw_plan else None
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
        # 有起始无结束：块不完整，当作纯文本（不冒险解析半个 JSON）
        return reply.strip(), None
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
        proposed = json.loads(raw)
    except json.JSONDecodeError:
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
    for entry in raw_agents:
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

    return {
        "decision": "orchestrate",
        "analysis": _text(proposed.get("analysis")),
        "goal": _text(proposed.get("goal")),
        "workflow": _text(proposed.get("workflow")),
        "agents": agents,
        "dropped_agents": dropped,
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
        # 目标无结构化字段（如 file_upload/none 型）：不接受任何预填字段
        return {}, sorted(raw_inputs.keys())

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
    return kept, sorted(stripped)


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
