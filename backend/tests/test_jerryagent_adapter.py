from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from backend.app.runtime.agent_execution import (
    AgentExecutionRequest,
    canonical_json_bytes,
    request_sha256,
)
from backend.app.runtime.jerryagent_adapter import (
    JerryAgentAdapter,
    JerryAgentAdapterError,
    JerryAgentSettingsError,
    load_jerryagent_settings,
)


TOKEN = "flai-jerryagent-test-token-00000001"


class _Events:
    def __init__(self) -> None:
        self.rows: list[tuple[str, dict[str, Any]]] = []

    def log(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        self.rows.append((event_type, dict(payload or {})))


def _settings_env() -> dict[str, str]:
    return {
        "FLAI_JERRYAGENT_ENABLED": "1",
        "FLAI_JERRYAGENT_URL": "http://127.0.0.1:43117",
        "FLAI_JERRYAGENT_TOKEN": TOKEN,
        "FLAI_JERRYAGENT_TIMEOUT_S": "30",
        "FLAI_JERRYAGENT_POLL_INTERVAL_S": "0.01",
    }


def _request(tmp_path: Path) -> tuple[AgentExecutionRequest, _Events]:
    events = _Events()
    task = {
        "id": "task-123",
        "agent_id": "jerryagent_research_agent",
        "agent_version": "0.1.0",
        "execution_adapter": "jerryagent_sidecar",
        "execution_contract_version": "flai.agent-layer.v1",
        "inputs": {
            "objective": "比较两个经过人签的研究结论",
            "constraints": ["只生成候选，不得声称批准"],
        },
        "input_file_ids": [],
    }
    agent = {
        "id": "jerryagent_research_agent",
        "name": "JerryAgent Research",
        "version": "0.1.0",
        "summary": "跨轮研究候选生成",
        "limitations": ["输出必须人工复核"],
        "execution": {
            "adapter": "jerryagent_sidecar",
            "contract_version": "flai.agent-layer.v1",
        },
    }
    return (
        AgentExecutionRequest(
            task=task,
            agent=agent,
            package_dir=tmp_path,
            output_dir=tmp_path / "output",
            context={"event_logger": events},
        ),
        events,
    )


def _health(*, revision: int = 7, session_id: str = "session-a") -> dict[str, Any]:
    return {
        "product": "JerryAgent",
        "schema": "flai.agent-layer.v1",
        "runtimeEventSchemaVersion": 1,
        "instanceId": "instance-a",
        "sessionId": session_id,
        "runtimeKind": "external",
        "revision": revision,
    }


def _projection(
    *,
    status: str,
    revision: int,
    request_sha256: str,
    session_id: str = "session-a",
) -> dict[str, Any]:
    return {
        "runtimeTaskId": "runtime-task-a",
        "status": status,
        "detail": "done" if status == "completed" else "working",
        "revision": revision,
        "identity": {
            "product": "JerryAgent",
            "schema": "flai.agent-layer.v1",
            "runtimeEventSchemaVersion": 1,
            "instanceId": "instance-a",
            "sessionId": session_id,
            "runtimeKind": "external",
            "executionId": "task-123",
            "externalTaskId": "task-123",
            "requestSha256": request_sha256,
        },
    }


def _result(
    *,
    revision: int,
    request_sha256: str,
    assistant_text: str = "这是待人工复核的研究候选。",
    session_id: str = "session-a",
) -> dict[str, Any]:
    projection = _projection(
        status="completed",
        revision=revision,
        request_sha256=request_sha256,
        session_id=session_id,
    )
    return {
        "runtimeTaskId": projection["runtimeTaskId"],
        "status": "completed",
        "assistantText": assistant_text,
        "revision": revision,
        "identity": projection["identity"],
    }


def _json(payload: dict[str, Any], status: int = 200) -> httpx.Response:
    return httpx.Response(
        status,
        stream=httpx.ByteStream(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        ),
        headers={"content-type": "application/json"},
    )


def _broken_json(payload: dict[str, Any], status: int = 202) -> httpx.Response:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()

    class _BrokenStream(httpx.SyncByteStream):
        def __iter__(self):
            yield encoded[: max(1, len(encoded) // 2)]
            raise httpx.ReadError("submission response connection lost")

    return httpx.Response(
        status,
        stream=_BrokenStream(),
        headers={"content-type": "application/json"},
    )


def test_settings_are_default_off_and_reject_ambiguous_configuration() -> None:
    assert load_jerryagent_settings({}).enabled is False
    with pytest.raises(JerryAgentSettingsError, match="literal 0 or 1"):
        load_jerryagent_settings({"FLAI_JERRYAGENT_ENABLED": "true"})
    with pytest.raises(JerryAgentSettingsError, match="loopback HTTP origin"):
        load_jerryagent_settings(
            {**_settings_env(), "FLAI_JERRYAGENT_URL": "http://localhost:43117"}
        )
    with pytest.raises(JerryAgentSettingsError, match="loopback HTTP origin"):
        load_jerryagent_settings(
            {**_settings_env(), "FLAI_JERRYAGENT_URL": "http://[::1]:43117"}
        )
    with pytest.raises(JerryAgentSettingsError, match="32 to 256"):
        load_jerryagent_settings({**_settings_env(), "FLAI_JERRYAGENT_TOKEN": "short"})


def test_adapter_binds_identity_polls_one_execution_and_writes_candidate(
    tmp_path: Path,
) -> None:
    submitted: dict[str, Any] = {}
    polls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal polls
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        if request.method == "GET" and request.url.path.endswith("/health"):
            return _json(_health())
        if request.method == "POST" and request.url.path.endswith("/executions"):
            assert request.content == canonical_json_bytes(json.loads(request.content))
            assert len(request.content) <= 64 * 1024
            assert request.headers["content-type"] == "application/json"
            submitted.update(json.loads(request.content))
            return _json(
                {
                    "executionId": "task-123",
                    "externalTaskId": "task-123",
                    "requestSha256": submitted["requestSha256"],
                    "runtimeTaskId": "runtime-task-a",
                    "replayed": False,
                },
                status=202,
            )
        if request.method == "GET" and request.url.path.endswith("/executions/task-123/result"):
            return _json(
                _result(
                    revision=9,
                    request_sha256=submitted["requestSha256"],
                )
            )
        if request.method == "GET" and request.url.path.endswith("/executions/task-123"):
            polls += 1
            if polls == 1:
                return _json(
                    _projection(
                        status="running",
                        revision=8,
                        request_sha256=submitted["requestSha256"],
                    )
                )
            return _json(
                _projection(
                    status="completed",
                    revision=9,
                    request_sha256=submitted["requestSha256"],
                )
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    request, events = _request(tmp_path)
    adapter = JerryAgentAdapter(
        load_jerryagent_settings(_settings_env()),
        transport=httpx.MockTransport(handler),
        sleeper=lambda _seconds: None,
    )
    outcome = adapter.execute(request)

    assert polls == 2
    assert submitted["schemaVersion"] == 1
    assert submitted["executionId"] == "task-123"
    assert submitted["externalTaskId"] == "task-123"
    assert submitted["autoCollaboration"] is True
    assert submitted["expectedIdentity"] == {
        key: _health()[key]
        for key in (
            "product",
            "schema",
            "runtimeEventSchemaVersion",
            "instanceId",
            "sessionId",
            "runtimeKind",
        )
    }
    assert len(submitted["requestSha256"]) == 64
    digest_basis = {
        key: value
        for key, value in submitted.items()
        if key not in {"requestSha256", "expectedIdentity"}
    }
    assert submitted["requestSha256"] == request_sha256(digest_basis)
    assert "唯一签发者" in submitted["prompt"]
    assert outcome.result["status"] == "success"
    assert outcome.receipt.final_revision == 9
    assert outcome.receipt.model_calls_attested_by_flai is False
    result_path = tmp_path / "output" / "jerryagent_result.md"
    assert result_path.is_file()
    rendered = result_path.read_text(encoding="utf-8")
    assert "待人工复核" in rendered
    assert "这是待人工复核的研究候选" in rendered
    assert [name for name, _payload in events.rows] == [
        "agent_layer_started",
        "agent_layer_submitted",
        "agent_layer_identity_bound",
        "agent_layer_observed",
        "agent_layer_observed",
    ]
    identity_bound = next(
        payload
        for name, payload in events.rows
        if name == "agent_layer_identity_bound"
    )
    assert identity_bound == {
        "execution_id": "task-123",
        "runtime_task_id": "runtime-task-a",
        "request_sha256": submitted["requestSha256"],
        "runtime_identity": {
            key: _health()[key]
            for key in (
                "product",
                "schema",
                "runtimeEventSchemaVersion",
                "instanceId",
                "sessionId",
                "runtimeKind",
            )
        },
    }


def test_lost_submission_receipt_reconciles_exact_execution_before_observing(
    tmp_path: Path,
) -> None:
    submitted: dict[str, Any] = {}
    posts = 0
    projections = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal posts, projections
        if request.url.path.endswith("/health"):
            return _json(_health())
        if request.method == "POST":
            posts += 1
            submitted.update(json.loads(request.content))
            return _broken_json(
                {
                    "executionId": "task-123",
                    "externalTaskId": "task-123",
                    "requestSha256": submitted["requestSha256"],
                    "runtimeTaskId": "runtime-task-a",
                    "replayed": False,
                }
            )
        if request.url.path.endswith("/result"):
            return _json(
                _result(revision=9, request_sha256=submitted["requestSha256"])
            )
        projections += 1
        return _json(
            _projection(
                status="running" if projections == 1 else "completed",
                revision=8 if projections == 1 else 9,
                request_sha256=submitted["requestSha256"],
            )
        )

    request, events = _request(tmp_path)
    adapter = JerryAgentAdapter(
        load_jerryagent_settings(_settings_env()),
        transport=httpx.MockTransport(handler),
        sleeper=lambda _seconds: None,
    )

    outcome = adapter.execute(request)

    assert posts == 1
    assert projections == 2
    assert outcome.receipt.request_sha256 == submitted["requestSha256"]
    submitted_event = next(
        payload for name, payload in events.rows if name == "agent_layer_submitted"
    )
    assert submitted_event == {
        "execution_id": "task-123",
        "runtime_task_id": "runtime-task-a",
        "replayed": None,
        "receipt_recovered": True,
        "submission_attempts": 1,
    }


def test_truncated_accepted_submission_envelope_reconciles_exact_execution(
    tmp_path: Path,
) -> None:
    posts = 0
    digest = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal posts, digest
        if request.url.path.endswith("/health"):
            return _json(_health())
        if request.method == "POST":
            posts += 1
            digest = json.loads(request.content)["requestSha256"]
            return httpx.Response(
                202,
                stream=httpx.ByteStream(b'{"executionId":"task-123"'),
                headers={"content-type": "application/json"},
            )
        if request.url.path.endswith("/result"):
            return _json(_result(revision=8, request_sha256=digest))
        return _json(
            _projection(
                status="completed",
                revision=8,
                request_sha256=digest,
            )
        )

    request, events = _request(tmp_path)
    adapter = JerryAgentAdapter(
        load_jerryagent_settings(_settings_env()),
        transport=httpx.MockTransport(handler),
    )

    outcome = adapter.execute(request)

    assert posts == 1
    assert outcome.receipt.request_sha256 == digest
    submitted_event = next(
        payload for name, payload in events.rows if name == "agent_layer_submitted"
    )
    assert submitted_event["receipt_recovered"] is True


def test_lost_submission_receipt_retries_exact_command_once_after_exact_404(
    tmp_path: Path,
) -> None:
    post_bodies: list[bytes] = []
    reconciliation_gets = 0
    digest = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal reconciliation_gets, digest
        if request.url.path.endswith("/health"):
            return _json(_health())
        if request.method == "POST":
            post_bodies.append(request.content)
            body = json.loads(request.content)
            digest = body["requestSha256"]
            receipt = {
                "executionId": "task-123",
                "externalTaskId": "task-123",
                "requestSha256": digest,
                "runtimeTaskId": "runtime-task-a",
                "replayed": False,
            }
            if len(post_bodies) == 1:
                return _broken_json(receipt)
            return _json(receipt, status=202)
        if request.url.path.endswith("/result"):
            return _json(_result(revision=9, request_sha256=digest))
        reconciliation_gets += 1
        if reconciliation_gets == 1:
            return _json({"error": "not found"}, status=404)
        return _json(
            _projection(
                status="completed",
                revision=9,
                request_sha256=digest,
            )
        )

    request, events = _request(tmp_path)
    adapter = JerryAgentAdapter(
        load_jerryagent_settings(_settings_env()),
        transport=httpx.MockTransport(handler),
        sleeper=lambda _seconds: None,
    )

    outcome = adapter.execute(request)

    assert len(post_bodies) == 2
    assert post_bodies[0] == post_bodies[1]
    assert outcome.receipt.request_sha256 == digest
    submitted_event = next(
        payload for name, payload in events.rows if name == "agent_layer_submitted"
    )
    assert submitted_event == {
        "execution_id": "task-123",
        "runtime_task_id": "runtime-task-a",
        "replayed": False,
        "receipt_recovered": False,
        "submission_attempts": 2,
    }


def test_submission_recovery_is_bounded_to_two_posts_and_two_exact_lookups(
    tmp_path: Path,
) -> None:
    posts = 0
    lookups = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal posts, lookups
        if request.url.path.endswith("/health"):
            return _json(_health())
        if request.method == "POST":
            posts += 1
            body = json.loads(request.content)
            return _broken_json(
                {
                    "executionId": "task-123",
                    "externalTaskId": "task-123",
                    "requestSha256": body["requestSha256"],
                    "runtimeTaskId": "runtime-task-a",
                    "replayed": posts > 1,
                },
                status=200 if posts > 1 else 202,
            )
        lookups += 1
        return _json({"error": "not found"}, status=404)

    request, events = _request(tmp_path)
    adapter = JerryAgentAdapter(
        load_jerryagent_settings(_settings_env()),
        transport=httpx.MockTransport(handler),
        sleeper=lambda _seconds: None,
    )

    with pytest.raises(JerryAgentAdapterError, match="one idempotent retry"):
        adapter.execute(request)

    assert posts == 2
    assert lookups == 2
    assert not (tmp_path / "output" / "jerryagent_result.md").exists()


def test_lost_receipt_can_reconcile_exact_historical_identity_with_wire_precondition(
    tmp_path: Path,
) -> None:
    posts = 0
    digest = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal posts, digest
        if request.url.path.endswith("/health"):
            return _json(_health(session_id="replacement-session"))
        if request.method == "POST":
            posts += 1
            digest = json.loads(request.content)["requestSha256"]
            return _broken_json(
                {
                    "executionId": "task-123",
                    "externalTaskId": "task-123",
                    "requestSha256": digest,
                    "runtimeTaskId": "runtime-task-a",
                    "replayed": True,
                },
                status=200,
            )
        if request.url.path.endswith("/result"):
            return _json(
                _result(
                    revision=8,
                    request_sha256=digest,
                    session_id="session-a",
                )
            )
        return _json(
            _projection(
                status="completed",
                revision=8,
                request_sha256=digest,
                session_id="session-a",
            )
        )

    request, events = _request(tmp_path)
    adapter = JerryAgentAdapter(
        load_jerryagent_settings(_settings_env()),
        transport=httpx.MockTransport(handler),
    )

    outcome = adapter.execute(request)

    assert posts == 1
    assert outcome.receipt.runtime_identity["sessionId"] == "session-a"
    submitted_event = next(
        payload for name, payload in events.rows if name == "agent_layer_submitted"
    )
    assert submitted_event["receipt_recovered"] is True


def test_semantically_invalid_submission_receipt_is_not_masked_by_reconciliation(
    tmp_path: Path,
) -> None:
    lookups = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal lookups
        if request.url.path.endswith("/health"):
            return _json(_health())
        if request.method == "POST":
            return _json(
                {
                    "executionId": "task-123",
                    "externalTaskId": "task-123",
                    "requestSha256": "0" * 64,
                    "runtimeTaskId": "runtime-task-a",
                    "replayed": False,
                },
                status=202,
            )
        lookups += 1
        raise AssertionError("an invalid receipt must fail before reconciliation")

    request, events = _request(tmp_path)
    adapter = JerryAgentAdapter(
        load_jerryagent_settings(_settings_env()),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(JerryAgentAdapterError, match="submission binding mismatch"):
        adapter.execute(request)
    assert lookups == 0


def test_adapter_rejects_runtime_identity_drift(tmp_path: Path) -> None:
    digest = "a" * 64

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/health"):
            return _json(_health())
        if request.method == "POST":
            body = json.loads(request.content)
            return _json(
                {
                    "executionId": "task-123",
                    "externalTaskId": "task-123",
                    "requestSha256": body["requestSha256"],
                    "runtimeTaskId": "runtime-task-a",
                    "replayed": False,
                },
                status=202,
            )
        return _json(
            _projection(
                status="completed",
                revision=9,
                request_sha256=digest,
                session_id="replacement-session",
            )
        )

    request, _events = _request(tmp_path)
    adapter = JerryAgentAdapter(
        load_jerryagent_settings(_settings_env()),
        transport=httpx.MockTransport(handler),
        sleeper=lambda _seconds: None,
    )
    with pytest.raises(JerryAgentAdapterError, match="identity|binding"):
        adapter.execute(request)


def test_exact_replay_after_restart_uses_frozen_execution_identity(
    tmp_path: Path,
) -> None:
    digest = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal digest
        if request.url.path.endswith("/health"):
            return _json(_health(revision=10, session_id="replacement-session"))
        if request.method == "POST":
            digest = json.loads(request.content)["requestSha256"]
            return _json(
                {
                    "executionId": "task-123",
                    "externalTaskId": "task-123",
                    "requestSha256": digest,
                    "runtimeTaskId": "runtime-task-a",
                    "replayed": True,
                },
                status=200,
            )
        if request.url.path.endswith("/result"):
            return _json(
                _result(
                    revision=11,
                    request_sha256=digest,
                    session_id="session-a",
                )
            )
        return _json(
            _projection(
                status="completed",
                revision=11,
                request_sha256=digest,
                session_id="session-a",
            )
        )

    request, events = _request(tmp_path)
    adapter = JerryAgentAdapter(
        load_jerryagent_settings(_settings_env()),
        transport=httpx.MockTransport(handler),
        sleeper=lambda _seconds: None,
    )

    outcome = adapter.execute(request)

    assert outcome.receipt.runtime_identity["sessionId"] == "session-a"
    assert outcome.receipt.runtime_identity["sessionId"] != "replacement-session"
    identity_bound = next(
        payload
        for name, payload in events.rows
        if name == "agent_layer_identity_bound"
    )
    assert identity_bound["runtime_identity"]["sessionId"] == "session-a"
    assert identity_bound["runtime_identity"]["sessionId"] != "replacement-session"


def test_result_may_advance_global_revision_after_terminal_projection(
    tmp_path: Path,
) -> None:
    digest = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal digest
        if request.url.path.endswith("/health"):
            return _json(_health())
        if request.method == "POST":
            digest = json.loads(request.content)["requestSha256"]
            return _json(
                {
                    "executionId": "task-123",
                    "externalTaskId": "task-123",
                    "requestSha256": digest,
                    "runtimeTaskId": "runtime-task-a",
                    "replayed": False,
                },
                status=202,
            )
        if request.url.path.endswith("/result"):
            return _json(_result(revision=10, request_sha256=digest))
        return _json(
            _projection(
                status="completed",
                revision=8,
                request_sha256=digest,
            )
        )

    request, _events = _request(tmp_path)
    adapter = JerryAgentAdapter(
        load_jerryagent_settings(_settings_env()),
        transport=httpx.MockTransport(handler),
        sleeper=lambda _seconds: None,
    )

    outcome = adapter.execute(request)

    assert outcome.receipt.final_revision == 10


def test_completed_projection_without_final_assistant_message_fails_closed(
    tmp_path: Path,
) -> None:
    submitted_digest = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal submitted_digest
        if request.url.path.endswith("/health"):
            return _json(_health())
        if request.method == "POST":
            submitted_digest = json.loads(request.content)["requestSha256"]
            return _json(
                {
                    "executionId": "task-123",
                    "externalTaskId": "task-123",
                    "requestSha256": submitted_digest,
                    "runtimeTaskId": "runtime-task-a",
                    "replayed": False,
                },
                status=202,
            )
        if request.url.path.endswith("/result"):
            return _json(
                _result(
                    revision=8,
                    request_sha256=submitted_digest,
                    assistant_text="",
                )
            )
        return _json(
            _projection(
                status="completed",
                revision=8,
                request_sha256=submitted_digest,
            )
        )

    request, _events = _request(tmp_path)
    adapter = JerryAgentAdapter(
        load_jerryagent_settings(_settings_env()),
        transport=httpx.MockTransport(handler),
        sleeper=lambda _seconds: None,
    )
    with pytest.raises(JerryAgentAdapterError, match="assistant message"):
        adapter.execute(request)
    assert not (tmp_path / "output" / "jerryagent_result.md").exists()


def test_adapter_rejects_undeclared_submission_status(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/health"):
            return _json(_health())
        body = json.loads(request.content)
        return _json(
            {
                "executionId": "task-123",
                "externalTaskId": "task-123",
                "requestSha256": body["requestSha256"],
                "runtimeTaskId": "runtime-task-a",
                "replayed": False,
            },
            status=201,
        )

    request, _events = _request(tmp_path)
    adapter = JerryAgentAdapter(
        load_jerryagent_settings(_settings_env()),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(JerryAgentAdapterError, match="unexpected HTTP 201"):
        adapter.execute(request)


@pytest.mark.parametrize(
    ("status", "replayed"),
    ((200, False), (202, True)),
)
def test_submission_http_status_must_match_replay_truth(
    tmp_path: Path, status: int, replayed: bool
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/health"):
            return _json(_health())
        body = json.loads(request.content)
        return _json(
            {
                "executionId": "task-123",
                "externalTaskId": "task-123",
                "requestSha256": body["requestSha256"],
                "runtimeTaskId": "runtime-task-a",
                "replayed": replayed,
            },
            status=status,
        )

    request, _events = _request(tmp_path)
    adapter = JerryAgentAdapter(
        load_jerryagent_settings(_settings_env()),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(JerryAgentAdapterError, match="replay truth"):
        adapter.execute(request)


def test_total_deadline_includes_health_preflight(tmp_path: Path) -> None:
    calls: list[str] = []
    clock = [0.0]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        clock[0] = 2.0
        return _json(_health())

    env = {**_settings_env(), "FLAI_JERRYAGENT_TIMEOUT_S": "1"}
    request, _events = _request(tmp_path)
    adapter = JerryAgentAdapter(
        load_jerryagent_settings(env),
        transport=httpx.MockTransport(handler),
        monotonic=lambda: clock[0],
    )
    with pytest.raises(JerryAgentAdapterError, match="timed out"):
        adapter.execute(request)
    assert calls == ["/api/agent-layer/v1/health"]


def test_unchanged_poll_projection_does_not_flood_flai_events(tmp_path: Path) -> None:
    submitted_digest = ""
    polls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal submitted_digest, polls
        if request.url.path.endswith("/health"):
            return _json(_health())
        if request.method == "POST":
            submitted_digest = json.loads(request.content)["requestSha256"]
            return _json(
                {
                    "executionId": "task-123",
                    "externalTaskId": "task-123",
                    "requestSha256": submitted_digest,
                    "runtimeTaskId": "runtime-task-a",
                    "replayed": False,
                },
                status=202,
            )
        if request.url.path.endswith("/result"):
            return _json(
                _result(
                    revision=9,
                    request_sha256=submitted_digest,
                    assistant_text="候选结果",
                )
            )
        polls += 1
        if polls < 3:
            return _json(
                _projection(
                    status="running",
                    revision=8,
                    request_sha256=submitted_digest,
                )
            )
        return _json(
            _projection(
                status="completed",
                revision=9,
                request_sha256=submitted_digest,
            )
        )

    request, events = _request(tmp_path)
    adapter = JerryAgentAdapter(
        load_jerryagent_settings(_settings_env()),
        transport=httpx.MockTransport(handler),
        sleeper=lambda _seconds: None,
    )
    adapter.execute(request)

    observed = [name for name, _payload in events.rows if name == "agent_layer_observed"]
    assert polls == 3
    assert observed == ["agent_layer_observed", "agent_layer_observed"]


def test_same_revision_projection_must_be_byte_for_byte_stable(tmp_path: Path) -> None:
    submitted_digest = ""
    polls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal submitted_digest, polls
        if request.url.path.endswith("/health"):
            return _json(_health())
        if request.method == "POST":
            submitted_digest = json.loads(request.content)["requestSha256"]
            return _json(
                {
                    "executionId": "task-123",
                    "externalTaskId": "task-123",
                    "requestSha256": submitted_digest,
                    "runtimeTaskId": "runtime-task-a",
                    "replayed": False,
                },
                status=202,
            )
        polls += 1
        projection = _projection(
            status="running",
            revision=8,
            request_sha256=submitted_digest,
        )
        if polls == 2:
            projection["detail"] = "mutated without revision"
        return _json(projection)

    request, _events = _request(tmp_path)
    adapter = JerryAgentAdapter(
        load_jerryagent_settings(_settings_env()),
        transport=httpx.MockTransport(handler),
        sleeper=lambda _seconds: None,
    )
    with pytest.raises(JerryAgentAdapterError, match="same revision changed"):
        adapter.execute(request)


def test_slow_drip_json_expires_inside_response_read_before_any_event(
    tmp_path: Path,
) -> None:
    clock = [0.0]

    class _SlowStream(httpx.SyncByteStream):
        def __iter__(self):
            encoded = canonical_json_bytes(_health())
            yield encoded[:1]
            clock[0] = 2.0
            yield encoded[1:]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/health")
        return httpx.Response(
            200,
            stream=_SlowStream(),
            headers={"content-type": "application/json"},
        )

    request, events = _request(tmp_path)
    adapter = JerryAgentAdapter(
        load_jerryagent_settings(
            {**_settings_env(), "FLAI_JERRYAGENT_TIMEOUT_S": "1"}
        ),
        transport=httpx.MockTransport(handler),
        monotonic=lambda: clock[0],
    )
    with pytest.raises(JerryAgentAdapterError, match="timed out while reading"):
        adapter.execute(request)
    assert events.rows == []
