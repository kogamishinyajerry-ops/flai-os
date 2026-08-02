from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from backend.app.storage import repos
from backend.app.runtime import runtime as runtime_module
from backend.app.runtime.package_snapshot import capture_agent_package
from backend.app.config import AGENTS_DIR
from backend.app.ontology.skill_reuse_evidence import (
    SkillReuseInvalidError,
    normalize_reuse_ref,
)
from backend.tests.test_m6_guide_conversation import (
    _CannedStub,
    _agent,
    _open_conversation,
    _orchestrate,
    _plan_reply,
)
from backend.tests.test_skill_auto_reuse_conversation import (
    _accept_and_approve_package as _accept_package_base,
)


def _accept_and_approve_package(client, app, *, task_name: str):
    """This ledger suite exercises the declared deterministic receipt path."""

    return _accept_package_base(
        client,
        app,
        task_name=task_name,
        agent_id="hello_agent",
    )


def _install_declared_hello_reuse_snapshot(app) -> None:
    """Install one test-only immutable Agent snapshot with receipt capability.

    Production ``hello_agent`` intentionally makes no such declaration.  These
    evidence-ledger cases wrap its Workflow with an exact-receipt adapter, so
    the snapshot used by Guide, batch and runtime must explicitly declare that
    test capability too; otherwise the product correctly refuses the match.
    """

    registry = app.state.agent_registry
    if getattr(registry, "_test_declared_hello_reuse_snapshot", False):
        return
    original_snapshot = registry.package_snapshot
    with TemporaryDirectory(prefix="flai-test-deterministic-reuse-") as temp_dir:
        package_dir = Path(temp_dir) / "hello_agent"
        shutil.copytree(AGENTS_DIR / "hello_agent", package_dir)
        manifest_path = package_dir / "agent.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest["version"] = "0.1.1"
        manifest["workflow"]["skill_reuse_application"] = (
            "deterministic_receipt_v1"
        )
        manifest_path.write_text(
            yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        declared_snapshot = capture_agent_package(package_dir)

    registry.package_snapshot = lambda agent_id: (
        declared_snapshot
        if agent_id == "hello_agent"
        else original_snapshot(agent_id)
    )
    registry._test_declared_hello_reuse_snapshot = True


def _plan_reply_for_hello() -> str:
    return _plan_reply(
        "我会沿用已核对的方法组织这次工作。",
        _orchestrate(
            [_agent("hello_agent", {"name": "复用执行"})],
            analysis="按已经核对的方法完成同类任务",
            goal="完成同类工程任务并保留证据",
            workflow="单执行单元完成并交回工程师核对",
        ),
    )


def test_reuse_ref_normalizer_accepts_contract_semver_prerelease() -> None:
    ref = {
        "schema_version": "skill_reuse_ref.v1",
        "package_id": "skill_package_" + "a" * 24,
        "package_version": "0.1.0-candidate.1",
        "package_digest": "sha256:" + "b" * 64,
        "candidate_digest": "sha256:" + "c" * 64,
        "skill_digest": "sha256:" + "d" * 64,
        "skill_name": "受控方法",
        "matched_agent_id": "hello_agent",
        "review_state": "approved",
        "match_policy_version": "skill_reuse_match.v1",
        "match_basis_digest": "sha256:" + "e" * 64,
    }

    assert normalize_reuse_ref(ref) == ref


def _matched_ref(client, app, *, suffix: str) -> tuple[str, dict[str, Any]]:
    _install_declared_hello_reuse_snapshot(app)
    gateway = _CannedStub(_plan_reply_for_hello())
    app.state.conversation_service.model_gateway = gateway
    conversation_id = _open_conversation(client)
    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": f"请再次完成起落架控制逻辑核对；本次案例 {suffix}。"},
    )
    assert response.status_code == 200, response.text
    return conversation_id, response.json()["message"]["recommendation"]["skill_reuse"]


def _create_reused_task(
    client,
    *,
    conversation_id: str,
    reuse_ref: dict[str, Any],
    input_name: str = "复用执行",
    retry_of: str | None = None,
    input_file_ids: list[str] | None = None,
) -> dict[str, Any]:
    response = client.post(
        "/api/tasks/batch",
        json={
            "conversation_id": conversation_id,
            "items": [
                {
                    "agent_id": "hello_agent",
                    "name": "自动复用 Skill 的任务",
                    "inputs": {"name": input_name},
                    "input_file_ids": list(input_file_ids or []),
                    "skill_package_ref": reuse_ref,
                    **({"retry_of": retry_of} if retry_of is not None else {}),
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["tasks"][0]


def _execute(app, task_id: str) -> dict[str, Any]:
    conn = app.state.conn_factory()
    try:
        repos.set_task_status(conn, task_id, "validating")
    finally:
        conn.close()

    # These integration cases exercise a compliant deterministic workflow:
    # profile:none must explicitly return the exact runtime-provided receipt.
    real_loader = runtime_module._load_workflow_module

    def receipt_aware_loader(*args, **kwargs):
        module = real_loader(*args, **kwargs)

        class ReceiptAwareWorkflow:
            @staticmethod
            def run(context):
                result = module.run(context)
                if (
                    isinstance(result, dict)
                    and result.get("status") == "success"
                    and isinstance(context.get("reused_skill"), dict)
                ):
                    result = dict(result)
                    result["skill_reuse_application_receipt"] = context["reused_skill"][
                        "application_receipt"
                    ]
                return result

        return ReceiptAwareWorkflow

    with patch.object(runtime_module, "_load_workflow_module", receipt_aware_loader):
        return app.state.runtime.execute(task_id)


def _formation(client, package_id: str) -> dict[str, Any]:
    response = client.get(f"/api/skill-packages/{package_id}")
    assert response.status_code == 200, response.text
    return response.json()["formation_evidence"]


def _seed_failed_lineage_task(
    app,
    *,
    task_id: str,
    retry_of: str | None = None,
    owner_username: str = "test_engineer",
) -> str:
    conn = app.state.conn_factory()
    try:
        repos.create_task(
            conn,
            task_id=task_id,
            agent_id="hello_agent",
            agent_version="1.0.0",
            name="失败恢复血缘",
            created_by="测试工程师",
            created_by_username=owner_username,
            inputs={"name": task_id},
            retry_of=retry_of,
        )
        conn.execute(
            "UPDATE tasks SET status = 'failed', finished_at = updated_at WHERE id = ?",
            (task_id,),
        )
    finally:
        conn.close()
    return task_id


def test_batch_revalidates_reuse_ref_and_invalid_ref_is_atomic_zero_write(
    app_env,
) -> None:
    client, app = app_env
    _accept_and_approve_package(
        client,
        app,
        task_name="起落架控制逻辑核对",
    )
    conversation_id, reuse_ref = _matched_ref(client, app, suffix="A")
    forged = {**reuse_ref, "package_digest": "sha256:" + "f" * 64}
    conn = app.state.conn_factory()
    try:
        before_tasks = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    finally:
        conn.close()

    response = client.post(
        "/api/tasks/batch",
        json={
            "conversation_id": conversation_id,
            "items": [
                {
                    "agent_id": "hello_agent",
                    "inputs": {"name": "不应创建"},
                    "skill_package_ref": forged,
                }
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "skill_package_reuse_invalid"
    conn = app.state.conn_factory()
    try:
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == before_tasks
        assert (
            conn.execute("SELECT COUNT(*) FROM skill_reuse_bindings").fetchone()[0] == 0
        )
    finally:
        conn.close()


@pytest.mark.parametrize(
    "poison",
    ["extra_top_level", "package_state", "source_agent", "skill_digest", "markdown"],
)
def test_resolved_context_validator_rejects_non_exact_binding_inputs(
    app_env, poison: str
) -> None:
    client, app = app_env
    _accept_and_approve_package(
        client,
        app,
        task_name="起落架控制逻辑核对",
    )
    _conversation_id, reuse_ref = _matched_ref(client, app, suffix=f"resolved-{poison}")
    conn = app.state.conn_factory()
    try:
        ledger = app.state.skill_reuse_evidence
        resolved = ledger.resolve_for_task(
            conn,
            ref=reuse_ref,
            username="test_engineer",
            agent_id="hello_agent",
        )
        if poison == "extra_top_level":
            resolved["unexpected"] = True
        elif poison == "package_state":
            resolved["package"]["state"] = "pending_review"
        elif poison == "source_agent":
            resolved["package"]["source"]["agent_id"] = "other_agent"
        elif poison == "skill_digest":
            resolved["skill_revision"]["content_digest"] = "sha256:" + "0" * 64
        else:
            resolved["skill_markdown"] = ""

        with pytest.raises(SkillReuseInvalidError):
            ledger.validate_resolved_context(
                resolved,
                expected_ref=reuse_ref,
                agent_id="hello_agent",
            )
    finally:
        conn.close()


def test_reused_skill_is_bound_to_task_runtime_context_and_terminal_evidence(
    app_env, monkeypatch
) -> None:
    client, app = app_env
    package = _accept_and_approve_package(
        client,
        app,
        task_name="起落架控制逻辑核对",
    )
    conversation_id, reuse_ref = _matched_ref(client, app, suffix="执行绑定")
    task = _create_reused_task(
        client,
        conversation_id=conversation_id,
        reuse_ref=reuse_ref,
        input_name="起落架执行绑定实证",
    )
    assert task["metadata"]["skill_package_ref"] == reuse_ref
    binding_digest = task["metadata"]["skill_reuse_binding_digest"]
    assert binding_digest.startswith("sha256:")

    captured: dict[str, Any] = {}

    class Workflow:
        @staticmethod
        def run(context):
            captured.update(context)
            return {"status": "success", "outputs": []}

    monkeypatch.setattr(
        "backend.app.runtime.runtime._load_workflow_module",
        lambda *_args, **_kwargs: Workflow,
    )
    result = _execute(app, task["id"])

    assert result["status"] == "completed"
    reused = captured["reused_skill"]
    assert reused["package_ref"] == reuse_ref
    assert reused["skill_revision"]["name"] == "起落架控制逻辑核对：可复用方法"
    assert reused["skill_markdown"].startswith("---\nname:")

    events = client.get(f"/api/tasks/{task['id']}/events").json()
    validation = next(
        event for event in events if event["event_type"] == "validation_started"
    )
    terminal = next(
        event for event in events if event["event_type"] == "task_completed"
    )
    reuse_event = next(
        event
        for event in events
        if event["event_type"] == "agent_log"
        and event["payload"].get("workflow_event_type") == "skill_reuse_bound"
    )
    applied_event = next(
        event
        for event in events
        if event["event_type"] == "agent_log"
        and event["payload"].get("workflow_event_type") == "skill_reuse_applied"
    )
    application_digest = reused["application_receipt"]["skill_reuse_application_digest"]
    assert validation["payload"]["skill_reuse_binding_digest"] == binding_digest
    assert terminal["payload"]["skill_reuse_binding_digest"] == binding_digest
    assert terminal["payload"]["skill_reuse_application_digest"] == application_digest
    assert reuse_event["payload"] == {
        "workflow_event_type": "skill_reuse_bound",
        "skill_package_id": package["id"],
        "skill_package_digest": package["package_digest"],
        "skill_reuse_binding_digest": binding_digest,
        "skill_method_digest": reused["application_receipt"]["skill_method_digest"],
        "skill_reuse_application_digest": application_digest,
        "work_case_fingerprint": validation["payload"]["work_case_fingerprint"],
    }
    assert applied_event["payload"] == {
        "workflow_event_type": "skill_reuse_applied",
        "application_mode": "deterministic_receipt",
        "skill_package_id": package["id"],
        "skill_package_digest": package["package_digest"],
        "skill_reuse_binding_digest": binding_digest,
        "skill_method_digest": reused["application_receipt"]["skill_method_digest"],
        "skill_reuse_application_digest": application_digest,
        "work_case_fingerprint": validation["payload"]["work_case_fingerprint"],
    }

    formation = _formation(client, package["id"])
    assert formation["independent_work_case_count"] == 1
    assert formation["workflow_candidate"]["eligible"] is False
    assert formation["agent_candidate"]["eligible"] is False


def test_only_two_independent_completed_reuses_reach_repeat_threshold_without_forming_workflow_or_agent(
    app_env,
) -> None:
    client, app = app_env
    package = _accept_and_approve_package(
        client,
        app,
        task_name="起落架控制逻辑核对",
    )

    for suffix, input_name in (
        ("独立案例一", "左主起落架收放互锁核对"),
        ("独立案例二", "右主起落架应急放下核对"),
    ):
        conversation_id, reuse_ref = _matched_ref(client, app, suffix=suffix)
        task = _create_reused_task(
            client,
            conversation_id=conversation_id,
            reuse_ref=reuse_ref,
            input_name=input_name,
        )
        result = _execute(app, task["id"])
        assert result["status"] == "completed"

    formation = _formation(client, package["id"])
    assert formation["independent_work_case_count"] == 2
    assert formation["required_independent_work_cases"] == 2
    assert formation["workflow_candidate"] == {
        "state": "not_formed",
        "eligible": False,
        "reason": "requires_stable_multi_skill_composition_evidence",
    }
    assert formation["agent_candidate"] == {
        "state": "not_formed",
        "eligible": False,
        "reason": "requires_approved_workflow_revision",
    }


def test_same_execution_evidence_is_only_one_independent_work_case(app_env) -> None:
    client, app = app_env
    package = _accept_and_approve_package(
        client,
        app,
        task_name="起落架控制逻辑核对",
    )

    for suffix in ("不同工作段甲", "不同工作段乙"):
        conversation_id, reuse_ref = _matched_ref(client, app, suffix=suffix)
        task = _create_reused_task(
            client,
            conversation_id=conversation_id,
            reuse_ref=reuse_ref,
            input_name="完全相同的执行输入",
        )
        assert _execute(app, task["id"])["status"] == "completed"

    assert _formation(client, package["id"])["independent_work_case_count"] == 1


def test_identical_reuploads_and_duplicate_attachments_count_as_one_work_case(
    app_env,
) -> None:
    client, app = app_env
    package = _accept_and_approve_package(
        client,
        app,
        task_name="起落架控制逻辑核对",
    )
    payload = b"same-reviewed-engineering-input"
    uploaded_ids: list[str] = []
    for filename in ("case-a.bin", "renamed.bin", "duplicate.bin"):
        uploaded = client.post("/api/files/upload", files={"file": (filename, payload)})
        assert uploaded.status_code == 200, uploaded.text
        uploaded_ids.append(uploaded.json()["id"])

    for suffix, file_ids in (
        ("原始附件", [uploaded_ids[0]]),
        ("改名重传并重复挂载", [uploaded_ids[2], uploaded_ids[1]]),
    ):
        conversation_id, reuse_ref = _matched_ref(client, app, suffix=suffix)
        task = _create_reused_task(
            client,
            conversation_id=conversation_id,
            reuse_ref=reuse_ref,
            input_name="相同内容案例",
            input_file_ids=file_ids,
        )
        assert _execute(app, task["id"])["status"] == "completed"

    assert _formation(client, package["id"])["independent_work_case_count"] == 1


def test_task_metadata_tamper_is_not_repeat_evidence(app_env) -> None:
    client, app = app_env
    package = _accept_and_approve_package(
        client,
        app,
        task_name="起落架控制逻辑核对",
    )
    conversation_id, reuse_ref = _matched_ref(client, app, suffix="元数据篡改")
    task = _create_reused_task(
        client,
        conversation_id=conversation_id,
        reuse_ref=reuse_ref,
        input_name="元数据篡改前真实执行",
    )
    assert _execute(app, task["id"])["status"] == "completed"

    conn = app.state.conn_factory()
    try:
        row = conn.execute(
            "SELECT metadata_json FROM tasks WHERE id = ?", (task["id"],)
        ).fetchone()
        metadata = json.loads(row["metadata_json"])
        metadata["skill_package_ref"]["match_basis_digest"] = "sha256:" + "0" * 64
        conn.execute(
            "UPDATE tasks SET metadata_json = ? WHERE id = ?",
            (json.dumps(metadata, ensure_ascii=False), task["id"]),
        )
    finally:
        conn.close()

    assert _formation(client, package["id"])["independent_work_case_count"] == 0


def test_skill_reuse_binding_row_is_update_immutable(app_env) -> None:
    client, app = app_env
    _accept_and_approve_package(client, app, task_name="起落架控制逻辑核对")
    conversation_id, reuse_ref = _matched_ref(client, app, suffix="不可变 binding")
    task = _create_reused_task(
        client,
        conversation_id=conversation_id,
        reuse_ref=reuse_ref,
        input_name="不可变 binding 执行",
    )

    conn = app.state.conn_factory()
    try:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute(
                "UPDATE skill_reuse_bindings SET match_basis_digest = ? WHERE task_id = ?",
                ("sha256:" + "0" * 64, task["id"]),
            )
    finally:
        conn.close()


def test_recursive_retry_family_counts_once_even_with_distinct_inputs_and_segments(
    app_env,
) -> None:
    client, app = app_env
    package = _accept_and_approve_package(
        client,
        app,
        task_name="起落架控制逻辑核对",
    )
    root = _seed_failed_lineage_task(app, task_id="task_retry_family_root")
    child = _seed_failed_lineage_task(
        app,
        task_id="task_retry_family_child",
        retry_of=root,
    )
    grandchild = _seed_failed_lineage_task(
        app,
        task_id="task_retry_family_grandchild",
        retry_of=child,
    )

    for suffix, input_name, retry_of in (
        ("深层恢复案例甲", "襟翼通道恢复核对", child),
        ("深层恢复案例乙", "缝翼通道恢复核对", grandchild),
    ):
        conversation_id, reuse_ref = _matched_ref(client, app, suffix=suffix)
        task = _create_reused_task(
            client,
            conversation_id=conversation_id,
            reuse_ref=reuse_ref,
            input_name=input_name,
            retry_of=retry_of,
        )
        assert _execute(app, task["id"])["status"] == "completed"

    assert _formation(client, package["id"])["independent_work_case_count"] == 1


@pytest.mark.parametrize("lineage_fault", ["missing", "cycle", "cross_owner"])
def test_unverifiable_retry_lineage_is_skipped(app_env, lineage_fault: str) -> None:
    client, app = app_env
    package = _accept_and_approve_package(
        client,
        app,
        task_name="起落架控制逻辑核对",
    )
    root = _seed_failed_lineage_task(
        app,
        task_id=f"task_retry_{lineage_fault}_root",
        owner_username=(
            "other_engineer" if lineage_fault == "cross_owner" else "test_engineer"
        ),
    )
    conversation_id, reuse_ref = _matched_ref(client, app, suffix=lineage_fault)
    task = _create_reused_task(
        client,
        conversation_id=conversation_id,
        reuse_ref=reuse_ref,
        input_name=f"{lineage_fault} 血缘执行",
        retry_of=root,
    )
    assert _execute(app, task["id"])["status"] == "completed"

    conn = app.state.conn_factory()
    try:
        if lineage_fault == "missing":
            conn.execute(
                "UPDATE tasks SET retry_of = 'task_missing_retry_ancestor' WHERE id = ?",
                (task["id"],),
            )
        elif lineage_fault == "cycle":
            conn.execute(
                "UPDATE tasks SET retry_of = ? WHERE id = ?",
                (task["id"], root),
            )
    finally:
        conn.close()

    assert _formation(client, package["id"])["independent_work_case_count"] == 0


@pytest.mark.parametrize("event_fault", ["missing", "ambiguous", "wrong_order"])
def test_unverifiable_skill_reuse_event_chain_is_skipped(
    app_env, event_fault: str
) -> None:
    client, app = app_env
    package = _accept_and_approve_package(
        client,
        app,
        task_name="起落架控制逻辑核对",
    )
    conversation_id, reuse_ref = _matched_ref(client, app, suffix=event_fault)
    task = _create_reused_task(
        client,
        conversation_id=conversation_id,
        reuse_ref=reuse_ref,
        input_name=f"{event_fault} 事件链执行",
    )
    assert _execute(app, task["id"])["status"] == "completed"

    conn = app.state.conn_factory()
    try:
        rows = conn.execute(
            "SELECT id, event_type, payload_json FROM task_events WHERE task_id = ? ORDER BY id",
            (task["id"],),
        ).fetchall()
        bound = next(
            row
            for row in rows
            if row["event_type"] == "agent_log"
            and json.loads(row["payload_json"]).get("workflow_event_type")
            == "skill_reuse_bound"
        )
        validation = next(
            row for row in rows if row["event_type"] == "validation_started"
        )
        if event_fault == "missing":
            conn.execute("DELETE FROM task_events WHERE id = ?", (bound["id"],))
        elif event_fault == "ambiguous":
            repos.append_event(
                conn,
                task_id=task["id"],
                agent_id="hello_agent",
                event_type="agent_log",
                level="info",
                message="重复的 Skill 绑定事件",
                payload=json.loads(bound["payload_json"]),
            )
        else:
            # Swap only the local sequence ids so the otherwise exact binding
            # event appears before validation_started.
            conn.execute(
                "UPDATE task_events SET id = -1 WHERE id = ?", (validation["id"],)
            )
            conn.execute(
                "UPDATE task_events SET id = ? WHERE id = ?",
                (validation["id"], bound["id"]),
            )
            conn.execute("UPDATE task_events SET id = ? WHERE id = -1", (bound["id"],))
    finally:
        conn.close()

    assert _formation(client, package["id"])["independent_work_case_count"] == 0


@pytest.mark.parametrize("application_fault", ["missing", "ambiguous", "wrong_order"])
def test_unverifiable_skill_application_event_chain_is_skipped(
    app_env, application_fault: str
) -> None:
    client, app = app_env
    package = _accept_and_approve_package(
        client,
        app,
        task_name="起落架控制逻辑核对",
    )
    conversation_id, reuse_ref = _matched_ref(
        client, app, suffix=f"application-{application_fault}"
    )
    task = _create_reused_task(
        client,
        conversation_id=conversation_id,
        reuse_ref=reuse_ref,
        input_name=f"{application_fault} 应用事件链执行",
    )
    assert _execute(app, task["id"])["status"] == "completed"

    conn = app.state.conn_factory()
    try:
        rows = conn.execute(
            "SELECT id, event_type, payload_json FROM task_events "
            "WHERE task_id = ? ORDER BY id",
            (task["id"],),
        ).fetchall()
        bound = next(
            row
            for row in rows
            if row["event_type"] == "agent_log"
            and json.loads(row["payload_json"]).get("workflow_event_type")
            == "skill_reuse_bound"
        )
        applied = next(
            row
            for row in rows
            if row["event_type"] == "agent_log"
            and json.loads(row["payload_json"]).get("workflow_event_type")
            == "skill_reuse_applied"
        )
        if application_fault == "missing":
            conn.execute("DELETE FROM task_events WHERE id = ?", (applied["id"],))
        elif application_fault == "ambiguous":
            repos.append_event(
                conn,
                task_id=task["id"],
                agent_id="hello_agent",
                event_type="agent_log",
                level="info",
                message="重复的 Skill 应用事件",
                payload=json.loads(applied["payload_json"]),
            )
        else:
            conn.execute("UPDATE task_events SET id = -1 WHERE id = ?", (bound["id"],))
            conn.execute(
                "UPDATE task_events SET id = ? WHERE id = ?",
                (bound["id"], applied["id"]),
            )
            conn.execute(
                "UPDATE task_events SET id = ? WHERE id = -1", (applied["id"],)
            )
    finally:
        conn.close()

    assert _formation(client, package["id"])["independent_work_case_count"] == 0


@pytest.mark.parametrize("model_event_fault", ["missing", "wrong_digest", "embed"])
def test_model_application_requires_digest_bound_chat_or_vision_event(
    app_env, tmp_path, monkeypatch, model_event_fault: str
) -> None:
    client, app = app_env
    package = _accept_and_approve_package(
        client,
        app,
        task_name="起落架控制逻辑核对",
    )
    conversation_id, reuse_ref = _matched_ref(
        client, app, suffix=f"model-event-{model_event_fault}"
    )

    model_agents = tmp_path / "model-agents"
    model_package_dir = model_agents / "hello_agent"
    shutil.copytree(AGENTS_DIR / "hello_agent", model_package_dir)
    manifest_path = model_package_dir / "agent.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["model"]["profile"] = "reasoning"
    manifest["workflow"]["requires_human_review"] = True
    manifest_path.write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    model_snapshot = capture_agent_package(model_package_dir)
    registry = app.state.agent_registry
    original_snapshot = registry.package_snapshot
    monkeypatch.setattr(
        registry,
        "package_snapshot",
        lambda agent_id: (
            model_snapshot if agent_id == "hello_agent" else original_snapshot(agent_id)
        ),
    )

    class Gateway:
        @staticmethod
        def chat(*_args, **_kwargs):
            return {"choices": [{"message": {"content": "done"}}]}

    class Workflow:
        @staticmethod
        def run(context):
            context["model_gateway"].chat(
                "reasoning", [{"role": "user", "content": "执行核对"}]
            )
            return {"status": "success", "outputs": []}

    app.state.runtime.model_gateway = Gateway()
    monkeypatch.setattr(
        runtime_module, "_load_workflow_module", lambda *_args: Workflow
    )
    task = _create_reused_task(
        client,
        conversation_id=conversation_id,
        reuse_ref=reuse_ref,
        input_name=f"模型证据 {model_event_fault}",
    )
    assert _execute(app, task["id"])["status"] == "waiting_review"
    approved = client.post(
        f"/api/tasks/{task['id']}/review", json={"action": "approve"}
    )
    assert approved.status_code == 200, approved.text
    assert _formation(client, package["id"])["independent_work_case_count"] == 1

    conn = app.state.conn_factory()
    try:
        row = conn.execute(
            "SELECT id, payload_json FROM task_events "
            "WHERE task_id = ? AND event_type = 'model_call'",
            (task["id"],),
        ).fetchone()
        assert row is not None
        if model_event_fault == "missing":
            conn.execute("DELETE FROM task_events WHERE id = ?", (row["id"],))
        else:
            payload = json.loads(row["payload_json"])
            if model_event_fault == "wrong_digest":
                payload["skill_reuse_application_digest"] = "sha256:" + "0" * 64
            else:
                payload["kind"] = "embed"
                payload.pop("skill_reuse_application_digest", None)
            conn.execute(
                "UPDATE task_events SET payload_json = ? WHERE id = ?",
                (json.dumps(payload, ensure_ascii=False), row["id"]),
            )
    finally:
        conn.close()

    assert _formation(client, package["id"])["independent_work_case_count"] == 0
