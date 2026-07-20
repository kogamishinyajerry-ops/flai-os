"""Application service for exact design comparison and promotion evidence."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Callable, Iterator, Literal

from pydantic import ValidationError

from tools_impl.open_design_daemon.policy import (
    CandidatePolicyError,
    validate_png,
    validate_safe_path,
)

from ..storage import design_promotion_repo as promotion_repo
from ..storage.file_integrity import open_verified_file
from .contracts import (
    Actor,
    ComparisonCreate,
    OpenDesignCandidateManifest,
    PublishRequest,
    ReleaseDecisionRequest,
    ReleaseRequestCreate,
    RollbackRequest,
    SelectionRequest,
    canonical_sha256,
)
from .targets import AssetTarget, CurrentFrame, TargetRegistry, TargetRegistryError


class DesignPromotionError(RuntimeError):
    status_code = 422
    code = "design_promotion_invalid"


class DesignPromotionNotFound(DesignPromotionError):
    status_code = 404
    code = "design_promotion_not_found"


class DesignPromotionConflict(DesignPromotionError):
    status_code = 409
    code = "design_promotion_conflict"


class SensitiveCandidateRequiresRoleAxis(DesignPromotionError):
    status_code = 403
    code = "sensitive_candidate_requires_role_axis"


_TRANSACTION_ESCAPE_ERROR = (
    "human review participant cannot own or escape the caller transaction"
)
# SQLite emits these authorizer actions from its parsed statement, so leading
# comments and alternate whitespace cannot disguise transaction control.  This
# is the complete action surface exercised by the human-review primitive;
# transaction/savepoint, DELETE, PRAGMA, DDL, ATTACH, and DETACH fail closed.
_TRANSACTION_PARTICIPANT_SQL_ACTIONS = frozenset(
    {
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_INSERT,
        sqlite3.SQLITE_UPDATE,
        sqlite3.SQLITE_FUNCTION,
    }
)


class _TransactionCursor:
    """Read/result-only cursor facade with no connection or SQL execution escape."""

    __slots__ = ("__cursor",)

    def __init__(self, cursor: sqlite3.Cursor) -> None:
        self.__cursor = cursor

    @property
    def connection(self) -> None:
        raise RuntimeError(_TRANSACTION_ESCAPE_ERROR)

    @property
    def rowcount(self) -> int:
        return self.__cursor.rowcount

    @property
    def lastrowid(self) -> int | None:
        return self.__cursor.lastrowid

    @property
    def description(self) -> tuple[tuple[Any, ...], ...] | None:
        return self.__cursor.description

    def fetchone(self) -> Any:
        return self.__cursor.fetchone()

    def fetchmany(self, size: int | None = None) -> list[Any]:
        if size is None:
            return self.__cursor.fetchmany()
        return self.__cursor.fetchmany(size)

    def fetchall(self) -> list[Any]:
        return self.__cursor.fetchall()

    def close(self) -> None:
        self.__cursor.close()

    def __iter__(self) -> _TransactionCursor:
        return self

    def __next__(self) -> Any:
        return next(self.__cursor)


class _TransactionParticipant:
    """Narrow connection facade that cannot own or escape the caller transaction."""

    __slots__ = ("__connection",)

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.__connection = connection

    @property
    def in_transaction(self) -> bool:
        return self.__connection.in_transaction

    def execute(
        self, sql: str, parameters: object = ()
    ) -> _TransactionCursor:
        if not isinstance(sql, str):
            raise RuntimeError("transaction participant SQL must be text")
        if not self.__connection.in_transaction:
            raise RuntimeError(_TRANSACTION_ESCAPE_ERROR)

        denied_action: int | None = None

        def _authorize(
            action_code: int,
            _arg1: str | None,
            _arg2: str | None,
            _database: str | None,
            _trigger: str | None,
        ) -> int:
            nonlocal denied_action
            if action_code in _TRANSACTION_PARTICIPANT_SQL_ACTIONS:
                return sqlite3.SQLITE_OK
            denied_action = action_code
            return sqlite3.SQLITE_DENY

        self.__connection.set_authorizer(_authorize)
        try:
            cursor = self.__connection.execute(sql, parameters)  # type: ignore[arg-type]
        except sqlite3.DatabaseError as exc:
            if denied_action is not None:
                raise RuntimeError(_TRANSACTION_ESCAPE_ERROR) from exc
            raise
        finally:
            self.__connection.set_authorizer(None)
        return _TransactionCursor(cursor)

    def commit(self) -> None:
        raise RuntimeError(_TRANSACTION_ESCAPE_ERROR)

    def rollback(self) -> None:
        raise RuntimeError(_TRANSACTION_ESCAPE_ERROR)


@contextmanager
def _exclusive_file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle: BinaryIO = path.open("a+b")
    acquired = False
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise DesignPromotionConflict("promotion target is locked") from exc
            acquired = True
        else:
            import errno
            import fcntl

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                if exc.errno in {errno.EACCES, errno.EAGAIN}:
                    raise DesignPromotionConflict("promotion target is locked") from exc
                raise
            acquired = True
        yield
    finally:
        try:
            if acquired and os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            elif acquired:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


@dataclass(frozen=True)
class PngFrame:
    content: bytes
    media_type: Literal["image/png"] = "image/png"


@dataclass(frozen=True)
class _CapturedFile:
    descriptor: Any
    record: dict[str, Any]
    content: bytes


@dataclass(frozen=True)
class _CandidateEvidence:
    manifest: OpenDesignCandidateManifest
    manifest_sha256: str
    promotable: _CapturedFile
    preview_files: dict[tuple[object, ...], _CapturedFile]


def _strict_json_object(content: bytes) -> dict[str, Any]:
    try:
        text = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise DesignPromotionConflict("candidate manifest is not strict UTF-8") from exc

    def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise DesignPromotionConflict("candidate manifest is not strict JSON") from exc
    if not isinstance(value, dict):
        raise DesignPromotionConflict("candidate manifest must be an object")
    return value


def _read_verified_record(record: dict[str, Any], *, root: Path) -> bytes:
    try:
        handle = open_verified_file(
            str(record["path"]),
            allowed_root=root,
            expected_size=int(record["size_bytes"]),
            expected_sha256=str(record["sha256"]),
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise DesignPromotionConflict("candidate file integrity check failed") from exc
    try:
        return handle.read()
    finally:
        handle.close()


def _path_has_exact_suffix(path: str, relative: str) -> bool:
    expected = PurePosixPath(relative).parts
    actual = Path(path).parts
    return bool(expected) and len(actual) >= len(expected) and tuple(actual[-len(expected) :]) == expected


def _safe_target_path(root: Path, relative: str, *, require_file: bool) -> Path:
    try:
        root_resolved = root.resolve(strict=True)
    except OSError as exc:
        raise DesignPromotionConflict("configured target root is unavailable") from exc
    candidate = root_resolved.joinpath(*PurePosixPath(relative).parts)
    current = root_resolved
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.exists() or current.is_symlink():
            if current.is_symlink():
                raise DesignPromotionConflict("allowlisted target path contains a symlink")
    try:
        resolved_parent = candidate.parent.resolve(strict=True)
    except OSError as exc:
        raise DesignPromotionConflict("allowlisted target parent is unavailable") from exc
    if root_resolved != resolved_parent and root_resolved not in resolved_parent.parents:
        raise DesignPromotionConflict("allowlisted target escapes its configured root")
    if require_file and not candidate.is_file():
        raise DesignPromotionConflict("trusted current frame is missing")
    if candidate.exists() and not candidate.is_file():
        raise DesignPromotionConflict("allowlisted target is not a regular file")
    return candidate


def _read_bounded_png(path: Path) -> tuple[bytes, dict[str, int]]:
    try:
        size = path.stat().st_size
        if size < 1 or size > 4 * 1024 * 1024:
            raise DesignPromotionConflict("PNG is outside the closed byte bounds")
        content = path.read_bytes()
        info = validate_png(content)
    except (OSError, CandidatePolicyError) as exc:
        raise DesignPromotionConflict("PNG failed passive structural validation") from exc
    return content, info


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        # Python exposes no portable directory fsync on Windows.  os.replace is
        # still atomic on one volume; Windows durability remains an explicit
        # platform verification item in ADR-0042.
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_new_fsynced(path: Path, content: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(content)
        written = 0
        while written < len(view):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                raise OSError("short write")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_verified(path: Path, content: bytes, *, expected_sha256: str) -> None:
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        _write_new_fsynced(temp, content)
        if hashlib.sha256(temp.read_bytes()).hexdigest() != expected_sha256:
            raise DesignPromotionConflict("temporary promotion bytes failed verification")
        os.replace(temp, path)
        _fsync_directory(path.parent)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def _snapshot_png_path(path: Path) -> tuple[str, str | None, bytes | None]:
    if not path.exists():
        return "absent", None, None
    content, _info = _read_bounded_png(path)
    return "present", hashlib.sha256(content).hexdigest(), content


def _public_comparison(
    internal: dict[str, Any],
    comparison_sha256: str,
    *,
    phase: str | None = None,
    workflow: dict[str, Any] | None = None,
) -> dict[str, Any]:
    public = json.loads(json.dumps(internal, ensure_ascii=False))
    for frame in public["frames"]:
        frame["current"].pop("_relative_path", None)
        frame["candidate"].pop("_file_id", None)
    public["comparison_sha256"] = comparison_sha256
    if phase is not None:
        public["phase"] = phase
    if workflow is not None:
        public["workflow"] = workflow
    return public


def _expected_target_value(kind: str, sha256: str | None) -> dict[str, str]:
    return {"kind": kind, **({"sha256": sha256} if sha256 is not None else {})}


def _normalized_comment(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _selection_response(row: dict[str, Any], task_status: str) -> dict[str, Any]:
    return {
        "schema_version": "flai-design-selection/v1",
        "selection_id": row["id"],
        "comparison_id": row["comparison_id"],
        "comparison_sha256": row["comparison_sha256"],
        "task_id": row["task_id"],
        "action": row["action"],
        "candidate_id": row["candidate_id"],
        "candidate_sha256": row["candidate_asset_sha256"],
        "task_decision_id": row["task_decision_id"],
        "selected_by": {
            "username": row["decided_by_username"],
            "display_name": row["decided_by_display_name"],
        },
        "reason_code": row["reason_code"],
        "comment": row["comment"],
        "created_at": row["created_at"],
        "task_status": task_status,
    }


def _release_request_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "flai-design-release-request/v1",
        "release_request_id": row["id"],
        "selection_id": row["selection_id"],
        "comparison_id": row["comparison_id"],
        "state": "awaiting_release_approval",
        "summary": row["summary"],
        "summary_sha256": row["summary_sha256"],
        "requested_by": {
            "username": row["requested_by_username"],
            "display_name": row["requested_by_display_name"],
        },
        "created_at": row["created_at"],
    }


def _release_decision_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "flai-design-release-decision/v1",
        "release_request_id": row["release_request_id"],
        "state": "release_approved" if row["action"] == "approve" else "release_rejected",
        "decision_id": row["id"],
        "action": row["action"],
        "summary_sha256": row["summary_sha256"],
        "decided_by": {
            "username": row["decided_by_username"],
            "display_name": row["decided_by_display_name"],
        },
        "reason_code": row["reason_code"],
        "comment": row["comment"],
        "created_at": row["created_at"],
        "release_package": row["release_package"],
    }


def _publish_event_state(
    events: list[dict[str, Any]],
) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None]:
    """Return (phase, pending_intent, latest confirmed public result)."""

    phase = "publish_ready"
    pending: dict[str, Any] | None = None
    latest_result: dict[str, Any] | None = None
    for event in events:
        event_type = str(event["event_type"])
        if event_type == "publish_intent":
            if phase != "publish_ready" or pending is not None:
                raise DesignPromotionConflict("publish ledger sequence is invalid")
            pending = event
            continue
        if event_type in {
            "publish_commit",
            "publish_abort",
            "publish_recovered_commit",
            "publish_manual_intervention",
        }:
            if (
                pending is None
                or pending["event_type"] != "publish_intent"
                or pending["attempt_id"] != event["attempt_id"]
            ):
                raise DesignPromotionConflict("publish terminal event lacks exact intent")
            pending = None
            if event_type == "publish_abort":
                phase = "publish_ready"
                latest_result = None
            elif event_type == "publish_manual_intervention":
                phase = "manual_intervention"
                latest_result = None
            else:
                phase = "published"
                latest_result = event["details"].get("public_result")
                if not isinstance(latest_result, dict):
                    raise DesignPromotionConflict("publish commit lacks public result")
            continue
        if event_type == "rollback_intent":
            if phase != "published" or pending is not None:
                raise DesignPromotionConflict("rollback intent is not based on publication")
            pending = event
            continue
        if event_type in {
            "rollback_commit",
            "rollback_abort",
            "rollback_recovered_commit",
            "rollback_manual_intervention",
        }:
            if (
                pending is None
                or pending["event_type"] != "rollback_intent"
                or pending["attempt_id"] != event["attempt_id"]
            ):
                raise DesignPromotionConflict("rollback terminal event lacks exact intent")
            pending = None
            if event_type == "rollback_abort":
                phase = "published"
            elif event_type == "rollback_manual_intervention":
                phase = "manual_intervention"
                latest_result = None
            else:
                phase = "rolled_back"
                latest_result = event["details"].get("public_result")
                if not isinstance(latest_result, dict):
                    raise DesignPromotionConflict("rollback commit lacks public result")
            continue
        raise DesignPromotionConflict("publish ledger contains an unknown event")
    return phase, pending, latest_result


def _published_result(
    *,
    release_request_id: str,
    event_id: str,
    target_id: str,
    before_sha256: str | None,
    after_sha256: str,
    backup_sha256: str | None,
    release_package_sha256: str,
    actor: Actor,
    created_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": "flai-design-publish-result/v1",
        "release_request_id": release_request_id,
        "state": "published",
        "publish_event_id": event_id,
        "target_id": target_id,
        "before_sha256": before_sha256,
        "after_sha256": after_sha256,
        "backup_sha256": backup_sha256,
        "release_package_sha256": release_package_sha256,
        "published_by": actor.model_dump(mode="json"),
        "published_at": created_at,
    }


def _rolled_back_result(
    *,
    release_request_id: str,
    event_id: str,
    target_id: str,
    before_sha256: str,
    after_sha256: str | None,
    backup_sha256: str | None,
    release_package_sha256: str,
    actor: Actor,
    created_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": "flai-design-publish-result/v1",
        "release_request_id": release_request_id,
        "state": "rolled_back",
        "rollback_event_id": event_id,
        "target_id": target_id,
        "before_sha256": before_sha256,
        "after_sha256": after_sha256,
        "backup_sha256": backup_sha256,
        "release_package_sha256": release_package_sha256,
        "rolled_back_by": actor.model_dump(mode="json"),
        "rolled_back_at": created_at,
    }


class DesignPromotionService:
    def __init__(
        self,
        *,
        conn_factory: Callable[[], sqlite3.Connection],
        task_runs_dir: Path,
        target_root: Path,
        promotion_runtime_dir: Path,
        targets: TargetRegistry,
        human_review_applier: Callable[..., dict[str, Any]] | None = None,
        fault_hook: Callable[[str], None] | None = None,
        allow_synthetic_internal_candidates: bool = False,
    ) -> None:
        if type(allow_synthetic_internal_candidates) is not bool:
            raise ValueError("synthetic candidate admission flag must be boolean")
        self._conn_factory = conn_factory
        self._task_runs_dir = task_runs_dir.resolve()
        self._target_root = target_root.resolve()
        self._promotion_runtime_dir = promotion_runtime_dir
        self._targets = targets
        self._human_review_applier = human_review_applier
        self._fault_hook = fault_hook
        self._allow_synthetic_internal_candidates = (
            allow_synthetic_internal_candidates
        )

    def _fault(self, point: str) -> None:
        if self._fault_hook is not None:
            self._fault_hook(point)

    @staticmethod
    def _workflow_projection(
        conn: sqlite3.Connection, comparison_id: str
    ) -> tuple[str, dict[str, Any]]:
        selection = promotion_repo.get_selection(conn, comparison_id=comparison_id)
        if selection is None:
            return "candidate_pending", {
                "selection": None,
                "release_request": None,
                "release_decision": None,
                "latest_publish": None,
            }
        selection_response = _selection_response(
            selection, "completed" if selection["action"] == "approve" else "failed"
        )
        if selection["action"] == "reject":
            return "candidate_rejected", {
                "selection": selection_response,
                "release_request": None,
                "release_decision": None,
                "latest_publish": None,
            }
        release = promotion_repo.get_release_request(
            conn, selection_id=selection["id"]
        )
        if release is None:
            return "candidate_approved", {
                "selection": selection_response,
                "release_request": None,
                "release_decision": None,
                "latest_publish": None,
            }
        if canonical_sha256(release["summary"]) != release["summary_sha256"]:
            raise DesignPromotionConflict("release summary hash drifted")
        release_response = _release_request_response(release)
        decision = promotion_repo.get_release_decision(conn, release["id"])
        if decision is None:
            return "release_pending", {
                "selection": selection_response,
                "release_request": release_response,
                "release_decision": None,
                "latest_publish": None,
            }
        decision_response = _release_decision_response(decision)
        if decision["action"] == "reject":
            return "release_rejected", {
                "selection": selection_response,
                "release_request": release_response,
                "release_decision": decision_response,
                "latest_publish": None,
            }
        events = promotion_repo.get_publish_events(conn, release["id"])
        for event in events:
            if canonical_sha256(event["details"]) != event["details_sha256"]:
                raise DesignPromotionConflict("publish event details hash drifted")
        phase, pending, latest_publish = _publish_event_state(events)
        if pending is not None:
            raise DesignPromotionConflict(
                "unresolved publication intent must be reconciled before projection"
            )
        return phase, {
            "selection": selection_response,
            "release_request": release_response,
            "release_decision": decision_response,
            "latest_publish": latest_publish,
        }

    def _assert_comparison_inputs_unchanged(
        self,
        conn: sqlite3.Connection,
        row: dict[str, Any],
        *,
        expected_task_status: str = "waiting_review",
        check_frames: bool = True,
    ) -> None:
        """Recheck every byte and classification used by a named selection.

        PNG scanning establishes only passive rendering structure.  It never
        declassifies candidate bytes, so task and every referenced output must
        still be explicitly ``internal`` at the selection boundary.
        """

        task_row = conn.execute(
            "SELECT status, data_classification FROM tasks WHERE id=?", (row["task_id"],)
        ).fetchone()
        if task_row is None:
            raise DesignPromotionConflict("comparison task is missing")
        if task_row[1] != "internal":
            raise SensitiveCandidateRequiresRoleAxis(
                "sensitive candidate requires the deferred role axis"
            )
        if task_row[0] != expected_task_status:
            raise DesignPromotionConflict("candidate task status is not exact")

        internal = row["comparison"]
        file_ids = {
            str(row["candidate_asset_file_id"]),
            *(str(frame["candidate"]["_file_id"]) for frame in internal["frames"]),
        }
        placeholders = ",".join("?" for _ in file_ids)
        file_rows = conn.execute(
            f"SELECT * FROM files WHERE id IN ({placeholders})", tuple(file_ids)
        ).fetchall()
        if len(file_rows) != len(file_ids):
            raise DesignPromotionConflict("comparison candidate file is missing")
        records = {str(item["id"]): dict(item) for item in file_rows}
        for record in records.values():
            if record.get("classification") != "internal":
                raise SensitiveCandidateRequiresRoleAxis(
                    "sensitive candidate requires the deferred role axis"
                )
            if record.get("task_id") != row["task_id"] or record.get("kind") != "output":
                raise DesignPromotionConflict("comparison candidate membership drifted")

        candidate = records[str(row["candidate_asset_file_id"])]
        candidate_content = _read_verified_record(candidate, root=self._task_runs_dir)
        if hashlib.sha256(candidate_content).hexdigest() != row["candidate_asset_sha256"]:
            raise DesignPromotionConflict("candidate asset hash drifted")
        try:
            validate_png(candidate_content)
        except CandidatePolicyError as exc:
            raise DesignPromotionConflict("candidate asset PNG scan failed") from exc

        for frame in internal["frames"] if check_frames else ():
            candidate_record = records[str(frame["candidate"]["_file_id"])]
            candidate_frame = _read_verified_record(
                candidate_record, root=self._task_runs_dir
            )
            try:
                candidate_info = validate_png(candidate_frame)
            except CandidatePolicyError as exc:
                raise DesignPromotionConflict("candidate frame PNG scan failed") from exc
            if (
                hashlib.sha256(candidate_frame).hexdigest()
                != frame["candidate"]["sha256"]
                or candidate_info
                != {
                    "width": frame["candidate"]["width"],
                    "height": frame["candidate"]["height"],
                }
            ):
                raise DesignPromotionConflict("candidate frame evidence drifted")

            current_path = _safe_target_path(
                self._target_root,
                frame["current"]["_relative_path"],
                require_file=True,
            )
            current_frame, current_info = _read_bounded_png(current_path)
            if (
                hashlib.sha256(current_frame).hexdigest()
                != frame["current"]["sha256"]
                or current_info
                != {
                    "width": frame["current"]["width"],
                    "height": frame["current"]["height"],
                }
            ):
                raise DesignPromotionConflict(
                    "current comparison frame drifted; create a new comparison"
                )

        try:
            target = self._targets.by_id(str(row["target_id"]))
        except TargetRegistryError as exc:
            raise DesignPromotionConflict(str(exc)) from exc
        if (
            target.asset_slot != row["asset_slot"]
            or target.relative_path != row["target_relative_path"]
        ):
            raise DesignPromotionConflict("comparison target allowlist binding drifted")
        current_kind, current_sha = self._target_snapshot(target)
        if (current_kind, current_sha) != (
            row["target_preimage_kind"],
            row["target_preimage_sha256"],
        ):
            raise DesignPromotionConflict(
                "target preimage drifted; create a new comparison"
            )

    def _load_candidate(self, conn: sqlite3.Connection, task_id: str) -> _CandidateEvidence:
        task_row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if task_row is None:
            raise DesignPromotionNotFound("design candidate task does not exist")
        task = dict(task_row)
        if task.get("status") != "waiting_review":
            raise DesignPromotionConflict("a new comparison requires waiting_review")
        if task.get("data_classification") != "internal":
            raise SensitiveCandidateRequiresRoleAxis(
                "sensitive candidate requires the deferred role axis"
            )
        try:
            metadata = json.loads(task.get("metadata_json") or "{}")
            output_ids = json.loads(task.get("output_file_ids") or "[]")
        except json.JSONDecodeError as exc:
            raise DesignPromotionConflict("task provenance is malformed") from exc
        if not isinstance(metadata, dict) or not isinstance(output_ids, list):
            raise DesignPromotionConflict("task provenance is malformed")
        if (
            metadata.get("review_contract") != "open-design-candidate/v1"
            or metadata.get("generator_kind") != "open_design_daemon"
        ):
            raise DesignPromotionConflict("task is not a production design candidate")
        if not output_ids or any(not isinstance(item, str) for item in output_ids):
            raise DesignPromotionConflict("task output manifest is empty or malformed")
        if len(set(output_ids)) != len(output_ids):
            raise DesignPromotionConflict("task output manifest contains duplicate ids")
        placeholders = ",".join("?" for _ in output_ids)
        rows = conn.execute(
            f"SELECT * FROM files WHERE id IN ({placeholders})", tuple(output_ids)
        ).fetchall()
        if len(rows) != len(output_ids):
            raise DesignPromotionConflict("task output manifest references a missing file")
        records = [dict(row) for row in rows]
        for record in records:
            if record.get("classification") != "internal":
                raise SensitiveCandidateRequiresRoleAxis(
                    "sensitive candidate requires the deferred role axis"
                )
            if record.get("task_id") != task_id or record.get("kind") != "output":
                raise DesignPromotionConflict("every design file must be an exact task output")
        manifest_rows = [
            record
            for record in records
            if record.get("filename") == "open_design_daemon_candidates.json"
        ]
        if len(manifest_rows) != 1:
            raise DesignPromotionConflict("candidate manifest must be unique")
        manifest_record = manifest_rows[0]
        expected_manifest_sha = metadata.get("candidate_manifest_sha256")
        if expected_manifest_sha != manifest_record.get("sha256"):
            raise DesignPromotionConflict("task metadata does not bind the candidate manifest")
        manifest_content = _read_verified_record(manifest_record, root=self._task_runs_dir)
        if hashlib.sha256(manifest_content).hexdigest() != expected_manifest_sha:
            raise DesignPromotionConflict("candidate manifest hash drifted")
        try:
            manifest = OpenDesignCandidateManifest.model_validate(
                _strict_json_object(manifest_content)
            )
        except ValidationError as exc:
            raise DesignPromotionConflict("candidate manifest violates the exact P2.7 contract") from exc
        # P2.7 truth is an independent classification witness.  Internal DB
        # projections or passive PNG scans can never override its explicit
        # sensitive declaration.  Only in-process state-machine tests may opt
        # into the synthetic fixture escape hatch; create_app never exposes it.
        if (
            manifest.classification == "sensitive"
            and self._allow_synthetic_internal_candidates is not True
        ):
            raise SensitiveCandidateRequiresRoleAxis(
                "sensitive candidate requires the deferred role axis"
            )

        captured: dict[str, _CapturedFile] = {}
        for descriptor in manifest.captured_files:
            try:
                validate_safe_path(descriptor.source_path)
                validate_safe_path(descriptor.bundle_relpath)
            except CandidatePolicyError as exc:
                raise DesignPromotionConflict("candidate manifest contains an unsafe path") from exc
            matches = [
                record
                for record in records
                if record.get("sha256") == descriptor.sha256
                and int(record.get("size_bytes", -1)) == descriptor.size_bytes
                and _path_has_exact_suffix(str(record.get("path", "")), descriptor.bundle_relpath)
            ]
            if len(matches) != 1:
                raise DesignPromotionConflict("captured candidate file membership is not unique")
            content = _read_verified_record(matches[0], root=self._task_runs_dir)
            if len(content) != descriptor.size_bytes or hashlib.sha256(content).hexdigest() != descriptor.sha256:
                raise DesignPromotionConflict("captured candidate bytes drifted")
            captured[descriptor.source_path] = _CapturedFile(descriptor, matches[0], content)

        promoted = captured.get(manifest.promotable_asset.source_path)
        if promoted is None or promoted.descriptor.bundle_relpath != manifest.promotable_asset.bundle_relpath:
            raise DesignPromotionConflict("promotable asset is not an exact captured file")
        try:
            promoted_info = validate_png(promoted.content)
        except CandidatePolicyError as exc:
            raise DesignPromotionConflict("promotable asset is not a passive PNG") from exc

        preview_files: dict[tuple[object, ...], _CapturedFile] = {}
        for preview in manifest.passive_previews:
            captured_preview = captured.get(preview.image.path)
            if captured_preview is None:
                raise DesignPromotionConflict("passive preview is not captured")
            try:
                info = validate_png(captured_preview.content)
            except CandidatePolicyError as exc:
                raise DesignPromotionConflict("passive preview PNG scan failed") from exc
            if info != {"width": preview.image.width, "height": preview.image.height}:
                raise DesignPromotionConflict("passive preview dimensions drifted")
            preview_files[preview.matrix_key] = captured_preview
        promoted_preview = next(
            item
            for item in manifest.passive_previews
            if item.slot_id == manifest.promotable_asset.slot_id
        )
        if promoted_info != {
            "width": promoted_preview.image.width,
            "height": promoted_preview.image.height,
        }:
            raise DesignPromotionConflict("promotable PNG dimensions are not exact")
        return _CandidateEvidence(
            manifest=manifest,
            manifest_sha256=expected_manifest_sha,
            promotable=promoted,
            preview_files=preview_files,
        )

    def _target_snapshot(self, target: AssetTarget) -> tuple[str, str | None]:
        path = _safe_target_path(
            self._target_root, target.relative_path, require_file=False
        )
        if not path.exists():
            return "absent", None
        content, _info = _read_bounded_png(path)
        return "present", hashlib.sha256(content).hexdigest()

    def _runtime_path(self, relative: str) -> Path:
        try:
            validate_safe_path(relative)
        except CandidatePolicyError as exc:
            raise DesignPromotionConflict("promotion runtime path is unsafe") from exc
        self._promotion_runtime_dir.mkdir(parents=True, exist_ok=True)
        root = self._promotion_runtime_dir.resolve(strict=True)
        candidate = root.joinpath(*PurePosixPath(relative).parts)
        current = root
        for part in PurePosixPath(relative).parts:
            current = current / part
            if current.is_symlink():
                raise DesignPromotionConflict("promotion runtime path contains a symlink")
        candidate.parent.mkdir(parents=True, exist_ok=True)
        resolved_parent = candidate.parent.resolve(strict=True)
        if root != resolved_parent and root not in resolved_parent.parents:
            raise DesignPromotionConflict("promotion runtime path escapes its root")
        return candidate

    def _read_existing_runtime_png(self, relative: str) -> bytes:
        """Read a recovery artifact without creating or repairing its path."""

        try:
            validate_safe_path(relative)
            root = self._promotion_runtime_dir.resolve(strict=True)
        except (CandidatePolicyError, OSError) as exc:
            raise DesignPromotionConflict(
                "promotion recovery runtime path is unavailable"
            ) from exc
        candidate = root.joinpath(*PurePosixPath(relative).parts)
        current = root
        for part in PurePosixPath(relative).parts:
            current = current / part
            if current.is_symlink():
                raise DesignPromotionConflict(
                    "promotion recovery runtime path contains a symlink"
                )
        try:
            resolved_parent = candidate.parent.resolve(strict=True)
        except OSError as exc:
            raise DesignPromotionConflict(
                "promotion recovery runtime parent is unavailable"
            ) from exc
        if root != resolved_parent and root not in resolved_parent.parents:
            raise DesignPromotionConflict(
                "promotion recovery runtime path escapes its root"
            )
        if not candidate.is_file():
            raise DesignPromotionConflict("promotion recovery artifact is missing")
        content, _info = _read_bounded_png(candidate)
        return content

    def _target_lock_path(self, target_id: str) -> Path:
        if target_id not in {target.target_id for target in self._targets.targets}:
            raise DesignPromotionConflict("promotion target is not allowlisted")
        return self._runtime_path(f"locks/{target_id}.lock")

    def _recovery_artifact_error(
        self, pending: dict[str, Any], *, prefix: str
    ) -> str | None:
        """Require the rollback evidence promised by a durable intent."""

        if prefix == "publish":
            if pending["before_kind"] == "absent":
                if (
                    pending["before_sha256"] is not None
                    or pending["backup_relative_path"] is not None
                    or pending["backup_sha256"] is not None
                ):
                    return "backup_binding_invalid"
                return None
            backup_relative = pending["backup_relative_path"]
            backup_sha = pending["backup_sha256"]
            if (
                pending["before_kind"] != "present"
                or not isinstance(backup_relative, str)
                or backup_sha != pending["before_sha256"]
            ):
                return "backup_binding_invalid"
            try:
                content = self._read_existing_runtime_png(backup_relative)
            except DesignPromotionConflict:
                return "backup_not_safely_readable"
            if hashlib.sha256(content).hexdigest() != backup_sha:
                return "backup_hash_drifted"
            return None

        if pending["after_kind"] == "present":
            backup_relative = pending["backup_relative_path"]
            backup_sha = pending["backup_sha256"]
            if (
                not isinstance(backup_relative, str)
                or backup_sha != pending["after_sha256"]
            ):
                return "backup_binding_invalid"
            try:
                content = self._read_existing_runtime_png(backup_relative)
            except DesignPromotionConflict:
                return "backup_not_safely_readable"
            if hashlib.sha256(content).hexdigest() != backup_sha:
                return "backup_hash_drifted"
            return None

        quarantine_relative = pending["details"].get("quarantine_relative_path")
        if (
            pending["after_kind"] != "absent"
            or pending["after_sha256"] is not None
            or not isinstance(quarantine_relative, str)
            or pending["before_sha256"] is None
        ):
            return "quarantine_binding_invalid"
        try:
            quarantine_path = _safe_target_path(
                self._target_root, quarantine_relative, require_file=True
            )
            content, _info = _read_bounded_png(quarantine_path)
        except DesignPromotionConflict:
            return "quarantine_not_safely_readable"
        if hashlib.sha256(content).hexdigest() != pending["before_sha256"]:
            return "quarantine_hash_drifted"
        return None

    def _approved_release(
        self, conn: sqlite3.Connection, release_request_id: str
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], AssetTarget]:
        release = promotion_repo.get_release_request(
            conn, release_request_id=release_request_id
        )
        if release is None:
            raise DesignPromotionNotFound("release request does not exist")
        if canonical_sha256(release["summary"]) != release["summary_sha256"]:
            raise DesignPromotionConflict("release summary hash drifted")
        decision = promotion_repo.get_release_decision(conn, release_request_id)
        if decision is None or decision["action"] != "approve":
            raise DesignPromotionConflict("release lacks a named approval")
        package = decision["release_package"]
        if not isinstance(package, dict):
            raise DesignPromotionConflict("approved release package is missing")
        if package.get("release_package_sha256") != decision["release_package_sha256"]:
            raise DesignPromotionConflict("release package hash binding drifted")
        unsigned = dict(package)
        unsigned.pop("release_package_sha256", None)
        if canonical_sha256(unsigned) != decision["release_package_sha256"]:
            raise DesignPromotionConflict("release package bytes drifted")
        if (
            package.get("summary") != release["summary"]
            or package.get("release_approval")
            != {
                "decision_id": decision["id"],
                "username": decision["decided_by_username"],
                "display_name": decision["decided_by_display_name"],
                "at": decision["created_at"],
            }
        ):
            raise DesignPromotionConflict("release package attribution drifted")
        comparison = promotion_repo.get_comparison(conn, release["comparison_id"])
        if comparison is None:
            raise DesignPromotionConflict("release comparison is missing")
        try:
            target = self._targets.by_id(release["target_id"])
        except TargetRegistryError as exc:
            raise DesignPromotionConflict(str(exc)) from exc
        if (
            target.relative_path != release["target_relative_path"]
            or comparison["target_id"] != target.target_id
            or comparison["target_relative_path"] != target.relative_path
        ):
            raise DesignPromotionConflict("release target allowlist binding drifted")
        return release, decision, comparison, target

    def _candidate_release_bytes(
        self, conn: sqlite3.Connection, release: dict[str, Any], comparison: dict[str, Any]
    ) -> bytes:
        task = conn.execute(
            "SELECT status, data_classification, output_file_ids FROM tasks WHERE id=?",
            (comparison["task_id"],),
        ).fetchone()
        if task is None or task[0] != "completed":
            raise DesignPromotionConflict("release task is not candidate-approved")
        if task[1] != "internal":
            raise SensitiveCandidateRequiresRoleAxis(
                "sensitive candidate requires the deferred role axis"
            )
        try:
            output_ids = json.loads(task[2])
        except (json.JSONDecodeError, TypeError) as exc:
            raise DesignPromotionConflict("release output manifest is malformed") from exc
        if (
            not isinstance(output_ids, list)
            or not output_ids
            or any(not isinstance(item, str) for item in output_ids)
            or len(set(output_ids)) != len(output_ids)
            or release["candidate_asset_file_id"] not in output_ids
        ):
            raise DesignPromotionConflict("release output manifest is not exact")
        placeholders = ",".join("?" for _ in output_ids)
        output_rows = conn.execute(
            f"SELECT id, task_id, kind, classification FROM files WHERE id IN ({placeholders})",
            tuple(output_ids),
        ).fetchall()
        if len(output_rows) != len(output_ids):
            raise DesignPromotionConflict("release output manifest references a missing file")
        for output in output_rows:
            if output[3] != "internal":
                raise SensitiveCandidateRequiresRoleAxis(
                    "sensitive candidate requires the deferred role axis"
                )
            if output[1] != comparison["task_id"] or output[2] != "output":
                raise DesignPromotionConflict("release output membership drifted")
        file_row = conn.execute(
            "SELECT * FROM files WHERE id=?", (release["candidate_asset_file_id"],)
        ).fetchone()
        if file_row is None:
            raise DesignPromotionConflict("release candidate file is missing")
        record = dict(file_row)
        if record.get("classification") != "internal":
            raise SensitiveCandidateRequiresRoleAxis(
                "sensitive candidate requires the deferred role axis"
            )
        if record.get("task_id") != comparison["task_id"] or record.get("kind") != "output":
            raise DesignPromotionConflict("release candidate membership drifted")
        content = _read_verified_record(record, root=self._task_runs_dir)
        if hashlib.sha256(content).hexdigest() != release["candidate_asset_sha256"]:
            raise DesignPromotionConflict("release candidate hash drifted")
        try:
            validate_png(content)
        except CandidatePolicyError as exc:
            raise DesignPromotionConflict("release candidate PNG scan failed") from exc
        return content

    @staticmethod
    def _append_promotion_event(
        conn: sqlite3.Connection,
        *,
        attempt_id: str,
        release: dict[str, Any],
        decision: dict[str, Any],
        event_type: str,
        actor: Actor,
        before_kind: str,
        before_sha256: str | None,
        after_kind: str,
        after_sha256: str | None,
        backup_relative_path: str | None,
        backup_sha256: str | None,
        details: dict[str, Any],
        created_at: str,
        event_id: str | None = None,
    ) -> str:
        event_id = event_id or promotion_repo.public_id("promotion_event")
        promotion_repo.insert_publish_event(
            conn,
            event_id=event_id,
            attempt_id=attempt_id,
            release_request_id=release["id"],
            release_decision_id=decision["id"],
            event_type=event_type,
            actor_username=actor.username,
            actor_display_name=actor.display_name,
            release_package_sha256=decision["release_package_sha256"],
            target_id=release["target_id"],
            target_relative_path=release["target_relative_path"],
            before_kind=before_kind,
            before_sha256=before_sha256,
            after_kind=after_kind,
            after_sha256=after_sha256,
            backup_relative_path=backup_relative_path,
            backup_sha256=backup_sha256,
            details=details,
            details_sha256=canonical_sha256(details),
            created_at=created_at,
        )
        return event_id

    def _reconcile_release(self, release_request_id: str) -> None:
        lookup = self._conn_factory()
        try:
            release = promotion_repo.get_release_request(
                lookup, release_request_id=release_request_id
            )
            if release is None:
                return
            try:
                target = self._targets.by_id(release["target_id"])
            except TargetRegistryError as exc:
                raise DesignPromotionConflict(str(exc)) from exc
        finally:
            lookup.close()
        with _exclusive_file_lock(self._target_lock_path(target.target_id)):
            self._reconcile_release_locked(release_request_id, target)

    def _reconcile_release_locked(
        self, release_request_id: str, target: AssetTarget
    ) -> None:
        conn = self._conn_factory()
        try:
            release, decision, _comparison, bound_target = self._approved_release(
                conn, release_request_id
            )
            if bound_target != target:
                raise DesignPromotionConflict("reconciliation target binding drifted")
            events = promotion_repo.get_publish_events(conn, release_request_id)
            for event in events:
                if canonical_sha256(event["details"]) != event["details_sha256"]:
                    raise DesignPromotionConflict("publish event details hash drifted")
            _phase, pending, _latest = _publish_event_state(events)
            if pending is None:
                return
            observation_error: str | None = None
            try:
                target_path = _safe_target_path(
                    self._target_root, target.relative_path, require_file=False
                )
                current_kind, current_sha, _content = _snapshot_png_path(target_path)
            except DesignPromotionConflict:
                # Recovery is a read-only classification step.  A symlink,
                # corrupt PNG, unsafe parent, or unreadable target is neither
                # the durable preimage nor postimage; record a terminal manual
                # fact without trying to repair or move the file.
                current_kind, current_sha = "unreadable", None
                observation_error = "target_not_safely_readable"
            current = (current_kind, current_sha)
            before = (pending["before_kind"], pending["before_sha256"])
            after = (pending["after_kind"], pending["after_sha256"])
            prefix = "publish" if pending["event_type"] == "publish_intent" else "rollback"
            artifact_error: str | None = None
            if observation_error is not None:
                outcome = "manual_intervention"
            elif current == after:
                artifact_error = self._recovery_artifact_error(
                    pending, prefix=prefix
                )
                outcome = (
                    "recovered_commit"
                    if artifact_error is None
                    else "manual_intervention"
                )
            elif current == before:
                outcome = "abort"
            else:
                outcome = "manual_intervention"

            event_type = f"{prefix}_{outcome}"
            created_at = promotion_repo.now_iso()
            actor = Actor(
                username=pending["actor_username"],
                display_name=pending["actor_display_name"],
            )
            event_id = promotion_repo.public_id("promotion_event")
            public_result: dict[str, Any] | None = None
            if outcome == "recovered_commit" and prefix == "publish":
                assert pending["after_sha256"] is not None
                public_result = _published_result(
                    release_request_id=release_request_id,
                    event_id=event_id,
                    target_id=target.target_id,
                    before_sha256=pending["before_sha256"],
                    after_sha256=pending["after_sha256"],
                    backup_sha256=pending["backup_sha256"],
                    release_package_sha256=pending["release_package_sha256"],
                    actor=actor,
                    created_at=created_at,
                )
            elif outcome == "recovered_commit":
                assert pending["before_sha256"] is not None
                public_result = _rolled_back_result(
                    release_request_id=release_request_id,
                    event_id=event_id,
                    target_id=target.target_id,
                    before_sha256=pending["before_sha256"],
                    after_sha256=pending["after_sha256"],
                    backup_sha256=pending["backup_sha256"],
                    release_package_sha256=pending["release_package_sha256"],
                    actor=actor,
                    created_at=created_at,
                )
            details: dict[str, Any] = {
                "schema_version": "flai-design-publish-reconciliation/v1",
                "operation": prefix,
                "outcome": outcome,
                "observed_target": _expected_target_value(current_kind, current_sha),
                "public_result": public_result,
            }
            if observation_error is not None:
                details["observation_error"] = observation_error
            if artifact_error is not None:
                details["artifact_error"] = artifact_error
            conn.execute("BEGIN IMMEDIATE")
            try:
                current_events = promotion_repo.get_publish_events(
                    conn, release_request_id
                )
                _current_phase, current_pending, _current_result = _publish_event_state(
                    current_events
                )
                if (
                    current_pending is None
                    or current_pending["attempt_id"] != pending["attempt_id"]
                ):
                    raise DesignPromotionConflict(
                        "publication intent changed during reconciliation"
                    )
                self._append_promotion_event(
                    conn,
                    attempt_id=pending["attempt_id"],
                    release=release,
                    decision=decision,
                    event_type=event_type,
                    actor=actor,
                    before_kind=pending["before_kind"],
                    before_sha256=pending["before_sha256"],
                    after_kind=pending["after_kind"],
                    after_sha256=pending["after_sha256"],
                    backup_relative_path=pending["backup_relative_path"],
                    backup_sha256=pending["backup_sha256"],
                    details=details,
                    created_at=created_at,
                    event_id=event_id,
                )
                intent_details = pending["details"]
                if public_result is not None:
                    promotion_repo.insert_idempotent_response(
                        conn,
                        operation=prefix,
                        actor_username=actor.username,
                        request_id=intent_details["request_id"],
                        request_sha256=intent_details["request_sha256"],
                        response_status=200,
                        response=public_result,
                        response_sha256=canonical_sha256(public_result),
                        resource_id=event_id,
                        created_at=created_at,
                    )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()

    def _reconcile_task(self, task_id: str) -> None:
        conn = self._conn_factory()
        try:
            release_ids = [
                str(row[0])
                for row in conn.execute(
                    """
                    SELECT release.id
                    FROM design_release_requests AS release
                    JOIN design_comparisons AS comparison
                      ON comparison.id = release.comparison_id
                    WHERE comparison.task_id=?
                    ORDER BY release.rowid
                    """,
                    (task_id,),
                )
            ]
        finally:
            conn.close()
        for release_id in release_ids:
            self._reconcile_release(release_id)

    def create_comparison(
        self, body: ComparisonCreate, *, actor: Actor
    ) -> dict[str, Any]:
        request_sha = canonical_sha256(body.model_dump(mode="json"))
        self._reconcile_task(body.task_id)
        conn = self._conn_factory()
        conn.execute("BEGIN IMMEDIATE")
        try:
            try:
                replay = promotion_repo.get_idempotent_response(
                    conn,
                    operation="comparison_create",
                    actor_username=actor.username,
                    request_id=body.request_id,
                    request_sha256=request_sha,
                )
            except promotion_repo.IdempotencyConflict as exc:
                raise DesignPromotionConflict(str(exc)) from exc
            if replay is not None:
                conn.execute("COMMIT")
                return replay[1]

            existing = promotion_repo.get_comparisons_for_task(conn, body.task_id)
            for row in existing:
                selection = promotion_repo.get_selection(
                    conn, comparison_id=row["id"]
                )
                if selection is not None:
                    if canonical_sha256(row["comparison"]) != row["comparison_sha256"]:
                        raise DesignPromotionConflict("comparison evidence hash drifted")
                    phase, workflow = self._workflow_projection(conn, row["id"])
                    response = _public_comparison(
                        row["comparison"],
                        row["comparison_sha256"],
                        phase=phase,
                        workflow=workflow,
                    )
                    created_at = promotion_repo.now_iso()
                    promotion_repo.insert_idempotent_response(
                        conn,
                        operation="comparison_create",
                        actor_username=actor.username,
                        request_id=body.request_id,
                        request_sha256=request_sha,
                        response_status=201,
                        response=response,
                        response_sha256=canonical_sha256(response),
                        resource_id=row["id"],
                        created_at=created_at,
                    )
                    conn.execute("COMMIT")
                    return response

            evidence = self._load_candidate(conn, body.task_id)
            try:
                target = self._targets.by_slot(evidence.manifest.asset_slot)
            except TargetRegistryError as exc:
                raise DesignPromotionConflict(str(exc)) from exc
            target_frame_map = {frame.matrix_key: frame for frame in target.frames}
            if set(target_frame_map) != set(evidence.preview_files):
                raise DesignPromotionConflict("current and candidate frame matrices differ")
            before_kind, before_sha = self._target_snapshot(target)
            if existing:
                latest = existing[0]
                if canonical_sha256(latest["comparison"]) != latest["comparison_sha256"]:
                    raise DesignPromotionConflict("comparison evidence hash drifted")
                if (
                    latest["candidate_manifest_sha256"] != evidence.manifest_sha256
                    or latest["candidate_id"] != evidence.manifest.candidate_id
                    or latest["candidate_asset_sha256"]
                    != evidence.manifest.promotable_asset.sha256
                    or latest["asset_slot"] != evidence.manifest.asset_slot
                    or latest["target_id"] != target.target_id
                    or latest["target_relative_path"] != target.relative_path
                ):
                    raise DesignPromotionConflict(
                        "sealed candidate no longer matches its latest comparison"
                    )
                if (before_kind, before_sha) == (
                    latest["target_preimage_kind"],
                    latest["target_preimage_sha256"],
                ):
                    phase, workflow = self._workflow_projection(conn, latest["id"])
                    response = _public_comparison(
                        latest["comparison"],
                        latest["comparison_sha256"],
                        phase=phase,
                        workflow=workflow,
                    )
                    created_at = promotion_repo.now_iso()
                    promotion_repo.insert_idempotent_response(
                        conn,
                        operation="comparison_create",
                        actor_username=actor.username,
                        request_id=body.request_id,
                        request_sha256=request_sha,
                        response_status=201,
                        response=response,
                        response_sha256=canonical_sha256(response),
                        resource_id=latest["id"],
                        created_at=created_at,
                    )
                    conn.execute("COMMIT")
                    return response

            comparison_id = promotion_repo.public_id("comparison")
            created_at = promotion_repo.now_iso()
            frames: list[dict[str, Any]] = []
            for preview in evidence.manifest.passive_previews:
                current_frame: CurrentFrame = target_frame_map[preview.matrix_key]
                current_path = _safe_target_path(
                    self._target_root,
                    current_frame.relative_path,
                    require_file=True,
                )
                current_content, current_info = _read_bounded_png(current_path)
                candidate_file = evidence.preview_files[preview.matrix_key]
                candidate_info = validate_png(candidate_file.content)
                if current_info != candidate_info:
                    raise DesignPromotionConflict(
                        "current and candidate frame dimensions must match"
                    )
                frame_seed = {
                    "slot_id": preview.slot_id,
                    "viewport": preview.viewport.model_dump(mode="json"),
                    "state": preview.state,
                    "theme": preview.theme,
                    "locale": preview.locale,
                }
                frame_id = "frame_" + canonical_sha256(frame_seed)[:32]
                frames.append(
                    {
                        "frame_id": frame_id,
                        **frame_seed,
                        "current": {
                            "sha256": hashlib.sha256(current_content).hexdigest(),
                            **current_info,
                            "url": f"/api/design-comparisons/{comparison_id}/frames/{frame_id}/current.png",
                            "_relative_path": current_frame.relative_path,
                        },
                        "candidate": {
                            "sha256": str(candidate_file.record["sha256"]),
                            **candidate_info,
                            "scan": "passed",
                            "url": f"/api/design-comparisons/{comparison_id}/frames/{frame_id}/candidate.png",
                            "_file_id": str(candidate_file.record["id"]),
                        },
                    }
                )
            internal = {
                "schema_version": "flai-design-comparison/v1",
                "comparison_id": comparison_id,
                "task_id": body.task_id,
                "candidate": {
                    "candidate_id": evidence.manifest.candidate_id,
                    "asset_slot": evidence.manifest.asset_slot,
                    "asset_file_id": str(evidence.promotable.record["id"]),
                    "asset_sha256": evidence.manifest.promotable_asset.sha256,
                    "media_type": "image/png",
                    "execution_trust": "untrusted_generated",
                },
                "target": {
                    "target_id": target.target_id,
                    "relative_path": target.relative_path,
                    "preimage": {"kind": before_kind, **({"sha256": before_sha} if before_sha else {})},
                },
                "phase": "candidate_pending",
                "provenance": {
                    "mock": False,
                    "project_id": evidence.manifest.project_id,
                    "run_id": evidence.manifest.run_id,
                    "result_package_sha256": evidence.manifest.result_package_sha256,
                    "design_reference_package_sha256": evidence.manifest.design_reference_package_sha256,
                    "file_set_sha256": evidence.manifest.file_set_sha256,
                    "production_readiness": evidence.manifest.production_readiness,
                },
                "frames": frames,
                "created_by": actor.model_dump(mode="json"),
                "created_at": created_at,
            }
            comparison_sha = canonical_sha256(internal)
            response = _public_comparison(
                internal,
                comparison_sha,
                phase="candidate_pending",
                workflow={
                    "selection": None,
                    "release_request": None,
                    "release_decision": None,
                    "latest_publish": None,
                },
            )
            response_sha = canonical_sha256(response)
            promotion_repo.insert_comparison(
                conn,
                comparison_id=comparison_id,
                task_id=body.task_id,
                candidate_id=evidence.manifest.candidate_id,
                asset_slot=evidence.manifest.asset_slot,
                candidate_asset_file_id=str(evidence.promotable.record["id"]),
                candidate_asset_sha256=evidence.manifest.promotable_asset.sha256,
                candidate_manifest_sha256=evidence.manifest_sha256,
                comparison=internal,
                comparison_sha256=comparison_sha,
                target_id=target.target_id,
                target_relative_path=target.relative_path,
                target_preimage_kind=before_kind,
                target_preimage_sha256=before_sha,
                actor_username=actor.username,
                actor_display_name=actor.display_name,
                created_at=created_at,
            )
            promotion_repo.insert_idempotent_response(
                conn,
                operation="comparison_create",
                actor_username=actor.username,
                request_id=body.request_id,
                request_sha256=request_sha,
                response_status=201,
                response=response,
                response_sha256=response_sha,
                resource_id=comparison_id,
                created_at=created_at,
            )
            conn.execute("COMMIT")
            return response
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def get_comparison(self, comparison_id: str) -> dict[str, Any]:
        lookup = self._conn_factory()
        try:
            task_row = lookup.execute(
                "SELECT task_id FROM design_comparisons WHERE id=?", (comparison_id,)
            ).fetchone()
        finally:
            lookup.close()
        if task_row is not None:
            self._reconcile_task(str(task_row[0]))
        conn = self._conn_factory()
        try:
            row = promotion_repo.get_comparison(conn, comparison_id)
            if row is None:
                raise DesignPromotionNotFound("comparison does not exist")
            task_row = conn.execute(
                "SELECT data_classification FROM tasks WHERE id=?",
                (row["task_id"],),
            ).fetchone()
            if task_row is None:
                raise DesignPromotionConflict("comparison task is missing")
            if task_row[0] != "internal":
                raise SensitiveCandidateRequiresRoleAxis(
                    "sensitive candidate requires the deferred role axis"
                )
            internal = row["comparison"]
            if canonical_sha256(internal) != row["comparison_sha256"]:
                raise DesignPromotionConflict("comparison evidence hash drifted")
            phase, workflow = self._workflow_projection(conn, comparison_id)
            return _public_comparison(
                internal,
                row["comparison_sha256"],
                phase=phase,
                workflow=workflow,
            )
        finally:
            conn.close()

    def decide_candidate(
        self,
        comparison_id: str,
        body: SelectionRequest,
        *,
        actor: Actor,
    ) -> dict[str, Any]:
        """Append selection and the ordinary human decision in one transaction.

        ``human_review_applier`` is deliberately an injected transaction-
        participating primitive.  It must use the supplied ``decision_id`` and
        must not begin, commit, or roll back a transaction itself.
        """

        if self._human_review_applier is None:
            raise DesignPromotionConflict(
                "transaction-participating human review primitive is unavailable"
            )
        request_object = body.model_dump(mode="json")
        request_object["comparison_id"] = comparison_id
        request_sha = canonical_sha256(request_object)
        normalized_comment = _normalized_comment(body.comment)
        shared_comment = normalized_comment
        shared_reason = None
        if body.action == "reject":
            assert body.reason_code is not None
            shared_reason = "other"
            shared_comment = f"design_selection_reason={body.reason_code}"
            if normalized_comment is not None:
                shared_comment += "\n" + normalized_comment
            if len(shared_comment) > 2000:
                raise DesignPromotionError(
                    "candidate rejection comment is too long after canonical mapping"
                )

        conn = self._conn_factory()
        conn.execute("BEGIN IMMEDIATE")
        try:
            try:
                replay = promotion_repo.get_idempotent_response(
                    conn,
                    operation="candidate_selection",
                    actor_username=actor.username,
                    request_id=body.request_id,
                    request_sha256=request_sha,
                )
            except promotion_repo.IdempotencyConflict as exc:
                raise DesignPromotionConflict(str(exc)) from exc
            if replay is not None:
                conn.execute("COMMIT")
                return replay[1]

            row = promotion_repo.get_comparison(conn, comparison_id)
            if row is None:
                raise DesignPromotionNotFound("comparison does not exist")
            task_row = conn.execute(
                "SELECT data_classification FROM tasks WHERE id=?",
                (row["task_id"],),
            ).fetchone()
            if task_row is None:
                raise DesignPromotionConflict("comparison task is missing")
            if task_row[0] != "internal":
                raise SensitiveCandidateRequiresRoleAxis(
                    "sensitive candidate requires the deferred role axis"
                )
            internal = row["comparison"]
            if canonical_sha256(internal) != row["comparison_sha256"]:
                raise DesignPromotionConflict("comparison evidence hash drifted")
            if body.expected_comparison_sha256 != row["comparison_sha256"]:
                raise DesignPromotionConflict("expected comparison hash is stale")
            if promotion_repo.get_selection(conn, comparison_id=comparison_id) is not None:
                raise DesignPromotionConflict("comparison already has a named selection")
            if body.action == "approve" and body.candidate_id != row["candidate_id"]:
                raise DesignPromotionConflict("approved candidate_id is not exact")

            self._assert_comparison_inputs_unchanged(conn, row)
            selection_id = promotion_repo.public_id("selection")
            decision_id = promotion_repo.public_id("decision")
            created_at = promotion_repo.now_iso()
            selected_candidate_id = row["candidate_id"] if body.action == "approve" else None
            selected_candidate_sha = (
                row["candidate_asset_sha256"] if body.action == "approve" else None
            )
            promotion_repo.insert_selection(
                conn,
                selection_id=selection_id,
                comparison_id=comparison_id,
                task_id=row["task_id"],
                action=body.action,
                candidate_id=selected_candidate_id,
                candidate_asset_sha256=selected_candidate_sha,
                comparison_sha256=row["comparison_sha256"],
                task_decision_id=decision_id,
                actor_username=actor.username,
                actor_display_name=actor.display_name,
                reason_code=body.reason_code,
                comment=normalized_comment,
                created_at=created_at,
            )
            applied = self._human_review_applier(
                _TransactionParticipant(conn),
                task_id=row["task_id"],
                decision_id=decision_id,
                action=body.action,
                reviewer_username=actor.username,
                reviewer_display_name=actor.display_name,
                reason_code=shared_reason,
                comment=shared_comment,
            )
            if not conn.in_transaction:
                raise RuntimeError("human review primitive escaped the caller transaction")
            expected_status = "completed" if body.action == "approve" else "failed"
            if not isinstance(applied, dict) or applied.get("status") != expected_status:
                raise RuntimeError("human review primitive returned an invalid status")
            decision = conn.execute(
                "SELECT * FROM task_human_decisions WHERE id=? AND task_id=?",
                (decision_id, row["task_id"]),
            ).fetchone()
            task_status = conn.execute(
                "SELECT status FROM tasks WHERE id=?", (row["task_id"],)
            ).fetchone()
            if (
                decision is None
                or decision["action"] != body.action
                or decision["reviewer_username"] != actor.username
                or decision["reviewer_display_name"] != actor.display_name
                or decision["reason_code"] != shared_reason
                or decision["comment"] != shared_comment
                or decision["paired_advice_id"] is not None
                or decision["schema_version"] != 1
                or task_status is None
                or task_status[0] != expected_status
            ):
                raise RuntimeError("human review primitive did not persist the exact named fact")

            response = {
                "schema_version": "flai-design-selection/v1",
                "selection_id": selection_id,
                "comparison_id": comparison_id,
                "comparison_sha256": row["comparison_sha256"],
                "task_id": row["task_id"],
                "action": body.action,
                "candidate_id": selected_candidate_id,
                "candidate_sha256": selected_candidate_sha,
                "task_decision_id": decision_id,
                "selected_by": actor.model_dump(mode="json"),
                "reason_code": body.reason_code,
                "comment": normalized_comment,
                "created_at": created_at,
                "task_status": expected_status,
            }
            promotion_repo.insert_idempotent_response(
                conn,
                operation="candidate_selection",
                actor_username=actor.username,
                request_id=body.request_id,
                request_sha256=request_sha,
                response_status=200,
                response=response,
                response_sha256=canonical_sha256(response),
                resource_id=selection_id,
                created_at=created_at,
            )
            conn.execute("COMMIT")
            return response
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def create_release_request(
        self, body: ReleaseRequestCreate, *, actor: Actor
    ) -> dict[str, Any]:
        request_sha = canonical_sha256(body.model_dump(mode="json"))
        conn = self._conn_factory()
        conn.execute("BEGIN IMMEDIATE")
        try:
            try:
                replay = promotion_repo.get_idempotent_response(
                    conn,
                    operation="release_request_create",
                    actor_username=actor.username,
                    request_id=body.request_id,
                    request_sha256=request_sha,
                )
            except promotion_repo.IdempotencyConflict as exc:
                raise DesignPromotionConflict(str(exc)) from exc
            if replay is not None:
                conn.execute("COMMIT")
                return replay[1]

            selection = promotion_repo.get_selection(
                conn, selection_id=body.selection_id
            )
            if selection is None:
                raise DesignPromotionNotFound("candidate selection does not exist")
            if selection["action"] != "approve":
                raise DesignPromotionConflict("only an approved candidate can request release")
            if promotion_repo.get_release_request(
                conn, selection_id=body.selection_id
            ) is not None:
                raise DesignPromotionConflict("selection already has a release request")
            comparison = promotion_repo.get_comparison(
                conn, str(selection["comparison_id"])
            )
            if comparison is None:
                raise DesignPromotionConflict("selected comparison is missing")
            if canonical_sha256(comparison["comparison"]) != comparison["comparison_sha256"]:
                raise DesignPromotionConflict("comparison evidence hash drifted")
            if (
                body.expected_comparison_sha256 != selection["comparison_sha256"]
                or body.expected_comparison_sha256 != comparison["comparison_sha256"]
            ):
                raise DesignPromotionConflict("expected comparison hash is stale")
            if (
                body.expected_candidate_sha256
                != selection["candidate_asset_sha256"]
                or body.expected_candidate_sha256
                != comparison["candidate_asset_sha256"]
            ):
                raise DesignPromotionConflict("expected candidate hash is stale")
            expected_target = body.expected_target.model_dump(
                mode="json", exclude_none=True
            )
            bound_target = _expected_target_value(
                comparison["target_preimage_kind"],
                comparison["target_preimage_sha256"],
            )
            if expected_target != bound_target:
                raise DesignPromotionConflict("expected target preimage is not exact")
            if (
                comparison["target_preimage_kind"] == "present"
                and comparison["target_preimage_sha256"]
                == selection["candidate_asset_sha256"]
            ):
                raise DesignPromotionConflict(
                    "candidate identical to target cannot form a recoverable release"
                )
            self._assert_comparison_inputs_unchanged(
                conn,
                comparison,
                expected_task_status="completed",
                check_frames=False,
            )

            decision = conn.execute(
                "SELECT * FROM task_human_decisions WHERE id=? AND task_id=?",
                (selection["task_decision_id"], selection["task_id"]),
            ).fetchone()
            if (
                decision is None
                or decision["action"] != "approve"
                or decision["reviewer_username"] != selection["decided_by_username"]
            ):
                raise DesignPromotionConflict("candidate approval attribution is incomplete")
            release_request_id = promotion_repo.public_id("release")
            created_at = promotion_repo.now_iso()
            summary = {
                "candidate": {
                    "task_id": selection["task_id"],
                    "candidate_id": selection["candidate_id"],
                    "asset_slot": comparison["asset_slot"],
                    "asset_sha256": selection["candidate_asset_sha256"],
                    "comparison_sha256": selection["comparison_sha256"],
                    "candidate_approval": {
                        "decision_id": selection["task_decision_id"],
                        "username": selection["decided_by_username"],
                        "display_name": selection["decided_by_display_name"],
                        "at": decision["created_at"],
                    },
                },
                "target": {
                    "target_id": comparison["target_id"],
                    "relative_path": comparison["target_relative_path"],
                    "preimage": bound_target,
                    "postimage_sha256": selection["candidate_asset_sha256"],
                },
            }
            summary_sha = canonical_sha256(summary)
            promotion_repo.insert_release_request(
                conn,
                release_request_id=release_request_id,
                selection_id=selection["id"],
                comparison_id=comparison["id"],
                candidate_asset_file_id=comparison["candidate_asset_file_id"],
                candidate_asset_sha256=comparison["candidate_asset_sha256"],
                comparison_sha256=comparison["comparison_sha256"],
                target_id=comparison["target_id"],
                target_relative_path=comparison["target_relative_path"],
                target_preimage_kind=comparison["target_preimage_kind"],
                target_preimage_sha256=comparison["target_preimage_sha256"],
                summary=summary,
                summary_sha256=summary_sha,
                actor_username=actor.username,
                actor_display_name=actor.display_name,
                created_at=created_at,
            )
            release_row = promotion_repo.get_release_request(
                conn, release_request_id=release_request_id
            )
            assert release_row is not None
            response = _release_request_response(release_row)
            promotion_repo.insert_idempotent_response(
                conn,
                operation="release_request_create",
                actor_username=actor.username,
                request_id=body.request_id,
                request_sha256=request_sha,
                response_status=201,
                response=response,
                response_sha256=canonical_sha256(response),
                resource_id=release_request_id,
                created_at=created_at,
            )
            conn.execute("COMMIT")
            return response
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def decide_release(
        self,
        release_request_id: str,
        body: ReleaseDecisionRequest,
        *,
        actor: Actor,
    ) -> dict[str, Any]:
        request_object = body.model_dump(mode="json")
        request_object["release_request_id"] = release_request_id
        request_sha = canonical_sha256(request_object)
        comment = _normalized_comment(body.comment)
        conn = self._conn_factory()
        conn.execute("BEGIN IMMEDIATE")
        try:
            try:
                replay = promotion_repo.get_idempotent_response(
                    conn,
                    operation="release_decision",
                    actor_username=actor.username,
                    request_id=body.request_id,
                    request_sha256=request_sha,
                )
            except promotion_repo.IdempotencyConflict as exc:
                raise DesignPromotionConflict(str(exc)) from exc
            if replay is not None:
                conn.execute("COMMIT")
                return replay[1]

            release = promotion_repo.get_release_request(
                conn, release_request_id=release_request_id
            )
            if release is None:
                raise DesignPromotionNotFound("release request does not exist")
            if canonical_sha256(release["summary"]) != release["summary_sha256"]:
                raise DesignPromotionConflict("release summary hash drifted")
            if body.expected_summary_sha256 != release["summary_sha256"]:
                raise DesignPromotionConflict("expected release summary hash is stale")
            if promotion_repo.get_release_decision(conn, release_request_id) is not None:
                raise DesignPromotionConflict("release request already has a named decision")
            comparison = promotion_repo.get_comparison(conn, release["comparison_id"])
            if comparison is None:
                raise DesignPromotionConflict("release comparison is missing")
            self._assert_comparison_inputs_unchanged(
                conn,
                comparison,
                expected_task_status="completed",
                check_frames=False,
            )
            decision_id = promotion_repo.public_id("release_decision")
            created_at = promotion_repo.now_iso()
            release_package: dict[str, Any] | None = None
            release_package_sha: str | None = None
            if body.action == "approve":
                release_approval = {
                    "decision_id": decision_id,
                    "username": actor.username,
                    "display_name": actor.display_name,
                    "at": created_at,
                }
                unsigned_package = {
                    "schema_version": "flai-design-release-package/v1",
                    "summary": release["summary"],
                    "release_approval": release_approval,
                }
                release_package_sha = canonical_sha256(unsigned_package)
                release_package = {
                    "schema_version": "flai-design-release-package/v1",
                    "release_package_sha256": release_package_sha,
                    "summary": release["summary"],
                    "release_approval": release_approval,
                }
            promotion_repo.insert_release_decision(
                conn,
                decision_id=decision_id,
                release_request_id=release_request_id,
                action=body.action,
                summary_sha256=release["summary_sha256"],
                reason_code=body.reason_code,
                comment=comment,
                actor_username=actor.username,
                actor_display_name=actor.display_name,
                release_package=release_package,
                release_package_sha256=release_package_sha,
                created_at=created_at,
            )
            decision_row = promotion_repo.get_release_decision(
                conn, release_request_id
            )
            assert decision_row is not None
            response = _release_decision_response(decision_row)
            promotion_repo.insert_idempotent_response(
                conn,
                operation="release_decision",
                actor_username=actor.username,
                request_id=body.request_id,
                request_sha256=request_sha,
                response_status=200,
                response=response,
                response_sha256=canonical_sha256(response),
                resource_id=decision_id,
                created_at=created_at,
            )
            conn.execute("COMMIT")
            return response
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def publish_release(
        self,
        release_request_id: str,
        body: PublishRequest,
        *,
        actor: Actor,
    ) -> dict[str, Any]:
        request_object = body.model_dump(mode="json")
        request_object["release_request_id"] = release_request_id
        request_sha = canonical_sha256(request_object)
        lookup = self._conn_factory()
        try:
            release = promotion_repo.get_release_request(
                lookup, release_request_id=release_request_id
            )
            if release is None:
                raise DesignPromotionNotFound("release request does not exist")
            try:
                target = self._targets.by_id(release["target_id"])
            except TargetRegistryError as exc:
                raise DesignPromotionConflict(str(exc)) from exc
        finally:
            lookup.close()

        with _exclusive_file_lock(self._target_lock_path(target.target_id)):
            self._reconcile_release_locked(release_request_id, target)
            conn = self._conn_factory()
            conn.execute("BEGIN IMMEDIATE")
            try:
                try:
                    replay = promotion_repo.get_idempotent_response(
                        conn,
                        operation="publish",
                        actor_username=actor.username,
                        request_id=body.request_id,
                        request_sha256=request_sha,
                    )
                except promotion_repo.IdempotencyConflict as exc:
                    raise DesignPromotionConflict(str(exc)) from exc
                if replay is not None:
                    conn.execute("COMMIT")
                    return replay[1]
                release, decision, comparison, bound_target = self._approved_release(
                    conn, release_request_id
                )
                if bound_target != target:
                    raise DesignPromotionConflict("publish target binding drifted")
                if (
                    body.expected_release_package_sha256
                    != decision["release_package_sha256"]
                ):
                    raise DesignPromotionConflict("expected release package hash is stale")
                expected_target = body.expected_target.model_dump(
                    mode="json", exclude_none=True
                )
                release_preimage = _expected_target_value(
                    release["target_preimage_kind"], release["target_preimage_sha256"]
                )
                if expected_target != release_preimage:
                    raise DesignPromotionConflict("expected publish target is not exact")
                events = promotion_repo.get_publish_events(conn, release_request_id)
                phase, pending, _latest = _publish_event_state(events)
                if pending is not None or phase != "publish_ready":
                    raise DesignPromotionConflict("release is not ready for first publication")
                candidate_content = self._candidate_release_bytes(
                    conn, release, comparison
                )
                target_path = _safe_target_path(
                    self._target_root, target.relative_path, require_file=False
                )
                before_kind, before_sha, before_content = _snapshot_png_path(target_path)
                if _expected_target_value(before_kind, before_sha) != release_preimage:
                    raise DesignPromotionConflict("publish target preimage drifted")
                if before_sha == release["candidate_asset_sha256"]:
                    raise DesignPromotionConflict(
                        "candidate and target preimage must differ for recoverable publication"
                    )
                attempt_id = promotion_repo.public_id("attempt")
                backup_relative = (
                    f"backups/{attempt_id}.png" if before_kind == "present" else None
                )
                backup_sha = before_sha if before_kind == "present" else None
                intent_details = {
                    "schema_version": "flai-design-publish-intent/v1",
                    "operation": "publish",
                    "request_id": body.request_id,
                    "request_sha256": request_sha,
                    "candidate_asset_file_id": release["candidate_asset_file_id"],
                    "candidate_asset_sha256": release["candidate_asset_sha256"],
                    "expected_target": release_preimage,
                }
                intent_at = promotion_repo.now_iso()
                self._append_promotion_event(
                    conn,
                    attempt_id=attempt_id,
                    release=release,
                    decision=decision,
                    event_type="publish_intent",
                    actor=actor,
                    before_kind=before_kind,
                    before_sha256=before_sha,
                    after_kind="present",
                    after_sha256=release["candidate_asset_sha256"],
                    backup_relative_path=backup_relative,
                    backup_sha256=backup_sha,
                    details=intent_details,
                    created_at=intent_at,
                )
                conn.execute("COMMIT")
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

            self._fault("after_publish_intent")
            temp_path = target_path.with_name(f".{target_path.name}.{attempt_id}.tmp")
            try:
                current_kind, current_sha, current_content = _snapshot_png_path(target_path)
                if (current_kind, current_sha) != (before_kind, before_sha):
                    raise DesignPromotionConflict("publish target changed after durable intent")
                if before_kind == "present":
                    assert before_content is not None and current_content is not None
                    if current_content != before_content:
                        raise DesignPromotionConflict("publish preimage bytes changed")
                    assert backup_relative is not None and backup_sha is not None
                    backup_path = self._runtime_path(backup_relative)
                    _atomic_write_verified(
                        backup_path, before_content, expected_sha256=backup_sha
                    )
                    backup_content, _backup_info = _read_bounded_png(backup_path)
                    if hashlib.sha256(backup_content).hexdigest() != backup_sha:
                        raise DesignPromotionConflict("publication backup verification failed")
                self._fault("after_publish_backup")
                _write_new_fsynced(temp_path, candidate_content)
                temp_content, _temp_info = _read_bounded_png(temp_path)
                if hashlib.sha256(temp_content).hexdigest() != release["candidate_asset_sha256"]:
                    raise DesignPromotionConflict("publication temporary file hash drifted")
                cas_kind, cas_sha, _cas_content = _snapshot_png_path(target_path)
                if (cas_kind, cas_sha) != (before_kind, before_sha):
                    raise DesignPromotionConflict("publish target failed final CAS")
                os.replace(temp_path, target_path)
                _fsync_directory(target_path.parent)
                after_kind, after_sha, _after_content = _snapshot_png_path(target_path)
                if (after_kind, after_sha) != (
                    "present",
                    release["candidate_asset_sha256"],
                ):
                    raise DesignPromotionConflict("published target post-hash is not exact")
                self._fault("after_publish_replace")
            finally:
                try:
                    temp_path.unlink()
                except FileNotFoundError:
                    pass

            commit_conn = self._conn_factory()
            commit_conn.execute("BEGIN IMMEDIATE")
            try:
                current_events = promotion_repo.get_publish_events(
                    commit_conn, release_request_id
                )
                _phase, current_pending, _latest = _publish_event_state(current_events)
                if (
                    current_pending is None
                    or current_pending["attempt_id"] != attempt_id
                    or current_pending["event_type"] != "publish_intent"
                ):
                    raise DesignPromotionConflict("publish intent changed before commit")
                commit_at = promotion_repo.now_iso()
                event_id = promotion_repo.public_id("promotion_event")
                response = _published_result(
                    release_request_id=release_request_id,
                    event_id=event_id,
                    target_id=target.target_id,
                    before_sha256=before_sha,
                    after_sha256=release["candidate_asset_sha256"],
                    backup_sha256=backup_sha,
                    release_package_sha256=decision["release_package_sha256"],
                    actor=actor,
                    created_at=commit_at,
                )
                details = {
                    "schema_version": "flai-design-publish-commit/v1",
                    "operation": "publish",
                    "outcome": "commit",
                    "public_result": response,
                }
                self._append_promotion_event(
                    commit_conn,
                    attempt_id=attempt_id,
                    release=release,
                    decision=decision,
                    event_type="publish_commit",
                    actor=actor,
                    before_kind=before_kind,
                    before_sha256=before_sha,
                    after_kind="present",
                    after_sha256=release["candidate_asset_sha256"],
                    backup_relative_path=backup_relative,
                    backup_sha256=backup_sha,
                    details=details,
                    created_at=commit_at,
                    event_id=event_id,
                )
                promotion_repo.insert_idempotent_response(
                    commit_conn,
                    operation="publish",
                    actor_username=actor.username,
                    request_id=body.request_id,
                    request_sha256=request_sha,
                    response_status=200,
                    response=response,
                    response_sha256=canonical_sha256(response),
                    resource_id=event_id,
                    created_at=commit_at,
                )
                commit_conn.execute("COMMIT")
                return response
            except Exception:
                commit_conn.execute("ROLLBACK")
                raise
            finally:
                commit_conn.close()

    def rollback_release(
        self,
        release_request_id: str,
        body: RollbackRequest,
        *,
        actor: Actor,
    ) -> dict[str, Any]:
        request_object = body.model_dump(mode="json")
        request_object["release_request_id"] = release_request_id
        request_sha = canonical_sha256(request_object)
        lookup = self._conn_factory()
        try:
            release = promotion_repo.get_release_request(
                lookup, release_request_id=release_request_id
            )
            if release is None:
                raise DesignPromotionNotFound("release request does not exist")
            try:
                target = self._targets.by_id(release["target_id"])
            except TargetRegistryError as exc:
                raise DesignPromotionConflict(str(exc)) from exc
        finally:
            lookup.close()

        with _exclusive_file_lock(self._target_lock_path(target.target_id)):
            self._reconcile_release_locked(release_request_id, target)
            conn = self._conn_factory()
            conn.execute("BEGIN IMMEDIATE")
            try:
                try:
                    replay = promotion_repo.get_idempotent_response(
                        conn,
                        operation="rollback",
                        actor_username=actor.username,
                        request_id=body.request_id,
                        request_sha256=request_sha,
                    )
                except promotion_repo.IdempotencyConflict as exc:
                    raise DesignPromotionConflict(str(exc)) from exc
                if replay is not None:
                    conn.execute("COMMIT")
                    return replay[1]
                release, decision, comparison, bound_target = self._approved_release(
                    conn, release_request_id
                )
                if bound_target != target:
                    raise DesignPromotionConflict("rollback target binding drifted")
                if (
                    body.expected_release_package_sha256
                    != decision["release_package_sha256"]
                ):
                    raise DesignPromotionConflict("expected release package hash is stale")
                if body.expected_current_sha256 != release["candidate_asset_sha256"]:
                    raise DesignPromotionConflict("expected rollback current hash is stale")
                self._candidate_release_bytes(conn, release, comparison)
                events = promotion_repo.get_publish_events(conn, release_request_id)
                phase, pending, _latest = _publish_event_state(events)
                if pending is not None or phase != "published":
                    raise DesignPromotionConflict("release is not in a published state")
                publish_commits = [
                    event
                    for event in events
                    if event["event_type"]
                    in {"publish_commit", "publish_recovered_commit"}
                ]
                if len(publish_commits) != 1:
                    raise DesignPromotionConflict("published state lacks one exact commit")
                published = publish_commits[0]
                target_path = _safe_target_path(
                    self._target_root, target.relative_path, require_file=True
                )
                before_kind, before_sha, _before_content = _snapshot_png_path(target_path)
                if (before_kind, before_sha) != (
                    "present",
                    release["candidate_asset_sha256"],
                ):
                    raise DesignPromotionConflict("rollback current target drifted")
                restore_kind = published["before_kind"]
                restore_sha = published["before_sha256"]
                backup_relative = published["backup_relative_path"]
                backup_sha = published["backup_sha256"]
                restore_content: bytes | None = None
                if restore_kind == "present":
                    if (
                        restore_sha is None
                        or backup_relative is None
                        or backup_sha != restore_sha
                    ):
                        raise DesignPromotionConflict("rollback backup binding is incomplete")
                    backup_path = self._runtime_path(backup_relative)
                    if not backup_path.is_file() or backup_path.is_symlink():
                        raise DesignPromotionConflict("rollback backup is unavailable")
                    restore_content, _restore_info = _read_bounded_png(backup_path)
                    if hashlib.sha256(restore_content).hexdigest() != restore_sha:
                        raise DesignPromotionConflict("rollback backup hash drifted")
                elif (
                    restore_kind != "absent"
                    or restore_sha is not None
                    or backup_relative is not None
                    or backup_sha is not None
                ):
                    raise DesignPromotionConflict("rollback absent preimage is malformed")

                attempt_id = promotion_repo.public_id("attempt")
                quarantine_relative = (
                    f"{target.relative_path}.rollback-{attempt_id}.quarantine.png"
                    if restore_kind == "absent"
                    else None
                )
                intent_details = {
                    "schema_version": "flai-design-rollback-intent/v1",
                    "operation": "rollback",
                    "request_id": body.request_id,
                    "request_sha256": request_sha,
                    "expected_current_sha256": body.expected_current_sha256,
                    "restore_target": _expected_target_value(
                        restore_kind, restore_sha
                    ),
                    "quarantine_relative_path": quarantine_relative,
                }
                intent_at = promotion_repo.now_iso()
                self._append_promotion_event(
                    conn,
                    attempt_id=attempt_id,
                    release=release,
                    decision=decision,
                    event_type="rollback_intent",
                    actor=actor,
                    before_kind="present",
                    before_sha256=release["candidate_asset_sha256"],
                    after_kind=restore_kind,
                    after_sha256=restore_sha,
                    backup_relative_path=backup_relative,
                    backup_sha256=backup_sha,
                    details=intent_details,
                    created_at=intent_at,
                )
                conn.execute("COMMIT")
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

            self._fault("after_rollback_intent")
            temp_path = target_path.with_name(f".{target_path.name}.{attempt_id}.tmp")
            try:
                cas_kind, cas_sha, _cas_content = _snapshot_png_path(target_path)
                if (cas_kind, cas_sha) != (
                    "present",
                    release["candidate_asset_sha256"],
                ):
                    raise DesignPromotionConflict("rollback target failed final CAS")
                if restore_kind == "present":
                    assert restore_content is not None and restore_sha is not None
                    _write_new_fsynced(temp_path, restore_content)
                    temp_content, _temp_info = _read_bounded_png(temp_path)
                    if hashlib.sha256(temp_content).hexdigest() != restore_sha:
                        raise DesignPromotionConflict("rollback temporary hash drifted")
                    os.replace(temp_path, target_path)
                    _fsync_directory(target_path.parent)
                else:
                    assert quarantine_relative is not None
                    # Keep the quarantine beside the target.  os.replace is
                    # atomic only within one filesystem; promotion_runtime may
                    # be configured on another volume (especially Windows).
                    quarantine_path = _safe_target_path(
                        self._target_root,
                        quarantine_relative,
                        require_file=False,
                    )
                    if quarantine_path.exists():
                        raise DesignPromotionConflict("rollback quarantine already exists")
                    os.replace(target_path, quarantine_path)
                    _fsync_directory(target_path.parent)
                    quarantined, _quarantine_info = _read_bounded_png(quarantine_path)
                    if (
                        hashlib.sha256(quarantined).hexdigest()
                        != release["candidate_asset_sha256"]
                    ):
                        raise DesignPromotionConflict("rollback quarantine hash drifted")
                after_kind, after_sha, _after_content = _snapshot_png_path(target_path)
                if (after_kind, after_sha) != (restore_kind, restore_sha):
                    raise DesignPromotionConflict("rollback target post-hash is not exact")
                self._fault("after_rollback_replace")
            finally:
                try:
                    temp_path.unlink()
                except FileNotFoundError:
                    pass

            commit_conn = self._conn_factory()
            commit_conn.execute("BEGIN IMMEDIATE")
            try:
                current_events = promotion_repo.get_publish_events(
                    commit_conn, release_request_id
                )
                _phase, current_pending, _latest = _publish_event_state(current_events)
                if (
                    current_pending is None
                    or current_pending["attempt_id"] != attempt_id
                    or current_pending["event_type"] != "rollback_intent"
                ):
                    raise DesignPromotionConflict("rollback intent changed before commit")
                commit_at = promotion_repo.now_iso()
                event_id = promotion_repo.public_id("promotion_event")
                response = _rolled_back_result(
                    release_request_id=release_request_id,
                    event_id=event_id,
                    target_id=target.target_id,
                    before_sha256=release["candidate_asset_sha256"],
                    after_sha256=restore_sha,
                    backup_sha256=backup_sha,
                    release_package_sha256=decision["release_package_sha256"],
                    actor=actor,
                    created_at=commit_at,
                )
                details = {
                    "schema_version": "flai-design-rollback-commit/v1",
                    "operation": "rollback",
                    "outcome": "commit",
                    "public_result": response,
                }
                self._append_promotion_event(
                    commit_conn,
                    attempt_id=attempt_id,
                    release=release,
                    decision=decision,
                    event_type="rollback_commit",
                    actor=actor,
                    before_kind="present",
                    before_sha256=release["candidate_asset_sha256"],
                    after_kind=restore_kind,
                    after_sha256=restore_sha,
                    backup_relative_path=backup_relative,
                    backup_sha256=backup_sha,
                    details=details,
                    created_at=commit_at,
                    event_id=event_id,
                )
                promotion_repo.insert_idempotent_response(
                    commit_conn,
                    operation="rollback",
                    actor_username=actor.username,
                    request_id=body.request_id,
                    request_sha256=request_sha,
                    response_status=200,
                    response=response,
                    response_sha256=canonical_sha256(response),
                    resource_id=event_id,
                    created_at=commit_at,
                )
                commit_conn.execute("COMMIT")
                return response
            except Exception:
                commit_conn.execute("ROLLBACK")
                raise
            finally:
                commit_conn.close()

    def get_comparison_frame(
        self,
        comparison_id: str,
        frame_id: str,
        side: Literal["current", "candidate"],
    ) -> PngFrame:
        if side not in {"current", "candidate"}:
            raise DesignPromotionNotFound("comparison frame side does not exist")
        conn = self._conn_factory()
        try:
            row = promotion_repo.get_comparison(conn, comparison_id)
            if row is None:
                raise DesignPromotionNotFound("comparison does not exist")
            task_row = conn.execute(
                "SELECT data_classification FROM tasks WHERE id=?",
                (row["task_id"],),
            ).fetchone()
            if task_row is None:
                raise DesignPromotionConflict("comparison task is missing")
            if task_row[0] != "internal":
                raise SensitiveCandidateRequiresRoleAxis(
                    "sensitive candidate requires the deferred role axis"
                )
            internal = row["comparison"]
            if canonical_sha256(internal) != row["comparison_sha256"]:
                raise DesignPromotionConflict("comparison evidence hash drifted")
            matches = [item for item in internal.get("frames", []) if item.get("frame_id") == frame_id]
            if len(matches) != 1:
                raise DesignPromotionNotFound("comparison frame does not exist")
            frame = matches[0]
            expected = frame[side]["sha256"]
            if side == "current":
                path = _safe_target_path(
                    self._target_root,
                    frame["current"]["_relative_path"],
                    require_file=True,
                )
                content, info = _read_bounded_png(path)
            else:
                file_id = frame["candidate"]["_file_id"]
                file_row = conn.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
                if file_row is None:
                    raise DesignPromotionConflict("candidate frame file record is missing")
                record = dict(file_row)
                if record.get("classification") != "internal":
                    raise SensitiveCandidateRequiresRoleAxis(
                        "sensitive candidate requires the deferred role axis"
                    )
                if record.get("task_id") != row["task_id"] or record.get("kind") != "output":
                    raise DesignPromotionConflict("candidate frame membership is invalid")
                content = _read_verified_record(record, root=self._task_runs_dir)
                try:
                    info = validate_png(content)
                except CandidatePolicyError as exc:
                    raise DesignPromotionConflict("candidate frame PNG scan failed") from exc
            if hashlib.sha256(content).hexdigest() != expected:
                raise DesignPromotionConflict("comparison frame hash drifted")
            if info != {"width": frame[side]["width"], "height": frame[side]["height"]}:
                raise DesignPromotionConflict("comparison frame dimensions drifted")
            return PngFrame(content=content)
        finally:
            conn.close()
