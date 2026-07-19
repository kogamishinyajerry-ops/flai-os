"""P2.3 public Question/Answer JSON contracts (invalid-first witnesses)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts"


def _schemas():
    answer = json.loads((CONTRACTS / "conversation_answer.schema.json").read_text(encoding="utf-8"))
    question = json.loads(
        (CONTRACTS / "conversation_question.schema.json").read_text(encoding="utf-8")
    )
    registry = Registry().with_resource(answer["$id"], Resource.from_contents(answer))
    return question, answer, registry


def _validators():
    question, answer, registry = _schemas()
    checker = FormatChecker()
    return (
        Draft202012Validator(question, registry=registry, format_checker=checker),
        Draft202012Validator(answer, format_checker=checker),
    )


def _answer() -> dict:
    return {
        "schema_version": "conversation-answer/v1",
        "question_id": "q_11111111111111111111111111111111",
        "question_revision": 1,
        "submission_id": "9f8868b8-ff36-498f-a716-a52d7231791b",
        "payload": {"kind": "option", "option_id": "option_1"},
        "answered_by_username": "alice",
        "answered_at": "2026-07-19T01:02:03+00:00",
        "answer_message_id": "msg_22222222222222222222222222222222",
        "response_message_id": "msg_33333333333333333333333333333333",
    }


def _question(*, kind: str = "single_choice", status: str = "pending") -> dict:
    options = (
        [
            {"id": "option_1", "label": "供电系统", "description": "主电源与应急电源"},
            {"id": "option_2", "label": "液压系统", "description": None},
        ]
        if kind == "single_choice"
        else []
    )
    return {
        "schema_version": "conversation-question/v1",
        "id": "q_11111111111111111111111111111111",
        "conversation_id": "conv_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "prompt_message_id": "msg_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "revision": 1,
        "kind": kind,
        "prompt": "这次先覆盖哪个系统？",
        "description": None,
        "options": options,
        "asked_to_username": "alice",
        "status": status,
        "created_at": "2026-07-19T00:00:00+00:00",
        "expires_at": "2026-07-20T00:00:00+00:00",
        "answer": _answer() if status == "answered" else None,
        "closed_at": "2026-07-19T01:02:03+00:00" if status == "answered" else None,
    }


def test_question_and_answer_schemas_are_valid_draft_2020_12() -> None:
    question, answer, _ = _schemas()
    Draft202012Validator.check_schema(question)
    Draft202012Validator.check_schema(answer)


def test_choice_free_text_and_answered_projections_validate() -> None:
    question_validator, answer_validator = _validators()
    question_validator.validate(_question())
    question_validator.validate(_question(kind="free_text"))
    answered = _question(status="answered")
    question_validator.validate(answered)
    answer_validator.validate(answered["answer"])


@pytest.mark.parametrize(
    "mutate",
    [
        lambda q: q.update({"unexpected": True}),
        lambda q: q.update({"kind": "approval"}),
        lambda q: q.update({"options": q["options"][:1]}),
        lambda q: q.update({"kind": "free_text"}),
        lambda q: q.update({"created_at": "not-a-date"}),
        lambda q: q.update({"status": "answered", "answer": None, "closed_at": None}),
        lambda q: q.update({"status": "pending", "closed_at": q["expires_at"]}),
        lambda q: q.update({"status": "expired", "answer": _answer(), "closed_at": q["expires_at"]}),
    ],
)
def test_question_schema_rejects_cross_state_and_shape_drift(mutate) -> None:
    question_validator, _ = _validators()
    candidate = copy.deepcopy(_question())
    mutate(candidate)
    with pytest.raises(ValidationError):
        question_validator.validate(candidate)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda a: a.update({"action": "approve"}),
        lambda a: a.update({"question_revision": 2}),
        lambda a: a.update({"answered_at": "yesterday"}),
        lambda a: a.update({"payload": {"kind": "option", "option_id": ""}}),
        lambda a: a.update({"payload": {"kind": "text", "text": ""}}),
        lambda a: a.update(
            {"payload": {"kind": "option", "option_id": "option_1", "text": "批准"}}
        ),
    ],
)
def test_answer_schema_rejects_review_fields_and_ambiguous_payloads(mutate) -> None:
    _, answer_validator = _validators()
    candidate = copy.deepcopy(_answer())
    mutate(candidate)
    with pytest.raises(ValidationError):
        answer_validator.validate(candidate)
