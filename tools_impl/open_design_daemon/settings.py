"""Strict, default-off configuration for the Open Design daemon seam."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlsplit


class OpenDesignSettingsError(ValueError):
    """The daemon cannot be contacted under the closed configuration contract."""


@dataclass(frozen=True)
class OpenDesignDaemonSettings:
    enabled: bool
    base_url: str | None = None
    expected_version: str | None = None
    expected_channel: str | None = None
    agent_id: str | None = None
    model_id: str | None = None
    design_system_id: str | None = None
    design_system_sha256: str | None = None


_ENV = {
    "url": "FLAI_OPEN_DESIGN_DAEMON_URL",
    "version": "FLAI_OPEN_DESIGN_DAEMON_VERSION",
    "channel": "FLAI_OPEN_DESIGN_DAEMON_CHANNEL",
    "agent": "FLAI_OPEN_DESIGN_AGENT_ID",
    "model": "FLAI_OPEN_DESIGN_MODEL_ID",
    "design_system": "FLAI_OPEN_DESIGN_DESIGN_SYSTEM_ID",
    "design_system_sha256": "FLAI_OPEN_DESIGN_DESIGN_SYSTEM_SHA256",
}
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,127}$")
_SAFE_CHANNEL = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
_SAFE_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


def _required(env: Mapping[str, str], key: str) -> str:
    name = _ENV[key]
    value = env.get(name)
    if not isinstance(value, str) or not value:
        raise OpenDesignSettingsError(f"{name} is required when the daemon adapter is enabled")
    if value != value.strip():
        raise OpenDesignSettingsError(f"{name} must not contain surrounding whitespace")
    return value


def _validate_loopback_origin(value: str) -> str:
    message = "FLAI_OPEN_DESIGN_DAEMON_URL must be an exact loopback HTTP origin"
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise OpenDesignSettingsError(message) from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or port is None
        or not 1 <= port <= 65535
        or parsed.path != ""
        or parsed.query != ""
        or parsed.fragment != ""
    ):
        raise OpenDesignSettingsError(message)
    canonical_netloc = f"[{parsed.hostname}]:{port}" if parsed.hostname == "::1" else f"{parsed.hostname}:{port}"
    if parsed.netloc != canonical_netloc or value != f"http://{canonical_netloc}":
        raise OpenDesignSettingsError(message)
    return value


def load_settings(env: Mapping[str, str] | None = None) -> OpenDesignDaemonSettings:
    """Load the seam without permissive booleans or identity fallbacks."""

    source = env if env is not None else __import__("os").environ
    raw_enabled = source.get("FLAI_OPEN_DESIGN_DAEMON_ENABLED")
    if raw_enabled is None or raw_enabled == "0":
        return OpenDesignDaemonSettings(enabled=False)
    if raw_enabled != "1":
        raise OpenDesignSettingsError(
            "FLAI_OPEN_DESIGN_DAEMON_ENABLED must be the literal 0 or 1"
        )

    base_url = _validate_loopback_origin(_required(source, "url"))
    version = _required(source, "version")
    channel = _required(source, "channel")
    agent = _required(source, "agent")
    model = _required(source, "model")
    design_system = _required(source, "design_system")
    digest = _required(source, "design_system_sha256")
    if _SAFE_VERSION.fullmatch(version) is None:
        raise OpenDesignSettingsError("FLAI_OPEN_DESIGN_DAEMON_VERSION is not an exact semver")
    if _SAFE_CHANNEL.fullmatch(channel) is None:
        raise OpenDesignSettingsError("FLAI_OPEN_DESIGN_DAEMON_CHANNEL is invalid")
    for name, value in (
        (_ENV["agent"], agent),
        (_ENV["model"], model),
        (_ENV["design_system"], design_system),
    ):
        if _SAFE_ID.fullmatch(value) is None:
            raise OpenDesignSettingsError(f"{name} is invalid")
    if _SHA256.fullmatch(digest) is None:
        raise OpenDesignSettingsError(
            "FLAI_OPEN_DESIGN_DESIGN_SYSTEM_SHA256 must be 64 lowercase hex characters"
        )
    return OpenDesignDaemonSettings(
        enabled=True,
        base_url=base_url,
        expected_version=version,
        expected_channel=channel,
        agent_id=agent,
        model_id=model,
        design_system_id=design_system,
        design_system_sha256=digest,
    )
