"""guide_agent workflow：interactive 型导引 Agent（M6 起，编排官化 M8/ADR-0012）。

ConversationService 每轮调用 `run(context)`（统一入口，interactive 型 context）：
1. 把包内 prompt.md（系统提示，唯一版本化来源）拼上**运行时从 Registry 生成的
   候选 Agent 清单**作为 system content；
2. 经 Model Gateway（profile=reasoning）发起对话，得到本轮 assistant 回复；
3. 若回复含计划块（`<<PLAN>>...<<END>>`），对其做**确定性校验**后才作为结构化
   计划返回。计划有两种裁决（decision）：
   - `orchestrate`：平台有合适 Agent。legacy 单节点保留 `agents[]`；多节点只有模型
     明确输出 `guide_dag.v1 + nodes` 时才按拓扑/版本/来源契约确定性规范化。
   - `refuse`：没有合适 Agent（甚至不值得为此建专用 Agent）。含拒绝理由、仍未
     解决的问题、以及如何重述/拆解才可接——**显式拒绝，不硬凑**。

LLM 边界（宪法铁律六 + §11.2）：LLM 只负责对话与**提议**，它说"召集 X、预填 Y"
不构成结构真值——本文件对 orchestrate 的**每个** Agent 确定性对账 Registry
（agent_id 必须真实存在、非 disabled、非 interactive、非导引自身）与目标
input_schema.json（逐字段校验，非法字段剥离并如实记名），任一 Agent 不过即剥离；
orchestrate 若无任何合法 Agent 存活 → 整份计划作废（fail-closed，不外露幻觉召集）。
导引 workflow **绝不创建或签发任务**。认证用户请求 safe_auto 时，平台后端另以
确定性 admission 物化满足白名单的单任务或 DAG；DAG 非叶只允许零模型确定性 Agent，
唯一叶强制人工 review，最终签发仍只能由人完成。
上游失败/空内容一律诚实抛错，绝不伪造对话或计划。
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

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


def _load_system_prompt() -> str:
    return Path(__file__).with_name("prompt.md").read_text(encoding="utf-8").strip()


def run(context: dict[str, Any]) -> dict[str, Any]:
    messages: list[dict[str, Any]] = context["messages"]
    model_gateway = context["model_gateway"]
    registry = context["agent_registry"]
    agent_config = context["agent_config"]
    profile = agent_config["model"]["profile"]  # =reasoning（以 agent.yaml 为准）

    eligible = context.get("safe_auto_agent_ids")
    safe_auto_agent_ids = (
        {item for item in eligible if isinstance(item, str)}
        if isinstance(eligible, (list, set, tuple, frozenset))
        else set()
    )
    candidates = _candidates(registry, safe_auto_agent_ids=safe_auto_agent_ids)
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

def _candidates(
    registry: Any, *, safe_auto_agent_ids: set[str] | None = None
) -> list[dict[str, Any]]:
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
                "version": agent.get("version", ""),
                "summary": agent.get("summary", ""),
                # 仅供模型优先选择；最终权威仍是 GuidePlanDispatch 在事务内复查。
                # 缺主体投影也 fail-closed 为不可；production 由 ConversationService
                # 注入，最终派发仍在事务内权威复查 manifest + 当前角色。
                "safe_auto": agent_id in (safe_auto_agent_ids or set()),
                "model_profile": (agent.get("model") or {}).get("profile"),
                "requires_human_review": (agent.get("workflow") or {}).get(
                    "requires_human_review"
                ),
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
    required = {name for name in schema.get("required", []) if isinstance(name, str)}
    return {
        name: (
            ("必填；" if name in required else "可选；")
            + str((spec or {}).get("description", ""))
        ).rstrip("；")
        for name, spec in props.items()
    }


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
            f"成熟度={c['maturity']}/{c['status']} "
            f"当前身份自动执行={'可' if c['safe_auto'] else '暂不可'} "
            f"模型={c['model_profile']} 人工审核={'是' if c['requires_human_review'] is True else '否'}"
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
    contract = proposed.get("contract")
    if contract is not None:
        if contract != "guide_dag.v1":
            return None
        return _validate_dag(proposed, registry, candidates)

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
                # 真实候选由 _candidates 固定带 version；纯函数/历史测试夹具若缺失
                # 则留空字符串，展示仍可用，而 safe_auto 的版本锁会 fail-closed。
                "agent_version": target.get("version", ""),
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
        # 审计列表收成有界：条数 ≤ _MAX_DROPPED、单条 ≤ _MAX_ID_CHARS（异源 Codex R1-#2）。
        "dropped_agents": [d[:_MAX_ID_CHARS] for d in dropped[:_MAX_DROPPED]],
        "capped": capped,
    }


def _validate_dag(
    proposed: dict[str, Any], registry: Any, candidates: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """只规范化模型明确给出的 guide_dag.v1；绝不从 legacy agents/workflow 猜边。"""
    raw_nodes = proposed.get("nodes")
    if not isinstance(raw_nodes, list) or not 1 <= len(raw_nodes) <= _MAX_PLAN_AGENTS:
        return None
    candidate_map = {candidate["id"]: candidate for candidate in candidates}
    nodes: list[dict[str, Any]] = []
    seen_nodes: set[str] = set()
    seen_agents: set[str] = set()
    referenced: set[str] = set()
    for entry in raw_nodes:
        if not isinstance(entry, dict):
            return None
        node_id = entry.get("node_id")
        agent_id = entry.get("agent_id")
        if (
            not isinstance(node_id, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", node_id) is None
            or node_id in seen_nodes
            or not isinstance(agent_id, str)
            or agent_id in seen_agents
            or agent_id not in candidate_map
        ):
            return None
        target = candidate_map[agent_id]
        if (
            target.get("safe_auto") is not True
            or entry.get("agent_version") != target.get("version")
        ):
            return None
        dependencies = entry.get("depends_on")
        if (
            not isinstance(dependencies, list)
            or any(not isinstance(dependency, str) for dependency in dependencies)
            or len(dependencies) != len(set(dependencies))
            or any(dependency not in seen_nodes for dependency in dependencies)
        ):
            return None
        artifact_binding = entry.get("artifact_binding")
        if (
            not isinstance(artifact_binding, dict)
            or set(artifact_binding) != {"mode", "from_nodes"}
        ):
            return None
        mode = artifact_binding.get("mode")
        from_nodes = artifact_binding.get("from_nodes")
        if (
            not isinstance(from_nodes, list)
            or any(not isinstance(source, str) for source in from_nodes)
            or len(from_nodes) != len(set(from_nodes))
            or not set(from_nodes).issubset(set(dependencies))
            or (
                mode == "none"
                and (bool(dependencies) or from_nodes != [])
            )
            or (
                mode == "all"
                and (not dependencies or from_nodes != dependencies)
            )
            or (
                mode == "selected"
                and (not dependencies or not from_nodes)
            )
            or mode not in {"none", "all", "selected"}
        ):
            return None
        attachment_binding = entry.get("attachment_binding")
        if (
            not isinstance(attachment_binding, dict)
            or set(attachment_binding) != {"mode"}
            or attachment_binding.get("mode") not in {"none", "current_turn"}
        ):
            return None
        raw_inputs = entry.get("prefilled_inputs")
        if not isinstance(raw_inputs, dict):
            return None
        prefilled, stripped = _clean_prefilled_inputs(registry, agent_id, raw_inputs)
        if stripped:
            return None
        nodes.append(
            {
                "node_id": node_id,
                "agent_id": agent_id,
                "agent_version": target["version"],
                "agent_name": target["name"],
                "category": target["category"],
                "status": target["status"],
                "maturity": target["maturity"],
                "role": _text(entry.get("role")),
                "rationale": _text(entry.get("rationale")),
                "prefilled_inputs": prefilled,
                "stripped_fields": [],
                "depends_on": dependencies,
                "artifact_binding": {
                    "mode": mode,
                    "from_nodes": from_nodes,
                },
                "attachment_binding": {"mode": attachment_binding["mode"]},
            }
        )
        referenced.update(dependencies)
        seen_nodes.add(node_id)
        seen_agents.add(agent_id)

    leaves = [node for node in nodes if node["node_id"] not in referenced]
    if len(leaves) != 1:
        return None
    leaf_id = leaves[0]["node_id"]
    for node in nodes:
        target = candidate_map[node["agent_id"]]
        if node["node_id"] == leaf_id:
            if target.get("requires_human_review") is not True:
                return None
        elif (
            target.get("model_profile") != "none"
            or target.get("requires_human_review") is not False
        ):
            return None

    return {
        "decision": "orchestrate",
        "contract": "guide_dag.v1",
        "analysis": _text(proposed.get("analysis")),
        "goal": _text(proposed.get("goal")),
        "workflow": _text(proposed.get("workflow")),
        "nodes": nodes,
        "dropped_agents": [],
        "capped": False,
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
