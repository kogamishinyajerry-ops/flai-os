from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _markdown_template(path: Path) -> str:
    document = path.read_text(encoding="utf-8")
    return document.split("```markdown", 1)[1].split("```", 1)[0]


def test_n10_raw_record_template_captures_required_json_fields_at_the_scene():
    template = _markdown_template(ROOT / "docs" / "N10-NOVICE-WALKTHROUGH.md")

    required_capture_keys = {
        "record_id",
        "participant_key",
        "participant_kind",
        "role_category",
        "novice_eligible",
        "environment_valid",
        "observer_username",
        "commit_sha",
        "build_id",
        "browser",
        "viewport.width",
        "viewport.height",
        "theme",
        "input_method",
        "data_mode",
        "gateway_mode",
        "started_at",
        "ended_at",
        "termination.kind",
        "termination.at_step",
        "termination.detail",
        "observer_attestation.observed_live",
        "observer_attestation.path_coaching_withheld",
        "observer_attestation.recorded_contemporaneously",
        "observer_attestation.attested_at",
        "duration_seconds",
        "first_action",
        "stall_point",
        "participant_quote",
        "observer_interpretation",
        "observer_rescue",
        "observable_result",
        "exit_interview.q1",
        "exit_interview.q2",
        "exit_interview.q3",
        "exit_interview.q4",
        "exit_interview.q5",
        "issues[].category",
        "issues[].step_id",
        "issues[].observation",
        "issues[].reproduction",
        "controlled_media_refs",
    }

    missing = sorted(key for key in required_capture_keys if key not in template)
    assert missing == [], f"N10 现场模板缺少结构包采集键：{missing}"

    for result in (
        "unassisted",
        "assisted",
        "failed",
        "aborted",
        "version_unavailable",
        "not_reached_after_abort",
        "not_started_invalid_session",
    ):
        assert result in template


def test_m4_field_card_covers_every_gate_item_and_short_path_stays_partial():
    document = (ROOT / "docs" / "M4_intranet_day1_recon_checklist.md").read_text(
        encoding="utf-8"
    )
    field_card = document.split("### M4 必填现场收集卡（23 项）", 1)[1].split(
        "#### 机械 gate 合同", 1
    )[0]

    required_item_ids = {
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
    }
    rows = {
        line.split("|", 2)[1].strip()
        for line in field_card.splitlines()
        if line.startswith("|") and line.count("|") >= 2
    }
    assert required_item_ids <= rows

    for field in (
        "result",
        "observed_at",
        "observer_id",
        "evidence_ids",
        "actors[].kind",
        "actors[].role",
        "actors[].authorities",
        "actors[].identity_evidence_id",
        "evidence[].kind",
        "evidence[].path",
        "evidence[].sha256",
    ):
        assert field in field_card

    short_path = document.split("## 踏点当天最短路径", 1)[1]
    assert "不能满足 `M4_SIGNAL_PACKAGE_COMPLETE`" in short_path
