"""Direct loopback REST client for the pinned Open Design daemon contract."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping
from urllib.parse import quote, urlsplit

import httpx

from .policy import CandidatePolicyError, validate_safe_path
from .settings import OpenDesignDaemonSettings


class OpenDesignDaemonError(RuntimeError):
    """The upstream daemon did not satisfy the exact REST contract."""


_MAX_JSON_BYTES = 1024 * 1024
_MAX_FILE_BYTES = 4 * 1024 * 1024


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_bounded_response(
    response: httpx.Response,
    *,
    limit: int,
    path: str,
) -> bytes:
    content_encoding = response.headers.get("content-encoding", "").strip().casefold()
    if content_encoding not in {"", "identity"}:
        raise OpenDesignDaemonError(f"{path} returned forbidden content-encoding")
    raw_length = response.headers.get("content-length")
    if raw_length is not None:
        try:
            announced_length = int(raw_length, 10)
        except ValueError as exc:
            raise OpenDesignDaemonError(f"{path} returned invalid content-length") from exc
        if announced_length < 0 or announced_length > limit:
            raise OpenDesignDaemonError(f"{path} exceeded the response byte limit")
    content = bytearray()
    for chunk in response.iter_raw():
        if len(content) + len(chunk) > limit:
            raise OpenDesignDaemonError(f"{path} exceeded the response byte limit")
        content.extend(chunk)
    return bytes(content)


def _strict_json(content: bytes, path: str) -> dict[str, Any]:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(
            content.decode("utf-8", errors="strict"),
            parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)),
            object_pairs_hook=unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise OpenDesignDaemonError(f"{path} returned invalid strict JSON") from exc
    if not isinstance(value, dict):
        raise OpenDesignDaemonError(f"{path} JSON root must be an object")
    return value


def _model_id(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        candidate = value.get("id")
        return candidate if isinstance(candidate, str) else None
    return None


class OpenDesignHttpClient:
    """No-proxy, no-redirect, no-retry client with exact identity preflight."""

    def __init__(
        self,
        settings: OpenDesignDaemonSettings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if settings.enabled is not True or settings.base_url is None:
            raise OpenDesignDaemonError("Open Design daemon adapter is disabled")
        self.settings = settings
        self._http = httpx.Client(
            base_url=settings.base_url,
            timeout=httpx.Timeout(30.0, connect=5.0),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
            headers={"accept": "application/json", "user-agent": "flai-os-open-design-adapter/0.1"},
        )

    def __enter__(self) -> "OpenDesignHttpClient":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        expected_status: int = 200,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if method not in {"GET", "POST"} or not path.startswith("/api/") or "/raw/" in path:
            raise OpenDesignDaemonError("adapter attempted a non-allowlisted daemon request")
        try:
            with self._http.stream(method, path, json=body) as response:
                if response.status_code != expected_status:
                    raise OpenDesignDaemonError(
                        f"{method} {path} returned unexpected HTTP {response.status_code}"
                    )
                content_type = (
                    response.headers.get("content-type", "")
                    .split(";", 1)[0]
                    .strip()
                    .casefold()
                )
                if content_type != "application/json":
                    raise OpenDesignDaemonError(f"{path} returned an invalid JSON media envelope")
                content = _read_bounded_response(
                    response,
                    limit=_MAX_JSON_BYTES,
                    path=path,
                )
        except httpx.HTTPError as exc:
            raise OpenDesignDaemonError(f"{method} {path} failed at the loopback boundary") from exc
        return _strict_json(content, path)

    def preflight(self) -> dict[str, Any]:
        expected_version = self.settings.expected_version
        expected_channel = self.settings.expected_channel
        agent_id = self.settings.agent_id
        model_id = self.settings.model_id
        design_system_id = self.settings.design_system_id
        expected_design_digest = self.settings.design_system_sha256
        if not all(
            isinstance(value, str) and value
            for value in (
                expected_version,
                expected_channel,
                agent_id,
                model_id,
                design_system_id,
                expected_design_digest,
            )
        ):
            raise OpenDesignDaemonError("enabled daemon settings lost an exact identity binding")

        health = self._request_json("GET", "/api/health")
        if set(health) != {"ok", "version"} or health != {
            "ok": True,
            "version": expected_version,
        }:
            raise OpenDesignDaemonError("daemon health identity mismatch")
        ready = self._request_json("GET", "/api/ready")
        if set(ready) != {"ok", "ready", "version"} or ready != {
            "ok": True,
            "ready": True,
            "version": expected_version,
        }:
            raise OpenDesignDaemonError("daemon is not exactly ready")
        version_payload = self._request_json("GET", "/api/version")
        if set(version_payload) != {"version"} or not isinstance(
            version_payload.get("version"), dict
        ):
            raise OpenDesignDaemonError("daemon version envelope mismatch")
        version = version_payload["version"]
        if set(version) != {"version", "channel", "packaged", "platform", "arch"}:
            raise OpenDesignDaemonError("daemon version fields mismatch")
        if version.get("version") != expected_version or version.get("channel") != expected_channel:
            raise OpenDesignDaemonError("daemon version/channel mismatch")
        if (
            type(version.get("packaged")) is not bool
            or not isinstance(version.get("platform"), str)
            or not isinstance(version.get("arch"), str)
        ):
            raise OpenDesignDaemonError("daemon version provenance is invalid")

        status = self._request_json("GET", "/api/daemon/status")
        parsed = urlsplit(str(self.settings.base_url))
        if (
            status.get("ok") is not True
            or status.get("version") != expected_version
            or status.get("bindHost") != parsed.hostname
            or status.get("port") != parsed.port
            or status.get("shuttingDown") is not False
            or status.get("sandboxMode") is not True
            or not isinstance(status.get("sandbox"), dict)
            or status["sandbox"].get("enabled") is not True
        ):
            raise OpenDesignDaemonError("daemon status/bind/sandbox preflight failed")

        agents_payload = self._request_json("GET", "/api/agents")
        if set(agents_payload) != {"agents"} or not isinstance(agents_payload.get("agents"), list):
            raise OpenDesignDaemonError("agent catalog envelope mismatch")
        matching_agents = [
            item
            for item in agents_payload["agents"]
            if isinstance(item, dict) and item.get("id") == agent_id
        ]
        if len(matching_agents) != 1:
            raise OpenDesignDaemonError("exact configured agent was not found uniquely")
        agent = matching_agents[0]
        models = agent.get("models")
        if (
            agent.get("available") is not True
            or agent.get("authStatus") != "ok"
            or agent.get("modelsSource") != "live"
            or not isinstance(models, list)
            or [_model_id(item) for item in models].count(model_id) != 1
        ):
            raise OpenDesignDaemonError("configured agent/model is not live and authenticated")

        systems_payload = self._request_json("GET", "/api/design-systems")
        if set(systems_payload) != {"designSystems"} or not isinstance(
            systems_payload.get("designSystems"), list
        ):
            raise OpenDesignDaemonError("design-system catalog envelope mismatch")
        matching_systems = [
            item
            for item in systems_payload["designSystems"]
            if isinstance(item, dict) and item.get("id") == design_system_id
        ]
        if len(matching_systems) != 1 or matching_systems[0].get("status") != "published":
            raise OpenDesignDaemonError("configured design system is not uniquely published")
        encoded_design_system_id = quote(design_system_id, safe="")
        detail_payload = self._request_json(
            "GET", f"/api/design-systems/{encoded_design_system_id}"
        )
        if not isinstance(detail_payload.get("designSystem"), dict):
            raise OpenDesignDaemonError("design-system detail envelope mismatch")
        design_system = detail_payload["designSystem"]
        if {key: value for key, value in detail_payload.items() if key != "designSystem"} != design_system:
            raise OpenDesignDaemonError("design-system expanded detail binding mismatch")
        digest = _sha256(canonical_json_bytes(design_system))
        if (
            design_system.get("id") != design_system_id
            or design_system.get("status") != "published"
            or digest != expected_design_digest
        ):
            raise OpenDesignDaemonError("published design-system digest mismatch")
        return {
            "version": expected_version,
            "channel": expected_channel,
            "packaged": version["packaged"],
            "platform": version["platform"],
            "arch": version["arch"],
            "agent_id": agent_id,
            "requested_model_id": model_id,
            "design_system_id": design_system_id,
            "design_system_sha256": digest,
            "sandbox_reported": True,
        }

    def create_project(self, project_id: str, name: str) -> dict[str, Any]:
        payload = self._request_json(
            "POST",
            "/api/projects",
            body={
                "id": project_id,
                "name": name,
                "skipDiscoveryBrief": True,
                "designSystemId": self.settings.design_system_id,
                "metadata": {
                    "kind": "prototype",
                    "flaiCandidateOnly": True,
                    "flaiReleaseEffect": "none",
                },
            },
        )
        if set(payload) != {"project", "conversationId"}:
            raise OpenDesignDaemonError("create-project response fields mismatch")
        project = payload.get("project")
        if (
            not isinstance(project, dict)
            or project.get("id") != project_id
            or project.get("name") != name
            or project.get("designSystemId") != self.settings.design_system_id
            or not isinstance(payload.get("conversationId"), str)
            or not payload["conversationId"]
        ):
            raise OpenDesignDaemonError("create-project result binding mismatch")
        return payload

    def start_run(
        self,
        project_id: str,
        conversation_id: str,
        prompt: str,
    ) -> dict[str, Any]:
        payload = self._request_json(
            "POST",
            "/api/runs",
            expected_status=202,
            body={
                "projectId": project_id,
                "conversationId": conversation_id,
                "message": prompt,
                "agentId": self.settings.agent_id,
                "model": self.settings.model_id,
                "designSystemId": self.settings.design_system_id,
            },
        )
        if set(payload) != {"runId", "conversationId", "assistantMessageId"}:
            raise OpenDesignDaemonError("start-run response fields mismatch")
        if (
            not isinstance(payload.get("runId"), str)
            or not payload["runId"]
            or payload.get("conversationId") != conversation_id
            or not isinstance(payload.get("assistantMessageId"), str)
            or not payload["assistantMessageId"]
        ):
            raise OpenDesignDaemonError("start-run result binding mismatch")
        return payload

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._request_json("GET", f"/api/runs/{quote(run_id, safe='')}")

    def get_result_package(self, run_id: str) -> dict[str, Any]:
        return self._request_json(
            "GET", f"/api/runs/{quote(run_id, safe='')}/result-package"
        )

    def list_files(self, project_id: str) -> dict[str, Any]:
        return self._request_json(
            "GET", f"/api/projects/{quote(project_id, safe='')}/files"
        )

    def get_file(self, project_id: str, path: str) -> tuple[str, bytes]:
        try:
            validate_safe_path(path)
        except CandidatePolicyError as exc:
            raise OpenDesignDaemonError("unsafe project file path rejected before transport") from exc
        encoded_path = "/".join(quote(segment, safe="") for segment in path.split("/"))
        route = f"/api/projects/{quote(project_id, safe='')}/files/{encoded_path}"
        if "/raw/" in route:
            raise OpenDesignDaemonError("raw project-file routes are forbidden")
        try:
            with self._http.stream("GET", route, headers={"accept": "*/*"}) as response:
                if response.status_code != 200:
                    raise OpenDesignDaemonError(
                        f"GET {route} returned unexpected HTTP {response.status_code}"
                    )
                media_type = (
                    response.headers.get("content-type", "")
                    .split(";", 1)[0]
                    .strip()
                    .casefold()
                )
                if not media_type:
                    raise OpenDesignDaemonError("project file is missing content-type")
                content = _read_bounded_response(
                    response,
                    limit=_MAX_FILE_BYTES,
                    path=route,
                )
        except httpx.HTTPError as exc:
            raise OpenDesignDaemonError(f"GET {route} failed at the loopback boundary") from exc
        return media_type, content
