from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError, validate


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "contracts" / "asset_candidate_event.schema.json"


def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _event(event_type: str) -> dict[str, Any]:
    event: dict[str, Any] = {
        "event_id": f"asset_candidate_event_{'1' * 32}",
        "candidate_id": f"asset_candidate_{'2' * 24}",
        "candidate_digest": f"sha256:{'3' * 64}",
        "bundle_digest": f"sha256:{'4' * 64}",
        "event_type": event_type,
        "from_state": "awaiting_human_review",
        "to_state": "accepted",
        "actor_source": "authenticated_session",
        "signer_display_name": "Test Engineer",
        "signer_user_id": 7,
        "signer_username": "test.engineer",
        "signer_session_hash": "5" * 64,
        "message": "Candidate revision accepted by its authenticated owner.",
        "payload": {},
        "created_at": "2026-08-02T12:00:00Z",
    }
    if event_type == "candidate_created":
        event.update(
            {
                "from_state": None,
                "to_state": "awaiting_human_review",
                "actor_source": "authenticated_task_owner",
                "signer_display_name": None,
                "signer_user_id": None,
                "signer_username": None,
                "signer_session_hash": None,
            }
        )
    elif event_type == "candidate_rejected":
        event["to_state"] = "rejected"
    elif event_type == "candidate_superseded":
        event.update(
            {
                "to_state": "superseded",
                "actor_source": "authenticated_task_owner",
                "signer_display_name": None,
                "signer_user_id": None,
                "signer_username": None,
                "signer_session_hash": None,
            }
        )
    return event


def test_asset_candidate_event_schema_is_valid_draft_2020_12() -> None:
    Draft202012Validator.check_schema(_schema())


@pytest.mark.parametrize(
    "event_type",
    [
        "candidate_created",
        "candidate_accepted",
        "candidate_rejected",
        "candidate_superseded",
    ],
)
def test_asset_candidate_event_contract_accepts_canonical_event(
    event_type: str,
) -> None:
    validate(_event(event_type), _schema())


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("from_state", "awaiting_human_review"),
        ("to_state", "accepted"),
        ("actor_source", "authenticated_session"),
        ("signer_display_name", "Test Engineer"),
        ("signer_user_id", 7),
        ("signer_username", "test.engineer"),
        ("signer_session_hash", "5" * 64),
    ],
)
def test_candidate_created_rejects_state_actor_or_signer_drift(
    field: str,
    invalid_value: Any,
) -> None:
    event = _event("candidate_created")
    event[field] = invalid_value

    with pytest.raises(ValidationError):
        validate(event, _schema())


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("from_state", None),
        ("to_state", "accepted"),
        ("actor_source", "authenticated_session"),
        ("signer_display_name", "Test Engineer"),
        ("signer_user_id", 7),
        ("signer_username", "test.engineer"),
        ("signer_session_hash", "5" * 64),
    ],
)
def test_candidate_superseded_rejects_state_actor_or_signer_drift(
    field: str,
    invalid_value: Any,
) -> None:
    event = _event("candidate_superseded")
    event[field] = invalid_value

    with pytest.raises(ValidationError):
        validate(event, _schema())


@pytest.mark.parametrize(
    ("event_type", "expected_to_state"),
    [
        ("candidate_accepted", "accepted"),
        ("candidate_rejected", "rejected"),
    ],
)
@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("from_state", None),
        ("to_state", "awaiting_human_review"),
        ("actor_source", "authenticated_task_owner"),
        ("signer_display_name", None),
        ("signer_user_id", None),
        ("signer_username", None),
        ("signer_session_hash", None),
    ],
)
def test_candidate_decision_rejects_state_actor_or_missing_signer(
    event_type: str,
    expected_to_state: str,
    field: str,
    invalid_value: Any,
) -> None:
    event = _event(event_type)
    assert event["to_state"] == expected_to_state
    event[field] = invalid_value

    with pytest.raises(ValidationError):
        validate(event, _schema())


@pytest.mark.parametrize(
    ("event_type", "other_terminal_state"),
    [
        ("candidate_accepted", "rejected"),
        ("candidate_rejected", "accepted"),
    ],
)
def test_candidate_decision_rejects_the_other_terminal_state(
    event_type: str,
    other_terminal_state: str,
) -> None:
    event = _event(event_type)
    event["to_state"] = other_terminal_state

    with pytest.raises(ValidationError):
        validate(event, _schema())
