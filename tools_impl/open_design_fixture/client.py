"""Open Design client boundary with a deterministic, fail-closed fixture.

The protocol mirrors the verified upstream MCP generation path:
``create_project -> start_run -> get_run -> get_artifact``.  This package does
not connect to the daemon; it exercises the same boundary with checked-in text
fixtures and records every operation as fixture/mock provenance.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping, Protocol

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError as JsonSchemaSchemaError
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

from .design_reference import (
    DesignReferenceError,
    build_design_reference_package,
    canonical_json_bytes,
    design_reference_package_sha256,
    sha256_bytes,
    validate_design_reference_package,
)

FIXTURE_ID = "flai-task-review-assets-v2"
FIXED_REQUEST_SHA256 = "aab2740108a2d13aca53869f6c4c39b732a5ab3c2c3f3848f61bcb7915038f2c"
PINNED_DESIGN_REFERENCE_PACKAGE_SHA256 = "4fa241ae49d3c992168b2589779e24344749300a129e1f9478337974a3d68ca3"

DEFAULT_EXPECTED_FILE_SHA256 = {
    "flai-task-review-candidate.html": "e1242ccccb30758c184d798f50edc2b3fc0f38508c3f70f6a7c0238fa5e27db1",
    "flai-task-review-candidate.svg": "8424d13080e3b1d79cef1e9a60a0e7a1a019d8f3a7bea4103fe3c523534bbd48",
    "request.json": "7b832b113811acec5e6edd23d45d180b85658defaac643206914acb5bd8dd484",
    "response.json": "d54b97caa5d250b6fdfe78df1e20b54ea96654a27ee4b68f72a93ab5daddb097",
    "response.schema.json": "2f8ec4924f4fe8e77287782de8dd8fc2d6c22b789c203d491fc17e44048283ab",
}
PINNED_CANDIDATE_FILE_SHA256 = {
    "flai-task-review-candidate.html": DEFAULT_EXPECTED_FILE_SHA256[
        "flai-task-review-candidate.html"
    ],
    "flai-task-review-candidate.svg": DEFAULT_EXPECTED_FILE_SHA256[
        "flai-task-review-candidate.svg"
    ],
}
PINNED_CANDIDATE_DESCRIPTORS = [
    {
        "id": "flai-task-review-html",
        "kind": "html",
        "filename": "flai-task-review-candidate.html",
        "media_type": "text/html",
        "title": "FLAi-OS 协议契约 HTML 机器夹具",
        "content_sha256": PINNED_CANDIDATE_FILE_SHA256["flai-task-review-candidate.html"],
    },
    {
        "id": "flai-task-review-svg",
        "kind": "svg",
        "filename": "flai-task-review-candidate.svg",
        "media_type": "image/svg+xml",
        "title": "FLAi-OS 协议契约 SVG 机器夹具",
        "content_sha256": PINNED_CANDIDATE_FILE_SHA256["flai-task-review-candidate.svg"],
    },
]
FIXTURE_BUNDLE_SHA256 = "70be2a7428ab385eb85e57845133b6b457402c6421c15d338a7f0a1b6b9eefd8"

_PROJECT_ID = "flai-task-review-fixture"
_PROJECT_NAME = "FLAi-OS task review candidate"
_RUN_ID = "flai-task-review-fixture-run"
_CONVERSATION_ID = "flai-task-review-fixture-conversation"
_EXPECTED_PROTOCOL_TRACE = [
    {"operation": "create_project", "access": "write", "status": "success"},
    {"operation": "start_run", "access": "write", "status": "success"},
    {"operation": "get_run", "access": "read", "status": "succeeded"},
    {"operation": "get_artifact", "access": "read", "status": "success"},
]
_MEDIA_BY_KIND = {"html": "text/html", "svg": "image/svg+xml"}
_EXT_BY_KIND = {"html": ".html", "svg": ".svg"}
_HTML_REQUIRED_TOKENS = (
    "--clay",
    "--clay-deep",
    "--ink",
    "--ink-soft",
    "--ink-faint",
    "--page-bg",
    "--card-bg",
    "--paper-surface",
    "--hairline",
    "--trust-pending",
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


class FixtureValidationError(ValueError):
    """The request, fixture, or protocol result failed a trust check."""


class OpenDesignClient(Protocol):
    """Production-shaped boundary; a future daemon client gets a separate tool id."""

    def create_project(self, payload: Mapping[str, Any]) -> dict[str, Any]: ...

    def start_run(self, payload: Mapping[str, Any]) -> dict[str, Any]: ...

    def get_run(self, payload: Mapping[str, Any]) -> dict[str, Any]: ...

    def get_artifact(self, payload: Mapping[str, Any]) -> dict[str, Any]: ...


def bundle_sha256(file_sha256: Mapping[str, str]) -> str:
    """Hash a canonical path->byte-hash manifest, independent of filesystem order."""

    return sha256_bytes(canonical_json_bytes(dict(file_sha256)))


def response_payload_sha256(output: Mapping[str, Any]) -> str:
    body = dict(output)
    body.pop("response_sha256", None)
    return sha256_bytes(canonical_json_bytes(body))


def _safe_candidate_content(candidate: Mapping[str, Any], content: bytes) -> str:
    kind = candidate.get("kind")
    filename = candidate.get("filename")
    if kind not in _MEDIA_BY_KIND:
        raise FixtureValidationError(f"candidate kind is not allowlisted: {kind!r}")
    if not isinstance(filename, str) or Path(filename).name != filename:
        raise FixtureValidationError(f"candidate filename is not a safe basename: {filename!r}")
    if not filename.endswith(_EXT_BY_KIND[kind]):
        raise FixtureValidationError(f"candidate extension does not match kind: {filename}")
    if candidate.get("media_type") != _MEDIA_BY_KIND[kind]:
        raise FixtureValidationError(f"candidate media_type does not match kind: {filename}")
    actual_sha256 = sha256_bytes(content)
    if candidate.get("content_sha256") != actual_sha256:
        raise FixtureValidationError(
            f"candidate content sha256 mismatch: {filename}: expected "
            f"{candidate.get('content_sha256')}, got {actual_sha256}"
        )
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FixtureValidationError(f"candidate is not UTF-8 text: {filename}") from exc
    lowered = text.lower()
    if kind == "html":
        blocked = ("<script", "<iframe", "<object", "<embed", "javascript:", "<form")
        blocked += ("<link", "<base", "<svg", "@import", "url(", "http-equiv")
        if any(marker in lowered for marker in blocked) or re.search(r"\son[a-z]+\s*=", lowered):
            raise FixtureValidationError(f"HTML candidate contains active content: {filename}")
        if re.search(r"(?:src|href)\s*=\s*['\"]\s*(?:https?:)?//", lowered):
            raise FixtureValidationError(f"HTML candidate references an external asset: {filename}")
    else:
        blocked = (
            "<script",
            "<foreignobject",
            "<image",
            "<set",
            "<animate",
            "javascript:",
            "xlink:",
            "url(",
            "@import",
        )
        if any(marker in lowered for marker in blocked) or re.search(r"\shref\s*=", lowered):
            raise FixtureValidationError(f"SVG candidate contains active/external content: {filename}")
    return text


_CSS_VAR_REFERENCE = r"var\(\s*(--[a-z0-9-]+)\s*\)"
_CSS_BORDER_WITH_TOKEN = re.compile(
    rf"^(?:0|(?:\d+(?:\.\d+)?)(?:px|rem|em)|thin|medium|thick)\s+"
    rf"(?:solid|dashed|dotted|double|groove|ridge|inset|outset)\s+{_CSS_VAR_REFERENCE}$"
)
_SVG_COLOR_ATTRIBUTES = (
    "color",
    "fill",
    "flood-color",
    "lighting-color",
    "solid-color",
    "stop-color",
    "stroke",
    "text-decoration",
    "text-decoration-color",
)


def _is_color_bearing_css_property(property_name: str) -> bool:
    if property_name == "color-scheme":
        return False
    return (
        property_name == "color"
        or property_name.endswith("-color")
        or property_name.startswith("background")
        or (property_name.startswith("border") and "radius" not in property_name)
        or property_name
        in {
            "box-shadow",
            "column-rule",
            "fill",
            "filter",
            "outline",
            "stroke",
            "text-decoration",
            "text-emphasis",
            "text-shadow",
            "-webkit-text-stroke",
        }
    )


def _validate_html_color_usage(scan_text: str, tokens: Mapping[str, Any]) -> None:
    legacy_or_inline = (
        "alink",
        "bgcolor",
        "bordercolor",
        "color",
        "link",
        "style",
        "text",
        "vlink",
    )
    attribute_pattern = "|".join(legacy_or_inline)
    if re.search(rf"\s(?:{attribute_pattern})\s*=", scan_text, flags=re.IGNORECASE):
        raise FixtureValidationError(
            "HTML fixture must not use inline style or legacy color attributes"
        )
    style_blocks = re.findall(r"<style(?:\s[^>]*)?>(.*?)</style\s*>", scan_text, flags=re.IGNORECASE | re.DOTALL)
    if len(style_blocks) != 1:
        raise FixtureValidationError("HTML fixture must contain exactly one inspectable style block")
    style_text = style_blocks[0]
    if "/*" in style_text or "*/" in style_text:
        raise FixtureValidationError("HTML fixture color grammar must not use CSS comments")
    if "\\" in style_text:
        raise FixtureValidationError("HTML fixture color grammar must not use CSS escapes")
    if re.search(r"(?m)(?:^|[;{])\s*--[a-zA-Z0-9-]+\s*:", style_text):
        raise FixtureValidationError("HTML fixture must not redefine pinned color tokens")
    declarations = re.findall(
        r"(?m)(?<![-\w])(-?[a-zA-Z][a-zA-Z0-9-]*)\s*:\s*([^;{}]+)(?:;|(?=\s*}))",
        style_text,
    )
    for raw_property, raw_value in declarations:
        property_name = raw_property.lower()
        if not _is_color_bearing_css_property(property_name):
            continue
        value = raw_value.strip()
        simple_match = re.fullmatch(_CSS_VAR_REFERENCE, value)
        border_match = _CSS_BORDER_WITH_TOKEN.fullmatch(value)
        token_name = simple_match.group(1) if simple_match else border_match.group(1) if border_match else None
        if token_name is None or token_name not in tokens:
            raise FixtureValidationError(
                f"HTML fixture color declaration must use one pinned token: {property_name}: {value}"
            )


def _validate_svg_color_usage(text: str, allowed_hex: set[str]) -> None:
    if re.search(r"<style\b|\sstyle\s*=", text, flags=re.IGNORECASE):
        raise FixtureValidationError("SVG fixture must not use style-based color expressions")
    if re.search(r"\sfilter\s*=", text, flags=re.IGNORECASE):
        raise FixtureValidationError("SVG fixture must not use filter-based color expressions")
    attribute_pattern = "|".join(re.escape(name) for name in _SVG_COLOR_ATTRIBUTES)
    declarations = re.findall(
        rf"\s(?:{attribute_pattern})\s*=\s*(['\"])(.*?)\1",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for _quote, raw_value in declarations:
        value = raw_value.strip().lower()
        if value not in allowed_hex:
            raise FixtureValidationError(
                f"SVG fixture color attribute is not a pinned token value: {raw_value.strip()}"
            )


def _validate_candidate_design_reference(
    candidate: Mapping[str, Any],
    text: str,
    package: Mapping[str, Any],
) -> None:
    """Prove fixture colors/tokens are a subset of the pinned design package."""

    tokens = package.get("tokens")
    if not isinstance(tokens, Mapping):
        raise FixtureValidationError("design reference package has no token map")
    allowed_hex = {
        value.lower()
        for value in tokens.values()
        if isinstance(value, str) and re.fullmatch(r"#[a-fA-F0-9]{6}", value)
    }
    observed_hex = {
        value.lower()
        for value in re.findall(r"(?<![a-fA-F0-9])#[a-fA-F0-9]{3,8}\b", text)
    }
    unexpected_hex = sorted(observed_hex - allowed_hex)
    if unexpected_hex:
        raise FixtureValidationError(
            f"candidate uses colors outside the design reference token set: {unexpected_hex}"
        )

    scan_text = text
    if candidate.get("kind") == "html":
        for token in _HTML_REQUIRED_TOKENS:
            matches = re.findall(
                rf"(?m)^\s*{re.escape(token)}\s*:\s*([^;\n]+);",
                text,
            )
            expected_value = tokens.get(token)
            if len(matches) != 1 or matches[0].strip() != expected_value:
                raise FixtureValidationError(
                    f"HTML fixture design token mismatch: {token}: expected {expected_value!r}, got {matches}"
                )
            scan_text, removed = re.subn(
                rf"(?m)^\s*{re.escape(token)}\s*:\s*[^;\n]+;\s*$",
                "",
                scan_text,
            )
            if removed != 1:
                raise FixtureValidationError(f"HTML fixture token scan boundary mismatch: {token}")
    else:
        clay = str(tokens.get("--clay", "")).lower()
        if not clay or text.lower().count(clay) != 1:
            raise FixtureValidationError("SVG fixture must use clay exactly once, on the review action")

    for forbidden in ("--trust-real", "--trust-signed", "--trust-fail"):
        if re.search(rf"var\(\s*{re.escape(forbidden)}\b", scan_text, flags=re.IGNORECASE):
            raise FixtureValidationError(
                f"machine-only fixture must not consume reserved trust token {forbidden}"
            )
        value = str(tokens.get(forbidden, "")).lower()
        if value and re.search(rf"(?<![a-fA-F0-9]){re.escape(value)}\b", scan_text, flags=re.IGNORECASE):
            raise FixtureValidationError(
                f"machine-only fixture must not consume reserved trust color {forbidden}"
            )
    if re.search(r"\b(?:rgb|rgba|hsl|hsla)\s*\(", scan_text, flags=re.IGNORECASE):
        raise FixtureValidationError(
            "machine-only fixture must not use rgb/rgba/hsl/hsla color functions outside pinned tokens"
        )
    if candidate.get("kind") == "html":
        _validate_html_color_usage(scan_text, tokens)
    else:
        _validate_svg_color_usage(scan_text, allowed_hex)


class FixtureOpenDesignClient:
    """Local deterministic implementation of the production-shaped protocol."""

    def __init__(
        self,
        *,
        fixture_dir: Path | None = None,
    ) -> None:
        self.fixture_dir = fixture_dir or (Path(__file__).resolve().parent / "fixtures")
        self._expected_file_sha256 = dict(DEFAULT_EXPECTED_FILE_SHA256)
        self._expected_bundle_sha256 = FIXTURE_BUNDLE_SHA256
        self._unsafe_test_integrity_override = False
        self._request: dict[str, Any] | None = None
        self._request_sha256 = ""
        self._design_reference_package: dict[str, Any] | None = None
        self._candidate_payloads: list[dict[str, Any]] = []

    @classmethod
    def _unsafe_with_test_integrity_manifest(
        cls,
        *,
        fixture_dir: Path,
        expected_file_sha256: Mapping[str, str],
        expected_bundle_sha256: str,
    ) -> FixtureOpenDesignClient:
        """Test-only seam for reaching validators behind the immutable byte gate.

        Instances created here are physically barred from returning a success
        result, even when a mutation is semantically accepted by an inner
        validator. Production adapters must use the exact pinned constructor.
        """

        client = cls(fixture_dir=fixture_dir)
        client._expected_file_sha256 = dict(expected_file_sha256)
        client._expected_bundle_sha256 = expected_bundle_sha256
        client._unsafe_test_integrity_override = True
        return client

    def _read_verified_files(self) -> dict[str, bytes]:
        actual_hashes: dict[str, str] = {}
        contents: dict[str, bytes] = {}
        if set(self._expected_file_sha256) != set(DEFAULT_EXPECTED_FILE_SHA256):
            raise FixtureValidationError("fixture integrity manifest file set mismatch")
        for filename, expected_sha256 in sorted(self._expected_file_sha256.items()):
            path = self.fixture_dir / filename
            if path.is_symlink():
                raise FixtureValidationError(f"fixture file must not be a symlink: {filename}")
            if not path.is_file():
                raise FixtureValidationError(f"fixture file missing: {filename}")
            content = path.read_bytes()
            actual_sha256 = sha256_bytes(content)
            if actual_sha256 != expected_sha256:
                raise FixtureValidationError(
                    f"fixture byte sha256 mismatch: {filename}: expected {expected_sha256}, got {actual_sha256}"
                )
            contents[filename] = content
            actual_hashes[filename] = actual_sha256
        actual_bundle_sha256 = bundle_sha256(actual_hashes)
        if actual_bundle_sha256 != self._expected_bundle_sha256:
            raise FixtureValidationError(
                "fixture bundle sha256 mismatch: "
                f"expected {self._expected_bundle_sha256}, got {actual_bundle_sha256}"
            )
        return contents

    def _verify_and_load(self, request: Mapping[str, Any]) -> None:
        request_sha256 = sha256_bytes(canonical_json_bytes(request))
        self._request_sha256 = request_sha256
        if request_sha256 != FIXED_REQUEST_SHA256:
            raise FixtureValidationError(
                f"request sha256 mismatch: expected {FIXED_REQUEST_SHA256}, got {request_sha256}"
            )

        package = build_design_reference_package()
        package_sha256 = design_reference_package_sha256(package)
        if package_sha256 != PINNED_DESIGN_REFERENCE_PACKAGE_SHA256:
            raise FixtureValidationError(
                "design reference package sha256 drift: "
                f"expected {PINNED_DESIGN_REFERENCE_PACKAGE_SHA256}, got {package_sha256}"
            )
        request_binding = request.get("design_reference_package")
        if not isinstance(request_binding, Mapping) or request_binding.get("package_sha256") != package_sha256:
            raise FixtureValidationError("request is not bound to the verified design reference package sha256")

        contents = self._read_verified_files()
        try:
            fixture_request = json.loads(contents["request.json"].decode("utf-8"))
            response_schema = json.loads(contents["response.schema.json"].decode("utf-8"))
            descriptor = json.loads(contents["response.json"].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FixtureValidationError(f"fixture JSON is malformed: {exc}") from exc
        if sha256_bytes(canonical_json_bytes(fixture_request)) != FIXED_REQUEST_SHA256:
            raise FixtureValidationError("checked-in request canonical sha256 mismatch")
        if fixture_request != dict(request):
            raise FixtureValidationError("request does not equal the checked-in fixed request")
        try:
            Draft202012Validator.check_schema(response_schema)
            Draft202012Validator(response_schema).validate(descriptor)
        except (JsonSchemaValidationError, JsonSchemaSchemaError) as exc:
            raise FixtureValidationError(f"response schema validation failed: {exc.message}") from exc
        if descriptor.get("design_reference_package_sha256") != package_sha256:
            raise FixtureValidationError("response is not bound to the verified design reference package sha256")

        candidates = descriptor.get("candidates")
        if not isinstance(candidates, list) or {item.get("kind") for item in candidates} != {"html", "svg"}:
            raise FixtureValidationError("fixture must contain exactly one HTML and one SVG candidate")
        ids: set[str] = set()
        filenames: set[str] = set()
        candidate_payloads: list[dict[str, Any]] = []
        for candidate in candidates:
            candidate_id = candidate.get("id")
            filename = candidate.get("filename")
            if candidate_id in ids or filename in filenames:
                raise FixtureValidationError("candidate ids and filenames must be unique")
            ids.add(candidate_id)
            filenames.add(filename)
            if filename not in contents:
                raise FixtureValidationError(f"candidate file is not integrity-pinned: {filename}")
            content = contents[filename]
            text = _safe_candidate_content(candidate, content)
            _validate_candidate_design_reference(candidate, text, package)
            candidate_payloads.append({**candidate, "size_bytes": len(content), "content": content.decode("utf-8")})

        self._request = dict(request)
        self._design_reference_package = package
        self._candidate_payloads = candidate_payloads

    def create_project(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        expected = {
            "name": _PROJECT_NAME,
            "id": _PROJECT_ID,
        }
        if dict(payload) != expected:
            raise FixtureValidationError("create_project payload mismatch")
        if self._request is None:
            raise FixtureValidationError("fixed request was not staged before create_project")
        return {"project": {"id": _PROJECT_ID, "name": _PROJECT_NAME}, "conversationId": _CONVERSATION_ID}

    def start_run(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if self._request is None or self._design_reference_package is None:
            raise FixtureValidationError("start_run called before verified create_project")
        expected = {
            "project": _PROJECT_ID,
            "prompt": self._request["asset_request"]["intent"],
            "inputs": {
                "candidate_only": True,
                "design_reference_package": self._design_reference_package,
                "design_reference_package_sha256": PINNED_DESIGN_REFERENCE_PACKAGE_SHA256,
            },
        }
        if dict(payload) != expected:
            raise FixtureValidationError("start_run payload mismatch")
        return {"runId": _RUN_ID, "projectId": _PROJECT_ID, "status": "queued"}

    def get_run(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if dict(payload) != {"runId": _RUN_ID}:
            raise FixtureValidationError("get_run payload mismatch")
        return {
            "id": _RUN_ID,
            "projectId": _PROJECT_ID,
            "status": "succeeded",
            "entryFile": "flai-task-review-candidate.html",
        }

    def get_artifact(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        expected = {
            "project": _PROJECT_ID,
            "entry": "flai-task-review-candidate.html",
            "include": "all",
        }
        if dict(payload) != expected:
            raise FixtureValidationError("get_artifact payload mismatch")
        return {
            "project": {"id": _PROJECT_ID, "name": _PROJECT_NAME},
            "entry": expected["entry"],
            "truncated": False,
            "files": list(self._candidate_payloads),
        }

    def generate(self, request: Mapping[str, Any]) -> dict[str, Any]:
        try:
            self._verify_and_load(request)
            if self._unsafe_test_integrity_override:
                raise FixtureValidationError(
                    "unsafe test integrity override cannot emit a successful fixture claim"
                )
            if self._design_reference_package is None:
                raise FixtureValidationError("verified design reference package was not staged")
            return run_generation_sequence(self, request, self._design_reference_package)
        except (FixtureValidationError, DesignReferenceError, OSError, TypeError) as exc:
            return failed_tool_output(
                f"{exc.__class__.__name__}: {exc}",
                request_sha256=self._request_sha256,
            )


def run_generation_sequence(
    client: OpenDesignClient,
    request: Mapping[str, Any],
    design_package: Mapping[str, Any],
) -> dict[str, Any]:
    """Orchestrate the verified upstream operation order against any client."""

    if getattr(client, "_unsafe_test_integrity_override", False) is True:
        raise FixtureValidationError(
            "unsafe test integrity override cannot enter the public generation sequence"
        )
    protocol_trace: list[dict[str, str]] = []
    request_sha256 = sha256_bytes(canonical_json_bytes(request))
    if request_sha256 != FIXED_REQUEST_SHA256:
        raise FixtureValidationError(
            f"request sha256 mismatch: expected {FIXED_REQUEST_SHA256}, got {request_sha256}"
        )
    if not isinstance(design_package, Mapping):
        raise FixtureValidationError("design reference package must be an object")
    validate_design_reference_package(design_package)
    package_sha256 = design_reference_package_sha256(design_package)
    if package_sha256 != PINNED_DESIGN_REFERENCE_PACKAGE_SHA256:
        raise FixtureValidationError("design reference package sha256 mismatch before start_run")
    request_binding = request.get("design_reference_package")
    if not isinstance(request_binding, Mapping) or request_binding.get("package_sha256") != package_sha256:
        raise FixtureValidationError("request is not bound to the verified design reference package sha256")

    project = client.create_project(
        {
            "name": _PROJECT_NAME,
            "id": _PROJECT_ID,
        }
    )
    expected_project = {
        "project": {"id": _PROJECT_ID, "name": _PROJECT_NAME},
        "conversationId": _CONVERSATION_ID,
    }
    if project != expected_project:
        raise FixtureValidationError(
            f"create_project result mismatch: expected {expected_project}, got {project}"
        )
    project_id = project["project"]["id"]
    protocol_trace.append(
        {"operation": "create_project", "access": "write", "status": "success"}
    )

    started = client.start_run(
        {
            "project": project_id,
            "prompt": request["asset_request"]["intent"],
            "inputs": {
                "candidate_only": True,
                "design_reference_package": design_package,
                "design_reference_package_sha256": PINNED_DESIGN_REFERENCE_PACKAGE_SHA256,
            },
        }
    )
    expected_started = {
        "runId": _RUN_ID,
        "projectId": project_id,
        "status": "queued",
    }
    if started != expected_started:
        raise FixtureValidationError(
            f"start_run result mismatch: expected {expected_started}, got {started}"
        )
    run_id = started["runId"]
    protocol_trace.append(
        {"operation": "start_run", "access": "write", "status": "success"}
    )
    run = client.get_run({"runId": run_id})
    expected_entry = "flai-task-review-candidate.html"
    expected_run = {
        "id": run_id,
        "projectId": project_id,
        "status": "succeeded",
        "entryFile": expected_entry,
    }
    if run != expected_run:
        raise FixtureValidationError(
            f"get_run result mismatch: expected {expected_run}, got {run}"
        )
    protocol_trace.append(
        {"operation": "get_run", "access": "read", "status": run["status"]}
    )
    artifact = client.get_artifact(
        {"project": project_id, "entry": expected_entry, "include": "all"}
    )
    expected_artifact_fields = {"project", "entry", "truncated", "files"}
    if set(artifact) != expected_artifact_fields:
        raise FixtureValidationError("get_artifact result fields do not match the closed contract")
    if artifact.get("project") != expected_project["project"]:
        raise FixtureValidationError("get_artifact project does not match the verified project")
    if artifact.get("entry") != expected_entry:
        raise FixtureValidationError("get_artifact entry does not match the verified run entry")
    if artifact.get("truncated") is not False:
        raise FixtureValidationError("get_artifact returned a truncated bundle")
    candidates = artifact.get("files")
    if not isinstance(candidates, list) or {candidate.get("kind") for candidate in candidates} != {"html", "svg"}:
        raise FixtureValidationError("get_artifact did not return the checked HTML/SVG pair")
    protocol_trace.append(
        {"operation": "get_artifact", "access": "read", "status": "success"}
    )

    output: dict[str, Any] = {
        "status": "success",
        "generator_mode": "fixture",
        "mock": True,
        "production_daemon_used": False,
        "fixture_id": FIXTURE_ID,
        "fixture_sha256": FIXTURE_BUNDLE_SHA256,
        "request_sha256": FIXED_REQUEST_SHA256,
        "response_sha256": "",
        "design_reference_package_sha256": PINNED_DESIGN_REFERENCE_PACKAGE_SHA256,
        "design_reference_package": design_package,
        "protocol_trace": protocol_trace,
        "candidates": candidates,
        "error_message": None,
    }
    output["response_sha256"] = response_payload_sha256(output)
    validate_tool_response(output)
    return output


def failed_tool_output(message: str, *, request_sha256: str = "") -> dict[str, Any]:
    output: dict[str, Any] = {
        "status": "failed",
        "generator_mode": "fixture",
        "mock": True,
        "production_daemon_used": False,
        "fixture_id": FIXTURE_ID,
        "fixture_sha256": "",
        "request_sha256": request_sha256,
        "response_sha256": "",
        "design_reference_package_sha256": "",
        "design_reference_package": {},
        "protocol_trace": [],
        "candidates": [],
        "error_message": message,
    }
    output["response_sha256"] = response_payload_sha256(output)
    return output


def validate_tool_response(output: Mapping[str, Any]) -> None:
    """Validate hashes and safety invariants independently of ToolRegistry schema."""

    required = {
        "status",
        "generator_mode",
        "mock",
        "production_daemon_used",
        "fixture_id",
        "fixture_sha256",
        "request_sha256",
        "response_sha256",
        "design_reference_package_sha256",
        "design_reference_package",
        "protocol_trace",
        "candidates",
        "error_message",
    }
    if set(output) != required:
        raise FixtureValidationError("tool response fields do not match the closed contract")
    if output.get("generator_mode") != "fixture" or output.get("mock") is not True:
        raise FixtureValidationError("tool response lost fixture/mock identity")
    if output.get("production_daemon_used") is not False:
        raise FixtureValidationError("fixture tool must never claim production daemon use")
    if output.get("fixture_id") != FIXTURE_ID:
        raise FixtureValidationError("tool response fixture_id mismatch")
    expected_response_sha256 = response_payload_sha256(output)
    if output.get("response_sha256") != expected_response_sha256:
        raise FixtureValidationError(
            "response_sha256 mismatch: "
            f"expected {expected_response_sha256}, got {output.get('response_sha256')}"
        )

    if output.get("status") != "success":
        raise FixtureValidationError(f"tool response is not successful: {output.get('error_message')}")
    if output.get("fixture_sha256") != FIXTURE_BUNDLE_SHA256:
        raise FixtureValidationError("tool response fixture_sha256 mismatch")
    if output.get("request_sha256") != FIXED_REQUEST_SHA256:
        raise FixtureValidationError("tool response request_sha256 mismatch")
    package = output.get("design_reference_package")
    if not isinstance(package, dict):
        raise FixtureValidationError("tool response design_reference_package must be an object")
    validate_design_reference_package(package)
    package_sha256 = design_reference_package_sha256(package)
    if package_sha256 != PINNED_DESIGN_REFERENCE_PACKAGE_SHA256:
        raise FixtureValidationError("tool response design reference package sha256 mismatch")
    if output.get("design_reference_package_sha256") != package_sha256:
        raise FixtureValidationError("tool response design reference binding mismatch")
    if output.get("error_message") is not None:
        raise FixtureValidationError("successful tool response must have error_message=null")

    trace = output.get("protocol_trace")
    if trace != _EXPECTED_PROTOCOL_TRACE:
        raise FixtureValidationError("tool response protocol trace mismatch")
    candidates = output.get("candidates")
    if not isinstance(candidates, list) or not all(isinstance(candidate, Mapping) for candidate in candidates):
        raise FixtureValidationError("tool response candidates must be objects")
    if len(candidates) != len(PINNED_CANDIDATE_DESCRIPTORS):
        raise FixtureValidationError("tool response candidates must be the pinned HTML/SVG pair")
    runtime_fields = {"size_bytes", "content"}
    for index, (candidate, descriptor) in enumerate(
        zip(candidates, PINNED_CANDIDATE_DESCRIPTORS, strict=True)
    ):
        if set(candidate) != set(descriptor) | runtime_fields:
            raise FixtureValidationError(
                f"tool response candidate fields mismatch at pinned index {index}"
            )
        metadata = {
            field: expected
            for field, expected in descriptor.items()
            if field != "content_sha256"
        }
        if any(candidate.get(field) != expected for field, expected in metadata.items()):
            raise FixtureValidationError(
                f"tool response candidate descriptor mismatch at pinned index {index}"
            )
        content = candidate.get("content")
        if not isinstance(content, str):
            raise FixtureValidationError("tool response candidate content must be text")
        content_bytes = content.encode("utf-8")
        if candidate.get("size_bytes") != len(content_bytes):
            raise FixtureValidationError("tool response candidate size_bytes mismatch")
        filename = candidate["filename"]
        actual_sha256 = sha256_bytes(content_bytes)
        if actual_sha256 != PINNED_CANDIDATE_FILE_SHA256[filename]:
            raise FixtureValidationError(
                "tool response candidate is not bound to the pinned fixture bytes: "
                f"{filename}: expected {PINNED_CANDIDATE_FILE_SHA256[filename]}, got {actual_sha256}"
            )
        text = _safe_candidate_content(candidate, content_bytes)
        _validate_candidate_design_reference(candidate, text, package)
