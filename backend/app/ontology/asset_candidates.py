"""Completed engineering task -> governed, content-addressed Asset Candidate.

This module owns the ADR-0034 admission gates and candidate state machine.  An
accepted revision may delegate deterministic SKILL.md materialization to the
ADR-0035 quarantine service inside the same transaction.  It still never
writes Agent packages, calls a model, registers an asset, executes work, or
promotes anything.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import unicodedata
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from jsonschema import ValidationError, validate

from ..governance.signer_provenance import (
    AUTHENTICATED_SESSION,
    SignerContext,
    resolve_signer,
    stored_signer_attests,
)
from ..runtime.package_snapshot import SNAPSHOT_CONTRACT
from ..runtime.task_evidence import input_files_evidence
from ..runtime.work_segments import (
    created_at_or_before,
    created_strictly_after,
    is_canonical_qa_delivery,
    is_guide_refuse_delivery,
    latest_valid_iso,
)
from ..storage import asset_candidates as candidate_store
from ..storage import repos
from .asset_builder import (
    AssetDraftBuilder,
    AssetDraftInputError,
    AssetDraftProjectionError,
    AssetDraftSourceError,
)

SCHEMA_VERSION = "asset_candidate.v1"
LINEAGE_SCHEMA_VERSION = "asset_candidate_lineage.v1"
POLICY_VERSION = "asset_candidate_policy.v1"
PROPOSAL_PROVENANCE_VERSION = "generalization_proposal_provenance.v1"

_HEX_DIGEST_LENGTH = 64
_MAX_FILE_REFERENCES = 64
_PROPOSAL_SOURCES = [
    "work_case_segment",
    "completed_task",
    "agent_package_snapshot",
    "artifact_digests",
    "signoff_evidence",
]


class AssetCandidateNotFoundError(LookupError):
    """The requested task/candidate does not exist."""


class AssetCandidateConflictError(RuntimeError):
    """A fail-closed admission, ownership, digest, or state gate rejected work."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class AssetCandidateUnavailableError(RuntimeError):
    """Persisted or Registry source data is malformed and cannot be trusted."""


class AssetCandidateLedger:
    """One deep public seam for create/read/decide over immutable candidates."""

    def __init__(
        self,
        *,
        builder: AssetDraftBuilder,
        agent_registry: Any,
        contracts_dir: Path,
    ) -> None:
        self._builder = builder
        self._agent_registry = agent_registry
        try:
            schema = json.loads(
                (Path(contracts_dir) / "asset_candidate.schema.json").read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise AssetCandidateUnavailableError(
                "asset candidate response schema is unavailable"
            ) from exc
        if not isinstance(schema, dict):
            raise AssetCandidateUnavailableError(
                "asset candidate response schema is not an object"
            )
        self._response_schema = schema
        self._materializer: Any | None = None

    def attach_materializer(self, materializer: Any) -> None:
        """Attach the one ADR-0035 quarantine seam during app assembly."""

        if materializer is None or not callable(
            getattr(materializer, "materialize_accepted", None)
        ):
            raise AssetCandidateUnavailableError(
                "candidate materializer is unavailable"
            )
        self._materializer = materializer

    def create_for_completed_task(
        self,
        conn: sqlite3.Connection,
        *,
        task_id: str,
        initiated_by_user_id: int,
        initiated_by_username: str,
    ) -> dict[str, Any]:
        if (
            not isinstance(initiated_by_user_id, int)
            or isinstance(initiated_by_user_id, bool)
            or initiated_by_user_id <= 0
        ):
            raise AssetCandidateUnavailableError("authenticated user id is invalid")
        actor_username = _required_text(
            initiated_by_username, "initiated_by_username", max_length=128
        )

        conn.execute("BEGIN IMMEDIATE")
        try:
            task = self._task_for_owner(conn, task_id, actor_username)
            projection = self._verified_projection(conn, task)
            conversation = projection["conversation"]
            bundle = projection["bundle"]
            lineage = projection["lineage"]
            proposal_provenance = _proposal_provenance()
            bundle_digest = _required_digest(
                bundle.get("draft_digest"), "bundle digest"
            )
            lineage_digest = _digest(lineage)
            proposal_provenance_digest = _digest(proposal_provenance)
            canonical_bundle = _canonical_json(bundle)
            canonical_lineage = _canonical_json(lineage)
            canonical_provenance = _canonical_json(proposal_provenance)

            existing = candidate_store.get_by_task(conn, task_id)
            revision = 1
            supersedes_candidate_digest: str | None = None
            if existing is not None:
                # Every create replay rebuilds the authoritative sources first.  A
                # byte-identical generation is idempotent; changed task evidence
                # forms a new immutable revision instead of returning a stale row.
                existing_public = self._public_projection(conn, existing)
                if (
                    _canonical_json(existing.get("bundle")) == canonical_bundle
                    and _canonical_json(existing.get("lineage")) == canonical_lineage
                    and _canonical_json(existing.get("proposal_provenance"))
                    == canonical_provenance
                ):
                    public = self._with_skill_package(conn, existing_public)
                    conn.execute("COMMIT")
                    return public

                previous_revision = existing.get("revision")
                if (
                    not isinstance(previous_revision, int)
                    or isinstance(previous_revision, bool)
                    or previous_revision < 1
                ):
                    raise AssetCandidateUnavailableError(
                        "candidate revision is malformed"
                    )
                revision = previous_revision + 1
                supersedes_candidate_digest = _required_digest(
                    existing.get("candidate_digest"),
                    "superseded candidate digest",
                )
                if existing.get("state") == "awaiting_human_review":
                    superseded_at = _now_iso()
                    superseded_event_id = f"asset_candidate_event_{uuid.uuid4().hex}"
                    candidate_store.append_event(
                        conn,
                        {
                            "event_id": superseded_event_id,
                            "candidate_id": existing["id"],
                            "candidate_digest": supersedes_candidate_digest,
                            "bundle_digest": existing["bundle_digest"],
                            "event_type": "candidate_superseded",
                            "from_state": "awaiting_human_review",
                            "to_state": "superseded",
                            "actor_source": "authenticated_task_owner",
                            "signer_display_name": None,
                            "signer_user_id": None,
                            "signer_username": None,
                            "signer_session_hash": None,
                            "message": (
                                "任务证据已变化，旧待审修订被新的内容寻址修订替代"
                            ),
                            "payload": {},
                            "created_at": superseded_at,
                        },
                    )
                    if (
                        candidate_store.cas_supersede(
                            conn,
                            candidate_id=existing["id"],
                            expected_candidate_digest=supersedes_candidate_digest,
                            event_id=superseded_event_id,
                            updated_at=superseded_at,
                        )
                        != 1
                    ):
                        _conflict(
                            "candidate_revision_conflict",
                            "旧候选已被并发决定或替代，请重新读取",
                        )
                elif existing.get("state") not in ("accepted", "rejected"):
                    raise AssetCandidateUnavailableError(
                        "latest candidate revision has an unsupported state"
                    )

            candidate_digest = _candidate_content_digest(
                revision=revision,
                supersedes_candidate_digest=supersedes_candidate_digest,
                bundle_digest=bundle_digest,
                lineage_digest=lineage_digest,
                proposal_provenance_digest=proposal_provenance_digest,
            )
            candidate_id = (
                f"asset_candidate_{candidate_digest.removeprefix('sha256:')[:24]}"
            )
            now = _now_iso()
            candidate_store.insert_candidate(
                conn,
                {
                    "id": candidate_id,
                    "schema_version": SCHEMA_VERSION,
                    "source_task_id": task["id"],
                    "source_conversation_id": conversation["id"],
                    "revision": revision,
                    "supersedes_candidate_digest": supersedes_candidate_digest,
                    "bundle_digest": bundle_digest,
                    "lineage_digest": lineage_digest,
                    "candidate_digest": candidate_digest,
                    "bundle_json": canonical_bundle,
                    "lineage_json": canonical_lineage,
                    "proposal_provenance_json": canonical_provenance,
                    "state": "awaiting_human_review",
                    "data_classification": "internal",
                    "initiated_by_user_id": initiated_by_user_id,
                    "initiated_by_username": actor_username,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            candidate_store.append_event(
                conn,
                {
                    "event_id": f"asset_candidate_event_{uuid.uuid4().hex}",
                    "candidate_id": candidate_id,
                    "candidate_digest": candidate_digest,
                    "bundle_digest": bundle_digest,
                    "event_type": "candidate_created",
                    "from_state": None,
                    "to_state": "awaiting_human_review",
                    "actor_source": "authenticated_task_owner",
                    "signer_display_name": None,
                    "signer_user_id": None,
                    "signer_username": None,
                    "signer_session_hash": None,
                    "message": "系统已从已完成任务形成待人工审核的资产候选",
                    "payload": {},
                    "created_at": now,
                },
            )
            stored = candidate_store.get_by_id(conn, candidate_id)
            if stored is None:
                raise AssetCandidateUnavailableError(
                    "candidate insert could not be read back"
                )
            public = self._with_skill_package(
                conn, self._public_projection(conn, stored)
            )
            conn.execute("COMMIT")
            return public
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def get_for_task(
        self,
        conn: sqlite3.Connection,
        *,
        task_id: str,
        username: str,
    ) -> dict[str, Any]:
        actor_username = _required_text(username, "username", max_length=128)
        try:
            task = self._task_for_owner(conn, task_id, actor_username)
            candidate = candidate_store.get_by_task(conn, task_id)
            if candidate is None:
                raise AssetCandidateNotFoundError(f"任务尚无资产候选：{task_id}")
            public = self._with_skill_package(
                conn, self._public_projection(conn, candidate)
            )
            live_projection = self._verified_projection(conn, task)
            live_bundle = live_projection["bundle"]
            live_lineage = live_projection["lineage"]
            live_bundle_digest = _required_digest(
                live_bundle.get("draft_digest"), "live bundle digest"
            )
            live_lineage_digest = _digest(live_lineage)
            live_proposal_provenance = _proposal_provenance()
            live_proposal_provenance_digest = _digest(live_proposal_provenance)
            live_candidate_digest = _candidate_content_digest(
                revision=candidate["revision"],
                supersedes_candidate_digest=candidate["supersedes_candidate_digest"],
                bundle_digest=live_bundle_digest,
                lineage_digest=live_lineage_digest,
                proposal_provenance_digest=live_proposal_provenance_digest,
            )
            if (
                candidate.get("source_conversation_id")
                != live_projection["conversation"].get("id")
                or _canonical_json(candidate.get("bundle"))
                != _canonical_json(live_bundle)
                or _canonical_json(candidate.get("lineage"))
                != _canonical_json(live_lineage)
                or _canonical_json(candidate.get("proposal_provenance"))
                != _canonical_json(live_proposal_provenance)
                or candidate.get("bundle_digest") != live_bundle_digest
                or candidate.get("lineage_digest") != live_lineage_digest
                or candidate.get("candidate_digest") != live_candidate_digest
            ):
                _conflict(
                    "candidate_source_drift",
                    "任务证据已变化，请自动形成新的候选修订后再决定",
                )
            return public
        except (AssetCandidateNotFoundError, AssetCandidateConflictError):
            raise
        except Exception as exc:
            raise AssetCandidateUnavailableError(
                "asset candidate source cannot be read safely"
            ) from exc

    def decide(
        self,
        conn: sqlite3.Connection,
        *,
        candidate_id: str,
        action: Literal["accept", "reject"],
        expected_candidate_digest: str,
        expected_bundle_digest: str,
        signer_context: SignerContext,
    ) -> dict[str, Any]:
        if action not in ("accept", "reject"):
            raise AssetCandidateUnavailableError("unsupported candidate decision")
        expected_candidate = _required_digest(
            expected_candidate_digest, "expected candidate digest"
        )
        expected_bundle = _required_digest(
            expected_bundle_digest, "expected bundle digest"
        )

        conn.execute("BEGIN IMMEDIATE")
        try:
            owner_context = candidate_store.get_owner_context_by_id(
                conn, candidate_id
            )
            if owner_context is None:
                raise AssetCandidateNotFoundError(
                    f"资产候选不存在：{candidate_id}"
                )
            signer = resolve_signer(conn, signer_context)
            if signer is None or signer.source != AUTHENTICATED_SESSION:
                _conflict(
                    "signer_session_unverifiable",
                    "提交时认证会话已失效，人工决定未写入",
                )
            if signer.username != owner_context.get("initiated_by_username"):
                _conflict(
                    "task_owner_mismatch",
                    "只有该任务的发起工程师可以决定其资产候选",
                )
            task = self._task_for_owner(
                conn, owner_context["source_task_id"], signer.username
            )

            candidate = candidate_store.get_by_id(conn, candidate_id)
            if candidate is None:
                raise AssetCandidateNotFoundError(f"资产候选不存在：{candidate_id}")
            if (
                candidate["candidate_digest"] != expected_candidate
                or candidate["bundle_digest"] != expected_bundle
            ):
                _conflict(
                    "candidate_digest_conflict",
                    "候选内容或证据代际已变化，请重新读取后决定",
                )
            if (
                candidate.get("state") != "awaiting_human_review"
                or candidate.get("decision_event_id") is not None
            ):
                _conflict(
                    "candidate_already_decided",
                    "该候选已经作出人工决定，不能重复或改写",
                )

            live_projection = self._verified_projection(conn, task)
            live_bundle = live_projection["bundle"]
            live_lineage = live_projection["lineage"]
            live_bundle_digest = _required_digest(
                live_bundle.get("draft_digest"), "live bundle digest"
            )
            live_lineage_digest = _digest(live_lineage)
            live_proposal_provenance = _proposal_provenance()
            live_proposal_provenance_digest = _digest(live_proposal_provenance)
            live_candidate_digest = _candidate_content_digest(
                revision=candidate["revision"],
                supersedes_candidate_digest=candidate["supersedes_candidate_digest"],
                bundle_digest=live_bundle_digest,
                lineage_digest=live_lineage_digest,
                proposal_provenance_digest=live_proposal_provenance_digest,
            )
            if (
                candidate.get("source_conversation_id")
                != live_projection["conversation"].get("id")
                or _canonical_json(candidate.get("bundle"))
                != _canonical_json(live_bundle)
                or _canonical_json(candidate.get("lineage"))
                != _canonical_json(live_lineage)
                or _canonical_json(candidate.get("proposal_provenance"))
                != _canonical_json(live_proposal_provenance)
                or candidate.get("bundle_digest") != live_bundle_digest
                or candidate.get("lineage_digest") != live_lineage_digest
                or candidate.get("candidate_digest") != live_candidate_digest
            ):
                _conflict(
                    "candidate_source_drift",
                    "任务、执行包、产物或签发证据已变化，原候选不能继续决定",
                )

            now = _now_iso()
            event_id = f"asset_candidate_event_{uuid.uuid4().hex}"
            to_state = "accepted" if action == "accept" else "rejected"
            candidate_store.append_event(
                conn,
                {
                    "event_id": event_id,
                    "candidate_id": candidate["id"],
                    "candidate_digest": candidate["candidate_digest"],
                    "bundle_digest": candidate["bundle_digest"],
                    "event_type": (
                        "candidate_accepted"
                        if action == "accept"
                        else "candidate_rejected"
                    ),
                    "from_state": "awaiting_human_review",
                    "to_state": to_state,
                    "actor_source": AUTHENTICATED_SESSION,
                    "signer_display_name": signer.confirmed_by,
                    "signer_user_id": signer.user_id,
                    "signer_username": signer.username,
                    "signer_session_hash": signer.session_hash,
                    "message": (
                        "工程师接受该精确资产候选修订并授权生成隔离待审 Skill Package；尚未包级批准、注册或发布"
                        if action == "accept"
                        else "工程师决定不保留该精确资产候选修订"
                    ),
                    "payload": {},
                    "created_at": now,
                },
            )
            updated = candidate_store.cas_decision(
                conn,
                candidate_id=candidate["id"],
                expected_candidate_digest=expected_candidate,
                event_id=event_id,
                state=to_state,
                updated_at=now,
            )
            if updated != 1:
                _conflict(
                    "candidate_already_decided",
                    "该候选已被并发决定，当前决定未写入",
                )
            final = candidate_store.get_by_id(conn, candidate["id"])
            if final is None:
                raise AssetCandidateUnavailableError(
                    "decided candidate could not be read back"
                )
            public = self._public_projection(conn, final)
            if action == "accept":
                if self._materializer is None:
                    raise AssetCandidateUnavailableError(
                        "candidate materializer is unavailable"
                    )
                accepted_event = _verified_terminal_event(conn, final)
                try:
                    self._materializer.materialize_accepted(
                        conn,
                        candidate_public=public,
                        accepted_event=accepted_event,
                    )
                except Exception as exc:
                    raise AssetCandidateUnavailableError(
                        "accepted candidate could not be materialized safely"
                    ) from exc
            public = self._with_skill_package(conn, public)
            conn.execute("COMMIT")
            return public
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def _verified_projection(
        self, conn: sqlite3.Connection, task: Mapping[str, Any]
    ) -> dict[str, Any]:
        snapshot_view = self._agent_registry.snapshot_view()
        snapshot = snapshot_view.package_snapshot(task["agent_id"])
        if snapshot is None:
            _conflict(
                "agent_package_unavailable",
                "任务对应的不可变 Agent Package 已不可用，不能形成资产候选",
            )
        try:
            manifest = snapshot.manifest
        except Exception as exc:
            raise AssetCandidateUnavailableError(
                "agent package manifest cannot be read safely"
            ) from exc
        execution_snapshot = self._validate_package_binding(
            conn, task, manifest, snapshot.digest
        )

        conversation, segment_messages = self._work_case_segment(conn, task)
        segment_user_file_ids = {
            file_id
            for message in segment_messages
            if message.get("role") == "user"
            for file_id in (message.get("file_ids") or [])
            if isinstance(file_id, str)
        }
        input_files = self._file_lineage(
            conn,
            task,
            task.get("input_file_ids"),
            expected_output=False,
            segment_user_file_ids=segment_user_file_ids,
            snapshot_view=snapshot_view,
        )
        output_files = self._file_lineage(
            conn,
            task,
            task.get("output_file_ids"),
            expected_output=True,
            segment_user_file_ids=segment_user_file_ids,
            snapshot_view=snapshot_view,
        )
        signoff = self._signoff_lineage(
            conn,
            task,
            manifest,
            execution_evidence_digest=execution_snapshot["execution_evidence_digest"],
        )
        generalization = self._generalization_proposal(
            task=task,
            manifest=manifest,
            package_digest=snapshot.digest,
            segment_messages=segment_messages,
            input_files=input_files,
            output_files=output_files,
            signoff=signoff,
        )
        resolved_conversation = {
            "id": conversation["id"],
            "agent_id": conversation["agent_id"],
            "status": conversation["status"],
            "messages": segment_messages,
        }
        try:
            bundle = self._builder.preview(
                conversation=resolved_conversation,
                generalization=generalization,
            )
        except AssetDraftSourceError as exc:
            _conflict("work_case_unverifiable", f"工作段不能形成 Work Case：{exc}")
        except AssetDraftInputError as exc:
            raise AssetCandidateUnavailableError(
                "automatic generalization violated the draft contract"
            ) from exc
        except AssetDraftProjectionError as exc:
            raise AssetCandidateUnavailableError(
                "work case projection is unavailable"
            ) from exc
        if (
            bundle.get("validation", {}).get("state") != "ready_for_human_review"
            or bundle.get("review", {}).get("ready") is not True
            or bundle.get("validation", {}).get("blocking_count") != 0
        ):
            _conflict(
                "generalization_not_ready",
                "自动归纳仍有语义缺口，请回到主对话补充后再试",
            )

        lineage = self._lineage(
            task=task,
            package_digest=snapshot.digest,
            bundle=bundle,
            segment_messages=segment_messages,
            input_files=input_files,
            output_files=output_files,
            execution_snapshot=execution_snapshot,
            signoff=signoff,
        )
        return {
            "bundle": bundle,
            "conversation": conversation,
            "lineage": lineage,
        }

    def _task_for_owner(
        self, conn: sqlite3.Connection, task_id: str, username: str
    ) -> dict[str, Any]:
        try:
            task = repos.get_task(conn, task_id)
        except Exception as exc:
            raise AssetCandidateUnavailableError(
                "task source cannot be decoded"
            ) from exc
        if task is None:
            raise AssetCandidateNotFoundError(f"任务不存在：{task_id}")
        owner = task.get("created_by_username")
        if owner is None:
            _conflict(
                "task_owner_unverifiable",
                "存量任务缺少不可变发起人身份，不能猜测资产所有者",
            )
        if owner != username:
            _conflict(
                "task_owner_mismatch",
                "只有任务发起工程师可以形成或查看其资产候选",
            )
        if task.get("status") != "completed":
            _conflict(
                "task_not_completed", "只有权威状态为 completed 的任务才能形成候选"
            )
        if task.get("origin") != "user":
            _conflict("task_origin_not_user", "评测或未知来源任务不能沉淀为工程资产")
        if task.get("data_classification") != "internal":
            _conflict(
                "classification_not_eligible",
                "首版资产候选只接收已明确标为 internal 的任务",
            )
        return task

    def _validate_package_binding(
        self,
        conn: sqlite3.Connection,
        task: Mapping[str, Any],
        manifest: Mapping[str, Any],
        snapshot_digest: Any,
    ) -> dict[str, Any]:
        current_digest = _required_raw_digest(
            snapshot_digest, "current package snapshot digest"
        )
        metadata = task.get("metadata")
        if not isinstance(metadata, Mapping):
            raise AssetCandidateUnavailableError("task metadata is not an object")
        pinned_digest = metadata.get("package_snapshot_digest")
        if not _is_raw_digest(pinned_digest):
            _conflict(
                "package_digest_unverifiable",
                "任务没有可核验的 Agent Package 摘要，不能推断执行代际",
            )
        if pinned_digest != current_digest:
            _conflict(
                "package_digest_drift",
                "任务执行包摘要与当前不可变快照不一致，不能形成候选",
            )
        if manifest.get("id") != task.get("agent_id") or manifest.get(
            "version"
        ) != task.get("agent_version"):
            _conflict(
                "package_digest_drift",
                "任务 Agent 版本与摘要绑定的 Package Snapshot 不一致",
            )

        rows = conn.execute(
            """
            SELECT event_id, event_type, payload_json, created_at
            FROM task_events
            WHERE task_id = ? AND event_type = 'validation_started'
            ORDER BY id ASC
            """,
            (task["id"],),
        ).fetchall()
        if len(rows) != 1:
            _conflict(
                "package_execution_unverifiable",
                "任务缺少唯一的执行时 Package Snapshot 校验事件",
            )
        row = rows[0]
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise AssetCandidateUnavailableError(
                "validation_started payload cannot be decoded"
            ) from exc
        if not isinstance(payload, Mapping):
            raise AssetCandidateUnavailableError(
                "validation_started payload is not an object"
            )
        executed_digest = payload.get("package_snapshot_digest")
        if (
            payload.get("package_snapshot_contract") != SNAPSHOT_CONTRACT
            or not _is_raw_digest(executed_digest)
            or executed_digest != pinned_digest
            or executed_digest != current_digest
        ):
            _conflict(
                "package_execution_digest_drift",
                "执行时、任务钉扎与当前 Package Snapshot 摘要不一致",
            )
        executed_input_file_ids = payload.get("input_file_ids")
        live_input_file_ids = task.get("input_file_ids")
        if (
            not _bounded_unique_text_list(executed_input_file_ids, _MAX_FILE_REFERENCES)
            or not _bounded_unique_text_list(live_input_file_ids, _MAX_FILE_REFERENCES)
            or executed_input_file_ids != live_input_file_ids
        ):
            _conflict(
                "execution_input_lineage_drift",
                "执行开始时的附件引用与当前任务血缘不一致",
            )
        live_input_evidence = input_files_evidence(conn, live_input_file_ids)
        executed_input_files_digest = payload.get("input_files_digest")
        if (
            not _is_prefixed_digest(executed_input_files_digest)
            or executed_input_files_digest != live_input_evidence["digest"]
        ):
            _conflict(
                "execution_input_lineage_drift",
                "执行开始时的附件摘要、生产任务或密级与当前证据不一致",
            )
        live_task_inputs_digest = _digest(task.get("inputs"))
        executed_task_inputs_digest = payload.get("task_inputs_digest")
        executed_evidence_digest = payload.get("execution_evidence_digest")
        expected_evidence_digest = _digest(
            {
                "package_snapshot_digest": executed_digest,
                "task_inputs_digest": live_task_inputs_digest,
                "input_file_ids": executed_input_file_ids,
                "input_files_digest": executed_input_files_digest,
            }
        )
        if (
            not _is_prefixed_digest(executed_task_inputs_digest)
            or executed_task_inputs_digest != live_task_inputs_digest
            or not _is_prefixed_digest(executed_evidence_digest)
            or executed_evidence_digest != expected_evidence_digest
        ):
            _conflict(
                "execution_input_lineage_drift",
                "执行开始时的任务参数与完成证据摘要不一致",
            )
        event_basis = {
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "created_at": row["created_at"],
            "package_snapshot_contract": SNAPSHOT_CONTRACT,
            "package_snapshot_digest": executed_digest,
            "input_file_ids": executed_input_file_ids,
            "input_files_digest": executed_input_files_digest,
            "task_inputs_digest": executed_task_inputs_digest,
            "execution_evidence_digest": executed_evidence_digest,
        }
        return {
            "event_id": row["event_id"],
            "event_digest": _digest(event_basis),
            "package_snapshot_contract": SNAPSHOT_CONTRACT,
            "package_snapshot_digest": executed_digest,
            "input_file_ids_digest": _digest(executed_input_file_ids),
            "input_files_digest": executed_input_files_digest,
            "task_inputs_digest": executed_task_inputs_digest,
            "execution_evidence_digest": executed_evidence_digest,
        }

    def _work_case_segment(
        self, conn: sqlite3.Connection, task: Mapping[str, Any]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        conversation_id = task.get("conversation_id")
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            _conflict(
                "conversation_unverifiable",
                "任务没有可核验的主对话血缘，不能形成 Work Case",
            )
        conversation = repos.get_conversation(conn, conversation_id)
        if conversation is None:
            _conflict(
                "conversation_unverifiable",
                "任务归属的主对话不存在，不能形成 Work Case",
            )
        created_at = _required_text(task.get("created_at"), "task.created_at")
        verified_batch_task_ids = _verified_batch_task_ids(
            conn,
            conversation_id=conversation_id,
            task=task,
        )
        previous_rows = conn.execute(
            """
            SELECT id, created_at, metadata_json FROM tasks
            WHERE conversation_id = ? AND id != ? AND created_at < ?
            ORDER BY created_at DESC, id DESC
            """,
            (conversation_id, task["id"], created_at),
        ).fetchall()
        prior_task_boundaries: list[Any] = []
        for row in previous_rows:
            if row["id"] in verified_batch_task_ids:
                # Only a complete, owner-bound batch with one unique member for
                # every declared index shares the segment preceding the batch.
                continue
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except (TypeError, json.JSONDecodeError) as exc:
                raise AssetCandidateUnavailableError(
                    "prior task metadata cannot be decoded"
                ) from exc
            if not isinstance(metadata, Mapping):
                raise AssetCandidateUnavailableError(
                    "prior task metadata is not an object"
                )
            prior_task_boundaries.append(row["created_at"])

        messages = repos.list_messages(conn, conversation_id)
        boundary_values = list(prior_task_boundaries)
        if conversation.get("agent_id") == "guide_agent":
            boundary_values.extend(
                message.get("created_at")
                for message in messages
                if created_at_or_before(message.get("created_at"), created_at)
                and (
                    is_guide_refuse_delivery(message)
                    or is_canonical_qa_delivery(message)
                )
            )
        lower_bound = latest_valid_iso(boundary_values)
        segment = [
            message
            for message in messages
            if created_at_or_before(message.get("created_at"), created_at)
            and (
                lower_bound is None
                or created_strictly_after(message.get("created_at"), lower_bound)
            )
        ]
        if not any(message.get("role") == "user" for message in segment):
            _conflict(
                "work_case_unverifiable",
                "当前任务工作段没有已保存的用户消息，不能形成 Work Case",
            )
        return conversation, segment

    def _file_lineage(
        self,
        conn: sqlite3.Connection,
        task: Mapping[str, Any],
        raw_file_ids: Any,
        *,
        expected_output: bool,
        segment_user_file_ids: set[str],
        snapshot_view: Any,
    ) -> list[dict[str, Any]]:
        if not isinstance(raw_file_ids, list) or any(
            not isinstance(file_id, str) or not file_id.strip()
            for file_id in raw_file_ids
        ):
            raise AssetCandidateUnavailableError("task file references are malformed")
        if len(raw_file_ids) > _MAX_FILE_REFERENCES or len(set(raw_file_ids)) != len(
            raw_file_ids
        ):
            _conflict(
                "artifact_lineage_unverifiable",
                "任务附件引用超出候选账本上限或包含重复项",
            )
        projected: list[dict[str, Any]] = []
        for file_id in raw_file_ids:
            record = repos.get_file(conn, file_id)
            if record is None:
                _conflict(
                    "artifact_lineage_unverifiable",
                    "任务引用的工程产物记录不存在，不能形成候选",
                )
            kind = record.get("kind")
            if expected_output:
                if kind != "output" or record.get("task_id") != task.get("id"):
                    _conflict(
                        "artifact_lineage_unverifiable",
                        "输出产物没有归属当前已完成任务",
                    )
                source_kind = "current_task_output"
                producer_task_id: str | None = task["id"]
            elif kind == "input":
                if file_id not in segment_user_file_ids:
                    _conflict(
                        "work_segment_attachment_mismatch",
                        "任务输入附件未出现在当前权威工作段的工程师消息中",
                    )
                task_owner = _required_text(
                    task.get("created_by_username"), "task owner", max_length=128
                )
                if (
                    repos.file_is_owned_by_username(conn, file_id, task_owner)
                    is not True
                ):
                    _conflict(
                        "work_segment_attachment_owner_mismatch",
                        "直接上传附件缺少与任务责任人一致的认证 username 血缘",
                    )
                source_kind = "work_segment_upload"
                producer_task_id = None
            elif kind == "output":
                producer_task_id = self._validate_upstream_output_input(
                    conn,
                    task=task,
                    file_id=file_id,
                    record=record,
                    snapshot_view=snapshot_view,
                )
                source_kind = "upstream_task_output"
            else:
                _conflict(
                    "artifact_lineage_unverifiable",
                    "输入附件类型不受资产候选账本支持",
                )
            if record.get("classification") != "internal":
                _conflict(
                    "classification_not_eligible",
                    "任务附件密级与 internal 候选边界不一致",
                )
            sha256 = _required_raw_digest(record.get("sha256"), "file sha256")
            size_bytes = record.get("size_bytes")
            if (
                not isinstance(size_bytes, int)
                or isinstance(size_bytes, bool)
                or size_bytes < 0
            ):
                raise AssetCandidateUnavailableError("file size is malformed")
            projected.append(
                {
                    "file_id": file_id,
                    "kind": kind,
                    "sha256": sha256,
                    "size_bytes": size_bytes,
                    "classification": "internal",
                    "source_kind": source_kind,
                    "producer_task_id": producer_task_id,
                }
            )
        return projected

    def _validate_upstream_output_input(
        self,
        conn: sqlite3.Connection,
        *,
        task: Mapping[str, Any],
        file_id: str,
        record: Mapping[str, Any],
        snapshot_view: Any,
    ) -> str:
        depends_on = task.get("depends_on")
        if not _bounded_unique_text_list(depends_on, 32):
            _conflict(
                "upstream_input_lineage_unverifiable",
                "任务依赖声明缺失或畸形，不能接收上游产物作为候选输入",
            )
        producer_task_id = record.get("task_id")
        if not isinstance(producer_task_id, str) or producer_task_id not in depends_on:
            _conflict(
                "upstream_input_lineage_unverifiable",
                "输入产物的生产任务不在当前任务的不可变依赖声明中",
            )

        binding = task.get("input_binding")
        if binding is not None:
            if not isinstance(binding, Mapping):
                raise AssetCandidateUnavailableError(
                    "task input binding is not an object"
                )
            from_tasks = binding.get("from_tasks")
            if not _bounded_unique_text_list(from_tasks, 32):
                raise AssetCandidateUnavailableError(
                    "task input binding sources are malformed"
                )
            if from_tasks and producer_task_id not in from_tasks:
                _conflict(
                    "upstream_input_lineage_unverifiable",
                    "输入产物的生产任务被 input_binding 明确排除",
                )

        owner = _required_text(
            task.get("created_by_username"), "task owner", max_length=128
        )
        upstream = self._task_for_owner(conn, producer_task_id, owner)
        if (
            upstream.get("conversation_id") != task.get("conversation_id")
            or not created_at_or_before(
                upstream.get("created_at"), task.get("created_at")
            )
            or file_id not in (upstream.get("output_file_ids") or [])
        ):
            _conflict(
                "upstream_input_lineage_unverifiable",
                "上游产物不属于同一会话内已完成且早于当前任务的声明依赖",
            )

        upstream_snapshot = snapshot_view.package_snapshot(upstream["agent_id"])
        if upstream_snapshot is None:
            _conflict(
                "upstream_input_lineage_unverifiable",
                "上游任务的不可变 Agent Package 已不可用",
            )
        upstream_manifest = upstream_snapshot.manifest
        upstream_execution_snapshot = self._validate_package_binding(
            conn, upstream, upstream_manifest, upstream_snapshot.digest
        )
        self._signoff_lineage(
            conn,
            upstream,
            upstream_manifest,
            execution_evidence_digest=upstream_execution_snapshot[
                "execution_evidence_digest"
            ],
        )

        rows = conn.execute(
            """
            SELECT payload_json
            FROM task_events
            WHERE task_id = ? AND event_type = 'agent_log'
            ORDER BY id ASC
            """,
            (task["id"],),
        ).fetchall()
        resolution_payloads: list[Mapping[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, json.JSONDecodeError) as exc:
                raise AssetCandidateUnavailableError(
                    "dependency resolution event cannot be decoded"
                ) from exc
            if (
                isinstance(payload, Mapping)
                and payload.get("workflow_event_type") == "dependency_resolved"
            ):
                resolution_payloads.append(payload)
        if len(resolution_payloads) != 1:
            _conflict(
                "upstream_input_lineage_unverifiable",
                "任务缺少唯一 dependency_resolved 事件",
            )
        resolution = resolution_payloads[0]
        piped_file_ids = resolution.get("piped_file_ids")
        if (
            resolution.get("upstream_task_ids") != depends_on
            or not _bounded_unique_text_list(piped_file_ids, _MAX_FILE_REFERENCES)
            or resolution.get("piped_file_count") != len(piped_file_ids)
        ):
            _conflict(
                "upstream_input_lineage_unverifiable",
                "依赖解析事件没有绑定精确的上游任务与产物集合",
            )
        live_upstream_inputs: list[str] = []
        for input_file_id in task.get("input_file_ids") or []:
            input_record = repos.get_file(conn, input_file_id)
            if input_record is not None and input_record.get("kind") == "output":
                live_upstream_inputs.append(input_file_id)
        if piped_file_ids != live_upstream_inputs or file_id not in piped_file_ids:
            _conflict(
                "upstream_input_lineage_unverifiable",
                "依赖解析事件与实际执行的上游产物引用不一致",
            )
        return producer_task_id

    def _signoff_lineage(
        self,
        conn: sqlite3.Connection,
        task: Mapping[str, Any],
        manifest: Mapping[str, Any],
        *,
        execution_evidence_digest: str,
    ) -> dict[str, Any]:
        expected_execution_evidence_digest = _required_digest(
            execution_evidence_digest, "execution evidence digest"
        )
        workflow = manifest.get("workflow")
        model = manifest.get("model")
        if not isinstance(workflow, Mapping) or not isinstance(model, Mapping):
            raise AssetCandidateUnavailableError("agent signoff policy is malformed")
        requires_review = workflow.get("requires_human_review")
        if requires_review is True:
            row = conn.execute(
                """
                SELECT event_id, event_type, payload_json, created_at
                FROM task_events
                WHERE task_id = ? AND event_type = 'review_approved'
                ORDER BY id DESC LIMIT 1
                """,
                (task["id"],),
            ).fetchone()
            if row is None:
                _conflict(
                    "task_signoff_unverifiable",
                    "任务虽为 completed，但缺少人工 review_approved 证据",
                )
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, json.JSONDecodeError) as exc:
                raise AssetCandidateUnavailableError(
                    "review_approved payload cannot be decoded"
                ) from exc
            if not isinstance(payload, Mapping):
                raise AssetCandidateUnavailableError(
                    "review_approved payload is not an object"
                )
            signer_username = payload.get("reviewer_username")
            if not isinstance(signer_username, str) or not signer_username.strip():
                _conflict(
                    "task_signoff_unverifiable",
                    "任务人工签发事件缺少稳定 username，不能用显示名猜测签发者",
                )
            if (
                payload.get("execution_evidence_digest")
                != expected_execution_evidence_digest
            ):
                _conflict(
                    "task_signoff_unverifiable",
                    "任务人工签发没有绑定执行开始时的同一输入证据",
                )
            event_basis = {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "created_at": row["created_at"],
                "signer_username": signer_username,
                "execution_evidence_digest": expected_execution_evidence_digest,
            }
            return {
                "required": True,
                "kind": "human_review_approved",
                "event_id": row["event_id"],
                "event_digest": _digest(event_basis),
                "signer_username": signer_username,
                "execution_evidence_digest": expected_execution_evidence_digest,
            }
        if requires_review is False and model.get("profile") == "none":
            rows = conn.execute(
                """
                SELECT event_id, event_type, payload_json, created_at
                FROM task_events
                WHERE task_id = ? AND event_type = 'task_completed'
                ORDER BY id ASC
                """,
                (task["id"],),
            ).fetchall()
            if len(rows) != 1:
                _conflict(
                    "task_completion_unverifiable",
                    "确定性任务缺少唯一 task_completed 事件，不能只凭状态声称已完成",
                )
            row = rows[0]
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, json.JSONDecodeError) as exc:
                raise AssetCandidateUnavailableError(
                    "task_completed payload cannot be decoded"
                ) from exc
            if (
                not isinstance(payload, Mapping)
                or payload.get("execution_evidence_digest")
                != expected_execution_evidence_digest
            ):
                _conflict(
                    "task_completion_unverifiable",
                    "确定性完成事件没有绑定执行开始时的同一输入证据",
                )
            event_basis = {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "created_at": row["created_at"],
                "execution_evidence_digest": expected_execution_evidence_digest,
            }
            return {
                "required": False,
                "kind": "deterministic_no_review",
                "event_id": row["event_id"],
                "event_digest": _digest(event_basis),
                "signer_username": None,
                "execution_evidence_digest": expected_execution_evidence_digest,
            }
        _conflict(
            "task_signoff_unverifiable",
            "任务缺少可证明的人工签发或显式确定性免审边界",
        )

    def _generalization_proposal(
        self,
        *,
        task: Mapping[str, Any],
        manifest: Mapping[str, Any],
        package_digest: str,
        segment_messages: list[dict[str, Any]],
        input_files: list[dict[str, Any]],
        output_files: list[dict[str, Any]],
        signoff: Mapping[str, Any],
    ) -> dict[str, Any]:
        name = _required_text(manifest.get("name"), "agent.name", max_length=80)
        summary = _required_text(
            manifest.get("summary"), "agent.summary", max_length=300
        )
        task_name = _required_text(task.get("name"), "task.name", max_length=300)
        if not isinstance(segment_messages, list) or not segment_messages:
            raise AssetCandidateUnavailableError("work case segment is empty")
        user_turn_count = sum(
            message.get("role") == "user" for message in segment_messages
        )
        assistant_turn_count = sum(
            message.get("role") == "assistant" for message in segment_messages
        )
        segment_attachment_count = sum(
            len(message.get("file_ids") or []) for message in segment_messages
        )
        segment_digest = _digest(segment_messages)
        input_contract = manifest.get("input")
        output_contract = manifest.get("output")
        workflow = manifest.get("workflow")
        if (
            not isinstance(input_contract, Mapping)
            or not isinstance(output_contract, Mapping)
            or not isinstance(workflow, Mapping)
        ):
            raise AssetCandidateUnavailableError("agent I/O contract is malformed")

        input_type = input_contract.get("type")
        if input_type == "params":
            raw_inputs = task.get("inputs")
            if not isinstance(raw_inputs, Mapping):
                raise AssetCandidateUnavailableError("task inputs are not an object")
            shaped_inputs = sorted(
                (
                    _required_text(key, "task input key", max_length=160),
                    _value_shape(raw_inputs[key]),
                )
                for key in raw_inputs.keys()
            )
            inputs = [
                f"结构化输入：{key}（{shape}）" for key, shape in shaped_inputs[:18]
            ] or ["符合已锁定 Agent Package 输入契约的结构化参数"]
        elif input_type == "file_upload":
            extensions = input_contract.get("allowed_extensions")
            if not isinstance(extensions, list) or not extensions:
                raise AssetCandidateUnavailableError(
                    "file-upload Agent has no extension contract"
                )
            inputs = [
                "工程附件（允许类型："
                + "、".join(
                    _required_text(ext, "allowed extension", max_length=16)
                    for ext in extensions[:16]
                )
                + "）"
            ]
        elif input_type == "none":
            inputs = ["无需额外工程输入；仅使用已锁定包内规则"]
        else:
            raise AssetCandidateUnavailableError("unsupported Agent input type")
        if input_files and not any("附件" in item for item in inputs):
            inputs.append("按文件摘要绑定的工程附件")
        if segment_attachment_count > 0:
            inputs.append(
                f"当前工作段中由工程师提交的附件引用（共 {segment_attachment_count} 个）"
            )

        raw_formats = output_contract.get("formats") or []
        if not isinstance(raw_formats, list):
            raise AssetCandidateUnavailableError("agent output formats are malformed")
        formats = [
            _required_text(value, "output format", max_length=16)
            for value in raw_formats[:16]
        ]
        outputs = [
            "任务产物（" + "、".join(formats) + "，按摘要核验）"
            if formats
            else "已完成任务的结构化结果与证据记录"
        ]
        if output_files:
            outputs.append(f"{len(output_files)} 份已登记产物的 SHA-256 血缘")

        requires_review = workflow.get("requires_human_review")
        steps = [
            (
                f"从同一主对话工作段的 {user_turn_count} 个工程师回合确认"
                f"“{task_name}”的目标、材料与停止条件"
            ),
            (
                f"按已实际执行的锁定版本 {task['agent_id']}@{task['agent_version']} "
                f"处理该类任务（本案例含 {assistant_turn_count} 个系统协作回合）"
            ),
            "核验任务终态、产物摘要与事件证据对应同一任务代际",
            (
                "由具名工程师审核工程结果并完成签发"
                if requires_review is True
                else "由工程师核对结果是否满足当前任务目标"
            ),
        ]
        evidence = [
            f"保留当前工作段摘要 {segment_digest}",
            f"保留 Agent Package 摘要 {package_digest}",
            "保留 completed 任务终态、完成时间与任务内容摘要",
            "保留输入和输出文件的 SHA-256 引用（如有）",
            (
                f"保留 review_approved 人工签发事件 {signoff.get('event_id')}"
                if requires_review is True
                else (
                    "保留 model.profile=none、requires_human_review=false 与实际 "
                    f"task_completed 事件 {signoff.get('event_id')}"
                )
            ),
        ]
        decisions = [
            "是否把该单案例方法接受为可复用资产候选，只能由任务发起工程师决定",
            "候选用于新工程语境前，工程师必须重新判断适用性与证据充分性",
        ]
        raw_limitations = manifest.get("limitations")
        if not isinstance(raw_limitations, list) or not raw_limitations:
            raise AssetCandidateUnavailableError("agent limitations are malformed")
        limitations = [
            _required_text(value, "agent limitation", max_length=1000)
            for value in raw_limitations[:17]
        ]
        limitations.extend(
            [
                "当前候选仅由一个已完成任务归纳，尚未形成 Workflow 或可部署 Agent",
                "接受候选只授权生成隔离待审 SKILL.md；不等于包级批准、注册、发布或晋级",
            ]
        )
        return {
            "title": f"{task_name}：可复用方法"[:160],
            "trigger": (
                f"当工程师需要再次完成“{task_name}”，且输入满足 {name} 的锁定包契约时："
                f"{summary}"
            )[:2000],
            "desired_outcome": (
                f"稳定复现“{task_name}”这类任务的已验证完成路径，并保留可由工程师"
                "核对的工作段、执行、产物与签发证据血缘"
            )[:2000],
            "inputs": inputs[:20],
            "outputs": outputs[:20],
            "steps": steps,
            "evidence_requirements": evidence,
            "human_decision_points": decisions,
            "limitations": limitations[:20],
        }

    def _lineage(
        self,
        *,
        task: Mapping[str, Any],
        package_digest: str,
        bundle: Mapping[str, Any],
        segment_messages: list[dict[str, Any]],
        input_files: list[dict[str, Any]],
        output_files: list[dict[str, Any]],
        execution_snapshot: dict[str, Any],
        signoff: dict[str, Any],
    ) -> dict[str, Any]:
        inputs_digest = _digest(task.get("inputs"))
        task_basis = {
            "task_id": task["id"],
            "initiated_by_username": _required_text(
                task.get("created_by_username"), "task.created_by_username"
            ),
            "agent_id": task["agent_id"],
            "agent_version": task["agent_version"],
            "agent_package_digest": package_digest,
            "origin": task["origin"],
            "terminal_status": task["status"],
            "created_at": task["created_at"],
            "finished_at": task["finished_at"],
            "data_classification": task["data_classification"],
            "inputs_digest": inputs_digest,
            "input_files": input_files,
            "output_files": output_files,
            "execution_snapshot": execution_snapshot,
            "signoff": signoff,
        }
        work_case = bundle.get("work_case")
        if not isinstance(work_case, Mapping):
            raise AssetCandidateUnavailableError("draft work case is malformed")
        return {
            "schema_version": LINEAGE_SCHEMA_VERSION,
            "task": {
                "task_id": task["id"],
                "initiated_by_username": _required_text(
                    task.get("created_by_username"), "task.created_by_username"
                ),
                "agent_id": task["agent_id"],
                "agent_version": task["agent_version"],
                "agent_package_digest": package_digest,
                "origin": "user",
                "terminal_status": "completed",
                "finished_at": _required_text(
                    task.get("finished_at"), "task.finished_at"
                ),
                "data_classification": "internal",
                "inputs_digest": inputs_digest,
                "task_snapshot_digest": _digest(task_basis),
            },
            "conversation": {
                "conversation_id": task["conversation_id"],
                "work_case_source_revision": _required_digest(
                    work_case.get("source_revision"), "work case source revision"
                ),
                "segment_message_count": len(segment_messages),
                "segment_user_message_count": sum(
                    message.get("role") == "user" for message in segment_messages
                ),
            },
            "input_files": input_files,
            "output_files": output_files,
            "execution_snapshot": execution_snapshot,
            "signoff": signoff,
        }

    def _public_projection(
        self, conn: sqlite3.Connection, candidate: Mapping[str, Any]
    ) -> dict[str, Any]:
        bundle = candidate.get("bundle")
        lineage = candidate.get("lineage")
        provenance = candidate.get("proposal_provenance")
        if (
            not isinstance(bundle, dict)
            or not isinstance(lineage, dict)
            or not isinstance(provenance, dict)
        ):
            raise AssetCandidateUnavailableError("candidate content is malformed")
        revision = candidate.get("revision")
        supersedes = candidate.get("supersedes_candidate_digest")
        if (
            not isinstance(revision, int)
            or isinstance(revision, bool)
            or revision < 1
            or (revision == 1 and supersedes is not None)
            or (revision > 1 and not _is_prefixed_digest(supersedes))
        ):
            raise AssetCandidateUnavailableError(
                "candidate revision lineage is malformed"
            )
        stored_bundle_digest = _required_digest(
            candidate.get("bundle_digest"), "stored bundle digest"
        )
        stored_lineage_digest = _required_digest(
            candidate.get("lineage_digest"), "stored lineage digest"
        )
        stored_proposal_provenance_digest = _digest(provenance)
        stored_candidate_digest = _required_digest(
            candidate.get("candidate_digest"), "stored candidate digest"
        )
        bundle_without_digest = dict(bundle)
        bundle_without_digest.pop("draft_digest", None)
        if (
            _required_digest(bundle.get("draft_digest"), "draft bundle digest")
            != stored_bundle_digest
            or _digest(bundle_without_digest) != stored_bundle_digest
            or _digest(lineage) != stored_lineage_digest
            or _candidate_content_digest(
                revision=revision,
                supersedes_candidate_digest=supersedes,
                bundle_digest=stored_bundle_digest,
                lineage_digest=stored_lineage_digest,
                proposal_provenance_digest=stored_proposal_provenance_digest,
            )
            != stored_candidate_digest
            or candidate.get("id")
            != f"asset_candidate_{stored_candidate_digest.removeprefix('sha256:')[:24]}"
        ):
            raise AssetCandidateUnavailableError(
                "candidate stored content does not match its address digests"
            )
        _verify_candidate_revision_chain(conn, candidate)
        task_lineage = lineage.get("task")
        if not isinstance(task_lineage, Mapping):
            raise AssetCandidateUnavailableError("candidate task lineage is malformed")
        lineage_owner = _required_text(
            task_lineage.get("initiated_by_username"),
            "candidate lineage task owner",
            max_length=128,
        )
        stored_owner = _required_text(
            candidate.get("initiated_by_username"),
            "candidate stored task owner",
            max_length=128,
        )
        if lineage_owner != stored_owner:
            raise AssetCandidateUnavailableError(
                "candidate stored owner does not match its task lineage"
            )

        state = candidate.get("state")
        decision_event_id = candidate.get("decision_event_id")
        decision: dict[str, Any] | None = None
        if state == "awaiting_human_review":
            if decision_event_id is not None:
                raise AssetCandidateUnavailableError(
                    "awaiting candidate has a decision pointer"
                )
            formed_state = "candidate_revision"
        elif state in ("accepted", "rejected"):
            if not isinstance(decision_event_id, str) or not decision_event_id:
                raise AssetCandidateUnavailableError(
                    "terminal candidate has no decision pointer"
                )
            event = _verified_terminal_event(conn, candidate)
            decision = {
                "action": "accept" if state == "accepted" else "reject",
                "decided_by": event["signer_display_name"],
                "decided_by_username": event["signer_username"],
                "signer_source": event["actor_source"],
                "signer_session_bound": True,
                "created_at": event["created_at"],
            }
            formed_state = (
                "approved_revision" if state == "accepted" else "rejected_revision"
            )
        else:
            raise AssetCandidateUnavailableError("candidate state is unsupported")

        public = {
            "schema_version": SCHEMA_VERSION,
            "id": candidate["id"],
            "revision": revision,
            "supersedes_candidate_digest": supersedes,
            "candidate_digest": candidate["candidate_digest"],
            "bundle_digest": candidate["bundle_digest"],
            "lineage_digest": candidate["lineage_digest"],
            "state": state,
            "source": {
                "task_id": task_lineage["task_id"],
                "initiated_by_username": lineage_owner,
                "conversation_id": candidate["source_conversation_id"],
                "task_status": task_lineage["terminal_status"],
                "agent_id": task_lineage["agent_id"],
                "agent_version": task_lineage["agent_version"],
                "agent_package_digest": task_lineage["agent_package_digest"],
                "finished_at": task_lineage["finished_at"],
            },
            "bundle": bundle,
            "lineage": lineage,
            "proposal_provenance": provenance,
            "asset_map": {
                "task_pattern": {
                    "state": formed_state,
                    "digest": bundle["task_pattern"]["content_digest"],
                },
                "skill": {
                    "state": formed_state,
                    "digest": bundle["skill"]["content_digest"],
                },
                "workflow": {
                    "state": "not_formed",
                    "digest": None,
                    "gate": "仅当需要组合一个或多个已批准 Skill Revision 时，才形成 Workflow Revision",
                },
                "agent": {
                    "state": "not_formed",
                    "digest": None,
                    "gate": "需先有合适的 Workflow Revision，并通过 Agent Package、Registry、Eval 与人工晋级门",
                },
            },
            "decision": decision,
            "skill_package": None,
            "effects": {
                "writes_candidate_store": True,
                "executes_work": False,
                "writes_package_files": False,
                "registers_asset": False,
                "promotes_asset": False,
            },
            "created_at": candidate["created_at"],
            "updated_at": candidate["updated_at"],
        }
        # ``accepted`` is an internal, transaction-local intermediate until
        # the deterministic materializer has created and cold-verified its
        # exact Skill Package.  The public contract intentionally forbids an
        # accepted Candidate with ``skill_package=null``; validation therefore
        # occurs only in ``_with_skill_package`` after that mandatory join.
        if state != "accepted":
            try:
                validate(public, self._response_schema)
            except ValidationError as exc:
                raise AssetCandidateUnavailableError(
                    "candidate response violates its public contract"
                ) from exc
        return public

    def _with_skill_package(
        self,
        conn: sqlite3.Connection,
        public: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Join the cold-verified package without recursing into materialization."""

        enriched = dict(public)
        package: dict[str, Any] | None = None
        if public.get("state") == "accepted":
            if self._materializer is None:
                raise AssetCandidateUnavailableError(
                    "accepted candidate has no materializer"
                )
            source = public.get("source")
            if not isinstance(source, Mapping):
                raise AssetCandidateUnavailableError(
                    "accepted candidate owner projection is malformed"
                )
            try:
                package = self._materializer.get_for_candidate_digest(
                    conn,
                    candidate_digest=public.get("candidate_digest"),
                    username=source.get("initiated_by_username"),
                )
            except Exception as exc:
                raise AssetCandidateUnavailableError(
                    "accepted candidate Skill Package cannot be verified"
                ) from exc
            if package is None:
                raise AssetCandidateUnavailableError(
                    "accepted candidate has no isolated Skill Package"
                )
        enriched["skill_package"] = package
        try:
            validate(enriched, self._response_schema)
        except ValidationError as exc:
            raise AssetCandidateUnavailableError(
                "candidate response violates its public contract"
            ) from exc
        return enriched


def _conflict(code: str, message: str) -> None:
    raise AssetCandidateConflictError(code, message)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _proposal_provenance() -> dict[str, Any]:
    return {
        "schema_version": PROPOSAL_PROVENANCE_VERSION,
        "kind": "deterministic_task_projection",
        "policy_version": POLICY_VERSION,
        "llm_used": False,
        "sources": list(_PROPOSAL_SOURCES),
    }


def _verify_candidate_revision_chain(
    conn: sqlite3.Connection, candidate: Mapping[str, Any]
) -> None:
    """Verify the immutable per-task chain and its system lifecycle events."""

    source_task_id = candidate.get("source_task_id")
    revision = candidate.get("revision")
    if (
        not isinstance(source_task_id, str)
        or not source_task_id.strip()
        or type(revision) is not int
        or revision < 1
    ):
        raise AssetCandidateUnavailableError("candidate revision chain is malformed")
    rows = conn.execute(
        """
        SELECT id, source_task_id, revision, supersedes_candidate_digest,
               candidate_digest, bundle_digest, state, decision_event_id,
               initiated_by_username, created_at, updated_at
        FROM asset_candidates
        WHERE source_task_id = ? AND revision <= ?
        ORDER BY revision ASC
        """,
        (source_task_id, revision),
    ).fetchall()
    if len(rows) != revision or rows[-1]["id"] != candidate.get("id"):
        raise AssetCandidateUnavailableError(
            "candidate previous revision is missing or belongs to another task"
        )

    previous_digest: str | None = None
    for expected_revision, row in enumerate(rows, start=1):
        if (
            row["revision"] != expected_revision
            or row["source_task_id"] != source_task_id
            or row["supersedes_candidate_digest"] != previous_digest
        ):
            raise AssetCandidateUnavailableError(
                "candidate revision does not bind its exact predecessor"
            )
        _verify_unique_created_event(conn, row)
        if expected_revision < revision:
            if row["state"] == "superseded":
                _verify_superseded_event(conn, row)
            elif row["state"] in ("accepted", "rejected"):
                _verified_terminal_event(conn, row)
            else:
                raise AssetCandidateUnavailableError(
                    "candidate predecessor was not terminally decided or superseded"
                )
        previous_digest = _required_digest(
            row["candidate_digest"], "candidate revision digest"
        )


def _verify_unique_created_event(
    conn: sqlite3.Connection, candidate: Mapping[str, Any]
) -> None:
    events = conn.execute(
        """
        SELECT * FROM asset_candidate_events
        WHERE candidate_id = ? AND event_type = 'candidate_created'
        ORDER BY id ASC
        """,
        (candidate["id"],),
    ).fetchall()
    if len(events) != 1:
        raise AssetCandidateUnavailableError(
            "candidate must have exactly one creation event"
        )
    event = events[0]
    if (
        event["candidate_digest"] != candidate["candidate_digest"]
        or event["bundle_digest"] != candidate["bundle_digest"]
        or event["from_state"] is not None
        or event["to_state"] != "awaiting_human_review"
        or event["actor_source"] != "authenticated_task_owner"
        or event["signer_display_name"] is not None
        or event["signer_user_id"] is not None
        or event["signer_username"] is not None
        or event["signer_session_hash"] is not None
        or event["created_at"] != candidate["created_at"]
    ):
        raise AssetCandidateUnavailableError(
            "candidate creation event does not bind the stored revision"
        )


def _verify_superseded_event(
    conn: sqlite3.Connection, candidate: Mapping[str, Any]
) -> None:
    events = conn.execute(
        """
        SELECT * FROM asset_candidate_events
        WHERE candidate_id = ? AND event_type = 'candidate_superseded'
        ORDER BY id ASC
        """,
        (candidate["id"],),
    ).fetchall()
    decision_event_id = candidate["decision_event_id"]
    if len(events) != 1 or not isinstance(decision_event_id, str):
        raise AssetCandidateUnavailableError(
            "superseded candidate has no unique retirement event"
        )
    event = events[0]
    if (
        event["event_id"] != decision_event_id
        or event["candidate_digest"] != candidate["candidate_digest"]
        or event["bundle_digest"] != candidate["bundle_digest"]
        or event["from_state"] != "awaiting_human_review"
        or event["to_state"] != "superseded"
        or event["actor_source"] != "authenticated_task_owner"
        or event["signer_display_name"] is not None
        or event["signer_user_id"] is not None
        or event["signer_username"] is not None
        or event["signer_session_hash"] is not None
        or event["created_at"] != candidate["updated_at"]
    ):
        raise AssetCandidateUnavailableError(
            "candidate retirement event does not bind the superseded revision"
        )


def _verified_terminal_event(
    conn: sqlite3.Connection, candidate: Mapping[str, Any]
) -> dict[str, Any]:
    record = dict(candidate)
    state = record.get("state")
    event_id = record.get("decision_event_id")
    expected_event_type = (
        "candidate_accepted" if state == "accepted" else "candidate_rejected"
    )
    event = (
        candidate_store.get_event(conn, event_id)
        if isinstance(event_id, str) and event_id
        else None
    )
    if (
        state not in ("accepted", "rejected")
        or event is None
        or event.get("event_type") != expected_event_type
        or event.get("candidate_id") != record.get("id")
        or event.get("candidate_digest") != record.get("candidate_digest")
        or event.get("bundle_digest") != record.get("bundle_digest")
        or event.get("from_state") != "awaiting_human_review"
        or event.get("to_state") != state
        or event.get("signer_username") != record.get("initiated_by_username")
    ):
        raise AssetCandidateUnavailableError(
            "candidate decision event does not bind its owner and terminal state"
        )
    attestation = {
        "signer_source": event.get("actor_source"),
        "confirmed_by": event.get("signer_display_name"),
        "signer_user_id": event.get("signer_user_id"),
        "signer_username": event.get("signer_username"),
        "signer_session_hash": event.get("signer_session_hash"),
    }
    if stored_signer_attests(attestation) is not True:
        raise AssetCandidateUnavailableError(
            "candidate decision signer provenance is invalid"
        )
    return event


def _stable_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise AssetCandidateUnavailableError(
                "canonical object keys must be strings"
            )
        return {
            unicodedata.normalize("NFC", key): _stable_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_stable_value(item) for item in value]
    if isinstance(value, tuple):
        return [_stable_value(item) for item in value]
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if value is None or isinstance(value, (bool, int)):
        return value
    if (
        isinstance(value, float)
        and value == value
        and value not in (float("inf"), float("-inf"))
    ):
        return value
    raise AssetCandidateUnavailableError(
        f"unsupported canonical value type: {type(value).__name__}"
    )


def _value_shape(value: Any) -> str:
    """Describe an input structurally without copying its engineering value."""

    if value is None:
        return "空值"
    if isinstance(value, bool):
        return "布尔值"
    if isinstance(value, int):
        return "整数"
    if isinstance(value, float):
        return "数值"
    if isinstance(value, str):
        return "文本"
    if isinstance(value, list):
        return "列表"
    if isinstance(value, Mapping):
        return "对象"
    raise AssetCandidateUnavailableError(
        f"task input contains unsupported value type: {type(value).__name__}"
    )


def _batch_operation_member(
    metadata: Any, created_by_username: Any
) -> tuple[str, str, str, int, int] | None:
    """Return a fully bounded Guide batch member identity, or no trust."""

    if not isinstance(metadata, Mapping):
        return None
    operation = metadata.get("guide_batch_operation")
    if operation is None:
        return None
    if not isinstance(operation, Mapping):
        return None
    if not isinstance(created_by_username, str) or not created_by_username.strip():
        return None
    operation_id = operation.get("operation_id")
    if not isinstance(operation_id, str) or not operation_id.strip():
        return None
    fingerprint = operation.get("fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint.strip():
        return None
    count = operation.get("count")
    index = operation.get("index")
    if type(count) is not int or count <= 0:
        return None
    if type(index) is not int or index < 0 or index >= count:
        return None
    return created_by_username, operation_id, fingerprint, count, index


def _verified_batch_task_ids(
    conn: sqlite3.Connection,
    *,
    conversation_id: str,
    task: Mapping[str, Any],
) -> set[str]:
    """Prove an atomic batch before suppressing any task boundary.

    `operation_id` alone is only a client idempotency key.  It cannot merge work
    cases across owners or payloads, and corrupt/missing/duplicate batch members
    must fall back to ordinary per-task boundaries.
    """

    current = _batch_operation_member(
        task.get("metadata"), task.get("created_by_username")
    )
    if current is None:
        return set()
    batch_key = current[:4]
    expected_count = current[3]
    rows = conn.execute(
        """
        SELECT id, created_by_username, metadata_json
        FROM tasks
        WHERE conversation_id = ?
        """,
        (conversation_id,),
    ).fetchall()
    members: list[tuple[str, int]] = []
    for row in rows:
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        member = _batch_operation_member(metadata, row["created_by_username"])
        if member is not None and member[:4] == batch_key:
            members.append((row["id"], member[4]))

    member_ids = {task_id for task_id, _index in members}
    indices = [index for _task_id, index in members]
    if (
        task.get("id") not in member_ids
        or len(members) != expected_count
        or len(set(indices)) != expected_count
        or set(indices) != set(range(expected_count))
    ):
        return set()
    return member_ids


def _bounded_unique_text_list(value: Any, limit: int) -> bool:
    if not isinstance(value, list) or len(value) > limit:
        return False
    if any(not isinstance(item, str) or not item.strip() for item in value):
        return False
    return len(set(value)) == len(value)


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            _stable_value(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise AssetCandidateUnavailableError("value cannot be canonicalized") from exc


def _digest(value: Any) -> str:
    payload = _canonical_json(value).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _candidate_content_digest(
    *,
    revision: int,
    supersedes_candidate_digest: str | None,
    bundle_digest: str,
    lineage_digest: str,
    proposal_provenance_digest: str,
) -> str:
    return _digest(
        {
            "schema_version": SCHEMA_VERSION,
            "revision": revision,
            "supersedes_candidate_digest": supersedes_candidate_digest,
            "bundle_digest": bundle_digest,
            "lineage_digest": lineage_digest,
            "proposal_provenance_digest": proposal_provenance_digest,
            "validation_policy_version": POLICY_VERSION,
        }
    )


def _is_raw_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _HEX_DIGEST_LENGTH
        and all(char in "0123456789abcdef" for char in value)
    )


def _required_raw_digest(value: Any, field: str) -> str:
    if not _is_raw_digest(value):
        raise AssetCandidateUnavailableError(f"{field} is not a SHA-256 digest")
    return value


def _is_prefixed_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and _is_raw_digest(value.removeprefix("sha256:"))
    )


def _required_digest(value: Any, field: str) -> str:
    if not _is_prefixed_digest(value):
        raise AssetCandidateUnavailableError(
            f"{field} is not a prefixed SHA-256 digest"
        )
    assert isinstance(value, str)
    return value


def _required_text(value: Any, field: str, *, max_length: int = 2000) -> str:
    if not isinstance(value, str):
        raise AssetCandidateUnavailableError(f"{field} must be text")
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized or len(normalized) > max_length:
        raise AssetCandidateUnavailableError(f"{field} is blank or exceeds its limit")
    return normalized
