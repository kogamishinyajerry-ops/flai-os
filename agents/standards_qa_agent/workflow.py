"""standards_qa_agent interactive workflow。

交互运行时未注入 knowledge/tool 能力；本 workflow 只通过声明的模型画像组织
prompt.md 中的合成目录线索，并确定性校验结构化 recommendation。任何无法通过
output_schema.json 的模型结果都会降级为显式拒答，绝不把自由文本当标准依据。
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
    return "本轮标准问题"


# 合成目录白名单（Codex R1 P2 + R2 P2 收严）：prompt.md 的两条虚构条款 + 三条
# 虚构实例是唯一合法出处。schema 的 source_ref 接受任意字符串——模型编造目录
# 外条款号/实例号也能过校验。R2 收严：子串包含会被「GJB-XXX / QZ-AIR-SYN-210
# §5.4.2」这类夹带通过——改为规范化精确匹配（剥尾部（…）注解后整串必须等于
# 目录条目）；越界整轮降级拒答。另核「双源(条款+机型实例)」宣称：basis 写
# 双源但 evidence 未同时含两 kind = 假权威，同样拒。
_CLAUSE_CATALOG = frozenset({"QZ-AIR-SYN-210 §5.4.2", "QZ-AIR-SYN-330 §7.1.3"})
_CASE_CATALOG = frozenset({"TC-XR100-017", "TC-XR300-008", "TC-XL7-004"})

# 归一后的展示规范形（Codex retro P1）：命中即整串替换——保留 prompt 自带的
# 「（虚构…）」诚实注解，剔除模型夹带的任何自由注解文本。
_DISPLAY_FORM = {
    "QZ-AIR-SYN-210 §5.4.2": "QZ-AIR-SYN-210 §5.4.2（虚构条款）",
    "QZ-AIR-SYN-330 §7.1.3": "QZ-AIR-SYN-330 §7.1.3（虚构条款）",
    "TC-XR100-017": "TC-XR100-017（虚构 XR-100 实例）",
    "TC-XR300-008": "TC-XR300-008（虚构 XR-300 实例）",
    "TC-XL7-004": "TC-XL7-004（虚构 巡线-7 实例）",
}

_TRAILING_ANNOTATION = re.compile(r"[（(][^（）()]*[）)]\s*$")


def _canonical_ref(ref: str) -> str:
    return _TRAILING_ANNOTATION.sub("", ref.strip()).strip()


def _enforce_catalog(payload: dict[str, Any]) -> None:
    """越界拒 + 归一重写（Codex retro P1）：伪造注解「条目（真实依据 REAL-xxx）」
    不得随原串持久化上屏——命中后 source_ref 就地替换为规范展示形。"""
    for finding in payload.get("findings", []):
        kinds: set[str] = set()
        for ev in finding.get("evidence", []):
            kind = ev.get("kind")
            ref = ev.get("source_ref", "")
            if kind == "standard_clause":
                allowed = _CLAUSE_CATALOG
            elif kind == "type_case":
                allowed = _CASE_CATALOG
            else:
                allowed = frozenset()
            canonical = _canonical_ref(ref)
            if (canonical in allowed) is False:
                # 静态文案（Codex retro-R1 P2）：source_ref 是模型可控文本，不进
                # 异常消息（会经拒答 reason 持久化上屏）；kind 是 schema enum
                # 收过的封闭值，可报。
                raise ValueError(f"依据出处越出合成目录白名单（kind={kind!r}，原文不复读）")
            ev["source_ref"] = _DISPLAY_FORM[canonical]
            kinds.add(kind)
        basis = ((finding.get("confidence") or {}).get("basis")) or ""
        if basis == "双源(条款+机型实例)" and ({"standard_clause", "type_case"} <= kinds) is False:
            raise ValueError("宣称双源但 evidence 未同时含条款与机型实例（假权威）")


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


# 拒答 reason 消毒（Codex R2 P2 + retro P2 再紧）：ValidationError 首行以违规
# 实例 repr 开头，「首行+截断」仍泄前 300 字符——改用校验器元数据构造 reason，
# 绝不引用实例值；其余异常走首行截断兜底。
_REASON_MAX_CHARS = 300


def _sanitize_reason(reason: str) -> str:
    first_line = (reason or "").strip().splitlines()[0] if (reason or "").strip() else "未知原因"
    if len(first_line) > _REASON_MAX_CHARS:
        first_line = first_line[: _REASON_MAX_CHARS] + "…（已截断）"
    return first_line


def _contract_error_reason(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        path = "/".join(str(p) for p in exc.absolute_path) or "<根>"
        return f"模型输出未通过结构化依据契约：字段 {path} 违反 {exc.validator} 约束"
    return _sanitize_reason(f"模型输出未通过结构化依据契约：{exc}")


def _refusal(question: str, reason: str) -> dict[str, Any]:
    answer = "本轮未形成可校验的条款/实例依据结构，因此不提供专业标准结论。请转正式标准库或标准责任人复核。"
    payload = {
        "answer": answer,
        "findings": [],
        "refusals": [
            {
                "question": question,
                "reason": _sanitize_reason(reason),
                "suggestion": "请提供已收录的合成条款号/实例号，或转正式标准库与标准责任人查询。",
            }
        ],
    }
    # 兜底自证：拒答 payload 本身必须过包内 output_schema（最后一道门，
    # ConversationService 不复验 recommendation）。
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
        raise ValueError("标准问答模型返回空内容，无法继续对话（诚实失败）")

    question = _question(messages)
    # finish_reason 白名单（Codex R2 P2）：异常收尾即便可解析也降级拒答。
    _finish = result.get("finish_reason")
    if _finish is not None and (isinstance(_finish, str) is False or _finish != "stop"):
        payload = _refusal(question, f"模型输出未正常收尾（finish_reason={_finish!r}），不采信本轮结论")
    else:
        try:
            payload = _parse_payload(raw)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            payload = _refusal(question, _contract_error_reason(exc))

    return {"assistant_message": payload["answer"], "recommendation": payload}
