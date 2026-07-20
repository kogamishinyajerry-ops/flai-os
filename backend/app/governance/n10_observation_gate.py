"""Completeness gate for declared N10 novice-walkthrough observations.

The gate never creates participant records, authenticates real-world identity,
or changes roadmap state.  It only evaluates the supplied local record package.
"""

from __future__ import annotations

import json
import os
import re
import stat
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SCHEMA_PATH = REPO_ROOT / "contracts" / "n10-observation-package.schema.json"
PACKAGE_SCHEMA_VERSION = "n10-observation-package.v1"
REPORT_SCHEMA_VERSION = "n10-observation-gate-report.v1"
REQUIRED_ELIGIBLE_RECORDS = 2
MAX_PACKAGE_BYTES = 2 * 1024 * 1024
EXPECTED_STEP_IDS = tuple(f"N{index}" for index in range(1, 11))
_CANONICAL_TIME_FORMATS = ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ")
_NOT_ATTEMPTED_RESULTS = frozenset(
    {"not_reached_after_abort", "not_started_invalid_session"}
)
_NOT_ATTEMPTED_STEP_SENTINELS: dict[str, dict[str, Any]] = {
    "not_reached_after_abort": {
        "first_action": "未到达（此前已中止）",
        "stall_point": "未到达（此前已中止）",
        "participant_quote": {
            "status": "not_captured",
            "reason": "此前已中止，未向参与者提出此步骤",
        },
        "observer_interpretation": "未到达，不作参与者行为归因",
        "observable_result": "未到达（此前已中止）",
    },
    "not_started_invalid_session": {
        "first_action": "本场无效，任务步骤未开始",
        "stall_point": "本场无效，未观察步骤停滞",
        "participant_quote": {
            "status": "not_captured",
            "reason": "本场在任务开始前已判定无效",
        },
        "observer_interpretation": "未开始，不作参与者行为归因",
        "observable_result": "本场无效，任务步骤未开始",
    },
}
_INVISIBLE_EVIDENCE_CHARACTERS = frozenset(
    {"\u115f", "\u1160", "\u2800", "\u3164", "\uffa0"}
)
_RECORD_ID_RE = re.compile(r"N10-[0-9]{8}-P[A-Z0-9_-]{1,31}")
_PARTICIPANT_KEY_RE = re.compile(r"P[A-Z0-9_-]{1,31}")
_COMMIT_SHA_RE = re.compile(r"[0-9a-f]{40}")
_OBSERVER_USERNAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_STEP_ID_RE = re.compile(r"N(?:10|[1-9])")


@dataclass(frozen=True)
class GateFinding:
    code: str
    path: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "detail": self.detail}


@dataclass(frozen=True)
class N10RecordReport:
    structurally_complete: bool
    declared_eligible_n: int
    package_sha256: str | None
    findings: tuple[GateFinding, ...]
    eligible_builds: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": REPORT_SCHEMA_VERSION,
            "N10_DECLARED_RECORD_PACKAGE_STRUCTURALLY_COMPLETE": (
                self.structurally_complete
            ),
            "declared_eligible_n": self.declared_eligible_n,
            "required_n": REQUIRED_ELIGIBLE_RECORDS,
            "eligible_builds": list(self.eligible_builds),
            "package_sha256": self.package_sha256,
            "finding_count": len(self.findings),
            "findings": [finding.as_dict() for finding in self.findings],
            "owner_identity_confirmation_required": True,
            "roadmap_effect": "none",
            "m4_status": "not_evaluated",
            "boundary": (
                "structural completeness and declared distinct participant keys only; "
                "does not authenticate real humans, prove usability or M4, or unlock "
                "the roadmap"
            ),
        }


class _DuplicateKeyError(ValueError):
    pass


class _PackageTooLargeError(ValueError):
    pass


def _strict_object(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def _read_bounded_regular_file(path: Path) -> bytes:
    metadata = path.lstat()
    if stat.S_ISREG(metadata.st_mode) is not True:
        raise OSError("package path is not a regular file")
    if metadata.st_size > MAX_PACKAGE_BYTES:
        raise _PackageTooLargeError(
            f"package exceeds {MAX_PACKAGE_BYTES} bytes"
        )
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
            opened = os.fstat(handle.fileno())
            if stat.S_ISREG(opened.st_mode) is not True:
                raise OSError("opened package object is not a regular file")
            if opened.st_size > MAX_PACKAGE_BYTES:
                raise _PackageTooLargeError(
                    f"package exceeds {MAX_PACKAGE_BYTES} bytes"
                )
            raw = handle.read(MAX_PACKAGE_BYTES + 1)
            if len(raw) > MAX_PACKAGE_BYTES:
                raise _PackageTooLargeError(
                    f"package exceeds {MAX_PACKAGE_BYTES} bytes"
                )
            return raw
    finally:
        if fd >= 0:
            os.close(fd)


def _parse_canonical_time(value: str) -> datetime | None:
    for fmt in _CANONICAL_TIME_FORMATS:
        try:
            parsed = datetime.strptime(value, fmt)
        except ValueError:
            continue
        if fmt.endswith(".%fZ") and len(value.rsplit(".", 1)[-1]) != 7:
            continue
        return parsed
    return None


def _first_identity_error(record: dict[str, Any], index: int) -> GateFinding | None:
    checks: list[tuple[str, Any, re.Pattern[str]]] = [
        ("record_id", record["record_id"], _RECORD_ID_RE),
        ("participant_key", record["participant_key"], _PARTICIPANT_KEY_RE),
        ("observer_username", record["observer_username"], _OBSERVER_USERNAME_RE),
        ("build.commit_sha", record["build"]["commit_sha"], _COMMIT_SHA_RE),
    ]
    checks.extend(
        (f"steps[{step_index}].step_id", step["step_id"], _STEP_ID_RE)
        for step_index, step in enumerate(record["steps"])
    )
    checks.extend(
        (f"issues[{issue_index}].step_id", issue["step_id"], _STEP_ID_RE)
        for issue_index, issue in enumerate(record["issues"])
    )
    for relative_path, value, pattern in checks:
        if not isinstance(value, str) or pattern.fullmatch(value) is None:
            return GateFinding(
                "identity_format_invalid",
                f"$.records[{index}].{relative_path}",
                "identity fields must match their exact lexical contract",
            )
    return None


def _captured_text_value(value: dict[str, Any]) -> str:
    return value["text"] if value["status"] == "captured" else value["reason"]


def _has_substantive_text(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = unicodedata.normalize("NFKC", value)
    return any(
        character not in _INVISIBLE_EVIDENCE_CHARACTERS
        and "FILLER" not in unicodedata.name(character, "")
        and unicodedata.name(character, "") != "BRAILLE PATTERN BLANK"
        and unicodedata.category(character)[0] in {"L", "N"}
        for character in normalized
    )


def _not_attempted_step_matches_sentinel(step: dict[str, Any]) -> bool:
    expected = _NOT_ATTEMPTED_STEP_SENTINELS.get(step["result"])
    return expected is not None and all(
        step[field] == value for field, value in expected.items()
    )


def _first_blank_evidence(record: dict[str, Any], index: int) -> GateFinding | None:
    values: list[tuple[str, Any]] = [
        ("role_category", record["role_category"]),
        ("build.build_id", record["build"]["build_id"]),
        ("build.browser", record["build"]["browser"]),
        ("termination.detail", record["termination"]["detail"]),
    ]
    for step_index, step in enumerate(record["steps"]):
        step_path = f"steps[{step_index}]"
        values.extend(
            (
                (f"{step_path}.first_action", step["first_action"]),
                (f"{step_path}.stall_point", step["stall_point"]),
                (
                    f"{step_path}.participant_quote",
                    _captured_text_value(step["participant_quote"]),
                ),
                (
                    f"{step_path}.observer_interpretation",
                    step["observer_interpretation"],
                ),
                (f"{step_path}.observable_result", step["observable_result"]),
            )
        )
        if step["observer_rescue"] is not None:
            values.append(
                (f"{step_path}.observer_rescue", step["observer_rescue"])
            )
    values.extend(
        (f"exit_interview.{question}", _captured_text_value(answer))
        for question, answer in record["exit_interview"].items()
    )
    for issue_index, issue in enumerate(record["issues"]):
        values.append((f"issues[{issue_index}].observation", issue["observation"]))
        if issue["reproduction"] is not None:
            values.append(
                (f"issues[{issue_index}].reproduction", issue["reproduction"])
            )
    values.extend(
        (f"controlled_media_refs[{ref_index}]", value)
        for ref_index, value in enumerate(record["controlled_media_refs"])
    )
    for relative_path, value in values:
        if _has_substantive_text(value) is not True:
            return GateFinding(
                "blank_evidence",
                f"$.records[{index}].{relative_path}",
                "required observation evidence must contain non-whitespace text",
            )
    return None


def _abort_topology_is_valid(results: tuple[str, ...], abort_step: Any) -> bool:
    if abort_step not in EXPECTED_STEP_IDS:
        return False
    abort_index = EXPECTED_STEP_IDS.index(abort_step)
    return (
        results.count("aborted") == 1
        and results[abort_index] == "aborted"
        and all(
            result not in _NOT_ATTEMPTED_RESULTS and result != "aborted"
            for result in results[:abort_index]
        )
        and all(
            result == "not_reached_after_abort"
            for result in results[abort_index + 1 :]
        )
    )


def _termination_topology_is_valid(
    record: dict[str, Any],
    results: tuple[str, ...],
) -> bool:
    termination = record["termination"]
    kind = termination["kind"]
    at_step = termination["at_step"]
    if kind == "completed":
        return (
            record["environment_valid"] is True
            and at_step is None
            and all(
                result not in _NOT_ATTEMPTED_RESULTS and result != "aborted"
                for result in results
            )
        )
    if kind in {"participant_stopped", "product_blocker"}:
        return (
            record["environment_valid"] is True
            and _abort_topology_is_valid(results, at_step)
        )
    if kind == "environment_invalid":
        return record["environment_valid"] is False and (
            (
                at_step is None
                and all(
                    result == "not_started_invalid_session" for result in results
                )
            )
            or _abort_topology_is_valid(results, at_step)
        )
    if kind == "ineligible_participant":
        declared_ineligible = (
            record["participant_kind"] != "real_colleague"
            or record["novice_eligible"] is False
        )
        return declared_ineligible and (
            (
                at_step is None
                and all(
                    result == "not_started_invalid_session" for result in results
                )
            )
            or _abort_topology_is_valid(results, at_step)
        )
    return False


def evaluate_n10_observation_package(package_path: Path) -> N10RecordReport:
    """Derive record-package completeness without claiming real-world truth."""

    try:
        raw = _read_bounded_regular_file(Path(package_path))
    except _PackageTooLargeError as exc:
        return N10RecordReport(
            structurally_complete=False,
            declared_eligible_n=0,
            package_sha256=None,
            findings=(GateFinding("package_too_large", "$", str(exc)),),
        )
    except (OSError, TypeError, ValueError) as exc:
        return N10RecordReport(
            structurally_complete=False,
            declared_eligible_n=0,
            package_sha256=None,
            findings=(GateFinding("package_unreadable", "$", str(exc)),),
        )
    package_sha256 = sha256(raw).hexdigest()
    try:
        package = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        return N10RecordReport(
            structurally_complete=False,
            declared_eligible_n=0,
            package_sha256=package_sha256,
            findings=(GateFinding("package_invalid", "$", str(exc)),),
        )

    try:
        schema = json.loads(DEFAULT_SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except Exception as exc:  # jsonschema raises SchemaError, not ValueError.
        return N10RecordReport(
            structurally_complete=False,
            declared_eligible_n=0,
            package_sha256=package_sha256,
            findings=(GateFinding("schema_unavailable", "$", str(exc)),),
        )
    try:
        schema_errors = sorted(
            Draft202012Validator(schema).iter_errors(package),
            key=lambda error: (
                tuple(str(part) for part in error.absolute_path),
                error.message,
            ),
        )
    except Exception as exc:
        return N10RecordReport(
            structurally_complete=False,
            declared_eligible_n=0,
            package_sha256=package_sha256,
            findings=(GateFinding("schema_evaluation_failed", "$", str(exc)),),
        )
    if schema_errors:
        findings = tuple(
            GateFinding(
                "schema_invalid",
                "$"
                + "".join(
                    f"[{part}]" if isinstance(part, int) else f".{part}"
                    for part in error.absolute_path
                ),
                error.message,
            )
            for error in schema_errors
        )
        return N10RecordReport(
            structurally_complete=False,
            declared_eligible_n=0,
            package_sha256=package_sha256,
            findings=findings,
        )

    records = package.get("records", []) if isinstance(package, dict) else []
    findings: list[GateFinding] = []
    eligible_keys: set[str] = set()
    eligible_build_counts: dict[tuple[str, str, str], int] = {}
    record_ids: set[str] = set()
    for index, record in enumerate(records):
        identity_error = _first_identity_error(record, index)
        if identity_error is not None:
            findings.append(identity_error)
            continue
        blank_evidence = _first_blank_evidence(record, index)
        if blank_evidence is not None:
            findings.append(blank_evidence)
            continue
        record_id = unicodedata.normalize("NFKC", record["record_id"]).casefold()
        if record_id in record_ids:
            findings.append(
                GateFinding(
                    "duplicate_record",
                    f"$.records[{index}].record_id",
                    "record_id must be unique within the package",
                )
            )
            continue
        record_ids.add(record_id)
        started_at = _parse_canonical_time(record["started_at"])
        ended_at = _parse_canonical_time(record["ended_at"])
        attested_at = _parse_canonical_time(
            record["observer_attestation"]["attested_at"]
        )
        if (
            started_at is None
            or ended_at is None
            or attested_at is None
            or ended_at < started_at
            or attested_at < ended_at
        ):
            findings.append(
                GateFinding(
                    "timestamp_invalid",
                    f"$.records[{index}]",
                    "times must be real canonical UTC and start <= end <= attestation",
                )
            )
            continue
        step_ids = tuple(step["step_id"] for step in record["steps"])
        if step_ids != EXPECTED_STEP_IDS:
            findings.append(
                GateFinding(
                    "step_sequence_invalid",
                    f"$.records[{index}].steps",
                    "steps must appear exactly once in N1 through N10 order",
                )
            )
            continue
        results = tuple(step["result"] for step in record["steps"])
        if _termination_topology_is_valid(record, results) is not True:
            findings.append(
                GateFinding(
                    "termination_topology_invalid",
                    f"$.records[{index}].termination",
                    "termination and attempted/not-reached step topology disagree",
                )
            )
            continue
        missing_attempted_duration = next(
            (
                step_index
                for step_index, step in enumerate(record["steps"])
                if step["result"] not in _NOT_ATTEMPTED_RESULTS
                and step["duration_seconds"] is None
            ),
            None,
        )
        if missing_attempted_duration is not None:
            findings.append(
                GateFinding(
                    "step_observation_invalid",
                    (
                        f"$.records[{index}].steps"
                        f"[{missing_attempted_duration}].duration_seconds"
                    ),
                    "an attempted step requires an observed duration",
                )
            )
            continue
        attempted_steps = tuple(
            step
            for step in record["steps"]
            if step["result"] not in _NOT_ATTEMPTED_RESULTS
        )
        attempted_duration = sum(
            step["duration_seconds"]
            for step in attempted_steps
        )
        session_duration = (ended_at - started_at).total_seconds()
        if attempted_steps and (
            session_duration <= 0
            or attempted_duration <= 0
            or attempted_duration > session_duration
        ):
            findings.append(
                GateFinding(
                    "duration_invalid",
                    f"$.records[{index}]",
                    "attempted steps require positive observed duration within the session",
                )
            )
            continue
        fabricated_not_reached = next(
            (
                step_index
                for step_index, step in enumerate(record["steps"])
                if step["result"] in _NOT_ATTEMPTED_RESULTS
                and (
                    step["duration_seconds"] is not None
                    or step["observer_rescue"] is not None
                    or _not_attempted_step_matches_sentinel(step) is not True
                )
            ),
            None,
        )
        if fabricated_not_reached is not None:
            findings.append(
                GateFinding(
                    "step_observation_invalid",
                    f"$.records[{index}].steps[{fabricated_not_reached}]",
                    "a non-attempted step must use the exact no-observation sentinel",
                )
            )
            continue
        assisted_without_rescue = next(
            (
                step_index
                for step_index, step in enumerate(record["steps"])
                if step["result"] == "assisted"
                and not (
                    isinstance(step["observer_rescue"], str)
                    and step["observer_rescue"].strip()
                )
            ),
            None,
        )
        if assisted_without_rescue is not None:
            findings.append(
                GateFinding(
                    "rescue_contract_invalid",
                    (
                        f"$.records[{index}].steps"
                        f"[{assisted_without_rescue}].observer_rescue"
                    ),
                    "assisted requires the observer's verbatim rescue",
                )
            )
            continue
        unassisted_with_rescue = next(
            (
                step_index
                for step_index, step in enumerate(record["steps"])
                if step["result"] == "unassisted"
                and step["observer_rescue"] is not None
            ),
            None,
        )
        if unassisted_with_rescue is not None:
            findings.append(
                GateFinding(
                    "rescue_contract_invalid",
                    (
                        f"$.records[{index}].steps"
                        f"[{unassisted_with_rescue}].observer_rescue"
                    ),
                    "unassisted cannot carry observer rescue text",
                )
            )
            continue
        declared_eligible = (
            isinstance(record, dict)
            and record.get("participant_kind") == "real_colleague"
            and record.get("novice_eligible") is True
            and record.get("environment_valid") is True
            and record.get("termination", {}).get("kind")
            in {"completed", "participant_stopped", "product_blocker"}
            and record.get("observer_attestation", {}).get("observed_live") is True
            and record.get("observer_attestation", {}).get(
                "path_coaching_withheld"
            )
            is True
            and record.get("observer_attestation", {}).get(
                "recorded_contemporaneously"
            )
            is True
        )
        if declared_eligible is not True:
            continue
        key = unicodedata.normalize("NFKC", record["participant_key"]).casefold()
        if key in eligible_keys:
            findings.append(
                GateFinding(
                    "duplicate_participant",
                    f"$.records[{index}].participant_key",
                    "the same declared participant cannot increase eligible n twice",
                )
            )
            continue
        eligible_keys.add(key)
        build = record["build"]
        build_key = (
            build["commit_sha"],
            build["build_id"],
            build["gateway_mode"],
        )
        eligible_build_counts[build_key] = eligible_build_counts.get(build_key, 0) + 1

    declared_eligible_n = len(eligible_keys)
    if declared_eligible_n < REQUIRED_ELIGIBLE_RECORDS:
        findings.append(
            GateFinding(
                "eligible_sample_shortfall",
                "$.records",
                f"declared eligible records={declared_eligible_n}; required=2",
            )
        )
    return N10RecordReport(
        structurally_complete=len(findings) == 0,
        declared_eligible_n=declared_eligible_n,
        package_sha256=package_sha256,
        findings=tuple(findings),
        eligible_builds=tuple(
            {
                "commit_sha": commit_sha,
                "build_id": build_id,
                "gateway_mode": gateway_mode,
                "declared_eligible_n": eligible_build_counts[
                    (commit_sha, build_id, gateway_mode)
                ],
            }
            for commit_sha, build_id, gateway_mode in sorted(eligible_build_counts)
        ),
    )
