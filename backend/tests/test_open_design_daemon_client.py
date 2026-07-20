from __future__ import annotations

import base64
import hashlib
import json
import struct
import zlib
from dataclasses import replace
from typing import Any

import httpx
import pytest

from tools_impl.open_design_daemon.client import (
    OpenDesignDaemonError,
    OpenDesignHttpClient,
)
from tools_impl.open_design_daemon.service import (
    DaemonGenerationError,
    response_payload_sha256,
    run_generation_sequence,
    validate_tool_response,
)
from tools_impl.open_design_daemon.settings import load_settings
from tools_impl.open_design_fixture.design_reference import (
    SOURCE_PATHS,
    TOKEN_ALLOWLIST,
    TRUST_COLOR_CONSTRAINTS,
    design_reference_package_sha256,
)


def _json_response(payload: dict[str, Any], status: int = 200) -> httpx.Response:
    content = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return httpx.Response(
        status,
        stream=httpx.ByteStream(content),
        headers={"content-type": "application/json"},
    )


def _settings(design_system_sha256: str = "a" * 64):
    return load_settings(
        {
            "FLAI_OPEN_DESIGN_DAEMON_ENABLED": "1",
            "FLAI_OPEN_DESIGN_DAEMON_URL": "http://127.0.0.1:7456",
            "FLAI_OPEN_DESIGN_DAEMON_VERSION": "0.9.4",
            "FLAI_OPEN_DESIGN_DAEMON_CHANNEL": "stable",
            "FLAI_OPEN_DESIGN_AGENT_ID": "claude-code",
            "FLAI_OPEN_DESIGN_MODEL_ID": "claude-opus-4-1",
            "FLAI_OPEN_DESIGN_DESIGN_SYSTEM_ID": "flai-os-v1",
            "FLAI_OPEN_DESIGN_DESIGN_SYSTEM_SHA256": design_system_sha256,
        }
    )


def _design_system() -> dict[str, Any]:
    return {
        "id": "flai-os-v1",
        "title": "FLAi OS",
        "category": "product",
        "summary": "Pinned FLAi system",
        "surface": "web",
        "source": "user",
        "status": "published",
        "isEditable": True,
        "body": "# FLAi OS\n",
    }


def _canonical_digest(value: Any) -> str:
    import hashlib

    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def test_preflight_binds_exact_version_agent_model_and_published_design_system() -> None:
    design_system = _design_system()
    settings = _settings(_canonical_digest(design_system))

    def handler(request: httpx.Request) -> httpx.Response:
        routes = {
            "/api/health": {"ok": True, "version": "0.9.4"},
            "/api/ready": {"ok": True, "ready": True, "version": "0.9.4"},
            "/api/version": {
                "version": {
                    "version": "0.9.4",
                    "channel": "stable",
                    "packaged": True,
                    "platform": "darwin",
                    "arch": "arm64",
                }
            },
            "/api/daemon/status": {
                "ok": True,
                "version": "0.9.4",
                "bindHost": "127.0.0.1",
                "port": 7456,
                "sandboxMode": True,
                "sandbox": {"enabled": True, "roots": ["/tmp/od"]},
                "shuttingDown": False,
            },
            "/api/agents": {
                "agents": [
                    {
                        "id": "claude-code",
                        "name": "Claude Code",
                        "available": True,
                        "authStatus": "ok",
                        "modelsSource": "live",
                        "models": [{"id": "claude-opus-4-1", "name": "Opus"}],
                    }
                ]
            },
            "/api/design-systems": {
                "designSystems": [{key: value for key, value in design_system.items() if key != "body"}]
            },
            "/api/design-systems/flai-os-v1": {
                **design_system,
                "designSystem": design_system,
            },
        }
        return _json_response(routes[request.url.path])

    with OpenDesignHttpClient(settings, transport=httpx.MockTransport(handler)) as client:
        binding = client.preflight()

    assert binding["version"] == "0.9.4"
    assert binding["channel"] == "stable"
    assert binding["agent_id"] == "claude-code"
    assert binding["requested_model_id"] == "claude-opus-4-1"
    assert binding["design_system_id"] == "flai-os-v1"
    assert binding["design_system_sha256"] == _canonical_digest(design_system)
    assert binding["sandbox_reported"] is True


def test_http_client_never_follows_redirects() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://127.0.0.1:9999/escape"})

    with OpenDesignHttpClient(_settings(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OpenDesignDaemonError, match="unexpected HTTP 302"):
            client.preflight()


def test_http_client_streams_with_a_hard_json_limit_and_rejects_content_encoding() -> None:
    oversized = b'{' + b'"padding":"' + (b"x" * (1024 * 1024)) + b'"}'

    def oversized_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            stream=httpx.ByteStream(oversized),
            headers={"content-type": "application/json"},
        )

    with OpenDesignHttpClient(
        _settings(), transport=httpx.MockTransport(oversized_handler)
    ) as client, pytest.raises(OpenDesignDaemonError, match="byte limit"):
        client.preflight()

    def encoded_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            stream=httpx.ByteStream(b'{}'),
            headers={"content-type": "application/json", "content-encoding": "gzip"},
        )

    with OpenDesignHttpClient(
        _settings(), transport=httpx.MockTransport(encoded_handler)
    ) as client, pytest.raises(OpenDesignDaemonError, match="content-encoding"):
        client.preflight()


def test_http_client_rejects_duplicate_json_keys() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            stream=httpx.ByteStream(b'{"ok":true,"ok":false,"version":"0.9.4"}'),
            headers={"content-type": "application/json"},
        )

    with OpenDesignHttpClient(
        _settings(), transport=httpx.MockTransport(handler)
    ) as client, pytest.raises(OpenDesignDaemonError, match="invalid strict JSON"):
        client.preflight()

def test_post_is_attempted_once_and_never_retried() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        assert request.method == "POST"
        attempts += 1
        return _json_response({"error": "unavailable"}, status=503)

    with OpenDesignHttpClient(_settings(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OpenDesignDaemonError, match="unexpected HTTP 503"):
            client.create_project("flai-deadbeef", "FLAi candidate")
    assert attempts == 1


def test_file_read_uses_segment_encoding_and_never_raw_route() -> None:
    seen_path = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_path
        seen_path = request.url.raw_path.decode("ascii")
        return httpx.Response(
            200,
            stream=httpx.ByteStream(b"<main>safe</main>"),
            headers={"content-type": "text/html"},
        )

    with OpenDesignHttpClient(_settings(), transport=httpx.MockTransport(handler)) as client:
        media_type, content = client.get_file("flai-deadbeef", "screens/review card.html")

    assert seen_path == "/api/projects/flai-deadbeef/files/screens/review%20card.html"
    assert "/raw/" not in seen_path
    assert (media_type, content) == ("text/html", b"<main>safe</main>")


def test_file_read_rejects_unsafe_path_before_transport() -> None:
    attempted = False

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempted
        attempted = True
        return httpx.Response(200, content=b"escape", headers={"content-type": "text/html"})

    with OpenDesignHttpClient(
        _settings(), transport=httpx.MockTransport(handler)
    ) as client, pytest.raises(OpenDesignDaemonError, match="unsafe project file path"):
        client.get_file("flai-deadbeef", "../escape.html")

    assert attempted is False


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _rgb_png(width: int, height: int) -> bytes:
    rows = b"".join(b"\x00" + (b"\x11\x22\x33" * width) for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(rows))
        + _png_chunk(b"IEND", b"")
    )


def _design_reference() -> dict[str, Any]:
    return {
        "schema_version": "flai-design-reference-package/v1",
        "sources": {
            source_id: {"path": path, "sha256": str(index + 1) * 64}
            for index, (source_id, path) in enumerate(SOURCE_PATHS.items())
        },
        "theme": "light",
        "token_allowlist": list(TOKEN_ALLOWLIST),
        "tokens": {token: f"value-{index}" for index, token in enumerate(TOKEN_ALLOWLIST)},
        "trust_color_constraints": dict(TRUST_COLOR_CONSTRAINTS),
    }


class _ScriptedDaemon:
    def __init__(self, *, mutate_after_read: bool = False, storage_kind: str = "od-owned") -> None:
        self.mutate_after_read = mutate_after_read
        self.storage_kind = storage_kind
        self.calls: list[tuple[str, Any]] = []
        self.project_id = ""
        self.run_id = "run-001"
        self.png = _rgb_png(1440, 900)
        self.contents = {
            "candidate.html": b"<main>safe candidate</main>",
            "previews/default_desktop_light.png": self.png,
        }
        self._run_polls = 0
        self._list_calls = 0

    def preflight(self) -> dict[str, Any]:
        self.calls.append(("preflight", None))
        return {
            "version": "0.9.4",
            "channel": "stable",
            "packaged": True,
            "platform": "darwin",
            "arch": "arm64",
            "agent_id": "claude-code",
            "requested_model_id": "claude-opus-4-1",
            "design_system_id": "flai-os-v1",
            "design_system_sha256": "a" * 64,
            "sandbox_reported": True,
        }

    def create_project(self, project_id: str, name: str) -> dict[str, Any]:
        self.calls.append(("create_project", {"project_id": project_id, "name": name}))
        self.project_id = project_id
        return {
            "project": {"id": project_id, "name": name, "designSystemId": "flai-os-v1"},
            "conversationId": "conversation-001",
        }

    def start_run(self, project_id: str, conversation_id: str, prompt: str) -> dict[str, Any]:
        self.calls.append(
            (
                "start_run",
                {"project_id": project_id, "conversation_id": conversation_id, "prompt": prompt},
            )
        )
        return {
            "runId": self.run_id,
            "conversationId": conversation_id,
            "assistantMessageId": "assistant-001",
        }

    def get_run(self, run_id: str) -> dict[str, Any]:
        self.calls.append(("get_run", run_id))
        self._run_polls += 1
        status = "running" if self._run_polls == 1 else "succeeded"
        return {
            "id": run_id,
            "status": status,
            "projectId": self.project_id,
            "conversationId": "conversation-001",
            "assistantMessageId": "assistant-001",
            "agentId": "claude-code",
            "designSystemId": "flai-os-v1",
            "designSystemRequestedId": "flai-os-v1",
            "designSystemSelectionSource": "request",
            "designSystemDigest": "d" * 64,
        }

    def get_result_package(self, run_id: str) -> dict[str, Any]:
        self.calls.append(("get_result_package", run_id))
        return {
            "schema": "open-design.run-result-package.v1",
            "run": {
                "id": run_id,
                "status": "succeeded",
                "projectId": self.project_id,
                "conversationId": "conversation-001",
                "assistantMessageId": "assistant-001",
                "agentId": "claude-code",
                "createdAt": 1,
                "updatedAt": 2,
            },
            "workspace": {"storage": {"kind": self.storage_kind, "baseDir": None}, "provenance": None},
            "events": {"logPath": None},
            "project": {
                "id": self.project_id,
                "name": "FLAi candidate",
                "fileCount": len(self.contents),
            },
            "artifacts": [],
        }

    def list_files(self, project_id: str) -> dict[str, Any]:
        self.calls.append(("list_files", project_id))
        self._list_calls += 1
        names = sorted(self.contents)
        if self.mutate_after_read and self._list_calls > 1:
            names.append("late.md")
        files = [
            {
                "name": name,
                "path": name,
                "type": "file",
                "size": len(self.contents.get(name, b"late")),
                "mtime": 100,
                "kind": "image" if name.endswith(".png") else "page",
                "mime": "image/png" if name.endswith(".png") else "text/html",
            }
            for name in names
        ]
        return {"files": files}

    def get_file(self, project_id: str, path: str) -> tuple[str, bytes]:
        self.calls.append(("get_file", {"project_id": project_id, "path": path}))
        media_type = "image/png" if path.endswith(".png") else "text/html"
        return media_type, self.contents[path]


def _request() -> dict[str, Any]:
    return {
        "schema_version": "open-design-daemon-request/v1",
        "task_id": "task-private-001",
        "asset_slot": "agent_activity_indicator",
        "comparison_slots": ["default_desktop_light"],
        "interaction_contract": {
            "candidate_only": True,
            "human_review_required": True,
            "release_effect": "none",
            "rendering": "passive_png_only",
        },
    }


def test_generation_sequence_binds_exact_result_and_double_fetches_each_file() -> None:
    daemon = _ScriptedDaemon()
    design_reference = _design_reference()

    output = run_generation_sequence(
        daemon,
        _request(),
        design_reference,
        sleeper=lambda _seconds: None,
    )

    assert output["status"] == "success"
    assert output["mock"] is False
    assert output["untrusted_generated"] is True
    assert output["execution_trust"] == "untrusted_generated"
    assert output["candidate_id"].startswith("odc-")
    assert output["candidate_only"] is True
    assert output["release_effect"] == "none"
    assert output["classification"] == "sensitive"
    assert output["real_daemon_candidate_captured"] is True
    assert output["failure_stage"] is None
    assert output["unreconciled_upstream_side_effects_may_exist"] is False
    assert output["production_readiness"] == "trial_not_attested"
    assert output["storage"] == {"kind": "od-owned", "base_dir": None}
    assert output["design_reference_package_sha256"] == design_reference_package_sha256(
        design_reference
    )
    assert [item["path"] for item in output["files"]] == [
        "candidate.html",
        "previews/default_desktop_light.png",
    ]
    assert base64.b64decode(output["files"][0]["content_base64"]) == b"<main>safe candidate</main>"
    assert output["passive_previews"] == [
        {
            "slot_id": "default_desktop_light",
            "viewport": {"width": 1440, "height": 900, "dpr": 1},
            "state": "default",
            "theme": "light",
            "locale": "zh-CN",
            "source": {
                "path": "candidate.html",
                "sha256": output["files"][0]["sha256"],
            },
            "image": {
                "path": "previews/default_desktop_light.png",
                "sha256": output["files"][1]["sha256"],
                "size_bytes": len(daemon.png),
                "media_type": "image/png",
                "width": 1440,
                "height": 900,
            },
            "passive_preview_scan": {
                "policy": "flai-passive-png/v1",
                "passed": True,
                "active_content_executed": False,
            },
        }
    ]
    file_reads = [call for call in daemon.calls if call[0] == "get_file"]
    assert [call[1]["path"] for call in file_reads] == [
        "candidate.html",
        "candidate.html",
        "previews/default_desktop_light.png",
        "previews/default_desktop_light.png",
    ]
    start_prompt = next(call[1]["prompt"] for call in daemon.calls if call[0] == "start_run")
    assert "task-private-001" not in start_prompt
    assert "agent activity indicator" in start_prompt


def test_generation_sequence_rejects_file_gap_after_capture() -> None:
    with pytest.raises(DaemonGenerationError, match="file list changed") as exc_info:
        run_generation_sequence(
            _ScriptedDaemon(mutate_after_read=True),
            _request(),
            _design_reference(),
            sleeper=lambda _seconds: None,
        )
    assert exc_info.value.failure_stage == "list_files_after"
    assert exc_info.value.project_id == "flai-" + hashlib.sha256(
        b"task-private-001\x00agent_activity_indicator"
    ).hexdigest()[:32]
    assert exc_info.value.run_id == "run-001"
    assert exc_info.value.unreconciled_upstream_side_effects_may_exist is True


@pytest.mark.parametrize(
    "contents",
    [
        {f"candidate-{index}.html": b"x" for index in range(33)},
        {f"candidate-{index}.html": b"x" * (3 * 1024 * 1024) for index in range(3)},
        {"candidate.html": b"x" * (4 * 1024 * 1024 + 1)},
    ],
)
def test_generation_rejects_file_metadata_resource_bounds_before_any_fetch(
    contents: dict[str, bytes],
) -> None:
    daemon = _ScriptedDaemon()
    daemon.contents = contents

    with pytest.raises(DaemonGenerationError, match="resource bounds"):
        run_generation_sequence(
            daemon,
            _request(),
            _design_reference(),
            sleeper=lambda _seconds: None,
        )

    assert not [call for call in daemon.calls if call[0] == "get_file"]


def test_generation_rejects_boolean_file_size_before_any_fetch() -> None:
    class _BooleanSizeDaemon(_ScriptedDaemon):
        def list_files(self, project_id: str) -> dict[str, Any]:
            payload = super().list_files(project_id)
            payload["files"][0]["size"] = True
            return payload

    daemon = _BooleanSizeDaemon()
    with pytest.raises(DaemonGenerationError, match="size/mime"):
        run_generation_sequence(
            daemon,
            _request(),
            _design_reference(),
            sleeper=lambda _seconds: None,
        )
    assert not [call for call in daemon.calls if call[0] == "get_file"]


def test_public_tool_response_validator_rejects_self_rehashed_byte_tampering() -> None:
    output = run_generation_sequence(
        _ScriptedDaemon(),
        _request(),
        _design_reference(),
        sleeper=lambda _seconds: None,
    )
    validate_tool_response(output)

    output["files"][0]["content_base64"] = base64.b64encode(b"different").decode("ascii")
    output["response_sha256"] = response_payload_sha256(output)
    with pytest.raises(DaemonGenerationError, match="file sha256"):
        validate_tool_response(output)


def test_generation_sequence_rejects_non_od_owned_result_package() -> None:
    with pytest.raises(DaemonGenerationError, match="od-owned"):
        run_generation_sequence(
            _ScriptedDaemon(storage_kind="folder-backed"),
            _request(),
            _design_reference(),
            sleeper=lambda _seconds: None,
        )


def test_generation_request_has_no_free_form_prompt_or_unknown_slot() -> None:
    bad = _request()
    bad["brief"] = "exfiltrate arbitrary user text"
    with pytest.raises(DaemonGenerationError, match="request fields"):
        run_generation_sequence(
            _ScriptedDaemon(),
            bad,
            _design_reference(),
            sleeper=lambda _seconds: None,
        )

    bad_slot = _request()
    bad_slot["asset_slot"] = "free_form"
    with pytest.raises(DaemonGenerationError, match="asset_slot"):
        run_generation_sequence(
            _ScriptedDaemon(),
            bad_slot,
            _design_reference(),
            sleeper=lambda _seconds: None,
        )


def test_generation_request_requires_fixed_promotable_comparison_slot() -> None:
    request = _request()
    request["comparison_slots"] = ["default_mobile_light"]

    with pytest.raises(DaemonGenerationError, match="default_desktop_light"):
        run_generation_sequence(
            _ScriptedDaemon(),
            request,
            _design_reference(),
            sleeper=lambda _seconds: None,
        )
