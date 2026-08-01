from __future__ import annotations

from copy import deepcopy

import pytest

from backend.app.ontology.asset_builder import (
    AssetDraftBuilder,
    AssetDraftInputError,
    AssetDraftProjectionError,
    AssetDraftSourceError,
)


def _conversation() -> dict:
    return {
        "id": "conv_asset_001",
        "agent_id": "guide_agent",
        "status": "active",
        "messages": [
            {
                "id": "msg_001",
                "role": "user",
                "content": "核对这批稳态算例的入口边界，并形成复核清单。",
                "file_ids": ["file_boundaries"],
            },
            {
                "id": "msg_002",
                "role": "assistant",
                "content": "先核输入完整性，再核边界与证据位置。",
                "file_ids": [],
            },
        ],
    }


def _generalization() -> dict:
    return {
        "title": "稳态算例入口边界复核",
        "trigger": "收到一批待计算的稳态算例，需要在开算前核对入口边界",
        "desired_outcome": "形成可逐项签认的入口边界复核清单",
        "inputs": ["算例清单", "入口边界条件表"],
        "outputs": ["入口边界复核清单"],
        "steps": [
            "逐项核对入口总压、总温与工况标识",
            "记录缺失、冲突和需要工程师裁决的边界",
        ],
        "evidence_requirements": ["每项结论保留原始表格位置"],
        "human_decision_points": ["冲突边界由责任工程师确认采用值"],
        "limitations": ["不适用于瞬态工况或未冻结的边界版本"],
    }


def test_preview_is_deterministic_and_only_ready_for_human_review() -> None:
    builder = AssetDraftBuilder()

    first = builder.preview(
        conversation=_conversation(), generalization=_generalization()
    )
    second = builder.preview(
        conversation=deepcopy(_conversation()),
        generalization=dict(reversed(list(_generalization().items()))),
    )

    assert first == second
    assert first["schema_version"] == "asset_draft_bundle.v1"
    assert first["status"] == "draft"
    assert first["validation"]["state"] == "ready_for_human_review"
    assert first["review"] == {
        "required": True,
        "ready": True,
        "state": "awaiting_human_review",
        "decision_state": "not_recorded",
        "requirements": [
            "核对草稿是否忠实对应原始 Work Case",
            "核对步骤、输入输出与不适用边界是否真的可复用",
            "核对人工判断点与证据要求是否充分",
        ],
    }
    assert first["generation"] == {
        "kind": "deterministic_projection",
        "llm_used": False,
    }
    assert first["effects"] == {
        "writes_database": False,
        "executes_work": False,
        "registers_asset": False,
        "promotes_asset": False,
    }
    assert first["work_case"]["source_revision"].startswith("sha256:")
    assert first["task_pattern"]["derived_from_work_case_revision"] == first["work_case"][
        "source_revision"
    ]
    assert first["skill"]["operationalizes_task_pattern_digest"] == first[
        "task_pattern"
    ]["content_digest"]
    assert first["draft_digest"].startswith("sha256:")


def test_incomplete_semantics_return_stable_blockers_without_fake_review_state() -> None:
    result = AssetDraftBuilder().preview(
        conversation=_conversation(),
        generalization={
            "title": "",
            "trigger": "",
            "desired_outcome": "",
            "inputs": [],
            "outputs": [],
            "steps": ["只有一步"],
            "evidence_requirements": [],
            "human_decision_points": [],
            "limitations": [],
        },
    )

    assert result["status"] == "draft"
    assert result["validation"]["state"] == "needs_revision"
    assert result["validation"]["blocking_count"] == 9
    assert result["validation"]["warning_count"] == 0
    assert [issue["code"] for issue in result["validation"]["issues"]] == [
        "task_pattern.title.required",
        "task_pattern.trigger.required",
        "task_pattern.outcome.required",
        "task_pattern.inputs.required",
        "task_pattern.outputs.required",
        "skill.instructions.minimum",
        "skill.human_boundary.required",
        "skill.verification.required",
        "skill.when_not_to_use.required",
    ]
    assert result["review"]["ready"] is False
    assert result["review"]["state"] == "not_ready"
    assert result["review"]["decision_state"] == "not_recorded"


def test_duplicate_items_are_preserved_and_reported_as_warning() -> None:
    generalization = _generalization()
    generalization["inputs"] = ["入口边界表", " 入口边界表 "]

    result = AssetDraftBuilder().preview(
        conversation=_conversation(), generalization=generalization
    )

    assert result["task_pattern"]["inputs"] == ["入口边界表", "入口边界表"]
    assert result["validation"]["state"] == "ready_for_human_review"
    assert result["validation"]["warning_count"] == 1
    assert result["validation"]["issues"][0]["code"] == (
        "generalization.inputs.duplicate"
    )


def test_source_change_changes_lineage_and_bundle_digest() -> None:
    builder = AssetDraftBuilder()
    first = builder.preview(
        conversation=_conversation(), generalization=_generalization()
    )
    changed = _conversation()
    changed["messages"][0]["content"] += "请同时核对单位。"
    second = builder.preview(conversation=changed, generalization=_generalization())

    assert first["work_case"]["source_revision"] != second["work_case"][
        "source_revision"
    ]
    assert first["task_pattern"]["content_digest"] != second["task_pattern"][
        "content_digest"
    ]
    assert first["draft_digest"] != second["draft_digest"]


def test_invalid_source_and_unknown_generalization_fields_fail_closed() -> None:
    with pytest.raises(AssetDraftSourceError, match="没有已保存的用户消息"):
        AssetDraftBuilder().preview(
            conversation={**_conversation(), "messages": []},
            generalization=_generalization(),
        )

    malformed = _conversation()
    malformed["messages"] = ["not-an-object"]
    with pytest.raises(AssetDraftProjectionError, match="必须是对象"):
        AssetDraftBuilder().preview(
            conversation=malformed, generalization=_generalization()
        )

    with pytest.raises(AssetDraftInputError, match="未知字段"):
        AssetDraftBuilder().preview(
            conversation=_conversation(),
            generalization={**_generalization(), "approved": True},
        )

    with pytest.raises(AssetDraftInputError, match="字段名必须是字符串"):
        AssetDraftBuilder().preview(
            conversation=_conversation(),
            generalization={**_generalization(), 1: "invalid"},
        )

    missing = _generalization()
    del missing["limitations"]
    with pytest.raises(AssetDraftInputError, match="缺少字段.*limitations"):
        AssetDraftBuilder().preview(
            conversation=_conversation(),
            generalization=missing,
        )


def test_blank_list_items_are_structural_errors_not_fake_content() -> None:
    generalization = _generalization()
    generalization["evidence_requirements"] = ["   "]

    with pytest.raises(AssetDraftInputError, match="不得为空白"):
        AssetDraftBuilder().preview(
            conversation=_conversation(), generalization=generalization
        )


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("title", "字" * 161, "不得超过 160"),
        ("title", "标题" + (" " * 159), "不得超过 160"),
        ("trigger", "字" * 2001, "不得超过 2000"),
        ("inputs", [f"输入 {index}" for index in range(21)], "不得超过 20 项"),
        ("outputs", ["字" * 1001], "数组项不得超过 1000"),
        ("outputs", ["输出" + (" " * 999)], "数组项不得超过 1000"),
    ],
)
def test_public_builder_seam_enforces_size_limits(
    field: str, value, message: str
) -> None:
    generalization = _generalization()
    generalization[field] = value

    with pytest.raises(AssetDraftInputError, match=message):
        AssetDraftBuilder().preview(
            conversation=_conversation(), generalization=generalization
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_source_numbers_fail_closed(value: float) -> None:
    conversation = _conversation()
    conversation["messages"][1]["recommendation"] = {"score": value}

    with pytest.raises(AssetDraftProjectionError, match="有限数字"):
        AssetDraftBuilder().preview(
            conversation=conversation,
            generalization=_generalization(),
        )


@pytest.mark.parametrize(
    "mutation, message",
    [
        (lambda value: value.__setitem__("id", "x" * 129), "conversation.id"),
        (lambda value: value.__setitem__("status", "corrupt"), "status"),
        (
            lambda value: value["messages"][0].__setitem__("file_ids", ""),
            "file_ids",
        ),
        (
            lambda value: value["messages"][0].__setitem__("file_ids", False),
            "file_ids",
        ),
        (
            lambda value: value["messages"][0].__setitem__("content", "bad\ud800"),
            "Unicode",
        ),
    ],
)
def test_malformed_source_shape_fails_closed(mutation, message: str) -> None:
    conversation = _conversation()
    mutation(conversation)

    with pytest.raises(AssetDraftProjectionError, match=message):
        AssetDraftBuilder().preview(
            conversation=conversation,
            generalization=_generalization(),
        )
