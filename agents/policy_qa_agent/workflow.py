"""policy_qa_agent interactive workflow。

交互运行时未注入 knowledge/tool 能力；本 workflow 只通过声明的模型画像组织
prompt.md 中的合成目录线索，并确定性校验结构化 recommendation。任何无法通过
output_schema.json 的模型结果都会降级为显式拒答，绝不把自由文本当已核依据。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from jsonschema import ValidationError, validate


def _load_text(name: str) -> str:
    return Path(__file__).with_name(name).read_text(encoding="utf-8").strip()


def _question(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user" and isinstance(message.get("content"), str):
            content = message["content"].strip()
            if content:
                return content[:1000]
    return "本轮制度问题"


# 合成目录白名单（Codex R1 P2 + R2 P2 收严）：prompt.md 的四条虚构文号是唯一
# 合法依据出处。schema 的 source_ref 只约束「任意字符串」——模型编造目录外
# 文号也能过 schema 校验。R2 收严：子串包含会被「REAL-2026-001 / 青岚质规
# 〔虚构2026〕014号」这类夹带通过（UI 会整串展示伪造前缀）——改为**规范化
# 精确匹配**：剥去尾部一段（…）注解后必须整串等于目录条目，越界 →
# ValueError → 整轮降级显式拒答。
_CATALOG = frozenset({
    "青岚质规〔虚构2026〕014号",
    "青岚保规〔虚构2026〕006号",
    "青岚人规〔虚构2026〕009号",
    "青岚流规〔虚构2026〕021号",
})

_TRAILING_ANNOTATION = re.compile(r"[（(][^（）()]*[）)]\s*$")


def _canonical_ref(ref: str) -> str:
    """剥去尾部一段括注（prompt 自带「（虚构…）」注解形态）后取整串。"""
    return _TRAILING_ANNOTATION.sub("", ref.strip()).strip()


def _enforce_catalog(payload: dict[str, Any]) -> None:
    for finding in payload.get("findings", []):
        for ev in finding.get("evidence", []):
            ref = ev.get("source_ref", "")
            if (_canonical_ref(ref) in _CATALOG) is False:
                raise ValueError(f"依据出处越出合成目录白名单：{ref!r}（未收录必拒答）")


def _parse_payload(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("模型回复中没有 JSON 对象")
    payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("结构化问答顶层必须是对象")
    schema = json.loads(_load_text("output_schema.json"))
    validate(payload, schema)
    _enforce_catalog(payload)
    return payload


# 拒答 reason 消毒（Codex R2 P2）：str(ValidationError) 会内嵌违规实例全文——
# 超长模型输出会让 reason 突破 output_schema 的长度上限，且把**被拒的模型
# 文本**原样持久化进会话（拒了又存=没拒干净）。只取首行并截断。
_REASON_MAX_CHARS = 300


def _sanitize_reason(reason: str) -> str:
    first_line = (reason or "").strip().splitlines()[0] if (reason or "").strip() else "未知原因"
    if len(first_line) > _REASON_MAX_CHARS:
        first_line = first_line[: _REASON_MAX_CHARS] + "…（已截断）"
    return first_line


def _refusal(question: str, reason: str) -> dict[str, Any]:
    answer = "本轮未形成可校验的制度依据结构，因此不提供制度结论。请按正式制度库或职能窗口复核。"
    payload = {
        "answer": answer,
        "findings": [],
        "refusals": [
            {
                "question": question,
                "reason": _sanitize_reason(reason),
                "suggestion": "请提供已收录的合成目录文号，或转正式制度库/对应职能窗口查询。",
            }
        ],
    }
    # 兜底自证（Codex R2 P2）：拒答 payload 本身必须过包内 output_schema——
    # ConversationService 不复验 recommendation，这里是最后一道门；不合格即
    # 诚实抛错（宁失败不落畸形拒答）。
    validate(payload, json.loads(_load_text("output_schema.json")))
    return payload


def run(context: dict[str, Any]) -> dict[str, Any]:
    messages: list[dict[str, Any]] = context["messages"]
    model_gateway = context["model_gateway"]
    agent_config = context["agent_config"]
    profile = agent_config["model"]["profile"]

    chat_messages = [{"role": "system", "content": _load_text("prompt.md")}, *messages]
    result = model_gateway.chat(profile, chat_messages)
    raw = result.get("content")
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("制度问答模型返回空内容，无法继续对话（诚实失败）")

    question = _question(messages)
    # finish_reason 白名单（Codex R2 P2，knowledge_qa/fault_history 同款口径）：
    # length 截断、content_filter 过滤等异常收尾即便 JSON 恰好可解析，也不得
    # 当完整结论展示——解析前先判，异常收尾直接降级拒答。非字符串同异常。
    _finish = result.get("finish_reason")
    if _finish is not None and (isinstance(_finish, str) is False or _finish != "stop"):
        payload = _refusal(question, f"模型输出未正常收尾（finish_reason={_finish!r}），不采信本轮结论")
    else:
        try:
            payload = _parse_payload(raw)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            payload = _refusal(question, f"模型输出未通过结构化依据契约：{exc}")

    return {"assistant_message": payload["answer"], "recommendation": payload}
