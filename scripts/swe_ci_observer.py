#!/usr/bin/env python3
"""Validate and compare SWE-CI-inspired local verification evidence.

This is a monitor-only, standard-library tool.  It never executes verifier
commands and never makes a release, promotion, or human-signoff decision.
Without a separately trusted evidence producer, a successful observation proves
only that the supplied bundle is internally consistent and content-addressed.
This R0 implementation requires race-safe POSIX ``dir_fd``/``O_NOFOLLOW`` file
opening and fails closed on platforms, including Windows, that lack it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any


MANIFEST_SCHEMA = "flai.swe-ci-gate-manifest.v1"
ITERATION_SCHEMA = "flai.swe-ci-iteration.v1"
OBSERVATION_SCHEMA = "flai.swe-ci-observation.v1"
AUTHENTICITY = "UNATTESTED_SELF_CONSISTENCY_ONLY"
STATUS_PRECEDENCE = ("error", "unknown", "failed", "passed")
GATE_STATUSES = frozenset(STATUS_PRECEDENCE)

_MANIFEST_FIELDS = {
    "schema_version",
    "work_item_id",
    "baseline_commit",
    "max_iterations",
    "verifier_digest",
    "requirement_refs",
    "gates",
}
_GATE_FIELDS = {"name", "command"}
_ITERATION_FIELDS = {
    "schema_version",
    "work_item_id",
    "iteration",
    "baseline_commit",
    "candidate_commit",
    "gate_manifest_digest",
    "verifier_digest",
    "started_at",
    "finished_at",
    "exit_code",
    "artifact_root",
    "gate_results",
}
_GATE_RESULT_FIELDS = {
    "name",
    "status",
    "exit_code",
    "duration_ms",
    "log_path",
    "log_sha256",
}
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_GATE_NAME_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
_REQUIREMENT_REF_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/#-]{0,255}")
_RFC3339_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})"
)
RACE_SAFE_DIR_FD = (
    os.open in os.supports_dir_fd
    and hasattr(os, "O_DIRECTORY")
    and hasattr(os, "O_NOFOLLOW")
)


class EvidenceError(ValueError):
    """Raised when evidence cannot be trusted even as a self-consistent bundle."""


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise EvidenceError("value cannot be encoded as canonical JSON") from exc


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def manifest_digest(manifest: dict[str, Any]) -> str:
    """Return the frozen manifest digest; validation is performed by observe()."""

    return _sha256_bytes(_canonical_bytes(manifest))


def _reject_constant(value: str) -> None:
    raise EvidenceError(f"non-finite JSON value is forbidden: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if any(0xD800 <= ord(char) <= 0xDFFF for char in key):
            raise EvidenceError("Unicode surrogate is forbidden in JSON keys")
        if key in result:
            raise EvidenceError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _open_directory_nofollow(path: Path, label: str) -> int:
    if not RACE_SAFE_DIR_FD:
        raise EvidenceError(
            "platform lacks race-safe dir_fd and O_NOFOLLOW support"
        )
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory_fd: int | None = None
    try:
        if path.is_absolute():
            directory_fd = os.open(path.anchor, directory_flags)
            parts = path.parts[1:]
        else:
            directory_fd = os.open(".", directory_flags)
            parts = path.parts
        if any(part in {"", ".", ".."} for part in parts):
            raise EvidenceError(
                f"{label} directory must use canonical path components"
            )
        for part in parts:
            next_fd = os.open(part, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        return directory_fd
    except EvidenceError:
        if directory_fd is not None:
            os.close(directory_fd)
        raise
    except OSError as exc:
        if directory_fd is not None:
            os.close(directory_fd)
        raise EvidenceError(
            f"{label} directory is missing, unreadable, symlinked, or changed"
        ) from exc


def _file_version(file_stat: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_size,
        file_stat.st_mtime_ns,
        file_stat.st_ctime_ns,
    )


def _read_regular_file_nofollow(path: Path, label: str) -> bytes:
    directory_fd: int | None = None
    file_fd: int | None = None
    try:
        if not path.name or path.name in {".", ".."}:
            raise EvidenceError(f"{label} path must name a regular file")
        directory_fd = _open_directory_nofollow(path.parent, label)
        file_fd = os.open(
            path.name,
            os.O_RDONLY | os.O_NOFOLLOW,
            dir_fd=directory_fd,
        )
        file_stat = os.fstat(file_fd)
        if not stat.S_ISREG(file_stat.st_mode):
            raise EvidenceError(f"{label} must remain a regular file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(file_fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        if _file_version(os.fstat(file_fd)) != _file_version(file_stat):
            raise EvidenceError(f"{label} changed while being read")
        return b"".join(chunks)
    except EvidenceError:
        raise
    except OSError as exc:
        raise EvidenceError(
            f"{label} is missing, unreadable, symlinked, or changed"
        ) from exc
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if directory_fd is not None:
            os.close(directory_fd)


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = _read_regular_file_nofollow(path, label).decode("utf-8")
        value = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except EvidenceError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"{label} is not readable strict JSON: {exc}") from exc
    if type(value) is not dict:
        raise EvidenceError(f"{label} root must be a JSON object")
    return value


def _expect_fields(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing fields {missing}")
        if extra:
            details.append(f"extra fields {extra}")
        raise EvidenceError(f"{label}: {'; '.join(details)}")


def _expect_text(
    value: Any,
    label: str,
    *,
    max_length: int = 2048,
) -> str:
    if type(value) is not str or not value.strip() or len(value) > max_length:
        raise EvidenceError(f"{label} must be a non-empty string")
    if "\x00" in value:
        raise EvidenceError(f"{label} must not contain NUL")
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise EvidenceError(f"{label} must not contain a Unicode surrogate")
    return value


def _expect_int(
    value: Any,
    label: str,
    *,
    minimum: int = 0,
    maximum: int = 2_147_483_647,
) -> int:
    if type(value) is not int:
        raise EvidenceError(f"{label} must be an integer")
    if not minimum <= value <= maximum:
        raise EvidenceError(f"{label} must be between {minimum} and {maximum}")
    return value


def _expect_commit(value: Any, label: str) -> str:
    text = _expect_text(value, label, max_length=40)
    if _COMMIT_RE.fullmatch(text) is None:
        raise EvidenceError(f"{label} must be a lowercase full 40-hex commit")
    return text


def _expect_sha256(value: Any, label: str) -> str:
    text = _expect_text(value, label, max_length=64)
    if _SHA256_RE.fullmatch(text) is None:
        raise EvidenceError(f"{label} must be a lowercase 64-hex SHA-256")
    return text


def _expect_verifier_digest(value: Any, label: str) -> str:
    text = _expect_text(value, label, max_length=71)
    if not text.startswith("sha256:") or _SHA256_RE.fullmatch(text[7:]) is None:
        raise EvidenceError(f"{label} must use sha256:<64 lowercase hex>")
    return text


def _expect_timestamp(value: Any, label: str) -> datetime:
    text = _expect_text(value, label, max_length=64)
    if _RFC3339_RE.fullmatch(text) is None:
        raise EvidenceError(
            f"{label} must be RFC3339 and include a timezone offset"
        )
    try:
        parsed = datetime.fromisoformat(
            text[:-1] + "+00:00" if text.endswith("Z") else text
        )
    except ValueError as exc:
        raise EvidenceError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError(f"{label} must include a timezone offset")
    return parsed


def _expect_relative_posix(value: Any, label: str) -> PurePosixPath:
    text = _expect_text(value, label, max_length=512)
    path = PurePosixPath(text)
    if (
        text in {".", ".."}
        or "\\" in text
        or ":" in text
        or path.is_absolute()
        or path.as_posix() != text
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise EvidenceError(f"{label} must be a canonical relative POSIX path")
    return path


def _sha256_artifact_file(
    evidence_parent: Path,
    artifact_root: PurePosixPath,
    log_path: PurePosixPath,
    label: str,
) -> tuple[str, tuple[int, int]]:
    if not RACE_SAFE_DIR_FD:
        raise EvidenceError(
            "platform lacks race-safe dir_fd and O_NOFOLLOW support"
        )
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_NOFOLLOW
    directory_fd: int | None = None
    file_fd: int | None = None
    try:
        directory_fd = _open_directory_nofollow(evidence_parent, label)
        directory_parts = artifact_root.parts + log_path.parts[:-1]
        for part in directory_parts:
            next_fd = os.open(
                part,
                directory_flags,
                dir_fd=directory_fd,
            )
            os.close(directory_fd)
            directory_fd = next_fd
        file_fd = os.open(log_path.parts[-1], file_flags, dir_fd=directory_fd)
        file_stat = os.fstat(file_fd)
        if not stat.S_ISREG(file_stat.st_mode):
            raise EvidenceError(f"{label} must remain a regular file")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(file_fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        if _file_version(os.fstat(file_fd)) != _file_version(file_stat):
            raise EvidenceError(f"{label} changed while being read")
        return digest.hexdigest(), (file_stat.st_dev, file_stat.st_ino)
    except OSError as exc:
        raise EvidenceError(
            f"{label} is missing, unreadable, symlinked, or changed"
        ) from exc
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if directory_fd is not None:
            os.close(directory_fd)


def _validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    _expect_fields(manifest, _MANIFEST_FIELDS, "manifest")
    if manifest["schema_version"] != MANIFEST_SCHEMA:
        raise EvidenceError(f"manifest.schema_version must be {MANIFEST_SCHEMA}")

    work_item_id = _expect_text(
        manifest["work_item_id"], "manifest.work_item_id", max_length=128
    )
    if _NAME_RE.fullmatch(work_item_id) is None:
        raise EvidenceError("manifest.work_item_id has invalid characters")
    _expect_commit(manifest["baseline_commit"], "manifest.baseline_commit")
    _expect_int(
        manifest["max_iterations"],
        "manifest.max_iterations",
        minimum=1,
        maximum=20,
    )
    _expect_verifier_digest(
        manifest["verifier_digest"], "manifest.verifier_digest"
    )

    refs = manifest["requirement_refs"]
    if type(refs) is not list or not 1 <= len(refs) <= 5:
        raise EvidenceError("manifest.requirement_refs must contain one to five items")
    validated_refs = [
        _expect_text(ref, f"manifest.requirement_refs[{index}]", max_length=256)
        for index, ref in enumerate(refs)
    ]
    if any(_REQUIREMENT_REF_RE.fullmatch(ref) is None for ref in validated_refs):
        raise EvidenceError(
            "manifest.requirement_refs must use non-prose reference syntax"
        )
    if len(set(validated_refs)) != len(validated_refs):
        raise EvidenceError("manifest.requirement_refs contains duplicate references")

    gates = manifest["gates"]
    if type(gates) is not list or not 1 <= len(gates) <= 64:
        raise EvidenceError("manifest.gates must contain one to 64 named gates")
    gate_names: list[str] = []
    for index, gate in enumerate(gates):
        label = f"manifest.gates[{index}]"
        if type(gate) is not dict:
            raise EvidenceError(f"{label} must be an object")
        _expect_fields(gate, _GATE_FIELDS, label)
        name = _expect_text(gate["name"], f"{label}.name", max_length=64)
        if _GATE_NAME_RE.fullmatch(name) is None:
            raise EvidenceError(f"{label}.name has invalid characters")
        gate_names.append(name)
        command = gate["command"]
        if type(command) is not list or not 1 <= len(command) <= 64:
            raise EvidenceError(f"{label}.command must be a non-empty string array")
        for arg_index, arg in enumerate(command):
            _expect_text(arg, f"{label}.command[{arg_index}]", max_length=1024)
    if len(set(gate_names)) != len(gate_names):
        raise EvidenceError("manifest.gates contains duplicate gate names")

    return {
        "gate_names": gate_names,
        "digest": manifest_digest(manifest),
    }


def _derive_status(statuses: list[str]) -> str:
    for candidate in STATUS_PRECEDENCE:
        if candidate in statuses:
            return candidate
    raise EvidenceError("gate status list is empty")


def _validate_iteration(
    manifest: dict[str, Any],
    manifest_meta: dict[str, Any],
    evidence_path: Path,
) -> tuple[dict[str, Any], str]:
    evidence = _load_json(evidence_path, "evidence")
    _expect_fields(evidence, _ITERATION_FIELDS, "evidence")
    if evidence["schema_version"] != ITERATION_SCHEMA:
        raise EvidenceError(f"evidence.schema_version must be {ITERATION_SCHEMA}")
    if evidence["work_item_id"] != manifest["work_item_id"]:
        raise EvidenceError("evidence work_item_id does not match manifest")

    iteration = _expect_int(
        evidence["iteration"],
        "evidence.iteration",
        minimum=0,
        maximum=manifest["max_iterations"],
    )
    if evidence["baseline_commit"] != manifest["baseline_commit"]:
        raise EvidenceError("evidence baseline_commit does not match manifest")
    _expect_commit(evidence["baseline_commit"], "evidence.baseline_commit")
    _expect_commit(evidence["candidate_commit"], "evidence.candidate_commit")

    supplied_manifest_digest = _expect_sha256(
        evidence["gate_manifest_digest"], "evidence.gate_manifest_digest"
    )
    if supplied_manifest_digest != manifest_meta["digest"]:
        raise EvidenceError("manifest digest mismatch")
    supplied_verifier_digest = _expect_verifier_digest(
        evidence["verifier_digest"], "evidence.verifier_digest"
    )
    if supplied_verifier_digest != manifest["verifier_digest"]:
        raise EvidenceError("verifier digest mismatch")

    started_at = _expect_timestamp(evidence["started_at"], "evidence.started_at")
    finished_at = _expect_timestamp(evidence["finished_at"], "evidence.finished_at")
    if finished_at < started_at:
        raise EvidenceError("evidence.finished_at is before started_at")
    top_exit_code = _expect_int(
        evidence["exit_code"], "evidence.exit_code", minimum=0, maximum=255
    )

    artifact_rel = _expect_relative_posix(
        evidence["artifact_root"], "evidence.artifact_root"
    )

    results = evidence["gate_results"]
    if type(results) is not list:
        raise EvidenceError("evidence.gate_results must be an array")
    parsed_results: dict[str, dict[str, Any]] = {}
    seen_log_paths: set[str] = set()
    seen_log_identities: set[tuple[int, int]] = set()
    for index, result in enumerate(results):
        label = f"evidence.gate_results[{index}]"
        if type(result) is not dict:
            raise EvidenceError(f"{label} must be an object")
        _expect_fields(result, _GATE_RESULT_FIELDS, label)
        name = _expect_text(result["name"], f"{label}.name", max_length=64)
        if name in parsed_results:
            raise EvidenceError("evidence.gate_results contains duplicate gate names")
        status_value = _expect_text(
            result["status"], f"{label}.status", max_length=16
        )
        if status_value not in GATE_STATUSES:
            raise EvidenceError(
                f"{label}.status must be one of {sorted(GATE_STATUSES)}"
            )
        gate_exit_code = _expect_int(
            result["exit_code"], f"{label}.exit_code", minimum=0, maximum=255
        )
        if (status_value == "passed") is not (gate_exit_code == 0):
            raise EvidenceError(f"{label}.exit_code is inconsistent with status")
        duration_ms = _expect_int(
            result["duration_ms"], f"{label}.duration_ms", minimum=0
        )
        log_rel = _expect_relative_posix(
            result["log_path"], f"{label}.log_path"
        )
        if log_rel.as_posix() in seen_log_paths:
            raise EvidenceError("evidence.gate_results contains duplicate log_path")
        seen_log_paths.add(log_rel.as_posix())
        expected_log_digest = _expect_sha256(
            result["log_sha256"], f"{label}.log_sha256"
        )
        actual_log_digest, log_identity = _sha256_artifact_file(
            evidence_path.parent,
            artifact_rel,
            log_rel,
            f"{label}.log_path",
        )
        if log_identity in seen_log_identities:
            raise EvidenceError(
                "evidence.gate_results contains duplicate physical log file"
            )
        seen_log_identities.add(log_identity)
        if actual_log_digest != expected_log_digest:
            raise EvidenceError(f"{label} log digest mismatch")
        parsed_results[name] = {
            "name": name,
            "status": status_value,
            "exit_code": gate_exit_code,
            "duration_ms": duration_ms,
            "log_path": log_rel.as_posix(),
            "log_sha256": expected_log_digest,
        }

    expected_names = manifest_meta["gate_names"]
    if set(parsed_results) != set(expected_names) or len(parsed_results) != len(
        expected_names
    ):
        raise EvidenceError("evidence gate result set does not match manifest")
    ordered_results = [parsed_results[name] for name in expected_names]
    statuses = [result["status"] for result in ordered_results]
    all_passed = all(status_value == "passed" for status_value in statuses)
    if all_passed is not (top_exit_code == 0):
        raise EvidenceError(
            "evidence.exit_code is inconsistent with named gate results"
        )
    status_value = _derive_status(statuses)

    validated = dict(evidence)
    validated["iteration"] = iteration
    validated["gate_results"] = ordered_results
    return validated, status_value


def observe(
    manifest_path: str | Path,
    evidence_path: str | Path,
    previous_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate a current bundle and optionally compare the preceding iteration."""

    manifest_file = Path(manifest_path)
    evidence_file = Path(evidence_path)
    manifest = _load_json(manifest_file, "manifest")
    manifest_meta = _validate_manifest(manifest)
    current, current_status = _validate_iteration(
        manifest, manifest_meta, evidence_file
    )

    current_bundle_digest = _sha256_bytes(
        _canonical_bytes(
            {
                "gate_manifest_digest": manifest_meta["digest"],
                "evidence": current,
            }
        )
    )
    previous_bundle_digest: str | None = None
    regressions: list[dict[str, str]] = []
    zero_regression: bool | None = None
    if previous_path is not None:
        previous, _ = _validate_iteration(
            manifest, manifest_meta, Path(previous_path)
        )
        previous_bundle_digest = _sha256_bytes(
            _canonical_bytes(
                {
                    "gate_manifest_digest": manifest_meta["digest"],
                    "evidence": previous,
                }
            )
        )
        if previous["iteration"] + 1 != current["iteration"]:
            raise EvidenceError(
                "previous evidence must be the immediately preceding iteration"
            )
        previous_finished = _expect_timestamp(
            previous["finished_at"], "previous.finished_at"
        )
        current_started = _expect_timestamp(
            current["started_at"], "current.started_at"
        )
        if current_started < previous_finished:
            raise EvidenceError(
                "current iteration starts before previous finished"
            )
        previous_by_name = {
            result["name"]: result["status"] for result in previous["gate_results"]
        }
        for result in current["gate_results"]:
            if (
                previous_by_name[result["name"]] == "passed"
                and result["status"] != "passed"
            ):
                regressions.append(
                    {
                        "name": result["name"],
                        "current_status": result["status"],
                    }
                )
        zero_regression = not regressions

    observation_digest = _sha256_bytes(
        _canonical_bytes(
            {
                "current_bundle_digest": current_bundle_digest,
                "previous_bundle_digest": previous_bundle_digest,
                "status": current_status,
                "previously_passing_now_failed": regressions,
                "zero_regression_since_previous": zero_regression,
            }
        )
    )
    return {
        "schema_version": OBSERVATION_SCHEMA,
        "work_item_id": current["work_item_id"],
        "iteration": current["iteration"],
        "baseline_commit": current["baseline_commit"],
        "candidate_commit": current["candidate_commit"],
        "gate_manifest_digest": manifest_meta["digest"],
        "verifier_digest": current["verifier_digest"],
        "current_bundle_digest": current_bundle_digest,
        "previous_bundle_digest": previous_bundle_digest,
        "observation_digest": observation_digest,
        "status": current_status,
        "gate_results": [
            {"name": result["name"], "status": result["status"]}
            for result in current["gate_results"]
        ],
        "previously_passing_now_failed": regressions,
        "zero_regression_since_previous": zero_regression,
        "requirement_reference_count": len(manifest["requirement_refs"]),
        "named_gate_count": len(manifest_meta["gate_names"]),
        "evidence_authenticity": AUTHENTICITY,
        "automatic_gate_eligible": False,
        "human_signoff_required": True,
    }


def _render(value: dict[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    )


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise EvidenceError(f"invalid invocation: {message}")


def main(argv: list[str] | None = None) -> int:
    parser = _JsonArgumentParser(
        description=(
            "Validate a content-addressed verification bundle without executing it."
        )
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--previous", type=Path)
    try:
        args = parser.parse_args(argv)
        result = observe(args.manifest, args.evidence, args.previous)
    except EvidenceError as exc:
        result = {
            "schema_version": OBSERVATION_SCHEMA,
            "status": "invalid",
            "error": str(exc),
            "evidence_authenticity": AUTHENTICITY,
            "automatic_gate_eligible": False,
            "human_signoff_required": True,
        }
        print(_render(result))
        return 2

    print(_render(result))
    return 0 if result["status"] == "passed" else (
        1 if result["status"] == "failed" else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
