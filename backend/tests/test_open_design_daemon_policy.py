from __future__ import annotations

import struct
import zlib
from types import SimpleNamespace

import pytest

from tools_impl.open_design_daemon.policy import (
    CandidatePolicyError,
    validate_candidate_bundle,
    validate_png,
    validate_safe_path,
)
from tools_impl.open_design_daemon.settings import (
    OpenDesignSettingsError,
    load_settings,
)


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _rgb_png(width: int = 1, height: int = 1) -> bytes:
    rows = b"".join(b"\x00" + (b"\x11\x22\x33" * width) for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(rows))
        + _png_chunk(b"IEND", b"")
    )


def _enabled_env() -> dict[str, str]:
    return {
        "FLAI_OPEN_DESIGN_DAEMON_ENABLED": "1",
        "FLAI_OPEN_DESIGN_DAEMON_URL": "http://127.0.0.1:7456",
        "FLAI_OPEN_DESIGN_DAEMON_VERSION": "0.9.4",
        "FLAI_OPEN_DESIGN_DAEMON_CHANNEL": "stable",
        "FLAI_OPEN_DESIGN_AGENT_ID": "claude-code",
        "FLAI_OPEN_DESIGN_MODEL_ID": "claude-opus-4-1",
        "FLAI_OPEN_DESIGN_DESIGN_SYSTEM_ID": "flai-os-v1",
        "FLAI_OPEN_DESIGN_DESIGN_SYSTEM_SHA256": "a" * 64,
    }


def test_daemon_adapter_is_default_off_and_rejects_ambiguous_boolean() -> None:
    assert load_settings({}).enabled is False
    assert load_settings({"FLAI_OPEN_DESIGN_DAEMON_ENABLED": "0"}).enabled is False

    with pytest.raises(OpenDesignSettingsError, match="literal 0 or 1"):
        load_settings({"FLAI_OPEN_DESIGN_DAEMON_ENABLED": "true"})


def test_default_off_adapter_returns_an_honest_schema_shaped_failure(monkeypatch) -> None:
    from tools_impl.open_design_daemon.adapter import run

    monkeypatch.delenv("FLAI_OPEN_DESIGN_DAEMON_ENABLED", raising=False)
    output = run(
        {
            "schema_version": "open-design-daemon-request/v1",
            "asset_slot": "agent_activity_indicator",
            "comparison_slots": ["default_desktop_light"],
            "interaction_contract": {
                "candidate_only": True,
                "human_review_required": True,
                "release_effect": "none",
                "rendering": "passive_png_only",
            },
        },
        {"task_id": "task-001"},
    )

    assert output["status"] == "failed"
    assert output["mock"] is False
    assert output["real_daemon_candidate_captured"] is False
    assert output["failure_stage"] == "adapter_disabled"
    assert output["unreconciled_upstream_side_effects_may_exist"] is False
    assert output["candidate_id"] is None
    assert output["files"] == []
    assert output["passive_previews"] == []
    assert "disabled by default" in output["error_message"]


def test_adapter_requires_runtime_task_identity_and_rejects_payload_forgery(monkeypatch) -> None:
    from tools_impl.open_design_daemon.adapter import run

    monkeypatch.delenv("FLAI_OPEN_DESIGN_DAEMON_ENABLED", raising=False)
    request = {
        "schema_version": "open-design-daemon-request/v1",
        "asset_slot": "agent_activity_indicator",
        "comparison_slots": ["default_desktop_light"],
        "interaction_contract": {
            "candidate_only": True,
            "human_review_required": True,
            "release_effect": "none",
            "rendering": "passive_png_only",
        },
    }

    missing = run(request, None)
    forged = run({**request, "task_id": "forged-task"}, {"task_id": "actual-task"})

    assert missing["status"] == "failed"
    assert "runtime task identity" in missing["error_message"]
    assert forged["status"] == "failed"
    assert "must not carry task_id" in forged["error_message"]


def test_adapter_preserves_unreconciled_upstream_progress_on_failure(monkeypatch) -> None:
    import tools_impl.open_design_daemon.adapter as adapter
    from tools_impl.open_design_daemon.service import DaemonGenerationError

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    monkeypatch.setattr(adapter, "load_settings", lambda: SimpleNamespace(enabled=True))
    monkeypatch.setattr(adapter, "build_design_reference_package", lambda: {})
    monkeypatch.setattr(adapter, "OpenDesignHttpClient", lambda _settings: _Client())

    def _fail_after_start(*_args, **_kwargs):
        raise DaemonGenerationError(
            "file capture failed",
            failure_stage="capture_files",
            project_id="flai-" + "1" * 32,
            run_id="run-001",
            unreconciled_upstream_side_effects_may_exist=True,
        )

    monkeypatch.setattr(adapter, "run_generation_sequence", _fail_after_start)
    output = adapter.run(
        {
            "schema_version": "open-design-daemon-request/v1",
            "asset_slot": "agent_activity_indicator",
            "comparison_slots": ["default_desktop_light"],
            "interaction_contract": {
                "candidate_only": True,
                "human_review_required": True,
                "release_effect": "none",
                "rendering": "passive_png_only",
            },
        },
        {"task_id": "task-001"},
    )

    assert output["status"] == "failed"
    assert output["real_daemon_candidate_captured"] is False
    assert output["failure_stage"] == "capture_files"
    assert output["project_id"] == "flai-" + "1" * 32
    assert output["run_id"] == "run-001"
    assert output["unreconciled_upstream_side_effects_may_exist"] is True


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:7456",
        "https://127.0.0.1:7456",
        "http://user@127.0.0.1:7456",
        "http://127.0.0.1",
        "http://127.0.0.1:7456/",
        "http://127.0.0.1:7456/api",
        "http://127.0.0.1:7456?x=1",
        "http://127.0.0.1:7456#fragment",
        "http://0.0.0.0:7456",
    ],
)
def test_enabled_settings_accept_only_an_exact_loopback_http_origin(url: str) -> None:
    env = _enabled_env()
    env["FLAI_OPEN_DESIGN_DAEMON_URL"] = url

    with pytest.raises(OpenDesignSettingsError, match="loopback HTTP origin"):
        load_settings(env)


def test_enabled_settings_bind_every_upstream_identity_without_fallback() -> None:
    settings = load_settings(_enabled_env())

    assert settings.enabled is True
    assert settings.base_url == "http://127.0.0.1:7456"
    assert settings.expected_version == "0.9.4"
    assert settings.expected_channel == "stable"
    assert settings.agent_id == "claude-code"
    assert settings.model_id == "claude-opus-4-1"
    assert settings.design_system_id == "flai-os-v1"
    assert settings.design_system_sha256 == "a" * 64

    missing_model = _enabled_env()
    missing_model.pop("FLAI_OPEN_DESIGN_MODEL_ID")
    with pytest.raises(OpenDesignSettingsError, match="MODEL_ID"):
        load_settings(missing_model)


@pytest.mark.parametrize(
    "path",
    [
        "../index.html",
        "/index.html",
        "C:/index.html",
        "nested\\index.html",
        "CON.md",
        "nested/com1.txt",
        "nested/trailing./index.html",
        "nested//index.html",
        "a/./b.html",
        "./b.html",
        "a/",
    ],
)
def test_candidate_bundle_rejects_cross_platform_unsafe_paths(path: str) -> None:
    with pytest.raises(CandidatePolicyError):
        validate_safe_path(path)
    with pytest.raises(CandidatePolicyError):
        validate_candidate_bundle([(path, "text/html", b"<main>safe</main>")])


@pytest.mark.parametrize(
    "media_type,content",
    [
        ("text/html", b"<script>alert(1)</script>"),
        ("text/html", b'<div onclick="go()">x</div>'),
        ("text/html", b'<img src="https://example.com/x.png">'),
        ("text/html", b'<img srcset="preview-1.png 1x, preview-2.png 2x">'),
        ("text/html", b'<a ping="audit-endpoint">x</a>'),
        ("text/html", b'<iframe src="candidate.html"></iframe>'),
        ("text/html", b'<a href="jav&#x61;script:alert(1)">x</a>'),
        ("text/html", b'<meta http-equiv="refresh" content="0;url=/api/secrets">'),
        ("image/svg+xml", b'<svg><animate attributeName="x"/></svg>'),
        ("text/css", b"@import 'theme.css';"),
        ("text/css", b"a{background:url(data:image/png;base64,AA==)}"),
        ("text/css", b"a{background:url(\\68 ttps://evil/x)}"),
        ("application/json", b'{"url":"blob:deadbeef"}'),
        ("application/json", b'{"slot":"a","slot":"b"}'),
    ],
)
def test_candidate_bundle_rejects_active_or_remote_content(
    media_type: str,
    content: bytes,
) -> None:
    suffix = {
        "text/html": ".html",
        "image/svg+xml": ".svg",
        "text/css": ".css",
        "application/json": ".json",
    }[media_type]
    with pytest.raises(CandidatePolicyError):
        validate_candidate_bundle([(f"candidate{suffix}", media_type, content)])


def test_candidate_bundle_rejects_casefold_collisions_and_unknown_binary() -> None:
    with pytest.raises(CandidatePolicyError, match="case-insensitive"):
        validate_candidate_bundle(
            [
                ("Panel.html", "text/html", b"<main>A</main>"),
                ("panel.html", "text/html", b"<main>B</main>"),
            ]
        )

    with pytest.raises(CandidatePolicyError, match="allowlist"):
        validate_candidate_bundle([("candidate.webp", "image/webp", b"RIFF")])

    with pytest.raises(CandidatePolicyError, match="non-empty"):
        validate_candidate_bundle([("candidate.html", "text/html", b"")])


def test_png_validator_accepts_a_small_non_interlaced_png() -> None:
    info = validate_png(_rgb_png(2, 3))
    assert info == {"width": 2, "height": 3}


def test_png_validator_rejects_palette_dependent_chunks_before_plte() -> None:
    candidate = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 3, 0, 0, 0))
        + _png_chunk(b"tRNS", b"\xff")
        + _png_chunk(b"PLTE", b"\x00\x00\x00")
        + _png_chunk(b"IDAT", zlib.compress(b"\x00\x00"))
        + _png_chunk(b"IEND", b"")
    )

    with pytest.raises(CandidatePolicyError, match="must follow PLTE"):
        validate_png(candidate)


def test_png_validator_rejects_color_space_chunks_after_plte() -> None:
    candidate = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 3, 0, 0, 0))
        + _png_chunk(b"PLTE", b"\x00\x00\x00")
        + _png_chunk(b"gAMA", struct.pack(">I", 45455))
        + _png_chunk(b"IDAT", zlib.compress(b"\x00\x00"))
        + _png_chunk(b"IEND", b"")
    )

    with pytest.raises(CandidatePolicyError, match="must precede PLTE"):
        validate_png(candidate)


@pytest.mark.parametrize("mutation", ["crc", "apng", "interlaced", "trailing", "oversized"])
def test_png_validator_fails_closed_on_structural_or_resource_hazards(mutation: str) -> None:
    if mutation == "crc":
        data = bytearray(_rgb_png())
        data[-5] ^= 1
        candidate = bytes(data)
    elif mutation == "apng":
        original = _rgb_png()
        candidate = original[:33] + _png_chunk(b"acTL", struct.pack(">II", 1, 0)) + original[33:]
    elif mutation == "interlaced":
        ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 1)
        candidate = (
            b"\x89PNG\r\n\x1a\n"
            + _png_chunk(b"IHDR", ihdr)
            + _png_chunk(b"IDAT", zlib.compress(b"\x00\x11\x22\x33"))
            + _png_chunk(b"IEND", b"")
        )
    elif mutation == "trailing":
        candidate = _rgb_png() + b"x"
    else:
        candidate = _rgb_png(4097, 1)

    with pytest.raises(CandidatePolicyError):
        validate_png(candidate)
