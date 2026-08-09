"""life_guide_agent 待审候选的 canonical record 追溯链路测试。

/demo 草稿卡片的后端 canonical record 契约:
1. 完整 <<DRAFT>> 与两条消息原子持久化为 server-owned record;
   落库消息正文剥离草稿块;
2. 无完整草稿时 assistant record 为 null，残缺/额外字段 fail-closed;
3. 顶层 response-only sidecar 已删除，POST/GET/stream 共用同一投影;
4. 人审唯一签发：record 仍是 model_draft/waiting_review。

不用 LLM:stub gateway 注入方式同 test_m6(app.state.conversation_service
.model_gateway = stub);其余链路(登录/鉴权/Registry/事务落库)全真。
"""

from __future__ import annotations

import json
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import yaml
from fastapi.testclient import TestClient

from backend.app.runtime import conversation as conversation_runtime
from backend.app.runtime.conversation import _ConversationGatewayContext
from backend.app.runtime.registry import AgentRegistry
from backend.app.storage import repos
from conftest import TEST_USERNAME

_DRAFT_FIELDS = {
    "title": "家常红烧肉(带皮五花肉版)",
    "trigger": "家里想吃红烧肉 + 有 2 小时 + 有炒锅和炖锅",
    "desired_outcome": "一盘 4-6 人份、能咬动、咸淡合适的红烧肉",
    "inputs": ["带皮五花肉 500-700g", "冰糖", "生抽老抽料酒"],
    "outputs": ["一盘红烧肉"],
    "steps": ["切块焯水", "炒糖色到琥珀色下肉", "小火炖 50 分钟", "尝咸淡收汁"],
    "evidence_requirements": ["糖色琥珀色", "尝咸淡通过"],
    "human_decision_points": ["尝咸淡必须人工"],
    "limitations": ["不适用高压锅", "不适用其他肉类"],
}

_DRAFT_BLOCK = (
    "<<DRAFT>>\n" + json.dumps(_DRAFT_FIELDS, ensure_ascii=False) + "\n<<END>>"
)
_REPLY_WITH_DRAFT = f"素材够了,我来投影草稿。\n{_DRAFT_BLOCK}\n审核权在你手里。"
_REPLY_FOLLOWUP = "两个关键问题:糖焦具体是哪一步?成功证据还有什么?"


class _CannedStub:
    """固定回复的 stub gateway;签名对齐 workflow 直连 model_gateway.chat。"""

    def __init__(
        self,
        reply: str,
        conn_factory,
        *,
        chunks: list[str] | None = None,
        receipt_count: int = 1,
        receipt_kind: str = "chat",
        emit_receipts: bool = True,
        stored_status_after_receipt: str | None = None,
    ) -> None:
        self.reply = reply
        self.conn_factory = conn_factory
        self.chunks = chunks
        self.receipt_count = receipt_count
        self.receipt_kind = receipt_kind
        self.emit_receipts = emit_receipts
        self.stored_status_after_receipt = stored_status_after_receipt

    def chat(
        self, profile: str, messages: list[dict[str, Any]], **kwargs: Any
    ) -> dict[str, Any]:
        on_delta = kwargs.get("on_delta")
        if callable(on_delta):
            for chunk in self.chunks or [self.reply]:
                on_delta(chunk)
        sink = kwargs.get("_receipt_sink")
        for _ in range(self.receipt_count):
            conn = self.conn_factory()
            try:
                row = repos.record_model_call(
                    conn,
                    task_id=None,
                    conversation_id=kwargs.get("conversation_id"),
                    agent_id=kwargs.get("agent_id"),
                    model_profile=profile,
                    model_name="stub",
                    status="success",
                    request_summary="life draft test",
                    response_summary=self.reply[:128],
                )
            finally:
                conn.close()
            if self.emit_receipts and callable(sink):
                sink(
                    {
                        "model_call_id": row["id"],
                        "kind": self.receipt_kind,
                        "status": "success",
                        "task_id": None,
                        "conversation_id": kwargs.get("conversation_id"),
                        "agent_id": kwargs.get("agent_id"),
                        "model_profile": profile,
                        "model_name": "stub",
                    }
                )
            if self.stored_status_after_receipt is not None:
                conn = self.conn_factory()
                try:
                    conn.execute(
                        "UPDATE model_calls SET status = ? WHERE id = ?",
                        (self.stored_status_after_receipt, row["id"]),
                    )
                finally:
                    conn.close()
        return {
            "content": self.reply,
            "token_usage": None,
            "model_name": "stub",
            "finish_reason": "stop",
        }


class _ConcurrentCannedStub(_CannedStub):
    """Hold both model rounds until they share the same message baseline."""

    def __init__(self, reply: str, conn_factory) -> None:
        super().__init__(reply, conn_factory)
        self.barrier = threading.Barrier(2)

    def chat(
        self, profile: str, messages: list[dict[str, Any]], **kwargs: Any
    ) -> dict[str, Any]:
        result = super().chat(profile, messages, **kwargs)
        self.barrier.wait(timeout=10)
        return result


def _open_life_conversation(client: TestClient) -> str:
    resp = client.post("/api/conversations", json={"agent_id": "life_guide_agent"})
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _publish_life_agent_status(app, tmp_path: Path, status: str) -> None:
    snapshot = app.state.agent_registry.package_snapshot("life_guide_agent")
    assert snapshot is not None
    shadow_root = tmp_path / f"life-guide-{status}-shadow"
    shadow_root.mkdir()
    with snapshot.materialized(parent=tmp_path) as frozen_dir:
        package_dir = shadow_root / "life_guide_agent"
        shutil.copytree(frozen_dir, package_dir)
    yaml_path = package_dir / "agent.yaml"
    manifest = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    manifest["status"] = status
    yaml_path.write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    shadow = AgentRegistry(shadow_root, app.state.agent_registry.schema_path)
    shadow.scan()
    assert shadow.errors == []
    app.state.agent_registry.adopt(shadow)


def _publish_life_agent_version(app, tmp_path: Path, version: str) -> None:
    snapshot = app.state.agent_registry.package_snapshot("life_guide_agent")
    assert snapshot is not None
    shadow_root = tmp_path / f"life-guide-version-{version}-shadow"
    shadow_root.mkdir()
    with snapshot.materialized(parent=tmp_path) as frozen_dir:
        package_dir = shadow_root / "life_guide_agent"
        shutil.copytree(frozen_dir, package_dir)
    yaml_path = package_dir / "agent.yaml"
    manifest = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    manifest["version"] = version
    yaml_path.write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    shadow = AgentRegistry(shadow_root, app.state.agent_registry.schema_path)
    shadow.scan()
    assert shadow.errors == []
    app.state.agent_registry.adopt(shadow)


def _round_counts(app, conversation_id: str) -> dict[str, int]:
    conn = app.state.conn_factory()
    try:
        return {
            "messages": conn.execute(
                "SELECT COUNT(*) FROM conversation_messages WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()[0],
            "records": conn.execute(
                "SELECT COUNT(*) FROM generalization_draft_records "
                "WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()[0],
            "model_calls": conn.execute(
                "SELECT COUNT(*) FROM model_calls WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()[0],
            "task_events": conn.execute(
                "SELECT COUNT(*) FROM task_events"
            ).fetchone()[0],
        }
    finally:
        conn.close()


def test_complete_draft_is_persisted_and_projected_on_assistant_message(app_env) -> None:
    client, app = app_env
    app.state.conversation_service.model_gateway = _CannedStub(
        _REPLY_WITH_DRAFT, app.state.conn_factory
    )
    conv_id = _open_life_conversation(client)

    resp = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "上周六我做了红烧肉,糖焦了重来一次,女儿说好吃。"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert "generalization_draft" not in body, "禁止顶层 response-only sidecar"
    record = body["message"]["generalization_draft_record"]
    assert record["schema_version"] == "generalization_draft_record.v1"
    assert record["payload_schema_version"] == "life_generalization.v1"
    assert record["state"] == "model_draft"
    assert record["review_status"] == "waiting_review"
    assert record["payload"] == _DRAFT_FIELDS
    assert record["lineage"]["conversation_id"] == conv_id
    assert record["lineage"]["assistant_message_id"] == body["message"]["id"]
    assert record["lineage"]["task_id"] is None
    # 正文剥离草稿块:工程师看到的文字不含结构块原文
    assert "<<DRAFT>>" not in body["message"]["content"]
    assert "审核权在你手里" in body["message"]["content"]


def test_followup_round_yields_no_draft(app_env) -> None:
    client, app = app_env
    app.state.conversation_service.model_gateway = _CannedStub(
        _REPLY_FOLLOWUP, app.state.conn_factory
    )
    conv_id = _open_life_conversation(client)

    resp = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "我做了红烧肉。"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "generalization_draft" not in body
    assert body["message"]["generalization_draft_record"] is None


def test_incomplete_explicit_draft_fails_round_without_messages(app_env) -> None:
    client, app = app_env
    incomplete = {k: v for k, v in _DRAFT_FIELDS.items() if k != "limitations"}
    reply = (
        "我先投影一版。\n<<DRAFT>>\n"
        + json.dumps(incomplete, ensure_ascii=False)
        + "\n<<END>>"
    )
    app.state.conversation_service.model_gateway = _CannedStub(
        reply, app.state.conn_factory
    )
    conv_id = _open_life_conversation(client)

    resp = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "我做了红烧肉,过程略。"},
    )
    assert resp.status_code == 502, resp.text
    assert client.get(f"/api/conversations/{conv_id}").json()["messages"] == []


def test_post_and_get_share_the_same_persisted_assistant_projection(app_env) -> None:
    client, app = app_env
    app.state.conversation_service.model_gateway = _CannedStub(
        _REPLY_WITH_DRAFT, app.state.conn_factory
    )
    conv_id = _open_life_conversation(client)
    posted = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "上周六我做了红烧肉。"},
    )
    assert posted.status_code == 200, posted.text

    conv = client.get(f"/api/conversations/{conv_id}")
    assert conv.status_code == 200
    persisted = conv.json()
    assert "generalization_draft" not in persisted
    assert [msg["role"] for msg in persisted["messages"]] == ["user", "assistant"]
    assert "generalization_draft_record" not in persisted["messages"][0]
    assert persisted["messages"][1] == posted.json()["message"]
    assert persisted["messages"][1]["generalization_draft_record"]["payload"] == _DRAFT_FIELDS
    assert "<<DRAFT>>" not in persisted["messages"][1]["content"]


def test_life_delta_callback_observes_committed_messages_and_record(app_env) -> None:
    client, app = app_env
    app.state.conversation_service.model_gateway = _CannedStub(
        _REPLY_WITH_DRAFT,
        app.state.conn_factory,
        chunks=["素材够了。", _DRAFT_BLOCK, "审核权在你手里。"],
    )
    conv_id = _open_life_conversation(client)
    observations: list[dict[str, Any]] = []

    def observe_delta(text: str) -> None:
        persisted = app.state.conversation_service.get(conv_id)["messages"]
        observations.append(
            {
                "text": text,
                "counts": _round_counts(app, conv_id),
                "message": persisted[-1],
            }
        )

    result = app.state.conversation_service.post_message(
        conversation_id=conv_id,
        content="请投影草稿",
        actor_username=TEST_USERNAME,
        on_delta=observe_delta,
    )

    assert len(observations) == 1
    observed = observations[0]
    assert observed["counts"]["messages"] == 2
    assert observed["counts"]["records"] == 1
    assert observed["text"] == result["message"]["content"]
    assert observed["message"] == result["message"]
    assert observed["message"]["generalization_draft_record"] is not None


def test_workflow_cannot_replace_or_observe_runtime_receipt_sink() -> None:
    server_receipts: list[dict[str, Any]] = []
    workflow_receipts: list[dict[str, Any]] = []
    exact_receipt = {
        "model_call_id": 41,
        "kind": "chat",
        "status": "success",
        "task_id": None,
        "conversation_id": "conv_receipt",
        "agent_id": "life_guide_agent",
        "model_profile": "fast",
        "model_name": "stub",
    }

    class _Gateway:
        def chat(self, profile, messages, **kwargs):
            kwargs["_receipt_sink"](exact_receipt)
            return {
                "content": "ok",
                "model_call_receipt": {"must": "stay private"},
                "_model_call_receipt": {"must": "stay private too"},
            }

    context = _ConversationGatewayContext(
        _Gateway(), "conv_receipt", "life_guide_agent", server_receipts.append
    )
    result = context.chat(
        "fast", [], _receipt_sink=workflow_receipts.append
    )

    assert workflow_receipts == []
    assert server_receipts == [exact_receipt]
    assert "model_call_receipt" not in result
    assert "_model_call_receipt" not in result


def test_complete_draft_without_exact_receipt_rolls_back_messages_but_keeps_model_audit(
    app_env,
) -> None:
    client, app = app_env
    app.state.conversation_service.model_gateway = _CannedStub(
        _REPLY_WITH_DRAFT,
        app.state.conn_factory,
        receipt_count=1,
        emit_receipts=False,
    )
    conv_id = _open_life_conversation(client)

    response = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "请生成草稿"},
    )

    assert response.status_code == 503
    assert client.get(f"/api/conversations/{conv_id}").json()["messages"] == []
    calls = client.get(f"/api/conversations/{conv_id}/model_calls")
    assert calls.status_code == 200
    assert len(calls.json()) == 1
    assert calls.json()[0]["status"] == "success"


def test_complete_draft_with_multiple_receipts_fails_closed(app_env) -> None:
    client, app = app_env
    app.state.conversation_service.model_gateway = _CannedStub(
        _REPLY_WITH_DRAFT,
        app.state.conn_factory,
        receipt_count=2,
    )
    conv_id = _open_life_conversation(client)

    response = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "请生成草稿"},
    )

    assert response.status_code == 503
    assert client.get(f"/api/conversations/{conv_id}").json()["messages"] == []


def test_concurrent_life_rounds_have_one_record_winner_and_one_conflict(app_env) -> None:
    client, app = app_env
    app.state.conversation_service.model_gateway = _ConcurrentCannedStub(
        _REPLY_WITH_DRAFT, app.state.conn_factory
    )
    conv_id = _open_life_conversation(client)

    def post(content: str):
        return client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"content": content},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(post, ["并发轮一", "并发轮二"]))

    assert sorted(response.status_code for response in responses) == [200, 409]
    conflict = next(response for response in responses if response.status_code == 409)
    assert "并发" in conflict.json()["detail"]
    assert _round_counts(app, conv_id) == {
        "messages": 2,
        "records": 1,
        "model_calls": 2,
        "task_events": 0,
    }
    persisted = client.get(f"/api/conversations/{conv_id}").json()["messages"]
    assert [message["role"] for message in persisted] == ["user", "assistant"]
    assert persisted[-1]["generalization_draft_record"] is not None


def test_life_draft_rejects_package_version_change_during_model_round(
    app_env, tmp_path: Path
) -> None:
    client, app = app_env

    class _VersionChangingStub(_CannedStub):
        def chat(
            self, profile: str, messages: list[dict[str, Any]], **kwargs: Any
        ) -> dict[str, Any]:
            result = super().chat(profile, messages, **kwargs)
            _publish_life_agent_version(app, tmp_path, "9.9.9")
            return result

    app.state.conversation_service.model_gateway = _VersionChangingStub(
        _REPLY_WITH_DRAFT, app.state.conn_factory
    )
    conv_id = _open_life_conversation(client)

    response = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "请基于当前包版本生成草稿"},
    )

    assert response.status_code == 409, response.text
    assert _round_counts(app, conv_id) == {
        "messages": 0,
        "records": 0,
        "model_calls": 1,
        "task_events": 0,
    }


def test_complete_draft_with_non_chat_receipt_fails_closed(app_env) -> None:
    client, app = app_env
    app.state.conversation_service.model_gateway = _CannedStub(
        _REPLY_WITH_DRAFT,
        app.state.conn_factory,
        receipt_kind="embed",
    )
    conv_id = _open_life_conversation(client)

    response = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "请生成草稿"},
    )

    assert response.status_code == 503
    assert client.get(f"/api/conversations/{conv_id}").json()["messages"] == []


def test_receipt_cold_verify_failure_rolls_back_messages_and_record_only(app_env) -> None:
    client, app = app_env
    app.state.conversation_service.model_gateway = _CannedStub(
        _REPLY_WITH_DRAFT,
        app.state.conn_factory,
        stored_status_after_receipt="failed",
    )
    conv_id = _open_life_conversation(client)

    response = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "请生成草稿"},
    )

    assert response.status_code == 503
    assert client.get(f"/api/conversations/{conv_id}").json()["messages"] == []
    conn = app.state.conn_factory()
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM generalization_draft_records"
        ).fetchone()[0] == 0
        calls = conn.execute(
            "SELECT status FROM model_calls WHERE conversation_id = ?",
            (conv_id,),
        ).fetchall()
    finally:
        conn.close()
    assert [row["status"] for row in calls] == ["failed"]


def test_life_stream_releases_only_committed_text_and_done_projection(app_env) -> None:
    client, app = app_env
    app.state.conversation_service.model_gateway = _CannedStub(
        _REPLY_WITH_DRAFT,
        app.state.conn_factory,
        chunks=[
            "素材够了,我来投影草稿。\n<<DRA",
            "FT>>\n" + json.dumps(_DRAFT_FIELDS, ensure_ascii=False),
            "\n<<END>>\n审核权在你手里。",
        ],
    )
    conv_id = _open_life_conversation(client)

    with client.stream(
        "POST",
        f"/api/conversations/{conv_id}/messages/stream",
        json={"content": "请投影草稿"},
    ) as response:
        assert response.status_code == 200
        events = [json.loads(line) for line in response.iter_lines() if line]

    assert [event["type"] for event in events] == ["start", "delta", "done"]
    streamed = "".join(
        event["text"] for event in events if event["type"] == "delta"
    )
    done = events[-1]
    assert streamed == done["message"]["content"]
    assert "<<DRAFT>>" not in json.dumps(events, ensure_ascii=False)
    assert "<<END>>" not in json.dumps(events, ensure_ascii=False)
    persisted = client.get(f"/api/conversations/{conv_id}").json()["messages"]
    assert done["message"] == persisted[-1]


def test_unclosed_life_draft_stream_exposes_no_delta_and_persists_nothing(app_env) -> None:
    client, app = app_env
    unclosed = "先说一句。<<DRAFT>>\n" + json.dumps(
        _DRAFT_FIELDS, ensure_ascii=False
    )
    app.state.conversation_service.model_gateway = _CannedStub(
        unclosed,
        app.state.conn_factory,
        chunks=["先说一句。<<DRA", "FT>>\n" + json.dumps(_DRAFT_FIELDS)],
    )
    conv_id = _open_life_conversation(client)

    with client.stream(
        "POST",
        f"/api/conversations/{conv_id}/messages/stream",
        json={"content": "请投影草稿"},
    ) as response:
        events = [json.loads(line) for line in response.iter_lines() if line]

    assert [event["type"] for event in events] == ["start", "error"]
    assert "先说一句" not in json.dumps(events, ensure_ascii=False)
    assert events[-1]["persisted"] is False
    assert client.get(f"/api/conversations/{conv_id}").json()["messages"] == []


def test_invalid_life_draft_stream_exposes_no_delta_and_persists_nothing(app_env) -> None:
    client, app = app_env
    incomplete = {k: v for k, v in _DRAFT_FIELDS.items() if k != "limitations"}
    reply = (
        "我先投影一版。\n<<DRAFT>>\n"
        + json.dumps(incomplete, ensure_ascii=False)
        + "\n<<END>>"
    )
    app.state.conversation_service.model_gateway = _CannedStub(
        reply,
        app.state.conn_factory,
        chunks=[
            "我先投影一版。\n<<DRAFT>>\n",
            json.dumps(incomplete, ensure_ascii=False),
            "\n<<END>>",
        ],
    )
    conv_id = _open_life_conversation(client)

    with client.stream(
        "POST",
        f"/api/conversations/{conv_id}/messages/stream",
        json={"content": "请投影草稿"},
    ) as response:
        events = [json.loads(line) for line in response.iter_lines() if line]

    assert [event["type"] for event in events] == ["start", "error"]
    assert all(event["type"] != "delta" for event in events)
    assert "我先投影一版" not in json.dumps(events, ensure_ascii=False)
    assert events[-1]["status"] == 502
    assert events[-1]["persisted"] is False
    assert client.get(f"/api/conversations/{conv_id}").json()["messages"] == []


def test_life_stream_private_buffer_overflow_exposes_no_delta_or_messages(
    app_env, monkeypatch
) -> None:
    client, app = app_env
    monkeypatch.setattr(
        conversation_runtime, "_MAX_DEFERRED_VISIBLE_STREAM_BYTES", 32
    )
    oversized = "x" * 33
    app.state.conversation_service.model_gateway = _CannedStub(
        oversized,
        app.state.conn_factory,
        chunks=[oversized],
    )
    conv_id = _open_life_conversation(client)

    with client.stream(
        "POST",
        f"/api/conversations/{conv_id}/messages/stream",
        json={"content": "继续"},
    ) as response:
        events = [json.loads(line) for line in response.iter_lines() if line]

    assert [event["type"] for event in events] == ["start", "error"]
    assert all(event["type"] != "delta" for event in events)
    assert events[-1]["status"] == 502
    assert events[-1]["persisted"] is False
    assert _round_counts(app, conv_id) == {
        "messages": 0,
        "records": 0,
        "model_calls": 0,
        "task_events": 0,
    }


def test_life_stream_receipt_failure_discards_complete_upstream_draft(app_env) -> None:
    client, app = app_env
    app.state.conversation_service.model_gateway = _CannedStub(
        _REPLY_WITH_DRAFT,
        app.state.conn_factory,
        chunks=[_REPLY_WITH_DRAFT],
        emit_receipts=False,
    )
    conv_id = _open_life_conversation(client)

    with client.stream(
        "POST",
        f"/api/conversations/{conv_id}/messages/stream",
        json={"content": "请投影草稿"},
    ) as response:
        events = [json.loads(line) for line in response.iter_lines() if line]

    assert [event["type"] for event in events] == ["start", "error"]
    assert all(event["type"] != "delta" for event in events)
    assert "<<DRAFT>>" not in json.dumps(events, ensure_ascii=False)
    assert events[-1]["status"] == 503
    assert events[-1]["persisted"] is False
    assert client.get(f"/api/conversations/{conv_id}").json()["messages"] == []


def test_existing_invalid_record_fails_get_and_next_post_before_model_call(app_env) -> None:
    client, app = app_env
    app.state.conversation_service.model_gateway = _CannedStub(
        _REPLY_WITH_DRAFT, app.state.conn_factory
    )
    conv_id = _open_life_conversation(client)
    created = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "请生成草稿"},
    )
    assert created.status_code == 200, created.text

    # Simulate out-of-band disk corruption by deliberately removing the
    # immutability guard in this disposable test DB. Public reads must not
    # disguise the now-existing bad record as a legacy null.
    conn = app.state.conn_factory()
    try:
        conn.execute("DROP TRIGGER trg_generalization_draft_records_no_update")
        conn.execute(
            "UPDATE generalization_draft_records SET content_digest = ? WHERE id = ?",
            (
                "sha256:" + "0" * 64,
                created.json()["message"]["generalization_draft_record"]["id"],
            ),
        )
    finally:
        conn.close()

    loaded = client.get(f"/api/conversations/{conv_id}")
    assert loaded.status_code == 503

    class _ModelTrap:
        calls = 0

        def chat(self, *args, **kwargs):
            self.calls += 1
            raise AssertionError("invalid persisted evidence must block before model work")

    trap = _ModelTrap()
    app.state.conversation_service.model_gateway = trap
    next_round = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "继续"},
    )
    assert next_round.status_code == 503
    assert trap.calls == 0


def test_disabled_life_agent_is_a_pre_model_create_post_and_stream_guard(
    app_env, tmp_path: Path
) -> None:
    client, app = app_env
    conv_id = _open_life_conversation(client)

    class _ModelTrap:
        calls = 0

        def chat(self, *args, **kwargs):
            self.calls += 1
            raise AssertionError("disabled life agent must fail before model work")

    trap = _ModelTrap()
    app.state.conversation_service.model_gateway = trap
    baseline = _round_counts(app, conv_id)
    _publish_life_agent_status(app, tmp_path, "disabled")
    try:
        create = client.post(
            "/api/conversations", json={"agent_id": "life_guide_agent"}
        )
        assert create.status_code == 409

        posted = client.post(
            f"/api/conversations/{conv_id}/messages", json={"content": "继续"}
        )
        assert posted.status_code == 409

        with client.stream(
            "POST",
            f"/api/conversations/{conv_id}/messages/stream",
            json={"content": "继续"},
        ) as response:
            events = [json.loads(line) for line in response.iter_lines() if line]
        assert [event["type"] for event in events] == ["start", "error"]
        assert events[-1]["status"] == 409
        assert events[-1]["persisted"] is False

        assert trap.calls == 0
        assert _round_counts(app, conv_id) == baseline
    finally:
        app.state.agent_registry.scan()
