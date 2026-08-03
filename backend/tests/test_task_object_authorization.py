"""Task public APIs enforce exact owner authorization and fail closed.

The seam under test is the authenticated FastAPI API.  Accounts are provisioned
through the same server-side service as ``user_admin.py``; every session and all
task/resource actions go through the real HTTP endpoints.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from conftest import login, seed_user


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def task_owner_env(tmp_path: Path) -> Iterator[tuple[TestClient, TestClient, object, Path]]:
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
            display_name="Alice",
            password="alice-pass-123",
        )
        seed_user(
            db_path,
            username="bob",
            display_name="Bob",
            password="bob-pass-123",
        )
        login(alice, username="alice", password="alice-pass-123")
        bob = TestClient(app)
        login(bob, username="bob", password="bob-pass-123")
        try:
            yield alice, bob, app, db_path
        finally:
            bob.close()


def _create_task(client: TestClient, *, name: str = "owner seam") -> dict:
    response = client.post(
        "/api/tasks",
        json={"agent_id": "hello_agent", "inputs": {"name": name}},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _open_conversation(client: TestClient) -> str:
    response = client.post(
        "/api/conversations",
        json={"agent_id": "guide_agent"},
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _upload_input(client: TestClient, *, filename: str) -> str:
    response = client.post(
        "/api/files/upload",
        files={"file": (filename, b"private input", "text/plain")},
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _mark_failed(app: object, task_id: str) -> None:
    from backend.app.storage import repos

    conn = app.state.conn_factory()
    try:
        for status in ("validating", "running", "failed"):
            repos.set_task_status(conn, task_id, status)
    finally:
        conn.close()


def _seed_eval_task(
    app: object,
    *,
    task_id: str = "task-eval-shared",
    output_file_id: str | None = None,
) -> dict:
    from backend.app.storage import repos

    conn = app.state.conn_factory()
    try:
        task = repos.create_task(
            conn,
            task_id=task_id,
            agent_id="hello_agent",
            agent_version="0.1.0",
            name="shared governance evidence",
            created_by="Eval Runner",
            created_by_username=None,
            origin="eval",
        )
        if output_file_id is not None:
            repos.create_file(
                conn,
                file_id=output_file_id,
                task_id=task_id,
                kind="output",
                filename="eval-evidence.txt",
                path="/nonexistent/eval-evidence.txt",
                size_bytes=13,
                sha256="e" * 64,
                classification="internal",
            )
            task = repos.set_task_outputs(conn, task_id, [output_file_id])
        return task
    finally:
        conn.close()


def _seed_failed_output_input_carrier(
    app: object,
    *,
    prefix: str,
    source_chain_nodes: int,
) -> str:
    """Seed a failed task whose lineage reaches a source through an output input."""
    from backend.app.storage import repos

    conn = app.state.conn_factory()
    try:
        source_task_id: str | None = None
        for index in range(source_chain_nodes):
            task_id = f"task-{prefix}-source-{index:02d}"
            repos.create_task(
                conn,
                task_id=task_id,
                agent_id="hello_agent",
                agent_version="0.1.0",
                name=f"{prefix} source {index}",
                created_by="Alice",
                created_by_username="alice",
                depends_on=(
                    [source_task_id] if source_task_id is not None else None
                ),
            )
            source_task_id = task_id

        input_file_ids: list[str] = []
        if source_task_id is not None:
            output_file_id = f"file-{prefix}-source-output"
            repos.create_file(
                conn,
                file_id=output_file_id,
                task_id=source_task_id,
                kind="output",
                filename=f"{prefix}.txt",
                path=f"/nonexistent/{prefix}.txt",
                size_bytes=1,
                sha256="d" * 64,
                classification="internal",
            )
            repos.set_task_outputs(conn, source_task_id, [output_file_id])
            input_file_ids = [output_file_id]

        carrier_id = f"task-{prefix}-carrier"
        repos.create_task(
            conn,
            task_id=carrier_id,
            agent_id="hello_agent",
            agent_version="0.1.0",
            name=f"{prefix} carrier",
            created_by="Alice",
            created_by_username="alice",
            input_file_ids=input_file_ids,
        )
        for status in ("queued", "validating", "running", "failed"):
            repos.set_task_status(conn, carrier_id, status)
        return carrier_id
    finally:
        conn.close()


def _task_event_counts(app: object) -> tuple[int, int]:
    conn = app.state.conn_factory()
    try:
        return (
            conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM task_events").fetchone()[0],
        )
    finally:
        conn.close()


def _batch_chain_items(*, retry_of: str) -> list[dict]:
    return [
        {
            "agent_id": "hello_agent",
            "inputs": {"name": f"batch depth {index}"},
            **({"retry_of": retry_of} if index == 0 else {}),
            **({"after": [index - 1]} if index > 0 else {}),
        }
        for index in range(32)
    ]


def test_task_list_and_detail_are_private_and_unknown_is_indistinguishable(
    task_owner_env,
) -> None:
    alice, bob, _app, _db_path = task_owner_env
    task = _create_task(alice)

    alice_rows = alice.get("/api/tasks").json()
    assert [row["id"] for row in alice_rows] == [task["id"]]

    bob_rows = bob.get("/api/tasks")
    assert bob_rows.status_code == 200
    assert bob_rows.json() == []

    foreign = bob.get(f"/api/tasks/{task['id']}")
    missing = bob.get("/api/tasks/task-does-not-exist")
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json() == {
        "detail": "资源不存在或不可访问"
    }


def test_task_list_filters_owner_before_limit_and_offset(task_owner_env) -> None:
    alice, bob, _app, _db_path = task_owner_env
    alice_old = _create_task(alice, name="Alice old")
    alice_new = _create_task(alice, name="Alice new")
    for index in range(3):
        _create_task(bob, name=f"Bob newer {index}")

    first = alice.get("/api/tasks?limit=1&offset=0")
    second = alice.get("/api/tasks?limit=1&offset=1")
    assert first.status_code == second.status_code == 200
    assert [row["id"] for row in first.json()] == [alice_new["id"]]
    assert [row["id"] for row in second.json()] == [alice_old["id"]]


def test_eval_tasks_are_global_read_only_and_all_visibility_precedes_pagination(
    task_owner_env,
) -> None:
    alice, bob, app, _db_path = task_owner_env
    alice_task = _create_task(alice, name="Alice private")
    bob_task = _create_task(bob, name="Bob private")
    eval_task = _seed_eval_task(
        app,
        output_file_id="file-eval-shared-output",
    )

    conn = app.state.conn_factory()
    try:
        conn.execute(
            "UPDATE tasks SET created_at = ? WHERE id = ?",
            ("2026-08-03T00:00:01+00:00", alice_task["id"]),
        )
        conn.execute(
            "UPDATE tasks SET created_at = ? WHERE id = ?",
            ("2026-08-03T00:00:02+00:00", eval_task["id"]),
        )
        conn.execute(
            "UPDATE tasks SET created_at = ? WHERE id = ?",
            ("2026-08-03T00:00:03+00:00", bob_task["id"]),
        )
        conn.commit()
    finally:
        conn.close()

    for client in (alice, bob):
        eval_rows = client.get("/api/tasks?origin=eval")
        assert eval_rows.status_code == 200
        assert [row["id"] for row in eval_rows.json()] == [eval_task["id"]]

        detail = client.get(f"/api/tasks/{eval_task['id']}")
        assert detail.status_code == 200
        assert detail.json()["origin"] == "eval"
        for suffix in (
            "/events",
            "/tool_runs",
            "/tool_runs/summary",
            "/model_calls",
            "/samples",
            "/output_files",
            "/delivery_summary",
            "/feedback",
        ):
            child = client.get(f"/api/tasks/{eval_task['id']}{suffix}")
            assert child.status_code == 200, (suffix, child.text)

    # Bob's newer private row must be removed by the SQL visibility predicate
    # before Alice's origin=all LIMIT/OFFSET window is selected.
    first = alice.get("/api/tasks?origin=all&limit=1&offset=0")
    second = alice.get("/api/tasks?origin=all&limit=1&offset=1")
    third = alice.get("/api/tasks?origin=all&limit=1&offset=2")
    assert first.status_code == second.status_code == third.status_code == 200
    assert [row["id"] for row in first.json()] == [eval_task["id"]]
    assert [row["id"] for row in second.json()] == [alice_task["id"]]
    assert third.json() == []


def test_eval_task_mutations_still_require_exact_owner(task_owner_env) -> None:
    alice, _bob, app, _db_path = task_owner_env
    eval_task = _seed_eval_task(app, task_id="task-eval-no-owner")
    task_id = eval_task["id"]
    missing_id = "task-does-not-exist"

    cases = (
        (f"/api/tasks/{task_id}/cancel", f"/api/tasks/{missing_id}/cancel", None),
        (
            f"/api/tasks/{task_id}/review",
            f"/api/tasks/{missing_id}/review",
            {"action": "approve"},
        ),
        (
            f"/api/tasks/{task_id}/sim-run-ref",
            f"/api/tasks/{missing_id}/sim-run-ref",
            {"module": "structopt", "run_id": "20260803-000000-000001"},
        ),
        (
            "/api/feedback",
            "/api/feedback",
            {
                "task_id": task_id,
                "rating": "bad",
                "category": "result_wrong",
                "message": "must not be written",
            },
        ),
    )
    for eval_path, missing_path, payload in cases:
        denied = alice.post(eval_path, json=payload)
        missing_payload = payload
        if eval_path == "/api/feedback":
            missing_payload = {**payload, "task_id": missing_id}
        missing = alice.post(missing_path, json=missing_payload)
        assert denied.status_code == missing.status_code == 404, eval_path
        assert denied.json() == missing.json() == {
            "detail": "资源不存在或不可访问"
        }

    detail = alice.get(f"/api/tasks/{task_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "created"
    assert detail.json()["metadata"] == {}
    assert alice.get(f"/api/tasks/{task_id}/feedback").json() == []


def test_cross_owner_task_reads_and_mutations_are_404_with_zero_business_writes(
    task_owner_env,
) -> None:
    alice, bob, _app, _db_path = task_owner_env
    task = _create_task(alice, name="private task")
    task_id = task["id"]
    missing_id = "task-does-not-exist"

    before_task = alice.get(f"/api/tasks/{task_id}").json()
    before_events = alice.get(f"/api/tasks/{task_id}/events").json()
    before_feedback = alice.get(f"/api/tasks/{task_id}/feedback").json()

    for suffix in (
        "",
        "/events",
        "/tool_runs",
        "/tool_runs/summary",
        "/model_calls",
        "/samples",
        "/output_files",
        "/delivery_summary",
        "/feedback",
    ):
        foreign = bob.get(f"/api/tasks/{task_id}{suffix}")
        missing = bob.get(f"/api/tasks/{missing_id}{suffix}")
        assert foreign.status_code == missing.status_code == 404, suffix
        assert foreign.json() == missing.json() == {
            "detail": "资源不存在或不可访问"
        }, suffix

    mutations = (
        (
            "post",
            f"/api/tasks/{task_id}/cancel",
            f"/api/tasks/{missing_id}/cancel",
            None,
        ),
        (
            "post",
            f"/api/tasks/{task_id}/review",
            f"/api/tasks/{missing_id}/review",
            {"action": "approve"},
        ),
        (
            "post",
            f"/api/tasks/{task_id}/sim-run-ref",
            f"/api/tasks/{missing_id}/sim-run-ref",
            {"module": "structopt", "run_id": "20260803-000000-000001"},
        ),
        (
            "post",
            "/api/feedback",
            "/api/feedback",
            {
                "task_id": task_id,
                "rating": "bad",
                "category": "result_wrong",
                "message": "must not be written",
            },
        ),
    )
    for _method, foreign_path, missing_path, payload in mutations:
        foreign = bob.post(foreign_path, json=payload)
        missing_payload = payload
        if foreign_path == "/api/feedback":
            missing_payload = {**payload, "task_id": missing_id}
        missing = bob.post(missing_path, json=missing_payload)
        assert foreign.status_code == missing.status_code == 404, foreign_path
        assert foreign.json() == missing.json() == {
            "detail": "资源不存在或不可访问"
        }, foreign_path

    assert alice.get(f"/api/tasks/{task_id}").json() == before_task
    assert alice.get(f"/api/tasks/{task_id}/events").json() == before_events
    assert alice.get(f"/api/tasks/{task_id}/feedback").json() == before_feedback


def test_single_task_creation_rejects_foreign_resource_references_before_writing(
    task_owner_env,
) -> None:
    alice, bob, app, _db_path = task_owner_env
    bob_task = _create_task(bob, name="Bob upstream")
    bob_conversation_id = _open_conversation(bob)
    bob_file_id = _upload_input(bob, filename="bob-private.txt")
    _mark_failed(app, bob_task["id"])

    cases = (
        (
            {"conversation_id": bob_conversation_id},
            {"conversation_id": "conversation-does-not-exist"},
        ),
        (
            {"input_file_ids": [bob_file_id]},
            {"input_file_ids": ["file-does-not-exist"]},
        ),
        (
            {"depends_on": [bob_task["id"]]},
            {"depends_on": ["task-does-not-exist"]},
        ),
        (
            {
                "depends_on": [bob_task["id"]],
                "input_binding": {"from_tasks": [bob_task["id"]]},
            },
            {
                "depends_on": ["task-does-not-exist"],
                "input_binding": {"from_tasks": ["task-does-not-exist"]},
            },
        ),
        (
            {"retry_of": bob_task["id"]},
            {"retry_of": "task-does-not-exist"},
        ),
    )
    base = {"agent_id": "hello_agent", "inputs": {"name": "Alice"}}
    for foreign_ref, missing_ref in cases:
        foreign = alice.post("/api/tasks", json={**base, **foreign_ref})
        missing = alice.post("/api/tasks", json={**base, **missing_ref})
        assert foreign.status_code == missing.status_code == 404, foreign_ref
        assert foreign.json() == missing.json() == {
            "detail": "资源不存在或不可访问"
        }, foreign_ref

    assert alice.get("/api/tasks").json() == []


def test_task_creation_rejects_owned_conversation_with_foreign_history(
    task_owner_env,
) -> None:
    from backend.app.storage import repos

    alice, bob, app, _db_path = task_owner_env
    conversation_id = _open_conversation(alice)
    bob_file_id = _upload_input(bob, filename="bob-history-private.txt")
    conn = app.state.conn_factory()
    try:
        repos.append_message(
            conn,
            conversation_id=conversation_id,
            role="user",
            content="legacy foreign history",
            file_ids=[bob_file_id],
        )
        before_tasks = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        before_events = conn.execute("SELECT COUNT(*) FROM task_events").fetchone()[0]
    finally:
        conn.close()

    single = alice.post(
        "/api/tasks",
        json={
            "agent_id": "hello_agent",
            "inputs": {"name": "must fail closed"},
            "conversation_id": conversation_id,
        },
    )
    batch = alice.post(
        "/api/tasks/batch",
        json={
            "conversation_id": conversation_id,
            "items": [{"agent_id": "hello_agent"}],
        },
    )
    assert single.status_code == batch.status_code == 404
    assert single.json() == batch.json() == {
        "detail": "资源不存在或不可访问"
    }

    conn = app.state.conn_factory()
    try:
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == before_tasks
        assert conn.execute("SELECT COUNT(*) FROM task_events").fetchone()[0] == before_events
    finally:
        conn.close()


def test_single_create_enforces_prospective_lineage_depth_32_33_before_writes(
    task_owner_env,
) -> None:
    alice, _bob, app, _db_path = task_owner_env
    depth_32_head = _seed_failed_output_input_carrier(
        app,
        prefix="single-depth32",
        source_chain_nodes=31,
    )
    depth_33_head = _seed_failed_output_input_carrier(
        app,
        prefix="single-depth33",
        source_chain_nodes=32,
    )

    allowed = alice.post(
        "/api/tasks",
        json={
            "agent_id": "hello_agent",
            "inputs": {"name": "prospective depth 32"},
            "depends_on": [depth_32_head],
            "input_binding": {"from_tasks": [depth_32_head]},
            "retry_of": depth_32_head,
        },
    )
    assert allowed.status_code == 200, allowed.text
    assert alice.get(f"/api/tasks/{allowed.json()['id']}").status_code == 200

    before = _task_event_counts(app)
    denied = alice.post(
        "/api/tasks",
        json={
            "agent_id": "hello_agent",
            "inputs": {"name": "prospective depth 33"},
            "depends_on": [depth_33_head],
            "input_binding": {"from_tasks": [depth_33_head]},
            "retry_of": depth_33_head,
        },
    )
    assert denied.status_code == 404
    assert denied.json() == {"detail": "资源不存在或不可访问"}
    assert _task_event_counts(app) == before


def test_batch_create_enforces_prospective_lineage_depth_32_33_before_writes(
    task_owner_env,
) -> None:
    alice, _bob, app, _db_path = task_owner_env
    depth_32_head = _seed_failed_output_input_carrier(
        app,
        prefix="batch-depth32",
        source_chain_nodes=0,
    )
    depth_33_head = _seed_failed_output_input_carrier(
        app,
        prefix="batch-depth33",
        source_chain_nodes=1,
    )

    allowed = alice.post(
        "/api/tasks/batch",
        json={"items": _batch_chain_items(retry_of=depth_32_head)},
    )
    assert allowed.status_code == 200, allowed.text
    allowed_tasks = allowed.json()["tasks"]
    assert len(allowed_tasks) == 32
    assert alice.get(f"/api/tasks/{allowed_tasks[-1]['id']}").status_code == 200

    before = _task_event_counts(app)
    denied = alice.post(
        "/api/tasks/batch",
        json={"items": _batch_chain_items(retry_of=depth_33_head)},
    )
    assert denied.status_code == 404
    assert denied.json() == {"detail": "资源不存在或不可访问"}
    assert _task_event_counts(app) == before


def test_batch_task_creation_rejects_foreign_resource_references_before_writing(
    task_owner_env,
) -> None:
    alice, bob, app, _db_path = task_owner_env
    bob_task = _create_task(bob, name="Bob retry source")
    bob_conversation_id = _open_conversation(bob)
    bob_file_id = _upload_input(bob, filename="bob-batch-private.txt")
    _mark_failed(app, bob_task["id"])

    cases = (
        (
            {"conversation_id": bob_conversation_id, "items": [{"agent_id": "hello_agent"}]},
            {
                "conversation_id": "conversation-does-not-exist",
                "items": [{"agent_id": "hello_agent"}],
            },
        ),
        (
            {
                "items": [
                    {"agent_id": "hello_agent", "input_file_ids": [bob_file_id]}
                ]
            },
            {
                "items": [
                    {
                        "agent_id": "hello_agent",
                        "input_file_ids": ["file-does-not-exist"],
                    }
                ]
            },
        ),
        (
            {
                "items": [
                    {"agent_id": "hello_agent", "retry_of": bob_task["id"]}
                ]
            },
            {
                "items": [
                    {
                        "agent_id": "hello_agent",
                        "retry_of": "task-does-not-exist",
                    }
                ]
            },
        ),
    )
    for foreign_payload, missing_payload in cases:
        foreign = alice.post("/api/tasks/batch", json=foreign_payload)
        missing = alice.post("/api/tasks/batch", json=missing_payload)
        assert foreign.status_code == missing.status_code == 404, foreign_payload
        assert foreign.json() == missing.json() == {
            "detail": "资源不存在或不可访问"
        }, foreign_payload

    assert alice.get("/api/tasks").json() == []


def test_batch_operation_replay_revalidates_recursive_owner_lineage(
    task_owner_env,
) -> None:
    import json

    alice, bob, app, _db_path = task_owner_env
    payload = {
        "operation_id": "owner-lineage-replay-001",
        "items": [
            {
                "agent_id": "hello_agent",
                "inputs": {"name": "owner replay"},
            }
        ],
    }
    created = alice.post("/api/tasks/batch", json=payload)
    assert created.status_code == 200, created.text
    task_id = created.json()["tasks"][0]["id"]
    bob_file_id = _upload_input(bob, filename="bob-replay-private.txt")

    conn = app.state.conn_factory()
    try:
        before_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        conn.execute(
            "UPDATE tasks SET input_file_ids = ? WHERE id = ?",
            (json.dumps([bob_file_id]), task_id),
        )
        conn.commit()
    finally:
        conn.close()

    replay = alice.post("/api/tasks/batch", json=payload)
    assert replay.status_code == 404
    assert replay.json() == {"detail": "资源不存在或不可访问"}
    conn = app.state.conn_factory()
    try:
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == before_count
    finally:
        conn.close()


def test_batch_operation_replay_rejects_malformed_persisted_lineage(
    task_owner_env,
) -> None:
    alice, _bob, app, _db_path = task_owner_env
    payload = {
        "operation_id": "owner-lineage-replay-malformed-001",
        "items": [
            {
                "agent_id": "hello_agent",
                "inputs": {"name": "malformed replay"},
            }
        ],
    }
    created = alice.post("/api/tasks/batch", json=payload)
    assert created.status_code == 200, created.text
    task_id = created.json()["tasks"][0]["id"]

    conn = app.state.conn_factory()
    try:
        before_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        conn.execute(
            "UPDATE tasks SET input_file_ids = '{not-json' WHERE id = ?",
            (task_id,),
        )
        conn.commit()
    finally:
        conn.close()

    replay = alice.post("/api/tasks/batch", json=payload)
    assert replay.status_code == 404
    assert replay.json() == {"detail": "资源不存在或不可访问"}
    conn = app.state.conn_factory()
    try:
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == before_count
    finally:
        conn.close()


def test_batch_operation_replay_redacts_sensitive_task_content(
    task_owner_env,
) -> None:
    alice, _bob, app, _db_path = task_owner_env
    payload = {
        "operation_id": "owner-lineage-replay-sensitive-001",
        "items": [
            {
                "agent_id": "hello_agent",
                "inputs": {"name": "sensitive replay"},
            }
        ],
    }
    created = alice.post("/api/tasks/batch", json=payload)
    assert created.status_code == 200, created.text
    task_id = created.json()["tasks"][0]["id"]

    conn = app.state.conn_factory()
    try:
        conn.execute(
            "UPDATE tasks SET data_classification = 'sensitive', "
            "error_message = 'private-tool-output' WHERE id = ?",
            (task_id,),
        )
        conn.commit()
    finally:
        conn.close()

    detail = alice.get(f"/api/tasks/{task_id}")
    replay = alice.post("/api/tasks/batch", json=payload)
    assert detail.status_code == replay.status_code == 200
    replay_task = replay.json()["tasks"][0]
    assert replay_task["error_message"] is None
    assert replay_task["content_withheld"] is True
    assert replay_task == detail.json()


def test_legacy_task_without_owner_is_not_claimed_by_display_name(
    task_owner_env,
) -> None:
    from backend.app.storage import repos

    alice, _bob, app, _db_path = task_owner_env
    conn = app.state.conn_factory()
    try:
        repos.create_task(
            conn,
            task_id="task-legacy-null-owner",
            agent_id="hello_agent",
            agent_version="0.1.0",
            name="legacy",
            created_by="Alice",
            created_by_username=None,
        )
    finally:
        conn.close()

    assert alice.get("/api/tasks").json() == []
    foreign = alice.get("/api/tasks/task-legacy-null-owner")
    missing = alice.get("/api/tasks/task-does-not-exist")
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json() == {
        "detail": "资源不存在或不可访问"
    }

    cancel = alice.post("/api/tasks/task-legacy-null-owner/cancel")
    assert cancel.status_code == 404
    assert cancel.json() == {"detail": "资源不存在或不可访问"}


@pytest.mark.parametrize(
    "poison_kind",
    [
        "foreign_conversation",
        "foreign_conversation_attachment",
        "foreign_direct_input",
        "foreign_output_input",
        "foreign_dependency",
        "foreign_retry",
        "foreign_input_binding",
    ],
)
def test_legacy_foreign_task_lineage_is_hidden_everywhere(
    task_owner_env,
    poison_kind: str,
) -> None:
    import json

    from backend.app.storage import repos

    alice, bob, app, _db_path = task_owner_env
    alice_task = _create_task(alice, name=f"legacy poison {poison_kind}")
    bob_task = _create_task(bob, name="Bob lineage")
    bob_file_id = _upload_input(bob, filename="bob-lineage.txt")
    bob_conversation_id = _open_conversation(bob)

    conn = app.state.conn_factory()
    try:
        if poison_kind == "foreign_conversation":
            conn.execute(
                "UPDATE tasks SET conversation_id = ? WHERE id = ?",
                (bob_conversation_id, alice_task["id"]),
            )
        elif poison_kind == "foreign_conversation_attachment":
            alice_conversation_id = _open_conversation(alice)
            repos.append_message(
                conn,
                conversation_id=alice_conversation_id,
                role="user",
                content="legacy cross-owner attachment",
                file_ids=[bob_file_id],
            )
            conn.execute(
                "UPDATE tasks SET conversation_id = ? WHERE id = ?",
                (alice_conversation_id, alice_task["id"]),
            )
        elif poison_kind == "foreign_direct_input":
            conn.execute(
                "UPDATE tasks SET input_file_ids = ? WHERE id = ?",
                (json.dumps([bob_file_id]), alice_task["id"]),
            )
        elif poison_kind == "foreign_output_input":
            bob_output = repos.create_file(
                conn,
                file_id="file-bob-lineage-output",
                task_id=bob_task["id"],
                kind="output",
                filename="bob-output.txt",
                path="/nonexistent/bob-output.txt",
                size_bytes=10,
                sha256="b" * 64,
                classification="internal",
            )
            repos.set_task_outputs(conn, bob_task["id"], [bob_output["id"]])
            conn.execute(
                "UPDATE tasks SET input_file_ids = ? WHERE id = ?",
                (json.dumps([bob_output["id"]]), alice_task["id"]),
            )
        elif poison_kind == "foreign_dependency":
            conn.execute(
                "UPDATE tasks SET depends_on = ? WHERE id = ?",
                (json.dumps([bob_task["id"]]), alice_task["id"]),
            )
        elif poison_kind == "foreign_retry":
            conn.execute(
                "UPDATE tasks SET retry_of = ? WHERE id = ?",
                (bob_task["id"], alice_task["id"]),
            )
        else:
            conn.execute(
                "UPDATE tasks SET depends_on = ?, input_binding = ? WHERE id = ?",
                (
                    json.dumps([bob_task["id"]]),
                    json.dumps({"from_tasks": [bob_task["id"]]}),
                    alice_task["id"],
                ),
            )

        alice_output = repos.create_file(
            conn,
            file_id=f"file-alice-poison-{poison_kind}",
            task_id=alice_task["id"],
            kind="output",
            filename="alice-output.txt",
            path="/nonexistent/alice-output.txt",
            size_bytes=12,
            sha256="a" * 64,
            classification="internal",
        )
        repos.set_task_outputs(conn, alice_task["id"], [alice_output["id"]])
        conn.commit()
    finally:
        conn.close()

    missing = {"detail": "资源不存在或不可访问"}
    detail = alice.get(f"/api/tasks/{alice_task['id']}")
    outputs = alice.get(f"/api/tasks/{alice_task['id']}/output_files")
    download = alice.get(f"/api/files/{alice_output['id']}/download")
    listing = alice.get("/api/tasks")
    personal = alice.get("/api/me/tasks")
    assert detail.status_code == outputs.status_code == download.status_code == 404
    assert listing.status_code == personal.status_code == 404
    assert (
        detail.json()
        == outputs.json()
        == download.json()
        == listing.json()
        == personal.json()
        == missing
    )


def test_task_lineage_cycle_and_depth_overflow_fail_closed(task_owner_env) -> None:
    import json

    from backend.app.storage import repos

    alice, _bob, app, _db_path = task_owner_env
    cycle_a = _create_task(alice, name="cycle A")
    cycle_b = _create_task(alice, name="cycle B")
    conn = app.state.conn_factory()
    try:
        conn.execute(
            "UPDATE tasks SET depends_on = ? WHERE id = ?",
            (json.dumps([cycle_b["id"]]), cycle_a["id"]),
        )
        conn.execute(
            "UPDATE tasks SET depends_on = ? WHERE id = ?",
            (json.dumps([cycle_a["id"]]), cycle_b["id"]),
        )

        previous_id: str | None = None
        for index in range(34):
            task_id = f"task-lineage-depth-{index:02d}"
            repos.create_task(
                conn,
                task_id=task_id,
                agent_id="hello_agent",
                agent_version="0.1.0",
                name=f"depth {index}",
                created_by="Alice",
                created_by_username="alice",
                depends_on=[previous_id] if previous_id is not None else None,
            )
            previous_id = task_id
        conn.commit()
    finally:
        conn.close()

    for task_id in (cycle_a["id"], previous_id):
        response = alice.get(f"/api/tasks/{task_id}")
        assert response.status_code == 404
        assert response.json() == {"detail": "资源不存在或不可访问"}


def test_output_file_projection_rejects_cross_task_relation(task_owner_env) -> None:
    import json

    from backend.app.storage import repos

    alice, bob, app, _db_path = task_owner_env
    alice_task = _create_task(alice, name="Alice projection")
    bob_task = _create_task(bob, name="Bob output")
    conn = app.state.conn_factory()
    try:
        record = repos.create_file(
            conn,
            file_id="file-bob-private-output",
            task_id=bob_task["id"],
            kind="output",
            filename="bob-private.txt",
            path="/nonexistent/bob-private.txt",
            size_bytes=12,
            sha256="0" * 64,
            classification="internal",
        )
        conn.execute(
            "UPDATE tasks SET output_file_ids = ? WHERE id = ?",
            (json.dumps([record["id"]]), alice_task["id"]),
        )
        conn.commit()
    finally:
        conn.close()

    corrupt = alice.get(f"/api/tasks/{alice_task['id']}/output_files")
    detail = alice.get(f"/api/tasks/{alice_task['id']}")
    listing = alice.get("/api/tasks")
    personal = alice.get("/api/me/tasks")
    missing = alice.get("/api/tasks/task-does-not-exist/output_files")
    assert (
        corrupt.status_code
        == detail.status_code
        == listing.status_code
        == personal.status_code
        == missing.status_code
        == 404
    )
    assert corrupt.json() == detail.json() == listing.json() == personal.json() == missing.json() == {
        "detail": "资源不存在或不可访问"
    }


def test_eval_output_file_requires_bidirectional_task_relation(task_owner_env) -> None:
    import json

    from backend.app.storage import repos

    alice, _bob, app, _db_path = task_owner_env
    projected = _seed_eval_task(app, task_id="task-eval-projected")
    actual = _seed_eval_task(app, task_id="task-eval-actual")
    conn = app.state.conn_factory()
    try:
        record = repos.create_file(
            conn,
            file_id="file-eval-cross-task-output",
            task_id=actual["id"],
            kind="output",
            filename="eval-cross-task.txt",
            path="/nonexistent/eval-cross-task.txt",
            size_bytes=15,
            sha256="c" * 64,
            classification="internal",
        )
        conn.execute(
            "UPDATE tasks SET output_file_ids = ? WHERE id = ?",
            (json.dumps([record["id"]]), projected["id"]),
        )
        conn.commit()
    finally:
        conn.close()

    projection = alice.get(f"/api/tasks/{projected['id']}/output_files")
    download = alice.get(f"/api/files/{record['id']}/download")
    assert projection.status_code == download.status_code == 404
    assert projection.json() == download.json() == {
        "detail": "资源不存在或不可访问"
    }
