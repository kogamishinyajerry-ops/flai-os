"""Canonical, server-owned Generalization Draft Record evidence.

Issue #75 deliberately keeps this module below the HTTP layer.  Callers own
the surrounding SQLite transaction; every public projection in this module is
derived from a cold read of the immutable ledger.
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from ..core.canonical_digest import canonical_digest
from ..storage import repos


RECORD_SCHEMA_VERSION = "generalization_draft_record.v1"
PAYLOAD_SCHEMA_VERSION = "life_generalization.v1"
SOURCE_CONTEXT_SCHEMA_VERSION = "asset_draft_source_context.v1"

_GENERALIZATION_FIELDS = (
    "title",
    "trigger",
    "desired_outcome",
    "inputs",
    "outputs",
    "steps",
    "evidence_requirements",
    "human_decision_points",
    "limitations",
)
_SCALAR_FIELDS = frozenset({"title", "trigger", "desired_outcome"})
_SCALAR_LIMITS = {"title": 160, "trigger": 2000, "desired_outcome": 2000}
_LIST_MAX_ITEMS = 20
_LIST_ITEM_MAX_CHARS = 1000
_HEX_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_RECORD_ID = re.compile(r"^gdr_[0-9a-f]{32}$")

_STORAGE_KEYS = frozenset(
    {
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
    }
)


class GeneralizationDraftPayloadError(ValueError):
    """A model-authored nine-field payload is not safe to persist."""


class GeneralizationDraftRecordIntegrityError(RuntimeError):
    """Persisted draft evidence does not satisfy its canonical bindings."""


class GeneralizationDraftRecordNotFoundError(LookupError):
    """No owner-visible record exists at the requested identity."""


def normalize_generalization_draft_payload(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact NFC nine-field payload or reject it fail-closed."""
    if not isinstance(raw, Mapping):
        raise GeneralizationDraftPayloadError("generalization_draft 必须是对象")
    if any(not isinstance(key, str) for key in raw):
        raise GeneralizationDraftPayloadError("generalization_draft 字段名必须是字符串")
    actual = set(raw)
    required = set(_GENERALIZATION_FIELDS)
    unknown = sorted(actual - required)
    missing = sorted(required - actual)
    if unknown:
        raise GeneralizationDraftPayloadError(
            f"generalization_draft 含未知字段：{', '.join(unknown)}"
        )
    if missing:
        raise GeneralizationDraftPayloadError(
            f"generalization_draft 缺少字段：{', '.join(missing)}"
        )

    normalized: dict[str, Any] = {}
    for field in _GENERALIZATION_FIELDS:
        value = raw[field]
        if field in _SCALAR_FIELDS:
            if not isinstance(value, str):
                raise GeneralizationDraftPayloadError(f"{field} 必须是字符串")
            if len(value) > _SCALAR_LIMITS[field]:
                raise GeneralizationDraftPayloadError(f"{field} 超过字符上限")
            text = _normalize_text(value, field)
            if not text or len(text) > _SCALAR_LIMITS[field]:
                raise GeneralizationDraftPayloadError(f"{field} 不得为空或超过字符上限")
            normalized[field] = text
            continue

        if not isinstance(value, list):
            raise GeneralizationDraftPayloadError(f"{field} 必须是字符串数组")
        minimum = 2 if field == "steps" else 1
        if not minimum <= len(value) <= _LIST_MAX_ITEMS:
            raise GeneralizationDraftPayloadError(
                f"{field} 必须包含 {minimum} 至 {_LIST_MAX_ITEMS} 项"
            )
        items: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise GeneralizationDraftPayloadError(f"{field} 必须是字符串数组")
            if len(item) > _LIST_ITEM_MAX_CHARS:
                raise GeneralizationDraftPayloadError(f"{field} 数组项超过字符上限")
            text = _normalize_text(item, field)
            if not text or len(text) > _LIST_ITEM_MAX_CHARS:
                raise GeneralizationDraftPayloadError(
                    f"{field} 数组项不得为空或超过字符上限"
                )
            items.append(text)
        normalized[field] = items

    # Exercise the shared value contract now, before any SQL side effect.
    _canonical_json_text(normalized)
    canonical_digest(normalized)
    return normalized


def create_generalization_draft_record(
    conn: sqlite3.Connection,
    *,
    payload: Mapping[str, Any],
    conversation_id: str,
    owner_username: str,
    source_user_message_id: int,
    source_assistant_message_id: int,
    model_call_receipt: Mapping[str, Any],
    agent_version: str,
) -> dict[str, Any]:
    """Build, insert and cold-verify one record in the caller's transaction."""
    if not conn.in_transaction:
        raise GeneralizationDraftRecordIntegrityError(
            "draft record creation requires the active round transaction"
        )
    normalized_payload = normalize_generalization_draft_payload(payload)
    conversation = repos.get_conversation(conn, conversation_id)
    current_owner = repos.get_conversation_owner_username(conn, conversation_id)
    if conversation is None:
        raise GeneralizationDraftRecordIntegrityError("source conversation is missing")
    _require_owner(owner_username)
    if current_owner != owner_username:
        raise GeneralizationDraftRecordIntegrityError(
            "source conversation owner binding mismatch"
        )
    agent_id = conversation.get("agent_id")
    if agent_id != "life_guide_agent":
        raise GeneralizationDraftRecordIntegrityError("source agent id is invalid")
    version = _require_nonblank(agent_version, "agent_version")

    receipt = _verify_exact_model_receipt(
        conn,
        model_call_receipt,
        conversation_id=conversation_id,
        agent_id=agent_id,
    )
    source_context = _build_source_context(
        conn,
        conversation_id=conversation_id,
        source_user_message_id=source_user_message_id,
        source_assistant_message_id=source_assistant_message_id,
        creation_status=conversation.get("status"),
    )
    payload_json = _canonical_json_text(normalized_payload)
    source_context_json = _canonical_json_text(source_context)
    content_digest = canonical_digest(
        {
            "payload_schema_version": PAYLOAD_SCHEMA_VERSION,
            "payload": normalized_payload,
        }
    )
    source_context_digest = canonical_digest(source_context)
    record_id = f"gdr_{uuid.uuid4().hex}"
    created_at = datetime.now(timezone.utc).isoformat()
    storage_record: dict[str, Any] = {
        "id": record_id,
        "schema_version": RECORD_SCHEMA_VERSION,
        "payload_schema_version": PAYLOAD_SCHEMA_VERSION,
        "state": "model_draft",
        "review_status": "waiting_review",
        "payload_json": payload_json,
        "content_digest": content_digest,
        "record_digest": "",
        "source_context_json": source_context_json,
        "source_context_digest": source_context_digest,
        "conversation_id": conversation_id,
        "owner_username": owner_username,
        "source_user_message_id": source_user_message_id,
        "source_assistant_message_id": source_assistant_message_id,
        "source_task_id": None,
        "model_call_id": receipt["id"],
        "model_call_kind": "chat",
        "model_profile": receipt["model_profile"],
        "model_name": receipt["model_name"],
        "model_agent_id": receipt["agent_id"],
        "agent_version": version,
        "created_at": created_at,
    }
    storage_record["record_digest"] = canonical_digest(
        _record_digest_basis(
            storage_record,
            payload=normalized_payload,
            source_context=source_context,
        )
    )
    try:
        repos.insert_generalization_draft_record(
            conn, storage_record=storage_record
        )
    except (sqlite3.IntegrityError, ValueError) as exc:
        raise GeneralizationDraftRecordIntegrityError(
            "canonical draft record INSERT violated its ledger contract"
        ) from exc
    verified = _verify_storage_record(conn, storage_record)
    return verified["public_record"]


def load_verified_generalization_draft_record(
    conn: sqlite3.Connection,
    *,
    conversation_id: str,
    record_id: str,
    owner_username: str,
) -> dict[str, Any]:
    """Load owner-visible evidence, then cold-verify every canonical binding."""
    row = repos.get_generalization_draft_record_storage(conn, record_id=record_id)
    current_owner = repos.get_conversation_owner_username(conn, conversation_id)
    if (
        row is None
        or current_owner != owner_username
        or row.get("conversation_id") != conversation_id
        or row.get("owner_username") != owner_username
    ):
        raise GeneralizationDraftRecordNotFoundError(record_id)
    return _verify_storage_record(conn, row)


def project_conversation_message(
    conn: sqlite3.Connection,
    *,
    message: Mapping[str, Any],
    conversation_id: str,
    owner_username: str,
) -> dict[str, Any]:
    public = dict(message)
    public.pop("generalization_draft_record", None)
    message_id = public.get("id")
    role = public.get("role")
    if not isinstance(message_id, int) or isinstance(message_id, bool):
        raise GeneralizationDraftRecordIntegrityError("message has no public integer id")
    if public.get("conversation_id") != conversation_id:
        raise GeneralizationDraftRecordIntegrityError(
            "message does not belong to the projected conversation"
        )
    if role == "user":
        return public
    if role != "assistant":
        raise GeneralizationDraftRecordIntegrityError("unsupported conversation role")

    row = repos.get_generalization_draft_record_storage_by_assistant_message(
        conn, assistant_message_id=message_id
    )
    if row is None:
        public["generalization_draft_record"] = None
        return public
    if (
        row.get("conversation_id") != conversation_id
        or row.get("owner_username") != owner_username
    ):
        raise GeneralizationDraftRecordIntegrityError(
            "assistant draft record crosses its authorized conversation"
        )
    verified = _verify_storage_record(conn, row)
    record = verified["public_record"]
    if record["lineage"]["assistant_message_id"] != message_id:
        raise GeneralizationDraftRecordIntegrityError(
            "assistant draft record lineage does not match its message"
        )
    public["generalization_draft_record"] = record
    return public


def project_conversation_messages(
    conn: sqlite3.Connection,
    *,
    messages: Sequence[Mapping[str, Any]],
    conversation_id: str,
    owner_username: str,
) -> list[dict[str, Any]]:
    return [
        project_conversation_message(
            conn,
            message=message,
            conversation_id=conversation_id,
            owner_username=owner_username,
        )
        for message in messages
    ]


def _normalize_text(value: str, field: str) -> str:
    # The payload contract normalizes Unicode and trims only the outer boundary.
    # Internal spaces/newlines are meaningful engineering content and survive.
    normalized = unicodedata.normalize("NFC", value).strip()
    try:
        normalized.encode("utf-8")
    except UnicodeError as exc:
        raise GeneralizationDraftPayloadError(f"{field} 包含无效 Unicode") from exc
    return normalized


def _stable_value(value: Any) -> Any:
    """Mirror backend.app.core.canonical_digest's NFC value contract."""
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise GeneralizationDraftRecordIntegrityError(
                "canonical object keys must be strings"
            )
        return {
            unicodedata.normalize("NFC", key): _stable_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_stable_value(item) for item in value]
    if isinstance(value, tuple):
        return [_stable_value(item) for item in value]
    if isinstance(value, str):
        normalized = unicodedata.normalize("NFC", value)
        try:
            normalized.encode("utf-8")
        except UnicodeError as exc:
            raise GeneralizationDraftRecordIntegrityError(
                "canonical value contains invalid Unicode"
            ) from exc
        return normalized
    if value is None or isinstance(value, (bool, int)):
        return value
    if (
        isinstance(value, float)
        and value == value
        and value not in (float("inf"), float("-inf"))
    ):
        return value
    raise GeneralizationDraftRecordIntegrityError(
        f"unsupported canonical value type: {type(value).__name__}"
    )


def _canonical_json_text(value: Any) -> str:
    try:
        return json.dumps(
            _stable_value(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, UnicodeError) as exc:
        raise GeneralizationDraftRecordIntegrityError(
            "value cannot be encoded as canonical JSON"
        ) from exc


def _parse_canonical_object(raw: Any, field: str) -> dict[str, Any]:
    if not isinstance(raw, str):
        raise GeneralizationDraftRecordIntegrityError(f"{field} is not JSON text")

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant: {value}")

    try:
        parsed = json.loads(raw, parse_constant=reject_constant)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise GeneralizationDraftRecordIntegrityError(f"{field} is invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise GeneralizationDraftRecordIntegrityError(f"{field} must be a JSON object")
    if raw != _canonical_json_text(parsed):
        raise GeneralizationDraftRecordIntegrityError(f"{field} is not canonical JSON")
    return parsed


def _require_nonblank(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or unicodedata.normalize("NFC", value) != value
    ):
        raise GeneralizationDraftRecordIntegrityError(f"{field} is not canonical text")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise GeneralizationDraftRecordIntegrityError(
            f"{field} contains invalid Unicode"
        ) from exc
    return value


def _require_owner(value: Any) -> str:
    owner = _require_nonblank(value, "owner_username")
    if len(owner) > 128:
        raise GeneralizationDraftRecordIntegrityError("owner_username exceeds limit")
    return owner


def _verify_exact_model_receipt(
    conn: sqlite3.Connection,
    receipt: Mapping[str, Any],
    *,
    conversation_id: str,
    agent_id: str,
) -> dict[str, Any]:
    if not isinstance(receipt, Mapping):
        raise GeneralizationDraftRecordIntegrityError("model receipt must be an object")
    receipt_keys = {
        "model_call_id",
        "kind",
        "status",
        "task_id",
        "conversation_id",
        "agent_id",
        "model_profile",
        "model_name",
    }
    if set(receipt) != receipt_keys:
        raise GeneralizationDraftRecordIntegrityError(
            "model receipt envelope has wrong keys"
        )
    receipt_id = receipt.get("model_call_id")
    if not isinstance(receipt_id, int) or isinstance(receipt_id, bool) or receipt_id <= 0:
        raise GeneralizationDraftRecordIntegrityError("model receipt id is invalid")
    stored = repos.get_model_call(conn, receipt_id)
    if stored is None:
        raise GeneralizationDraftRecordIntegrityError("exact model receipt is missing")
    fields = ("task_id", "conversation_id", "agent_id", "model_profile", "model_name", "status")
    if any(receipt.get(field) != stored.get(field) for field in fields):
        raise GeneralizationDraftRecordIntegrityError("model receipt does not match its row")
    if (
        receipt.get("kind") != "chat"
        or
        stored.get("task_id") is not None
        or stored.get("conversation_id") != conversation_id
        or stored.get("agent_id") != agent_id
        or stored.get("status") != "success"
    ):
        raise GeneralizationDraftRecordIntegrityError(
            "model receipt is not the successful conversation chat receipt"
        )
    _require_nonblank(stored.get("model_profile"), "model_profile")
    _require_nonblank(stored.get("model_name"), "model_name")
    _require_nonblank(stored.get("agent_id"), "model_agent_id")
    return stored


def _project_source_message(message: Mapping[str, Any]) -> dict[str, Any]:
    message_id = message.get("id")
    role = message.get("role")
    content = message.get("content")
    file_ids = message.get("file_ids")
    recommendation = message.get("recommendation")
    if not isinstance(message_id, int) or isinstance(message_id, bool):
        raise GeneralizationDraftRecordIntegrityError("source message id is invalid")
    if role not in {"user", "assistant"} or not isinstance(content, str):
        raise GeneralizationDraftRecordIntegrityError("source message body is invalid")
    if not isinstance(file_ids, list) or any(
        not isinstance(file_id, str) for file_id in file_ids
    ):
        raise GeneralizationDraftRecordIntegrityError("source file_ids are invalid")
    if recommendation is not None and not isinstance(recommendation, dict):
        raise GeneralizationDraftRecordIntegrityError(
            "source recommendation projection is invalid"
        )
    return {
        "id": message_id,
        "role": role,
        "content": content,
        "file_ids": list(file_ids),
        "recommendation": recommendation,
    }


def _build_source_context(
    conn: sqlite3.Connection,
    *,
    conversation_id: str,
    source_user_message_id: int,
    source_assistant_message_id: int,
    creation_status: Any,
) -> dict[str, Any]:
    for field, value in (
        ("source_user_message_id", source_user_message_id),
        ("source_assistant_message_id", source_assistant_message_id),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise GeneralizationDraftRecordIntegrityError(f"{field} is invalid")
    if source_user_message_id == source_assistant_message_id:
        raise GeneralizationDraftRecordIntegrityError(
            "source user and assistant message ids must differ"
        )
    conversation = repos.get_conversation(conn, conversation_id)
    if conversation is None:
        raise GeneralizationDraftRecordIntegrityError("source conversation is missing")
    agent_id = _require_nonblank(conversation.get("agent_id"), "conversation.agent_id")
    status = _require_nonblank(creation_status, "conversation.status")
    try:
        messages = repos.list_messages_through_id(
            conn,
            conversation_id,
            end_message_id=source_assistant_message_id,
        )
    except (TypeError, ValueError, UnicodeError) as exc:
        raise GeneralizationDraftRecordIntegrityError(
            "source message prefix cannot be decoded"
        ) from exc
    assistant_positions = [
        index
        for index, message in enumerate(messages)
        if message.get("id") == source_assistant_message_id
    ]
    if len(assistant_positions) != 1:
        raise GeneralizationDraftRecordIntegrityError(
            "source assistant message is missing or ambiguous"
        )
    prefix = messages[: assistant_positions[0] + 1]
    if (
        len(prefix) < 2
        or prefix[-2].get("id") != source_user_message_id
        or prefix[-2].get("role") != "user"
        or prefix[-1].get("role") != "assistant"
    ):
        raise GeneralizationDraftRecordIntegrityError(
            "source user/assistant round lineage is invalid"
        )
    projected = [_project_source_message(message) for message in prefix]
    return _stable_value(
        {
            "schema_version": SOURCE_CONTEXT_SCHEMA_VERSION,
            "conversation": {
                "id": conversation_id,
                "agent_id": agent_id,
                "status": status,
                "messages": projected,
            },
        }
    )


def _record_digest_basis(
    storage: Mapping[str, Any], *, payload: Mapping[str, Any], source_context: Mapping[str, Any]
) -> dict[str, Any]:
    """Enumerate every stored field except the digest itself, parsing JSON bodies."""
    return {
        "id": storage["id"],
        "schema_version": storage["schema_version"],
        "payload_schema_version": storage["payload_schema_version"],
        "state": storage["state"],
        "review_status": storage["review_status"],
        "payload_json": payload,
        "content_digest": storage["content_digest"],
        "source_context_json": source_context,
        "source_context_digest": storage["source_context_digest"],
        "conversation_id": storage["conversation_id"],
        "owner_username": storage["owner_username"],
        "source_user_message_id": storage["source_user_message_id"],
        "source_assistant_message_id": storage["source_assistant_message_id"],
        "source_task_id": storage["source_task_id"],
        "model_call_id": storage["model_call_id"],
        "model_call_kind": storage["model_call_kind"],
        "model_profile": storage["model_profile"],
        "model_name": storage["model_name"],
        "model_agent_id": storage["model_agent_id"],
        "agent_version": storage["agent_version"],
        "created_at": storage["created_at"],
    }


def _verify_storage_record(
    conn: sqlite3.Connection, storage: Mapping[str, Any]
) -> dict[str, Any]:
    if set(storage) != _STORAGE_KEYS:
        raise GeneralizationDraftRecordIntegrityError("record storage keys are invalid")
    record_id = storage.get("id")
    if not isinstance(record_id, str) or _RECORD_ID.fullmatch(record_id) is None:
        raise GeneralizationDraftRecordIntegrityError("record id is invalid")
    if (
        storage.get("schema_version") != RECORD_SCHEMA_VERSION
        or storage.get("payload_schema_version") != PAYLOAD_SCHEMA_VERSION
        or storage.get("state") != "model_draft"
        or storage.get("review_status") != "waiting_review"
        or storage.get("source_task_id") is not None
        or storage.get("model_call_kind") != "chat"
    ):
        raise GeneralizationDraftRecordIntegrityError("record constants are invalid")
    for field in ("content_digest", "record_digest", "source_context_digest"):
        value = storage.get(field)
        if not isinstance(value, str) or _HEX_DIGEST.fullmatch(value) is None:
            raise GeneralizationDraftRecordIntegrityError(f"{field} is invalid")
    owner = _require_owner(storage.get("owner_username"))
    conversation_id = _require_nonblank(
        storage.get("conversation_id"), "conversation_id"
    )
    agent_version = _require_nonblank(storage.get("agent_version"), "agent_version")
    created_at = _require_nonblank(storage.get("created_at"), "created_at")
    try:
        parsed_time = datetime.fromisoformat(created_at)
    except ValueError as exc:
        raise GeneralizationDraftRecordIntegrityError("created_at is invalid") from exc
    if parsed_time.tzinfo is None or parsed_time.utcoffset() is None:
        raise GeneralizationDraftRecordIntegrityError("created_at must be timezone-aware")

    payload = _parse_canonical_object(storage.get("payload_json"), "payload_json")
    try:
        normalized_payload = normalize_generalization_draft_payload(payload)
    except GeneralizationDraftPayloadError as exc:
        raise GeneralizationDraftRecordIntegrityError(
            "stored payload violates the nine-field contract"
        ) from exc
    if normalized_payload != payload:
        raise GeneralizationDraftRecordIntegrityError("stored payload is not normalized")
    if storage["content_digest"] != canonical_digest(
        {
            "payload_schema_version": PAYLOAD_SCHEMA_VERSION,
            "payload": payload,
        }
    ):
        raise GeneralizationDraftRecordIntegrityError("content digest mismatch")

    source_context = _parse_canonical_object(
        storage.get("source_context_json"), "source_context_json"
    )
    if set(source_context) != {"schema_version", "conversation"} or (
        source_context.get("schema_version") != SOURCE_CONTEXT_SCHEMA_VERSION
    ):
        raise GeneralizationDraftRecordIntegrityError("source context envelope is invalid")
    context_conversation = source_context.get("conversation")
    if not isinstance(context_conversation, dict) or set(context_conversation) != {
        "id",
        "agent_id",
        "status",
        "messages",
    }:
        raise GeneralizationDraftRecordIntegrityError("source conversation is invalid")
    if context_conversation.get("id") != conversation_id:
        raise GeneralizationDraftRecordIntegrityError("source context conversation mismatch")
    expected_context = _build_source_context(
        conn,
        conversation_id=conversation_id,
        source_user_message_id=storage["source_user_message_id"],
        source_assistant_message_id=storage["source_assistant_message_id"],
        creation_status=context_conversation.get("status"),
    )
    if source_context != expected_context:
        raise GeneralizationDraftRecordIntegrityError("source message prefix drifted")
    if storage["source_context_digest"] != canonical_digest(source_context):
        raise GeneralizationDraftRecordIntegrityError("source context digest mismatch")

    conversation = repos.get_conversation(conn, conversation_id)
    if conversation is None or repos.get_conversation_owner_username(
        conn, conversation_id
    ) != owner:
        raise GeneralizationDraftRecordIntegrityError("conversation owner binding mismatch")
    if (
        conversation.get("agent_id") != "life_guide_agent"
        or storage.get("model_agent_id") != "life_guide_agent"
    ):
        raise GeneralizationDraftRecordIntegrityError("model agent lineage mismatch")
    model_call_id = storage.get("model_call_id")
    if not isinstance(model_call_id, int) or isinstance(model_call_id, bool):
        raise GeneralizationDraftRecordIntegrityError("model call id is invalid")
    model_call = repos.get_model_call(conn, model_call_id)
    if model_call is None or (
        model_call.get("task_id") is not None
        or model_call.get("conversation_id") != conversation_id
        or model_call.get("agent_id") != storage.get("model_agent_id")
        or model_call.get("model_profile") != storage.get("model_profile")
        or model_call.get("model_name") != storage.get("model_name")
        or model_call.get("status") != "success"
    ):
        raise GeneralizationDraftRecordIntegrityError("model receipt lineage mismatch")
    _require_nonblank(storage.get("model_profile"), "model_profile")
    _require_nonblank(storage.get("model_name"), "model_name")
    _require_nonblank(storage.get("model_agent_id"), "model_agent_id")

    expected_record_digest = canonical_digest(
        _record_digest_basis(
            storage, payload=payload, source_context=source_context
        )
    )
    if storage["record_digest"] != expected_record_digest:
        raise GeneralizationDraftRecordIntegrityError("record digest mismatch")

    public_record = {
        "id": record_id,
        "schema_version": RECORD_SCHEMA_VERSION,
        "payload_schema_version": PAYLOAD_SCHEMA_VERSION,
        "state": "model_draft",
        "review_status": "waiting_review",
        "payload": payload,
        "content_digest": storage["content_digest"],
        "record_digest": storage["record_digest"],
        "source_context_digest": storage["source_context_digest"],
        "model_attribution": {
            "model_call_id": model_call_id,
            "kind": "chat",
            "agent_id": storage["model_agent_id"],
            "agent_version": agent_version,
            "profile": storage["model_profile"],
            "model_name": storage["model_name"],
        },
        "lineage": {
            "conversation_id": conversation_id,
            "user_message_id": storage["source_user_message_id"],
            "assistant_message_id": storage["source_assistant_message_id"],
            "task_id": None,
        },
        "created_at": created_at,
    }
    return {
        "public_record": public_record,
        "payload": payload,
        "source_context": source_context,
    }
