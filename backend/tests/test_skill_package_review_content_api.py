from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import ValidationError, validate

from backend.tests.conftest import TEST_PASSWORD, TEST_USERNAME, login, seed_user
from backend.tests.test_asset_candidates_api import (
    _create_candidate,
    _decision,
    _seed_task,
)


CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "contracts"
    / ("skill_package_review_content.schema.json")
)


def _accepted_package(client, app) -> dict:
    candidate = _create_candidate(client, _seed_task(app)).json()
    response = client.post(
        f"/api/asset-candidates/{candidate['id']}/decision",
        json=_decision(candidate),
    )
    assert response.status_code == 200
    return response.json()["skill_package"]


def test_review_content_api_returns_exact_contract_bound_package_bytes(
    app_env,
) -> None:
    client, app = app_env
    package = _accepted_package(client, app)

    response = client.get(f"/api/skill-packages/{package['id']}/review-content")

    assert response.status_code == 200
    body = response.json()
    validate(body, json.loads(CONTRACT.read_text(encoding="utf-8")))
    assert body["package_id"] == package["id"]
    assert body["package_digest"] == package["package_digest"]
    assert [item["path"] for item in body["files"]] == [
        "SKILL.md",
        "references/provenance.json",
        "references/skill-revision.json",
        "references/task-pattern-revision.json",
    ]
    assert body["files"][0]["text"].startswith("---\n")


def test_review_content_contract_locks_each_file_to_its_canonical_position(
    app_env,
) -> None:
    client, app = app_env
    package = _accepted_package(client, app)
    body = client.get(f"/api/skill-packages/{package['id']}/review-content").json()
    schema = json.loads(CONTRACT.read_text(encoding="utf-8"))

    body["files"][0], body["files"][1] = body["files"][1], body["files"][0]
    with pytest.raises(ValidationError):
        validate(body, schema)

    body = client.get(f"/api/skill-packages/{package['id']}/review-content").json()
    body["files"][1] = {
        "path": "SKILL.md",
        "text": "different bytes under a duplicate path",
    }
    with pytest.raises(ValidationError):
        validate(body, schema)


def test_review_content_api_hides_other_owners_before_disclosing_bytes(
    app_env,
) -> None:
    client, app = app_env
    package = _accepted_package(client, app)
    seed_user(
        app.state.db_path,
        username="review_content_intruder",
        display_name="无权复核者",
        password=TEST_PASSWORD,
    )
    client.post("/api/auth/logout")
    login(
        client,
        username="review_content_intruder",
        password=TEST_PASSWORD,
    )

    response = client.get(f"/api/skill-packages/{package['id']}/review-content")

    assert response.status_code == 404
    assert package["package_digest"] not in response.text
    assert TEST_USERNAME not in response.text
