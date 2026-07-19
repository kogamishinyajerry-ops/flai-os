"""P2.1 task live snapshot contract tests.

The public seam is ``GET /api/tasks/{id}/live-snapshot``.  Existing task and
event responses remain unchanged; the envelope adds a per-task monotonic
sequence and an exact anchor so clients can reject gaps and resnapshot.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, ValidationError
import pytest
from referencing import Registry, Resource

from conftest import TEST_USERNAME

from backend.app.storage import repos


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = REPO_ROOT / "contracts"


def _validator() -> Draft202012Validator:
    live_schema = json.loads((CONTRACTS / "task_live_snapshot.schema.json").read_text(encoding="utf-8"))
    resources = []
    for name in ("task.schema.json", "event.schema.json"):
        schema = json.loads((CONTRACTS / name).read_text(encoding="utf-8"))
        resources.append((schema["$id"], Resource.from_contents(schema)))
    return Draft202012Validator(live_schema, registry=Registry().with_resources(resources))


def _create_task(client: TestClient) -> str:
    response = client.post(
        "/api/tasks",
        json={"agent_id": "hello_agent", "inputs": {"name": "live snapshot"}},
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_live_snapshot_not_found_is_404(app_env) -> None:
    client, _ = app_env
    response = client.get("/api/tasks/task_missing/live-snapshot")
    assert response.status_code == 404


def test_live_snapshot_rejects_nonzero_sequence_without_exact_anchor(app_env) -> None:
    client, _ = app_env
    task_id = _create_task(client)

    response = client.get(
        f"/api/tasks/{task_id}/live-snapshot",
        params={"after_sequence": 1},
    )

    assert response.status_code == 422
    assert "anchor_event_id" in response.text


def test_live_snapshot_initial_and_incremental_sequences_are_contiguous(app_env) -> None:
    client, app = app_env
    task_id = _create_task(client)

    initial_response = client.get(f"/api/tasks/{task_id}/live-snapshot")
    assert initial_response.status_code == 200
    assert initial_response.headers["cache-control"] == "no-store"
    initial = initial_response.json()
    _validator().validate(initial)
    assert initial["schema_version"] == "task-live-snapshot/v1"
    assert initial["resync_required"] is False
    assert initial["base"] == {"sequence": 0, "event_id": None}
    assert initial["cursor"]["sequence"] == len(initial["events"])
    assert [item["sequence"] for item in initial["events"]] == list(
        range(1, initial["cursor"]["sequence"] + 1)
    )
    assert initial["cursor"]["event_id"] == initial["events"][-1]["event"]["event_id"]

    conn = app.state.conn_factory()
    try:
        appended = repos.append_event(
            conn,
            task_id=task_id,
            agent_id="hello_agent",
            event_type="agent_log",
            level="info",
            message="incremental witness",
            payload={"phase": "p2.1"},
        )
        conn.commit()
    finally:
        conn.close()

    incremental_response = client.get(
        f"/api/tasks/{task_id}/live-snapshot",
        params={
            "after_sequence": initial["cursor"]["sequence"],
            "anchor_event_id": initial["cursor"]["event_id"],
        },
    )
    assert incremental_response.status_code == 200
    incremental = incremental_response.json()
    _validator().validate(incremental)
    assert incremental["resync_required"] is False
    assert incremental["base"] == initial["cursor"]
    assert incremental["events"] == [
        {
            "sequence": initial["cursor"]["sequence"] + 1,
            "event": appended,
        }
    ]
    assert incremental["cursor"] == {
        "sequence": initial["cursor"]["sequence"] + 1,
        "event_id": appended["event_id"],
    }


def test_live_snapshot_wrong_anchor_forces_resnapshot_and_never_returns_delta(app_env) -> None:
    client, _ = app_env
    task_id = _create_task(client)
    initial = client.get(f"/api/tasks/{task_id}/live-snapshot").json()

    response = client.get(
        f"/api/tasks/{task_id}/live-snapshot",
        params={
            "after_sequence": initial["cursor"]["sequence"],
            "anchor_event_id": "evt_wrong_anchor",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["resync_required"] is True
    assert body["resync_reason"] == "anchor_mismatch"
    assert body["events"] == []
    assert body["cursor"] == initial["cursor"]


def test_live_snapshot_cursor_ahead_forces_resnapshot(app_env) -> None:
    client, _ = app_env
    task_id = _create_task(client)
    initial = client.get(f"/api/tasks/{task_id}/live-snapshot").json()

    response = client.get(
        f"/api/tasks/{task_id}/live-snapshot",
        params={
            "after_sequence": initial["cursor"]["sequence"] + 1,
            "anchor_event_id": initial["cursor"]["event_id"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["resync_required"] is True
    assert body["resync_reason"] == "cursor_ahead"
    assert body["events"] == []


def test_live_snapshot_accepts_a_contract_legal_long_event_anchor(app_env) -> None:
    client, app = app_env
    task_id = _create_task(client)
    long_event_id = "evt_" + ("x" * 180)
    conn = app.state.conn_factory()
    try:
        conn.execute(
            """
            INSERT INTO task_events
              (event_id, task_id, agent_id, event_type, level, message, payload_json, created_at)
            VALUES (?, ?, ?, 'agent_log', 'info', 'long anchor', '{}', ?)
            """,
            (long_event_id, task_id, "hello_agent", "2026-07-19T00:00:00+00:00"),
        )
        conn.commit()
    finally:
        conn.close()

    initial = client.get(f"/api/tasks/{task_id}/live-snapshot").json()
    assert initial["cursor"]["event_id"] == long_event_id
    response = client.get(
        f"/api/tasks/{task_id}/live-snapshot",
        params={
            "after_sequence": initial["cursor"]["sequence"],
            "anchor_event_id": long_event_id,
        },
    )
    assert response.status_code == 200
    assert response.json()["base"] == initial["cursor"]


def test_task_events_are_mechanically_append_only(app_env) -> None:
    client, app = app_env
    task_id = _create_task(client)
    event_id = client.get(f"/api/tasks/{task_id}/events").json()[0]["event_id"]
    conn = app.state.conn_factory()
    try:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute(
                "UPDATE task_events SET message = 'rewritten' WHERE event_id = ?",
                (event_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("DELETE FROM task_events WHERE event_id = ?", (event_id,))
        original = conn.execute(
            "SELECT id, task_id, agent_id, event_type, level, payload_json, created_at "
            "FROM task_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute(
                """
                INSERT OR REPLACE INTO task_events
                  (id, event_id, task_id, agent_id, event_type, level, message, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'rewritten by replace', ?, ?)
                """,
                (
                    original["id"], event_id, original["task_id"], original["agent_id"],
                    original["event_type"], original["level"], original["payload_json"],
                    original["created_at"],
                ),
            )
        assert conn.execute(
            "SELECT message FROM task_events WHERE event_id = ?", (event_id,)
        ).fetchone()[0] != "rewritten by replace"
    finally:
        conn.close()


def test_all_live_authority_reads_are_no_store(app_env) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        repos.create_conversation(
            conn,
            conversation_id="conv_live_authority",
            agent_id="hello_agent",
            created_by="测试用户",
            created_by_username=TEST_USERNAME,
        )
    finally:
        conn.close()

    for path in (
        "/api/tasks?limit=100",
        "/api/conversations/conv_live_authority",
        "/api/conversations/conv_live_authority/tasks",
    ):
        response = client.get(path)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"


def test_live_snapshot_does_not_change_existing_event_response_shape(app_env) -> None:
    client, _ = app_env
    task_id = _create_task(client)

    events = client.get(f"/api/tasks/{task_id}/events").json()

    assert isinstance(events, list)
    assert events
    assert "sequence" not in events[0]


def test_live_snapshot_sensitive_task_and_events_stay_redacted(app_env) -> None:
    client, app = app_env
    task_id = _create_task(client)
    conn = app.state.conn_factory()
    try:
        conn.execute(
            "UPDATE tasks SET data_classification = 'sensitive', error_message = ? WHERE id = ?",
            ("task secret", task_id),
        )
        repos.append_event(
            conn,
            task_id=task_id,
            agent_id="hello_agent",
            event_type="agent_log",
            level="info",
            message="event secret",
            payload={"secret": "event payload"},
        )
        conn.commit()
    finally:
        conn.close()

    response = client.get(f"/api/tasks/{task_id}/live-snapshot")
    assert response.status_code == 200
    body = response.json()
    _validator().validate(body)
    assert body["task"]["error_message"] is None
    assert body["task"]["content_withheld"] is True
    redacted = next(item["event"] for item in body["events"] if item["event"]["event_type"] == "agent_log")
    assert redacted["message"] is None
    assert redacted["payload"] is None
    assert redacted["content_withheld"] is True


def test_unredacted_event_cannot_smuggle_a_null_payload_through_live_contract(app_env) -> None:
    client, _ = app_env
    task_id = _create_task(client)
    body = client.get(f"/api/tasks/{task_id}/live-snapshot").json()
    forged = json.loads(json.dumps(body))
    forged["events"][0]["event"]["payload"] = None
    with pytest.raises(ValidationError):
        _validator().validate(forged)
