"""SWE-CI-inspired evidence observer: strict contract and fail-closed tests.

The observer never runs a verifier.  These tests construct content-addressed
verification bundles and ensure status is derived from deterministic evidence,
not from an Agent-supplied claim.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "swe_ci_observer.py"
SPEC = importlib.util.spec_from_file_location("swe_ci_observer", SCRIPT)
assert SPEC and SPEC.loader
observer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(observer)

BASE_SHA = "a" * 40
CANDIDATE_SHA = "b" * 40
NEXT_SHA = "c" * 40
VERIFIER_DIGEST = "sha256:" + "d" * 64


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _manifest() -> dict:
    return {
        "schema_version": "flai.swe-ci-gate-manifest.v1",
        "work_item_id": "observer-test-001",
        "baseline_commit": BASE_SHA,
        "max_iterations": 20,
        "verifier_digest": VERIFIER_DIGEST,
        "requirement_refs": ["observer-test-001#R1"],
        "gates": [
            {
                "name": "python-tests",
                "command": ["python", "-m", "pytest", "-q"],
            },
            {
                "name": "scope-audit",
                "command": ["python", "scripts/scope_audit.py"],
            },
        ],
    }


def _bundle(
    root: Path,
    *,
    name: str,
    iteration: int,
    candidate_commit: str,
    statuses: dict[str, str],
    manifest: dict | None = None,
    exit_code: int | None = None,
) -> tuple[Path, Path, dict, dict]:
    manifest = json.loads(json.dumps(manifest or _manifest()))
    manifest_path = root / "manifest.json"
    _write_json(manifest_path, manifest)

    evidence_dir = root / name
    artifact_dir = evidence_dir / "artifacts"
    artifact_dir.mkdir(parents=True)
    gate_results = []
    for gate in manifest["gates"]:
        gate_name = gate["name"]
        status = statuses[gate_name]
        log_bytes = f"{gate_name}:{status}\n".encode()
        log_path = artifact_dir / f"{gate_name}.log"
        log_path.write_bytes(log_bytes)
        gate_results.append(
            {
                "name": gate_name,
                "status": status,
                "exit_code": 0 if status == "passed" else (1 if status == "failed" else 2),
                "duration_ms": 10,
                "log_path": f"{gate_name}.log",
                "log_sha256": hashlib.sha256(log_bytes).hexdigest(),
            }
        )
    if exit_code is None:
        if all(status == "passed" for status in statuses.values()):
            exit_code = 0
        elif any(status in {"error", "unknown"} for status in statuses.values()):
            exit_code = 2
        else:
            exit_code = 1
    started = datetime(2026, 7, 26, 2, 0, tzinfo=timezone.utc) + timedelta(
        seconds=iteration * 10
    )
    evidence = {
        "schema_version": "flai.swe-ci-iteration.v1",
        "work_item_id": manifest["work_item_id"],
        "iteration": iteration,
        "baseline_commit": manifest["baseline_commit"],
        "candidate_commit": candidate_commit,
        "gate_manifest_digest": observer.manifest_digest(manifest),
        "verifier_digest": manifest["verifier_digest"],
        "started_at": started.isoformat(),
        "finished_at": (started + timedelta(seconds=5)).isoformat(),
        "exit_code": exit_code,
        "artifact_root": "artifacts",
        "gate_results": gate_results,
    }
    evidence_path = evidence_dir / "iteration.json"
    _write_json(evidence_path, evidence)
    return manifest_path, evidence_path, manifest, evidence


def _observe(
    tmp_path: Path,
    *,
    statuses: dict[str, str] | None = None,
    previous: Path | None = None,
) -> dict:
    manifest_path, evidence_path, _, _ = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses=statuses
        or {"python-tests": "passed", "scope-audit": "passed"},
    )
    return observer.observe(manifest_path, evidence_path, previous)


def test_all_named_gates_pass_but_human_signoff_remains_required(tmp_path: Path) -> None:
    result = _observe(tmp_path)

    assert result["status"] == "passed"
    assert result["zero_regression_since_previous"] is None
    assert result["previously_passing_now_failed"] == []
    assert result["human_signoff_required"] is True
    assert result["evidence_authenticity"] == "UNATTESTED_SELF_CONSISTENCY_ONLY"
    assert result["automatic_gate_eligible"] is False
    assert len(result["current_bundle_digest"]) == 64
    assert result["previous_bundle_digest"] is None
    assert len(result["observation_digest"]) == 64


def test_previous_pass_to_current_failure_is_explicit_regression(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest_path, previous_path, _, _ = _bundle(
        tmp_path,
        name="previous",
        iteration=0,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "passed", "scope-audit": "passed"},
        manifest=manifest,
    )
    _, current_path, _, _ = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=NEXT_SHA,
        statuses={"python-tests": "failed", "scope-audit": "passed"},
        manifest=manifest,
    )

    result = observer.observe(manifest_path, current_path, previous_path)

    assert result["status"] == "failed"
    assert result["zero_regression_since_previous"] is False
    assert result["previously_passing_now_failed"] == [
        {"name": "python-tests", "current_status": "failed"}
    ]


def test_regression_is_compared_per_gate_even_when_previous_overall_failed(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    manifest_path, previous_path, _, _ = _bundle(
        tmp_path,
        name="previous",
        iteration=0,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "failed", "scope-audit": "passed"},
        manifest=manifest,
    )
    _, current_path, _, _ = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=NEXT_SHA,
        statuses={"python-tests": "passed", "scope-audit": "unknown"},
        manifest=manifest,
    )

    result = observer.observe(manifest_path, current_path, previous_path)

    assert result["status"] == "unknown"
    assert result["zero_regression_since_previous"] is False
    assert result["previously_passing_now_failed"] == [
        {"name": "scope-audit", "current_status": "unknown"}
    ]


def test_observation_digest_binds_the_previous_bundle(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest_path, previous_passed, _, _ = _bundle(
        tmp_path,
        name="previous-passed",
        iteration=0,
        candidate_commit=BASE_SHA,
        statuses={"python-tests": "passed", "scope-audit": "passed"},
        manifest=manifest,
    )
    _, previous_failed, _, _ = _bundle(
        tmp_path,
        name="previous-failed",
        iteration=0,
        candidate_commit=BASE_SHA,
        statuses={"python-tests": "failed", "scope-audit": "passed"},
        manifest=manifest,
    )
    _, current_path, _, _ = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "failed", "scope-audit": "passed"},
        manifest=manifest,
    )

    from_passed = observer.observe(manifest_path, current_path, previous_passed)
    from_failed = observer.observe(manifest_path, current_path, previous_failed)

    assert from_passed["current_bundle_digest"] == from_failed["current_bundle_digest"]
    assert from_passed["previous_bundle_digest"] != from_failed["previous_bundle_digest"]
    assert from_passed["observation_digest"] != from_failed["observation_digest"]
    assert from_passed["zero_regression_since_previous"] is False
    assert from_failed["zero_regression_since_previous"] is True


@pytest.mark.parametrize(
    ("gate_status", "expected"),
    [("error", "error"), ("unknown", "unknown")],
)
def test_error_and_unknown_never_collapse_to_failed_or_passed(
    tmp_path: Path,
    gate_status: str,
    expected: str,
) -> None:
    result = _observe(
        tmp_path,
        statuses={"python-tests": gate_status, "scope-audit": "passed"},
    )
    assert result["status"] == expected
    assert result["human_signoff_required"] is True


def test_agent_supplied_status_field_is_rejected(tmp_path: Path) -> None:
    manifest_path, evidence_path, _, evidence = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "failed", "scope-audit": "passed"},
    )
    evidence["status"] = "passed"
    _write_json(evidence_path, evidence)

    with pytest.raises(observer.EvidenceError, match="extra fields.*status"):
        observer.observe(manifest_path, evidence_path)


@pytest.mark.parametrize(
    ("field_path", "bad_value"),
    [
        (("iteration",), True),
        (("exit_code",), True),
        (("gate_results", 0, "duration_ms"), True),
        (("gate_results", 0, "exit_code"), True),
    ],
)
def test_truthy_booleans_are_not_accepted_as_integers(
    tmp_path: Path,
    field_path: tuple,
    bad_value: object,
) -> None:
    manifest_path, evidence_path, _, evidence = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "passed", "scope-audit": "passed"},
    )
    target: object = evidence
    for part in field_path[:-1]:
        target = target[part]  # type: ignore[index]
    target[field_path[-1]] = bad_value  # type: ignore[index]
    _write_json(evidence_path, evidence)

    with pytest.raises(observer.EvidenceError, match="must be an integer"):
        observer.observe(manifest_path, evidence_path)


@pytest.mark.parametrize("count", [0, 6])
def test_manifest_requires_one_to_five_requirements(
    tmp_path: Path,
    count: int,
) -> None:
    manifest = _manifest()
    manifest["requirement_refs"] = [f"observer-test-001#R{i}" for i in range(count)]
    manifest_path, evidence_path, _, _ = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "passed", "scope-audit": "passed"},
        manifest=manifest,
    )

    with pytest.raises(observer.EvidenceError, match="one to five"):
        observer.observe(manifest_path, evidence_path)


def test_requirement_refs_and_gate_names_must_be_unique(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["requirement_refs"] = ["observer-test-001#R1", "observer-test-001#R1"]
    manifest["gates"].append(
        {"name": "python-tests", "command": ["python", "-m", "pytest"]}
    )
    manifest_path, evidence_path, _, _ = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "passed", "scope-audit": "passed"},
        manifest=manifest,
    )

    with pytest.raises(observer.EvidenceError, match="duplicate"):
        observer.observe(manifest_path, evidence_path)


def test_requirement_reference_cannot_smuggle_prose_truth(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["requirement_refs"] = ["Implement everything and declare it resolved"]
    manifest_path, evidence_path, _, _ = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "passed", "scope-audit": "passed"},
        manifest=manifest,
    )

    with pytest.raises(observer.EvidenceError, match="reference syntax"):
        observer.observe(manifest_path, evidence_path)


@pytest.mark.parametrize("bad_value", [True, 0, 21])
def test_manifest_iteration_budget_is_strict_and_bounded(
    tmp_path: Path,
    bad_value: object,
) -> None:
    manifest = _manifest()
    manifest["max_iterations"] = bad_value
    manifest_path, evidence_path, _, _ = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "passed", "scope-audit": "passed"},
        manifest=manifest,
    )

    with pytest.raises(observer.EvidenceError, match="max_iterations"):
        observer.observe(manifest_path, evidence_path)


def test_gate_result_set_must_match_manifest_exactly(tmp_path: Path) -> None:
    manifest_path, evidence_path, _, evidence = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "passed", "scope-audit": "passed"},
    )
    evidence["gate_results"].pop()
    _write_json(evidence_path, evidence)

    with pytest.raises(observer.EvidenceError, match="gate result set"):
        observer.observe(manifest_path, evidence_path)


def test_manifest_digest_mismatch_fails_closed(tmp_path: Path) -> None:
    manifest_path, evidence_path, _, evidence = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "passed", "scope-audit": "passed"},
    )
    evidence["gate_manifest_digest"] = "0" * 64
    _write_json(evidence_path, evidence)

    with pytest.raises(observer.EvidenceError, match="manifest digest mismatch"):
        observer.observe(manifest_path, evidence_path)


def test_evidence_cannot_self_select_a_different_verifier(tmp_path: Path) -> None:
    manifest_path, evidence_path, _, evidence = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "passed", "scope-audit": "passed"},
    )
    evidence["verifier_digest"] = "sha256:" + "f" * 64
    _write_json(evidence_path, evidence)

    with pytest.raises(observer.EvidenceError, match="verifier digest mismatch"):
        observer.observe(manifest_path, evidence_path)


def test_log_digest_mismatch_fails_closed(tmp_path: Path) -> None:
    manifest_path, evidence_path, _, evidence = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "passed", "scope-audit": "passed"},
    )
    evidence["gate_results"][0]["log_sha256"] = "0" * 64
    _write_json(evidence_path, evidence)

    with pytest.raises(observer.EvidenceError, match="log digest mismatch"):
        observer.observe(manifest_path, evidence_path)


def test_two_gates_cannot_reuse_one_log_path(tmp_path: Path) -> None:
    manifest_path, evidence_path, _, evidence = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "passed", "scope-audit": "passed"},
    )
    first = evidence["gate_results"][0]
    second = evidence["gate_results"][1]
    second["log_path"] = first["log_path"]
    second["log_sha256"] = first["log_sha256"]
    _write_json(evidence_path, evidence)

    with pytest.raises(observer.EvidenceError, match="duplicate log_path"):
        observer.observe(manifest_path, evidence_path)


def test_two_gates_cannot_reuse_one_physical_log_file(tmp_path: Path) -> None:
    manifest_path, evidence_path, _, evidence = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "passed", "scope-audit": "passed"},
    )
    artifact_dir = evidence_path.parent / "artifacts"
    first = evidence["gate_results"][0]
    second = evidence["gate_results"][1]
    first_path = artifact_dir / first["log_path"]
    second_path = artifact_dir / second["log_path"]
    second_path.unlink()
    os.link(first_path, second_path)
    second["log_sha256"] = first["log_sha256"]
    _write_json(evidence_path, evidence)

    with pytest.raises(observer.EvidenceError, match="duplicate physical log file"):
        observer.observe(manifest_path, evidence_path)


@pytest.mark.parametrize(
    ("raw_fragment", "message"),
    [
        ('"work_item_id":"first","work_item_id":"second"', "duplicate JSON key"),
        ('"iteration":NaN', "non-finite JSON value"),
        ('"iteration":Infinity', "non-finite JSON value"),
    ],
)
def test_duplicate_keys_and_non_finite_json_are_rejected(
    tmp_path: Path,
    raw_fragment: str,
    message: str,
) -> None:
    manifest_path, evidence_path, _, evidence = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "passed", "scope-audit": "passed"},
    )
    if raw_fragment.startswith('"work_item_id"'):
        raw = evidence_path.read_text(encoding="utf-8")
        raw = raw.replace(
            '"work_item_id": "observer-test-001"',
            raw_fragment,
            1,
        )
    else:
        raw = evidence_path.read_text(encoding="utf-8")
        raw = raw.replace('"iteration": 1', raw_fragment, 1)
    evidence_path.write_text(raw, encoding="utf-8")

    with pytest.raises(observer.EvidenceError, match=message):
        observer.observe(manifest_path, evidence_path)


def test_isolated_unicode_surrogate_is_rejected_without_cli_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest_path, evidence_path, manifest, _ = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "passed", "scope-audit": "passed"},
    )
    raw = json.dumps(manifest, ensure_ascii=True, separators=(",", ":"))
    raw = raw.replace('"observer-test-001#R1"', '"\\ud800"', 1)
    manifest_path.write_text(raw, encoding="utf-8")

    assert observer.main(
        ["--manifest", str(manifest_path), "--evidence", str(evidence_path)]
    ) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "invalid"
    assert "Unicode surrogate" in payload["error"]


@pytest.mark.parametrize("bad_path", ["../escape.log", "/tmp/escape.log", r"..\escape.log"])
def test_log_path_escape_is_rejected(tmp_path: Path, bad_path: str) -> None:
    manifest_path, evidence_path, _, evidence = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "passed", "scope-audit": "passed"},
    )
    evidence["gate_results"][0]["log_path"] = bad_path
    _write_json(evidence_path, evidence)

    with pytest.raises(observer.EvidenceError, match="relative POSIX path"):
        observer.observe(manifest_path, evidence_path)


@pytest.mark.skipif(os.name == "nt", reason="Windows symlink creation may require elevation")
def test_symlinked_log_is_rejected(tmp_path: Path) -> None:
    manifest_path, evidence_path, _, evidence = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "passed", "scope-audit": "passed"},
    )
    log_path = evidence_path.parent / "artifacts" / "python-tests.log"
    outside = tmp_path / "outside.log"
    outside.write_text("python-tests:passed\n", encoding="utf-8")
    log_path.unlink()
    log_path.symlink_to(outside)
    evidence["gate_results"][0]["log_sha256"] = hashlib.sha256(outside.read_bytes()).hexdigest()
    _write_json(evidence_path, evidence)

    with pytest.raises(observer.EvidenceError, match="symlink"):
        observer.observe(manifest_path, evidence_path)


@pytest.mark.skipif(os.name == "nt", reason="Windows symlink creation may require elevation")
def test_symlinked_artifact_root_is_rejected(tmp_path: Path) -> None:
    manifest_path, evidence_path, _, _ = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "passed", "scope-audit": "passed"},
    )
    artifact_root = evidence_path.parent / "artifacts"
    moved = evidence_path.parent / "moved-artifacts"
    artifact_root.rename(moved)
    artifact_root.symlink_to(moved, target_is_directory=True)

    with pytest.raises(observer.EvidenceError, match="symlink"):
        observer.observe(manifest_path, evidence_path)


@pytest.mark.skipif(
    not observer.RACE_SAFE_DIR_FD,
    reason="race-safe dir_fd traversal unavailable on this platform",
)
def test_symlinked_json_ancestor_is_rejected(tmp_path: Path) -> None:
    real_root = tmp_path / "real-bundle"
    _, _, _, _ = _bundle(
        real_root,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "passed", "scope-audit": "passed"},
    )
    alias_root = tmp_path / "bundle-alias"
    alias_root.symlink_to(real_root, target_is_directory=True)

    with pytest.raises(observer.EvidenceError, match="symlink"):
        observer.observe(
            alias_root / "manifest.json",
            alias_root / "current" / "iteration.json",
        )


@pytest.mark.skipif(
    not observer.RACE_SAFE_DIR_FD,
    reason="race-safe dir_fd traversal unavailable on this platform",
)
@pytest.mark.parametrize("target", ["manifest", "evidence"])
def test_json_file_swap_cannot_redirect_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    manifest_path, evidence_path, manifest, evidence = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "passed", "scope-audit": "passed"},
    )
    target_path = manifest_path if target == "manifest" else evidence_path
    outside_path = tmp_path / f"outside-{target}.json"
    _write_json(outside_path, manifest if target == "manifest" else evidence)
    real_open = observer.os.open
    swapped = False

    def swapping_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if (
            path == target_path.name
            and kwargs.get("dir_fd") is not None
            and not swapped
        ):
            moved_path = target_path.with_name(f"{target_path.name}.before-swap")
            target_path.rename(moved_path)
            target_path.symlink_to(outside_path)
            swapped = True
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(observer.os, "open", swapping_open)
    with pytest.raises(observer.EvidenceError, match="symlink"):
        observer.observe(manifest_path, evidence_path)
    assert swapped is True


@pytest.mark.skipif(
    not observer.RACE_SAFE_DIR_FD,
    reason="race-safe dir_fd traversal unavailable on this platform",
)
def test_parent_directory_swap_cannot_redirect_log_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, evidence_path, _, evidence = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "passed", "scope-audit": "passed"},
    )
    artifact_root = evidence_path.parent / "artifacts"
    logs = artifact_root / "logs"
    logs.mkdir()
    original_log = artifact_root / "python-tests.log"
    nested_log = logs / "python-tests.log"
    original_log.rename(nested_log)
    external = tmp_path / "external"
    external.mkdir()
    external_log = external / "python-tests.log"
    external_log.write_text("forged external log\n", encoding="utf-8")
    result = evidence["gate_results"][0]
    result["log_path"] = "logs/python-tests.log"
    result["log_sha256"] = hashlib.sha256(external_log.read_bytes()).hexdigest()
    _write_json(evidence_path, evidence)

    real_open = observer.os.open
    swapped = False

    def swapping_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if path == "python-tests.log" and kwargs.get("dir_fd") is not None and not swapped:
            moved = artifact_root / "logs-before-swap"
            logs.rename(moved)
            logs.symlink_to(external, target_is_directory=True)
            swapped = True
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(observer.os, "open", swapping_open)
    with pytest.raises(observer.EvidenceError, match="log digest mismatch"):
        observer.observe(manifest_path, evidence_path)
    assert swapped is True
    assert logs.is_symlink()


@pytest.mark.parametrize(
    ("started", "finished", "message"),
    [
        (
            "2026-07-26T10:00:00",
            "2026-07-26T10:00:05+08:00",
            "timezone offset",
        ),
        (
            "2026-07-26 10:00:00+08:00",
            "2026-07-26T10:00:05+08:00",
            "RFC3339",
        ),
        (
            "2026-07-26T10:00:05+08:00",
            "2026-07-26T10:00:00+08:00",
            "before started_at",
        ),
    ],
)
def test_time_evidence_is_offset_aware_and_ordered(
    tmp_path: Path,
    started: str,
    finished: str,
    message: str,
) -> None:
    manifest_path, evidence_path, _, evidence = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "passed", "scope-audit": "passed"},
    )
    evidence["started_at"] = started
    evidence["finished_at"] = finished
    _write_json(evidence_path, evidence)

    with pytest.raises(observer.EvidenceError, match=message):
        observer.observe(manifest_path, evidence_path)


@pytest.mark.parametrize(
    ("statuses", "exit_code"),
    [
        ({"python-tests": "passed", "scope-audit": "passed"}, 1),
        ({"python-tests": "failed", "scope-audit": "passed"}, 0),
    ],
)
def test_top_level_exit_code_must_agree_with_named_gates(
    tmp_path: Path,
    statuses: dict[str, str],
    exit_code: int,
) -> None:
    manifest_path, evidence_path, _, _ = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses=statuses,
        exit_code=exit_code,
    )

    with pytest.raises(observer.EvidenceError, match="exit_code is inconsistent"):
        observer.observe(manifest_path, evidence_path)


def test_mixed_status_precedence_is_error_then_unknown_then_failed(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    manifest["gates"].append(
        {"name": "link-audit", "command": ["python", "scripts/link_audit.py"]}
    )
    manifest_path, evidence_path, _, _ = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses={
            "python-tests": "failed",
            "scope-audit": "unknown",
            "link-audit": "error",
        },
        manifest=manifest,
    )
    assert observer.observe(manifest_path, evidence_path)["status"] == "error"


def test_previous_iteration_must_be_immediate_and_same_manifest(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest_path, previous_path, _, _ = _bundle(
        tmp_path,
        name="previous",
        iteration=0,
        candidate_commit=BASE_SHA,
        statuses={"python-tests": "passed", "scope-audit": "passed"},
        manifest=manifest,
    )
    _, current_path, _, current = _bundle(
        tmp_path,
        name="current",
        iteration=2,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "passed", "scope-audit": "passed"},
        manifest=manifest,
    )

    with pytest.raises(observer.EvidenceError, match="immediately preceding"):
        observer.observe(manifest_path, current_path, previous_path)

    current["iteration"] = 1
    current["gate_manifest_digest"] = "e" * 64
    _write_json(current_path, current)
    with pytest.raises(observer.EvidenceError, match="manifest digest mismatch"):
        observer.observe(manifest_path, current_path, previous_path)


def test_current_iteration_cannot_start_before_previous_finished(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    manifest_path, previous_path, _, _ = _bundle(
        tmp_path,
        name="previous",
        iteration=0,
        candidate_commit=BASE_SHA,
        statuses={"python-tests": "passed", "scope-audit": "passed"},
        manifest=manifest,
    )
    _, current_path, _, current = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "passed", "scope-audit": "passed"},
        manifest=manifest,
    )
    current["started_at"] = "2026-07-26T02:00:04+00:00"
    current["finished_at"] = "2026-07-26T02:00:09+00:00"
    _write_json(current_path, current)

    with pytest.raises(observer.EvidenceError, match="starts before previous finished"):
        observer.observe(manifest_path, current_path, previous_path)


def test_cli_exit_codes_are_status_sensitive_and_json_is_deterministic(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest_path, evidence_path, _, _ = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "failed", "scope-audit": "passed"},
    )
    args = ["--manifest", str(manifest_path), "--evidence", str(evidence_path)]

    assert observer.main(args) == 1
    first = capsys.readouterr().out
    assert observer.main(args) == 1
    second = capsys.readouterr().out
    assert first == second
    payload = json.loads(first)
    assert payload["status"] == "failed"
    assert "generated_at" not in payload


def test_cli_invalid_bundle_returns_two_without_fake_result(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest_path, evidence_path, _, evidence = _bundle(
        tmp_path,
        name="current",
        iteration=1,
        candidate_commit=CANDIDATE_SHA,
        statuses={"python-tests": "passed", "scope-audit": "passed"},
    )
    evidence["candidate_commit"] = "not-a-sha"
    _write_json(evidence_path, evidence)

    assert observer.main(
        ["--manifest", str(manifest_path), "--evidence", str(evidence_path)]
    ) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "invalid"
    assert payload["human_signoff_required"] is True
    assert payload["automatic_gate_eligible"] is False


def test_cli_argument_errors_are_machine_readable_and_fail_closed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert observer.main([]) == 2
    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["status"] == "invalid"
    assert payload["human_signoff_required"] is True
    assert payload["automatic_gate_eligible"] is False
