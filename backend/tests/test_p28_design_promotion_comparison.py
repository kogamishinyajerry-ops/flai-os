from __future__ import annotations

import hashlib
import json
import struct
import zlib
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from conftest import seed_and_login

from backend.app.design_promotion.contracts import (
    Actor,
    ComparisonCreate,
    ExpectedTarget,
    PublishRequest,
    ReleaseDecisionRequest,
    ReleaseRequestCreate,
    RollbackRequest,
    SelectionRequest,
)
from backend.app.design_promotion.service import (
    DesignPromotionService,
    SensitiveCandidateRequiresRoleAxis,
)
from backend.app.design_promotion.targets import (
    AssetTarget,
    CurrentFrame,
    TargetRegistry,
)
from backend.app.api.design_promotions import router as design_promotions_router
from backend.app.main import create_app
from backend.app.storage import repos
from backend.app.storage.db import get_conn, init_db
from backend.app.storage.design_promotion_schema import (
    assert_design_promotion_schema,
    design_promotion_schema_witnesses,
    install_design_promotion_schema,
)
from backend.app.storage.design_promotion_repo import now_iso


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _png(width: int, height: int, rgb: bytes) -> bytes:
    rows = b"".join(b"\x00" + (rgb * width) for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(rows))
        + _chunk(b"IEND", b"")
    )


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _assert_public_contract(value) -> None:
    schema_path = Path(__file__).parents[2] / "contracts/design-promotion.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(value)


def _api_client(service, *, username: str = "api_reviewer") -> TestClient:
    app = FastAPI()
    app.state.design_promotion_service = service

    @app.middleware("http")
    async def _principal(request: Request, call_next):
        request.state.user = {
            "username": username,
            "display_name": "API Reviewer",
        }
        return await call_next(request)

    app.include_router(design_promotions_router)
    return TestClient(app)


def _seed_candidate(
    db_path: Path,
    task_runs: Path,
    *,
    task_classification: str = "internal",
    candidate_classification: str = "internal",
) -> dict[str, str]:
    task_id = "task_design"
    candidate = _png(2, 2, b"\x11\x22\x33")
    preview = _png(100, 80, b"\x44\x55\x66")
    manifest = {
        "schema_version": "open-design-daemon-candidate-manifest/v1",
        "review_contract": "open-design-candidate/v1",
        "generator_kind": "open_design_daemon",
        "classification": "sensitive",
        "candidate_id": "odc-" + "1" * 32,
        "asset_slot": "task_review_summary",
        "execution_trust": "untrusted_generated",
        "production_readiness": "trial_not_attested",
        "candidate_only": True,
        "release_effect": "none",
        "mock": False,
        "project_id": "flai-task-design",
        "run_id": "od-run-1",
        "result_package_sha256": "c" * 64,
        "design_reference_package_sha256": "d" * 64,
        "file_set_sha256": "e" * 64,
        "captured_files": [
            {
                "source_path": "candidate.png",
                "bundle_relpath": "captured/candidate.png",
                "media_type": "image/png",
                "size_bytes": len(candidate),
                "sha256": _sha(candidate),
                "role": "candidate_source",
            },
            {
                "source_path": "preview.png",
                "bundle_relpath": "captured/preview.png",
                "media_type": "image/png",
                "size_bytes": len(preview),
                "sha256": _sha(preview),
                "role": "passive_preview",
            },
        ],
        "passive_previews": [
            {
                "slot_id": "default_desktop_light",
                "viewport": {"width": 100, "height": 80, "dpr": 1},
                "state": "default",
                "theme": "light",
                "locale": "zh-CN",
                "source": {"path": "candidate.png", "sha256": _sha(candidate)},
                "image": {
                    "path": "preview.png",
                    "sha256": _sha(preview),
                    "size_bytes": len(preview),
                    "media_type": "image/png",
                    "width": 100,
                    "height": 80,
                },
                "passive_preview_scan": {
                    "policy": "flai-passive-png/v1",
                    "passed": True,
                    "active_content_executed": False,
                },
            }
        ],
        "promotable_asset": {
            "slot_id": "default_desktop_light",
            "source_path": "preview.png",
            "bundle_relpath": "captured/preview.png",
            "media_type": "image/png",
            "size_bytes": len(preview),
            "sha256": _sha(preview),
        },
    }
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    manifest_sha = _sha(manifest_bytes)

    task_dir = task_runs / task_id
    captured_dir = task_dir / "captured"
    captured_dir.mkdir(parents=True)
    paths = {
        "manifest": task_dir / "open_design_daemon_candidates.json",
        "candidate": captured_dir / "candidate.png",
        "preview": captured_dir / "preview.png",
    }
    paths["manifest"].write_bytes(manifest_bytes)
    paths["candidate"].write_bytes(candidate)
    paths["preview"].write_bytes(preview)

    conn = get_conn(db_path)
    try:
        repos.create_task(
            conn,
            task_id=task_id,
            agent_id="open_design_daemon_candidate_agent",
            agent_version="0.1.0",
            name="Design candidate",
            created_by="Reviewer",
            created_by_username="reviewer",
            metadata={
                "review_contract": "open-design-candidate/v1",
                "generator_kind": "open_design_daemon",
                "candidate_manifest_sha256": manifest_sha,
            },
        )
        repos.set_task_data_classification(conn, task_id, task_classification)
        records = (
            ("file_manifest", paths["manifest"], manifest_bytes, "internal"),
            ("file_candidate", paths["candidate"], candidate, candidate_classification),
            ("file_preview", paths["preview"], preview, "internal"),
        )
        for file_id, path, content, classification in records:
            repos.create_file(
                conn,
                file_id=file_id,
                task_id=task_id,
                kind="output",
                filename=path.name,
                path=str(path),
                size_bytes=len(content),
                sha256=_sha(content),
                classification=classification,
            )
        repos.set_task_outputs(
            conn, task_id, ["file_manifest", "file_candidate", "file_preview"]
        )
        repos.set_task_status(conn, task_id, "queued")
        repos.set_task_status(conn, task_id, "validating")
        repos.set_task_status(conn, task_id, "running")
        repos.set_task_status(conn, task_id, "waiting_review")
    finally:
        conn.close()
    return {
        "task_id": task_id,
        "candidate_sha256": _sha(preview),
        "preview_sha256": _sha(preview),
    }


def _service(
    tmp_path: Path,
    *,
    task_classification: str = "internal",
    candidate_classification: str = "internal",
    fail_human_review: bool = False,
    escape_human_review: bool = False,
    escape_transaction_sql: str | None = None,
    corrupt_human_review: bool = False,
    use_real_human_review: bool = False,
    fault_hook=None,
    target_present: bool = True,
    allow_synthetic_internal_candidates: bool = True,
):
    db_path = tmp_path / "flai.db"
    task_runs = tmp_path / "task_runs"
    target_root = tmp_path / "trusted_assets"
    target_root.mkdir()
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        install_design_promotion_schema(conn)
    finally:
        conn.close()
    seeded = _seed_candidate(
        db_path,
        task_runs,
        task_classification=task_classification,
        candidate_classification=candidate_classification,
    )
    current_asset = _png(2, 2, b"\xaa\xbb\xcc")
    current_frame = _png(100, 80, b"\xdd\xee\xff")
    (target_root / "frontend/src/assets/open-design").mkdir(parents=True)
    (target_root / "frames").mkdir()
    target_path = target_root / "frontend/src/assets/open-design/task-review-summary.png"
    if target_present:
        target_path.write_bytes(current_asset)
    (target_root / "frames/task-card-default.png").write_bytes(current_frame)
    registry = TargetRegistry(
        (
            AssetTarget(
                target_id="open_design_task_review_summary_v1",
                asset_slot="task_review_summary",
                relative_path="frontend/src/assets/open-design/task-review-summary.png",
                frames=(
                    CurrentFrame(
                        slot_id="default_desktop_light",
                        relative_path="frames/task-card-default.png",
                        viewport_width=100,
                        viewport_height=80,
                        dpr=1,
                        state="default",
                        theme="light",
                        locale="zh-CN",
                    ),
                ),
            ),
        )
    )

    def _apply_human_review(conn, **kwargs):
        if fail_human_review:
            raise RuntimeError("injected human-review failure")
        action = kwargs["action"]
        created_at = now_iso()
        conn.execute(
            """
            INSERT INTO task_human_decisions
                (id, task_id, paired_advice_id, action, reason_code, comment,
                 reviewer_username, reviewer_display_name, schema_version, created_at)
            VALUES (?, ?, NULL, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                kwargs["decision_id"],
                kwargs["task_id"],
                action,
                kwargs["reason_code"],
                kwargs["comment"],
                kwargs["reviewer_username"],
                (
                    "Wrong Reviewer"
                    if corrupt_human_review
                    else kwargs["reviewer_display_name"]
                ),
                created_at,
            ),
        )
        event = repos.append_event(
            conn,
            task_id=kwargs["task_id"],
            agent_id="open_design_daemon_candidate_agent",
            event_type="review_approved" if action == "approve" else "review_rejected",
            level="info" if action == "approve" else "warning",
            message="synthetic P2.8 human decision",
            payload={
                "reviewer": (
                    "Wrong Reviewer"
                    if corrupt_human_review
                    else kwargs["reviewer_display_name"]
                ),
                "reviewer_username": kwargs["reviewer_username"],
                "comment": kwargs["comment"],
                "decision_id": kwargs["decision_id"],
                "reason_code": kwargs["reason_code"],
                "paired_advice_id": None,
            },
        )
        assert event is not None
        new_status = "completed" if action == "approve" else "failed"
        error_message = None
        if action == "reject":
            error_message = (
                f"人工拒绝（reviewer={kwargs['reviewer_display_name']}；"
                f"reason={kwargs['reason_code']}）"
                + (f"：{kwargs['comment']}" if kwargs["comment"] else "")
            )
        conn.execute(
            "UPDATE tasks SET status=?, updated_at=?, finished_at=?, error_message=? WHERE id=?",
            (new_status, created_at, created_at, error_message, kwargs["task_id"]),
        )
        if escape_human_review:
            conn.execute("SELECT 1").connection.commit()
        if escape_transaction_sql is not None:
            conn.execute(escape_transaction_sql)
        return {"status": new_status, "decision_id": kwargs["decision_id"]}

    def _apply_real_human_review(conn, **kwargs):
        task, _sample_rows = repos.apply_human_review_in_transaction(
            conn,
            kwargs["task_id"],
            decision_id=kwargs["decision_id"],
            action=kwargs["action"],
            reviewer_display_name=kwargs["reviewer_display_name"],
            reviewer_username=kwargs["reviewer_username"],
            reason_code=kwargs["reason_code"],
            comment=kwargs["comment"],
        )
        return task

    service = DesignPromotionService(
        conn_factory=lambda: get_conn(db_path),
        task_runs_dir=task_runs,
        target_root=target_root,
        promotion_runtime_dir=tmp_path / "promotion_runtime",
        targets=registry,
        human_review_applier=(
            _apply_real_human_review if use_real_human_review else _apply_human_review
        ),
        fault_hook=fault_hook,
        allow_synthetic_internal_candidates=allow_synthetic_internal_candidates,
    )
    seeded["target_path"] = str(target_path)
    seeded["target_preimage_sha256"] = _sha(current_asset) if target_present else None
    return service, seeded, db_path


def test_create_comparison_binds_exact_internal_pngs_and_serves_only_frames(tmp_path) -> None:
    service, seeded, _db_path = _service(tmp_path)
    response = service.create_comparison(
        ComparisonCreate(
            request_id="req_" + "1" * 32,
            task_id=seeded["task_id"],
        ),
        actor=Actor(username="reviewer", display_name="Reviewer"),
    )

    assert response["schema_version"] == "flai-design-comparison/v1"
    assert response["candidate"]["execution_trust"] == "untrusted_generated"
    assert response["candidate"]["asset_sha256"] == seeded["candidate_sha256"]
    assert response["frames"][0]["candidate"]["scan"] == "passed"
    assert response["frames"][0]["candidate"]["sha256"] == seeded["preview_sha256"]
    _assert_public_contract(response)

    frame = service.get_comparison_frame(
        response["comparison_id"], response["frames"][0]["frame_id"], "candidate"
    )
    assert frame.media_type == "image/png"
    assert _sha(frame.content) == seeded["preview_sha256"]


@pytest.mark.parametrize("side", ["current", "candidate"])
def test_comparison_frames_recheck_task_classification_before_serving(
    tmp_path, side: str
) -> None:
    service, seeded, db_path = _service(tmp_path)
    comparison = service.create_comparison(
        ComparisonCreate(
            request_id="req_" + "f" * 32,
            task_id=seeded["task_id"],
        ),
        actor=Actor(username="reviewer", display_name="Reviewer"),
    )
    conn = get_conn(db_path)
    try:
        # Privileged tamper fixture: remove the ordinary sealed-package guard so
        # the read boundary itself must still fail closed on a drifted class.
        conn.execute("DROP TRIGGER trg_review_package_tasks_provenance_immutable")
        conn.execute(
            "UPDATE tasks SET data_classification='sensitive' WHERE id=?",
            (seeded["task_id"],),
        )
    finally:
        conn.close()

    with pytest.raises(SensitiveCandidateRequiresRoleAxis):
        service.get_comparison_frame(
            comparison["comparison_id"],
            comparison["frames"][0]["frame_id"],
            side,
        )


def test_comparison_rejects_non_internal_candidate_without_side_channel(tmp_path) -> None:
    service, seeded, db_path = _service(
        tmp_path,
        task_classification="sensitive",
        candidate_classification="sensitive",
    )
    with pytest.raises(SensitiveCandidateRequiresRoleAxis) as caught:
        service.create_comparison(
            ComparisonCreate(
                request_id="req_" + "2" * 32,
                task_id=seeded["task_id"],
            ),
            actor=Actor(username="reviewer", display_name="Reviewer"),
        )
    assert caught.value.code == "sensitive_candidate_requires_role_axis"
    conn = get_conn(db_path)
    try:
        assert conn.execute("SELECT count(*) FROM design_comparisons").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM design_idempotency").fetchone()[0] == 0
    finally:
        conn.close()


def test_default_service_rejects_manifest_declared_sensitive_even_if_db_rows_are_internal(
    tmp_path,
) -> None:
    service, seeded, db_path = _service(
        tmp_path,
        allow_synthetic_internal_candidates=False,
    )
    with pytest.raises(SensitiveCandidateRequiresRoleAxis) as caught:
        service.create_comparison(
            ComparisonCreate(
                request_id="req_" + "2" * 32,
                task_id=seeded["task_id"],
            ),
            actor=Actor(username="reviewer", display_name="Reviewer"),
        )
    assert caught.value.code == "sensitive_candidate_requires_role_axis"
    conn = get_conn(db_path)
    try:
        assert conn.execute("SELECT count(*) FROM design_comparisons").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM design_idempotency").fetchone()[0] == 0
    finally:
        conn.close()


def test_candidate_selection_and_task_human_decision_commit_as_one_named_fact(tmp_path) -> None:
    service, seeded, db_path = _service(tmp_path)
    comparison = service.create_comparison(
        ComparisonCreate(request_id="req_" + "3" * 32, task_id=seeded["task_id"]),
        actor=Actor(username="candidate_reviewer", display_name="Candidate Reviewer"),
    )
    selected = service.decide_candidate(
        comparison["comparison_id"],
        SelectionRequest(
            request_id="req_" + "4" * 32,
            action="approve",
            expected_comparison_sha256=comparison["comparison_sha256"],
            candidate_id=comparison["candidate"]["candidate_id"],
            reason_code=None,
            comment="matrix checked",
        ),
        actor=Actor(username="candidate_reviewer", display_name="Candidate Reviewer"),
    )

    assert selected["task_status"] == "completed"
    assert selected["selected_by"]["username"] == "candidate_reviewer"
    assert service.get_comparison(comparison["comparison_id"])["phase"] == "candidate_approved"
    conn = get_conn(db_path)
    try:
        selection = conn.execute(
            "SELECT * FROM design_candidate_selections WHERE id=?",
            (selected["selection_id"],),
        ).fetchone()
        decision = conn.execute(
            "SELECT * FROM task_human_decisions WHERE id=?",
            (selected["task_decision_id"],),
        ).fetchone()
        assert selection is not None and decision is not None
        assert selection["task_decision_id"] == decision["id"]
        assert decision["reviewer_username"] == "candidate_reviewer"
    finally:
        conn.close()


def test_candidate_selection_uses_the_real_transactional_human_review_primitive(
    tmp_path,
) -> None:
    service, seeded, db_path = _service(tmp_path, use_real_human_review=True)
    comparison = service.create_comparison(
        ComparisonCreate(request_id="req_" + "d" * 32, task_id=seeded["task_id"]),
        actor=Actor(username="reviewer", display_name="Reviewer"),
    )
    body = SelectionRequest(
        request_id="req_" + "e" * 32,
        action="approve",
        expected_comparison_sha256=comparison["comparison_sha256"],
        candidate_id=comparison["candidate"]["candidate_id"],
        reason_code=None,
        comment="matrix checked",
    )
    actor = Actor(username="named_reviewer", display_name="Named Reviewer")
    selected = service.decide_candidate(
        comparison["comparison_id"],
        body,
        actor=actor,
    )
    replay = service.decide_candidate(comparison["comparison_id"], body, actor=actor)
    assert replay == selected
    assert selected["task_status"] == "completed"
    conn = get_conn(db_path)
    try:
        decision = conn.execute(
            "SELECT * FROM task_human_decisions WHERE id=?",
            (selected["task_decision_id"],),
        ).fetchone()
        assert decision["reviewer_username"] == "named_reviewer"
        event = conn.execute(
            "SELECT payload_json FROM task_events "
            "WHERE task_id=? AND event_type='review_approved'",
            (seeded["task_id"],),
        ).fetchone()
        assert json.loads(event[0])["decision_id"] == selected["task_decision_id"]
        assert conn.execute(
            "SELECT count(*) FROM design_candidate_selections"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT count(*) FROM task_human_decisions"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT count(*) FROM task_events "
            "WHERE task_id=? AND event_type='review_approved'",
            (seeded["task_id"],),
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT count(*) FROM design_idempotency "
            "WHERE operation='candidate_selection'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT status FROM tasks WHERE id=?", (seeded["task_id"],)
        ).fetchone()[0] == "completed"
    finally:
        conn.close()


def test_candidate_rejection_maps_local_reason_into_global_human_review(tmp_path) -> None:
    service, seeded, db_path = _service(tmp_path)
    comparison = service.create_comparison(
        ComparisonCreate(request_id="req_" + "5" * 32, task_id=seeded["task_id"]),
        actor=Actor(username="reviewer", display_name="Reviewer"),
    )
    rejected = service.decide_candidate(
        comparison["comparison_id"],
        SelectionRequest(
            request_id="req_" + "6" * 32,
            action="reject",
            expected_comparison_sha256=comparison["comparison_sha256"],
            candidate_id=None,
            reason_code="accessibility",
            comment="  contrast evidence missing  ",
        ),
        actor=Actor(username="named_reviewer", display_name="Named Reviewer"),
    )

    assert rejected["reason_code"] == "accessibility"
    assert rejected["comment"] == "contrast evidence missing"
    assert rejected["task_status"] == "failed"
    assert service.get_comparison(comparison["comparison_id"])["phase"] == "candidate_rejected"
    conn = get_conn(db_path)
    try:
        decision = conn.execute(
            "SELECT reason_code, comment FROM task_human_decisions WHERE id=?",
            (rejected["task_decision_id"],),
        ).fetchone()
        assert tuple(decision) == (
            "other",
            "design_selection_reason=accessibility\ncontrast evidence missing",
        )
    finally:
        conn.close()


def test_human_review_callback_failure_rolls_back_selection_and_decision(tmp_path) -> None:
    service, seeded, db_path = _service(tmp_path, fail_human_review=True)
    comparison = service.create_comparison(
        ComparisonCreate(request_id="req_" + "7" * 32, task_id=seeded["task_id"]),
        actor=Actor(username="reviewer", display_name="Reviewer"),
    )
    with pytest.raises(RuntimeError, match="injected human-review failure"):
        service.decide_candidate(
            comparison["comparison_id"],
            SelectionRequest(
                request_id="req_" + "8" * 32,
                action="approve",
                expected_comparison_sha256=comparison["comparison_sha256"],
                candidate_id=comparison["candidate"]["candidate_id"],
                reason_code=None,
                comment=None,
            ),
            actor=Actor(username="reviewer", display_name="Reviewer"),
        )

    conn = get_conn(db_path)
    try:
        assert conn.execute("SELECT count(*) FROM design_candidate_selections").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM task_human_decisions").fetchone()[0] == 0
        assert conn.execute(
            "SELECT count(*) FROM design_idempotency WHERE operation='candidate_selection'"
        ).fetchone()[0] == 0
        assert conn.execute("SELECT status FROM tasks WHERE id=?", (seeded["task_id"],)).fetchone()[0] == "waiting_review"
    finally:
        conn.close()


@pytest.mark.parametrize("mode", ["escape", "corrupt"])
def test_human_review_callback_cannot_escape_or_weaken_exact_named_fact(
    tmp_path, mode: str
) -> None:
    service, seeded, db_path = _service(
        tmp_path,
        escape_human_review=mode == "escape",
        corrupt_human_review=mode == "corrupt",
    )
    comparison = service.create_comparison(
        ComparisonCreate(request_id="req_" + "b" * 32, task_id=seeded["task_id"]),
        actor=Actor(username="reviewer", display_name="Reviewer"),
    )
    with pytest.raises(RuntimeError):
        service.decide_candidate(
            comparison["comparison_id"],
            SelectionRequest(
                request_id="req_" + "c" * 32,
                action="approve",
                expected_comparison_sha256=comparison["comparison_sha256"],
                candidate_id=comparison["candidate"]["candidate_id"],
                reason_code=None,
                comment="matrix checked",
            ),
            actor=Actor(username="reviewer", display_name="Reviewer"),
        )

    conn = get_conn(db_path)
    try:
        effects = {
            "selections": conn.execute(
                "SELECT count(*) FROM design_candidate_selections"
            ).fetchone()[0],
            "human_decisions": conn.execute(
                "SELECT count(*) FROM task_human_decisions"
            ).fetchone()[0],
            "review_events": conn.execute(
                "SELECT count(*) FROM task_events "
                "WHERE task_id=? AND event_type='review_approved'",
                (seeded["task_id"],),
            ).fetchone()[0],
            "selection_idempotency": conn.execute(
                "SELECT count(*) FROM design_idempotency "
                "WHERE operation='candidate_selection'"
            ).fetchone()[0],
            "task_status": conn.execute(
                "SELECT status FROM tasks WHERE id=?", (seeded["task_id"],)
            ).fetchone()[0],
        }
        assert effects == {
            "selections": 0,
            "human_decisions": 0,
            "review_events": 0,
            "selection_idempotency": 0,
            "task_status": "waiting_review",
        }
    finally:
        conn.close()


@pytest.mark.parametrize(
    "escape_sql",
    ["-- harmless comment\nCOMMIT", "/* harmless comment */ COMMIT"],
    ids=["line-comment", "block-comment"],
)
def test_commented_transaction_control_cannot_escape_atomic_selection(
    tmp_path, escape_sql: str
) -> None:
    service, seeded, db_path = _service(
        tmp_path,
        escape_transaction_sql=escape_sql,
    )
    comparison = service.create_comparison(
        ComparisonCreate(request_id="req_" + "0" * 32, task_id=seeded["task_id"]),
        actor=Actor(username="reviewer", display_name="Reviewer"),
    )

    with pytest.raises(RuntimeError):
        service.decide_candidate(
            comparison["comparison_id"],
            SelectionRequest(
                request_id="req_" + "f" * 32,
                action="approve",
                expected_comparison_sha256=comparison["comparison_sha256"],
                candidate_id=comparison["candidate"]["candidate_id"],
                reason_code=None,
                comment="matrix checked",
            ),
            actor=Actor(username="reviewer", display_name="Reviewer"),
        )

    conn = get_conn(db_path)
    try:
        assert {
            "selections": conn.execute(
                "SELECT count(*) FROM design_candidate_selections"
            ).fetchone()[0],
            "human_decisions": conn.execute(
                "SELECT count(*) FROM task_human_decisions"
            ).fetchone()[0],
            "review_events": conn.execute(
                "SELECT count(*) FROM task_events "
                "WHERE task_id=? AND event_type='review_approved'",
                (seeded["task_id"],),
            ).fetchone()[0],
            "selection_idempotency": conn.execute(
                "SELECT count(*) FROM design_idempotency "
                "WHERE operation='candidate_selection'"
            ).fetchone()[0],
            "task_status": conn.execute(
                "SELECT status FROM tasks WHERE id=?", (seeded["task_id"],)
            ).fetchone()[0],
        } == {
            "selections": 0,
            "human_decisions": 0,
            "review_events": 0,
            "selection_idempotency": 0,
            "task_status": "waiting_review",
        }
    finally:
        conn.close()


def test_release_request_and_named_release_approval_are_separate_from_candidate_decision(
    tmp_path,
) -> None:
    service, seeded, db_path = _service(tmp_path)
    comparison = service.create_comparison(
        ComparisonCreate(request_id="req_" + "9" * 32, task_id=seeded["task_id"]),
        actor=Actor(username="comparison_author", display_name="Comparison Author"),
    )
    selection = service.decide_candidate(
        comparison["comparison_id"],
        SelectionRequest(
            request_id="req_" + "a" * 32,
            action="approve",
            expected_comparison_sha256=comparison["comparison_sha256"],
            candidate_id=comparison["candidate"]["candidate_id"],
            reason_code=None,
            comment=None,
        ),
        actor=Actor(username="candidate_reviewer", display_name="Candidate Reviewer"),
    )
    target_preimage = ExpectedTarget.model_validate(comparison["target"]["preimage"])
    release = service.create_release_request(
        ReleaseRequestCreate(
            request_id="req_" + "b" * 32,
            selection_id=selection["selection_id"],
            expected_comparison_sha256=comparison["comparison_sha256"],
            expected_candidate_sha256=selection["candidate_sha256"],
            expected_target=target_preimage,
        ),
        actor=Actor(username="release_requester", display_name="Release Requester"),
    )
    assert release["state"] == "awaiting_release_approval"
    assert release["summary"]["candidate"]["candidate_approval"]["decision_id"] == selection["task_decision_id"]
    assert release["summary"]["candidate"]["candidate_approval"]["username"] == "candidate_reviewer"
    assert release["summary"]["candidate"]["candidate_approval"]["display_name"] == "Candidate Reviewer"

    approved = service.decide_release(
        release["release_request_id"],
        ReleaseDecisionRequest(
            request_id="req_" + "c" * 32,
            action="approve",
            expected_summary_sha256=release["summary_sha256"],
            reason_code=None,
            comment="ready",
        ),
        actor=Actor(username="release_approver", display_name="Release Approver"),
    )
    assert approved["state"] == "release_approved"
    assert approved["decided_by"]["username"] == "release_approver"
    assert approved["release_package"]["summary"] == release["summary"]
    assert approved["release_package"]["release_approval"]["decision_id"] == approved["decision_id"]
    assert len(approved["release_package"]["release_package_sha256"]) == 64

    conn = get_conn(db_path)
    try:
        assert conn.execute("SELECT count(*) FROM task_human_decisions").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM design_release_decisions").fetchone()[0] == 1
    finally:
        conn.close()


def test_comparison_post_is_get_or_create_and_projects_resume_workflow(tmp_path) -> None:
    service, seeded, db_path = _service(tmp_path)
    first = service.create_comparison(
        ComparisonCreate(request_id="req_" + "d" * 32, task_id=seeded["task_id"]),
        actor=Actor(username="reviewer", display_name="Reviewer"),
    )
    refreshed_pending = service.create_comparison(
        ComparisonCreate(request_id="req_" + "e" * 32, task_id=seeded["task_id"]),
        actor=Actor(username="reviewer", display_name="Reviewer"),
    )
    assert refreshed_pending["comparison_id"] == first["comparison_id"]
    assert refreshed_pending["phase"] == "candidate_pending"
    assert refreshed_pending["workflow"] == {
        "selection": None,
        "release_request": None,
        "release_decision": None,
        "latest_publish": None,
    }

    selection = service.decide_candidate(
        first["comparison_id"],
        SelectionRequest(
            request_id="req_" + "f" * 32,
            action="approve",
            expected_comparison_sha256=first["comparison_sha256"],
            candidate_id=first["candidate"]["candidate_id"],
            reason_code=None,
            comment=None,
        ),
        actor=Actor(username="candidate_reviewer", display_name="Candidate Reviewer"),
    )
    refreshed_approved = service.create_comparison(
        ComparisonCreate(request_id="req_" + "0" * 32, task_id=seeded["task_id"]),
        actor=Actor(username="reviewer", display_name="Reviewer"),
    )
    assert refreshed_approved["comparison_id"] == first["comparison_id"]
    assert refreshed_approved["phase"] == "candidate_approved"
    assert refreshed_approved["workflow"]["selection"]["selection_id"] == selection["selection_id"]
    conn = get_conn(db_path)
    try:
        assert conn.execute("SELECT count(*) FROM design_comparisons").fetchone()[0] == 1
    finally:
        conn.close()


def _approved_release(service, seeded):
    values = iter("12345")
    comparison = service.create_comparison(
        ComparisonCreate(
            request_id="req_" + next(values) * 32, task_id=seeded["task_id"]
        ),
        actor=Actor(username="reviewer", display_name="Reviewer"),
    )
    selection = service.decide_candidate(
        comparison["comparison_id"],
        SelectionRequest(
            request_id="req_" + next(values) * 32,
            action="approve",
            expected_comparison_sha256=comparison["comparison_sha256"],
            candidate_id=comparison["candidate"]["candidate_id"],
            reason_code=None,
            comment=None,
        ),
        actor=Actor(username="candidate_reviewer", display_name="Candidate Reviewer"),
    )
    release = service.create_release_request(
        ReleaseRequestCreate(
            request_id="req_" + next(values) * 32,
            selection_id=selection["selection_id"],
            expected_comparison_sha256=comparison["comparison_sha256"],
            expected_candidate_sha256=selection["candidate_sha256"],
            expected_target=ExpectedTarget.model_validate(
                comparison["target"]["preimage"]
            ),
        ),
        actor=Actor(username="requester", display_name="Requester"),
    )
    decision = service.decide_release(
        release["release_request_id"],
        ReleaseDecisionRequest(
            request_id="req_" + next(values) * 32,
            action="approve",
            expected_summary_sha256=release["summary_sha256"],
            reason_code=None,
            comment=None,
        ),
        actor=Actor(username="release_reviewer", display_name="Release Reviewer"),
    )
    return comparison, selection, release, decision


def test_publish_and_rollback_use_durable_intents_exact_hashes_and_backups(tmp_path) -> None:
    service, seeded, db_path = _service(tmp_path)
    comparison, _selection, release, decision = _approved_release(service, seeded)
    package_sha = decision["release_package"]["release_package_sha256"]
    publish_body = PublishRequest(
        request_id="req_" + "6" * 32,
        expected_release_package_sha256=package_sha,
        expected_target=ExpectedTarget.model_validate(comparison["target"]["preimage"]),
        confirm=True,
    )
    published = service.publish_release(
        release["release_request_id"],
        publish_body,
        actor=Actor(username="publisher", display_name="Publisher"),
    )
    assert published["state"] == "published"
    _assert_public_contract(published)
    assert _sha(Path(seeded["target_path"]).read_bytes()) == seeded["candidate_sha256"]
    assert published["before_sha256"] == seeded["target_preimage_sha256"]
    assert published["backup_sha256"] == seeded["target_preimage_sha256"]
    assert service.publish_release(
        release["release_request_id"],
        publish_body,
        actor=Actor(username="publisher", display_name="Publisher"),
    ) == published
    projected = service.get_comparison(comparison["comparison_id"])
    assert projected["phase"] == "published"
    assert projected["workflow"]["latest_publish"] == published

    rolled_back = service.rollback_release(
        release["release_request_id"],
        RollbackRequest(
            request_id="req_" + "7" * 32,
            expected_release_package_sha256=package_sha,
            expected_current_sha256=published["after_sha256"],
            confirm=True,
        ),
        actor=Actor(username="rollback_operator", display_name="Rollback Operator"),
    )
    assert rolled_back["state"] == "rolled_back"
    _assert_public_contract(rolled_back)
    assert _sha(Path(seeded["target_path"]).read_bytes()) == seeded["target_preimage_sha256"]
    projected = service.get_comparison(comparison["comparison_id"])
    assert projected["phase"] == "rolled_back"
    assert projected["workflow"]["latest_publish"] == rolled_back
    conn = get_conn(db_path)
    try:
        assert [
            row[0]
            for row in conn.execute(
                "SELECT event_type FROM design_publish_events ORDER BY rowid"
            )
        ] == [
            "publish_intent",
            "publish_commit",
            "rollback_intent",
            "rollback_commit",
        ]
        assert_design_promotion_schema(conn)
    finally:
        conn.close()


def test_schema_witness_rejects_cross_ledger_publish_binding_drift(tmp_path) -> None:
    service, seeded, db_path = _service(tmp_path)
    comparison, _selection, release, decision = _approved_release(service, seeded)
    service.publish_release(
        release["release_request_id"],
        PublishRequest(
            request_id="req_" + "6" * 32,
            expected_release_package_sha256=decision["release_package"]["release_package_sha256"],
            expected_target=ExpectedTarget.model_validate(comparison["target"]["preimage"]),
            confirm=True,
        ),
        actor=Actor(username="publisher", display_name="Publisher"),
    )
    conn = get_conn(db_path)
    try:
        trigger_name = "trg_design_publish_events_no_update"
        trigger_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?",
            (trigger_name,),
        ).fetchone()[0]
        conn.execute(f'DROP TRIGGER "{trigger_name}"')
        conn.execute(
            "UPDATE design_publish_events SET target_id='tampered_target' "
            "WHERE event_type='publish_intent'"
        )
        conn.execute(trigger_sql)
        witnesses = design_promotion_schema_witnesses(conn)
        assert witnesses["required_triggers"] is True
        assert witnesses["reference_integrity"] is False
        with pytest.raises(RuntimeError, match="reference_integrity"):
            assert_design_promotion_schema(conn)
    finally:
        conn.close()


def test_get_reconciles_publish_intent_at_candidate_hash_as_recovered_commit(tmp_path) -> None:
    armed = True

    def fault(point: str) -> None:
        nonlocal armed
        if armed and point == "after_publish_replace":
            armed = False
            raise RuntimeError("simulated process loss after replace")

    service, seeded, db_path = _service(tmp_path, fault_hook=fault)
    comparison, _selection, release, decision = _approved_release(service, seeded)
    body = PublishRequest(
        request_id="req_" + "6" * 32,
        expected_release_package_sha256=decision["release_package"]["release_package_sha256"],
        expected_target=ExpectedTarget.model_validate(comparison["target"]["preimage"]),
        confirm=True,
    )
    with pytest.raises(RuntimeError, match="simulated process loss"):
        service.publish_release(
            release["release_request_id"],
            body,
            actor=Actor(username="publisher", display_name="Publisher"),
        )
    assert _sha(Path(seeded["target_path"]).read_bytes()) == seeded["candidate_sha256"]

    projected = service.get_comparison(comparison["comparison_id"])
    assert projected["phase"] == "published"
    recovered = projected["workflow"]["latest_publish"]
    assert recovered["state"] == "published"
    assert service.publish_release(
        release["release_request_id"],
        body,
        actor=Actor(username="publisher", display_name="Publisher"),
    ) == recovered
    conn = get_conn(db_path)
    try:
        assert [row[0] for row in conn.execute(
            "SELECT event_type FROM design_publish_events ORDER BY rowid"
        )] == ["publish_intent", "publish_recovered_commit"]
    finally:
        conn.close()


def test_publish_recovery_requires_the_bound_backup_artifact(tmp_path) -> None:
    armed = True

    def fault(point: str) -> None:
        nonlocal armed
        if armed and point == "after_publish_replace":
            armed = False
            raise RuntimeError("simulated process loss after replace")

    service, seeded, db_path = _service(tmp_path, fault_hook=fault)
    comparison, _selection, release, decision = _approved_release(service, seeded)
    body = PublishRequest(
        request_id="req_" + "6" * 32,
        expected_release_package_sha256=decision["release_package"]["release_package_sha256"],
        expected_target=ExpectedTarget.model_validate(comparison["target"]["preimage"]),
        confirm=True,
    )
    with pytest.raises(RuntimeError, match="simulated process loss"):
        service.publish_release(
            release["release_request_id"],
            body,
            actor=Actor(username="publisher", display_name="Publisher"),
        )
    conn = get_conn(db_path)
    try:
        backup_relative = conn.execute(
            "SELECT backup_relative_path FROM design_publish_events "
            "WHERE event_type='publish_intent'"
        ).fetchone()[0]
    finally:
        conn.close()
    (tmp_path / "promotion_runtime" / backup_relative).unlink()

    projected = service.get_comparison(comparison["comparison_id"])

    assert projected["phase"] == "manual_intervention"
    assert projected["workflow"]["latest_publish"] is None
    conn = get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT event_type, details_json FROM design_publish_events ORDER BY rowid"
        ).fetchall()
        assert [row[0] for row in rows] == [
            "publish_intent",
            "publish_manual_intervention",
        ]
        details = json.loads(bytes(rows[-1][1]))
        assert details["artifact_error"] == "backup_not_safely_readable"
    finally:
        conn.close()


def test_absent_rollback_recovery_requires_the_bound_quarantine_artifact(tmp_path) -> None:
    armed = True

    def fault(point: str) -> None:
        nonlocal armed
        if armed and point == "after_rollback_replace":
            armed = False
            raise RuntimeError("simulated process loss after rollback replace")

    service, seeded, db_path = _service(
        tmp_path, target_present=False, fault_hook=fault
    )
    comparison, _selection, release, decision = _approved_release(service, seeded)
    package_sha = decision["release_package"]["release_package_sha256"]
    published = service.publish_release(
        release["release_request_id"],
        PublishRequest(
            request_id="req_" + "6" * 32,
            expected_release_package_sha256=package_sha,
            expected_target=ExpectedTarget(kind="absent"),
            confirm=True,
        ),
        actor=Actor(username="publisher", display_name="Publisher"),
    )
    with pytest.raises(RuntimeError, match="simulated process loss"):
        service.rollback_release(
            release["release_request_id"],
            RollbackRequest(
                request_id="req_" + "7" * 32,
                expected_release_package_sha256=package_sha,
                expected_current_sha256=published["after_sha256"],
                confirm=True,
            ),
            actor=Actor(
                username="rollback_operator", display_name="Rollback Operator"
            ),
        )
    conn = get_conn(db_path)
    try:
        details = json.loads(
            bytes(
                conn.execute(
                    "SELECT details_json FROM design_publish_events "
                    "WHERE event_type='rollback_intent'"
                ).fetchone()[0]
            )
        )
    finally:
        conn.close()
    (tmp_path / "trusted_assets" / details["quarantine_relative_path"]).unlink()

    projected = service.get_comparison(comparison["comparison_id"])

    assert projected["phase"] == "manual_intervention"
    assert projected["workflow"]["latest_publish"] is None
    conn = get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT event_type, details_json FROM design_publish_events ORDER BY rowid"
        ).fetchall()
        assert [row[0] for row in rows] == [
            "publish_intent",
            "publish_commit",
            "rollback_intent",
            "rollback_manual_intervention",
        ]
        recovery = json.loads(bytes(rows[-1][1]))
        assert recovery["artifact_error"] == "quarantine_not_safely_readable"
    finally:
        conn.close()


def test_get_reconciles_publish_intent_at_preimage_as_abort(tmp_path) -> None:
    armed = True

    def fault(point: str) -> None:
        nonlocal armed
        if armed and point == "after_publish_intent":
            armed = False
            raise RuntimeError("simulated process loss after intent")

    service, seeded, db_path = _service(tmp_path, fault_hook=fault)
    comparison, _selection, release, decision = _approved_release(service, seeded)
    body = PublishRequest(
        request_id="req_" + "6" * 32,
        expected_release_package_sha256=decision["release_package"]["release_package_sha256"],
        expected_target=ExpectedTarget.model_validate(comparison["target"]["preimage"]),
        confirm=True,
    )
    with pytest.raises(RuntimeError, match="simulated process loss"):
        service.publish_release(
            release["release_request_id"],
            body,
            actor=Actor(username="publisher", display_name="Publisher"),
        )
    projected = service.get_comparison(comparison["comparison_id"])
    assert projected["phase"] == "publish_ready"
    assert projected["workflow"]["latest_publish"] is None
    conn = get_conn(db_path)
    try:
        assert [row[0] for row in conn.execute(
            "SELECT event_type FROM design_publish_events ORDER BY rowid"
        )] == ["publish_intent", "publish_abort"]
    finally:
        conn.close()


def test_get_reconciles_unknown_publish_hash_as_manual_without_file_mutation(tmp_path) -> None:
    armed = True

    def fault(point: str) -> None:
        nonlocal armed
        if armed and point == "after_publish_intent":
            armed = False
            raise RuntimeError("simulated process loss after intent")

    service, seeded, db_path = _service(tmp_path, fault_hook=fault)
    comparison, _selection, release, decision = _approved_release(service, seeded)
    body = PublishRequest(
        request_id="req_" + "6" * 32,
        expected_release_package_sha256=decision["release_package"]["release_package_sha256"],
        expected_target=ExpectedTarget.model_validate(comparison["target"]["preimage"]),
        confirm=True,
    )
    with pytest.raises(RuntimeError, match="simulated process loss"):
        service.publish_release(
            release["release_request_id"],
            body,
            actor=Actor(username="publisher", display_name="Publisher"),
        )
    unknown = _png(2, 2, b"\x12\x34\x56")
    Path(seeded["target_path"]).write_bytes(unknown)

    projected = service.get_comparison(comparison["comparison_id"])
    assert projected["phase"] == "manual_intervention"
    assert projected["workflow"]["latest_publish"] is None
    assert Path(seeded["target_path"]).read_bytes() == unknown
    conn = get_conn(db_path)
    try:
        assert [row[0] for row in conn.execute(
            "SELECT event_type FROM design_publish_events ORDER BY rowid"
        )] == ["publish_intent", "publish_manual_intervention"]
    finally:
        conn.close()


@pytest.mark.parametrize("tamper", ["invalid_png", "symlink"])
def test_get_reconciles_unreadable_publish_target_as_manual_without_mutation(
    tmp_path, tamper: str
) -> None:
    armed = True

    def fault(point: str) -> None:
        nonlocal armed
        if armed and point == "after_publish_intent":
            armed = False
            raise RuntimeError("simulated process loss after intent")

    service, seeded, db_path = _service(tmp_path, fault_hook=fault)
    comparison, _selection, release, decision = _approved_release(service, seeded)
    body = PublishRequest(
        request_id="req_" + "6" * 32,
        expected_release_package_sha256=decision["release_package"]["release_package_sha256"],
        expected_target=ExpectedTarget.model_validate(comparison["target"]["preimage"]),
        confirm=True,
    )
    with pytest.raises(RuntimeError, match="simulated process loss"):
        service.publish_release(
            release["release_request_id"],
            body,
            actor=Actor(username="publisher", display_name="Publisher"),
        )

    target_path = Path(seeded["target_path"])
    if tamper == "invalid_png":
        target_path.write_bytes(b"not-a-png")
    else:
        outside = tmp_path / "outside.png"
        outside.write_bytes(_png(2, 2, b"\x12\x34\x56"))
        target_path.unlink()
        try:
            target_path.symlink_to(outside)
        except OSError as exc:
            pytest.skip(f"symlink fixture unavailable: {exc}")

    projected = service.get_comparison(comparison["comparison_id"])
    assert projected["phase"] == "manual_intervention"
    assert projected["workflow"]["latest_publish"] is None
    if tamper == "invalid_png":
        assert target_path.read_bytes() == b"not-a-png"
    else:
        assert target_path.is_symlink()
    conn = get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT event_type, details_json FROM design_publish_events ORDER BY rowid"
        ).fetchall()
        assert [row[0] for row in rows] == [
            "publish_intent",
            "publish_manual_intervention",
        ]
        details = json.loads(bytes(rows[-1][1]))
        assert details["observed_target"] == {"kind": "unreadable"}
        assert details["observation_error"] == "target_not_safely_readable"
    finally:
        conn.close()


def test_absent_allowlisted_target_can_publish_then_rollback_to_absence(tmp_path) -> None:
    service, seeded, db_path = _service(tmp_path, target_present=False)
    comparison, _selection, release, decision = _approved_release(service, seeded)
    assert comparison["target"]["preimage"] == {"kind": "absent"}
    package_sha = decision["release_package"]["release_package_sha256"]
    published = service.publish_release(
        release["release_request_id"],
        PublishRequest(
            request_id="req_" + "6" * 32,
            expected_release_package_sha256=package_sha,
            expected_target=ExpectedTarget(kind="absent"),
            confirm=True,
        ),
        actor=Actor(username="publisher", display_name="Publisher"),
    )
    assert published["before_sha256"] is None
    assert published["backup_sha256"] is None
    assert Path(seeded["target_path"]).is_file()

    rolled_back = service.rollback_release(
        release["release_request_id"],
        RollbackRequest(
            request_id="req_" + "7" * 32,
            expected_release_package_sha256=package_sha,
            expected_current_sha256=published["after_sha256"],
            confirm=True,
        ),
        actor=Actor(username="rollback_operator", display_name="Rollback Operator"),
    )
    assert rolled_back["after_sha256"] is None
    assert rolled_back["backup_sha256"] is None
    assert not Path(seeded["target_path"]).exists()
    conn = get_conn(db_path)
    try:
        intent = conn.execute(
            "SELECT details_json FROM design_publish_events "
            "WHERE event_type='rollback_intent'"
        ).fetchone()
        details = json.loads(bytes(intent[0]))
    finally:
        conn.close()
    quarantine = details["quarantine_relative_path"]
    assert quarantine.startswith(
        "frontend/src/assets/open-design/task-review-summary.png.rollback-"
    )
    assert quarantine.endswith(".quarantine.png")
    assert (tmp_path / "trusted_assets" / quarantine).is_file()
    assert not (tmp_path / "promotion_runtime" / "quarantine").exists()


def test_api_derives_actor_and_returns_exact_sensitive_role_axis_error(tmp_path) -> None:
    service, seeded, db_path = _service(tmp_path)
    client = _api_client(service)
    response = client.post(
        "/api/design-comparisons",
        json={"request_id": "req_" + "8" * 32, "task_id": seeded["task_id"]},
    )
    assert response.status_code == 201
    assert response.json()["created_by"] == {
        "username": "api_reviewer",
        "display_name": "API Reviewer",
    }
    assert response.headers["cache-control"] == "no-store"
    refreshed = client.post(
        "/api/design-comparisons",
        json={"request_id": "req_" + "a" * 32, "task_id": seeded["task_id"]},
    )
    assert refreshed.status_code == 201
    assert refreshed.json()["comparison_id"] == response.json()["comparison_id"]
    conn = get_conn(db_path)
    try:
        assert [
            row[0]
            for row in conn.execute(
                "SELECT response_status FROM design_idempotency "
                "WHERE operation='comparison_create' ORDER BY rowid"
            )
        ] == [201, 201]
    finally:
        conn.close()

    sensitive_root = tmp_path / "sensitive"
    sensitive_root.mkdir()
    sensitive, sensitive_seeded, _sensitive_db = _service(
        sensitive_root,
        task_classification="sensitive",
        candidate_classification="sensitive",
    )
    denied = _api_client(sensitive).post(
        "/api/design-comparisons",
        json={
            "request_id": "req_" + "9" * 32,
            "task_id": sensitive_seeded["task_id"],
        },
    )
    assert denied.status_code == 403
    assert denied.json() == {
        "detail": {
            "code": "sensitive_candidate_requires_role_axis",
            "message": "sensitive candidate requires the deferred role axis",
        }
    }


def test_api_serves_comparison_frames_as_inline_no_store_png(tmp_path) -> None:
    service, seeded, _db_path = _service(tmp_path)
    client = _api_client(service)
    comparison = client.post(
        "/api/design-comparisons",
        json={"request_id": "req_" + "b" * 32, "task_id": seeded["task_id"]},
    ).json()

    response = client.get(comparison["frames"][0]["candidate"]["url"])

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-disposition"] == "inline"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"] == "default-src 'none'; sandbox"


def test_main_app_keeps_real_sensitive_p27_candidate_out_of_p28(tmp_path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    db_path = tmp_path / "flai.db"
    task_runs = tmp_path / "task_runs"
    app = create_app(
        agents_dir=repo_root / "agents",
        tools_dir=repo_root / "tools_impl",
        contracts_dir=repo_root / "contracts",
        knowledge_dir=tmp_path / "knowledge",
        db_path=db_path,
        uploads_dir=tmp_path / "uploads",
        task_runs_dir=task_runs,
        frontend_dist_dir=tmp_path / "frontend-dist",
        design_target_root=tmp_path / "trusted-assets",
        design_promotion_runtime_dir=tmp_path / "promotion-runtime",
    )
    with TestClient(app) as client:
        seed_and_login(client, db_path)
        seeded = _seed_candidate(db_path, task_runs)

        response = client.post(
            "/api/design-comparisons",
            json={
                "request_id": "req_" + "c" * 32,
                "task_id": seeded["task_id"],
            },
        )

    assert response.status_code == 403
    assert response.json() == {
        "detail": {
            "code": "sensitive_candidate_requires_role_axis",
            "message": "sensitive candidate requires the deferred role axis",
        }
    }
    conn = get_conn(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM design_comparisons").fetchone()[0] == 0
    finally:
        conn.close()
