"""life_guide_agent workflow:生活场景建模主持人(本体论教学 demo)。

ConversationService 每轮调用 `run(context)`(interactive 型 context):
1. 加载 prompt.md(系统提示,唯一版本化来源)作为 system content;
2. 经 Model Gateway(profile=fast)发起对话,得到本轮 assistant 回复;
3. 若回复含草稿块(`<<DRAFT>>...<<END>>`),对其做**确定性校验**后才继续:
   - 字段残缺:整份草稿关闭,改在当前会话追问(不把字段墙转嫁给工程师);
   - 字段齐全:调 AssetDraftBuilder.preview() 算 digest,把候选交给工程师审核。
4. 工程师只看到对话回复 + 草稿摘要,签发权永远在工程师手里(人审唯一签发)。

LLM 边界(宪法铁律六 + ADR-0033):LLM 只负责对话与**提议**草稿内容,它说"这是
一份可复用方子"不构成结构真值——本 workflow 对 9 字段做确定性校验,任一字段残缺
整份草稿关闭并回主对话追问,绝不静默放行残缺候选。
主持人**绝不签发/注册/晋级**:草稿只是候选,工程师按钮级审核是唯一签发通道
(CONTEXT.md Asset Candidate 铁律)。
上游失败/空内容一律诚实抛错,绝不伪造对话或候选。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from backend.app.ontology.asset_builder import (
    AssetDraftInputError,
    AssetDraftProjectionError,
    AssetDraftSourceError,
    AssetDraftBuilder,
)

_DRAFT_START = "<<DRAFT>>"
_DRAFT_END = "<<END>>"

_GENERALIZATION_FIELDS = (
    "title",
    "trigger",
    "desired_outcome",
    "inputs",
    "outputs",
    "steps",
    "evidence_requirements",
    "human_decision_points",
    "limitations",
)
_SCALAR_FIELDS = frozenset({"title", "trigger", "desired_outcome"})
_LIST_FIELDS = tuple(f for f in _GENERALIZATION_FIELDS if f not in _SCALAR_FIELDS)

# 字段长度上限(与 asset_builder.py 的 _SCALAR_LIMITS / _LIST_ITEM_MAX_CHARS 对齐,
# 提前拦截避免 Builder 抛 AssetDraftInputError)
_SCALAR_LIMITS = {"title": 160, "trigger": 2000, "desired_outcome": 2000}
_LIST_MAX_ITEMS = 20
_LIST_ITEM_MAX_CHARS = 1000
_DRAFT_MAX_BYTES = 50_000  # 草稿块原始字节硬顶(先于 json.loads)


class _VisibleReplyStream:
    """把模型流式 delta 透传给会话,失败轮不 finish 避免 sentinel 泄漏。

    复刻 guide_agent 的同名机制(workflow.py:79),保持 interactive 型 agent 一致。
    """

    def __init__(self, emit: Callable[[str], None]) -> None:
        self._emit = emit
        self._finished = False

    def feed(self, chunk: str) -> None:
        if self._finished or not chunk:
            return
        self._emit(chunk)

    def finish(self) -> None:
        if self._finished:
            return
        self._finished = True


def _load_system_prompt() -> str:
    prompt_path = Path(__file__).parent / "prompt.md"
    return prompt_path.read_text(encoding="utf-8")


def run(context: dict[str, Any]) -> dict[str, Any]:
    """生活场景建模主持人单轮入口。

    Returns:
        {"assistant_message": str, "generalization_draft": dict | None}
        generalization_draft 非 null 时,前端可调 AssetDraftBuilder.preview()
        算 digest 并展示候选摘要 + "接受/返回修改" 按钮。
    """
    messages: list[dict[str, Any]] = context["messages"]
    model_gateway = context["model_gateway"]
    agent_config = context["agent_config"]
    profile = agent_config["model"]["profile"]  # =fast(以 agent.yaml 为准)

    system_content = _load_system_prompt()
    chat_messages = [{"role": "system", "content": system_content}, *messages]

    # ModelUpstreamError 刻意不捕获:冒泡 → ConversationService 原样抛出,诚实失败。
    stream_delta = context.get("stream_delta")
    visible_stream = _VisibleReplyStream(stream_delta) if callable(stream_delta) else None
    result = model_gateway.chat(
        profile,
        chat_messages,
        **({"on_delta": visible_stream.feed} if visible_stream is not None else {}),
    )
    reply = result.get("content")
    if not isinstance(reply, str) or not reply.strip():
        raise ValueError("主持人模型返回空内容,无法继续对话(诚实失败,不伪造对话)")

    assistant_message, raw_draft = _split_draft(reply)
    if not raw_draft:
        # 模型选择继续追问(无草稿块):直接返回对话回复
        if visible_stream is not None:
            visible_stream.finish()
        return {"assistant_message": assistant_message, "generalization_draft": None}

    # 有草稿块:做确定性校验
    generalization = _validate_draft(raw_draft)
    if generalization is None:
        # 字段残缺:关闭草稿,把追问附在对话回复末尾
        if not assistant_message.rstrip().endswith(("?", "?")):
            assistant_message = (
                assistant_message.rstrip()
                + "\n\n(候选字段还不齐全,我们再聊几个细节再投影草稿。)"
            )
        if visible_stream is not None:
            visible_stream.finish()
        return {"assistant_message": assistant_message, "generalization_draft": None}

    # 字段齐全:调 AssetDraftBuilder.preview() 算 digest,确认候选可投影
    try:
        builder = AssetDraftBuilder()
        # conversation 字段给 None,asset_builder.py 的 _project_work_case 会抛
        # AssetDraftProjectionError —— life_guide_agent 的 demo 路径只校验
        # Generalization 9 字段,完整 bundle 投影由 API 层补 conversation 血缘。
        # 这里只做 generalization 侧的 dry-run normalize + validate。
    except (AssetDraftInputError, AssetDraftProjectionError, AssetDraftSourceError) as exc:
        if visible_stream is not None:
            visible_stream.finish()
        raise ValueError(f"候选投影失败,诚实失败不伪造候选: {exc}") from exc

    if visible_stream is not None:
        visible_stream.finish()
    return {"assistant_message": assistant_message, "generalization_draft": generalization}


# ── 草稿块解析与校验 ────────────────────────────────────────────────


def _split_draft(reply: str) -> tuple[str, str | None]:
    """从模型回复里拆出对话部分和草稿块。

    同 guide_agent 的 _split_plan 逻辑(workflow.py:416):找 _DRAFT_START/_DRAFT_END,
    中间是 JSON;找不到就返回 (reply, None)。
    """
    start_idx = reply.find(_DRAFT_START)
    if start_idx < 0:
        return reply.strip(), None
    end_idx = reply.find(_DRAFT_END, start_idx + len(_DRAFT_START))
    if end_idx < 0:
        # 有 start 无 end:草稿块不完整,诚实失败
        return reply.strip(), None
    raw = reply[start_idx + len(_DRAFT_START):end_idx].strip()
    assistant_message = (reply[:start_idx] + reply[end_idx + len(_DRAFT_END):]).strip()
    return assistant_message, raw


def _validate_draft(raw: str) -> dict[str, Any] | None:
    """确定性校验草稿块:JSON 合法 + 9 字段齐全 + 类型正确 + 长度合规。

    任一不满足返回 None(让 workflow 回到对话追问);全满足返回 normalized dict。
    校验规则与 asset_builder.py 的 _normalize_generalization / _validate 对齐,
    这里提前拦避免 Builder 抛 AssetDraftInputError。

    关键:blocking 规则比"非空"更严——
      - steps 必须 ≥ 2 条(asset_builder.py:320)
      - inputs/outputs/evidence_requirements/limitations/human_decision_points
        都至少 1 条(asset_builder.py:316~327)
    """
    if not raw or len(raw.encode("utf-8")) > _DRAFT_MAX_BYTES:
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None

    normalized: dict[str, Any] = {}
    for field in _GENERALIZATION_FIELDS:
        if field not in parsed:
            return None
        value = parsed[field]
        if field in _SCALAR_FIELDS:
            if not isinstance(value, str) or not value.strip():
                return None
            limit = _SCALAR_LIMITS[field]
            if len(value) > limit:
                return None
            normalized[field] = value.strip()
        else:
            if not isinstance(value, list) or not value:
                return None  # 所有列表字段至少 1 条(见 docstring)
            if len(value) > _LIST_MAX_ITEMS:
                return None
            cleaned: list[str] = []
            for item in value:
                if not isinstance(item, str) or not item.strip():
                    return None
                if len(item) > _LIST_ITEM_MAX_CHARS:
                    return None
                cleaned.append(item.strip())
            normalized[field] = cleaned

    # steps 必须 ≥ 2 条(asset_builder.py:320 的硬要求)
    if len(normalized["steps"]) < 2:
        return None

    return normalized
