"""Owner-scoped, fail-closed read-only functionality and asset projection."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any, Mapping

from jsonschema import validate

from ..storage import asset_candidates as candidate_store
from ..storage import skill_packages as package_store

SCHEMA_VERSION = "feature_asset_map.v1"
_MAX_ASSETS = 100
_MAX_CAPABILITIES = 200
_ASSET_STATE_BY_CANDIDATE_STATE = {
    "awaiting_human_review": "candidate_revision",
    "accepted": "approved_revision",
    "rejected": "rejected_revision",
}


class FeatureAssetMapUnavailableError(RuntimeError):
    """One source cannot produce a complete and ownership-safe projection."""


class FeatureAssetMapCatalog:
    """Join existing ontology and governed assets without adding an authority."""

    def __init__(
        self,
        *,
        agent_shell_catalog: Any,
        asset_candidate_ledger: Any,
        asset_candidate_authorizer: Callable[
            [sqlite3.Connection, str, str], Mapping[str, Any]
        ],
        contracts_dir: Path,
    ) -> None:
        self._agent_shell_catalog = agent_shell_catalog
        self._asset_candidate_ledger = asset_candidate_ledger
        if not callable(asset_candidate_authorizer):
            raise FeatureAssetMapUnavailableError(
                "feature asset map owner authorizer is unavailable"
            )
        self._asset_candidate_authorizer = asset_candidate_authorizer
        try:
            schema = json.loads(
                (contracts_dir / "feature_asset_map.schema.json").read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise FeatureAssetMapUnavailableError(
                "feature asset map contract is unavailable"
            ) from exc
        if not isinstance(schema, dict):
            raise FeatureAssetMapUnavailableError(
                "feature asset map contract is not an object"
            )
        self._response_schema = schema

    def snapshot(
        self,
        conn: sqlite3.Connection,
        *,
        username: str,
    ) -> dict[str, Any]:
        """Return one complete owner projection or fail without partial data."""

        owner = _required_owner(username)
        started_read_snapshot = False
        try:
            if conn.in_transaction:
                raise FeatureAssetMapUnavailableError(
                    "feature asset map requires a fresh read connection"
                )
            shell = self._agent_shell_catalog.snapshot()
            functionality = _project_functionality(shell)
            conn.execute("BEGIN")
            started_read_snapshot = True
            package_ids = package_store.list_ids_for_owner(
                conn,
                owner,
                _MAX_ASSETS + 1,
            )
            if len(package_ids) > _MAX_ASSETS:
                raise FeatureAssetMapUnavailableError(
                    "owner package population exceeds bounded projection"
                )
            for package_id in package_ids:
                package_context = package_store.get_owner_context_by_id(
                    conn,
                    package_id,
                )
                if not isinstance(package_context, Mapping):
                    raise FeatureAssetMapUnavailableError(
                        "owner package context is unavailable"
                    )
                candidate_id = package_context.get("source_candidate_id")
                if not isinstance(candidate_id, str) or not candidate_id:
                    raise FeatureAssetMapUnavailableError(
                        "owner package candidate identity is unavailable"
                    )
                candidate_context = self._asset_candidate_authorizer(
                    conn,
                    candidate_id,
                    owner,
                )
                if (
                    not isinstance(candidate_context, Mapping)
                    or package_context.get("id") != package_id
                    or package_context.get("owner_username") != owner
                    or package_context.get("source_candidate_id") != candidate_id
                    or package_context.get("source_candidate_digest")
                    != candidate_context.get("candidate_digest")
                    or package_context.get("source_task_id")
                    != candidate_context.get("source_task_id")
                ):
                    raise FeatureAssetMapUnavailableError(
                        "owner package lineage is inconsistent"
                    )
            task_ids = candidate_store.list_latest_task_ids_for_owner(
                conn,
                owner,
                _MAX_ASSETS + 1,
            )
            if len(task_ids) > _MAX_ASSETS:
                raise FeatureAssetMapUnavailableError(
                    "owner asset population exceeds bounded projection"
                )
            assets: list[dict[str, Any]] = []
            for task_id in task_ids:
                candidate_id = candidate_store.get_latest_id_for_task(
                    conn, task_id
                )
                if not isinstance(candidate_id, str) or not candidate_id:
                    raise FeatureAssetMapUnavailableError(
                        "owner asset candidate identity is unavailable"
                    )
                owner_context = self._asset_candidate_authorizer(
                    conn,
                    candidate_id,
                    owner,
                )
                if (
                    not isinstance(owner_context, Mapping)
                    or owner_context.get("source_task_id") != task_id
                ):
                    raise FeatureAssetMapUnavailableError(
                        "owner asset candidate lineage is inconsistent"
                    )
                candidate = self._asset_candidate_ledger.get_for_task(
                    conn,
                    task_id=task_id,
                    username=owner,
                )
                if (
                    not isinstance(candidate, Mapping)
                    or candidate.get("id") != candidate_id
                ):
                    raise FeatureAssetMapUnavailableError(
                        "owner asset candidate projection drifted"
                    )
                assets.append(_project_asset(candidate))
            accepted_count = sum(1 for item in assets if item["state"] == "accepted")
            packages = [
                item["skill_package"]
                for item in assets
                if item["skill_package"] is not None
            ]
            document = {
                "schema_version": SCHEMA_VERSION,
                "source": {
                    "kind": "owner_scoped_cold_projection",
                    "owner_username": owner,
                    "owner_scoped": True,
                    "read_only": True,
                },
                "summary": {
                    "capability_count": len(functionality["capabilities"]),
                    "asset_candidate_count": len(assets),
                    "accepted_candidate_count": accepted_count,
                    "skill_package_count": len(packages),
                    "approved_skill_package_count": sum(
                        1 for package in packages if package["state"] == "approved"
                    ),
                    "unresolved_reference_count": functionality[
                        "unresolved_reference_count"
                    ],
                },
                "functionality": {
                    "work_types": functionality["work_types"],
                    "domains": functionality["domains"],
                    "capabilities": functionality["capabilities"],
                },
                "assets": assets,
                "effects": {
                    "writes_database": False,
                    "executes_work": False,
                    "registers_asset": False,
                    "promotes_asset": False,
                },
            }
            validate(document, self._response_schema)
            if not conn.in_transaction:
                raise FeatureAssetMapUnavailableError(
                    "feature asset map read snapshot ended unexpectedly"
                )
            return document
        except FeatureAssetMapUnavailableError:
            raise
        except Exception as exc:
            raise FeatureAssetMapUnavailableError(
                "feature asset map sources cannot be read safely"
            ) from exc
        finally:
            if started_read_snapshot and conn.in_transaction:
                try:
                    conn.rollback()
                except Exception as exc:
                    raise FeatureAssetMapUnavailableError(
                        "feature asset map read snapshot cannot be released safely"
                    ) from exc


def _project_functionality(shell: Any) -> dict[str, Any]:
    if not isinstance(shell, Mapping):
        raise FeatureAssetMapUnavailableError("Agent Shell projection is malformed")
    summary = _mapping(shell.get("summary"), "Agent Shell summary")
    facets = _mapping(shell.get("facets"), "Agent Shell facets")
    agents = shell.get("agents")
    if not isinstance(agents, list) or len(agents) > _MAX_CAPABILITIES:
        raise FeatureAssetMapUnavailableError(
            "Agent Shell capability population is malformed or unbounded"
        )
    capabilities = [_project_capability(agent) for agent in agents]
    unresolved_count = _non_negative_int(
        summary.get("unresolved_reference_count"),
        "Agent Shell unresolved reference count",
    )
    if unresolved_count != sum(
        item["unresolved_reference_count"] for item in capabilities
    ):
        raise FeatureAssetMapUnavailableError(
            "Agent Shell unresolved reference count is inconsistent"
        )
    if _non_negative_int(summary.get("agent_count"), "Agent Shell agent count") != len(
        capabilities
    ):
        raise FeatureAssetMapUnavailableError("Agent Shell agent count is inconsistent")
    return {
        "work_types": _project_facets(facets.get("work_types"), "work types"),
        "domains": _project_facets(facets.get("domains"), "domains"),
        "capabilities": capabilities,
        "unresolved_reference_count": unresolved_count,
    }


def _project_capability(value: Any) -> dict[str, Any]:
    agent = _mapping(value, "Agent Shell capability")
    identity = _mapping(agent.get("identity"), "Agent Shell identity")
    classification = _mapping(
        agent.get("classification"), "Agent Shell classification"
    )
    capability = _mapping(agent.get("capability"), "Agent Shell capability detail")
    trust = _mapping(agent.get("trust"), "Agent Shell trust")
    launch = _mapping(agent.get("launch"), "Agent Shell launch")
    tools = _list(capability.get("tools"), "Agent Shell tools")
    scopes = _list(
        capability.get("knowledge_scopes"), "Agent Shell knowledge scopes"
    )
    refs = tools + scopes
    for ref in refs:
        _mapping(ref, "Agent Shell reference")
    review = trust.get("requires_human_review")
    if review is not None and not isinstance(review, bool):
        raise FeatureAssetMapUnavailableError(
            "Agent Shell human review flag is not literal boolean or null"
        )
    return {
        "agent_id": _required_text(identity.get("agent_id"), "Agent id"),
        "name": _optional_text(identity.get("name"), "Agent name"),
        "summary": _optional_text(identity.get("summary"), "Agent summary"),
        "category": _optional_text(
            classification.get("category"), "Agent category"
        ),
        "domain": _optional_text(classification.get("domain"), "Agent domain"),
        "specialty": _optional_text(
            classification.get("specialty"), "Agent specialty"
        ),
        "launch_kind": _required_text(launch.get("kind"), "Agent launch kind"),
        "status": _optional_text(trust.get("status"), "Agent status"),
        "maturity": _optional_text(trust.get("maturity"), "Agent maturity"),
        "requires_human_review": review,
        "tool_count": len(tools),
        "knowledge_scope_count": len(scopes),
        "unresolved_reference_count": sum(
            1 for ref in refs if ref.get("state") == "unresolved"
        ),
        "mock_tool_count": sum(1 for ref in tools if ref.get("mock") is True),
    }


def _project_facets(value: Any, field: str) -> list[dict[str, Any]]:
    facets = _list(value, f"Agent Shell {field}")
    if len(facets) > _MAX_CAPABILITIES:
        raise FeatureAssetMapUnavailableError(
            f"Agent Shell {field} population is unbounded"
        )
    projected: list[dict[str, Any]] = []
    for raw in facets:
        facet = _mapping(raw, f"Agent Shell {field} facet")
        projected.append(
            {
                "id": _required_text(facet.get("id"), f"Agent Shell {field} id"),
                "total_count": _non_negative_int(
                    facet.get("total_count"), f"Agent Shell {field} count"
                ),
            }
        )
    return projected


def _project_asset(value: Any) -> dict[str, Any]:
    candidate = _mapping(value, "Asset Candidate")
    candidate_state = _required_text(candidate.get("state"), "Candidate state")
    expected_asset_state = _ASSET_STATE_BY_CANDIDATE_STATE.get(candidate_state)
    if expected_asset_state is None:
        raise FeatureAssetMapUnavailableError("Candidate state is malformed")
    source = _mapping(candidate.get("source"), "Asset Candidate source")
    bundle = _mapping(candidate.get("bundle"), "Asset Candidate bundle")
    task_pattern = _mapping(bundle.get("task_pattern"), "Task Pattern")
    skill = _mapping(bundle.get("skill"), "Skill")
    asset_map = _mapping(candidate.get("asset_map"), "Candidate asset map")
    package_value = candidate.get("skill_package")
    package = None
    if package_value is not None:
        raw_package = _mapping(package_value, "Skill Package")
        reuse_eligible = raw_package.get("reuse_eligible")
        if not isinstance(reuse_eligible, bool):
            raise FeatureAssetMapUnavailableError(
                "Skill Package reuse eligibility is not literal boolean"
            )
        package_state = _required_text(
            raw_package.get("state"), "Skill Package state"
        )
        if package_state not in {"pending_review", "approved", "rejected"}:
            raise FeatureAssetMapUnavailableError("Skill Package state is malformed")
        if reuse_eligible is not (package_state == "approved"):
            raise FeatureAssetMapUnavailableError(
                "Skill Package reuse eligibility contradicts review state"
            )
        package = {
            "id": _required_text(raw_package.get("id"), "Skill Package id"),
            "name": _required_text(raw_package.get("name"), "Skill Package name"),
            "version": _required_text(
                raw_package.get("version"), "Skill Package version"
            ),
            "package_digest": _required_text(
                raw_package.get("package_digest"), "Skill Package digest"
            ),
            "state": package_state,
            "reuse_eligible": reuse_eligible,
        }
    if (candidate_state == "accepted") is not (package is not None):
        raise FeatureAssetMapUnavailableError(
            "Candidate state contradicts Skill Package presence"
        )
    revision = candidate.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise FeatureAssetMapUnavailableError("Candidate revision is malformed")
    return {
        "candidate_id": _required_text(candidate.get("id"), "Candidate id"),
        "candidate_digest": _required_text(
            candidate.get("candidate_digest"), "Candidate digest"
        ),
        "revision": revision,
        "state": candidate_state,
        "source": {
            "task_id": _required_text(source.get("task_id"), "Candidate task id"),
            "conversation_id": _required_text(
                source.get("conversation_id"), "Candidate conversation id"
            ),
            "agent_id": _required_text(
                source.get("agent_id"), "Candidate Agent id"
            ),
            "finished_at": _required_text(
                source.get("finished_at"), "Candidate finished time"
            ),
        },
        "task_pattern": {
            "title": _required_text(
                task_pattern.get("title"), "Task Pattern title", max_length=160
            ),
            **_project_formed_asset_level(
                asset_map.get("task_pattern"),
                "Task Pattern",
                expected_state=expected_asset_state,
            ),
        },
        "skill": {
            "name": _required_text(
                skill.get("name"), "Skill name", max_length=160
            ),
            "description": _required_text(
                skill.get("description"), "Skill description", max_length=4200
            ),
            **_project_formed_asset_level(
                asset_map.get("skill"),
                "Skill",
                expected_state=expected_asset_state,
            ),
        },
        "skill_package": package,
        "workflow": _project_unformed_asset_level(
            asset_map.get("workflow"), "Workflow"
        ),
        "agent": _project_unformed_asset_level(
            asset_map.get("agent"), "Agent asset"
        ),
        "updated_at": _required_text(candidate.get("updated_at"), "Candidate updated time"),
    }


def _project_formed_asset_level(
    value: Any,
    field: str,
    *,
    expected_state: str,
) -> dict[str, Any]:
    level = _mapping(value, field)
    state = _required_text(level.get("state"), f"{field} state")
    if state != expected_state:
        raise FeatureAssetMapUnavailableError(
            f"{field} state contradicts Candidate state"
        )
    return {
        "state": state,
        "digest": _required_text(level.get("digest"), f"{field} digest"),
    }


def _project_unformed_asset_level(value: Any, field: str) -> dict[str, Any]:
    level = _mapping(value, field)
    if level.get("state") != "not_formed" or level.get("digest") is not None:
        raise FeatureAssetMapUnavailableError(f"{field} formation state is malformed")
    return {
        "state": "not_formed",
        "digest": None,
        "gate": _required_text(level.get("gate"), f"{field} gate"),
    }


def _required_owner(value: Any) -> str:
    owner = _required_text(value, "owner username", max_length=128)
    if owner != owner.strip() or any(ord(char) < 32 for char in owner):
        raise FeatureAssetMapUnavailableError("owner username is not canonical")
    return owner


def _required_text(value: Any, field: str, *, max_length: int = 2000) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > max_length
    ):
        raise FeatureAssetMapUnavailableError(f"{field} is malformed")
    return value


def _optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field)


def _non_negative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FeatureAssetMapUnavailableError(f"{field} is malformed")
    return value


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FeatureAssetMapUnavailableError(f"{field} is malformed")
    return value


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise FeatureAssetMapUnavailableError(f"{field} is malformed")
    return value
