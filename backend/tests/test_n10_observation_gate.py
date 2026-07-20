from __future__ import annotations

import json
import os
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from backend.app.governance import n10_observation_gate
from backend.app.governance.n10_observation_gate import (
    DEFAULT_SCHEMA_PATH,
    MAX_PACKAGE_BYTES,
    PACKAGE_SCHEMA_VERSION,
    evaluate_n10_observation_package,
)
from scripts import verify_n10_observation_package


def _quote(text: str = "我在等什么？") -> dict[str, str]:
    return {"status": "captured", "text": text}


def _record(participant_key: str, record_id: str) -> dict:
    return {
        "record_id": record_id,
        "participant_key": participant_key,
        "participant_kind": "real_colleague",
        "role_category": "工程岗位",
        "novice_eligible": True,
        "environment_valid": True,
        "observer_username": "observer-a",
        "build": {
            "commit_sha": "a" * 40,
            "build_id": "local-n10-build",
            "browser": "Chromium 140",
            "viewport": {"width": 1440, "height": 900},
            "theme": "light",
            "input_method": "mouse_keyboard",
            "data_mode": "synthetic",
            "gateway_mode": "live_configured",
        },
        "started_at": "2026-07-20T01:00:00Z",
        "ended_at": "2026-07-20T01:20:00Z",
        "termination": {
            "kind": "completed",
            "at_step": None,
            "detail": "十步均走到可观察结果",
        },
        "observer_attestation": {
            "observed_live": True,
            "path_coaching_withheld": True,
            "recorded_contemporaneously": True,
            "attested_at": "2026-07-20T01:21:00Z",
        },
        "steps": [
            {
                "step_id": f"N{index}",
                "result": "unassisted",
                "duration_seconds": 60,
                "first_action": "先观察页面并尝试进入相关区域",
                "stall_point": "未观察到停滞",
                "participant_quote": _quote(),
                "observer_interpretation": "参与者自行完成；这是观察者解释，不是引语",
                "observer_rescue": None,
                "observable_result": "到达该步要求的可观察状态",
            }
            for index in range(1, 11)
        ],
        "exit_interview": {
            f"q{index}": _quote(f"结束访谈回答 {index}")
            for index in range(1, 6)
        },
        "issues": [],
        "controlled_media_refs": [],
    }


def _abort_record(record: dict, at_step: str = "N5") -> dict:
    abort_index = int(at_step.removeprefix("N")) - 1
    record["termination"] = {
        "kind": "product_blocker",
        "at_step": at_step,
        "detail": "真实产品阻塞，中止后续步骤",
    }
    record["steps"][abort_index]["result"] = "aborted"
    for step in record["steps"][abort_index + 1 :]:
        step.update(
            {
                "result": "not_reached_after_abort",
                "duration_seconds": None,
                "first_action": "未到达（此前已中止）",
                "stall_point": "未到达（此前已中止）",
                "participant_quote": {
                    "status": "not_captured",
                    "reason": "此前已中止，未向参与者提出此步骤",
                },
                "observer_interpretation": "未到达，不作参与者行为归因",
                "observer_rescue": None,
                "observable_result": "未到达（此前已中止）",
            }
        )
    return record


def _not_started_record(record: dict, kind: str) -> dict:
    if kind == "environment_invalid":
        record["environment_valid"] = False
        detail = "测试账号未准备完成，本场不计入 n"
    elif kind == "ineligible_participant":
        record["novice_eligible"] = False
        detail = "现场确认不符合新手口径，本场不计入 n"
    else:  # pragma: no cover - test helper contract
        raise ValueError(f"unsupported not-started kind: {kind}")
    record["termination"] = {
        "kind": kind,
        "at_step": None,
        "detail": detail,
    }
    for step in record["steps"]:
        step.update(
            {
                "result": "not_started_invalid_session",
                "duration_seconds": None,
                "first_action": "本场无效，任务步骤未开始",
                "stall_point": "本场无效，未观察步骤停滞",
                "participant_quote": {
                    "status": "not_captured",
                    "reason": "本场在任务开始前已判定无效",
                },
                "observer_interpretation": "未开始，不作参与者行为归因",
                "observer_rescue": None,
                "observable_result": "本场无效，任务步骤未开始",
            }
        )
    return record


def _write_package(tmp_path: Path, records: list[dict]) -> Path:
    path = tmp_path / "n10-package.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "n10-observation-package.v1",
                "protocol_version": "N10-2026-07-19",
                "records": records,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def test_contract_is_valid_draft_2020_12_schema() -> None:
    schema = json.loads(DEFAULT_SCHEMA_PATH.read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["properties"]["schema_version"]["const"] == PACKAGE_SCHEMA_VERSION


def test_single_declared_eligible_record_never_satisfies_n2(tmp_path: Path) -> None:
    package_path = _write_package(
        tmp_path,
        [_record("P01", "N10-20260720-P01")],
    )

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is False
    assert report.declared_eligible_n == 1
    assert any(finding.code == "eligible_sample_shortfall" for finding in report.findings)


def test_two_distinct_complete_declared_records_bind_exact_package_digest(
    tmp_path: Path,
) -> None:
    package_path = _write_package(
        tmp_path,
        [
            _record("P01", "N10-20260720-P01"),
            _record("P02", "N10-20260720-P02"),
        ],
    )

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is True
    assert report.declared_eligible_n == 2
    assert report.package_sha256 == sha256(package_path.read_bytes()).hexdigest()
    assert report.findings == ()


def test_package_cannot_self_report_n_completion_or_success_rate(tmp_path: Path) -> None:
    package_path = _write_package(
        tmp_path,
        [
            _record("P01", "N10-20260720-P01"),
            _record("P02", "N10-20260720-P02"),
        ],
    )
    package = json.loads(package_path.read_text(encoding="utf-8"))
    package.update(
        {
            "n": 2,
            "N10_RECORD_PACKAGE_COMPLETE": True,
            "N10_DECLARED_RECORD_PACKAGE_STRUCTURALLY_COMPLETE": True,
            "success_rate": 1.0,
        }
    )
    package_path.write_text(json.dumps(package), encoding="utf-8")

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is False
    assert report.declared_eligible_n == 0
    assert any(finding.code == "schema_invalid" for finding in report.findings)


def test_repeated_participant_key_cannot_inflate_declared_eligible_n(
    tmp_path: Path,
) -> None:
    package_path = _write_package(
        tmp_path,
        [
            _record("P01", "N10-20260720-P01"),
            _record("P01", "N10-20260721-P01"),
        ],
    )

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is False
    assert report.declared_eligible_n == 1
    assert any(finding.code == "duplicate_participant" for finding in report.findings)


def test_each_record_requires_exact_ordered_n1_through_n10(tmp_path: Path) -> None:
    first = _record("P01", "N10-20260720-P01")
    first["steps"][-1]["step_id"] = "N9"
    package_path = _write_package(
        tmp_path,
        [first, _record("P02", "N10-20260720-P02")],
    )

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is False
    assert report.declared_eligible_n == 1
    assert any(finding.code == "step_sequence_invalid" for finding in report.findings)


def test_assisted_step_requires_verbatim_observer_rescue(tmp_path: Path) -> None:
    first = _record("P01", "N10-20260720-P01")
    first["steps"][3]["result"] = "assisted"
    first["steps"][3]["observer_rescue"] = None
    package_path = _write_package(
        tmp_path,
        [first, _record("P02", "N10-20260720-P02")],
    )

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is False
    assert report.declared_eligible_n == 1
    assert any(finding.code == "rescue_contract_invalid" for finding in report.findings)


def test_unassisted_step_cannot_hide_observer_rescue(tmp_path: Path) -> None:
    first = _record("P01", "N10-20260720-P01")
    first["steps"][3]["observer_rescue"] = "观察者指出了右上角按钮"
    package_path = _write_package(
        tmp_path,
        [first, _record("P02", "N10-20260720-P02")],
    )

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is False
    assert report.declared_eligible_n == 1
    assert any(finding.code == "rescue_contract_invalid" for finding in report.findings)


def test_steps_after_abort_must_be_explicitly_not_reached(tmp_path: Path) -> None:
    first = _abort_record(_record("P01", "N10-20260720-P01"))
    first["steps"][5] = _record("PX", "N10-20260720-PX")["steps"][5]
    package_path = _write_package(
        tmp_path,
        [first, _record("P02", "N10-20260720-P02")],
    )

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is False
    assert report.declared_eligible_n == 1
    assert any(finding.code == "termination_topology_invalid" for finding in report.findings)


def test_record_times_must_be_real_and_monotonic(tmp_path: Path) -> None:
    first = _record("P01", "N10-20260720-P01")
    first["ended_at"] = "2026-07-20T00:59:59Z"
    package_path = _write_package(
        tmp_path,
        [first, _record("P02", "N10-20260720-P02")],
    )

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is False
    assert report.declared_eligible_n == 1
    assert any(finding.code == "timestamp_invalid" for finding in report.findings)


def test_duplicate_json_keys_fail_before_record_evaluation(tmp_path: Path) -> None:
    package_path = _write_package(
        tmp_path,
        [
            _record("P01", "N10-20260720-P01"),
            _record("P02", "N10-20260720-P02"),
        ],
    )
    raw = package_path.read_text(encoding="utf-8")
    package_path.write_text(
        raw.replace(
            "{",
            '{"schema_version":"n10-observation-package.v1",',
            1,
        ),
        encoding="utf-8",
    )

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is False
    assert report.declared_eligible_n == 0
    assert any(finding.code == "package_invalid" for finding in report.findings)


def test_package_size_is_bounded_before_json_evaluation(tmp_path: Path) -> None:
    package_path = tmp_path / "oversized.json"
    package_path.write_bytes(b"{" + b" " * MAX_PACKAGE_BYTES)

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is False
    assert report.declared_eligible_n == 0
    assert report.package_sha256 is None
    assert any(finding.code == "package_too_large" for finding in report.findings)


def test_record_id_must_be_unique_even_for_distinct_participants(tmp_path: Path) -> None:
    package_path = _write_package(
        tmp_path,
        [
            _record("P01", "N10-20260720-P01"),
            _record("P02", "N10-20260720-P01"),
        ],
    )

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is False
    assert report.declared_eligible_n == 1
    assert any(finding.code == "duplicate_record" for finding in report.findings)


def test_attempted_step_requires_observed_duration(tmp_path: Path) -> None:
    first = _record("P01", "N10-20260720-P01")
    first["steps"][0]["duration_seconds"] = None
    package_path = _write_package(
        tmp_path,
        [first, _record("P02", "N10-20260720-P02")],
    )

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is False
    assert report.declared_eligible_n == 1
    assert any(finding.code == "step_observation_invalid" for finding in report.findings)


def test_not_reached_step_cannot_carry_fabricated_observation(tmp_path: Path) -> None:
    first = _abort_record(_record("P01", "N10-20260720-P01"))
    first["steps"][6]["duration_seconds"] = 1
    first["steps"][6]["participant_quote"] = _quote("其实我继续做了")
    package_path = _write_package(
        tmp_path,
        [first, _record("P02", "N10-20260720-P02")],
    )

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is False
    assert report.declared_eligible_n < 2
    assert {finding.code for finding in report.findings} & {
        "schema_invalid",
        "step_observation_invalid",
    }


@pytest.mark.parametrize(
    ("field", "fabricated_value"),
    [
        ("first_action", "参与者继续点击并成功进入下一页"),
        ("stall_point", "参与者没有停滞"),
        ("observer_interpretation", "参与者已经理解并完成任务"),
        ("observable_result", "产物已经正式发布"),
        (
            "participant_quote",
            {"status": "not_captured", "reason": "参与者已成功但没有记录引语"},
        ),
    ],
)
def test_not_reached_step_cannot_hide_fabricated_narrative(
    tmp_path: Path,
    field: str,
    fabricated_value: object,
) -> None:
    first = _abort_record(_record("P01", "N10-20260720-P01"))
    first["steps"][6][field] = fabricated_value
    package_path = _write_package(
        tmp_path,
        [first, _record("P02", "N10-20260720-P02")],
    )

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is False


def test_real_product_blocker_abort_still_counts_as_complete_record(
    tmp_path: Path,
) -> None:
    package_path = _write_package(
        tmp_path,
        [
            _abort_record(_record("P01", "N10-20260720-P01")),
            _record("P02", "N10-20260720-P02"),
        ],
    )

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is True
    assert report.declared_eligible_n == 2
    assert report.findings == ()


def test_environment_invalid_record_is_retained_but_never_counts(tmp_path: Path) -> None:
    first = _not_started_record(
        _record("P01", "N10-20260720-P01"),
        "environment_invalid",
    )
    package_path = _write_package(
        tmp_path,
        [first, _record("P02", "N10-20260720-P02")],
    )

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is False
    assert report.declared_eligible_n == 1
    assert any(finding.code == "eligible_sample_shortfall" for finding in report.findings)
    assert not any(
        finding.code == "termination_topology_invalid"
        for finding in report.findings
    )


def test_honest_environment_invalid_record_can_coexist_with_complete_sample(
    tmp_path: Path,
) -> None:
    invalid_session = _not_started_record(
        _record("P00", "N10-20260720-P00"),
        "environment_invalid",
    )
    package_path = _write_package(
        tmp_path,
        [
            invalid_session,
            _record("P01", "N10-20260720-P01"),
            _record("P02", "N10-20260720-P02"),
        ],
    )

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is True
    assert report.declared_eligible_n == 2


def test_eligible_records_from_different_builds_are_reported_separately(
    tmp_path: Path,
) -> None:
    second = _record("P02", "N10-20260720-P02")
    second["build"]["commit_sha"] = "b" * 40
    second["build"]["build_id"] = "local-n10-build-b"
    second["build"]["gateway_mode"] = "controlled_stub"
    package_path = _write_package(
        tmp_path,
        [_record("P01", "N10-20260720-P01"), second],
    )

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is True
    assert report.declared_eligible_n == 2
    assert report.eligible_builds == (
        {
            "commit_sha": "a" * 40,
            "build_id": "local-n10-build",
            "gateway_mode": "live_configured",
            "declared_eligible_n": 1,
        },
        {
            "commit_sha": "b" * 40,
            "build_id": "local-n10-build-b",
            "gateway_mode": "controlled_stub",
            "declared_eligible_n": 1,
        },
    )
    assert "success_rate" not in report.as_dict()


def test_non_human_record_is_retained_but_never_inflates_n(tmp_path: Path) -> None:
    automation = _record("P01", "N10-20260720-P01")
    automation["participant_kind"] = "automation"
    package_path = _write_package(
        tmp_path,
        [automation, _record("P02", "N10-20260720-P02")],
    )

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is False
    assert report.declared_eligible_n == 1
    assert any(finding.code == "eligible_sample_shortfall" for finding in report.findings)


def test_assisted_and_failed_steps_do_not_turn_n_into_a_success_metric(
    tmp_path: Path,
) -> None:
    first = _record("P01", "N10-20260720-P01")
    first["steps"][2]["result"] = "assisted"
    first["steps"][2]["observer_rescue"] = "请继续按你自己的理解尝试。"
    first["steps"][7]["result"] = "failed"
    package_path = _write_package(
        tmp_path,
        [first, _record("P02", "N10-20260720-P02")],
    )

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is True
    assert report.declared_eligible_n == 2
    assert "success_rate" not in report.as_dict()


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink contract")
def test_package_symlink_is_rejected_without_following_target(tmp_path: Path) -> None:
    target = _write_package(
        tmp_path,
        [
            _record("P01", "N10-20260720-P01"),
            _record("P02", "N10-20260720-P02"),
        ],
    )
    link = tmp_path / "n10-package-link.json"
    link.symlink_to(target)

    report = evaluate_n10_observation_package(link)

    assert report.structurally_complete is False
    assert report.package_sha256 is None
    assert any(finding.code == "package_unreadable" for finding in report.findings)


def test_invalid_repository_schema_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package_path = _write_package(
        tmp_path,
        [
            _record("P01", "N10-20260720-P01"),
            _record("P02", "N10-20260720-P02"),
        ],
    )
    invalid_schema = tmp_path / "invalid-schema.json"
    invalid_schema.write_text(
        json.dumps({"type": "definitely-not-a-json-schema-type"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        n10_observation_gate,
        "DEFAULT_SCHEMA_PATH",
        invalid_schema,
    )

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is False
    assert any(finding.code == "schema_unavailable" for finding in report.findings)


def test_trailing_newline_cannot_bypass_declared_participant_dedup(
    tmp_path: Path,
) -> None:
    second = _record("P01", "N10-20260720-P02")
    second["participant_key"] = "P01\n"
    package_path = _write_package(
        tmp_path,
        [_record("P01", "N10-20260720-P01"), second],
    )

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is False
    assert report.declared_eligible_n < 2


def test_whitespace_only_raw_observation_is_not_complete(tmp_path: Path) -> None:
    first = _record("P01", "N10-20260720-P01")
    first["steps"][0]["participant_quote"] = {
        "status": "captured",
        "text": "   ",
    }
    package_path = _write_package(
        tmp_path,
        [first, _record("P02", "N10-20260720-P02")],
    )

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is False


@pytest.mark.parametrize(
    "invisible_text",
    [
        "\u200b\u200c",
        "\u2800",
        "\u115f\u1160",
        "\u3164\uffa0",
        "---",
        "🛩️",
    ],
)
def test_non_substantive_characters_are_not_raw_observation_evidence(
    tmp_path: Path,
    invisible_text: str,
) -> None:
    first = _record("P01", "N10-20260720-P01")
    first["exit_interview"]["q1"] = {
        "status": "captured",
        "text": invisible_text,
    }
    package_path = _write_package(
        tmp_path,
        [first, _record("P02", "N10-20260720-P02")],
    )

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is False
    assert any(finding.code == "blank_evidence" for finding in report.findings)


def test_environment_termination_must_agree_with_environment_flag_and_steps(
    tmp_path: Path,
) -> None:
    contradictory = _record("P00", "N10-20260720-P00")
    contradictory["termination"] = {
        "kind": "environment_invalid",
        "at_step": "N5",
        "detail": "自称环境无效，但仍保留十步完成记录",
    }
    package_path = _write_package(
        tmp_path,
        [
            contradictory,
            _record("P01", "N10-20260720-P01"),
            _record("P02", "N10-20260720-P02"),
        ],
    )

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is False
    assert any(
        finding.code == "termination_topology_invalid"
        for finding in report.findings
    )


def test_abort_topology_rejects_an_earlier_second_abort(tmp_path: Path) -> None:
    first = _abort_record(_record("P01", "N10-20260720-P01"), at_step="N5")
    first["steps"][2]["result"] = "aborted"
    package_path = _write_package(
        tmp_path,
        [first, _record("P02", "N10-20260720-P02")],
    )

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is False
    assert any(
        finding.code == "termination_topology_invalid"
        for finding in report.findings
    )


@pytest.mark.parametrize("step_duration", [0, 60])
def test_attempted_durations_must_fit_inside_session_interval(
    tmp_path: Path,
    step_duration: int,
) -> None:
    first = _record("P01", "N10-20260720-P01")
    first["ended_at"] = first["started_at"]
    for step in first["steps"]:
        step["duration_seconds"] = step_duration
    package_path = _write_package(
        tmp_path,
        [first, _record("P02", "N10-20260720-P02")],
    )

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is False
    assert any(finding.code == "duration_invalid" for finding in report.findings)


def test_attempted_session_requires_some_positive_observed_duration(
    tmp_path: Path,
) -> None:
    first = _record("P01", "N10-20260720-P01")
    for step in first["steps"]:
        step["duration_seconds"] = 0
    package_path = _write_package(
        tmp_path,
        [first, _record("P02", "N10-20260720-P02")],
    )

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is False
    assert any(finding.code == "duration_invalid" for finding in report.findings)


def test_invalid_json_report_still_binds_exact_input_digest(tmp_path: Path) -> None:
    package_path = tmp_path / "invalid.json"
    package_path.write_bytes(b'{"records": [}')

    report = evaluate_n10_observation_package(package_path)

    assert report.structurally_complete is False
    assert report.package_sha256 == sha256(package_path.read_bytes()).hexdigest()


def test_cli_emits_stable_json_and_propagates_completeness_exit_code(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    package_path = _write_package(
        tmp_path,
        [
            _record("P01", "N10-20260720-P01"),
            _record("P02", "N10-20260720-P02"),
        ],
    )

    ok_exit = verify_n10_observation_package.main(
        ["--package", str(package_path)]
    )
    ok_report = json.loads(capsys.readouterr().out)
    assert ok_exit == 0
    assert ok_report["N10_DECLARED_RECORD_PACKAGE_STRUCTURALLY_COMPLETE"] is True
    assert ok_report["owner_identity_confirmation_required"] is True
    assert ok_report["roadmap_effect"] == "none"
    assert ok_report["m4_status"] == "not_evaluated"
    assert "does not authenticate real humans" in ok_report["boundary"]

    package_path = _write_package(
        tmp_path,
        [_record("P01", "N10-20260720-P01")],
    )
    failed_exit = verify_n10_observation_package.main(
        ["--package", str(package_path)]
    )
    failed_report = json.loads(capsys.readouterr().out)
    assert failed_exit == 1
    assert failed_report["N10_DECLARED_RECORD_PACKAGE_STRUCTURALLY_COMPLETE"] is False


@pytest.mark.parametrize(
    ("executable", "wrapper"),
    [
        ("bash", "verify_n10_observation_package.sh"),
        ("pwsh", "verify_n10_observation_package.ps1"),
    ],
)
def test_platform_wrapper_propagates_true_and_false_exit_codes(
    executable: str,
    wrapper: str,
    tmp_path: Path,
) -> None:
    command = shutil.which(executable)
    if command is None:
        pytest.skip(f"{executable} is not installed on this host")
    package_path = _write_package(
        tmp_path,
        [
            _record("P01", "N10-20260720-P01"),
            _record("P02", "N10-20260720-P02"),
        ],
    )
    wrapper_path = DEFAULT_SCHEMA_PATH.parent.parent / "scripts" / wrapper
    prefix = [command]
    if executable == "pwsh":
        prefix.extend(["-NoProfile", "-File"])

    valid = subprocess.run(
        [*prefix, str(wrapper_path), "--package", str(package_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert valid.returncode == 0
    assert json.loads(valid.stdout)[
        "N10_DECLARED_RECORD_PACKAGE_STRUCTURALLY_COMPLETE"
    ] is True

    package_path = _write_package(
        tmp_path,
        [_record("P01", "N10-20260720-P01")],
    )
    invalid = subprocess.run(
        [*prefix, str(wrapper_path), "--package", str(package_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert invalid.returncode == 1
    assert json.loads(invalid.stdout)[
        "N10_DECLARED_RECORD_PACKAGE_STRUCTURALLY_COMPLETE"
    ] is False
