"""Issue #75 canonical Generalization Draft Record storage contract."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from backend.app.storage import repos
from backend.app.storage.db import get_conn, init_db
from backend.app.runtime.generalization_draft_record import (
    create_generalization_draft_record,
    load_verified_generalization_draft_record,
    project_conversation_messages,
)


def _payload() -> dict:
    return {
        "title": "  Cafe\u0301  检查  ",
        "trigger": "收到试验异常",
        "desired_outcome": "形成可复核结论",
        "inputs": ["试验记录"],
        "outputs": ["检查说明"],
        "steps": ["核对来源", "形成草稿"],
        "evidence_requirements": ["原始记录位置"],
        "human_decision_points": ["工程师复核"],
        "limitations": ["不得替代签发"],
    }


def test_fresh_init_creates_empty_immutable_record_ledger(tmp_path) -> None:
    db_path = tmp_path / "draft-record.sqlite3"

    init_db(db_path)

    conn = get_conn(db_path)
    try:
        columns = [
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(generalization_draft_records)"
            ).fetchall()
        ]
        objects = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE tbl_name = 'generalization_draft_records'"
            ).fetchall()
        }
        count = conn.execute(
            "SELECT COUNT(*) FROM generalization_draft_records"
        ).fetchone()[0]
    finally:
        conn.close()

    assert columns == [
        "id",
        "schema_version",
        "payload_schema_version",
        "state",
        "review_status",
        "payload_json",
        "content_digest",
        "record_digest",
        "source_context_json",
        "source_context_digest",
        "conversation_id",
        "owner_username",
        "source_user_message_id",
        "source_assistant_message_id",
        "source_task_id",
        "model_call_id",
        "model_call_kind",
        "model_profile",
        "model_name",
        "model_agent_id",
        "agent_version",
        "created_at",
    ]
    assert objects == {
        "generalization_draft_records",
        "sqlite_autoindex_generalization_draft_records_1",
        "sqlite_autoindex_generalization_draft_records_2",
        "sqlite_autoindex_generalization_draft_records_3",
        "sqlite_autoindex_generalization_draft_records_4",
        "sqlite_autoindex_generalization_draft_records_5",
        "trg_generalization_draft_records_no_update",
        "trg_generalization_draft_records_no_delete",
        "idx_generalization_draft_records_conversation_message",
        "idx_generalization_draft_records_source_task",
    }
    assert count == 0


def test_message_repository_exposes_stable_public_integer_id(tmp_path) -> None:
    db_path = tmp_path / "message-id.sqlite3"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        repos.create_conversation(
            conn,
            conversation_id="conv_public_message_id",
            agent_id="life_guide_agent",
            created_by="Owner",
            created_by_username="owner",
        )

        created = repos.append_message(
            conn,
            conversation_id="conv_public_message_id",
            role="user",
            content="一次真实工作",
        )
        reloaded = repos.list_messages(conn, "conv_public_message_id")
    finally:
        conn.close()

    assert isinstance(created["id"], int)
    assert created["id"] > 0
    assert reloaded == [created]


def test_create_cold_load_and_message_projection_share_one_canonical_record(
    tmp_path,
) -> None:
    db_path = tmp_path / "record-roundtrip.sqlite3"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        repos.create_conversation(
            conn,
            conversation_id="conv_record_roundtrip",
            agent_id="life_guide_agent",
            created_by="Owner",
            created_by_username="owner",
        )
        user_message = repos.append_message(
            conn,
            conversation_id="conv_record_roundtrip",
            role="user",
            content="这是一次工作",
        )
        assistant_message = repos.append_message(
            conn,
            conversation_id="conv_record_roundtrip",
            role="assistant",
            content="已形成待审草稿",
        )
        receipt = repos.record_model_call(
            conn,
            conversation_id="conv_record_roundtrip",
            agent_id="life_guide_agent",
            model_profile="deep_reasoning",
            model_name="test-model",
            status="success",
        )
        exact_chat_receipt = {
            "model_call_id": receipt["id"],
            "kind": "chat",
            "status": receipt["status"],
            "task_id": receipt["task_id"],
            "conversation_id": receipt["conversation_id"],
            "agent_id": receipt["agent_id"],
            "model_profile": receipt["model_profile"],
            "model_name": receipt["model_name"],
        }

        conn.execute("BEGIN IMMEDIATE")
        created = create_generalization_draft_record(
            conn,
            payload=_payload(),
            conversation_id="conv_record_roundtrip",
            owner_username="owner",
            source_user_message_id=user_message["id"],
            source_assistant_message_id=assistant_message["id"],
            model_call_receipt=exact_chat_receipt,
            agent_version="1.0.0",
        )
        conn.execute("COMMIT")

        loaded = load_verified_generalization_draft_record(
            conn,
            conversation_id="conv_record_roundtrip",
            record_id=created["id"],
            owner_username="owner",
        )
        projected = project_conversation_messages(
            conn,
            messages=repos.list_messages(conn, "conv_record_roundtrip"),
            conversation_id="conv_record_roundtrip",
            owner_username="owner",
        )
    finally:
        conn.close()

    assert created["payload"]["title"] == "Caf\u00e9  检查"
    assert loaded["public_record"] == created
    assert loaded["payload"] == created["payload"]
    assert loaded["source_context"]["conversation"]["messages"][-1]["id"] == (
        assistant_message["id"]
    )
    assert "generalization_draft_record" not in projected[0]
    assert projected[1]["generalization_draft_record"] == created
    schema = json.loads(
        (Path(__file__).parents[2] / "contracts/generalization_draft_record.schema.json")
        .read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(created)
