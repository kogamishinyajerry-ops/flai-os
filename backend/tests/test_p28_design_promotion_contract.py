from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from backend.app.design_promotion.contracts import (
    PublishRequest,
    ReleaseDecisionRequest,
    ReleaseRequestCreate,
    SelectionRequest,
)


SHA_A = "a" * 64
SHA_B = "b" * 64


def _release_summary(*, candidate_decision_id: str) -> dict[str, object]:
    return {
        "candidate": {
            "task_id": "task_1",
            "candidate_id": "odc-" + "1" * 32,
            "asset_slot": "task_review_summary",
            "asset_sha256": SHA_B,
            "comparison_sha256": SHA_A,
            "candidate_approval": {
                "decision_id": candidate_decision_id,
                "username": "candidate_reviewer",
                "display_name": "Candidate Reviewer",
                "at": "2026-07-20T09:00:00Z",
            },
        },
        "target": {
            "target_id": "open_design_task_review_summary_v1",
            "relative_path": "frontend/src/assets/open-design/task-review-summary.png",
            "preimage": {"kind": "absent"},
            "postimage_sha256": SHA_B,
        },
    }


def _wire_errors(value: object) -> list[object]:
    schema = json.loads(
        (Path(__file__).parents[2] / "contracts/design-promotion.schema.json")
        .read_text(encoding="utf-8")
    )
    return list(Draft202012Validator(schema).iter_errors(value))


def test_mutation_contracts_reject_coerced_confirmation_and_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        PublishRequest.model_validate(
            {
                "request_id": "req_" + "1" * 32,
                "expected_release_package_sha256": SHA_A,
                "expected_target": {"kind": "present", "sha256": SHA_B},
                "confirm": "true",
            }
        )

    with pytest.raises(ValidationError):
        ReleaseRequestCreate.model_validate(
            {
                "request_id": "req_" + "2" * 32,
                "selection_id": "selection_" + "3" * 32,
                "expected_comparison_sha256": SHA_A,
                "expected_candidate_sha256": SHA_B,
                "expected_target": {"kind": "absent"},
                "target_path": "frontend/src/App.vue",
            }
        )


def test_candidate_and_release_decisions_keep_approve_reject_shapes_disjoint() -> None:
    with pytest.raises(ValidationError):
        SelectionRequest.model_validate(
            {
                "request_id": "req_" + "4" * 32,
                "action": "approve",
                "expected_comparison_sha256": SHA_A,
                "candidate_id": "odc-" + "5" * 32,
                "reason_code": "visual_mismatch",
                "comment": None,
            }
        )


def test_json_schema_matches_reason_and_nonblank_other_decision_rules() -> None:
    invalid = (
        {
            "request_id": "req_" + "7" * 32,
            "action": "approve",
            "expected_summary_sha256": SHA_A,
            "reason_code": "other",
            "comment": "because",
        },
        {
            "request_id": "req_" + "8" * 32,
            "action": "reject",
            "expected_summary_sha256": SHA_A,
            "reason_code": "other",
            "comment": "   ",
        },
        {
            "request_id": "req_" + "9" * 32,
            "action": "reject",
            "expected_comparison_sha256": SHA_A,
            "candidate_id": None,
            "reason_code": "other",
            "comment": None,
        },
    )
    assert all(_wire_errors(value) for value in invalid)

    valid = {
        "request_id": "req_" + "a" * 32,
        "action": "reject",
        "expected_summary_sha256": SHA_A,
        "reason_code": "other",
        "comment": "specific release concern",
    }
    assert _wire_errors(valid) == []

    with pytest.raises(ValidationError):
        ReleaseDecisionRequest.model_validate(
            {
                "request_id": "req_" + "6" * 32,
                "action": "reject",
                "expected_summary_sha256": SHA_A,
                "reason_code": "other",
                "comment": "   ",
            }
        )


def test_json_schema_requires_exact_nested_decision_attribution_ids() -> None:
    valid_summary = _release_summary(candidate_decision_id="decision_" + "2" * 32)
    release_request = {
        "schema_version": "flai-design-release-request/v1",
        "release_request_id": "release_" + "3" * 32,
        "selection_id": "selection_" + "4" * 32,
        "comparison_id": "comparison_" + "5" * 32,
        "state": "awaiting_release_approval",
        "summary": valid_summary,
        "summary_sha256": SHA_A,
        "requested_by": {"username": "requester", "display_name": "Requester"},
        "created_at": "2026-07-20T09:01:00Z",
    }
    release_decision = {
        "schema_version": "flai-design-release-decision/v1",
        "release_request_id": "release_" + "3" * 32,
        "state": "release_approved",
        "decision_id": "release_decision_" + "6" * 32,
        "action": "approve",
        "summary_sha256": SHA_A,
        "decided_by": {"username": "publisher", "display_name": "Publisher"},
        "reason_code": None,
        "comment": None,
        "created_at": "2026-07-20T09:02:00Z",
        "release_package": {
            "schema_version": "flai-design-release-package/v1",
            "release_package_sha256": SHA_B,
            "summary": valid_summary,
            "release_approval": {
                "decision_id": "release_decision_" + "6" * 32,
                "username": "publisher",
                "display_name": "Publisher",
                "at": "2026-07-20T09:02:00Z",
            },
        },
    }
    assert _wire_errors(release_request) == []
    assert _wire_errors(release_decision) == []

    invalid_candidate_attribution = json.loads(json.dumps(release_request))
    invalid_candidate_attribution["summary"]["candidate"]["candidate_approval"][
        "decision_id"
    ] = "decision_1"
    invalid_release_attribution = json.loads(json.dumps(release_decision))
    invalid_release_attribution["release_package"]["release_approval"][
        "decision_id"
    ] = "release_decision_1"

    assert _wire_errors(invalid_candidate_attribution)
    assert _wire_errors(invalid_release_attribution)
