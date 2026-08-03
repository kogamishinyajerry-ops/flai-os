from __future__ import annotations

import hashlib
import json
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from jsonschema import ValidationError, validate

from backend.app.runtime.package_snapshot import SNAPSHOT_CONTRACT
from backend.app.runtime.task_evidence import input_files_evidence
from backend.app.storage import repos
from backend.app.storage.db import init_db
from backend.tests.conftest import (
    TEST_DISPLAY_NAME,
    TEST_PASSWORD,
    TEST_USERNAME,
    login,
    seed_user,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "contracts"


def _schema(name: str) -> dict[str, Any]:
    return json.loads((CONTRACTS_DIR / name).read_text(encoding="utf-8"))


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _seed_task(
    app,
    *,
    agent_id: str = "hello_agent",
    task_name: str = "一次真实工程任务",
    task_inputs: dict[str, Any] | None = None,
    user_message: str = "SECRET_WORK_CASE：请完成一次真实工程任务。",
    message_file_ids: list[str] | None = None,
    task_input_file_ids: list[str] | None = None,
    status: str = "completed",
    classification: str | None = "internal",
    origin: str = "user",
    owner_username: str | None = TEST_USERNAME,
    with_package_digest: bool = True,
    package_digest: str | None = None,
    with_execution_event: bool = True,
    execution_package_digest: str | None = None,
    with_execution_input_binding: bool = True,
    with_completion_event: bool = True,
    with_conversation: bool = True,
    with_user_message: bool = True,
    with_refuse_boundary: bool = False,
    with_review_event: bool = True,
    existing_conversation_id: str | None = None,
    depends_on: list[str] | None = None,
    input_binding: dict[str, Any] | None = None,
    dependency_resolved_payload: dict[str, Any] | None = None,
    guide_batch_operation: dict[str, Any] | None = None,
) -> str:
    suffix = uuid.uuid4().hex
    task_id = f"task_asset_{suffix}"
    conversation_id = (
        existing_conversation_id
        if existing_conversation_id is not None
        else f"conv_asset_{suffix}"
        if with_conversation
        else None
    )
    snapshot = app.state.agent_registry.package_snapshot(agent_id)
    assert snapshot is not None
    manifest = snapshot.manifest
    metadata: dict[str, Any] = {}
    if with_package_digest:
        metadata["package_snapshot_digest"] = package_digest or snapshot.digest
    if guide_batch_operation is not None:
        metadata["guide_batch_operation"] = deepcopy(guide_batch_operation)

    conn = app.state.conn_factory()
    try:
        if conversation_id is not None and existing_conversation_id is None:
            repos.create_conversation(
                conn,
                conversation_id=conversation_id,
                agent_id="guide_agent",
                created_by=TEST_DISPLAY_NAME,
                created_by_username=owner_username,
            )
        if conversation_id is not None and with_user_message:
            repos.append_message(
                conn,
                conversation_id=conversation_id,
                role="user",
                content=user_message,
                file_ids=message_file_ids or [],
            )
            repos.append_message(
                conn,
                conversation_id=conversation_id,
                role="assistant",
                content="已形成可核对方案。",
                file_ids=[],
            )
            if with_refuse_boundary:
                repos.append_message(
                    conn,
                    conversation_id=conversation_id,
                    role="assistant",
                    content="当前请求不进入工程执行。",
                    recommendation={
                        "decision": "refuse",
                        "reason": "当前工作段已结束",
                    },
                )
                repos.append_message(
                    conn,
                    conversation_id=conversation_id,
                    role="user",
                    content="请处理一个新的工程目标。",
                    file_ids=[],
                )
                repos.append_message(
                    conn,
                    conversation_id=conversation_id,
                    role="assistant",
                    content="已形成新的可核对方案。",
                    file_ids=[],
                )

        repos.create_task(
            conn,
            task_id=task_id,
            agent_id=agent_id,
            agent_version=manifest["version"],
            name=task_name,
            created_by=TEST_DISPLAY_NAME,
            created_by_username=owner_username,
            inputs=task_inputs or {"name": "候选资产测试"},
            input_file_ids=task_input_file_ids or [],
            metadata=metadata,
            conversation_id=conversation_id,
            origin=origin,
            depends_on=depends_on,
            input_binding=input_binding,
        )
        if classification is not None:
            repos.set_task_data_classification(conn, task_id, classification)

        if status != "created":
            execution_evidence_digest: str | None = None
            repos.set_task_status(conn, task_id, "queued")
            repos.set_task_status(conn, task_id, "validating")
            if dependency_resolved_payload is not None:
                repos.append_event(
                    conn,
                    task_id=task_id,
                    agent_id=agent_id,
                    event_type="agent_log",
                    level="info",
                    message="依赖产物已解析",
                    payload=dependency_resolved_payload,
                )
            if with_execution_event:
                validation_payload: dict[str, Any] = {
                    "package_snapshot_contract": SNAPSHOT_CONTRACT,
                    "package_snapshot_digest": (
                        execution_package_digest or snapshot.digest
                    ),
                }
                if with_execution_input_binding:
                    execution_input_ids = task_input_file_ids or []
                    task_inputs_digest = _canonical_digest(
                        task_inputs or {"name": "候选资产测试"}
                    )
                    execution_input_files_digest = input_files_evidence(
                        conn, execution_input_ids
                    )["digest"]
                    execution_evidence_digest = _canonical_digest(
                        {
                            "package_snapshot_digest": (
                                execution_package_digest or snapshot.digest
                            ),
                            "task_inputs_digest": task_inputs_digest,
                            "input_file_ids": execution_input_ids,
                            "input_files_digest": execution_input_files_digest,
                        }
                    )
                    validation_payload["input_file_ids"] = execution_input_ids
                    validation_payload["input_files_digest"] = (
                        execution_input_files_digest
                    )
                    validation_payload["task_inputs_digest"] = task_inputs_digest
                    validation_payload["execution_evidence_digest"] = (
                        execution_evidence_digest
                    )
                repos.append_event(
                    conn,
                    task_id=task_id,
                    agent_id=agent_id,
                    event_type="validation_started",
                    level="info",
                    message="开始校验输入",
                    payload=validation_payload,
                )
            repos.set_task_status(conn, task_id, "running")
            requires_review = manifest["workflow"]["requires_human_review"] is True
            if requires_review:
                repos.append_event(
                    conn,
                    task_id=task_id,
                    agent_id=agent_id,
                    event_type="review_requested",
                    level="info",
                    message="请工程师复核",
                    payload={"execution_evidence_digest": execution_evidence_digest},
                )
                repos.set_task_status(conn, task_id, "waiting_review")
                if status == "completed":
                    if with_review_event:
                        repos.apply_human_review(
                            conn,
                            task_id,
                            action="approve",
                            reviewer=TEST_DISPLAY_NAME,
                            reviewer_username=TEST_USERNAME,
                            comment=None,
                        )
                    else:
                        # Deliberately reproduce a legacy/corrupt terminal row whose
                        # status says completed but whose human-signoff event is absent.
                        repos.set_task_status(conn, task_id, "completed")
            else:
                repos.set_task_status(conn, task_id, "analyzing")
                if status == "completed":
                    repos.set_task_status(conn, task_id, "completed")
                    if with_completion_event:
                        repos.append_event(
                            conn,
                            task_id=task_id,
                            agent_id=agent_id,
                            event_type="task_completed",
                            level="info",
                            message="任务执行完成",
                            payload={
                                "execution_evidence_digest": execution_evidence_digest
                            },
                        )
        return task_id
    finally:
        conn.close()


def _counts(app) -> tuple[int, int]:
    conn = app.state.conn_factory()
    try:
        return (
            conn.execute("SELECT COUNT(*) FROM asset_candidates").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM asset_candidate_events").fetchone()[0],
        )
    finally:
        conn.close()


def _create_candidate(client, task_id: str):
    return client.post(f"/api/tasks/{task_id}/asset-candidate")


def _decision(candidate: dict[str, Any], action: str = "accept") -> dict[str, Any]:
    return {
        "schema_version": "asset_candidate_decision_request.v1",
        "action": action,
        "expected_candidate_digest": candidate["candidate_digest"],
        "expected_bundle_digest": candidate["bundle_digest"],
    }


@pytest.mark.parametrize(
    "task_kwargs, expected_code",
    [
        ({"status": "created"}, "task_not_completed"),
        ({"origin": "eval"}, "task_origin_not_user"),
        ({"classification": "sensitive"}, "classification_not_eligible"),
        ({"classification": None}, "classification_not_eligible"),
        ({"owner_username": "another_engineer"}, "task_owner_mismatch"),
        ({"owner_username": None}, "task_owner_unverifiable"),
        ({"with_package_digest": False}, "package_digest_unverifiable"),
        ({"with_execution_event": False}, "package_execution_unverifiable"),
        ({"with_execution_input_binding": False}, "execution_input_lineage_drift"),
        ({"with_completion_event": False}, "task_completion_unverifiable"),
        (
            {"execution_package_digest": "f" * 64},
            "package_execution_digest_drift",
        ),
        (
            {"with_package_digest": True, "package_digest": "0" * 64},
            "package_digest_drift",
        ),
        ({"with_conversation": False}, "conversation_unverifiable"),
        ({"with_user_message": False}, "work_case_unverifiable"),
        (
            {"agent_id": "fta_agent", "with_review_event": False},
            "task_signoff_unverifiable",
        ),
    ],
)
def test_candidate_admission_gates_fail_closed_without_writes(
    app_env, task_kwargs: dict[str, Any], expected_code: str
) -> None:
    client, app = app_env
    task_id = _seed_task(app, **task_kwargs)
    before = _counts(app)

    response = _create_candidate(client, task_id)

    if expected_code in {
        "task_origin_not_user",
        "task_owner_mismatch",
        "task_owner_unverifiable",
    }:
        assert response.status_code == 404
        assert response.json() == {"detail": "资源不存在或不可访问"}
    else:
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == expected_code
    assert _counts(app) == before


def test_completed_task_forms_content_addressed_candidate_without_source_echo(
    app_env,
) -> None:
    client, app = app_env
    task_id = _seed_task(app)

    response = _create_candidate(client, task_id)

    assert response.status_code == 200
    body = response.json()
    validate(body, _schema("asset_candidate.schema.json"))
    validate(body["bundle"], _schema("asset_draft_bundle.schema.json"))
    assert body["source"]["task_id"] == task_id
    assert body["source"]["task_status"] == "completed"
    assert body["source"]["initiated_by_username"] == TEST_USERNAME
    assert body["lineage"]["task"]["initiated_by_username"] == TEST_USERNAME
    assert body["revision"] == 1
    assert body["supersedes_candidate_digest"] is None
    assert body["state"] == "awaiting_human_review"
    assert body["bundle"]["review"]["decision_state"] == "not_recorded"
    assert body["bundle"]["effects"]["writes_database"] is False
    assert body["effects"] == {
        "writes_candidate_store": True,
        "executes_work": False,
        "writes_package_files": False,
        "registers_asset": False,
        "promotes_asset": False,
    }
    assert body["asset_map"]["task_pattern"]["state"] == "candidate_revision"
    assert body["asset_map"]["skill"]["state"] == "candidate_revision"
    assert body["asset_map"]["workflow"]["state"] == "not_formed"
    assert body["asset_map"]["agent"]["state"] == "not_formed"
    assert (
        body["lineage"]["execution_snapshot"]["package_snapshot_digest"]
        == (body["source"]["agent_package_digest"])
    )
    assert (
        body["lineage"]["execution_snapshot"]["execution_evidence_digest"]
        == body["lineage"]["signoff"]["execution_evidence_digest"]
    )
    assert (
        body["lineage"]["execution_snapshot"]["task_inputs_digest"]
        == (body["lineage"]["task"]["inputs_digest"])
    )
    assert "SECRET_WORK_CASE" not in response.text
    assert _counts(app) == (1, 1)


def test_direct_input_attachment_must_come_from_current_user_work_segment(
    app_env,
) -> None:
    client, app = app_env
    file_id = f"file_segment_{uuid.uuid4().hex}"
    conn = app.state.conn_factory()
    try:
        repos.create_file(
            conn,
            file_id=file_id,
            kind="input",
            filename="segment.txt",
            path="/tmp/segment.txt",
            size_bytes=7,
            sha256="7" * 64,
            classification="internal",
            uploaded_by=TEST_DISPLAY_NAME,
            owner_username=TEST_USERNAME,
        )
    finally:
        conn.close()

    valid_task = _seed_task(
        app,
        message_file_ids=[file_id],
        task_input_file_ids=[file_id],
    )
    valid = _create_candidate(client, valid_task)
    assert valid.status_code == 200
    assert valid.json()["lineage"]["input_files"] == [
        {
            "file_id": file_id,
            "kind": "input",
            "sha256": "7" * 64,
            "size_bytes": 7,
            "classification": "internal",
            "source_kind": "work_segment_upload",
            "producer_task_id": None,
        }
    ]

    stray_task = _seed_task(app, task_input_file_ids=[file_id])
    before = _counts(app)
    stray = _create_candidate(client, stray_task)
    assert stray.status_code == 409
    assert stray.json()["detail"]["code"] == "work_segment_attachment_mismatch"
    assert _counts(app) == before


@pytest.mark.parametrize("file_owner", [None, "another_engineer"])
def test_direct_work_segment_upload_must_belong_to_task_owner(
    app_env, file_owner: str | None
) -> None:
    client, app = app_env
    file_id = f"file_owner_{uuid.uuid4().hex}"
    conn = app.state.conn_factory()
    try:
        repos.create_file(
            conn,
            file_id=file_id,
            kind="input",
            filename="owned-input.txt",
            path="/tmp/owned-input.txt",
            size_bytes=8,
            sha256="2" * 64,
            classification="internal",
            uploaded_by=TEST_DISPLAY_NAME,
            owner_username=file_owner,
        )
    finally:
        conn.close()
    task_id = _seed_task(
        app,
        message_file_ids=[file_id],
        task_input_file_ids=[file_id],
    )

    response = _create_candidate(client, task_id)

    assert response.status_code == 404
    assert response.json() == {"detail": "资源不存在或不可访问"}
    assert _counts(app) == (0, 0)


def test_attachment_before_guide_refusal_is_not_in_the_new_work_segment(
    app_env,
) -> None:
    client, app = app_env
    file_id = f"file_old_segment_{uuid.uuid4().hex}"
    conn = app.state.conn_factory()
    try:
        repos.create_file(
            conn,
            file_id=file_id,
            kind="input",
            filename="old-segment.txt",
            path="/tmp/old-segment.txt",
            size_bytes=5,
            sha256="5" * 64,
            classification="internal",
            uploaded_by=TEST_DISPLAY_NAME,
            owner_username=TEST_USERNAME,
        )
    finally:
        conn.close()
    task_id = _seed_task(
        app,
        message_file_ids=[file_id],
        task_input_file_ids=[file_id],
        with_refuse_boundary=True,
    )

    response = _create_candidate(client, task_id)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "work_segment_attachment_mismatch"
    assert _counts(app) == (0, 0)


@pytest.mark.parametrize(
    "prior_owner, prior_operation, current_operation",
    [
        (
            "another_engineer",
            {
                "operation_id": "reused_candidate_batch",
                "fingerprint": "a" * 64,
                "index": 0,
                "count": 2,
            },
            {
                "operation_id": "reused_candidate_batch",
                "fingerprint": "a" * 64,
                "index": 1,
                "count": 2,
            },
        ),
        (
            TEST_USERNAME,
            {
                "operation_id": "reused_candidate_batch",
                "fingerprint": "a" * 64,
                "index": 0,
                "count": 2,
            },
            {
                "operation_id": "reused_candidate_batch",
                "fingerprint": "b" * 64,
                "index": 1,
                "count": 2,
            },
        ),
        (
            TEST_USERNAME,
            {
                "operation_id": "reused_candidate_batch",
                "fingerprint": "a" * 64,
                "index": 0,
                "count": 2,
            },
            {
                "operation_id": "reused_candidate_batch",
                "fingerprint": "a" * 64,
                "index": 1,
                "count": 3,
            },
        ),
        (
            TEST_USERNAME,
            {
                "operation_id": "reused_candidate_batch",
                "fingerprint": "a" * 64,
                "index": 0,
                "count": 2,
            },
            {
                "operation_id": "reused_candidate_batch",
                "fingerprint": "a" * 64,
                "index": 0,
                "count": 2,
            },
        ),
        (
            TEST_USERNAME,
            {
                "operation_id": "reused_candidate_batch",
                "fingerprint": "a" * 64,
                "index": 0,
                "count": 2,
            },
            {
                "operation_id": "reused_candidate_batch",
                "fingerprint": "a" * 64,
                "index": 2,
                "count": 2,
            },
        ),
    ],
    ids=[
        "different-owner",
        "different-request-fingerprint",
        "different-count",
        "duplicate-index",
        "out-of-range-index",
    ],
)
def test_reused_operation_id_without_verified_batch_identity_remains_boundary(
    app_env,
    prior_owner: str,
    prior_operation: dict[str, Any],
    current_operation: dict[str, Any],
) -> None:
    client, app = app_env
    file_id = f"file_prior_batch_{uuid.uuid4().hex}"
    conn = app.state.conn_factory()
    try:
        repos.create_file(
            conn,
            file_id=file_id,
            kind="input",
            filename="prior-batch.txt",
            path="/tmp/prior-batch.txt",
            size_bytes=9,
            sha256="8" * 64,
            classification="internal",
            uploaded_by=TEST_DISPLAY_NAME,
            owner_username=TEST_USERNAME,
        )
    finally:
        conn.close()

    prior_task = _seed_task(
        app,
        user_message="第一项工作使用这个附件。",
        message_file_ids=[file_id],
        owner_username=prior_owner,
        guide_batch_operation=prior_operation,
    )
    conn = app.state.conn_factory()
    try:
        prior = repos.get_task(conn, prior_task)
        assert prior is not None
        conversation_id = prior["conversation_id"]
    finally:
        conn.close()
    current_task = _seed_task(
        app,
        user_message="这是后续独立工作，不再提供前一项附件。",
        task_input_file_ids=[file_id],
        existing_conversation_id=conversation_id,
        guide_batch_operation=current_operation,
    )

    response = _create_candidate(client, current_task)

    if prior_owner != TEST_USERNAME:
        assert response.status_code == 404
        assert response.json() == {"detail": "资源不存在或不可访问"}
    else:
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == (
            "work_segment_attachment_mismatch"
        )
    assert _counts(app) == (0, 0)


def test_verified_atomic_guide_batch_shares_pre_batch_work_segment(app_env) -> None:
    client, app = app_env
    file_id = f"file_verified_batch_{uuid.uuid4().hex}"
    conn = app.state.conn_factory()
    try:
        repos.create_file(
            conn,
            file_id=file_id,
            kind="input",
            filename="verified-batch.txt",
            path="/tmp/verified-batch.txt",
            size_bytes=10,
            sha256="9" * 64,
            classification="internal",
            uploaded_by=TEST_DISPLAY_NAME,
            owner_username=TEST_USERNAME,
        )
    finally:
        conn.close()
    operation_id = f"verified_candidate_batch_{uuid.uuid4().hex}"
    fingerprint = "c" * 64
    prior_task = _seed_task(
        app,
        user_message="这一个开工动作同时需要两项工作，共享这个附件。",
        message_file_ids=[file_id],
        guide_batch_operation={
            "operation_id": operation_id,
            "fingerprint": fingerprint,
            "index": 0,
            "count": 2,
        },
    )
    conn = app.state.conn_factory()
    try:
        prior = repos.get_task(conn, prior_task)
        assert prior is not None
        conversation_id = prior["conversation_id"]
    finally:
        conn.close()
    current_task = _seed_task(
        app,
        user_message="继续同一个原子开工动作的第二项工作。",
        task_input_file_ids=[file_id],
        existing_conversation_id=conversation_id,
        guide_batch_operation={
            "operation_id": operation_id,
            "fingerprint": fingerprint,
            "index": 1,
            "count": 2,
        },
    )

    response = _create_candidate(client, current_task)

    assert response.status_code == 200, response.text
    assert response.json()["lineage"]["input_files"][0]["file_id"] == file_id
    assert _counts(app) == (1, 1)


def test_execution_input_content_digest_rejects_file_ledger_drift(app_env) -> None:
    client, app = app_env
    file_id = f"file_execution_input_{uuid.uuid4().hex}"
    conn = app.state.conn_factory()
    try:
        repos.create_file(
            conn,
            file_id=file_id,
            kind="input",
            filename="execution-input.txt",
            path="/tmp/execution-input.txt",
            size_bytes=12,
            sha256="4" * 64,
            classification="internal",
            uploaded_by=TEST_DISPLAY_NAME,
            owner_username=TEST_USERNAME,
        )
    finally:
        conn.close()
    task_id = _seed_task(
        app,
        message_file_ids=[file_id],
        task_input_file_ids=[file_id],
    )
    candidate = _create_candidate(client, task_id).json()

    conn = app.state.conn_factory()
    try:
        conn.execute(
            "UPDATE files SET sha256 = ? WHERE id = ?",
            ("5" * 64, file_id),
        )
    finally:
        conn.close()

    restored = client.get(f"/api/tasks/{task_id}/asset-candidate")
    assert restored.status_code == 409
    assert restored.json()["detail"]["code"] == "execution_input_lineage_drift"
    decision = client.post(
        f"/api/asset-candidates/{candidate['id']}/decision",
        json=_decision(candidate),
    )
    assert decision.status_code == 409
    assert decision.json()["detail"]["code"] == "execution_input_lineage_drift"
    assert _counts(app) == (1, 1)


def test_execution_task_inputs_digest_rejects_mutable_task_row_drift(app_env) -> None:
    client, app = app_env
    task_id = _seed_task(app, task_inputs={"name": "执行时输入"})
    conn = app.state.conn_factory()
    try:
        conn.execute(
            "UPDATE tasks SET inputs_json = ? WHERE id = ?",
            (json.dumps({"name": "事后替换输入"}, ensure_ascii=False), task_id),
        )
    finally:
        conn.close()

    response = _create_candidate(client, task_id)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "execution_input_lineage_drift"
    assert _counts(app) == (0, 0)


@pytest.mark.parametrize(
    "event_type, field, mutation, expected_code",
    [
        (
            "validation_started",
            "task_inputs_digest",
            "remove",
            "execution_input_lineage_drift",
        ),
        (
            "validation_started",
            "execution_evidence_digest",
            "replace",
            "execution_input_lineage_drift",
        ),
        (
            "task_completed",
            "execution_evidence_digest",
            "remove",
            "task_completion_unverifiable",
        ),
        (
            "task_completed",
            "execution_evidence_digest",
            "replace",
            "task_completion_unverifiable",
        ),
    ],
)
def test_candidate_requires_one_execution_evidence_digest_through_signoff(
    app_env,
    event_type: str,
    field: str,
    mutation: str,
    expected_code: str,
) -> None:
    client, app = app_env
    task_id = _seed_task(app)
    conn = app.state.conn_factory()
    try:
        row = conn.execute(
            """
            SELECT id, payload_json FROM task_events
            WHERE task_id = ? AND event_type = ?
            """,
            (task_id, event_type),
        ).fetchone()
        assert row is not None
        payload = json.loads(row["payload_json"])
        if mutation == "remove":
            payload.pop(field, None)
        else:
            payload[field] = "sha256:" + "0" * 64
        conn.execute(
            "UPDATE task_events SET payload_json = ? WHERE id = ?",
            (json.dumps(payload, ensure_ascii=False), row["id"]),
        )
    finally:
        conn.close()

    response = _create_candidate(client, task_id)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == expected_code
    assert _counts(app) == (0, 0)


@pytest.mark.parametrize("mutation", ["remove", "replace"])
def test_human_signoff_must_bind_the_same_execution_evidence_digest(
    app_env, mutation: str
) -> None:
    client, app = app_env
    task_id = _seed_task(app, agent_id="fta_agent")
    conn = app.state.conn_factory()
    try:
        row = conn.execute(
            """
            SELECT id, payload_json FROM task_events
            WHERE task_id = ? AND event_type = 'review_approved'
            """,
            (task_id,),
        ).fetchone()
        assert row is not None
        payload = json.loads(row["payload_json"])
        if mutation == "remove":
            payload.pop("execution_evidence_digest", None)
        else:
            payload["execution_evidence_digest"] = "sha256:" + "1" * 64
        conn.execute(
            "UPDATE task_events SET payload_json = ? WHERE id = ?",
            (json.dumps(payload, ensure_ascii=False), row["id"]),
        )
    finally:
        conn.close()

    response = _create_candidate(client, task_id)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "task_signoff_unverifiable"
    assert _counts(app) == (0, 0)


def test_arbitrary_other_task_output_cannot_be_attached_as_candidate_input(
    app_env,
) -> None:
    client, app = app_env
    producer_task = _seed_task(app)
    file_id = f"file_other_output_{uuid.uuid4().hex}"
    conn = app.state.conn_factory()
    try:
        repos.create_file(
            conn,
            file_id=file_id,
            task_id=producer_task,
            kind="output",
            filename="other.json",
            path="/tmp/other.json",
            size_bytes=11,
            sha256="6" * 64,
            classification="internal",
        )
        repos.set_task_outputs(conn, producer_task, [file_id])
    finally:
        conn.close()
    target_task = _seed_task(app, task_input_file_ids=[file_id])

    response = _create_candidate(client, target_task)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == ("upstream_input_lineage_unverifiable")
    assert _counts(app) == (0, 0)


def test_declared_signed_same_conversation_upstream_output_is_valid_input(
    app_env,
) -> None:
    client, app = app_env
    producer_task = _seed_task(app, task_name="生成上游校核结果")
    conn = app.state.conn_factory()
    try:
        producer = repos.get_task(conn, producer_task)
        assert producer is not None
        conversation_id = producer["conversation_id"]
        file_id = f"file_upstream_output_{uuid.uuid4().hex}"
        repos.create_file(
            conn,
            file_id=file_id,
            task_id=producer_task,
            kind="output",
            filename="upstream.json",
            path="/tmp/upstream.json",
            size_bytes=13,
            sha256="3" * 64,
            classification="internal",
        )
        repos.set_task_outputs(conn, producer_task, [file_id])
    finally:
        conn.close()

    target_task = _seed_task(
        app,
        task_name="复用上游校核结果",
        user_message="请基于刚完成的校核结果继续处理。",
        task_input_file_ids=[file_id],
        existing_conversation_id=conversation_id,
        depends_on=[producer_task],
        input_binding={"from_tasks": [producer_task]},
        dependency_resolved_payload={
            "workflow_event_type": "dependency_resolved",
            "upstream_task_ids": [producer_task],
            "piped_file_count": 1,
            "piped_file_ids": [file_id],
        },
    )

    response = _create_candidate(client, target_task)

    assert response.status_code == 200
    assert response.json()["lineage"]["input_files"] == [
        {
            "file_id": file_id,
            "kind": "output",
            "sha256": "3" * 64,
            "size_bytes": 13,
            "classification": "internal",
            "source_kind": "upstream_task_output",
            "producer_task_id": producer_task,
        }
    ]


def test_generalization_is_task_specific_and_uses_work_segment_and_completion_evidence(
    app_env,
) -> None:
    client, app = app_env
    first_task = _seed_task(
        app,
        task_name="校核起落架载荷边界",
        user_message="SECRET_ALPHA：请校核这次起落架载荷边界。",
    )
    second_task = _seed_task(
        app,
        task_name="核对液压系统试验记录",
        user_message="SECRET_BETA：请核对这次液压系统试验记录。",
    )

    first = _create_candidate(client, first_task).json()
    second = _create_candidate(client, second_task).json()

    first_pattern = first["bundle"]["task_pattern"]
    second_pattern = second["bundle"]["task_pattern"]
    assert "校核起落架载荷边界" in first_pattern["title"]
    assert "核对液压系统试验记录" in second_pattern["title"]
    assert first_pattern["title"] != second_pattern["title"]
    assert first_pattern["trigger"] != second_pattern["trigger"]
    assert first_pattern["content_digest"] != second_pattern["content_digest"]
    assert any("工作段摘要" in item for item in first_pattern["evidence_requirements"])
    assert any(
        "task_completed" in item for item in first_pattern["evidence_requirements"]
    )
    assert first["lineage"]["signoff"]["event_id"]
    assert first["lineage"]["signoff"]["event_digest"]
    assert "SECRET_ALPHA" not in json.dumps(first, ensure_ascii=False)
    assert "SECRET_BETA" not in json.dumps(second, ensure_ascii=False)


def test_candidate_creation_is_idempotent_and_cold_read_is_authoritative(
    app_env,
) -> None:
    client, app = app_env
    task_id = _seed_task(app)

    first = _create_candidate(client, task_id)
    second = _create_candidate(client, task_id)
    restored = client.get(f"/api/tasks/{task_id}/asset-candidate")

    assert first.status_code == second.status_code == restored.status_code == 200
    assert first.json() == second.json() == restored.json()
    assert _counts(app) == (1, 1)


def test_changed_task_evidence_creates_new_immutable_candidate_revision(
    app_env,
) -> None:
    client, app = app_env
    task_id = _seed_task(app)
    first = _create_candidate(client, task_id).json()

    conn = app.state.conn_factory()
    try:
        file_id = f"file_revision_{uuid.uuid4().hex}"
        repos.create_file(
            conn,
            file_id=file_id,
            task_id=task_id,
            kind="output",
            filename="revision.json",
            path="/tmp/revision.json",
            size_bytes=9,
            sha256="8" * 64,
            classification="internal",
        )
        repos.set_task_outputs(conn, task_id, [file_id])
    finally:
        conn.close()

    second_response = _create_candidate(client, task_id)

    assert second_response.status_code == 200
    second = second_response.json()
    assert second["revision"] == 2
    assert second["supersedes_candidate_digest"] == first["candidate_digest"]
    assert second["id"] != first["id"]
    assert second["candidate_digest"] != first["candidate_digest"]
    assert client.get(f"/api/tasks/{task_id}/asset-candidate").json() == second
    assert _counts(app) == (2, 3)

    conn = app.state.conn_factory()
    try:
        repos.set_task_outputs(conn, task_id, [])
    finally:
        conn.close()

    third_response = _create_candidate(client, task_id)
    assert third_response.status_code == 200
    third = third_response.json()
    assert third["revision"] == 3
    assert third["supersedes_candidate_digest"] == second["candidate_digest"]
    assert third["id"] not in {first["id"], second["id"]}
    assert third["candidate_digest"] not in {
        first["candidate_digest"],
        second["candidate_digest"],
    }
    assert _counts(app) == (3, 5)

    old_decision = client.post(
        f"/api/asset-candidates/{first['id']}/decision",
        json=_decision(first),
    )
    assert old_decision.status_code == 409
    assert old_decision.json()["detail"]["code"] == "candidate_already_decided"


def test_cold_read_recomputes_stored_content_address_digests(app_env) -> None:
    client, app = app_env
    task_id = _seed_task(app)
    candidate = _create_candidate(client, task_id).json()

    conn = app.state.conn_factory()
    try:
        stored = conn.execute(
            "SELECT bundle_json FROM asset_candidates WHERE id = ?",
            (candidate["id"],),
        ).fetchone()
        bundle = json.loads(stored["bundle_json"])
        bundle["task_pattern"]["title"] = "被篡改但摘要未更新"
        conn.execute(
            "UPDATE asset_candidates SET bundle_json = ? WHERE id = ?",
            (json.dumps(bundle, ensure_ascii=False, sort_keys=True), candidate["id"]),
        )
    finally:
        conn.close()

    restored = client.get(f"/api/tasks/{task_id}/asset-candidate")
    assert restored.status_code == 503
    assert "被篡改" not in restored.text


def test_candidate_address_binds_proposal_provenance_and_rejects_tamper(
    app_env,
) -> None:
    client, app = app_env
    task_id = _seed_task(app)
    candidate = _create_candidate(client, task_id).json()

    def digest(value: Any) -> str:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"

    proposal_digest = digest(candidate["proposal_provenance"])
    assert candidate["candidate_digest"] == digest(
        {
            "schema_version": "asset_candidate.v1",
            "revision": candidate["revision"],
            "supersedes_candidate_digest": candidate["supersedes_candidate_digest"],
            "bundle_digest": candidate["bundle_digest"],
            "lineage_digest": candidate["lineage_digest"],
            "proposal_provenance_digest": proposal_digest,
            "validation_policy_version": "asset_candidate_policy.v1",
        }
    )

    conn = app.state.conn_factory()
    try:
        tampered = deepcopy(candidate["proposal_provenance"])
        tampered["sources"] = list(reversed(tampered["sources"]))
        conn.execute(
            """
            UPDATE asset_candidates
            SET proposal_provenance_json = ?
            WHERE id = ?
            """,
            (json.dumps(tampered, ensure_ascii=False), candidate["id"]),
        )
    finally:
        conn.close()

    restored = client.get(f"/api/tasks/{task_id}/asset-candidate")
    assert restored.status_code == 503
    assert "signoff_evidence" not in restored.text


def test_cold_read_binds_revision_chain_into_candidate_digest(app_env) -> None:
    client, app = app_env
    task_id = _seed_task(app)
    candidate = _create_candidate(client, task_id).json()

    conn = app.state.conn_factory()
    try:
        conn.execute(
            """
            UPDATE asset_candidates
            SET revision = 2, supersedes_candidate_digest = ?
            WHERE id = ?
            """,
            ("sha256:" + "9" * 64, candidate["id"]),
        )
    finally:
        conn.close()

    restored = client.get(f"/api/tasks/{task_id}/asset-candidate")
    assert restored.status_code == 503


@pytest.mark.parametrize(
    "tamper",
    ["cross-task-predecessor", "predecessor-digest", "missing-supersede-event"],
)
def test_cold_read_proves_exact_previous_revision_and_supersede_event(
    app_env, tamper: str
) -> None:
    client, app = app_env
    task_id = _seed_task(app)
    first = _create_candidate(client, task_id).json()
    conn = app.state.conn_factory()
    try:
        file_id = f"file_chain_{uuid.uuid4().hex}"
        repos.create_file(
            conn,
            file_id=file_id,
            task_id=task_id,
            kind="output",
            filename="chain.json",
            path="/tmp/chain.json",
            size_bytes=7,
            sha256="d" * 64,
            classification="internal",
        )
        repos.set_task_outputs(conn, task_id, [file_id])
    finally:
        conn.close()
    second = _create_candidate(client, task_id).json()
    assert second["revision"] == 2

    conn = app.state.conn_factory()
    try:
        if tamper == "cross-task-predecessor":
            other_task_id = _seed_task(app)
            conn.execute(
                "UPDATE asset_candidates SET source_task_id = ? WHERE id = ?",
                (other_task_id, first["id"]),
            )
        elif tamper == "predecessor-digest":
            conn.execute(
                "UPDATE asset_candidates SET candidate_digest = ? WHERE id = ?",
                ("sha256:" + "e" * 64, first["id"]),
            )
        else:
            predecessor = conn.execute(
                "SELECT decision_event_id FROM asset_candidates WHERE id = ?",
                (first["id"],),
            ).fetchone()
            assert predecessor is not None
            assert predecessor["decision_event_id"]
            conn.execute(
                "DELETE FROM asset_candidate_events WHERE event_id = ?",
                (predecessor["decision_event_id"],),
            )
    finally:
        conn.close()

    restored = client.get(f"/api/tasks/{task_id}/asset-candidate")
    assert restored.status_code == 503


@pytest.mark.parametrize("tamper", ["missing", "duplicate", "digest-drift"])
def test_cold_read_requires_one_exact_candidate_created_event(
    app_env, tamper: str
) -> None:
    client, app = app_env
    task_id = _seed_task(app)
    candidate = _create_candidate(client, task_id).json()

    conn = app.state.conn_factory()
    try:
        created = conn.execute(
            """
            SELECT * FROM asset_candidate_events
            WHERE candidate_id = ? AND event_type = 'candidate_created'
            """,
            (candidate["id"],),
        ).fetchone()
        assert created is not None
        if tamper == "missing":
            conn.execute(
                "DELETE FROM asset_candidate_events WHERE event_id = ?",
                (created["event_id"],),
            )
        elif tamper == "duplicate":
            conn.execute(
                """
                INSERT INTO asset_candidate_events (
                    event_id, candidate_id, candidate_digest, bundle_digest,
                    event_type, from_state, to_state, actor_source,
                    signer_display_name, signer_user_id, signer_username,
                    signer_session_hash, message, payload_json, created_at
                )
                SELECT ?, candidate_id, candidate_digest, bundle_digest,
                       event_type, from_state, to_state, actor_source,
                       signer_display_name, signer_user_id, signer_username,
                       signer_session_hash, message, payload_json, created_at
                FROM asset_candidate_events WHERE event_id = ?
                """,
                (f"asset_candidate_event_{uuid.uuid4().hex}", created["event_id"]),
            )
        else:
            conn.execute(
                """
                UPDATE asset_candidate_events SET candidate_digest = ?
                WHERE event_id = ?
                """,
                ("sha256:" + "f" * 64, created["event_id"]),
            )
    finally:
        conn.close()

    restored = client.get(f"/api/tasks/{task_id}/asset-candidate")
    assert restored.status_code == 503


def test_unknown_task_or_candidate_is_honest_and_authenticated(app_env) -> None:
    client, _app = app_env

    assert _create_candidate(client, "task_missing").status_code == 404
    assert client.get("/api/tasks/task_missing/asset-candidate").status_code == 404
    assert (
        client.post(
            "/api/asset-candidates/asset_candidate_missing/decision",
            json={
                "schema_version": "asset_candidate_decision_request.v1",
                "action": "accept",
                "expected_candidate_digest": "sha256:" + "1" * 64,
                "expected_bundle_digest": "sha256:" + "2" * 64,
            },
        ).status_code
        == 404
    )

    client.cookies.clear()
    assert _create_candidate(client, "task_missing").status_code == 401


def test_human_decision_binds_both_digests_and_exact_live_session(app_env) -> None:
    client, app = app_env
    task_id = _seed_task(app)
    candidate = _create_candidate(client, task_id).json()

    response = client.post(
        f"/api/asset-candidates/{candidate['id']}/decision",
        json=_decision(candidate),
    )

    assert response.status_code == 200
    accepted = response.json()
    validate(accepted, _schema("asset_candidate.schema.json"))
    assert accepted["state"] == "accepted"
    assert accepted["decision"] == {
        "action": "accept",
        "decided_by": TEST_DISPLAY_NAME,
        "decided_by_username": TEST_USERNAME,
        "signer_source": "authenticated_session",
        "signer_session_bound": True,
        "created_at": accepted["decision"]["created_at"],
    }
    assert "session_hash" not in response.text
    assert accepted["asset_map"]["skill"]["state"] == "approved_revision"
    assert accepted["asset_map"]["workflow"]["state"] == "not_formed"
    assert _counts(app) == (1, 2)


@pytest.mark.parametrize("tamper", ["stored-owner", "terminal-signer"])
def test_cold_read_rejects_owner_or_terminal_signer_drift(app_env, tamper: str) -> None:
    client, app = app_env
    task_id = _seed_task(app)
    candidate = _create_candidate(client, task_id).json()
    if tamper == "terminal-signer":
        accepted = client.post(
            f"/api/asset-candidates/{candidate['id']}/decision",
            json=_decision(candidate),
        )
        assert accepted.status_code == 200

    conn = app.state.conn_factory()
    try:
        if tamper == "stored-owner":
            # Emulate a database poisoned before the insert-once owner trigger
            # existed, then reinstall the current schema guard before the API
            # read.  Direct tampering on a current database is covered by the
            # dedicated immutability tests and must be rejected at SQLite.
            conn.execute(
                "DROP TRIGGER trg_asset_candidates_initiator_immutable"
            )
            conn.execute(
                """
                UPDATE asset_candidates SET initiated_by_username = ?
                WHERE id = ?
                """,
                ("another_engineer", candidate["id"]),
            )
        else:
            row = conn.execute(
                "SELECT decision_event_id FROM asset_candidates WHERE id = ?",
                (candidate["id"],),
            ).fetchone()
            assert row is not None and row["decision_event_id"]
            conn.execute(
                """
                UPDATE asset_candidate_events SET signer_username = ?
                WHERE event_id = ?
                """,
                ("another_engineer", row["decision_event_id"]),
            )
    finally:
        conn.close()
    if tamper == "stored-owner":
        init_db(app.state.db_path)

    restored = client.get(f"/api/tasks/{task_id}/asset-candidate")
    if tamper == "stored-owner":
        assert restored.status_code == 404
        assert restored.json() == {"detail": "资源不存在或不可访问"}
    else:
        assert restored.status_code == 503


def test_human_review_lineage_uses_stable_database_username(app_env) -> None:
    client, app = app_env
    task_id = _seed_task(app, agent_id="fta_agent")

    response = _create_candidate(client, task_id)

    assert response.status_code == 200
    signoff = response.json()["lineage"]["signoff"]
    assert signoff["kind"] == "human_review_approved"
    assert signoff["signer_username"] == TEST_USERNAME


def test_decision_revalidates_live_task_lineage_before_atomic_write(app_env) -> None:
    client, app = app_env
    task_id = _seed_task(app)
    candidate = _create_candidate(client, task_id).json()

    conn = app.state.conn_factory()
    try:
        file_id = f"file_drift_{uuid.uuid4().hex}"
        repos.create_file(
            conn,
            file_id=file_id,
            task_id=task_id,
            kind="output",
            filename="drift.txt",
            path="/tmp/drift.txt",
            size_bytes=5,
            sha256="9" * 64,
            classification="internal",
        )
        repos.set_task_outputs(conn, task_id, [file_id])
    finally:
        conn.close()

    response = client.post(
        f"/api/asset-candidates/{candidate['id']}/decision",
        json=_decision(candidate),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "candidate_source_drift"
    assert _counts(app) == (1, 1)
    restored = client.get(f"/api/tasks/{task_id}/asset-candidate")
    assert restored.status_code == 409
    assert restored.json()["detail"]["code"] == "candidate_source_drift"


def test_final_transaction_session_revalidation_rolls_back_decision(
    app_env, monkeypatch
) -> None:
    client, app = app_env
    task_id = _seed_task(app)
    candidate = _create_candidate(client, task_id).json()
    monkeypatch.setattr(
        "backend.app.ontology.asset_candidates.resolve_signer",
        lambda _conn, _context: None,
    )

    response = client.post(
        f"/api/asset-candidates/{candidate['id']}/decision",
        json=_decision(candidate),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "signer_session_unverifiable"
    assert _counts(app) == (1, 1)
    restored = client.get(f"/api/tasks/{task_id}/asset-candidate").json()
    assert restored["state"] == "awaiting_human_review"


@pytest.mark.parametrize(
    "digest_field", ["expected_candidate_digest", "expected_bundle_digest"]
)
def test_digest_drift_and_second_decision_are_atomic_conflicts(
    app_env, digest_field: str
) -> None:
    client, app = app_env
    task_id = _seed_task(app)
    candidate = _create_candidate(client, task_id).json()
    invalid = _decision(candidate)
    invalid[digest_field] = "sha256:" + "f" * 64

    drift = client.post(
        f"/api/asset-candidates/{candidate['id']}/decision", json=invalid
    )
    assert drift.status_code == 409
    assert drift.json()["detail"]["code"] == "candidate_digest_conflict"
    assert _counts(app) == (1, 1)

    accepted = client.post(
        f"/api/asset-candidates/{candidate['id']}/decision",
        json=_decision(candidate),
    )
    second = client.post(
        f"/api/asset-candidates/{candidate['id']}/decision",
        json=_decision(candidate, "reject"),
    )
    assert accepted.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "candidate_already_decided"
    assert _counts(app) == (1, 2)


def test_decision_contract_rejects_client_authority_fields(app_env) -> None:
    client, app = app_env
    task_id = _seed_task(app)
    candidate = _create_candidate(client, task_id).json()

    for forbidden in ("reviewer", "state", "signer_source", "registers_asset"):
        body = _decision(candidate)
        body[forbidden] = "forged"
        response = client.post(
            f"/api/asset-candidates/{candidate['id']}/decision", json=body
        )
        assert response.status_code == 422


def test_candidate_contract_locks_effects_and_decision_request_authority(
    app_env,
) -> None:
    client, app = app_env
    candidate = _create_candidate(client, _seed_task(app)).json()
    schema = _schema("asset_candidate.schema.json")
    validate(candidate, schema)

    for field in (
        "executes_work",
        "writes_package_files",
        "registers_asset",
        "promotes_asset",
    ):
        invalid = deepcopy(candidate)
        invalid["effects"][field] = True
        with pytest.raises(ValidationError):
            validate(invalid, schema)

    decision_schema = _schema("asset_candidate_decision_request.schema.json")
    validate(_decision(candidate), decision_schema)
    forged = _decision(candidate)
    forged["reviewer"] = TEST_DISPLAY_NAME
    with pytest.raises(ValidationError):
        validate(forged, decision_schema)


def test_feature_asset_map_is_owner_scoped_read_only_and_schema_valid(app_env) -> None:
    client, app = app_env
    candidate = _create_candidate(client, _seed_task(app)).json()
    accepted = client.post(
        f"/api/asset-candidates/{candidate['id']}/decision",
        json=_decision(candidate),
    )
    assert accepted.status_code == 200
    counts_before_read = _counts(app)

    response = client.get("/api/feature-asset-map")

    assert response.status_code == 200
    body = response.json()
    validate(body, _schema("feature_asset_map.schema.json"))
    assert body["source"] == {
        "kind": "owner_scoped_cold_projection",
        "owner_username": TEST_USERNAME,
        "owner_scoped": True,
        "read_only": True,
    }
    assert body["summary"]["capability_count"] == len(
        body["functionality"]["capabilities"]
    )
    assert body["summary"]["asset_candidate_count"] == 1
    assert body["summary"]["accepted_candidate_count"] == 1
    assert body["summary"]["skill_package_count"] == 1
    assert body["summary"]["approved_skill_package_count"] == 0
    assert body["assets"] == [
        {
            "candidate_id": accepted.json()["id"],
            "candidate_digest": accepted.json()["candidate_digest"],
            "revision": 1,
            "state": "accepted",
            "source": {
                "task_id": accepted.json()["source"]["task_id"],
                "conversation_id": accepted.json()["source"]["conversation_id"],
                "agent_id": accepted.json()["source"]["agent_id"],
                "finished_at": accepted.json()["source"]["finished_at"],
            },
            "task_pattern": {
                "title": accepted.json()["bundle"]["task_pattern"]["title"],
                **accepted.json()["asset_map"]["task_pattern"],
            },
            "skill": {
                "name": accepted.json()["bundle"]["skill"]["name"],
                "description": accepted.json()["bundle"]["skill"]["description"],
                **accepted.json()["asset_map"]["skill"],
            },
            "skill_package": {
                "id": accepted.json()["skill_package"]["id"],
                "name": accepted.json()["skill_package"]["name"],
                "version": accepted.json()["skill_package"]["version"],
                "package_digest": accepted.json()["skill_package"]["package_digest"],
                "state": "pending_review",
                "reuse_eligible": False,
            },
            "workflow": accepted.json()["asset_map"]["workflow"],
            "agent": accepted.json()["asset_map"]["agent"],
            "updated_at": accepted.json()["updated_at"],
        }
    ]
    assert body["effects"] == {
        "writes_database": False,
        "executes_work": False,
        "registers_asset": False,
        "promotes_asset": False,
    }
    missing_gate = deepcopy(body)
    del missing_gate["assets"][0]["workflow"]["gate"]
    with pytest.raises(ValidationError):
        validate(missing_gate, _schema("feature_asset_map.schema.json"))

    unknown_formation = deepcopy(body)
    unknown_formation["assets"][0]["workflow"]["state"] = "formed"
    with pytest.raises(ValidationError):
        validate(unknown_formation, _schema("feature_asset_map.schema.json"))

    forged_reuse = deepcopy(body)
    forged_reuse["assets"][0]["skill_package"]["reuse_eligible"] = True
    with pytest.raises(ValidationError):
        validate(forged_reuse, _schema("feature_asset_map.schema.json"))

    assert _counts(app) == counts_before_read
    assert "SECRET_WORK_CASE" not in response.text
    assert client.post("/api/feature-asset-map").status_code == 405

    other_username = "other_engineer"
    other_password = "Other-Engineer-Password-2026!"
    seed_user(
        app.state.db_path,
        username=other_username,
        display_name="另一位工程师",
        password=other_password,
    )
    login(client, username=other_username, password=other_password)
    other_map = client.get("/api/feature-asset-map")
    assert other_map.status_code == 200
    assert other_map.json()["source"]["owner_username"] == other_username
    assert other_map.json()["summary"]["asset_candidate_count"] == 0
    assert other_map.json()["assets"] == []
    assert candidate["candidate_digest"] not in other_map.text

    login(client, username=TEST_USERNAME, password=TEST_PASSWORD)
    restored = client.get("/api/feature-asset-map")
    assert restored.status_code == 200
    assert restored.json()["assets"][0]["candidate_id"] == candidate["id"]


def test_feature_asset_map_fails_closed_on_current_owner_attribution_drift(
    app_env,
) -> None:
    client, app = app_env
    candidate = _create_candidate(client, _seed_task(app)).json()
    conn = app.state.conn_factory()
    try:
        # Legacy-corruption seam: current databases reject this UPDATE before
        # the API layer, so temporarily remove and then reinstall the trigger.
        conn.execute("DROP TRIGGER trg_asset_candidates_initiator_immutable")
        conn.execute(
            "UPDATE asset_candidates SET initiated_by_username = ? WHERE id = ?",
            ("other_engineer", candidate["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    init_db(app.state.db_path)
    counts_before_read = _counts(app)

    response = client.get("/api/feature-asset-map")

    assert response.status_code == 503
    assert response.json() == {"detail": "功能/资产地图暂不可用"}
    assert candidate["candidate_digest"] not in response.text
    assert TEST_USERNAME not in response.text
    assert _counts(app) == counts_before_read


def test_feature_asset_map_does_not_filter_source_task_owner_drift(app_env) -> None:
    client, app = app_env
    owned_task_id = _seed_task(app)
    candidate = _create_candidate(client, owned_task_id).json()
    other_task_id = _seed_task(
        app,
        owner_username="other_engineer",
        task_name="另一责任人的任务",
        user_message="另一责任人的独立工作段。",
    )
    conn = app.state.conn_factory()
    try:
        conn.execute(
            "UPDATE asset_candidates SET source_task_id = ? WHERE id = ?",
            (other_task_id, candidate["id"]),
        )
        conn.commit()
    finally:
        conn.close()

    response = client.get("/api/feature-asset-map")

    assert response.status_code == 503
    assert response.json() == {"detail": "功能/资产地图暂不可用"}
    assert candidate["candidate_digest"] not in response.text


def test_feature_asset_map_pins_and_releases_one_read_snapshot(app_env) -> None:
    _client, app = app_env
    conn = app.state.conn_factory()
    statements: list[str] = []
    conn.set_trace_callback(statements.append)
    try:
        snapshot = app.state.feature_asset_map_catalog.snapshot(
            conn,
            username=TEST_USERNAME,
        )
        assert snapshot["source"]["read_only"] is True
        assert any(statement == "BEGIN" for statement in statements)
        assert statements[-1] == "ROLLBACK"
        assert conn.in_transaction is False
    finally:
        conn.close()


@pytest.mark.parametrize("failure_stage", ["connect", "close"])
def test_feature_asset_map_connection_lifecycle_fails_as_generic_503(
    app_env,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    client, app = app_env
    real_factory = app.state.conn_factory

    if failure_stage == "connect":
        def failing_factory():
            raise RuntimeError("private connection detail")

        monkeypatch.setattr(app.state, "conn_factory", failing_factory)
    else:
        class CloseFailure:
            def __init__(self, conn) -> None:
                self._conn = conn

            def __getattr__(self, name: str):
                return getattr(self._conn, name)

            def close(self) -> None:
                self._conn.close()
                raise RuntimeError("private close detail")

        monkeypatch.setattr(
            app.state,
            "conn_factory",
            lambda: CloseFailure(real_factory()),
        )

    response = client.get("/api/feature-asset-map")

    assert response.status_code == 503
    assert response.json() == {"detail": "功能/资产地图暂不可用"}
    assert "private" not in response.text


def test_feature_asset_map_rejects_asset_overflow_without_truncation(
    app_env,
    monkeypatch,
) -> None:
    client, _app = app_env

    def oversized_owner_assets(_conn, _owner_username, limit):
        assert limit == 101
        return [f"task_overflow_{index}" for index in range(101)]

    monkeypatch.setattr(
        "backend.app.ontology.feature_asset_map.candidate_store."
        "list_latest_task_ids_for_owner",
        oversized_owner_assets,
    )

    response = client.get("/api/feature-asset-map")

    assert response.status_code == 503
    assert response.json() == {"detail": "功能/资产地图暂不可用"}
