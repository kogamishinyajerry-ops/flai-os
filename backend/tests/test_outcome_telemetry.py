"""M4 前置产物结果遥测：只记可证明的签发产物流转，不把交付冒充采用。"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from pathlib import Path

import anyio
import pytest

from backend.app.api.files import _VerifiedFileResponse
from backend.app.jobs.runner import resolve_dependencies_once
from backend.app.storage import repos
from backend.app.storage.db import get_conn, init_db

TEST_USERNAME = "test_engineer"


def _create_task(
    conn: sqlite3.Connection,
    task_id: str,
    *,
    origin: str = "user",
    depends_on: list[str] | None = None,
    input_file_ids: list[str] | None = None,
) -> dict:
    return repos.create_task(
        conn,
        task_id=task_id,
        agent_id="hello_agent",
        agent_version="0.1.0",
        name=task_id,
        created_by="测试工程师",
        created_by_username=TEST_USERNAME,
        inputs={},
        input_file_ids=input_file_ids,
        metadata={},
        origin=origin,
        depends_on=depends_on,
    )


def _attach_output(
    conn: sqlite3.Connection,
    task_id: str,
    *,
    file_id: str | None = None,
    path: Path | None = None,
    content: bytes = b"signed-output",
) -> str:
    file_id = file_id or f"file_{uuid.uuid4().hex}"
    if path is None:
        path = Path(f"/tmp/{file_id}.txt")
    repos.create_file(
        conn,
        file_id=file_id,
        task_id=task_id,
        kind="output",
        filename=path.name,
        path=str(path),
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        classification="internal",
    )
    task = repos.get_task(conn, task_id)
    repos.set_task_outputs(conn, task_id, [*task["output_file_ids"], file_id])
    return file_id


def _approve(conn: sqlite3.Connection, task_id: str) -> str:
    for status in ("queued", "validating", "running", "waiting_review"):
        repos.set_task_status(conn, task_id, status)
    repos.apply_human_review(
        conn,
        task_id,
        action="approve",
        reviewer="测试工程师",
        reviewer_username=TEST_USERNAME,
        reason_code=None,
        comment="已核对",
    )
    row = conn.execute(
        "SELECT event_id FROM task_events "
        "WHERE task_id = ? AND event_type = 'review_approved'",
        (task_id,),
    ).fetchone()
    assert row is not None
    return str(row["event_id"])


@pytest.fixture()
def outcome_db(tmp_path: Path):
    db_path = tmp_path / "outcomes.db"
    init_db(db_path)
    return db_path


def test_capture_is_created_only_for_new_user_approval_and_not_backfilled(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM artifact_outcome_events").fetchone()[0] == 0
        _create_task(conn, "source")
        file_id = _attach_output(conn, "source")
        review_event_id = _approve(conn, "source")

        row = conn.execute("SELECT * FROM artifact_outcome_events").fetchone()
        assert row is not None
        assert row["event_type"] == "capture_started"
        assert row["source_task_id"] == "source"
        assert row["source_file_id"] == file_id
        assert row["review_event_id"] == review_event_id
        assert row["actor_username"] is None
        assert row["downstream_task_id"] is None
        assert row["delivered_bytes"] is None
    finally:
        conn.close()


def test_invalid_foreign_non_user_unsigned_and_bad_download_rows_are_rejected(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "signed")
        signed_file = _attach_output(conn, "signed")
        review_event_id = _approve(conn, "signed")

        _create_task(conn, "unsigned")
        unsigned_file = _attach_output(conn, "unsigned")
        _create_task(conn, "eval-source", origin="eval")
        eval_file = _attach_output(conn, "eval-source")
        eval_review = repos.append_event(
            conn,
            task_id="eval-source",
            agent_id="hello_agent",
            event_type="review_approved",
            level="info",
            message="test-only persisted signer event",
            payload={},
        )["event_id"]

        invalid_rows = [
            dict(
                event_type="capture_started",
                source_task_id="missing",
                source_file_id=signed_file,
                review_event_id=review_event_id,
            ),
            dict(
                event_type="capture_started",
                source_task_id="signed",
                source_file_id=unsigned_file,
                review_event_id=review_event_id,
            ),
            dict(
                event_type="capture_started",
                source_task_id="eval-source",
                source_file_id=eval_file,
                review_event_id=eval_review,
            ),
            dict(
                event_type="capture_started",
                source_task_id="unsigned",
                source_file_id=unsigned_file,
                review_event_id=review_event_id,
            ),
            dict(
                event_type="full_download",
                source_task_id="signed",
                source_file_id=signed_file,
                review_event_id=review_event_id,
                actor_username="\n\t",
                delivered_bytes=len(b"signed-output"),
            ),
            dict(
                event_type="full_download",
                source_task_id="signed",
                source_file_id=signed_file,
                review_event_id=review_event_id,
                actor_username=TEST_USERNAME,
                delivered_bytes=1,
            ),
        ]
        before = conn.execute("SELECT COUNT(*) FROM artifact_outcome_events").fetchone()[0]
        for row in invalid_rows:
            with pytest.raises((sqlite3.IntegrityError, ValueError)):
                repos.append_artifact_outcome_event(conn, **row)
        assert conn.execute("SELECT COUNT(*) FROM artifact_outcome_events").fetchone()[0] == before
    finally:
        conn.close()


def test_outcome_ledger_blocks_update_delete_replace_and_explicit_rowid_replace(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "source")
        file_id = _attach_output(conn, "source")
        review_event_id = _approve(conn, "source")
        repos.append_artifact_outcome_event(
            conn,
            event_type="full_download",
            source_task_id="source",
            source_file_id=file_id,
            review_event_id=review_event_id,
            actor_username=TEST_USERNAME,
            delivered_bytes=len(b"signed-output"),
        )
        row = conn.execute(
            "SELECT rowid, * FROM artifact_outcome_events "
            "WHERE event_type = 'full_download'"
        ).fetchone()
        assert row is not None
        columns = (
            "id, event_type, source_task_id, source_file_id, review_event_id, "
            "actor_username, downstream_task_id, delivered_bytes, schema_version, created_at"
        )

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE artifact_outcome_events SET created_at = created_at WHERE id = ?",
                (row["id"],),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM artifact_outcome_events WHERE id = ?", (row["id"],))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                f"INSERT OR REPLACE INTO artifact_outcome_events ({columns}) "
                f"SELECT {columns} FROM artifact_outcome_events WHERE id = ?",
                (row["id"],),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT OR REPLACE INTO artifact_outcome_events "
                "(rowid, id, event_type, source_task_id, source_file_id, review_event_id, "
                " actor_username, downstream_task_id, delivered_bytes, schema_version, created_at) "
                "VALUES (?, ?, 'full_download', 'source', ?, ?, ?, NULL, ?, 1, ?)",
                (
                    row["rowid"],
                    f"outcome_{uuid.uuid4().hex}",
                    file_id,
                    review_event_id,
                    TEST_USERNAME,
                    len(b"signed-output"),
                    row["created_at"],
                ),
            )
    finally:
        conn.close()


def test_missing_outcome_table_with_managed_trigger_residue_fails_startup(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        # DROP TABLE removes its own triggers/indexes, but guards attached to
        # files/tasks remain as detectable residue. Startup must not silently
        # create a fresh empty ledger and erase the tamper signal.
        conn.execute("DROP TABLE artifact_outcome_events")
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'trigger' "
            "AND name LIKE 'trg_witnessed_artifact_%'"
        ).fetchone()[0] > 0
    finally:
        conn.close()

    with pytest.raises(sqlite3.IntegrityError, match="residue"):
        init_db(outcome_db)


def test_full_download_records_only_after_complete_200_body(app_env) -> None:
    client, app = app_env
    task_id = f"task_{uuid.uuid4().hex}"
    content = b"authoritative signed artifact"
    path = app.state.task_runs_dir / task_id / "artifact.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    conn = app.state.conn_factory()
    try:
        _create_task(conn, task_id)
        file_id = _attach_output(conn, task_id, path=path, content=content)
        _approve(conn, task_id)
    finally:
        conn.close()

    assert client.get(f"/api/files/{file_id}/preview").status_code == 200
    assert client.get(
        f"/api/files/{file_id}/download", headers={"Range": "bytes=0-3"}
    ).status_code == 206
    # If-Range mismatch makes Starlette send a simple 200 body, but the mere
    # presence of Range keeps this request outside full_download semantics.
    if_range = client.get(
        f"/api/files/{file_id}/download",
        headers={"Range": "bytes=0-3", "If-Range": '"stale-validator"'},
    )
    assert if_range.status_code == 200
    assert if_range.content == content
    # FastAPI/Starlette 版本可能返回 200 空正文或 405；任一都不得记完整交付。
    assert client.head(f"/api/files/{file_id}/download").status_code in {200, 405}
    conn = app.state.conn_factory()
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM artifact_outcome_events WHERE event_type = 'full_download'"
        ).fetchone()[0] == 0
    finally:
        conn.close()

    response_1 = client.get(f"/api/files/{file_id}/download")
    response_2 = client.get(f"/api/files/{file_id}/download")
    assert response_1.status_code == response_2.status_code == 200
    assert response_1.content == response_2.content == content
    conn = app.state.conn_factory()
    try:
        rows = conn.execute(
            "SELECT * FROM artifact_outcome_events "
            "WHERE event_type = 'full_download' ORDER BY rowid"
        ).fetchall()
        assert len(rows) == 2  # repeated real deliveries are not deduplicated
        assert {row["source_task_id"] for row in rows} == {task_id}
        assert {row["source_file_id"] for row in rows} == {file_id}
        assert {row["actor_username"] for row in rows} == {TEST_USERNAME}
        assert {row["delivered_bytes"] for row in rows} == {len(content)}
    finally:
        conn.close()


def test_download_post_send_capture_failure_does_not_change_delivered_response(
    app_env, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    client, app = app_env
    task_id = f"task_{uuid.uuid4().hex}"
    content = b"already delivered"
    path = app.state.task_runs_dir / task_id / "artifact.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    conn = app.state.conn_factory()
    try:
        _create_task(conn, task_id)
        file_id = _attach_output(conn, task_id, path=path, content=content)
        _approve(conn, task_id)
    finally:
        conn.close()

    def fail_capture(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(repos, "record_full_download_outcome", fail_capture)
    response = client.get(f"/api/files/{file_id}/download")
    assert response.status_code == 200
    assert response.content == content
    assert "artifact_outcome_capture_failed" in caplog.text
    assert "post_send_db_failure" in caplog.text


def test_interrupted_simple_send_never_calls_post_send_capture(tmp_path: Path) -> None:
    path = tmp_path / "artifact.bin"
    path.write_bytes(b"123456")
    calls: list[int] = []
    handle = path.open("rb")
    response = _VerifiedFileResponse(
        handle,
        path=str(path),
        filename=path.name,
        expected_full_bytes=6,
        on_full_body_sent=calls.append,
    )

    async def send(message):
        if message["type"] == "http.response.body":
            raise ConnectionError("client disconnected")

    async def exercise() -> None:
        with pytest.raises(ConnectionError):
            await response._handle_simple(send, False, False)

    try:
        anyio.run(exercise)
    finally:
        handle.close()
    assert calls == []


def test_exact_chunk_final_empty_terminator_failure_is_not_full_delivery(
    tmp_path: Path,
) -> None:
    path = tmp_path / "exact-chunk.bin"
    path.write_bytes(b"123456")
    calls: list[int] = []
    handle = path.open("rb")
    response = _VerifiedFileResponse(
        handle,
        path=str(path),
        filename=path.name,
        expected_full_bytes=6,
        on_full_body_sent=calls.append,
    )
    response.chunk_size = 6
    body_sends = 0

    async def send(message):
        nonlocal body_sends
        if message["type"] == "http.response.body":
            body_sends += 1
            if body_sends == 2:  # final empty more_body=False terminator
                raise ConnectionError("disconnect before terminator ack")

    async def exercise() -> None:
        with pytest.raises(ConnectionError):
            await response._handle_simple(send, False, False)

    try:
        anyio.run(exercise)
    finally:
        handle.close()
    assert body_sends == 2
    assert calls == []


def test_pipeline_handoff_is_atomic_and_exact_for_captured_piped_files(
    outcome_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = get_conn(outcome_db)
    try:
        _create_task(conn, "upstream")
        file_id = _attach_output(conn, "upstream")
        review_event_id = _approve(conn, "upstream")
        _create_task(conn, "downstream", depends_on=["upstream"])
    finally:
        conn.close()
    assert resolve_dependencies_once(lambda: get_conn(outcome_db)) == 1
    conn = get_conn(outcome_db)
    try:
        row = conn.execute(
            "SELECT * FROM artifact_outcome_events WHERE event_type = 'pipeline_handoff'"
        ).fetchone()
        assert row is not None
        assert row["source_task_id"] == "upstream"
        assert row["source_file_id"] == file_id
        assert row["review_event_id"] == review_event_id
        assert row["downstream_task_id"] == "downstream"
        assert row["actor_username"] is None
        assert row["delivered_bytes"] is None

        # A file already present before this enqueue call is not transferred by
        # this resolver action, so it must not acquire a new handoff fact.
        _create_task(
            conn,
            "downstream-preexisting",
            depends_on=["upstream"],
            input_file_ids=[file_id],
        )
        repos.enqueue_dependent_task(conn, "downstream-preexisting", [file_id])
        assert conn.execute(
            "SELECT COUNT(*) FROM artifact_outcome_events "
            "WHERE event_type = 'pipeline_handoff' "
            "AND downstream_task_id = 'downstream-preexisting'"
        ).fetchone()[0] == 0

        _create_task(conn, "downstream-rollback", depends_on=["upstream"])
        original = repos.append_artifact_outcome_event

        def fail_pipeline(*args, **kwargs):
            if kwargs.get("event_type") == "pipeline_handoff":
                raise sqlite3.IntegrityError("injected telemetry failure")
            return original(*args, **kwargs)

        monkeypatch.setattr(repos, "append_artifact_outcome_event", fail_pipeline)
        with pytest.raises(sqlite3.IntegrityError):
            repos.enqueue_dependent_task(conn, "downstream-rollback", [file_id])
        rolled_back = repos.get_task(conn, "downstream-rollback")
        assert rolled_back["status"] == "created"
        assert rolled_back["input_file_ids"] == []
        assert conn.execute(
            "SELECT COUNT(*) FROM artifact_outcome_events "
            "WHERE event_type = 'pipeline_handoff' AND downstream_task_id = 'downstream-rollback'"
        ).fetchone()[0] == 0
    finally:
        conn.close()


def test_deterministic_unsigned_legal_pipeline_still_flows_without_fake_outcome(
    outcome_db: Path,
) -> None:
    conn = get_conn(outcome_db)
    try:
        manifest = {
            "id": "hello_agent",
            "version": "0.1.0",
            "model": {"profile": "none"},
            "workflow": {"mode": "job", "requires_human_review": False},
        }
        conn.execute(
            "INSERT INTO agent_versions "
            "(agent_id, version, yaml_json, created_at) VALUES (?,?,?,?)",
            (
                "hello_agent",
                "0.1.0",
                json.dumps(manifest),
                "2026-07-19T00:00:00+00:00",
            ),
        )
        _create_task(conn, "deterministic-source")
        file_id = _attach_output(conn, "deterministic-source")
        for status in ("queued", "validating", "running", "analyzing", "completed"):
            repos.set_task_status(conn, "deterministic-source", status)
        _create_task(
            conn,
            "deterministic-downstream",
            depends_on=["deterministic-source"],
        )
    finally:
        conn.close()

    assert resolve_dependencies_once(lambda: get_conn(outcome_db)) == 1
    conn = get_conn(outcome_db)
    try:
        downstream = repos.get_task(conn, "deterministic-downstream")
        assert downstream["status"] == "queued"
        assert downstream["input_file_ids"] == [file_id]
        assert conn.execute(
            "SELECT COUNT(*) FROM artifact_outcome_events"
        ).fetchone()[0] == 0
    finally:
        conn.close()
