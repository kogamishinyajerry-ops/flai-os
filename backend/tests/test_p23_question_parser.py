"""P2.3 Guide structured clarification parser contract.

These tests deliberately exercise malformed model output before the persistence/API
slice exists.  A Question is an explicit, validated workflow object; ordinary prose
or ``recommendation is None`` must never be guessed into one.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_workflow():
    path = REPO_ROOT / "agents" / "guide_agent" / "workflow.py"
    spec = importlib.util.spec_from_file_location("guide_question_workflow", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _Gateway:
    def __init__(self, reply: str) -> None:
        self.reply = reply

    def chat(self, profile: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        return {"content": self.reply}


class _EmptyRegistry:
    def list(self) -> list[dict[str, Any]]:
        return []


def _question_reply(text: str, question: dict[str, Any]) -> str:
    return (
        f"{text}\n<<QUESTION>>\n"
        f"{json.dumps(question, ensure_ascii=False)}\n"
        "<<END_QUESTION>>"
    )


def _run(reply: str) -> dict[str, Any]:
    workflow = _load_workflow()
    return workflow.run(
        {
            "messages": [{"role": "user", "content": "请帮我分析"}],
            "model_gateway": _Gateway(reply),
            "agent_registry": _EmptyRegistry(),
            "agent_config": {"model": {"profile": "reasoning"}},
        }
    )


def test_single_choice_question_is_explicit_and_deterministically_normalized() -> None:
    result = _run(
        _question_reply(
            "先确认分析范围。",
            {
                "kind": "single_choice",
                "prompt": "这次先覆盖哪个系统？",
                "description": "可选最接近的一项，也可在界面中自定义回答。",
                "options": [
                    {"label": "供电系统", "description": "主电源与应急电源"},
                    {"label": "液压系统"},
                ],
            },
        )
    )

    assert result["assistant_message"] == "先确认分析范围。"
    assert result["recommendation"] is None
    assert result["question"] == {
        "kind": "single_choice",
        "prompt": "这次先覆盖哪个系统？",
        "description": "可选最接近的一项，也可在界面中自定义回答。",
        "options": [
            {"id": "option_1", "label": "供电系统", "description": "主电源与应急电源"},
            {"id": "option_2", "label": "液压系统", "description": None},
        ],
    }


def test_free_text_question_has_no_model_controlled_options() -> None:
    result = _run(
        _question_reply(
            "还缺一个验收条件。",
            {"kind": "free_text", "prompt": "请写明你希望如何验收结果。"},
        )
    )

    assert result["question"] == {
        "kind": "free_text",
        "prompt": "请写明你希望如何验收结果。",
        "description": None,
        "options": [],
    }


def test_plain_assistant_prose_is_never_guessed_into_a_question() -> None:
    result = _run("请问这个系统的关键组件有哪些？")
    assert result == {
        "assistant_message": "请问这个系统的关键组件有哪些？",
        "recommendation": None,
        "question": None,
    }


@pytest.mark.parametrize(
    "question",
    [
        {"kind": "unknown", "prompt": "选一个"},
        {"kind": "free_text", "prompt": " \n\t"},
        {"kind": "free_text", "prompt": "说明", "unexpected": True},
        {
            "kind": "free_text",
            "prompt": "说明",
            "options": [{"label": "不应存在"}, {"label": "也不应存在"}],
        },
        {
            "kind": "single_choice",
            "prompt": "选一个",
            "options": [{"label": "只有一个"}],
        },
        {
            "kind": "single_choice",
            "prompt": "选一个",
            "options": [{"label": "重复"}, {"label": " 重复 "}],
        },
        {
            "kind": "single_choice",
            "prompt": "选一个",
            "options": [{"label": "A", "id": "模型不得指定 id"}, {"label": "B"}],
        },
        {
            "kind": "single_choice",
            "prompt": "选一个",
            "options": [{"label": "A"}, {"label": "B"}] * 4,
        },
    ],
)
def test_explicit_malformed_question_fails_the_whole_round(question: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="结构化问题"):
        _run(_question_reply("需要补充信息。", question))


@pytest.mark.parametrize(
    "reply",
    [
        "正文\n<<QUESTION>>\n{\"kind\":\"free_text\",\"prompt\":\"缺尾标记\"}",
        "正文\n<<END_QUESTION>>",
        (
            "正文\n<<QUESTION>>\n{\"kind\":\"free_text\",\"prompt\":\"一\"}\n"
            "<<END_QUESTION>>\n<<QUESTION>>\n{\"kind\":\"free_text\",\"prompt\":\"二\"}\n"
            "<<END_QUESTION>>"
        ),
    ],
)
def test_incomplete_or_multiple_question_envelopes_fail_closed(reply: str) -> None:
    with pytest.raises(ValueError, match="结构化问题"):
        _run(reply)


def test_plan_and_question_cannot_coexist_in_one_model_reply() -> None:
    reply = (
        _question_reply(
            "不能同时追问和裁决。",
            {"kind": "free_text", "prompt": "请补充。"},
        )
        + "\n<<PLAN>>\n"
        + json.dumps(
            {
                "decision": "refuse",
                "reason": "无能力",
                "residual_problems": [],
                "reframe": [],
            },
            ensure_ascii=False,
        )
        + "\n<<END>>"
    )

    with pytest.raises(ValueError, match="同时"):
        _run(reply)


@pytest.mark.parametrize(
    "reply",
    [
        "正文\n<<PLAN>>\n{}",
        "正文\n<<END>>",
        "正文\n<<END>>\n{}\n<<PLAN>>",
        "正文\n<<PLAN>>\n{}\n<<PLAN>>\n{}\n<<END>>",
        "正文\n<<PLAN>>\n{}\n<<END>>\n<<END>>",
        "正文\n<<PLAN>>\n{}\n<<END>>\n<<PLAN>>\n{}\n<<END>>",
    ],
)
def test_any_malformed_or_duplicate_plan_envelope_fails_closed(reply: str) -> None:
    """PLAN sentinel 也是结构协议；不完整/重复时不得“只认第一个”。"""
    with pytest.raises(ValueError, match="结构化计划"):
        _run(reply)


@pytest.mark.parametrize(
    "reply",
    [
        # 两种完整 envelope 无论先后，都不能让任一 parser 先剥离后放行另一个。
        (
            "正文\n<<PLAN>>\n{\"decision\":\"refuse\"}\n<<END>>\n"
            "<<QUESTION>>\n{\"kind\":\"free_text\",\"prompt\":\"说明\"}\n"
            "<<END_QUESTION>>"
        ),
        (
            "正文\n<<QUESTION>>\n{\"kind\":\"free_text\",\"prompt\":\"说明\"}\n"
            "<<END_QUESTION>>\n<<PLAN>>\n{\"decision\":\"refuse\"}\n<<END>>"
        ),
        # 完整 Question 嵌在 PLAN 中。
        (
            "正文\n<<PLAN>>\n{\"decision\":\"refuse\",\"reason\":\""
            "<<QUESTION>> x <<END_QUESTION>>\"}\n<<END>>"
        ),
        # 完整 PLAN 嵌在 Question 中。
        (
            "正文\n<<QUESTION>>\n{\"kind\":\"free_text\",\"prompt\":\""
            "<<PLAN>> x <<END>>\"}\n<<END_QUESTION>>"
        ),
        # 交错 envelope：单独看计数完整，但拓扑非法。
        "正文\n<<PLAN>>\n<<QUESTION>>\n{}\n<<END>>\n<<END_QUESTION>>",
        # 即使另一家族只出现孤立 marker，也不得先解出一个“有效”结构。
        (
            "正文\n<<QUESTION>>\n{\"kind\":\"free_text\",\"prompt\":\"说明\"}\n"
            "<<END_QUESTION>>\n<<PLAN>>"
        ),
    ],
)
def test_plan_and_question_marker_families_anywhere_fail_before_splitting(reply: str) -> None:
    with pytest.raises(ValueError, match="同时"):
        _run(reply)


def test_one_well_formed_plan_envelope_still_parses_normally() -> None:
    result = _run(
        "请根据下方裁决继续。\n<<PLAN>>\n"
        + json.dumps(
            {
                "decision": "refuse",
                "reason": "当前没有对口能力",
                "residual_problems": [],
                "reframe": [],
            },
            ensure_ascii=False,
        )
        + "\n<<END>>"
    )

    assert result["assistant_message"] == "请根据下方裁决继续。"
    assert result["recommendation"]["decision"] == "refuse"
    assert result["question"] is None
