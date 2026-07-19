"""Deterministic FLAi design-reference package grounded in repository SSOT.

The package is not a second design system.  It is a byte-stable, allowlisted
projection of the existing ``App.vue`` tokens plus hashes of the three governing
sources.  Any missing source, source drift, missing token, or duplicate token is a
hard failure so a fixture can never silently generate against stale styling rules.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "flai-design-reference-package/v1"

SOURCE_PATHS = {
    "app_tokens": "frontend/src/App.vue",
    "motion_system": "docs/design/MOTION-SYSTEM.md",
    "ui_paradigm": "docs/design/UI-PARADIGM.md",
}

# Pinned to the trusted source bytes for fixture snapshot 0.1.1.  Updating any
# SSOT requires an explicit fixture snapshot update; runtime never learns new
# hashes from the files it is supposed to authenticate.  ``SCHEMA_VERSION``
# changes only when the projected package shape or semantics change.
EXPECTED_SOURCE_SHA256 = {
    "frontend/src/App.vue": "b19bfd2fad7d66e6d02917f4e20d2e78c1ea30d48d836d5aed987ad0a5219ed7",
    "docs/design/MOTION-SYSTEM.md": "8942f2d781e90b80af07fe61ac8697d9a3a6f7f46ce254d04ceadfa1b858bb9a",
    "docs/design/UI-PARADIGM.md": "6985d3ce38d9667d4a351c44499f0cd4685257adca956fb6475e0ca6247677b9",
}

# Only tokens actually consumed by the checked-in candidates are projected.  The
# order is part of the contract even though canonical JSON also sorts object keys.
TOKEN_ALLOWLIST = (
    "--clay",
    "--clay-deep",
    "--ink",
    "--ink-soft",
    "--ink-faint",
    "--page-bg",
    "--card-bg",
    "--paper-surface",
    "--hairline",
    "--trust-real",
    "--trust-signed",
    "--trust-fail",
    "--trust-pending",
    "--focus-ring-clay",
    "--radius-sm",
    "--radius-lg",
    "--space-1",
    "--space-2",
    "--space-3",
    "--space-4",
    "--space-6",
    "--shadow-card",
    "--serif",
    "--sans",
)

TRUST_COLOR_CONSTRAINTS = {
    "--clay": "work_or_selected_only",
    "--trust-fail": "true_failure_or_rejection_only",
    "--trust-pending": "unverified_degraded_or_waiting_review_only",
    "--trust-real": "real_evidence_only",
    "--trust-signed": "human_signed_only",
    "cancelled": "neutral_no_trust_color",
    "completed": "neutral_no_trust_color",
    "human_is_only_signer": True,
}


class DesignReferenceError(ValueError):
    """The live repository cannot prove the pinned design reference."""


def canonical_json_bytes(value: Any) -> bytes:
    """Return the single canonical JSON encoding used by every fixture hash."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _first_root_block(app_source: str) -> str:
    match = re.search(r"(?m)^:root\s*\{", app_source)
    if match is None:
        raise DesignReferenceError("App.vue missing light :root token block")
    start = match.end()
    depth = 1
    for index in range(start, len(app_source)):
        char = app_source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return app_source[start:index]
    raise DesignReferenceError("App.vue light :root token block is not closed")


def _extract_allowlisted_tokens(app_source: str) -> dict[str, str]:
    block = _first_root_block(app_source)
    tokens: dict[str, str] = {}
    for token in TOKEN_ALLOWLIST:
        matches = re.findall(
            rf"(?m)^\s*{re.escape(token)}\s*:\s*([^;\n]+);",
            block,
        )
        if len(matches) != 1:
            raise DesignReferenceError(
                f"App.vue token {token} expected exactly once in light :root; found {len(matches)}"
            )
        value = matches[0].strip()
        if not value:
            raise DesignReferenceError(f"App.vue token {token} has an empty value")
        tokens[token] = value
    return tokens


def build_design_reference_package(
    *,
    repo_root: Path | None = None,
    expected_source_sha256: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Verify pinned sources and build the deterministic package object.

    ``expected_source_sha256`` is an explicit test seam.  Production callers omit
    it and therefore always use the hardcoded integrity manifest above.
    """

    root = (repo_root or _repo_root()).resolve()
    expected = dict(expected_source_sha256 or EXPECTED_SOURCE_SHA256)
    sources: dict[str, dict[str, str]] = {}
    source_bytes: dict[str, bytes] = {}

    for source_id, relative_path in SOURCE_PATHS.items():
        path = root / relative_path
        if path.is_symlink():
            raise DesignReferenceError(f"design SSOT must not be a symlink: {relative_path}")
        if not path.is_file():
            raise DesignReferenceError(f"design SSOT missing: {relative_path}")
        content = path.read_bytes()
        actual_sha256 = sha256_bytes(content)
        pinned_sha256 = expected.get(relative_path)
        if pinned_sha256 is None:
            raise DesignReferenceError(f"design SSOT has no pinned sha256: {relative_path}")
        if actual_sha256 != pinned_sha256:
            raise DesignReferenceError(
                f"design SSOT sha256 drift: {relative_path}: expected {pinned_sha256}, got {actual_sha256}"
            )
        sources[source_id] = {"path": relative_path, "sha256": actual_sha256}
        source_bytes[source_id] = content

    try:
        app_source = source_bytes["app_tokens"].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DesignReferenceError("frontend/src/App.vue is not valid UTF-8") from exc

    package = {
        "schema_version": SCHEMA_VERSION,
        "sources": sources,
        "theme": "light",
        "token_allowlist": list(TOKEN_ALLOWLIST),
        "tokens": _extract_allowlisted_tokens(app_source),
        "trust_color_constraints": dict(TRUST_COLOR_CONSTRAINTS),
    }
    validate_design_reference_package(package)
    return package


def design_reference_package_sha256(package: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(package))


def validate_design_reference_package(package: Mapping[str, Any]) -> None:
    """Self-check the projected structure before it crosses the tool boundary."""

    if package.get("schema_version") != SCHEMA_VERSION:
        raise DesignReferenceError("design reference schema_version mismatch")
    if package.get("theme") != "light":
        raise DesignReferenceError("design reference theme must be light")
    if package.get("token_allowlist") != list(TOKEN_ALLOWLIST):
        raise DesignReferenceError("design reference token allowlist mismatch")
    tokens = package.get("tokens")
    if not isinstance(tokens, dict) or set(tokens) != set(TOKEN_ALLOWLIST):
        raise DesignReferenceError("design reference tokens do not match the allowlist")
    if package.get("trust_color_constraints") != TRUST_COLOR_CONSTRAINTS:
        raise DesignReferenceError("design reference trust-color constraints mismatch")
    sources = package.get("sources")
    if not isinstance(sources, dict) or set(sources) != set(SOURCE_PATHS):
        raise DesignReferenceError("design reference sources mismatch")
    for source_id, relative_path in SOURCE_PATHS.items():
        source = sources.get(source_id)
        if not isinstance(source, dict) or source.get("path") != relative_path:
            raise DesignReferenceError(f"design reference source path mismatch: {source_id}")
        if re.fullmatch(r"[a-f0-9]{64}", str(source.get("sha256", ""))) is None:
            raise DesignReferenceError(f"design reference source sha256 invalid: {source_id}")
