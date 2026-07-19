"""P2.4 exact server-side addressing/search contracts.

Invalid inputs and authority boundaries are intentionally tested before the
happy path.  Search is a read-only navigation projection; it must never turn a
partial failure into an empty result or use display names as principals.
"""

from __future__ import annotations

import base64
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from conftest import login, seed_pre_p23_legacy_conversation, seed_user

from backend.app.main import create_app
from backend.app.storage import repos


REPO_ROOT = Path(__file__).resolve().parents[2]
SEARCH_SCHEMA = REPO_ROOT / "contracts" / "search-page.schema.json"
DISPLAY_NAME = "同名工程师"


@pytest.fixture()
def two_user_search_env(tmp_path: Path):
    db_path = tmp_path / "flai_os.db"
    app = create_app(
        agents_dir=REPO_ROOT / "agents",
        tools_dir=REPO_ROOT / "tools_impl",
        contracts_dir=REPO_ROOT / "contracts",
        db_path=db_path,
        uploads_dir=tmp_path / "uploads",
        task_runs_dir=tmp_path / "task_runs",
    )
    with TestClient(app) as alice:
        seed_user(
            db_path,
            username="alice",
            display_name=DISPLAY_NAME,
            password="alice-pass-123",
        )
        seed_user(
            db_path,
            username="bob",
            display_name=DISPLAY_NAME,
            password="bob-pass-123",
        )
        login(alice, username="alice", password="alice-pass-123")
        bob = TestClient(app)
        login(bob, username="bob", password="bob-pass-123")
        try:
            yield alice, bob, app
        finally:
            bob.close()


def _open_conversation(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/conversations", json={"agent_id": "guide_agent"})
    assert response.status_code == 200, response.text
    return response.json()


def _append_message(app: Any, conversation_id: str, content: str) -> dict[str, Any]:
    conn = app.state.conn_factory()
    try:
        return repos.append_message(
            conn,
            conversation_id=conversation_id,
            role="user",
            content=content,
        )
    finally:
        conn.close()


def _create_task(
    app: Any,
    *,
    task_id: str,
    username: str | None,
    name: str | None,
    inputs: dict[str, Any] | None = None,
    agent_id: str = "hello_agent",
    origin: str = "user",
    status: str = "created",
) -> dict[str, Any]:
    conn = app.state.conn_factory()
    try:
        task = repos.create_task(
            conn,
            task_id=task_id,
            agent_id=agent_id,
            agent_version="0.1.0",
            name=name,
            created_by=DISPLAY_NAME,
            created_by_username=username,
            inputs=inputs or {},
            origin=origin,
        )
        if status != "created":
            conn.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                (status, task["updated_at"], task_id),
            )
            task = repos.get_task(conn, task_id)
        return task
    finally:
        conn.close()


def _create_file(
    app: Any,
    *,
    file_id: str,
    task_id: str | None,
    kind: str,
    filename: str,
    classification: str = "internal",
) -> dict[str, Any]:
    conn = app.state.conn_factory()
    try:
        return repos.create_file(
            conn,
            file_id=file_id,
            task_id=task_id,
            kind=kind,
            filename=filename,
            path=f"/bounded-fixture/{file_id}",
            size_bytes=123,
            sha256="a" * 64,
            classification=classification,
        )
    finally:
        conn.close()


def _set_outputs(app: Any, task_id: str, file_ids: list[str]) -> None:
    conn = app.state.conn_factory()
    try:
        repos.set_task_outputs(conn, task_id, file_ids)
    finally:
        conn.close()


def _search(client: TestClient, **params: Any):
    return client.get("/api/search", params=params)


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"q": ""},
        {"q": "   "},
        {"q": "x"},
        {"q": "x" * 129},
        {"q": "ab\x00cd"},
        {"q": "ab\ncd"},
        {"q": "ab\x85cd", "scope": "message"},
        {"q": "valid", "scope": "unknown"},
        {"q": "valid", "limit": 0},
        {"q": "valid", "limit": 21},
        {"q": "valid", "limit": "true"},
        {"q": "valid", "scope": "message", "status": "running"},
        {"q": "valid", "owner": "bob"},
        {"q": "valid", "username": "bob"},
    ],
)
def test_invalid_search_inputs_fail_before_any_write(app_env, params: dict[str, Any]) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        before = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("tasks", "conversation_messages", "files", "task_events")
        }
    finally:
        conn.close()

    response = _search(client, **params)
    assert response.status_code == 422, response.text

    conn = app.state.conn_factory()
    try:
        after = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in before
        }
    finally:
        conn.close()
    assert after == before


def test_duplicate_scope_and_cursor_shape_are_rejected(app_env) -> None:
    client, _ = app_env
    duplicate = client.get(
        "/api/search",
        params=[("q", "valid"), ("scope", "message"), ("scope", "task")],
    )
    assert duplicate.status_code == 422
    assert _search(client, q="valid", scope="message", cursor="not-base64").status_code == 422


def test_message_search_uses_exact_username_not_duplicate_display_name(
    two_user_search_env,
) -> None:
    alice, bob, app = two_user_search_env
    alice_conv = _open_conversation(alice)
    bob_conv = _open_conversation(bob)
    alice_message = _append_message(app, alice_conv["id"], "shared-needle alice-only")
    bob_message = _append_message(app, bob_conv["id"], "shared-needle bob-only")

    conn = app.state.conn_factory()
    try:
        seed_pre_p23_legacy_conversation(
            conn,
            conversation_id="conv_legacy_search",
            agent_id="guide_agent",
            created_by=DISPLAY_NAME,
        )
        legacy_message = repos.append_message(
            conn,
            conversation_id="conv_legacy_search",
            role="user",
            content="shared-needle legacy-ownerless",
        )
    finally:
        conn.close()

    alice_page = _search(alice, q="shared-needle", scope="message").json()
    assert [item["id"] for item in alice_page["items"]] == [alice_message["message_id"]]
    assert bob_message["message_id"] not in {item["id"] for item in alice_page["items"]}
    assert legacy_message["message_id"] not in {item["id"] for item in alice_page["items"]}

    # Exact foreign IDs remain a non-oracle: successful empty page, never 403.
    foreign = _search(alice, q=bob_message["message_id"], scope="message")
    assert foreign.status_code == 200
    assert foreign.json()["items"] == []

    bob_page = _search(bob, q="shared-needle", scope="message").json()
    assert [item["id"] for item in bob_page["items"]] == [bob_message["message_id"]]


def test_message_projection_is_stable_bounded_literal_and_schema_valid(app_env) -> None:
    client, app = app_env
    conversation = _open_conversation(client)
    literal = '100%_\\"quoted"'
    message = _append_message(
        app,
        conversation["id"],
        "A" * 180 + literal + "B" * 180,
    )

    response = _search(client, q=literal, scope="message")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    Draft202012Validator(json.loads(SEARCH_SCHEMA.read_text(encoding="utf-8"))).validate(body)
    assert body["schema_version"] == "search-page/v1"
    assert body["scope"] == "message"
    assert body["query"] == literal
    assert body["has_more"] is False
    assert body["next_cursor"] is None

    hit = body["items"][0]
    assert hit["id"] == message["message_id"]
    assert hit["conversation_id"] == conversation["id"]
    assert literal in hit["snippet"]
    assert len(hit["snippet"]) <= 240
    assert hit["snippet_truncated"] is True
    for forbidden in ("content", "file_ids", "recommendation", "internal_id"):
        assert forbidden not in hit


def test_conversation_search_exposes_no_fake_title_or_owner(app_env) -> None:
    client, _ = app_env
    conversation = _open_conversation(client)
    response = _search(client, q=conversation["id"], scope="conversation")
    assert response.status_code == 200, response.text
    hit = response.json()["items"][0]
    assert hit == {
        "kind": "conversation",
        "id": conversation["id"],
        "agent_id": "guide_agent",
        "status": "active",
        "created_at": conversation["created_at"],
        "match_kind": "exact_id",
    }


def test_task_search_is_global_metadata_only_and_never_indexes_inputs(
    two_user_search_env,
) -> None:
    alice, bob, app = two_user_search_env
    alice_task = _create_task(
        app,
        task_id="task_alice_search",
        username="alice",
        name="alice neutral",
        inputs={"requirement": "alice-input-needle"},
        status="running",
    )
    bob_task = _create_task(
        app,
        task_id="task_bob_search",
        username="bob",
        name="shared-meta-needle",
        inputs={"requirement": "bob-input-needle"},
        status="queued",
    )
    eval_task = _create_task(
        app,
        task_id="task_eval_search",
        username="alice",
        name="shared-meta-needle",
        origin="eval",
    )

    assert _search(alice, q="alice-input-needle", scope="task").json()["items"] == []
    assert _search(alice, q="bob-input-needle", scope="task").json()["items"] == []
    assert _search(bob, q="bob-input-needle", scope="task").json()["items"] == []

    global_response = _search(alice, q="shared-meta-needle", scope="task")
    assert global_response.status_code == 200, global_response.text
    Draft202012Validator(json.loads(SEARCH_SCHEMA.read_text(encoding="utf-8"))).validate(
        global_response.json()
    )
    global_metadata = global_response.json()["items"]
    assert [item["id"] for item in global_metadata] == [bob_task["id"]]
    assert eval_task["id"] not in {item["id"] for item in global_metadata}
    assert _search(
        alice,
        q="shared-meta-needle",
        scope="task",
        task_scope="mine",
    ).json()["items"] == []

    filtered = _search(
        alice,
        q="task_",
        scope="task",
        status="running",
        agent_id="hello_agent",
    )
    assert [item["id"] for item in filtered.json()["items"]] == [alice_task["id"]]
    for item in global_metadata:
        for forbidden in (
            "inputs",
            "error_message",
            "metadata",
            "output_file_ids",
            "created_by",
            "created_by_username",
        ):
            assert forbidden not in item


def test_artifact_search_requires_authoritative_output_membership(app_env) -> None:
    client, app = app_env
    task = _create_task(
        app,
        task_id="task_artifact_search",
        username="test_engineer",
        name="artifact parent",
    )
    valid = _create_file(
        app,
        file_id="file_valid_output",
        task_id=task["id"],
        kind="output",
        filename="searchable-result-report.md",
        classification="sensitive",
    )
    _create_file(
        app,
        file_id="file_input_only",
        task_id=task["id"],
        kind="input",
        filename="searchable-result-input.md",
    )
    _create_file(
        app,
        file_id="file_orphan_output",
        task_id=None,
        kind="output",
        filename="searchable-result-orphan.md",
    )
    _create_file(
        app,
        file_id="file_unlisted_output",
        task_id=task["id"],
        kind="output",
        filename="searchable-result-unlisted.md",
    )
    _set_outputs(app, task["id"], [valid["id"]])

    response = _search(client, q="searchable-result", scope="artifact")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    Draft202012Validator(json.loads(SEARCH_SCHEMA.read_text(encoding="utf-8"))).validate(
        response.json()
    )
    assert response.json()["items"] == [
        {
            "kind": "artifact",
            "id": valid["id"],
            "filename": valid["filename"],
            "task_id": task["id"],
            "task_name": task["name"],
            "size_bytes": 123,
            "data_classification": "sensitive",
            "content_withheld": True,
            "created_at": valid["created_at"],
            "match_kind": "text_prefix",
        }
    ]
    serialized = response.text
    for forbidden in ("/bounded-fixture/", "sha256", "uploaded_by", "preview", "download"):
        assert forbidden not in serialized


def test_search_cursor_is_snapshot_bound_replayable_and_principal_bound(
    two_user_search_env,
) -> None:
    alice, bob, app = two_user_search_env
    conversation = _open_conversation(alice)
    seeded = [
        _append_message(app, conversation["id"], f"page-needle {index}")
        for index in range(5)
    ]

    first = _search(alice, q="page-needle", scope="message", limit=2)
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert len(first_body["items"]) == 2
    assert first_body["has_more"] is True
    cursor = first_body["next_cursor"]
    assert isinstance(cursor, str) and cursor

    # A new, more recent hit must not jump into the already-frozen page chain.
    inserted_after_snapshot = _append_message(app, conversation["id"], "page-needle newest")
    second = _search(
        alice,
        q="page-needle",
        scope="message",
        limit=2,
        cursor=cursor,
    )
    replay = _search(
        alice,
        q="page-needle",
        scope="message",
        limit=2,
        cursor=cursor,
    )
    assert second.status_code == replay.status_code == 200
    assert second.json() == replay.json()
    assert inserted_after_snapshot["message_id"] not in {
        item["id"] for item in second.json()["items"]
    }

    seen = [item["id"] for item in first_body["items"]]
    page = second.json()
    while True:
        seen.extend(item["id"] for item in page["items"])
        if page["next_cursor"] is None:
            break
        page_response = _search(
            alice,
            q="page-needle",
            scope="message",
            limit=2,
            cursor=page["next_cursor"],
        )
        assert page_response.status_code == 200, page_response.text
        page = page_response.json()
    assert len(seen) == len(set(seen)) == len(seeded)
    assert set(seen) == {item["message_id"] for item in seeded}

    assert _search(
        alice,
        q="different-query",
        scope="message",
        limit=2,
        cursor=cursor,
    ).status_code == 422
    assert _search(
        alice,
        q="page-needle",
        scope="task",
        limit=2,
        cursor=cursor,
    ).status_code == 422
    assert _search(
        bob,
        q="page-needle",
        scope="message",
        limit=2,
        cursor=cursor,
    ).status_code == 422

    padded = cursor + "=" * (-len(cursor) % 4)
    cursor_payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    cursor_payload["mac"] = "0" * 64
    tampered = base64.urlsafe_b64encode(
        json.dumps(cursor_payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    assert _search(
        alice,
        q="page-needle",
        scope="message",
        limit=2,
        cursor=tampered,
    ).status_code == 422

    cursor_payload["snapshot_at"] = "0001-01-01T00:00:00+14:00"
    cursor_payload["last"]["created_at"] = "0001-01-01T00:00:00+14:00"
    extreme_tamper = base64.urlsafe_b64encode(
        json.dumps(cursor_payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    extreme_response = _search(
        alice,
        q="page-needle",
        scope="message",
        limit=2,
        cursor=extreme_tamper,
    )
    assert extreme_response.status_code == 422
    assert extreme_response.headers["cache-control"] == "no-store"


def test_search_capacity_and_sql_failure_return_503_not_false_empty(
    app_env, monkeypatch
) -> None:
    client, app = app_env
    conversation = _open_conversation(client)
    _append_message(app, conversation["id"], "capacity-needle one")
    _append_message(app, conversation["id"], "capacity-needle two")

    from backend.app.storage import search as search_store

    monkeypatch.setattr(search_store, "MAX_SOURCE_ROWS", 1)
    capacity = _search(client, q="capacity-needle", scope="message")
    assert capacity.status_code == 503
    assert "capacity" in capacity.json()["detail"]

    monkeypatch.setattr(search_store, "MAX_SOURCE_ROWS", 50_000)
    monkeypatch.setattr(search_store, "MAX_SOURCE_TEXT_CHARS", 1)
    text_capacity = _search(client, q="capacity-needle", scope="message")
    assert text_capacity.status_code == 503
    assert "capacity" in text_capacity.json()["detail"]

    monkeypatch.setattr(search_store, "MAX_SOURCE_TEXT_CHARS", 16_000_000)
    original = search_store._search_scope

    def fail_sql(*args: Any, **kwargs: Any):
        raise sqlite3.OperationalError("forced search read failure")

    monkeypatch.setattr(search_store, "_search_scope", fail_sql)
    failed = _search(client, q="capacity-needle", scope="message")
    assert failed.status_code == 503
    assert failed.json()["detail"] != ""
    monkeypatch.setattr(search_store, "_search_scope", original)


def test_search_connection_failure_is_explicit_503_with_no_store(
    app_env, monkeypatch
) -> None:
    client, app = app_env

    def fail_open():
        raise sqlite3.OperationalError("forced connection failure")

    monkeypatch.setattr(app.state, "conn_factory", fail_open)
    response = _search(client, q="valid", scope="message")
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"detail": "search_source_unavailable"}


def test_invalid_search_is_rejected_before_connection_acquisition(
    app_env, monkeypatch
) -> None:
    client, app = app_env

    def fail_open():
        raise sqlite3.OperationalError("connection must not be attempted")

    monkeypatch.setattr(app.state, "conn_factory", fail_open)
    probes = (
        {"q": "x", "scope": "message"},
        {"q": "valid", "scope": "bogus"},
        {"q": "valid", "scope": "message", "cursor": "bad"},
    )
    for params in probes:
        response = _search(client, **params)
        assert response.status_code == 422, (params, response.text)
        assert response.headers["cache-control"] == "no-store"


def test_extreme_source_timestamp_fails_as_explicit_503(app_env) -> None:
    client, app = app_env
    task = _create_task(
        app,
        task_id="task_extreme_timestamp",
        username="test_engineer",
        name="extreme timestamp needle",
    )
    conn = app.state.conn_factory()
    try:
        conn.execute(
            "UPDATE tasks SET created_at = ? WHERE id = ?",
            ("0001-01-01T00:00:00+14:00", task["id"]),
        )
    finally:
        conn.close()

    response = _search(client, q="extreme timestamp", scope="task")
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"detail": "search_source_unavailable"}


def test_search_is_read_only_and_never_calls_model(app_env) -> None:
    client, app = app_env
    conversation = _open_conversation(client)
    _append_message(app, conversation["id"], "read-only-needle")
    conn = app.state.conn_factory()
    try:
        before = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "tasks",
                "conversation_messages",
                "files",
                "task_events",
                "model_calls",
            )
        }
    finally:
        conn.close()

    response = _search(client, q="read-only-needle", scope="message")
    assert response.status_code == 200, response.text

    conn = app.state.conn_factory()
    try:
        after = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in before
        }
    finally:
        conn.close()
    assert after == before
