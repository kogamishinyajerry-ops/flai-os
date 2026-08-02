"""Accepted Asset Candidate -> isolated, review-gated Skill Package.

The materializer deliberately stops at a quarantined, content-addressed file
tree.  It never registers a Skill, imports Python, executes package content, or
writes into an Agent package directory.  Callers own the surrounding database
transaction; ``materialize_accepted`` and ``decide`` are intended to run under
``BEGIN IMMEDIATE`` so their append-only events and CAS pointers commit as one
unit.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import unicodedata
import uuid
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import ValidationError, validate

from ..config import CONTRACTS_DIR
from ..core.canonical_digest import canonical_digest as candidate_canonical_digest
from ..core.errors import FileIntegrityError
from ..governance.signer_provenance import (
    AUTHENTICATED_SESSION,
    SignerContext,
    resolve_signer,
    stored_signer_attests,
)
from ..storage import asset_candidates as candidate_store
from ..storage import skill_packages as package_store
from ..storage.file_integrity import open_verified_file


SCHEMA_VERSION = "skill_package_revision.v1"
MATERIALIZER_POLICY_VERSION = "candidate_materializer_policy.v1"
PACKAGE_DIGEST_SCHEMA_VERSION = "candidate_skill_package_digest.v1"
PROVENANCE_SCHEMA_VERSION = "candidate_skill_package_provenance.v1"
ACCEPTANCE_ATTESTATION_SCHEMA_VERSION = "asset_candidate_acceptance_attestation.v1"
REVIEW_CONTENT_SCHEMA_VERSION = "skill_package_review_content.v1"

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_PACKAGE_ID_RE = re.compile(r"^skill_package_[0-9a-f]{24}$")
_PACKAGE_DIR_RE = re.compile(r"^skill_package_[0-9a-f]{24}$")
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_SESSION_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_EXPECTED_FILE_PATHS = (
    "SKILL.md",
    "references/provenance.json",
    "references/skill-revision.json",
    "references/task-pattern-revision.json",
)
_FORBIDDEN_ROOT_PARTS = {"agents", ".agents", ".codex"}


class SkillPackageNotFoundError(LookupError):
    """The requested package does not exist in the caller's ownership scope."""


class SkillPackageConflictError(RuntimeError):
    """A state, digest, ownership, or live-session gate rejected the action."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class SkillPackageUnavailableError(RuntimeError):
    """Stored package bytes or provenance cannot be trusted."""


class CandidateMaterializer:
    """Materialize and review immutable Skill Package revisions."""

    def __init__(
        self,
        root: Path,
        ledger: Any,
        *,
        forbidden_roots: Iterable[Path],
        contracts_dir: Path = CONTRACTS_DIR,
    ) -> None:
        self._root = Path(root)
        self._ledger = ledger
        self._formation_evidence_provider: Any | None = None
        _assert_isolated_root(self._root)
        normalized_forbidden: list[Path] = []
        for forbidden in forbidden_roots:
            path = Path(forbidden)
            if not path.is_absolute():
                raise ValueError("forbidden Skill Package roots must be absolute")
            normalized_forbidden.append(path)
        if not normalized_forbidden:
            raise ValueError("at least one forbidden Skill Package root is required")
        self._forbidden_roots = tuple(normalized_forbidden)
        _assert_root_realpath_outside_forbidden(
            self._root,
            self._forbidden_roots,
            constructor=True,
        )
        self._package_schema = _load_contract_schema(
            Path(contracts_dir),
            "candidate_skill_package.schema.json",
        )
        self._event_schema = _load_contract_schema(
            Path(contracts_dir),
            "skill_package_event.schema.json",
        )
        self._review_content_schema = _load_contract_schema(
            Path(contracts_dir),
            "skill_package_review_content.schema.json",
        )

    @property
    def root(self) -> Path:
        return self._root

    def attach_formation_evidence_provider(self, provider: Any) -> None:
        """Attach the runtime-backed independent-work evidence reader."""

        if provider is None or not callable(
            getattr(provider, "formation_evidence", None)
        ):
            raise ValueError("formation evidence provider is unavailable")
        self._formation_evidence_provider = provider

    def materialize_accepted(
        self,
        conn: sqlite3.Connection,
        candidate_public: Mapping[str, Any],
        accepted_event: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Create one deterministic pending-review package inside quarantine.

        The caller must already hold ``BEGIN IMMEDIATE``.  Files are completed
        before the database row becomes visible.  A crash after the atomic
        rename can leave only an unreferenced quarantine directory; a retry may
        adopt it only if every expected byte is identical.
        """

        _require_active_transaction(conn)
        self._assert_runtime_isolation()
        candidate, source_event = self._fresh_accepted_candidate(
            conn,
            candidate_public=candidate_public,
            accepted_event=accepted_event,
        )
        candidate_digest = _required_digest(
            candidate.get("candidate_digest"), "candidate digest"
        )
        owner = _candidate_owner(candidate)

        existing = _package_by_candidate_digest(conn, candidate_digest)
        if existing is not None:
            if existing.get("owner_username") != owner:
                raise SkillPackageUnavailableError(
                    "materialized package owner does not match its accepted candidate"
                )
            return self._public_projection(conn, existing)

        source = _package_source(candidate, source_event)
        name = _package_name(candidate)
        version = _package_version(candidate)
        file_bytes = _render_package_files(
            candidate=candidate,
            source=source,
            name=name,
            version=version,
        )
        manifest = _file_manifest(file_bytes)
        package_digest = _package_digest(
            name=name,
            version=version,
            source=source,
            files=manifest,
        )
        digest_hex = package_digest.removeprefix("sha256:")
        package_id = f"skill_package_{digest_hex[:24]}"
        storage_relpath = f"quarantine/{package_id}"
        final_dir = self._root / "quarantine" / package_id

        self._install_or_adopt_tree(
            final_dir=final_dir,
            storage_relpath=storage_relpath,
            file_bytes=file_bytes,
        )

        now = _now_iso()
        record = {
            "id": package_id,
            "schema_version": SCHEMA_VERSION,
            "name": name,
            "version": version,
            "package_digest": package_digest,
            "state": "pending_review",
            "source_candidate_id": source["candidate_id"],
            "source_candidate_digest": source["candidate_digest"],
            "source_bundle_digest": source["bundle_digest"],
            "source_skill_digest": source["skill_digest"],
            "source_acceptance_event_digest": source["acceptance_event_digest"],
            "source_task_id": source["task_id"],
            "source_agent_id": source["agent_id"],
            "owner_username": source["initiated_by_username"],
            "storage_relpath": storage_relpath,
            "file_manifest_json": _canonical_json(manifest),
            "files": manifest,
            "review_event_id": None,
            "created_at": now,
            "updated_at": now,
        }
        try:
            package_store.insert_package(conn, record)
        except sqlite3.IntegrityError as exc:
            raced = _package_by_candidate_digest(conn, candidate_digest)
            if raced is not None:
                return self._public_projection(conn, raced)
            raise SkillPackageUnavailableError(
                "skill package address collided with another stored revision"
            ) from exc

        event = {
            "event_id": f"skill_package_event_{uuid.uuid4().hex}",
            "package_id": package_id,
            "package_digest": package_digest,
            "event_type": "materialized",
            "from_state": None,
            "to_state": "pending_review",
            "actor_source": "candidate_materializer",
            "signer_display_name": None,
            "signer_user_id": None,
            "signer_username": None,
            "signer_session_hash": None,
            "message": "已接受候选被确定性材化为隔离、待审的 Skill Package",
            "payload": {
                "source_candidate_digest": source["candidate_digest"],
                "source_acceptance_event_digest": source["acceptance_event_digest"],
            },
            "created_at": now,
        }
        package_store.append_event(conn, event, schema=self._event_schema)
        stored = _package_by_id(conn, package_id)
        if stored is None:
            raise SkillPackageUnavailableError(
                "materialized package could not be read back"
            )
        return self._public_projection(conn, stored)

    def backfill_legacy_accepted(
        self,
        conn_factory: Callable[[], sqlite3.Connection],
    ) -> int:
        """Materialize legacy accepted candidates, committing one row at a time.

        The discovery query is read-only and never prepares the quarantine root.
        Therefore a database with no legacy accepted rows creates no package
        directory.  Per-row transactions make startup recovery resumable: an
        invalid later row cannot roll back an already materialized earlier row.
        """

        if not callable(conn_factory):
            raise TypeError("conn_factory must be callable")
        self._assert_runtime_isolation()
        discovery = conn_factory()
        try:
            candidate_ids = candidate_store.list_accepted_without_package_ids(discovery)
        finally:
            discovery.close()

        materialized = 0
        for candidate_id in candidate_ids:
            conn = conn_factory()
            try:
                conn.execute("BEGIN IMMEDIATE")
                candidate = _candidate_by_id(conn, candidate_id)
                if candidate is None or candidate.get("state") != "accepted":
                    conn.execute("COMMIT")
                    continue
                source_task_id = candidate.get("source_task_id")
                if not isinstance(source_task_id, str) or not source_task_id:
                    raise SkillPackageUnavailableError(
                        "legacy candidate source task is malformed"
                    )
                if _latest_candidate_id(conn, source_task_id) != candidate_id:
                    # Discovery is read-only and intentionally precedes each
                    # write transaction.  A newer revision may arrive between
                    # those points; historical revisions must never materialize.
                    conn.execute("COMMIT")
                    continue
                candidate_digest = _required_digest(
                    candidate.get("candidate_digest"), "candidate digest"
                )
                if _package_by_candidate_digest(conn, candidate_digest) is not None:
                    conn.execute("COMMIT")
                    continue
                projector = getattr(self._ledger, "_public_projection", None)
                if not callable(projector):
                    raise SkillPackageUnavailableError(
                        "candidate ledger has no verified projection seam"
                    )
                public = projector(conn, candidate)
                event_id = candidate.get("decision_event_id")
                accepted_event = (
                    _candidate_event(conn, event_id)
                    if isinstance(event_id, str) and event_id
                    else None
                )
                if accepted_event is None:
                    raise SkillPackageUnavailableError(
                        "legacy accepted candidate has no acceptance event"
                    )
                self.materialize_accepted(
                    conn,
                    candidate_public=public,
                    accepted_event=accepted_event,
                )
                conn.execute("COMMIT")
                materialized += 1
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()
        return materialized

    def get(
        self,
        conn: sqlite3.Connection,
        package_id: str,
        username: str,
    ) -> dict[str, Any]:
        self._assert_runtime_isolation()
        owner = _required_owner(username)
        if _package_owner_by_id(conn, package_id) != owner:
            raise SkillPackageNotFoundError(f"Skill Package 不存在：{package_id}")
        stored = _package_by_id(conn, package_id)
        if stored is None:
            raise SkillPackageNotFoundError(f"Skill Package 不存在：{package_id}")
        return self._public_projection(conn, stored)

    def get_for_candidate_digest(
        self,
        conn: sqlite3.Connection,
        candidate_digest: str,
        username: str,
    ) -> dict[str, Any] | None:
        self._assert_runtime_isolation()
        digest = _required_digest(candidate_digest, "candidate digest")
        owner = _required_owner(username)
        if _package_owner_by_candidate_digest(conn, digest) != owner:
            return None
        stored = _package_by_candidate_digest(conn, digest)
        if stored is None:
            return None
        return self._public_projection(conn, stored)

    def decide(
        self,
        conn: sqlite3.Connection,
        package_id: str,
        expected_package_digest: str,
        action: str,
        signer_context: SignerContext,
    ) -> dict[str, Any]:
        """Approve or reject one exact pending package with human-only CAS."""

        _require_active_transaction(conn)
        self._assert_runtime_isolation()
        if action not in ("approve", "reject"):
            _conflict(
                "unsupported_skill_package_decision",
                "Skill Package 仅支持批准或拒绝",
            )
        signer = resolve_signer(conn, signer_context)
        if signer is None or signer.source != AUTHENTICATED_SESSION:
            _conflict(
                "signer_session_unverifiable",
                "提交时认证会话已失效，Skill Package 决定未写入",
            )
        # Ownership is deliberately indistinguishable from absence.  Digest,
        # state, review history, and file-integrity differences are evaluated
        # only after this 404 gate so another engineer cannot use the endpoint
        # as a package-state oracle.
        if _package_owner_by_id(conn, package_id) != signer.username:
            raise SkillPackageNotFoundError(f"Skill Package 不存在：{package_id}")
        stored = _package_by_id(conn, package_id)
        if stored is None:
            raise SkillPackageNotFoundError(f"Skill Package 不存在：{package_id}")
        expected = _required_digest(expected_package_digest, "expected package digest")
        if stored.get("package_digest") != expected:
            _conflict(
                "skill_package_digest_conflict",
                "Skill Package 内容代际已变化，请重新读取后决定",
            )
        if (
            stored.get("state") != "pending_review"
            or stored.get("review_event_id") is not None
        ):
            _conflict(
                "skill_package_already_decided",
                "该 Skill Package 已经作出人工决定，不能重复或改写",
            )

        # Review is forbidden when any byte or accepted-source proof has drifted.
        self._public_projection(conn, stored)
        now = _now_iso()
        to_state = "approved" if action == "approve" else "rejected"
        event_id = f"skill_package_event_{uuid.uuid4().hex}"
        package_store.append_event(
            conn,
            {
                "event_id": event_id,
                "package_id": package_id,
                "package_digest": expected,
                "event_type": to_state,
                "from_state": "pending_review",
                "to_state": to_state,
                "actor_source": AUTHENTICATED_SESSION,
                "signer_display_name": signer.confirmed_by,
                "signer_user_id": signer.user_id,
                "signer_username": signer.username,
                "signer_session_hash": signer.session_hash,
                "message": (
                    "工程师批准该精确 Skill Package 修订可供受控方法复用"
                    if action == "approve"
                    else "工程师拒绝该精确 Skill Package 修订"
                ),
                "payload": {},
                "created_at": now,
            },
            schema=self._event_schema,
        )
        updated = package_store.cas_decision(
            conn,
            package_id=package_id,
            expected_package_digest=expected,
            event_id=event_id,
            state=to_state,
            updated_at=now,
        )
        if updated != 1:
            _conflict(
                "skill_package_already_decided",
                "该 Skill Package 已被并发决定，当前决定未写入",
            )
        final = _package_by_id(conn, package_id)
        if final is None:
            raise SkillPackageUnavailableError(
                "decided Skill Package could not be read back"
            )
        return self._public_projection(conn, final)

    def list_reuse_eligible(
        self,
        conn: sqlite3.Connection,
        *,
        username: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return only approved, byte-verified methods; corrupt rows fail soft.

        Guide routing remains available when one quarantined package is damaged,
        but that package is never returned as reusable.
        """

        self._assert_runtime_isolation()
        owner = _required_owner(username)
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 101
        ):
            raise ValueError("limit must be an integer between 1 and 101")
        list_ids = getattr(package_store, "list_approved_ids_for_owner", None)
        if callable(list_ids):
            package_ids = list_ids(conn, owner, limit)
        else:
            # Compatibility while older repositories are migrated.  A malformed
            # decoded row must disable reuse, never the Guide route itself.
            try:
                package_ids = [
                    row["id"]
                    for row in package_store.list_approved_for_owner(conn, owner)[
                        :limit
                    ]
                ]
            except (ValueError, json.JSONDecodeError, sqlite3.DatabaseError):
                return []
        if limit == 101 and len(package_ids) >= 101:
            # This is the matcher policy's raw population sentinel.  Reject it
            # before decoding/filtering any row; otherwise one corrupt package
            # could hide a 101st valid tie and manufacture false uniqueness.
            raise SkillPackageUnavailableError(
                "approved Skill Package population exceeds the bounded reuse scan"
            )
        reusable: list[dict[str, Any]] = []
        for package_id in package_ids:
            try:
                stored = _package_by_id(conn, package_id)
                if stored is None:
                    continue
                package = self._public_projection(conn, stored)
                if package.get("reuse_eligible") is not True:
                    continue
                content = self._verified_file_content(stored)
                skill_revision = json.loads(
                    content["references/skill-revision.json"].decode("utf-8")
                )
                skill_markdown = content["SKILL.md"].decode("utf-8")
                if not isinstance(skill_revision, dict):
                    raise SkillPackageUnavailableError(
                        "stored Skill revision is not an object"
                    )
                reusable.append(
                    {
                        "package": package,
                        "skill_revision": skill_revision,
                        "skill_markdown": skill_markdown,
                    }
                )
            except (
                FileNotFoundError,
                FileIntegrityError,
                SkillPackageUnavailableError,
                UnicodeError,
                json.JSONDecodeError,
                OSError,
                ValueError,
            ):
                continue
        return reusable

    def load_reuse_payload(
        self,
        conn: sqlite3.Connection,
        *,
        package_id: str,
        username: str,
    ) -> dict[str, Any]:
        """Cold-load one exact approved package for a downstream trusted seam."""

        self._assert_runtime_isolation()
        package = self.get(conn, package_id, username)
        if package.get("reuse_eligible") is not True:
            _conflict(
                "skill_package_not_reuse_eligible",
                "Skill Package 尚未通过人工审核，不能用于自动复用",
            )
        stored = _package_by_id(conn, package_id)
        if stored is None:
            raise SkillPackageNotFoundError(f"Skill Package 不存在：{package_id}")
        content = self._verified_file_content(stored)
        try:
            skill_revision = json.loads(
                content["references/skill-revision.json"].decode("utf-8")
            )
            skill_markdown = content["SKILL.md"].decode("utf-8")
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise SkillPackageUnavailableError(
                "Skill Package method content cannot be decoded"
            ) from exc
        if not isinstance(skill_revision, dict):
            raise SkillPackageUnavailableError("stored Skill revision is not an object")
        return {
            "package": package,
            "skill_revision": skill_revision,
            "skill_markdown": skill_markdown,
        }

    def get_review_content(
        self,
        conn: sqlite3.Connection,
        *,
        package_id: str,
        username: str,
    ) -> dict[str, Any]:
        """Return exact cold-verified UTF-8 bytes for human package review."""

        self._assert_runtime_isolation()
        package = self.get(conn, package_id, username)
        stored = _package_by_id(conn, package_id)
        if stored is None:
            raise SkillPackageNotFoundError(f"Skill Package 不存在：{package_id}")
        content = self._verified_file_content(stored)
        files: list[dict[str, str]] = []
        try:
            for path in _EXPECTED_FILE_PATHS:
                files.append({"path": path, "text": content[path].decode("utf-8")})
        except (KeyError, UnicodeError) as exc:
            raise SkillPackageUnavailableError(
                "Skill Package review content is not valid UTF-8"
            ) from exc
        review_content = {
            "schema_version": REVIEW_CONTENT_SCHEMA_VERSION,
            "package_id": package["id"],
            "package_digest": package["package_digest"],
            "files": files,
        }
        try:
            validate(review_content, self._review_content_schema)
        except ValidationError as exc:
            raise SkillPackageUnavailableError(
                "Skill Package review content violates its public contract"
            ) from exc
        return review_content

    def resolve_reuse_eligible(
        self,
        conn: sqlite3.Connection,
        *,
        ref: Mapping[str, Any],
        username: str,
        agent_id: str,
    ) -> dict[str, Any]:
        """Resolve an exact trusted ref into freshly verified method content.

        Match-policy and match-basis validation belongs to the routing boundary
        that created the reference.  This seam pins the package/source identity
        used by task creation and runtime execution, then cold-verifies bytes and
        the accepted human-signature chain again.
        """

        self._assert_runtime_isolation()
        if not isinstance(ref, Mapping):
            _invalid_reuse_ref()
        owner = _required_owner(username)
        expected_agent = _required_text(agent_id, "reuse Agent id")
        package_id = ref.get("package_id")
        if (
            not isinstance(package_id, str)
            or _PACKAGE_ID_RE.fullmatch(package_id) is None
        ):
            _invalid_reuse_ref()
        payload = self.load_reuse_payload(
            conn,
            package_id=package_id,
            username=owner,
        )
        package = payload["package"]
        source = package.get("source")
        revision = payload["skill_revision"]
        if not isinstance(source, Mapping) or not isinstance(revision, Mapping):
            raise SkillPackageUnavailableError(
                "verified Skill Package reuse payload is malformed"
            )
        if (
            ref.get("schema_version") != "skill_reuse_ref.v1"
            or ref.get("package_version") != package.get("version")
            or ref.get("package_digest") != package.get("package_digest")
            or ref.get("candidate_digest") != source.get("candidate_digest")
            or ref.get("skill_digest") != source.get("skill_digest")
            or ref.get("review_state") != "approved"
            or ref.get("matched_agent_id") != expected_agent
            or source.get("agent_id") != expected_agent
            or revision.get("content_digest") != source.get("skill_digest")
            or ref.get("skill_name") != revision.get("name")
        ):
            _invalid_reuse_ref()
        return payload

    def _fresh_accepted_candidate(
        self,
        conn: sqlite3.Connection,
        *,
        candidate_public: Mapping[str, Any],
        accepted_event: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not isinstance(candidate_public, Mapping) or not isinstance(
            accepted_event, Mapping
        ):
            raise SkillPackageUnavailableError(
                "accepted candidate materialization input is malformed"
            )
        candidate_id = candidate_public.get("id")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise SkillPackageUnavailableError("accepted candidate id is malformed")
        stored = _candidate_by_id(conn, candidate_id)
        if stored is None:
            raise SkillPackageNotFoundError(f"资产候选不存在：{candidate_id}")
        projector = getattr(self._ledger, "_public_projection", None)
        if not callable(projector):
            raise SkillPackageUnavailableError(
                "candidate ledger has no verified projection seam"
            )
        try:
            fresh = projector(conn, stored)
        except Exception as exc:
            raise SkillPackageUnavailableError(
                "accepted candidate could not be independently verified"
            ) from exc
        if not isinstance(fresh, dict):
            raise SkillPackageUnavailableError(
                "candidate ledger returned a malformed projection"
            )
        if _canonical_json(_candidate_materialization_view(fresh)) != _canonical_json(
            _candidate_materialization_view(candidate_public)
        ):
            raise SkillPackageUnavailableError(
                "accepted candidate projection changed before materialization"
            )
        decision_event_id = stored.get("decision_event_id")
        if not isinstance(decision_event_id, str) or not decision_event_id:
            raise SkillPackageUnavailableError(
                "accepted candidate has no terminal decision event"
            )
        source_event = _candidate_event(conn, decision_event_id)
        if source_event is None:
            raise SkillPackageUnavailableError(
                "accepted candidate decision event is unavailable"
            )
        if _canonical_json(source_event) != _canonical_json(accepted_event):
            raise SkillPackageUnavailableError(
                "accepted candidate event changed before materialization"
            )
        _verify_candidate_content(fresh)
        _verify_accepted_event(fresh, source_event)
        return fresh, source_event

    def _verified_source_for_package(
        self,
        conn: sqlite3.Connection,
        stored: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        candidate_id = stored.get("source_candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise SkillPackageUnavailableError(
                "stored Skill Package candidate pointer is malformed"
            )
        candidate_row = _candidate_by_id(conn, candidate_id)
        if candidate_row is None:
            raise SkillPackageUnavailableError(
                "stored Skill Package source candidate is missing"
            )
        projector = getattr(self._ledger, "_public_projection", None)
        if not callable(projector):
            raise SkillPackageUnavailableError(
                "candidate ledger has no verified projection seam"
            )
        try:
            candidate = projector(conn, candidate_row)
        except Exception as exc:
            raise SkillPackageUnavailableError(
                "stored Skill Package source candidate is unverifiable"
            ) from exc
        decision_event_id = candidate_row.get("decision_event_id")
        if not isinstance(decision_event_id, str) or not decision_event_id:
            raise SkillPackageUnavailableError(
                "stored Skill Package source has no acceptance event"
            )
        accepted_event = _candidate_event(conn, decision_event_id)
        if accepted_event is None:
            raise SkillPackageUnavailableError(
                "stored Skill Package acceptance event is missing"
            )
        _verify_candidate_content(candidate)
        _verify_accepted_event(candidate, accepted_event)
        return candidate, accepted_event

    def _public_projection(
        self,
        conn: sqlite3.Connection,
        stored: Mapping[str, Any],
    ) -> dict[str, Any]:
        self._assert_runtime_isolation()
        candidate, accepted_event = self._verified_source_for_package(conn, stored)
        source = _package_source(candidate, accepted_event)
        expected_name = _package_name(candidate)
        expected_version = _package_version(candidate)
        files = _validated_manifest(stored.get("files"))
        expected_digest = _package_digest(
            name=expected_name,
            version=expected_version,
            source=source,
            files=files,
        )
        package_digest = _required_digest(
            stored.get("package_digest"), "stored package digest"
        )
        package_id = stored.get("id")
        expected_id = f"skill_package_{expected_digest.removeprefix('sha256:')[:24]}"
        expected_relpath = f"quarantine/{expected_id}"
        if (
            stored.get("schema_version") != SCHEMA_VERSION
            or stored.get("name") != expected_name
            or stored.get("version") != expected_version
            or package_digest != expected_digest
            or package_id != expected_id
            or stored.get("storage_relpath") != expected_relpath
            or stored.get("source_candidate_id") != source["candidate_id"]
            or stored.get("source_candidate_digest") != source["candidate_digest"]
            or stored.get("source_bundle_digest") != source["bundle_digest"]
            or stored.get("source_skill_digest") != source["skill_digest"]
            or stored.get("source_acceptance_event_digest")
            != source["acceptance_event_digest"]
            or stored.get("source_task_id") != source["task_id"]
            or stored.get("source_agent_id") != source["agent_id"]
            or stored.get("owner_username") != source["initiated_by_username"]
        ):
            raise SkillPackageUnavailableError(
                "stored Skill Package does not match its content address"
            )
        self._verified_file_content(stored)
        review = self._verified_event_projection(conn, stored, source)
        state = stored.get("state")
        formation_evidence = {
            "schema_version": "composition_eligibility.v1",
            "independent_work_case_count": 0,
            "required_independent_work_cases": 2,
            "workflow_candidate": {
                "state": "not_formed",
                "eligible": False,
                "reason": "requires_independent_composition_evidence",
            },
            "agent_candidate": {
                "state": "not_formed",
                "eligible": False,
                "reason": "requires_approved_workflow_revision",
            },
        }
        if self._formation_evidence_provider is not None:
            formation_evidence = self._formation_evidence_provider.formation_evidence(
                conn,
                package_id=package_id,
                owner_username=source["initiated_by_username"],
            )
        public = {
            "schema_version": SCHEMA_VERSION,
            "id": package_id,
            "name": expected_name,
            "version": expected_version,
            "package_digest": package_digest,
            "state": state,
            "source": source,
            "files": files,
            "storage_relpath": expected_relpath,
            "review": review,
            "reuse_eligible": state == "approved",
            "isolation": {
                "zone": "candidate_quarantine",
                "registered": False,
                "executable": False,
            },
            "formation_evidence": formation_evidence,
            "created_at": stored.get("created_at"),
            "updated_at": stored.get("updated_at"),
        }
        try:
            validate(public, self._package_schema)
        except ValidationError as exc:
            raise SkillPackageUnavailableError(
                "Skill Package response violates its public contract"
            ) from exc
        return public

    def _verified_event_projection(
        self,
        conn: sqlite3.Connection,
        stored: Mapping[str, Any],
        source: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        try:
            events = package_store.list_events(conn, str(stored.get("id") or ""))
        except (ValueError, json.JSONDecodeError, sqlite3.DatabaseError) as exc:
            raise SkillPackageUnavailableError(
                "Skill Package event history cannot be decoded"
            ) from exc
        state = stored.get("state")
        review_event_id = stored.get("review_event_id")
        if state not in ("pending_review", "approved", "rejected"):
            raise SkillPackageUnavailableError(
                "stored Skill Package state is unsupported"
            )
        expected_count = 1 if state == "pending_review" else 2
        if len(events) != expected_count:
            raise SkillPackageUnavailableError(
                "Skill Package event history is missing or ambiguous"
            )
        materialized = [
            event for event in events if event.get("event_type") == "materialized"
        ]
        if len(materialized) != 1:
            raise SkillPackageUnavailableError(
                "Skill Package has no unique materialization event"
            )
        first = materialized[0]
        expected_payload = {
            "source_candidate_digest": source["candidate_digest"],
            "source_acceptance_event_digest": source["acceptance_event_digest"],
        }
        if (
            first.get("package_id") != stored.get("id")
            or first.get("package_digest") != stored.get("package_digest")
            or first.get("from_state") is not None
            or first.get("to_state") != "pending_review"
            or first.get("actor_source") != "candidate_materializer"
            or any(
                first.get(field) is not None
                for field in (
                    "signer_display_name",
                    "signer_user_id",
                    "signer_username",
                    "signer_session_hash",
                )
            )
            or first.get("payload") != expected_payload
        ):
            raise SkillPackageUnavailableError(
                "Skill Package materialization event is malformed"
            )
        if state == "pending_review":
            if review_event_id is not None:
                raise SkillPackageUnavailableError(
                    "pending Skill Package has a review pointer"
                )
            return None

        if not isinstance(review_event_id, str) or not review_event_id:
            raise SkillPackageUnavailableError(
                "decided Skill Package has no review pointer"
            )
        review_events = [
            event for event in events if event.get("event_id") == review_event_id
        ]
        if len(review_events) != 1:
            raise SkillPackageUnavailableError(
                "Skill Package review event pointer is ambiguous"
            )
        event = review_events[0]
        expected_event_type = "approved" if state == "approved" else "rejected"
        attestation = {
            "signer_source": event.get("actor_source"),
            "confirmed_by": event.get("signer_display_name"),
            "signer_user_id": event.get("signer_user_id"),
            "signer_username": event.get("signer_username"),
            "signer_session_hash": event.get("signer_session_hash"),
        }
        if (
            event.get("package_id") != stored.get("id")
            or event.get("package_digest") != stored.get("package_digest")
            or event.get("event_type") != expected_event_type
            or event.get("from_state") != "pending_review"
            or event.get("to_state") != state
            or event.get("actor_source") != AUTHENTICATED_SESSION
            or event.get("signer_username") != stored.get("owner_username")
            or event.get("payload") != {}
            or stored_signer_attests(attestation) is not True
        ):
            raise SkillPackageUnavailableError(
                "Skill Package review signer provenance is invalid"
            )
        return {
            "action": "approve" if state == "approved" else "reject",
            "reviewed_by": event["signer_display_name"],
            "reviewed_by_username": event["signer_username"],
            "signer_source": AUTHENTICATED_SESSION,
            "signer_session_bound": True,
            "created_at": event["created_at"],
        }

    def _verified_file_content(self, stored: Mapping[str, Any]) -> dict[str, bytes]:
        self._assert_runtime_isolation()
        files = _validated_manifest(stored.get("files"))
        package_dir = _safe_package_dir(
            root=self._root,
            storage_relpath=stored.get("storage_relpath"),
            package_id=stored.get("id"),
        )
        content: dict[str, bytes] = {}
        try:
            for item in files:
                self._assert_runtime_isolation()
                path = package_dir.joinpath(*PurePosixPath(item["path"]).parts)
                with open_verified_file(
                    path,
                    allowed_root=self._root,
                    expected_size=item["size_bytes"],
                    expected_sha256=item["sha256"],
                ) as handle:
                    content[item["path"]] = handle.read()
            _assert_exact_tree(package_dir, set(_EXPECTED_FILE_PATHS))
        except (FileNotFoundError, FileIntegrityError, OSError) as exc:
            raise SkillPackageUnavailableError(
                "Skill Package files failed cold integrity verification"
            ) from exc
        return content

    def _install_or_adopt_tree(
        self,
        *,
        final_dir: Path,
        storage_relpath: str,
        file_bytes: Mapping[str, bytes],
    ) -> None:
        self._assert_runtime_isolation()
        _safe_package_dir(
            root=self._root,
            storage_relpath=storage_relpath,
            package_id=final_dir.name,
            require_root=False,
        )
        _prepare_isolated_root(self._root)
        self._assert_runtime_isolation()
        quarantine_root = self._root / "quarantine"
        staging_root = self._root / ".staging"
        _prepare_isolated_child(quarantine_root)
        _prepare_isolated_child(staging_root)
        _fsync_directory(self._root)
        if _lexists(final_dir):
            _verify_expected_tree(
                final_dir,
                self._root,
                file_bytes,
                guard=self._assert_runtime_isolation,
            )
            _fsync_package_directories(final_dir, quarantine_root, self._root)
            return

        staging_dir = staging_root / f"materialize_{uuid.uuid4().hex}"
        staging_dir.mkdir(mode=0o700, exist_ok=False)
        _fsync_directory(staging_root)
        renamed = False
        try:
            references_dir = staging_dir / "references"
            references_dir.mkdir(mode=0o700, exist_ok=False)
            _fsync_directory(staging_dir)
            for relative_path in _EXPECTED_FILE_PATHS:
                self._assert_runtime_isolation()
                destination = staging_dir.joinpath(*PurePosixPath(relative_path).parts)
                _write_exclusive(destination, file_bytes[relative_path])
            _fsync_directory(references_dir)
            _fsync_directory(staging_dir)
            _verify_expected_tree(
                staging_dir,
                self._root,
                file_bytes,
                guard=self._assert_runtime_isolation,
            )
            if _lexists(final_dir):
                _verify_expected_tree(
                    final_dir,
                    self._root,
                    file_bytes,
                    guard=self._assert_runtime_isolation,
                )
                return
            self._assert_runtime_isolation()
            os.rename(staging_dir, final_dir)
            renamed = True
            _fsync_directory(staging_root)
            _fsync_directory(quarantine_root)
            _fsync_directory(self._root)
            _verify_expected_tree(
                final_dir,
                self._root,
                file_bytes,
                guard=self._assert_runtime_isolation,
            )
            _fsync_package_directories(final_dir, quarantine_root, self._root)
        except FileExistsError:
            if not _lexists(final_dir):
                raise
            _verify_expected_tree(
                final_dir,
                self._root,
                file_bytes,
                guard=self._assert_runtime_isolation,
            )
            _fsync_package_directories(final_dir, quarantine_root, self._root)
        except (FileIntegrityError, OSError, KeyError) as exc:
            raise SkillPackageUnavailableError(
                "Skill Package could not be installed into quarantine"
            ) from exc
        finally:
            if not renamed and staging_dir.exists():
                shutil.rmtree(staging_dir)
                _fsync_directory(staging_root)

    def _assert_runtime_isolation(self) -> None:
        _assert_root_realpath_outside_forbidden(
            self._root,
            self._forbidden_roots,
            constructor=False,
        )


def _load_contract_schema(contracts_dir: Path, name: str) -> dict[str, Any]:
    try:
        loaded = json.loads((contracts_dir / name).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SkillPackageUnavailableError(
            f"Skill Package contract is unavailable: {name}"
        ) from exc
    if not isinstance(loaded, dict):
        raise SkillPackageUnavailableError(
            f"Skill Package contract is not an object: {name}"
        )
    return loaded


def _package_by_id(conn: sqlite3.Connection, package_id: str) -> dict[str, Any] | None:
    try:
        return package_store.get_by_id(conn, package_id)
    except (ValueError, json.JSONDecodeError, sqlite3.DatabaseError) as exc:
        raise SkillPackageUnavailableError(
            "stored Skill Package row cannot be decoded"
        ) from exc


def _package_owner_by_id(conn: sqlite3.Connection, package_id: str) -> str | None:
    try:
        return package_store.get_owner_by_id(conn, package_id)
    except sqlite3.DatabaseError as exc:
        raise SkillPackageUnavailableError(
            "stored Skill Package owner cannot be read"
        ) from exc


def _package_owner_by_candidate_digest(
    conn: sqlite3.Connection,
    candidate_digest: str,
) -> str | None:
    try:
        return package_store.get_owner_by_candidate_digest(conn, candidate_digest)
    except sqlite3.DatabaseError as exc:
        raise SkillPackageUnavailableError(
            "stored Skill Package owner cannot be read"
        ) from exc


def _package_by_candidate_digest(
    conn: sqlite3.Connection, candidate_digest: str
) -> dict[str, Any] | None:
    try:
        return package_store.get_by_candidate_digest(conn, candidate_digest)
    except (ValueError, json.JSONDecodeError, sqlite3.DatabaseError) as exc:
        raise SkillPackageUnavailableError(
            "stored Skill Package row cannot be decoded"
        ) from exc


def _candidate_by_id(
    conn: sqlite3.Connection, candidate_id: str
) -> dict[str, Any] | None:
    try:
        return candidate_store.get_by_id(conn, candidate_id)
    except (ValueError, json.JSONDecodeError, sqlite3.DatabaseError) as exc:
        raise SkillPackageUnavailableError(
            "stored Asset Candidate row cannot be decoded"
        ) from exc


def _latest_candidate_id(conn: sqlite3.Connection, task_id: str) -> str | None:
    try:
        return candidate_store.get_latest_id_for_task(conn, task_id)
    except sqlite3.DatabaseError as exc:
        raise SkillPackageUnavailableError(
            "latest Asset Candidate revision cannot be read"
        ) from exc


def _candidate_event(conn: sqlite3.Connection, event_id: str) -> dict[str, Any] | None:
    try:
        return candidate_store.get_event(conn, event_id)
    except (ValueError, json.JSONDecodeError, sqlite3.DatabaseError) as exc:
        raise SkillPackageUnavailableError(
            "stored Asset Candidate decision event cannot be decoded"
        ) from exc


def _package_source(
    candidate: Mapping[str, Any], accepted_event: Mapping[str, Any]
) -> dict[str, Any]:
    source = candidate.get("source")
    bundle = candidate.get("bundle")
    if not isinstance(source, Mapping) or not isinstance(bundle, Mapping):
        raise SkillPackageUnavailableError("accepted candidate source is malformed")
    skill = bundle.get("skill")
    if not isinstance(skill, Mapping):
        raise SkillPackageUnavailableError("accepted Skill revision is malformed")
    return {
        "candidate_id": _required_text(candidate.get("id"), "candidate id"),
        "candidate_digest": _required_digest(
            candidate.get("candidate_digest"), "candidate digest"
        ),
        "bundle_digest": _required_digest(
            candidate.get("bundle_digest"), "bundle digest"
        ),
        "skill_digest": _required_digest(
            skill.get("content_digest"), "Skill revision digest"
        ),
        "acceptance_event_digest": _acceptance_attestation_digest(
            candidate,
            accepted_event,
        ),
        "task_id": _required_text(source.get("task_id"), "source task id"),
        "agent_id": _required_text(source.get("agent_id"), "source Agent id"),
        "initiated_by_username": _required_owner(source.get("initiated_by_username")),
    }


def _package_name(candidate: Mapping[str, Any]) -> str:
    source = candidate.get("source")
    if not isinstance(source, Mapping):
        raise SkillPackageUnavailableError("accepted candidate source is malformed")
    agent_id = _required_text(source.get("agent_id"), "source Agent id")
    task_id = _required_text(source.get("task_id"), "source task id")
    slug = _SLUG_RE.sub("-", unicodedata.normalize("NFC", agent_id).lower()).strip("-")
    if not slug:
        slug = "engineering-method"
    suffix = hashlib.sha256(
        unicodedata.normalize("NFC", task_id).encode("utf-8")
    ).hexdigest()[:10]
    available = 63 - len("-method-") - len(suffix)
    slug = slug[:available].rstrip("-") or "engineering"
    name = f"{slug}-method-{suffix}"
    if len(name) >= 64 or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) is None:
        raise SkillPackageUnavailableError("derived Skill Package name is invalid")
    return name


def _package_version(candidate: Mapping[str, Any]) -> str:
    revision = candidate.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise SkillPackageUnavailableError("accepted candidate revision is malformed")
    return f"0.{revision}.0"


def _render_package_files(
    *,
    candidate: Mapping[str, Any],
    source: Mapping[str, Any],
    name: str,
    version: str,
) -> dict[str, bytes]:
    bundle = candidate.get("bundle")
    if not isinstance(bundle, Mapping):
        raise SkillPackageUnavailableError("accepted candidate bundle is malformed")
    task_pattern = bundle.get("task_pattern")
    skill = bundle.get("skill")
    if not isinstance(task_pattern, Mapping) or not isinstance(skill, Mapping):
        raise SkillPackageUnavailableError("accepted candidate revisions are malformed")
    provenance = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "materializer_policy_version": MATERIALIZER_POLICY_VERSION,
        "name": name,
        "version": version,
        "source": dict(source),
        "isolation": {
            "zone": "candidate_quarantine",
            "registered": False,
            "executable": False,
        },
    }
    rendered = {
        "SKILL.md": _render_skill_markdown(name=name, skill=skill).encode("utf-8"),
        "references/provenance.json": _canonical_json_document(provenance),
        "references/skill-revision.json": _canonical_json_document(skill),
        "references/task-pattern-revision.json": _canonical_json_document(task_pattern),
    }
    return {path: rendered[path] for path in _EXPECTED_FILE_PATHS}


def _render_skill_markdown(*, name: str, skill: Mapping[str, Any]) -> str:
    description = _required_text(skill.get("description"), "Skill description")
    display_name = _required_text(skill.get("name"), "Skill name")
    when_to_use = _required_text(skill.get("when_to_use"), "Skill usage trigger")
    sections = (
        (
            "不适用条件",
            _required_text_list(skill.get("when_not_to_use"), "when_not_to_use"),
        ),
        ("输入", _required_text_list(skill.get("inputs"), "inputs")),
        ("输出", _required_text_list(skill.get("outputs"), "outputs")),
        ("执行步骤", _required_text_list(skill.get("instructions"), "instructions")),
        ("验证", _required_text_list(skill.get("verification"), "verification")),
        (
            "人工边界",
            _required_text_list(skill.get("human_boundaries"), "human_boundaries"),
        ),
    )
    lines = [
        "---",
        f"name: {name}",
        "description: "
        + json.dumps(_one_line(description), ensure_ascii=False, separators=(",", ":")),
        "---",
        "",
        f"# {_one_line(display_name)}",
        "",
        "## 适用时机",
        "",
        _one_line(when_to_use),
    ]
    for title, items in sections:
        lines.extend(("", f"## {title}", ""))
        lines.extend(f"- {_one_line(item)}" for item in items)
    return unicodedata.normalize("NFC", "\n".join(lines) + "\n")


def _verify_candidate_content(candidate: Mapping[str, Any]) -> None:
    if candidate.get("state") != "accepted":
        _conflict(
            "candidate_not_accepted",
            "只有已由工程师接受的资产候选可以材化 Skill Package",
        )
    bundle = candidate.get("bundle")
    if not isinstance(bundle, Mapping):
        raise SkillPackageUnavailableError("accepted candidate bundle is malformed")
    task_pattern = bundle.get("task_pattern")
    skill = bundle.get("skill")
    if not isinstance(task_pattern, Mapping) or not isinstance(skill, Mapping):
        raise SkillPackageUnavailableError(
            "accepted candidate Task Pattern or Skill revision is malformed"
        )
    task_digest = _required_digest(
        task_pattern.get("content_digest"), "Task Pattern revision digest"
    )
    skill_digest = _required_digest(
        skill.get("content_digest"), "Skill revision digest"
    )
    task_content = dict(task_pattern)
    task_content.pop("suggested_id", None)
    task_content.pop("content_digest", None)
    skill_content = dict(skill)
    skill_content.pop("suggested_id", None)
    skill_content.pop("content_digest", None)
    if (
        candidate_canonical_digest(task_content) != task_digest
        or candidate_canonical_digest(skill_content) != skill_digest
        or skill.get("operationalizes_task_pattern_digest") != task_digest
    ):
        raise SkillPackageUnavailableError(
            "accepted candidate revision content digests do not verify"
        )


def _verify_accepted_event(
    candidate: Mapping[str, Any], event: Mapping[str, Any]
) -> None:
    source = candidate.get("source")
    decision = candidate.get("decision")
    if not isinstance(source, Mapping) or not isinstance(decision, Mapping):
        raise SkillPackageUnavailableError(
            "accepted candidate decision projection is malformed"
        )
    owner = _candidate_owner(candidate)
    attestation = {
        "signer_source": event.get("actor_source"),
        "confirmed_by": event.get("signer_display_name"),
        "signer_user_id": event.get("signer_user_id"),
        "signer_username": event.get("signer_username"),
        "signer_session_hash": event.get("signer_session_hash"),
    }
    if (
        event.get("event_type") != "candidate_accepted"
        or event.get("from_state") != "awaiting_human_review"
        or event.get("to_state") != "accepted"
        or event.get("actor_source") != AUTHENTICATED_SESSION
        or event.get("candidate_id") != candidate.get("id")
        or event.get("candidate_digest") != candidate.get("candidate_digest")
        or event.get("bundle_digest") != candidate.get("bundle_digest")
        or event.get("signer_username") != owner
        or event.get("payload") != {}
        or stored_signer_attests(attestation) is not True
        or decision.get("action") != "accept"
        or decision.get("decided_by") != event.get("signer_display_name")
        or decision.get("decided_by_username") != event.get("signer_username")
        or decision.get("signer_source") != AUTHENTICATED_SESSION
        or decision.get("signer_session_bound") is not True
        or decision.get("created_at") != event.get("created_at")
    ):
        raise SkillPackageUnavailableError(
            "accepted candidate human-signature provenance is invalid"
        )


def _acceptance_attestation_digest(
    candidate: Mapping[str, Any],
    event: Mapping[str, Any],
) -> str:
    """Digest the exact stable human attestation, not transport ephemera.

    ``event_id``, ``created_at`` and localized ``message`` are generated by the
    persistence adapter and may legitimately change when a transaction rolls
    back after the filesystem rename.  The basis below still binds the exact
    candidate/bundle, transition, authenticated identity and session.  Thus the
    same signer/session retry adopts identical orphan bytes, while any identity,
    session, content or decision change produces a different address.
    """

    return _digest(
        {
            "schema_version": ACCEPTANCE_ATTESTATION_SCHEMA_VERSION,
            "candidate_id": candidate.get("id"),
            "candidate_digest": event.get("candidate_digest"),
            "bundle_digest": event.get("bundle_digest"),
            "event_type": event.get("event_type"),
            "from_state": event.get("from_state"),
            "to_state": event.get("to_state"),
            "actor_source": event.get("actor_source"),
            "signer_display_name": event.get("signer_display_name"),
            "signer_user_id": event.get("signer_user_id"),
            "signer_username": event.get("signer_username"),
            "signer_session_hash": event.get("signer_session_hash"),
            "payload": event.get("payload"),
        }
    )


def _candidate_owner(candidate: Mapping[str, Any]) -> str:
    source = candidate.get("source")
    if not isinstance(source, Mapping):
        raise SkillPackageUnavailableError("accepted candidate source is malformed")
    return _required_owner(source.get("initiated_by_username"))


def _candidate_materialization_view(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: candidate.get(key)
        for key in (
            "schema_version",
            "id",
            "revision",
            "supersedes_candidate_digest",
            "candidate_digest",
            "bundle_digest",
            "lineage_digest",
            "state",
            "source",
            "bundle",
            "lineage",
            "proposal_provenance",
            "decision",
            "created_at",
            "updated_at",
        )
    }


def _package_digest(
    *,
    name: str,
    version: str,
    source: Mapping[str, Any],
    files: list[dict[str, Any]],
) -> str:
    return _digest(
        {
            "schema_version": PACKAGE_DIGEST_SCHEMA_VERSION,
            "materializer_policy_version": MATERIALIZER_POLICY_VERSION,
            "name": name,
            "version": version,
            "source_candidate_digest": source["candidate_digest"],
            "source_bundle_digest": source["bundle_digest"],
            "source_skill_digest": source["skill_digest"],
            "source_acceptance_event_digest": source["acceptance_event_digest"],
            "files": files,
        }
    )


def _file_manifest(file_bytes: Mapping[str, bytes]) -> list[dict[str, Any]]:
    if set(file_bytes) != set(_EXPECTED_FILE_PATHS):
        raise SkillPackageUnavailableError(
            "materialized package file set is unsupported"
        )
    return [
        {
            "path": path,
            "sha256": hashlib.sha256(file_bytes[path]).hexdigest(),
            "size_bytes": len(file_bytes[path]),
        }
        for path in _EXPECTED_FILE_PATHS
    ]


def _validated_manifest(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) != len(_EXPECTED_FILE_PATHS):
        raise SkillPackageUnavailableError("stored file manifest is malformed")
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise SkillPackageUnavailableError("stored file manifest is malformed")
        path = item.get("path")
        sha256 = item.get("sha256")
        size = item.get("size_bytes")
        if (
            not isinstance(path, str)
            or not isinstance(sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", sha256) is None
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
            or set(item) != {"path", "sha256", "size_bytes"}
        ):
            raise SkillPackageUnavailableError("stored file manifest is malformed")
        normalized.append({"path": path, "sha256": sha256, "size_bytes": size})
    if tuple(item["path"] for item in normalized) != _EXPECTED_FILE_PATHS:
        raise SkillPackageUnavailableError(
            "stored file manifest paths are missing, unordered, or unsupported"
        )
    return normalized


def _safe_package_dir(
    *,
    root: Path,
    storage_relpath: Any,
    package_id: Any,
    require_root: bool = True,
) -> Path:
    if (
        not isinstance(storage_relpath, str)
        or not isinstance(package_id, str)
        or _PACKAGE_ID_RE.fullmatch(package_id) is None
        or _PACKAGE_DIR_RE.fullmatch(package_id) is None
    ):
        raise SkillPackageUnavailableError(
            "stored Skill Package path identity is malformed"
        )
    relative = PurePosixPath(storage_relpath)
    if (
        relative.is_absolute()
        or relative.parts != ("quarantine", package_id)
        or any(part in ("", ".", "..") for part in relative.parts)
    ):
        raise SkillPackageUnavailableError(
            "stored Skill Package path escapes its isolation contract"
        )
    if require_root and not root.exists():
        raise SkillPackageUnavailableError("Skill Package isolation root is missing")
    return root.joinpath(*relative.parts)


def _assert_exact_tree(package_dir: Path, expected_files: set[str]) -> None:
    if package_dir.is_symlink() or not package_dir.is_dir():
        raise FileIntegrityError("Skill Package address is not a regular directory")
    actual: set[str] = set()
    for path in package_dir.rglob("*"):
        if path.is_symlink():
            raise FileIntegrityError("Skill Package tree contains a symbolic link")
        if path.is_file():
            actual.add(path.relative_to(package_dir).as_posix())
        elif not path.is_dir():
            raise FileIntegrityError("Skill Package tree contains a special object")
    if actual != expected_files:
        raise FileIntegrityError("Skill Package tree contains unexpected files")


def _verify_expected_tree(
    package_dir: Path,
    root: Path,
    expected: Mapping[str, bytes],
    *,
    guard: Callable[[], None] | None = None,
) -> None:
    if guard is not None:
        guard()
    _assert_exact_tree(package_dir, set(_EXPECTED_FILE_PATHS))
    for relative_path in _EXPECTED_FILE_PATHS:
        if guard is not None:
            guard()
        payload = expected[relative_path]
        path = package_dir.joinpath(*PurePosixPath(relative_path).parts)
        with open_verified_file(
            path,
            allowed_root=root,
            expected_size=len(payload),
            expected_sha256=hashlib.sha256(payload).hexdigest(),
        ) as handle:
            if handle.read() != payload:
                raise FileIntegrityError(
                    "orphan Skill Package bytes do not match the accepted candidate"
                )


def _prepare_isolated_root(root: Path) -> None:
    if _lexists(root) and root.is_symlink():
        raise SkillPackageUnavailableError(
            "Skill Package isolation root cannot be a symbolic link"
        )
    if _lexists(root):
        if not root.is_dir():
            raise SkillPackageUnavailableError(
                "Skill Package isolation root is not a regular directory"
            )
        _fsync_directory(root)
        return
    # Startup owns creation of the data parent.  Creating only this leaf keeps
    # the durability boundary explicit: after persisting the new directory we
    # must also persist the parent dirent that makes it reachable.
    root.mkdir(mode=0o700, exist_ok=False)
    if root.is_symlink() or not root.is_dir():
        raise SkillPackageUnavailableError(
            "Skill Package isolation root is not a regular directory"
        )
    _fsync_directory(root)
    _fsync_directory(root.parent)


def _prepare_isolated_child(path: Path) -> None:
    if _lexists(path):
        if path.is_symlink() or not path.is_dir():
            raise SkillPackageUnavailableError(
                "Skill Package isolation child is not a regular directory"
            )
        _fsync_directory(path)
        return
    path.mkdir(mode=0o700, exist_ok=False)
    if path.is_symlink() or not path.is_dir():
        raise SkillPackageUnavailableError(
            "Skill Package isolation child is not a regular directory"
        )
    _fsync_directory(path)
    _fsync_directory(path.parent)


def _lexists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise SkillPackageUnavailableError(
            "Skill Package isolation path cannot be inspected"
        ) from exc
    return True


def _assert_isolated_root(root: Path) -> None:
    if not root.is_absolute():
        raise ValueError("candidate Skill Package root must be absolute")
    lowered = {part.lower() for part in root.parts}
    if lowered & _FORBIDDEN_ROOT_PARTS:
        raise ValueError(
            "candidate Skill Package root must not be inside Agent or user Skill paths"
        )


def _assert_root_realpath_outside_forbidden(
    root: Path,
    forbidden_roots: tuple[Path, ...],
    *,
    constructor: bool,
) -> None:
    try:
        resolved_root = Path(os.path.realpath(os.fspath(root)))
        resolved_forbidden = tuple(
            Path(os.path.realpath(os.fspath(path))) for path in forbidden_roots
        )
    except (OSError, TypeError, ValueError) as exc:
        if constructor:
            raise ValueError(
                "candidate Skill Package root realpath is unavailable"
            ) from exc
        raise SkillPackageUnavailableError(
            "Skill Package isolation root realpath is unavailable"
        ) from exc
    if any(
        resolved_root == forbidden or resolved_root.is_relative_to(forbidden)
        for forbidden in resolved_forbidden
    ):
        if constructor:
            raise ValueError(
                "candidate Skill Package root resolves inside a forbidden root"
            )
        raise SkillPackageUnavailableError(
            "Skill Package isolation root resolves inside a forbidden root"
        )


def _require_active_transaction(conn: sqlite3.Connection) -> None:
    if not isinstance(conn, sqlite3.Connection) or conn.in_transaction is not True:
        raise SkillPackageUnavailableError(
            "Skill Package mutation requires a caller-owned active transaction"
        )


def _fsync_directory(path: Path) -> None:
    """Persist directory metadata on POSIX; Windows has no equivalent contract.

    Windows cannot portably open directories for ``fsync`` through Python's
    stdlib.  The Windows path therefore relies on flush+close for file bytes and
    atomic ``os.rename`` semantics, without claiming POSIX crash durability.
    POSIX errors are never swallowed: the enclosing candidate transaction must
    roll back rather than report a package whose directory entries are not
    durable.
    """

    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_package_directories(
    package_dir: Path,
    quarantine_root: Path,
    root: Path,
) -> None:
    _fsync_directory(package_dir / "references")
    _fsync_directory(package_dir)
    _fsync_directory(quarantine_root)
    _fsync_directory(root)


def _write_exclusive(path: Path, payload: bytes) -> None:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_BINARY", 0)
    )
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def _package_schema_document(value: Any) -> Any:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise SkillPackageUnavailableError("canonical object keys must be strings")
        return {
            unicodedata.normalize("NFC", key): _package_schema_document(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_package_schema_document(item) for item in value]
    if isinstance(value, tuple):
        return [_package_schema_document(item) for item in value]
    if isinstance(value, str):
        return (
            unicodedata.normalize("NFC", value)
            .replace("\r\n", "\n")
            .replace("\r", "\n")
        )
    if value is None or isinstance(value, (bool, int)):
        return value
    if (
        isinstance(value, float)
        and value == value
        and value not in (float("inf"), float("-inf"))
    ):
        return value
    raise SkillPackageUnavailableError(
        f"unsupported canonical value type: {type(value).__name__}"
    )


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            _package_schema_document(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise SkillPackageUnavailableError(
            "Skill Package value cannot be canonicalized"
        ) from exc


def _canonical_json_document(value: Any) -> bytes:
    return (_canonical_json(value) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return (
        f"sha256:{hashlib.sha256(_canonical_json(value).encode('utf-8')).hexdigest()}"
    )


def _required_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise SkillPackageUnavailableError(f"{label} is malformed")
    return value


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SkillPackageUnavailableError(f"{label} is missing")
    return unicodedata.normalize("NFC", value)


def _required_owner(value: Any) -> str:
    owner = _required_text(value, "owner username").strip()
    if len(owner) > 128:
        raise SkillPackageUnavailableError("owner username is malformed")
    return owner


def _required_text_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise SkillPackageUnavailableError(f"Skill {label} is malformed")
    result: list[str] = []
    for item in value:
        result.append(_required_text(item, f"Skill {label} item"))
    return result


def _one_line(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conflict(code: str, message: str) -> None:
    raise SkillPackageConflictError(code, message)


def _invalid_reuse_ref() -> None:
    _conflict(
        "skill_package_reuse_invalid",
        "Skill 复用引用与已审核包、来源候选或目标 Agent 不一致",
    )
