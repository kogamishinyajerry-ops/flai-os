"""Deterministic, read-only Agent Shell catalog projection.

The registries remain the only source of truth.  This module pins one immutable
Agent Registry generation and turns its manifests and package snapshots into a
UI-oriented semantic catalog.  It does not authorize, launch, sign, or mutate
anything.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import PurePosixPath
from threading import RLock
from typing import Any

SCHEMA_VERSION = "agent_shell.v1"

_WORK_TYPE_ORDER = (
    "tool_automation",
    "knowledge_qa",
    "structured_gen",
    "reasoning_assist",
)
_DOMAIN_ORDER = (
    "policy_qa",
    "standards_qa",
    "fault_history",
    "sys_calc",
    "cfd_sim",
    "test_data",
    "design_opt",
    "generic",
)
_LAUNCH_ORDER = ("task", "conversation", "unknown")
_STATUS_VALUES = frozenset({"draft", "trial", "released", "disabled"})
_MATURITY_VALUES = frozenset({"L0", "L1", "L2", "L3"})
_USEFULNESS_VALUES = frozenset({"L1", "L2", "L3"})
_INPUT_TYPES = frozenset({"file_upload", "params", "none"})
_VISIBILITY_VALUES = frozenset({"admin_only", "department_trial", "all"})
_ROLE_VALUES = frozenset({"admin", "agent_developer", "business_user"})
_CLEARANCE_VALUES = frozenset({"public", "internal", "sensitive"})
_EVIDENCE_KINDS = frozenset(
    {
        "regulation_clause",
        "standard_clause",
        "type_case",
        "fault_case",
        "knowledge_doc",
        "calculation",
    }
)
_TOOL_CLASSIFICATIONS = frozenset({"internal", "sensitive"})
_SCOPE_KINDS = frozenset({"document", "engineering_experience", "run_memory"})
_SCOPE_CONFIDENTIALITY = frozenset({"public_internal", "department", "restricted"})
_SCHEMA_MAX_BYTES = 512 * 1024
_SCHEMA_CACHE_MAX_ENTRIES = 512


class AgentShellProjectionError(RuntimeError):
    """The source registries cannot produce an honest catalog snapshot."""


class AgentShellCatalog:
    """Build one semantic snapshot from the three existing registries.

    ``snapshot()`` deliberately has no write/action surface.  Launch capability
    and authorization continue to be decided by the existing task,
    conversation, and auth contracts.
    """

    def __init__(self, agent_registry: Any, tool_registry: Any, scope_registry: Any) -> None:
        self._agent_registry = agent_registry
        self._tool_registry = tool_registry
        self._scope_registry = scope_registry
        self._schema_cache: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()
        self._schema_cache_lock = RLock()

    def snapshot(self) -> dict[str, Any]:
        tools = _index_registry(self._tool_registry, "id")
        scopes = _index_registry(self._scope_registry, "scope_id")
        diagnostics: list[dict[str, str]] = []
        agents: list[dict[str, Any]] = []

        # One call, one generation: manifests and sibling schema bytes are read
        # only through this pinned view, never through the mutable authoring tree.
        try:
            with self._agent_registry.snapshot_view() as registry_view:
                raw_agents = registry_view.list()
                if not isinstance(raw_agents, list):
                    raise AgentShellProjectionError("Agent Registry snapshot is not a list")
                for index, raw_agent in enumerate(raw_agents):
                    if not isinstance(raw_agent, dict):
                        raise AgentShellProjectionError(
                            f"Agent Registry snapshot item {index} is not an object"
                        )
                    agent = raw_agent
                    agent_id = _agent_id(agent.get("id"), index, diagnostics)
                    package_snapshot = registry_view.package_snapshot(agent_id)
                    agents.append(
                        _project_agent(
                            agent,
                            agent_id=agent_id,
                            package_snapshot=package_snapshot,
                            tools=tools,
                            scopes=scopes,
                            diagnostics=diagnostics,
                            schema_cache=self._schema_cache,
                            schema_cache_lock=self._schema_cache_lock,
                        )
                    )
        except AgentShellProjectionError:
            raise
        except Exception as exc:
            raise AgentShellProjectionError("Agent Registry snapshot is unavailable") from exc

        agents.sort(key=lambda item: item["identity"]["agent_id"])
        facets = {
            "work_types": _facet_items(
                agents,
                values=_ordered_observed(
                    (agent["classification"]["category"] for agent in agents),
                    _WORK_TYPE_ORDER,
                ),
                value_of=lambda agent: agent["classification"]["category"] or "unknown",
            ),
            "domains": _facet_items(
                agents,
                values=_ordered_observed(
                    (agent["classification"]["domain"] for agent in agents),
                    _DOMAIN_ORDER,
                ),
                value_of=lambda agent: agent["classification"]["domain"] or "unknown",
            ),
            "launch_kinds": _facet_items(
                agents,
                values=list(_LAUNCH_ORDER),
                value_of=lambda agent: agent["launch"]["kind"],
            ),
        }
        diagnostics.sort(key=lambda item: (item["agent_id"], item["field"], item["state"]))

        unresolved_count = sum(
            1
            for agent in agents
            for ref in (
                list(agent["capability"]["tools"])
                + list(agent["capability"]["knowledge_scopes"])
            )
            if ref["state"] == "unresolved"
        )
        defaulted_clearance_count = sum(
            1
            for agent in agents
            if agent["trust"]["clearance"]["source"] in {"defaulted", "invalid_defaulted"}
        )
        mock_tool_reference_count = sum(
            1
            for agent in agents
            for ref in agent["capability"]["tools"]
            if ref["mock"] is True
        )

        return {
            "schema_version": SCHEMA_VERSION,
            "source": {"kind": "registry_snapshot", "read_only": True},
            "summary": {
                "agent_count": len(agents),
                "work_type_count": sum(
                    1 for item in facets["work_types"] if item["id"] != "unknown"
                ),
                "domain_count": sum(
                    1 for item in facets["domains"] if item["id"] != "unknown"
                ),
                "unresolved_reference_count": unresolved_count,
                "defaulted_clearance_count": defaulted_clearance_count,
                "mock_tool_reference_count": mock_tool_reference_count,
            },
            "facets": facets,
            "agents": agents,
            "diagnostics": diagnostics,
        }


def _index_registry(registry: Any, key: str) -> dict[str, dict[str, Any]]:
    try:
        values = registry.list()
    except Exception as exc:
        raise AgentShellProjectionError(f"Registry {key!r} is unavailable") from exc
    if not isinstance(values, list):
        raise AgentShellProjectionError(f"Registry {key!r} snapshot is not a list")
    indexed: dict[str, dict[str, Any]] = {}
    for value in values:
        if not isinstance(value, dict):
            continue
        identifier = value.get(key)
        if isinstance(identifier, str) and identifier and identifier not in indexed:
            # Only scalar/list data is projected below.  Taking a shallow copy
            # prevents a concurrent registry dict replacement from changing the
            # object currently being projected.
            indexed[identifier] = dict(value)
    return indexed


def _agent_id(
    value: Any,
    index: int,
    diagnostics: list[dict[str, str]],
) -> str:
    if _valid_utf8_text(value):
        return value
    fallback = f"unknown_agent_{index + 1:04d}"
    _diagnose(diagnostics, fallback, "identity.agent_id", "invalid")
    return fallback


def _project_agent(
    agent: dict[str, Any],
    *,
    agent_id: str,
    package_snapshot: Any,
    tools: dict[str, dict[str, Any]],
    scopes: dict[str, dict[str, Any]],
    diagnostics: list[dict[str, str]],
    schema_cache: OrderedDict[tuple[str, str], dict[str, Any]],
    schema_cache_lock: RLock,
) -> dict[str, Any]:
    expertise = _mapping(agent.get("expertise"))
    input_decl = _mapping(agent.get("input"))
    output_decl = _mapping(agent.get("output"))
    workflow = _mapping(agent.get("workflow"))
    knowledge = _mapping(agent.get("knowledge"))
    permissions = _mapping(agent.get("permissions"))
    evidence = _mapping(agent.get("evidence_policy"))

    category = _enum_or_none(
        agent.get("category"),
        frozenset(_WORK_TYPE_ORDER),
        diagnostics,
        agent_id,
        "classification.category",
    )
    domain = _enum_or_none(
        expertise.get("domain"),
        frozenset(_DOMAIN_ORDER),
        diagnostics,
        agent_id,
        "classification.domain",
        missing_state="undeclared",
    )
    input_type = _enum_or_none(
        input_decl.get("type"),
        _INPUT_TYPES,
        diagnostics,
        agent_id,
        "capability.input.type",
    )
    launch = _launch_kind(workflow.get("mode"), diagnostics, agent_id)
    clearance = _clearance(agent.get("clearance"), diagnostics, agent_id)
    review = _literal_bool(
        workflow.get("requires_human_review"),
        diagnostics,
        agent_id,
        "trust.requires_human_review",
    )
    evidence_required = _literal_bool(
        evidence.get("required"),
        diagnostics,
        agent_id,
        "trust.evidence.required",
        missing_state="undeclared",
    )

    projected_tools = _project_tools(
        agent.get("tools"), tools, diagnostics=diagnostics, agent_id=agent_id
    )
    if knowledge.get("enabled") is True:
        projected_scopes = _project_scopes(
            knowledge.get("scopes"),
            scopes,
            diagnostics=diagnostics,
            agent_id=agent_id,
        )
    else:
        projected_scopes = []
        if isinstance(knowledge.get("scopes"), list) and knowledge.get("scopes"):
            _diagnose(
                diagnostics,
                agent_id,
                "capability.knowledge_scopes",
                "disabled_not_projected",
            )

    return {
        "identity": {
            "agent_id": agent_id,
            "name": _text_or_none(
                agent.get("name"), diagnostics, agent_id, "identity.name"
            ),
            "version": _text_or_none(
                agent.get("version"), diagnostics, agent_id, "identity.version"
            ),
            "summary": _text_or_none(
                agent.get("summary"), diagnostics, agent_id, "identity.summary"
            ),
        },
        "classification": {
            "category": category,
            "domain": domain,
            "specialty": _text_or_none(
                expertise.get("specialty"),
                diagnostics,
                agent_id,
                "classification.specialty",
                missing_state="undeclared",
            ),
            "usefulness_level": _enum_or_none(
                expertise.get("usefulness_level"),
                _USEFULNESS_VALUES,
                diagnostics,
                agent_id,
                "classification.usefulness_level",
                missing_state="undeclared",
            ),
        },
        "capability": {
            "input": {
                "type": input_type,
                "schema": _schema_metadata(
                    package_snapshot,
                    input_decl,
                    default_filename="input_schema.json",
                    diagnostics=diagnostics,
                    agent_id=agent_id,
                    field="capability.input.schema",
                    cache=schema_cache,
                    cache_lock=schema_cache_lock,
                ),
            },
            "output": {
                "formats": _string_list(
                    output_decl.get("formats"),
                    diagnostics,
                    agent_id,
                    "capability.output.formats",
                    missing_is_empty=True,
                ),
                "schema": _schema_metadata(
                    package_snapshot,
                    output_decl,
                    default_filename="output_schema.json",
                    diagnostics=diagnostics,
                    agent_id=agent_id,
                    field="capability.output.schema",
                    cache=schema_cache,
                    cache_lock=schema_cache_lock,
                ),
            },
            "tools": projected_tools,
            "knowledge_scopes": projected_scopes,
        },
        "trust": {
            "status": _enum_or_none(
                agent.get("status"),
                _STATUS_VALUES,
                diagnostics,
                agent_id,
                "trust.status",
            ),
            "maturity": _enum_or_none(
                agent.get("maturity"),
                _MATURITY_VALUES,
                diagnostics,
                agent_id,
                "trust.maturity",
            ),
            "limitations": _string_list(
                agent.get("limitations"),
                diagnostics,
                agent_id,
                "trust.limitations",
            ),
            "visibility": _enum_or_none(
                permissions.get("visibility"),
                _VISIBILITY_VALUES,
                diagnostics,
                agent_id,
                "trust.visibility",
            ),
            "allowed_roles": _enum_list(
                permissions.get("allowed_roles"),
                _ROLE_VALUES,
                diagnostics,
                agent_id,
                "trust.allowed_roles",
            ),
            "clearance": clearance,
            "requires_human_review": review,
            "evidence": {
                "required": evidence_required,
                "kinds": _enum_list(
                    evidence.get("kinds"),
                    _EVIDENCE_KINDS,
                    diagnostics,
                    agent_id,
                    "trust.evidence.kinds",
                    missing_is_empty=True,
                ),
            },
        },
        "launch": {"kind": launch},
    }


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text_or_none(
    value: Any,
    diagnostics: list[dict[str, str]],
    agent_id: str,
    field: str,
    *,
    missing_state: str = "missing",
) -> str | None:
    if _valid_utf8_text(value):
        return value
    state = _invalid_text_state(value, missing_state=missing_state)
    _diagnose(diagnostics, agent_id, field, state)
    return None


def _enum_or_none(
    value: Any,
    allowed: frozenset[str],
    diagnostics: list[dict[str, str]],
    agent_id: str,
    field: str,
    *,
    missing_state: str = "missing",
) -> str | None:
    if isinstance(value, str) and value in allowed:
        return value
    _diagnose(diagnostics, agent_id, field, missing_state if value is None else "invalid")
    return None


def _literal_bool(
    value: Any,
    diagnostics: list[dict[str, str]],
    agent_id: str,
    field: str,
    *,
    missing_state: str = "missing",
) -> bool | None:
    if type(value) is bool:
        return value
    _diagnose(
        diagnostics,
        agent_id,
        field,
        missing_state if value is None else "invalid_boolean",
    )
    return None


def _launch_kind(
    value: Any,
    diagnostics: list[dict[str, str]],
    agent_id: str,
) -> str:
    if value == "job":
        return "task"
    if value == "interactive":
        return "conversation"
    _diagnose(diagnostics, agent_id, "launch.kind", "missing" if value is None else "invalid")
    return "unknown"


def _clearance(
    value: Any,
    diagnostics: list[dict[str, str]],
    agent_id: str,
) -> dict[str, str]:
    if value is None:
        _diagnose(diagnostics, agent_id, "trust.clearance", "defaulted")
        return {"effective": "internal", "source": "defaulted"}
    if not isinstance(value, dict):
        _diagnose(diagnostics, agent_id, "trust.clearance", "invalid_defaulted")
        return {"effective": "internal", "source": "invalid_defaulted"}
    declared = value.get("max_data_classification")
    if isinstance(declared, str) and declared in _CLEARANCE_VALUES:
        return {"effective": declared, "source": "declared"}
    _diagnose(diagnostics, agent_id, "trust.clearance", "invalid_defaulted")
    return {"effective": "internal", "source": "invalid_defaulted"}


def _string_list(
    value: Any,
    diagnostics: list[dict[str, str]],
    agent_id: str,
    field: str,
    *,
    missing_is_empty: bool = False,
) -> list[str]:
    if value is None and missing_is_empty:
        return []
    if not isinstance(value, list) or any(not _valid_utf8_text(item) for item in value):
        _diagnose(diagnostics, agent_id, field, "missing" if value is None else "invalid")
        return []
    return list(value)


def _enum_list(
    value: Any,
    allowed: frozenset[str],
    diagnostics: list[dict[str, str]],
    agent_id: str,
    field: str,
    *,
    missing_is_empty: bool = False,
) -> list[str]:
    if value is None and missing_is_empty:
        return []
    if not isinstance(value, list) or any(
        not isinstance(item, str) or item not in allowed for item in value
    ):
        _diagnose(diagnostics, agent_id, field, "missing" if value is None else "invalid")
        return []
    return list(value)


def _project_tools(
    raw_refs: Any,
    tools: dict[str, dict[str, Any]],
    *,
    diagnostics: list[dict[str, str]],
    agent_id: str,
) -> list[dict[str, Any]]:
    refs = _reference_ids(raw_refs, diagnostics, agent_id, "capability.tools")
    result: list[dict[str, Any]] = []
    for tool_id in refs:
        tool = tools.get(tool_id)
        if tool is None:
            _diagnose(diagnostics, agent_id, f"capability.tools.{tool_id}", "unresolved")
            result.append(
                {
                    "id": tool_id,
                    "name": None,
                    "version": None,
                    "state": "unresolved",
                    "mock": None,
                    "output_classification": None,
                }
            )
            continue
        mock_declared = "mock" in tool
        mock_value = tool.get("mock")
        if type(mock_value) is bool:
            mock = mock_value
        else:
            mock = None
            _diagnose(
                diagnostics,
                agent_id,
                f"capability.tools.{tool_id}.mock",
                "missing" if mock_declared is not True else "invalid_boolean",
            )
        output_classification = tool.get("output_classification")
        if output_classification not in _TOOL_CLASSIFICATIONS:
            output_classification = None
            _diagnose(
                diagnostics,
                agent_id,
                f"capability.tools.{tool_id}.output_classification",
                "invalid",
            )
        result.append(
            {
                "id": tool_id,
                "name": _ref_text(
                    tool.get("name"),
                    diagnostics,
                    agent_id,
                    f"capability.tools.{tool_id}.name",
                ),
                "version": _ref_text(
                    tool.get("version"),
                    diagnostics,
                    agent_id,
                    f"capability.tools.{tool_id}.version",
                ),
                "state": "resolved",
                "mock": mock,
                "output_classification": output_classification,
            }
        )
    return result


def _project_scopes(
    raw_refs: Any,
    scopes: dict[str, dict[str, Any]],
    *,
    diagnostics: list[dict[str, str]],
    agent_id: str,
) -> list[dict[str, Any]]:
    refs = _reference_ids(
        raw_refs, diagnostics, agent_id, "capability.knowledge_scopes"
    )
    result: list[dict[str, Any]] = []
    for scope_id in refs:
        scope = scopes.get(scope_id)
        if scope is None:
            _diagnose(
                diagnostics,
                agent_id,
                f"capability.knowledge_scopes.{scope_id}",
                "unresolved",
            )
            result.append(
                {
                    "id": scope_id,
                    "name": None,
                    "kind": None,
                    "confidentiality": None,
                    "state": "unresolved",
                }
            )
            continue
        kind = scope.get("kind")
        if kind not in _SCOPE_KINDS:
            kind = None
            _diagnose(
                diagnostics,
                agent_id,
                f"capability.knowledge_scopes.{scope_id}.kind",
                "invalid",
            )
        confidentiality = scope.get("confidentiality")
        if confidentiality not in _SCOPE_CONFIDENTIALITY:
            confidentiality = None
            _diagnose(
                diagnostics,
                agent_id,
                f"capability.knowledge_scopes.{scope_id}.confidentiality",
                "invalid",
            )
        result.append(
            {
                "id": scope_id,
                "name": _ref_text(
                    scope.get("name"),
                    diagnostics,
                    agent_id,
                    f"capability.knowledge_scopes.{scope_id}.name",
                ),
                "kind": kind,
                "confidentiality": confidentiality,
                "state": "resolved",
            }
        )
    return result


def _reference_ids(
    value: Any,
    diagnostics: list[dict[str, str]],
    agent_id: str,
    field: str,
) -> list[str]:
    if not isinstance(value, list) or any(
        not _valid_utf8_text(item) for item in value
    ):
        _diagnose(diagnostics, agent_id, field, "missing" if value is None else "invalid")
        return []
    return list(value)


def _ref_text(
    value: Any,
    diagnostics: list[dict[str, str]],
    agent_id: str,
    field: str,
) -> str | None:
    if _valid_utf8_text(value):
        return value
    state = _invalid_text_state(value, missing_state="missing")
    _diagnose(diagnostics, agent_id, field, state)
    return None


def _valid_utf8_text(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _invalid_text_state(value: Any, *, missing_state: str) -> str:
    if value is None:
        return missing_state
    if not isinstance(value, str) or value == "":
        return "invalid"
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return "invalid_utf8"
    return "invalid"


def _schema_metadata(
    package_snapshot: Any,
    declaration: dict[str, Any],
    *,
    default_filename: str,
    diagnostics: list[dict[str, str]],
    agent_id: str,
    field: str,
    cache: OrderedDict[tuple[str, str], dict[str, Any]],
    cache_lock: RLock,
) -> dict[str, Any]:
    declared = declaration.get("schema", default_filename)
    if not isinstance(declared, str) or not declared:
        _diagnose(diagnostics, agent_id, field, "invalid_filename")
        return _unavailable_schema(None, "invalid_filename")
    if not _valid_utf8_text(declared):
        _diagnose(diagnostics, agent_id, field, "invalid_utf8")
        return _unavailable_schema(None, "invalid_utf8")
    if not _safe_relative_filename(declared):
        _diagnose(diagnostics, agent_id, field, "unsafe_filename")
        return _unavailable_schema(declared, "unsafe_filename")

    digest = getattr(package_snapshot, "digest", None)
    cache_key = (digest, declared) if _valid_utf8_text(digest) else None
    if cache_key is not None:
        with cache_lock:
            cached = cache.get(cache_key)
            if cached is not None:
                cache.move_to_end(cache_key)
                result = dict(cached)
                reason = result.get("reason")
                if result.get("state") == "unavailable" and isinstance(reason, str):
                    _diagnose(diagnostics, agent_id, field, reason)
                return result
            result = _load_schema_metadata(
                package_snapshot,
                declared,
                diagnostics=diagnostics,
                agent_id=agent_id,
                field=field,
            )
            if len(cache) >= _SCHEMA_CACHE_MAX_ENTRIES:
                cache.popitem(last=False)
            cache[cache_key] = dict(result)
            return result

    return _load_schema_metadata(
        package_snapshot,
        declared,
        diagnostics=diagnostics,
        agent_id=agent_id,
        field=field,
    )


def _load_schema_metadata(
    package_snapshot: Any,
    declared: str,
    *,
    diagnostics: list[dict[str, str]],
    agent_id: str,
    field: str,
) -> dict[str, Any]:

    files_value = getattr(package_snapshot, "files", ()) if package_snapshot is not None else ()
    try:
        files = dict(files_value)
    except (TypeError, ValueError):
        files = {}
    payload = files.get(declared)
    if not isinstance(payload, bytes):
        _diagnose(diagnostics, agent_id, field, "file_missing")
        return _unavailable_schema(declared, "file_missing")
    if len(payload) > _SCHEMA_MAX_BYTES:
        _diagnose(diagnostics, agent_id, field, "file_too_large")
        return _unavailable_schema(declared, "file_too_large")
    try:
        document = json.loads(payload.decode("utf-8"))
    except UnicodeError:
        _diagnose(diagnostics, agent_id, field, "invalid_utf8")
        return _unavailable_schema(declared, "invalid_utf8")
    except (ValueError, RecursionError):
        _diagnose(diagnostics, agent_id, field, "invalid_json")
        return _unavailable_schema(declared, "invalid_json")
    if not isinstance(document, dict):
        _diagnose(diagnostics, agent_id, field, "not_object")
        return _unavailable_schema(declared, "not_object")
    properties = document.get("properties", {})
    required = document.get("required", [])
    if not isinstance(properties, dict) or not isinstance(required, list):
        _diagnose(diagnostics, agent_id, field, "invalid_schema_shape")
        return _unavailable_schema(declared, "invalid_schema_shape")
    return {
        "state": "available",
        "reason": None,
        "filename": declared,
        "property_count": len(properties),
        "required_count": len(required),
    }


def _safe_relative_filename(filename: str) -> bool:
    if "\\" in filename:
        return False
    path = PurePosixPath(filename)
    return (
        not path.is_absolute()
        and filename == path.as_posix()
        and bool(path.parts)
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def _unavailable_schema(filename: str | None, reason: str) -> dict[str, Any]:
    return {
        "state": "unavailable",
        "reason": reason,
        "filename": filename,
        "property_count": 0,
        "required_count": 0,
    }


def _ordered_observed(values: Any, preferred_order: tuple[str, ...]) -> list[str]:
    observed = {value if isinstance(value, str) else "unknown" for value in values}
    ordered = [value for value in preferred_order if value in observed]
    extras = sorted(value for value in observed if value not in {*preferred_order, "unknown"})
    if "unknown" in observed:
        return ordered + extras + ["unknown"]
    return ordered + extras


def _facet_items(
    agents: list[dict[str, Any]],
    *,
    values: list[str],
    value_of: Any,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for value in values:
        members = [agent for agent in agents if value_of(agent) == value]
        result.append(
            {
                "id": value,
                "total_count": len(members),
                "task_count": sum(1 for agent in members if agent["launch"]["kind"] == "task"),
                "conversation_count": sum(
                    1 for agent in members if agent["launch"]["kind"] == "conversation"
                ),
                "unknown_launch_count": sum(
                    1 for agent in members if agent["launch"]["kind"] == "unknown"
                ),
            }
        )
    return result


def _diagnose(
    diagnostics: list[dict[str, str]],
    agent_id: str,
    field: str,
    state: str,
) -> None:
    diagnostics.append({"agent_id": agent_id, "field": field, "state": state})
