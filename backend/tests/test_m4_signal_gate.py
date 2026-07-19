"""M4 signal-package gate: invalid evidence must fail before any unlock claim."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from backend.app.governance import m4_signal_gate
from backend.app.governance.m4_signal_gate import (
    DEFAULT_SCHEMA_PATH,
    MANDATORY_ITEM_IDS,
    PACKAGE_SCHEMA_VERSION,
    evaluate_signal_package,
)
from scripts import verify_m4_signal_package


def _put_evidence(
    root: Path,
    evidence: dict[str, dict[str, str]],
    evidence_id: str,
    kind: str,
) -> str:
    relative = f"records/{evidence_id}.txt"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = f"controlled evidence: {evidence_id}\n".encode()
    path.write_bytes(payload)
    evidence[evidence_id] = {
        "kind": kind,
        "path": relative,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    return evidence_id


def _valid_package(tmp_path: Path) -> tuple[Path, Path, dict]:
    evidence_root = tmp_path / "evidence"
    evidence: dict[str, dict[str, str]] = {}

    actors = {
        "observer-01": {
            "kind": "person",
            "role": "现场观察者",
            "authorities": ["observer"],
            "identity_evidence_id": _put_evidence(
                evidence_root, evidence, "identity-observer", "identity_mapping"
            ),
        },
        "business-owner-01": {
            "kind": "person",
            "role": "业务负责人",
            "authorities": ["business_owner", "policy_owner"],
            "identity_evidence_id": _put_evidence(
                evidence_root, evidence, "identity-business-owner", "identity_mapping"
            ),
        },
        "policy-owner-01": {
            "kind": "person",
            "role": "核验政策负责人",
            "authorities": ["policy_owner"],
            "identity_evidence_id": _put_evidence(
                evidence_root, evidence, "identity-policy-owner", "identity_mapping"
            ),
        },
        "data-owner-01": {
            "kind": "person",
            "role": "数据与出口管制责任人",
            "authorities": ["data_export_control_owner"],
            "identity_evidence_id": _put_evidence(
                evidence_root, evidence, "identity-data-owner", "identity_mapping"
            ),
        },
        "candidate-service-01": {
            "kind": "service",
            "role": "候选生成服务",
            "authorities": ["service"],
            "identity_evidence_id": _put_evidence(
                evidence_root, evidence, "identity-candidate-service", "identity_mapping"
            ),
        },
    }

    items: dict[str, dict] = {}
    for item_id in MANDATORY_ITEM_IDS:
        evidence_id = _put_evidence(
            evidence_root,
            evidence,
            f"item-{item_id}",
            "report",
        )
        items[item_id] = {
            "result": "observed_yes",
            "observed_at": "2026-07-20T09:00:00Z",
            "observer_id": "observer-01",
            "evidence_ids": [evidence_id],
        }

    required_fixture_kinds = {
        "1-1": ("endpoint_probe",),
        "1-2": ("endpoint_probe",),
        "1-3": ("endpoint_probe",),
        "1-4": ("endpoint_probe",),
        "1-5": ("endpoint_probe",),
        "1-6": ("endpoint_probe", "model_inventory"),
        "2-1": ("command_output",),
        "2-2": ("command_output",),
        "2-3": ("command_output",),
        "2-5": ("command_output",),
        "2-6": ("command_output",),
        "4-2": ("workflow_trace",),
    }
    for item_id, kinds in required_fixture_kinds.items():
        for old_id in items[item_id]["evidence_ids"]:
            evidence.pop(old_id)
        items[item_id]["evidence_ids"] = [
            _put_evidence(
                evidence_root,
                evidence,
                f"item-{item_id}-{kind}",
                kind,
            )
            for kind in kinds
        ]

    matrix_id = _put_evidence(
        evidence_root, evidence, "review-matrix", "relationship_matrix"
    )
    items["5-1"]["evidence_ids"] = [matrix_id]

    separation_id = _put_evidence(
        evidence_root, evidence, "separation-ruling", "policy_ruling"
    )
    items["5-2"]["evidence_ids"] = [separation_id]

    inventory_id = _put_evidence(
        evidence_root, evidence, "model-inventory", "model_inventory"
    )
    endpoint_id = _put_evidence(
        evidence_root, evidence, "model-endpoint-probe", "endpoint_probe"
    )
    items["5-3"]["evidence_ids"] = [inventory_id, endpoint_id]

    m54_ruling_id = _put_evidence(
        evidence_root, evidence, "m54-not-applicable-ruling", "policy_ruling"
    )
    items["5-4"] = {
        "result": "not_applicable",
        "observed_at": "2026-07-20T09:00:00Z",
        "observer_id": "observer-01",
        "evidence_ids": [m54_ruling_id],
        "applicability_ruling": {
            "owner_id": "business-owner-01",
            "reason": "真实端点已确认存在第二基础模型家族。",
            "ruling_evidence_id": m54_ruling_id,
        },
    }

    category_id = _put_evidence(
        evidence_root, evidence, "human-sign-category-map", "category_mapping"
    )
    floor_ruling_id = _put_evidence(
        evidence_root, evidence, "human-sign-floor-ruling", "policy_ruling"
    )
    items["5-5"]["evidence_ids"] = [category_id, floor_ruling_id]

    candidate_trace = _put_evidence(
        evidence_root, evidence, "candidate-trace", "workflow_trace"
    )
    approval_trace = _put_evidence(
        evidence_root, evidence, "approval-trace", "workflow_trace"
    )
    publication_trace = _put_evidence(
        evidence_root, evidence, "publication-trace", "workflow_trace"
    )
    items["5-6"]["evidence_ids"] = [
        candidate_trace,
        approval_trace,
        publication_trace,
    ]

    package = {
        "schema_version": "m4-signal-package.v1",
        "package_id": "m4-20260720-lab-a",
        "actors": actors,
        "evidence": evidence,
        "items": items,
        "claims": {
            "review_relationship": {
                "matrix_evidence_id": matrix_id,
                "business_owner_id": "business-owner-01",
            },
            "separation_ruling": {
                "status": "defined",
                "ruling_evidence_id": separation_id,
                "business_owner_id": "business-owner-01",
            },
            "model_family": {
                "inventory_evidence_id": inventory_id,
                "endpoint_probe_evidence_id": endpoint_id,
                "second_family_available": True,
                "families": ["family-a", "family-b"],
            },
            "same_family_compensation": None,
            "permanent_human_sign_floor": {
                "category_mapping_evidence_id": category_id,
                "ruling_evidence_id": floor_ruling_id,
                "owner_id": "data-owner-01",
                "policy_owner_id": "policy-owner-01",
                "percent": 100,
                "configurable": False,
                "unknown_category_action": "require_named_human_sign",
            },
            "three_state_flow": {
                "candidate": {
                    "state": "candidate",
                    "action": "generate_candidate",
                    "actor_id": "candidate-service-01",
                    "audit_evidence_id": candidate_trace,
                },
                "human_approval": {
                    "state": "waiting_review",
                    "action": "named_human_approve",
                    "actor_id": "business-owner-01",
                    "audit_evidence_id": approval_trace,
                },
                "publication": {
                    "state": "published",
                    "action": "publish_exact_digest",
                    "actor_id": "business-owner-01",
                    "audit_evidence_id": publication_trace,
                },
            },
        },
    }
    package_path = tmp_path / "m4-signal-package.json"
    package_path.write_text(
        json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return package_path, evidence_root, package


def _evaluate(tmp_path: Path, package: dict, evidence_root: Path):
    package_path = tmp_path / "m4-signal-package-mutated.json"
    package_path.write_text(
        json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return evaluate_signal_package(package_path, evidence_root)


def test_valid_package_derives_true_and_binds_exact_package_digest(tmp_path: Path) -> None:
    package_path, evidence_root, _ = _valid_package(tmp_path)

    report = evaluate_signal_package(package_path, evidence_root)

    assert report.complete is True
    assert report.findings == ()
    assert report.package_sha256 == hashlib.sha256(package_path.read_bytes()).hexdigest()


def test_missing_required_item_and_optional_substitute_fail_closed(tmp_path: Path) -> None:
    _, evidence_root, package = _valid_package(tmp_path)
    package["items"]["1-7"] = package["items"].pop("1-1")

    report = _evaluate(tmp_path, package, evidence_root)

    assert report.complete is False
    assert "schema_invalid" in {finding.code for finding in report.findings}


@pytest.mark.parametrize("invalid_result", [None, "", "unknown", "pending", "Observed_Yes", 1])
def test_unknown_blank_or_truthy_result_never_counts(
    tmp_path: Path, invalid_result: object
) -> None:
    _, evidence_root, package = _valid_package(tmp_path)
    package["items"]["1-1"]["result"] = invalid_result

    report = _evaluate(tmp_path, package, evidence_root)

    assert report.complete is False
    assert "schema_invalid" in {finding.code for finding in report.findings}


@pytest.mark.parametrize("fault", ["missing", "digest", "traversal", "symlink"])
def test_evidence_must_be_local_retrievable_and_digest_exact(
    tmp_path: Path, fault: str
) -> None:
    _, evidence_root, package = _valid_package(tmp_path)
    evidence_id = package["items"]["1-1"]["evidence_ids"][0]
    evidence = package["evidence"][evidence_id]
    evidence_path = evidence_root / evidence["path"]
    if fault == "missing":
        evidence_path.unlink()
    elif fault == "digest":
        evidence_path.write_text("drift", encoding="utf-8")
    elif fault == "traversal":
        evidence["path"] = "../outside.txt"
    else:
        target = evidence_root / "real-evidence.txt"
        target.write_text("controlled evidence", encoding="utf-8")
        evidence_path.unlink()
        evidence_path.symlink_to(target)

    report = _evaluate(tmp_path, package, evidence_root)

    assert report.complete is False
    assert "evidence_untrusted" in {finding.code for finding in report.findings}


def test_not_applicable_is_forbidden_on_required_special_claims(tmp_path: Path) -> None:
    _, evidence_root, package = _valid_package(tmp_path)
    package["items"]["5-1"] = deepcopy(package["items"]["5-4"])

    report = _evaluate(tmp_path, package, evidence_root)

    assert report.complete is False
    assert "special_item_not_applicable" in {
        finding.code for finding in report.findings
    }


def test_observed_no_blocks_unless_named_controls_are_accepted(tmp_path: Path) -> None:
    _, evidence_root, package = _valid_package(tmp_path)
    ruling_id = _put_evidence(
        evidence_root, package["evidence"], "negative-ruling", "policy_ruling"
    )
    control_id = _put_evidence(
        evidence_root, package["evidence"], "negative-control", "policy_ruling"
    )
    item = package["items"]["2-1"]
    item["result"] = "observed_no"
    item["evidence_ids"].extend([ruling_id, control_id])
    item["negative_disposition"] = {
        "outcome": "blocks",
        "controls": [],
        "policy_owner_id": "policy-owner-01",
        "ruling_evidence_id": ruling_id,
    }
    blocked = _evaluate(tmp_path, package, evidence_root)
    assert blocked.complete is False
    assert "negative_result_blocks" in {finding.code for finding in blocked.findings}

    item["negative_disposition"] = {
        "outcome": "accepted_with_controls",
        "controls": [
            {"name": "保持人工门并补跑目标机探针", "evidence_id": control_id}
        ],
        "policy_owner_id": "policy-owner-01",
        "ruling_evidence_id": ruling_id,
    }
    accepted = _evaluate(tmp_path, package, evidence_root)
    assert accepted.complete is True


def test_no_second_model_family_requires_complete_named_compensation(tmp_path: Path) -> None:
    _, evidence_root, package = _valid_package(tmp_path)
    ruling_id = _put_evidence(
        evidence_root, package["evidence"], "same-family-ruling", "policy_ruling"
    )
    deterministic_id = _put_evidence(
        evidence_root,
        package["evidence"],
        "deterministic-verification-policy",
        "policy_ruling",
    )
    sampling_id = _put_evidence(
        evidence_root,
        package["evidence"],
        "human-sampling-floor-policy",
        "policy_ruling",
    )
    package["claims"]["model_family"] = {
        "inventory_evidence_id": package["claims"]["model_family"][
            "inventory_evidence_id"
        ],
        "endpoint_probe_evidence_id": package["claims"]["model_family"][
            "endpoint_probe_evidence_id"
        ],
        "second_family_available": False,
        "families": ["family-a"],
    }
    package["items"]["5-3"]["result"] = "observed_no"
    package["items"]["5-3"]["evidence_ids"].extend(
        [ruling_id, deterministic_id, sampling_id]
    )
    package["items"]["5-3"]["negative_disposition"] = {
        "outcome": "accepted_with_controls",
        "controls": [
            {
                "name": "确定性核验加权",
                "evidence_id": deterministic_id,
            },
            {
                "name": "人工抽检地板",
                "evidence_id": sampling_id,
            },
        ],
        "policy_owner_id": "policy-owner-01",
        "ruling_evidence_id": ruling_id,
    }
    package["items"]["5-4"] = {
        "result": "observed_yes",
        "observed_at": "2026-07-20T09:00:00Z",
        "observer_id": "observer-01",
        "evidence_ids": [deterministic_id, sampling_id, ruling_id],
    }
    package["claims"]["same_family_compensation"] = {
        "deterministic_verification_policy_evidence_id": deterministic_id,
        "human_sampling_floor_policy_evidence_id": sampling_id,
        "policy_owner_id": "policy-owner-01",
        "ruling_evidence_id": ruling_id,
    }

    complete = _evaluate(tmp_path, package, evidence_root)
    assert complete.complete is True

    package["claims"]["same_family_compensation"].pop(
        "human_sampling_floor_policy_evidence_id"
    )
    incomplete = _evaluate(tmp_path, package, evidence_root)
    assert incomplete.complete is False
    assert "schema_invalid" in {finding.code for finding in incomplete.findings}


def test_relationship_owner_ruling_must_match_and_be_written(tmp_path: Path) -> None:
    _, evidence_root, package = _valid_package(tmp_path)
    package["claims"]["separation_ruling"]["business_owner_id"] = "policy-owner-01"

    report = _evaluate(tmp_path, package, evidence_root)

    assert report.complete is False
    assert "review_owner_mismatch" in {finding.code for finding in report.findings}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("percent", 99),
        ("configurable", True),
        ("unknown_category_action", "allow"),
        ("owner_id", "business-owner-01"),
    ],
)
def test_permanent_human_sign_floor_is_not_relaxable(
    tmp_path: Path, field: str, value: object
) -> None:
    _, evidence_root, package = _valid_package(tmp_path)
    package["claims"]["permanent_human_sign_floor"][field] = value

    report = _evaluate(tmp_path, package, evidence_root)

    assert report.complete is False
    assert "human_sign_floor_invalid" in {finding.code for finding in report.findings}


def test_three_states_need_distinct_state_action_and_audit_but_not_distinct_people(
    tmp_path: Path,
) -> None:
    _, evidence_root, package = _valid_package(tmp_path)
    complete = _evaluate(tmp_path, package, evidence_root)
    assert complete.complete is True, "同一具名人可承担批准和发布，但动作/状态/证据不合并"

    package["claims"]["three_state_flow"]["publication"]["audit_evidence_id"] = (
        package["claims"]["three_state_flow"]["human_approval"][
            "audit_evidence_id"
        ]
    )
    report = _evaluate(tmp_path, package, evidence_root)

    assert report.complete is False
    assert "three_state_flow_collapsed" in {finding.code for finding in report.findings}


def test_input_cannot_self_report_complete(tmp_path: Path) -> None:
    _, evidence_root, package = _valid_package(tmp_path)
    package["M4_SIGNAL_PACKAGE_COMPLETE"] = True

    report = _evaluate(tmp_path, package, evidence_root)

    assert report.complete is False
    assert "schema_invalid" in {finding.code for finding in report.findings}


def test_contract_is_valid_draft_2020_12_schema() -> None:
    schema = json.loads(DEFAULT_SCHEMA_PATH.read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    assert schema["properties"]["schema_version"]["const"] == PACKAGE_SCHEMA_VERSION
    generic_item_ids = (
        set(schema["properties"]["items"]["propertyNames"]["enum"])
        - {"5-1", "5-2", "5-3", "5-4", "5-5", "5-6"}
    )
    assert set(m4_signal_gate._ITEM_REQUIRED_KIND_GROUPS) == generic_item_ids


@pytest.mark.parametrize("poison", ["duplicate_key", "nan"])
def test_noncanonical_json_fails_before_semantic_evaluation(
    tmp_path: Path, poison: str
) -> None:
    package_path, evidence_root, _ = _valid_package(tmp_path)
    source = package_path.read_text(encoding="utf-8")
    if poison == "duplicate_key":
        source = source.replace(
            '"package_id": "m4-20260720-lab-a",',
            '"package_id": "m4-20260720-lab-a",\n'
            '  "package_id": "m4-duplicate",',
            1,
        )
    else:
        source = source.replace('"percent": 100', '"percent": NaN', 1)
    package_path.write_text(source, encoding="utf-8")

    report = evaluate_signal_package(package_path, evidence_root)

    assert report.complete is False
    assert {finding.code for finding in report.findings} == {"package_invalid"}


@pytest.mark.parametrize(
    ("timestamp", "expected_code"),
    [
        ("2026-02-30T09:00:00Z", "timestamp_invalid"),
        ("2026-07-20T09:00:00+00:00", "schema_invalid"),
        ("2026-07-20T09:00:00.123Z", "schema_invalid"),
    ],
)
def test_observation_time_is_real_and_canonical_utc(
    tmp_path: Path, timestamp: str, expected_code: str
) -> None:
    _, evidence_root, package = _valid_package(tmp_path)
    package["items"]["1-1"]["observed_at"] = timestamp

    report = _evaluate(tmp_path, package, evidence_root)

    assert report.complete is False
    assert expected_code in {finding.code for finding in report.findings}


def test_parent_symlink_and_absolute_path_fail_closed(tmp_path: Path) -> None:
    _, evidence_root, package = _valid_package(tmp_path)
    evidence_id = package["items"]["1-1"]["evidence_ids"][0]
    original = package["evidence"][evidence_id]["path"]
    (evidence_root / "linked-records").symlink_to(evidence_root / "records")
    package["evidence"][evidence_id]["path"] = (
        "linked-records/" + Path(original).name
    )
    linked = _evaluate(tmp_path, package, evidence_root)
    assert linked.complete is False
    assert "evidence_untrusted" in {finding.code for finding in linked.findings}

    package["evidence"][evidence_id]["path"] = str(
        (evidence_root / original).resolve()
    )
    absolute = _evaluate(tmp_path, package, evidence_root)
    assert absolute.complete is False
    assert "evidence_untrusted" in {finding.code for finding in absolute.findings}


def test_evidence_root_symlink_fails_closed(tmp_path: Path) -> None:
    package_path, evidence_root, _ = _valid_package(tmp_path)
    linked_root = tmp_path / "linked-evidence-root"
    linked_root.symlink_to(evidence_root, target_is_directory=True)

    report = evaluate_signal_package(package_path, linked_root)

    assert report.complete is False
    assert "evidence_untrusted" in {finding.code for finding in report.findings}


def test_windows_reparse_attribute_is_treated_as_a_junction() -> None:
    class FakeMetadata:
        st_mode = stat.S_IFDIR
        st_file_attributes = 0x400

    class FakePath:
        @staticmethod
        def lstat() -> FakeMetadata:
            return FakeMetadata()

    assert m4_signal_gate._is_link_or_junction(FakePath()) is True


def test_evidence_size_limit_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package_path, evidence_root, _ = _valid_package(tmp_path)
    monkeypatch.setattr(m4_signal_gate, "MAX_EVIDENCE_BYTES", 8)

    report = evaluate_signal_package(package_path, evidence_root)

    assert report.complete is False
    assert "evidence_untrusted" in {finding.code for finding in report.findings}


def test_package_limit_is_checked_before_any_unbounded_path_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package_path, evidence_root, _ = _valid_package(tmp_path)
    monkeypatch.setattr(m4_signal_gate, "MAX_PACKAGE_BYTES", 1)

    def forbidden_read_bytes(_path: Path) -> bytes:
        raise AssertionError("oversized package must be rejected before read_bytes")

    monkeypatch.setattr(Path, "read_bytes", forbidden_read_bytes)

    report = evaluate_signal_package(package_path, evidence_root)

    assert report.complete is False
    assert {finding.code for finding in report.findings} == {"package_invalid"}


def test_package_must_be_strict_utf8_json(tmp_path: Path) -> None:
    package_path, evidence_root, package = _valid_package(tmp_path)
    package_path.write_bytes(json.dumps(package).encode("utf-16"))

    report = evaluate_signal_package(package_path, evidence_root)

    assert report.complete is False
    assert {finding.code for finding in report.findings} == {"package_invalid"}


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO is a POSIX input type")
def test_package_fifo_is_rejected_before_open(tmp_path: Path) -> None:
    _, evidence_root, _ = _valid_package(tmp_path)
    package_path = tmp_path / "m4-package.fifo"
    os.mkfifo(package_path)

    report = evaluate_signal_package(package_path, evidence_root)

    assert report.complete is False
    assert {finding.code for finding in report.findings} == {"package_unreadable"}


def test_evidence_swap_after_path_check_cannot_escape_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, evidence_root, package = _valid_package(tmp_path)
    evidence_id = package["items"]["1-1"]["evidence_ids"][0]
    record = package["evidence"][evidence_id]
    original_path = evidence_root / record["path"]
    original_size = original_path.stat().st_size
    outside_path = tmp_path / "outside-evidence.txt"
    outside_payload = b"x" * original_size
    outside_path.write_bytes(outside_payload)
    record["sha256"] = hashlib.sha256(outside_payload).hexdigest()
    original_resolver = m4_signal_gate._resolve_evidence_file

    def swap_after_check(root: Path, relative: str):
        resolved, error = original_resolver(root, relative)
        if relative == record["path"] and error is None:
            original_path.unlink()
            original_path.symlink_to(outside_path)
        return resolved, error

    monkeypatch.setattr(
        m4_signal_gate, "_resolve_evidence_file", swap_after_check
    )

    report = _evaluate(tmp_path, package, evidence_root)

    assert report.complete is False
    assert "evidence_untrusted" in {finding.code for finding in report.findings}


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory-fd atomicity contract")
def test_evidence_parent_swap_after_check_cannot_introduce_an_inward_symlink(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, evidence_root, package = _valid_package(tmp_path)
    target_id = package["claims"]["three_state_flow"]["publication"][
        "audit_evidence_id"
    ]
    target_relative = package["evidence"][target_id]["path"]
    records_dir = evidence_root / "records"
    anchored_dir = evidence_root / "records-anchored"
    original_resolver = m4_signal_gate._resolve_evidence_file

    def swap_parent_after_check(root: Path, relative: str):
        candidate, error = original_resolver(root, relative)
        if relative == target_relative and error is None:
            records_dir.rename(anchored_dir)
            records_dir.symlink_to(anchored_dir, target_is_directory=True)
        return candidate, error

    monkeypatch.setattr(
        m4_signal_gate,
        "_resolve_evidence_file",
        swap_parent_after_check,
    )

    report = _evaluate(tmp_path, package, evidence_root)

    assert report.complete is False
    assert "evidence_untrusted" in {finding.code for finding in report.findings}


def test_different_evidence_ids_cannot_alias_one_physical_file(tmp_path: Path) -> None:
    _, evidence_root, package = _valid_package(tmp_path)
    flow = package["claims"]["three_state_flow"]
    source_id = flow["candidate"]["audit_evidence_id"]
    for step_name in ("human_approval", "publication"):
        alias_id = flow[step_name]["audit_evidence_id"]
        package["evidence"][alias_id]["path"] = package["evidence"][source_id]["path"]
        package["evidence"][alias_id]["sha256"] = package["evidence"][source_id][
            "sha256"
        ]

    report = _evaluate(tmp_path, package, evidence_root)

    assert report.complete is False
    assert "evidence_alias" in {finding.code for finding in report.findings}


def test_copied_byte_identical_evidence_cannot_masquerade_as_independent(
    tmp_path: Path,
) -> None:
    _, evidence_root, package = _valid_package(tmp_path)
    flow = package["claims"]["three_state_flow"]
    source_id = flow["candidate"]["audit_evidence_id"]
    alias_id = flow["human_approval"]["audit_evidence_id"]
    source_path = evidence_root / package["evidence"][source_id]["path"]
    alias_path = evidence_root / package["evidence"][alias_id]["path"]
    alias_path.write_bytes(source_path.read_bytes())
    package["evidence"][alias_id]["sha256"] = package["evidence"][source_id][
        "sha256"
    ]

    report = _evaluate(tmp_path, package, evidence_root)

    assert report.complete is False
    assert "evidence_alias" in {finding.code for finding in report.findings}


def test_generic_observation_rejects_identity_mapping_as_its_only_kind(
    tmp_path: Path,
) -> None:
    _, evidence_root, package = _valid_package(tmp_path)
    evidence_id = package["items"]["1-1"]["evidence_ids"][0]
    package["evidence"][evidence_id]["kind"] = "identity_mapping"

    report = _evaluate(tmp_path, package, evidence_root)

    assert report.complete is False
    assert "item_evidence_kind_invalid" in {
        finding.code for finding in report.findings
    }


def test_gateway_protocol_observation_rejects_model_inventory_as_its_only_kind(
    tmp_path: Path,
) -> None:
    _, evidence_root, package = _valid_package(tmp_path)
    evidence_id = package["items"]["1-1"]["evidence_ids"][0]
    package["evidence"][evidence_id]["kind"] = "model_inventory"

    report = _evaluate(tmp_path, package, evidence_root)

    assert report.complete is False
    assert "item_evidence_kind_invalid" in {
        finding.code for finding in report.findings
    }


def test_model_families_must_be_distinct_after_canonicalization(tmp_path: Path) -> None:
    _, evidence_root, package = _valid_package(tmp_path)
    package["claims"]["model_family"]["families"] = ["GLM", " glm "]

    report = _evaluate(tmp_path, package, evidence_root)

    assert report.complete is False
    assert "model_family_invalid" in {finding.code for finding in report.findings}


def test_model_families_reject_invisible_format_character_aliases(
    tmp_path: Path,
) -> None:
    _, evidence_root, package = _valid_package(tmp_path)
    package["claims"]["model_family"]["families"] = ["GLM", "G\u200bLM"]

    report = _evaluate(tmp_path, package, evidence_root)

    assert report.complete is False
    assert "model_family_invalid" in {finding.code for finding in report.findings}


@pytest.mark.parametrize("field", ["state", "action"])
def test_three_state_flow_rejects_case_and_whitespace_aliases(
    tmp_path: Path, field: str
) -> None:
    _, evidence_root, package = _valid_package(tmp_path)
    flow = package["claims"]["three_state_flow"]
    flow["publication"][field] = f"  {flow['candidate'][field].upper()}  "

    report = _evaluate(tmp_path, package, evidence_root)

    assert report.complete is False
    assert "three_state_flow_collapsed" in {
        finding.code for finding in report.findings
    }


def test_three_state_flow_rejects_invisible_format_characters(tmp_path: Path) -> None:
    _, evidence_root, package = _valid_package(tmp_path)
    flow = package["claims"]["three_state_flow"]
    flow["publication"]["state"] = "can\u200bdidate"

    report = _evaluate(tmp_path, package, evidence_root)

    assert report.complete is False
    assert "three_state_flow_collapsed" in {
        finding.code for finding in report.findings
    }


def test_human_sign_floor_requires_a_named_policy_owner(tmp_path: Path) -> None:
    _, evidence_root, package = _valid_package(tmp_path)
    package["claims"]["permanent_human_sign_floor"]["policy_owner_id"] = (
        "data-owner-01"
    )

    report = _evaluate(tmp_path, package, evidence_root)

    assert report.complete is False
    assert "human_sign_floor_invalid" in {finding.code for finding in report.findings}


@pytest.mark.parametrize("fault", ["identity", "ruling"])
def test_human_sign_policy_owner_and_ruling_stay_evidence_bound(
    tmp_path: Path, fault: str
) -> None:
    _, evidence_root, package = _valid_package(tmp_path)
    floor = package["claims"]["permanent_human_sign_floor"]
    if fault == "identity":
        identity_id = package["actors"][floor["policy_owner_id"]][
            "identity_evidence_id"
        ]
        package["evidence"].pop(identity_id)
    else:
        floor["ruling_evidence_id"] = "missing-policy-ruling"

    report = _evaluate(tmp_path, package, evidence_root)

    assert report.complete is False
    assert {finding.code for finding in report.findings} & {
        "actor_identity_untrusted",
        "human_sign_floor_invalid",
    }


@pytest.mark.parametrize("target", ["package", "evidence"])
def test_cli_report_cannot_overwrite_an_input(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, target: str
) -> None:
    package_path, evidence_root, package = _valid_package(tmp_path)
    if target == "package":
        report_path = package_path
    else:
        evidence_id = package["items"]["1-1"]["evidence_ids"][0]
        report_path = evidence_root / package["evidence"][evidence_id]["path"]
    original = report_path.read_bytes()

    exit_code = verify_m4_signal_package.main(
        [
            "--package",
            str(package_path),
            "--evidence-root",
            str(evidence_root),
            "--report",
            str(report_path),
        ]
    )

    assert exit_code == 1
    assert report_path.read_bytes() == original
    assert "report path" in capsys.readouterr().err.lower()


@pytest.mark.parametrize("target", ["package_case_alias", "evidence_case_alias"])
def test_cli_report_rejects_casefolded_input_aliases(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, target: str
) -> None:
    package_path, evidence_root, package = _valid_package(tmp_path)
    if target == "package_case_alias":
        input_path = package_path
        report_path = package_path.with_name(package_path.name.upper())
    else:
        evidence_id = package["items"]["1-1"]["evidence_ids"][0]
        input_path = evidence_root / package["evidence"][evidence_id]["path"]
        report_path = (
            evidence_root.with_name(evidence_root.name.upper())
            / "RECORDS"
            / input_path.name.upper()
        )
    original = input_path.read_bytes()

    exit_code = verify_m4_signal_package.main(
        [
            "--package",
            str(package_path),
            "--evidence-root",
            str(evidence_root),
            "--report",
            str(report_path),
        ]
    )

    assert exit_code == 1
    assert input_path.read_bytes() == original
    assert "report path" in capsys.readouterr().err.lower()


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory-fd atomicity contract")
def test_cli_report_parent_swap_cannot_redirect_write_into_evidence(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    package_path, evidence_root, _ = _valid_package(tmp_path)
    report_parent = tmp_path / "reports"
    report_parent.mkdir()
    displaced_parent = tmp_path / "reports-displaced"
    evidence_destination = evidence_root / "derived"
    evidence_destination.mkdir()
    report_path = report_parent / "m4-report.json"
    original_writer = verify_m4_signal_package._write_report_atomically

    def swap_parent_then_write(path: Path, rendered: str) -> None:
        report_parent.rename(displaced_parent)
        report_parent.symlink_to(evidence_destination, target_is_directory=True)
        original_writer(path, rendered)

    monkeypatch.setattr(
        verify_m4_signal_package,
        "_write_report_atomically",
        swap_parent_then_write,
    )

    exit_code = verify_m4_signal_package.main(
        [
            "--package",
            str(package_path),
            "--evidence-root",
            str(evidence_root),
            "--report",
            str(report_path),
        ]
    )

    assert exit_code == 1
    assert (evidence_destination / report_path.name).exists() is False
    assert "report write failed" in capsys.readouterr().err.lower()


def test_cli_emits_stable_json_and_propagates_gate_exit_code(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    package_path, evidence_root, package = _valid_package(tmp_path)
    report_path = tmp_path / "gate-report.json"

    ok_exit = verify_m4_signal_package.main(
        [
            "--package",
            str(package_path),
            "--evidence-root",
            str(evidence_root),
            "--report",
            str(report_path),
        ]
    )
    stdout_report = json.loads(capsys.readouterr().out)
    file_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert ok_exit == 0
    assert stdout_report == file_report
    assert stdout_report["M4_SIGNAL_PACKAGE_COMPLETE"] is True
    assert "does not prove N10" in stdout_report["boundary"]

    package["items"].pop("1-1")
    package_path.write_text(json.dumps(package), encoding="utf-8")
    failed_exit = verify_m4_signal_package.main(
        ["--package", str(package_path), "--evidence-root", str(evidence_root)]
    )
    failed_report = json.loads(capsys.readouterr().out)
    assert failed_exit == 1
    assert failed_report["M4_SIGNAL_PACKAGE_COMPLETE"] is False


@pytest.mark.parametrize(
    ("executable", "wrapper"),
    [
        ("bash", "verify_m4_signal_package.sh"),
        ("pwsh", "verify_m4_signal_package.ps1"),
    ],
)
def test_platform_wrapper_really_propagates_true_and_false_exit_codes(
    executable: str, wrapper: str, tmp_path: Path
) -> None:
    command = shutil.which(executable)
    if command is None:
        pytest.skip(f"{executable} is not installed on this host")
    package_path, evidence_root, package = _valid_package(tmp_path)
    repo_root = DEFAULT_SCHEMA_PATH.parent.parent
    wrapper_path = repo_root / "scripts" / wrapper
    prefix = [command]
    if executable == "pwsh":
        prefix.extend(["-NoProfile", "-File"])
    valid = subprocess.run(
        [
            *prefix,
            str(wrapper_path),
            "--package",
            str(package_path),
            "--evidence-root",
            str(evidence_root),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert valid.returncode == 0, valid.stderr
    assert json.loads(valid.stdout)["M4_SIGNAL_PACKAGE_COMPLETE"] is True

    package["items"].pop("1-1")
    package_path.write_text(json.dumps(package), encoding="utf-8")
    invalid = subprocess.run(
        [
            *prefix,
            str(wrapper_path),
            "--package",
            str(package_path),
            "--evidence-root",
            str(evidence_root),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert invalid.returncode == 1, invalid.stderr
    assert json.loads(invalid.stdout)["M4_SIGNAL_PACKAGE_COMPLETE"] is False
