"""Fail-closed evaluator for the M4 scheduling signal package.

This module validates a locally mirrored evidence bundle.  It never creates
observations, changes roadmap state, proves N10, or grants Gate 1 authority.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator

from ..core.errors import FileIntegrityError
from ..storage.file_integrity import open_verified_relative_file


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SCHEMA_PATH = REPO_ROOT / "contracts" / "m4-signal-package.schema.json"
PACKAGE_SCHEMA_VERSION = "m4-signal-package.v1"
REPORT_SCHEMA_VERSION = "m4-signal-gate-report.v1"
MAX_PACKAGE_BYTES = 2 * 1024 * 1024
MAX_EVIDENCE_BYTES = 256 * 1024 * 1024

MANDATORY_ITEM_IDS = (
    "1-1",
    "1-2",
    "1-3",
    "1-4",
    "1-5",
    "1-6",
    "2-1",
    "2-2",
    "2-3",
    "2-4",
    "2-5",
    "2-6",
    "3-1",
    "3-2",
    "4-1",
    "4-2",
    "4-3",
    "5-1",
    "5-2",
    "5-3",
    "5-4",
    "5-5",
    "5-6",
)

_NON_APPLICABLE_FORBIDDEN = frozenset({"5-1", "5-2", "5-3", "5-5", "5-6"})
_CANONICAL_TIME_FORMATS = ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ")
_SPECIAL_ITEM_IDS = frozenset({"5-1", "5-2", "5-3", "5-4", "5-5", "5-6"})
_ITEM_REQUIRED_KIND_GROUPS: Mapping[str, tuple[frozenset[str], ...]] = {
    "1-1": (frozenset({"endpoint_probe"}),),
    "1-2": (frozenset({"endpoint_probe"}),),
    "1-3": (frozenset({"endpoint_probe"}),),
    "1-4": (frozenset({"endpoint_probe"}),),
    "1-5": (frozenset({"endpoint_probe"}),),
    "1-6": (
        frozenset({"endpoint_probe"}),
        frozenset({"model_inventory"}),
    ),
    "1-7": (frozenset({"report", "model_inventory"}),),
    "2-1": (frozenset({"command_output"}),),
    "2-2": (frozenset({"command_output"}),),
    "2-3": (frozenset({"command_output"}),),
    "2-4": (frozenset({"report"}),),
    "2-5": (frozenset({"command_output"}),),
    "2-6": (frozenset({"command_output"}),),
    "3-1": (frozenset({"report", "category_mapping"}),),
    "3-2": (frozenset({"report"}),),
    "3-3": (frozenset({"report"}),),
    "3-4": (frozenset({"report", "endpoint_probe"}),),
    "4-1": (frozenset({"report"}),),
    "4-2": (frozenset({"workflow_trace"}),),
    "4-3": (frozenset({"report", "policy_ruling"}),),
    "4-4": (frozenset({"report"}),),
}


@dataclass(frozen=True)
class GateFinding:
    code: str
    path: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "detail": self.detail}


@dataclass(frozen=True)
class GateReport:
    complete: bool
    package_sha256: str | None
    findings: tuple[GateFinding, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": REPORT_SCHEMA_VERSION,
            "M4_SIGNAL_PACKAGE_COMPLETE": self.complete,
            "package_sha256": self.package_sha256,
            "finding_count": len(self.findings),
            "findings": [finding.as_dict() for finding in self.findings],
            "boundary": (
                "M4 scheduling signal only; does not prove N10 and does not grant "
                "Gate 1 or deployment authority"
            ),
        }


class _DuplicateKeyError(ValueError):
    pass


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


class _FindingCollector:
    def __init__(self) -> None:
        self._findings: list[GateFinding] = []
        self._seen: set[tuple[str, str, str]] = set()

    def add(self, code: str, path: str, detail: str) -> None:
        key = (code, path, detail)
        if key not in self._seen:
            self._seen.add(key)
            self._findings.append(GateFinding(code=code, path=path, detail=detail))

    def freeze(self) -> tuple[GateFinding, ...]:
        return tuple(
            sorted(
                self._findings,
                key=lambda item: (item.path, item.code, item.detail),
            )
        )


def _strict_object(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _json_path(parts: Iterable[Any]) -> str:
    path = "$"
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}"
    return path


def _canonical_label(value: str) -> str | None:
    if any(unicodedata.category(character).startswith("C") for character in value):
        return None
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split()).casefold()


def _is_link_or_junction(path: Path) -> bool:
    """Reject symlinks and Windows reparse points on every supported Python.

    ``Path.is_junction`` only exists in newer Python releases.  Windows exposes
    junctions through the reparse-point file attribute, so inspect ``lstat``
    directly instead of silently weakening the check on Python 3.10/3.11.
    """

    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode):
        return True
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _read_bounded_regular_file(path: Path, max_bytes: int) -> bytes:
    """Read at most ``max_bytes`` from one no-follow regular-file handle."""

    try:
        if _is_link_or_junction(path):
            raise OSError("path is a symlink or junction")
        initial = path.lstat()
    except OSError:
        raise
    if stat.S_ISREG(initial.st_mode) is not True:
        raise OSError("path is not a regular file")
    if initial.st_size > max_bytes:
        raise OverflowError(f"file exceeds {max_bytes} bytes")

    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    fd = os.open(path, flags)
    try:
        with os.fdopen(fd, "rb") as handle:
            fd = -1
            actual = os.fstat(handle.fileno())
            if stat.S_ISREG(actual.st_mode) is not True:
                raise OSError("opened object is not a regular file")
            if actual.st_size > max_bytes:
                raise OverflowError(f"file exceeds {max_bytes} bytes")
            raw = handle.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise OverflowError(f"file exceeds {max_bytes} bytes")
            return raw
    finally:
        if fd >= 0:
            os.close(fd)


def _is_canonical_utc(value: str) -> bool:
    for fmt in _CANONICAL_TIME_FORMATS:
        try:
            parsed = datetime.strptime(value, fmt)
        except ValueError:
            continue
        if fmt.endswith(".%fZ") and len(value.rsplit(".", 1)[-1]) != 7:
            continue
        return parsed.tzinfo is None
    return False


def _load_package(
    path: Path,
) -> tuple[Mapping[str, Any] | None, str | None, GateFinding | None]:
    try:
        raw = _read_bounded_regular_file(path, MAX_PACKAGE_BYTES)
    except OverflowError as exc:
        return (
            None,
            None,
            GateFinding("package_invalid", "$", str(exc)),
        )
    except OSError as exc:
        return None, None, GateFinding("package_unreadable", "$", str(exc))
    package_sha256 = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8", errors="strict")
        package = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        _DuplicateKeyError,
        ValueError,
    ) as exc:
        return None, package_sha256, GateFinding("package_invalid", "$", str(exc))
    if not isinstance(package, dict):
        return (
            None,
            package_sha256,
            GateFinding("package_invalid", "$", "top-level JSON value must be an object"),
        )
    return package, package_sha256, None


def _load_schema(path: Path) -> Mapping[str, Any]:
    raw = path.read_text(encoding="utf-8")
    schema = json.loads(raw, object_pairs_hook=_strict_object)
    if not isinstance(schema, dict):
        raise ValueError("schema top-level value must be an object")
    Draft202012Validator.check_schema(schema)
    return schema


def _validate_schema(
    package: Mapping[str, Any],
    schema_path: Path,
    findings: _FindingCollector,
) -> bool:
    try:
        schema = _load_schema(schema_path)
    except Exception as exc:
        findings.add("schema_unavailable", "$", str(exc))
        return False
    errors = sorted(
        Draft202012Validator(schema).iter_errors(package),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.message,
        ),
    )
    for error in errors:
        findings.add("schema_invalid", _json_path(error.absolute_path), error.message)
    return not errors


def _resolve_evidence_file(root: Path, relative: str) -> tuple[Path | None, str | None]:
    if "\\" in relative or ":" in relative:
        return None, "evidence path must use portable forward-slash relative syntax"
    pure = PurePosixPath(relative)
    if (
        pure.is_absolute()
        or not pure.parts
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        return None, "evidence path must stay below evidence root"

    candidate = root
    for part in pure.parts:
        candidate = candidate / part
        try:
            if _is_link_or_junction(candidate):
                return None, "evidence path contains a symlink or junction"
        except FileNotFoundError:
            return None, "evidence file is not retrievable"
        except OSError as exc:
            return None, f"evidence path is not safely inspectable: {exc}"
    return candidate, None


@dataclass
class _EvaluationContext:
    root: Path
    actors: Mapping[str, Any]
    evidence: Mapping[str, Any]
    items: Mapping[str, Any]
    claims: Mapping[str, Any]
    findings: _FindingCollector
    valid_evidence: set[str]

    def actor_has(
        self,
        actor_id: str,
        authority: str | tuple[str, ...],
        *,
        person_only: bool = True,
    ) -> bool:
        actor = self.actors.get(actor_id)
        if not isinstance(actor, dict):
            return False
        if person_only and actor.get("kind") != "person":
            return False
        expected = (authority,) if isinstance(authority, str) else authority
        return any(value in actor.get("authorities", []) for value in expected)

    def check_evidence_ref(
        self,
        evidence_id: str,
        *,
        path: str,
        expected_kind: str | None = None,
        item_id: str | None = None,
        code: str = "claim_evidence_invalid",
    ) -> bool:
        record = self.evidence.get(evidence_id)
        ok = isinstance(record, dict) and evidence_id in self.valid_evidence
        if expected_kind is not None:
            ok = ok and record.get("kind") == expected_kind
        if item_id is not None:
            ok = ok and evidence_id in self.items[item_id]["evidence_ids"]
        if ok is not True:
            self.findings.add(
                code,
                path,
                "evidence is missing, untrusted, wrong-kind, or not bound "
                "to its checklist item",
            )
        return ok is True


def _validate_evidence_files(context: _EvaluationContext) -> None:
    seen_files: dict[tuple[Any, ...], str] = {}
    seen_digests: dict[str, str] = {}
    for evidence_id, record in context.evidence.items():
        record_path = f"$.evidence.{evidence_id}"
        candidate, error = _resolve_evidence_file(context.root, record["path"])
        if error is not None:
            context.findings.add("evidence_untrusted", f"{record_path}.path", error)
            continue
        assert candidate is not None
        try:
            expected_size = candidate.lstat().st_size
            if expected_size < 1:
                raise FileIntegrityError("evidence file is empty")
            if expected_size > MAX_EVIDENCE_BYTES:
                raise FileIntegrityError(
                    f"evidence file exceeds {MAX_EVIDENCE_BYTES} bytes"
                )
            handle = open_verified_relative_file(
                record["path"],
                allowed_root=context.root,
                expected_size=expected_size,
                expected_sha256=record["sha256"],
            )
            try:
                actual = os.fstat(handle.fileno())
                if actual.st_ino:
                    file_identity: tuple[Any, ...] = (
                        "inode",
                        actual.st_dev,
                        actual.st_ino,
                    )
                else:
                    file_identity = (
                        "path",
                        os.path.normcase(str(candidate.resolve(strict=True))),
                    )
            finally:
                handle.close()
        except (FileIntegrityError, FileNotFoundError, OSError) as exc:
            context.findings.add(
                "evidence_untrusted", record_path, f"evidence unreadable: {exc}"
            )
            continue

        existing_id = seen_files.get(file_identity)
        digest_alias_id = seen_digests.get(record["sha256"])
        if existing_id is not None or digest_alias_id is not None:
            original_id = existing_id or digest_alias_id
            context.findings.add(
                "evidence_alias",
                f"{record_path}.path",
                f"physical or byte-identical evidence is already registered as {original_id}",
            )
            continue
        seen_files[file_identity] = evidence_id
        seen_digests[record["sha256"]] = evidence_id
        context.valid_evidence.add(evidence_id)


def _validate_actor_identities(context: _EvaluationContext) -> None:
    for actor_id, actor in context.actors.items():
        context.check_evidence_ref(
            actor["identity_evidence_id"],
            path=f"$.actors.{actor_id}.identity_evidence_id",
            expected_kind="identity_mapping",
            code="actor_identity_untrusted",
        )


def _validate_not_applicable(
    context: _EvaluationContext,
    item_id: str,
    item: Mapping[str, Any],
) -> None:
    item_path = f"$.items.{item_id}"
    if item_id in _NON_APPLICABLE_FORBIDDEN:
        context.findings.add(
            "special_item_not_applicable",
            f"{item_path}.result",
            "this item requires substantive observed evidence",
        )
    ruling = item.get("applicability_ruling")
    if not isinstance(ruling, dict):
        context.findings.add(
            "applicability_ruling_invalid",
            item_path,
            "not_applicable requires a named business/IT owner ruling",
        )
    else:
        if context.actor_has(
            ruling["owner_id"], ("business_owner", "it_owner")
        ) is not True:
            context.findings.add(
                "applicability_ruling_invalid",
                f"{item_path}.applicability_ruling.owner_id",
                "ruling owner lacks business/IT authority",
            )
        context.check_evidence_ref(
            ruling["ruling_evidence_id"],
            path=f"{item_path}.applicability_ruling.ruling_evidence_id",
            expected_kind="policy_ruling",
            item_id=item_id,
            code="applicability_ruling_invalid",
        )
    if "negative_disposition" in item:
        context.findings.add(
            "item_shape_invalid",
            item_path,
            "not_applicable cannot also carry a negative disposition",
        )


def _validate_observed_no(
    context: _EvaluationContext,
    item_id: str,
    item: Mapping[str, Any],
) -> None:
    item_path = f"$.items.{item_id}"
    disposition = item.get("negative_disposition")
    if not isinstance(disposition, dict):
        context.findings.add(
            "negative_disposition_invalid",
            item_path,
            "observed_no requires an explicit named disposition",
        )
    else:
        if context.actor_has(
            disposition["policy_owner_id"], "policy_owner"
        ) is not True:
            context.findings.add(
                "negative_disposition_invalid",
                f"{item_path}.negative_disposition.policy_owner_id",
                "negative result requires a retrievable policy owner",
            )
        context.check_evidence_ref(
            disposition["ruling_evidence_id"],
            path=f"{item_path}.negative_disposition.ruling_evidence_id",
            expected_kind="policy_ruling",
            item_id=item_id,
            code="negative_disposition_invalid",
        )
        if disposition["outcome"] == "blocks":
            context.findings.add(
                "negative_result_blocks",
                f"{item_path}.negative_disposition.outcome",
                "observed negative result remains an explicit scheduling blocker",
            )
        elif not disposition["controls"]:
            context.findings.add(
                "negative_disposition_invalid",
                f"{item_path}.negative_disposition.controls",
                "accepted negative result requires at least one named control",
            )
        else:
            for index, control in enumerate(disposition["controls"]):
                context.check_evidence_ref(
                    control["evidence_id"],
                    path=(
                        f"{item_path}.negative_disposition.controls"
                        f"[{index}].evidence_id"
                    ),
                    expected_kind="policy_ruling",
                    item_id=item_id,
                    code="negative_disposition_invalid",
                )
    if "applicability_ruling" in item:
        context.findings.add(
            "item_shape_invalid",
            item_path,
            "observed_no cannot also claim not_applicable",
        )


def _validate_items(context: _EvaluationContext) -> None:
    for item_id, item in context.items.items():
        item_path = f"$.items.{item_id}"
        if _is_canonical_utc(item["observed_at"]) is not True:
            context.findings.add(
                "timestamp_invalid",
                f"{item_path}.observed_at",
                "timestamp must be a real canonical UTC instant",
            )
        if context.actor_has(item["observer_id"], "observer") is not True:
            context.findings.add(
                "observer_invalid",
                f"{item_path}.observer_id",
                "observer must be a retrievable person with observer authority",
            )
        for evidence_id in item["evidence_ids"]:
            context.check_evidence_ref(
                evidence_id,
                path=f"{item_path}.evidence_ids",
                code="item_evidence_untrusted",
            )
        if item_id not in _SPECIAL_ITEM_IDS and item["result"] != "not_applicable":
            evidence_kinds = {
                context.evidence[evidence_id]["kind"]
                for evidence_id in item["evidence_ids"]
                if evidence_id in context.valid_evidence
            }
            for required_group in _ITEM_REQUIRED_KIND_GROUPS[item_id]:
                if evidence_kinds.isdisjoint(required_group):
                    context.findings.add(
                        "item_evidence_kind_invalid",
                        f"{item_path}.evidence_ids",
                        "item validation method requires one evidence kind from: "
                        + ", ".join(sorted(required_group)),
                    )

        if item["result"] == "not_applicable":
            _validate_not_applicable(context, item_id, item)
        elif item["result"] == "observed_no":
            _validate_observed_no(context, item_id, item)
        elif "applicability_ruling" in item or "negative_disposition" in item:
            context.findings.add(
                "item_shape_invalid",
                item_path,
                "observed_yes cannot carry not-applicable or negative-disposition fields",
            )


def _validate_review_claims(context: _EvaluationContext) -> None:
    review = context.claims["review_relationship"]
    review_owner = review["business_owner_id"]
    if context.items["5-1"]["result"] != "observed_yes":
        context.findings.add(
            "review_relationship_invalid",
            "$.items.5-1.result",
            "real review relationship must be positively observed",
        )
    if context.actor_has(review_owner, "business_owner") is not True:
        context.findings.add(
            "review_relationship_invalid",
            "$.claims.review_relationship.business_owner_id",
            "review relationship requires a retrievable business owner",
        )
    context.check_evidence_ref(
        review["matrix_evidence_id"],
        path="$.claims.review_relationship.matrix_evidence_id",
        expected_kind="relationship_matrix",
        item_id="5-1",
        code="review_relationship_invalid",
    )

    separation = context.claims["separation_ruling"]
    if (
        context.items["5-2"]["result"] != "observed_yes"
        or separation["status"] != "defined"
    ):
        context.findings.add(
            "separation_ruling_undefined",
            "$.claims.separation_ruling.status",
            "undefined duties/self-review policy cannot unlock scheduling",
        )
    if separation["business_owner_id"] != review_owner:
        context.findings.add(
            "review_owner_mismatch",
            "$.claims.separation_ruling.business_owner_id",
            "5-2 ruling must come from the same owner who vouches for 5-1",
        )
    context.check_evidence_ref(
        separation["ruling_evidence_id"],
        path="$.claims.separation_ruling.ruling_evidence_id",
        expected_kind="policy_ruling",
        item_id="5-2",
        code="separation_ruling_undefined",
    )


def _validate_same_family_compensation(
    context: _EvaluationContext,
    compensation: Mapping[str, Any] | None,
) -> None:
    if not isinstance(compensation, dict):
        context.findings.add(
            "same_family_compensation_invalid",
            "$.claims.same_family_compensation",
            "same-family deployment requires deterministic and human-floor compensation",
        )
        return
    compensation_ids = (
        compensation["deterministic_verification_policy_evidence_id"],
        compensation["human_sampling_floor_policy_evidence_id"],
        compensation["ruling_evidence_id"],
    )
    if len(set(compensation_ids)) != 3:
        context.findings.add(
            "same_family_compensation_invalid",
            "$.claims.same_family_compensation",
            "deterministic policy, sampling floor, and owner ruling need distinct evidence",
        )
    if context.actor_has(compensation["policy_owner_id"], "policy_owner") is not True:
        context.findings.add(
            "same_family_compensation_invalid",
            "$.claims.same_family_compensation.policy_owner_id",
            "same-family compensation requires a retrievable policy owner",
        )
    for key in (
        "deterministic_verification_policy_evidence_id",
        "human_sampling_floor_policy_evidence_id",
        "ruling_evidence_id",
    ):
        context.check_evidence_ref(
            compensation[key],
            path=f"$.claims.same_family_compensation.{key}",
            expected_kind="policy_ruling",
            item_id="5-4",
            code="same_family_compensation_invalid",
        )


def _validate_model_claims(context: _EvaluationContext) -> None:
    model_family = context.claims["model_family"]
    for key, kind in (
        ("inventory_evidence_id", "model_inventory"),
        ("endpoint_probe_evidence_id", "endpoint_probe"),
    ):
        context.check_evidence_ref(
            model_family[key],
            path=f"$.claims.model_family.{key}",
            expected_kind=kind,
            item_id="5-3",
            code="model_family_invalid",
        )

    families = model_family["families"]
    canonical_families = [_canonical_label(value) for value in families]
    if any(not value for value in canonical_families) or len(
        set(canonical_families)
    ) != len(canonical_families):
        context.findings.add(
            "model_family_invalid",
            "$.claims.model_family.families",
            "base model families must remain distinct after NFKC, whitespace, "
            "and case normalization",
        )

    compensation = context.claims["same_family_compensation"]
    if model_family["second_family_available"] is True:
        if len(set(canonical_families)) < 2:
            context.findings.add(
                "model_family_invalid",
                "$.claims.model_family.families",
                "second-family claim requires at least two named base families",
            )
        if context.items["5-3"]["result"] != "observed_yes":
            context.findings.add(
                "model_family_invalid",
                "$.items.5-3.result",
                "second-family availability must match observed_yes",
            )
        if context.items["5-4"]["result"] != "not_applicable":
            context.findings.add(
                "same_family_compensation_invalid",
                "$.items.5-4.result",
                "5-4 is only not_applicable after a second family is actually verified",
            )
        if compensation is not None:
            context.findings.add(
                "same_family_compensation_invalid",
                "$.claims.same_family_compensation",
                "compensation must be null when a second family is verified",
            )
        return

    if context.items["5-3"]["result"] != "observed_no":
        context.findings.add(
            "model_family_invalid",
            "$.items.5-3.result",
            "absence of a second family must remain an observed_no result",
        )
    if context.items["5-4"]["result"] != "observed_yes":
        context.findings.add(
            "same_family_compensation_invalid",
            "$.items.5-4.result",
            "same-family compensation must be positively observed",
        )
    _validate_same_family_compensation(context, compensation)


def _validate_human_sign_floor(context: _EvaluationContext) -> None:
    floor = context.claims["permanent_human_sign_floor"]
    if context.items["5-5"]["result"] != "observed_yes":
        context.findings.add(
            "human_sign_floor_invalid",
            "$.items.5-5.result",
            "permanent floor must be positively confirmed",
        )
    if (
        type(floor["percent"]) is not int
        or floor["percent"] != 100
        or floor["configurable"] is not False
        or floor["unknown_category_action"] != "require_named_human_sign"
        or context.actor_has(
            floor["owner_id"], "data_export_control_owner"
        ) is not True
        or context.actor_has(floor["policy_owner_id"], "policy_owner") is not True
    ):
        context.findings.add(
            "human_sign_floor_invalid",
            "$.claims.permanent_human_sign_floor",
            "floor must be 100%, non-configurable, confirmed by data/export "
            "and policy owners, and fail closed for unknown categories",
        )
    for key, kind in (
        ("category_mapping_evidence_id", "category_mapping"),
        ("ruling_evidence_id", "policy_ruling"),
    ):
        context.check_evidence_ref(
            floor[key],
            path=f"$.claims.permanent_human_sign_floor.{key}",
            expected_kind=kind,
            item_id="5-5",
            code="human_sign_floor_invalid",
        )


def _validate_three_state_flow(context: _EvaluationContext) -> None:
    flow = context.claims["three_state_flow"]
    if context.items["5-6"]["result"] != "observed_yes":
        context.findings.add(
            "three_state_flow_collapsed",
            "$.items.5-6.result",
            "candidate, approval, and publication must be positively walked through",
        )
    steps = (flow["candidate"], flow["human_approval"], flow["publication"])
    canonical_states = [_canonical_label(step["state"]) for step in steps]
    canonical_actions = [_canonical_label(step["action"]) for step in steps]
    if (
        any(not value for value in canonical_states)
        or any(not value for value in canonical_actions)
        or len(set(canonical_states)) != 3
        or len(set(canonical_actions)) != 3
        or len({step["audit_evidence_id"] for step in steps}) != 3
    ):
        context.findings.add(
            "three_state_flow_collapsed",
            "$.claims.three_state_flow",
            "three steps require distinct states, actions, and audit evidence",
        )
    for name, step in flow.items():
        if step["actor_id"] not in context.actors:
            context.findings.add(
                "three_state_flow_invalid",
                f"$.claims.three_state_flow.{name}.actor_id",
                "flow actor is not registered and identity-bound",
            )
        context.check_evidence_ref(
            step["audit_evidence_id"],
            path=f"$.claims.three_state_flow.{name}.audit_evidence_id",
            expected_kind="workflow_trace",
            item_id="5-6",
            code="three_state_flow_invalid",
        )
    approval_actor = context.actors.get(flow["human_approval"]["actor_id"])
    if not isinstance(approval_actor, dict) or approval_actor.get("kind") != "person":
        context.findings.add(
            "three_state_flow_invalid",
            "$.claims.three_state_flow.human_approval.actor_id",
            "human approval actor must be a retrievable person",
        )


def evaluate_signal_package(
    package_path: Path,
    evidence_root: Path,
    *,
    schema_path: Path = DEFAULT_SCHEMA_PATH,
) -> GateReport:
    """Derive the M4 completion predicate from exact local evidence.

    Every uncertain, malformed, missing, drifting, or unresolvable input produces
    ``complete=False``.  The input cannot self-report the final boolean.
    """

    findings = _FindingCollector()
    package, package_sha256, load_error = _load_package(Path(package_path))
    if load_error is not None:
        findings.add(load_error.code, load_error.path, load_error.detail)
        return GateReport(False, package_sha256, findings.freeze())
    assert package is not None

    if _validate_schema(package, Path(schema_path), findings) is not True:
        return GateReport(False, package_sha256, findings.freeze())

    root_input = Path(evidence_root)
    try:
        root_is_link = _is_link_or_junction(root_input)
    except OSError as exc:
        findings.add(
            "evidence_untrusted",
            "$.evidence",
            f"evidence root unavailable: {exc}",
        )
        return GateReport(False, package_sha256, findings.freeze())
    if root_is_link:
        findings.add(
            "evidence_untrusted",
            "$.evidence",
            "evidence root itself cannot be a symlink or junction",
        )
        return GateReport(False, package_sha256, findings.freeze())
    try:
        root = root_input.resolve(strict=True)
    except OSError as exc:
        findings.add("evidence_untrusted", "$.evidence", f"evidence root unavailable: {exc}")
        return GateReport(False, package_sha256, findings.freeze())
    if root.is_dir() is not True:
        findings.add("evidence_untrusted", "$.evidence", "evidence root is not a directory")
        return GateReport(False, package_sha256, findings.freeze())

    context = _EvaluationContext(
        root=root,
        actors=package["actors"],
        evidence=package["evidence"],
        items=package["items"],
        claims=package["claims"],
        findings=findings,
        valid_evidence=set(),
    )
    _validate_evidence_files(context)
    _validate_actor_identities(context)
    _validate_items(context)
    _validate_review_claims(context)
    _validate_model_claims(context)
    _validate_human_sign_floor(context)
    _validate_three_state_flow(context)

    frozen = findings.freeze()
    return GateReport(len(frozen) == 0, package_sha256, frozen)
