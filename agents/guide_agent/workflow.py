"""guide_agent workflow：interactive 型导引 Agent（M6，ADR-0012）。

ConversationService 每轮调用 `run(context)`（统一入口，interactive 型 context）：
1. 把包内 prompt.md（系统提示，唯一版本化来源）拼上**运行时从 Registry 生成的
   候选 Agent 清单**作为 system content；
2. 经 Model Gateway（profile=reasoning）发起对话，得到本轮 assistant 回复；
3. 若回复含推荐块（`<<RECOMMEND>>...<<END>>`），对其做**确定性校验**后才作为
   推荐（预填任务草案）返回。

LLM 边界（宪法铁律六 + §11.2）：LLM 只负责对话与**提议**，它说"推荐 X、预填 Y"
不构成结构真值——本文件确定性对账 Registry（agent_id 必须真实存在、非 disabled、
非 interactive、非导引自身）与目标 Agent 的 input_schema.json（逐字段校验，非法字段
剥离并如实记名），通过才算数。导引**绝不创建/签发任务**：推荐只是草案，人在 tasks
端点签发。上游失败/空内容一律诚实抛错，绝不伪造对话或推荐。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import validate

_RECO_START = "<<RECOMMEND>>"
_RECO_END = "<<END>>"
_SELF_ID = "guide_agent"


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
    # 带上 agent_id 让 model_calls 落库可归因到导引（反方 P3-3：interactive 路径可观测性）。
    result = model_gateway.chat(profile, chat_messages, agent_id=agent_config.get("id"))
    reply = result.get("content")
    if not isinstance(reply, str) or not reply.strip():
        raise ValueError("导引模型返回空内容，无法继续对话（诚实失败，不伪造对话）")

    assistant_message, raw_reco = _split_recommendation(reply)
    recommendation = _validate_recommendation(raw_reco, registry, candidates) if raw_reco else None
    return {"assistant_message": assistant_message, "recommendation": recommendation}


# ── 候选 Agent 清单（注入系统提示，供 LLM 选择/预填）─────────────────────

def _candidates(registry: Any) -> list[dict[str, Any]]:
    """可推荐面 = 非 disabled、非 interactive、非导引自身的 specialist Agent
    （与 create_task 门一致：可运行即可推荐，ADR-0012 决策 4/7）。"""
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
        return "## 当前可推荐的 Agent\n\n（平台暂无可推荐的 Agent，请如实告知用户。）"
    lines = ["## 当前可推荐的 Agent", ""]
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


# ── 推荐块解析 + 确定性校验（LLM 边界的咬合点）──────────────────────────

def _split_recommendation(reply: str) -> tuple[str, str | None]:
    """把 assistant 文本与推荐块拆开。无块 → (原文, None)；有块 → (块前文本, 块内 JSON 串)。
    块前文本（推荐理由）永远原样展示给用户，绝不因块存在而丢。"""
    start = reply.find(_RECO_START)
    if start == -1:
        return reply.strip(), None
    end = reply.find(_RECO_END, start)
    if end == -1:
        # 有起始无结束：块不完整，当作纯文本（不冒险解析半个 JSON）
        return reply.strip(), None
    message = reply[:start].strip()
    raw = reply[start + len(_RECO_START):end].strip()
    if not message:
        message = "已根据你的需求给出推荐草案，请在下方确认。"
    return message, raw


def _validate_recommendation(
    raw: str, registry: Any, candidates: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """对 LLM 提议做确定性对账；任一硬校验不过 → 返回 None（fail-closed，不外露非法推荐）。

    - agent_id 必须是候选清单里的真实 id（拦截幻觉 Agent / disabled / interactive / 自身）；
    - prefilled_inputs 逐字段过目标 input_schema：未声明字段或违反字段子 schema 的一律
      剥离，剥离项如实记入 stripped_fields，绝不把非法草案当合法预填交给用户。
    """
    try:
        proposed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(proposed, dict):
        return None

    agent_id = proposed.get("agent_id")
    candidate_map = {c["id"]: c for c in candidates}
    if not isinstance(agent_id, str) or agent_id not in candidate_map:
        return None  # 幻觉/非法/不可推荐的 agent_id，整个推荐作废

    target = candidate_map[agent_id]
    rationale = proposed.get("rationale")
    rationale = rationale if isinstance(rationale, str) else ""

    raw_inputs = proposed.get("prefilled_inputs")
    raw_inputs = raw_inputs if isinstance(raw_inputs, dict) else {}
    prefilled, stripped = _clean_prefilled_inputs(registry, agent_id, raw_inputs)

    return {
        "agent_id": agent_id,
        "agent_name": target["name"],
        "category": target["category"],
        "status": target["status"],
        "maturity": target["maturity"],
        "rationale": rationale,
        "prefilled_inputs": prefilled,
        "stripped_fields": stripped,
    }


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
