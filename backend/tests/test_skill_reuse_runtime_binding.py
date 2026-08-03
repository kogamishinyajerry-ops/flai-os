from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from backend.app.config import AGENTS_DIR
from backend.app.core.canonical_digest import canonical_digest
from backend.app.core.errors import ReviewEvidenceUnavailableError
from backend.app.runtime.task_evidence import work_case_fingerprint
from backend.app.storage import repos
from backend.app.storage.db import get_conn, init_db
from backend.tests.test_runtime import _make_runtime


_BINDING_DIGEST = "sha256:" + "a" * 64
_APPLICATION_DIGEST = "sha256:" + "d" * 64
_PACKAGE_DIGEST = "sha256:" + "b" * 64
_PACKAGE_REF = {
    "package_id": "skill_package_1234567890abcdef12345678",
    "package_digest": _PACKAGE_DIGEST,
}


def _make_model_runtime(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    package_dir = agents_dir / "hello_agent"
    shutil.copytree(AGENTS_DIR / "hello_agent", package_dir)
    manifest_path = package_dir / "agent.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["model"]["profile"] = "reasoning"
    manifest["workflow"]["requires_human_review"] = True
    manifest_path.write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return _make_runtime(agents_dir, tmp_path)


def _make_declared_deterministic_reuse_runtime(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    package_dir = agents_dir / "hello_agent"
    shutil.copytree(AGENTS_DIR / "hello_agent", package_dir)
    manifest_path = package_dir / "agent.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert manifest["model"]["profile"] == "none"
    manifest["workflow"]["skill_reuse_application"] = "deterministic_receipt_v1"
    manifest_path.write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return _make_runtime(agents_dir, tmp_path)


def test_work_case_fingerprint_folds_ids_names_order_and_duplicate_bytes() -> None:
    def file_evidence(
        file_id: str, filename: str, sha256: str, *, size: int = 4
    ) -> dict[str, Any]:
        return {
            "file_id": file_id,
            "filename": filename,
            "missing": False,
            "task_id": None,
            "kind": "input",
            "sha256": sha256,
            "size_bytes": size,
            "classification": "internal",
        }

    same_a = file_evidence("file-a", "first.step", "1" * 64)
    same_b = file_evidence("file-b", "renamed.step", "1" * 64)
    other = file_evidence("file-c", "other.step", "2" * 64)

    def fingerprint(inputs, files):
        return work_case_fingerprint(
            task_inputs=inputs,
            input_file_evidence={"files": files},
            agent_id="hello_agent",
            package_id=_PACKAGE_REF["package_id"],
            package_digest=_PACKAGE_DIGEST,
        )

    baseline = fingerprint({"name": "case"}, [same_a, other])
    assert fingerprint({"name": "case"}, [other, same_b, same_a, same_b]) == baseline
    assert fingerprint({"name": "case"}, [same_a]) != baseline
    assert fingerprint({"name": "different"}, [same_a, other]) != baseline
    assert fingerprint(
        {"name": "case"},
        [file_evidence("file-d", "different.step", "3" * 64)],
    ) != fingerprint({"name": "case"}, [same_a])


def _create_validating_reuse_task(
    db_path: Path,
    *,
    task_id: str = "reuse_runtime_task",
    inputs: dict[str, Any] | None = None,
) -> str:
    conn = get_conn(db_path)
    try:
        repos.create_conversation(
            conn,
            conversation_id="conversation_reuse_runtime",
            agent_id="hello_agent",
            created_by="工程师",
            created_by_username="engineer",
        )
        repos.create_task(
            conn,
            task_id=task_id,
            agent_id="hello_agent",
            agent_version="0.1.0",
            name="复用运行时证据测试",
            created_by="工程师",
            created_by_username="engineer",
            conversation_id="conversation_reuse_runtime",
            inputs=inputs if inputs is not None else {"name": "复用执行"},
            input_file_ids=[],
            metadata={"skill_package_ref": dict(_PACKAGE_REF)},
        )
        repos.set_task_status(conn, task_id, "queued")
        repos.set_task_status(conn, task_id, "validating")
        return task_id
    finally:
        conn.close()


def test_runtime_reuse_gate_precedes_input_validation_and_fails_closed_without_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, db_path = _make_runtime(AGENTS_DIR, tmp_path)
    task_id = _create_validating_reuse_task(db_path, inputs={})

    monkeypatch.setattr(
        "backend.app.runtime.runtime._load_workflow_module",
        lambda *_args, **_kwargs: pytest.fail("复用证据失败后不得加载 workflow"),
    )
    result = runtime.execute(task_id)

    assert result["status"] == "failed"
    assert "未装配 Skill 复用证据服务" in result["task"]["error_message"]
    conn = get_conn(db_path)
    try:
        events = repos.list_events(conn, task_id)
        assert [event["event_type"] for event in events] == ["task_failed"]
        assert repos.list_tool_runs(conn, task_id) == []
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM files WHERE task_id = ?", (task_id,)
            ).fetchone()[0]
            == 0
        )
    finally:
        conn.close()


def test_runtime_reuse_verification_failure_never_loads_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, db_path = _make_runtime(AGENTS_DIR, tmp_path)
    task_id = _create_validating_reuse_task(db_path)

    class BrokenEvidence:
        @staticmethod
        def verify_runtime(_conn, *, task):
            assert task["id"] == task_id
            raise RuntimeError("package bytes tampered")

    runtime.skill_reuse_evidence = BrokenEvidence()
    monkeypatch.setattr(
        "backend.app.runtime.runtime._load_workflow_module",
        lambda *_args, **_kwargs: pytest.fail("复用包篡改后不得加载 workflow"),
    )
    result = runtime.execute(task_id)

    assert result["status"] == "failed"
    assert "package bytes tampered" in result["task"]["error_message"]
    conn = get_conn(db_path)
    try:
        assert [event["event_type"] for event in repos.list_events(conn, task_id)] == [
            "task_failed"
        ]
        assert repos.list_tool_runs(conn, task_id) == []
    finally:
        conn.close()


def test_profile_none_exact_receipt_is_applied_once_and_bound_to_terminal_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, db_path = _make_declared_deterministic_reuse_runtime(tmp_path)
    task_id = _create_validating_reuse_task(db_path)
    order: list[str] = []
    captured: dict[str, Any] = {}

    class Evidence:
        @staticmethod
        def verify_runtime(_conn, *, task):
            order.append("verify")
            assert task["id"] == task_id
            return {
                "package_ref": dict(_PACKAGE_REF),
                "binding_digest": _BINDING_DIGEST,
                "skill_revision": {"name": "起落架核对方法"},
                "skill_markdown": "---\nname: landing-gear-check\n---\n",
            }

    class Workflow:
        @staticmethod
        def run(context):
            order.append("workflow")
            captured.update(context)
            return {
                "status": "success",
                "outputs": [],
                "skill_reuse_application_receipt": context["reused_skill"][
                    "application_receipt"
                ],
            }

    runtime.skill_reuse_evidence = Evidence()
    monkeypatch.setattr(
        "backend.app.runtime.runtime._load_workflow_module",
        lambda *_args, **_kwargs: Workflow,
    )
    result = runtime.execute(task_id)

    assert result["status"] == "completed"
    assert order == ["verify", "workflow"]
    assert captured["reused_skill"] == {
        "package_ref": _PACKAGE_REF,
        "skill_revision": {"name": "起落架核对方法"},
        "skill_markdown": "---\nname: landing-gear-check\n---\n",
        "application_receipt": captured["reused_skill"]["application_receipt"],
    }
    conn = get_conn(db_path)
    try:
        events = repos.list_events(conn, task_id)
        validation = next(
            event for event in events if event["event_type"] == "validation_started"
        )
        reuse_bound = next(
            event
            for event in events
            if event["event_type"] == "agent_log"
            and event["payload"].get("workflow_event_type") == "skill_reuse_bound"
        )
        terminal = next(
            event for event in events if event["event_type"] == "task_completed"
        )
        applied = [
            event
            for event in events
            if event["event_type"] == "agent_log"
            and event["payload"].get("workflow_event_type") == "skill_reuse_applied"
        ]
        assert len(applied) == 1
        application_digest = captured["reused_skill"]["application_receipt"][
            "skill_reuse_application_digest"
        ]
        assert validation["payload"]["skill_reuse_binding_digest"] == _BINDING_DIGEST
        assert terminal["payload"]["skill_reuse_binding_digest"] == _BINDING_DIGEST
        assert (
            terminal["payload"]["skill_reuse_application_digest"] == application_digest
        )
        assert (
            applied[0]["payload"]["skill_reuse_application_digest"]
            == application_digest
        )
        assert reuse_bound["payload"] == {
            "workflow_event_type": "skill_reuse_bound",
            "skill_package_id": _PACKAGE_REF["package_id"],
            "skill_package_digest": _PACKAGE_DIGEST,
            "skill_reuse_binding_digest": _BINDING_DIGEST,
            "skill_method_digest": captured["reused_skill"]["application_receipt"][
                "skill_method_digest"
            ],
            "skill_reuse_application_digest": application_digest,
            "work_case_fingerprint": validation["payload"]["work_case_fingerprint"],
        }
        evidence_basis = {
            "package_snapshot_digest": validation["payload"]["package_snapshot_digest"],
            "task_inputs_digest": validation["payload"]["task_inputs_digest"],
            "input_file_ids": validation["payload"]["input_file_ids"],
            "input_files_digest": validation["payload"]["input_files_digest"],
        }
        assert validation["payload"]["execution_evidence_digest"] == canonical_digest(
            evidence_basis
        )
    finally:
        conn.close()


def test_profile_none_reuse_without_exact_application_receipt_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, db_path = _make_declared_deterministic_reuse_runtime(tmp_path)
    task_id = _create_validating_reuse_task(
        db_path, task_id="reuse_missing_application_receipt"
    )

    class Evidence:
        @staticmethod
        def verify_runtime(_conn, *, task):
            assert task["id"] == task_id
            return {
                "package_ref": dict(_PACKAGE_REF),
                "binding_digest": _BINDING_DIGEST,
                "skill_revision": {"name": "起落架核对方法"},
                "skill_markdown": "---\nname: landing-gear-check\n---\n",
            }

    class Workflow:
        @staticmethod
        def run(context):
            assert "application_receipt" in context["reused_skill"]
            return {"status": "success", "outputs": []}

    runtime.skill_reuse_evidence = Evidence()
    monkeypatch.setattr(
        "backend.app.runtime.runtime._load_workflow_module",
        lambda *_args, **_kwargs: Workflow,
    )

    result = runtime.execute(task_id)

    assert result["status"] == "failed"
    assert "Skill 复用方法未形成精确应用回执" in result["task"]["error_message"]
    conn = get_conn(db_path)
    try:
        events = repos.list_events(conn, task_id)
        assert not any(
            event["event_type"] == "agent_log"
            and event["payload"].get("workflow_event_type") == "skill_reuse_applied"
            for event in events
        )
        assert not any(
            event["event_type"] in {"task_completed", "review_requested"}
            for event in events
        )
    finally:
        conn.close()


def test_profile_none_without_snapshot_capability_never_loads_workflow_for_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, db_path = _make_runtime(AGENTS_DIR, tmp_path)
    task_id = _create_validating_reuse_task(
        db_path, task_id="reuse_undeclared_deterministic_capability"
    )

    class Evidence:
        @staticmethod
        def verify_runtime(_conn, *, task):
            assert task["id"] == task_id
            return {
                "package_ref": dict(_PACKAGE_REF),
                "binding_digest": _BINDING_DIGEST,
                "skill_revision": {"name": "起落架核对方法"},
                "skill_markdown": "---\nname: landing-gear-check\n---\n",
            }

    runtime.skill_reuse_evidence = Evidence()
    monkeypatch.setattr(
        "backend.app.runtime.runtime._load_workflow_module",
        lambda *_args, **_kwargs: pytest.fail(
            "未声明 deterministic receipt 能力不得加载 workflow"
        ),
    )

    result = runtime.execute(task_id)

    assert result["status"] == "failed"
    assert "未声明可验证的 Skill 应用能力" in result["task"]["error_message"]
    conn = get_conn(db_path)
    try:
        assert [event["event_type"] for event in repos.list_events(conn, task_id)] == [
            "task_failed"
        ]
    finally:
        conn.close()


@pytest.mark.parametrize("invocation_kind", ["chat", "vision"])
def test_model_reuse_is_applied_only_through_bounded_chat_or_vision_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invocation_kind: str,
) -> None:
    runtime, db_path = _make_model_runtime(tmp_path)
    task_id = _create_validating_reuse_task(
        db_path, task_id=f"reuse_model_{invocation_kind}"
    )
    captured: dict[str, Any] = {}

    class Evidence:
        @staticmethod
        def verify_runtime(_conn, *, task):
            assert task["id"] == task_id
            return {
                "package_ref": dict(_PACKAGE_REF),
                "binding_digest": _BINDING_DIGEST,
                "skill_revision": {"name": "起落架核对方法"},
                "skill_markdown": "---\nname: landing-gear-check\n---\n按复核步骤执行。",
            }

    class Gateway:
        @staticmethod
        def chat(profile, messages, **kwargs):
            captured["profile"] = profile
            captured["messages"] = messages
            captured["kwargs"] = kwargs
            return {"choices": [{"message": {"content": "done"}}]}

        @staticmethod
        def vision(profile, image_path, prompt, **kwargs):
            captured["profile"] = profile
            captured["image_path"] = image_path
            captured["prompt"] = prompt
            captured["kwargs"] = kwargs
            return {"choices": [{"message": {"content": "done"}}]}

        @staticmethod
        def embed(*_args, **_kwargs):
            raise AssertionError("本用例不得调用 embedding")

    class Workflow:
        @staticmethod
        def run(context):
            if invocation_kind == "chat":
                context["model_gateway"].chat(
                    "reasoning", [{"role": "user", "content": "执行核对"}]
                )
            else:
                context["model_gateway"].vision(
                    "reasoning", "/tmp/input.png", "检查图像"
                )
            return {"status": "success", "outputs": []}

    runtime.skill_reuse_evidence = Evidence()
    runtime.model_gateway = Gateway()
    monkeypatch.setattr(
        "backend.app.runtime.runtime._load_workflow_module",
        lambda *_args, **_kwargs: Workflow,
    )

    result = runtime.execute(task_id)

    assert result["status"] == "waiting_review"
    if invocation_kind == "chat":
        assert captured["messages"][0]["role"] == "system"
        envelope = captured["messages"][0]["content"]
        assert captured["messages"][1] == {
            "role": "user",
            "content": "执行核对",
        }
    else:
        envelope = captured["prompt"]
        assert envelope.endswith("<task_prompt>\n检查图像\n</task_prompt>")
    assert "<flai_skill_method_data>" in envelope
    assert "按复核步骤执行。" in envelope
    assert captured["kwargs"]["task_id"] == task_id
    assert captured["kwargs"]["agent_id"] == "hello_agent"

    conn = get_conn(db_path)
    try:
        events = repos.list_events(conn, task_id)
        applied = [
            event
            for event in events
            if event["event_type"] == "agent_log"
            and event["payload"].get("workflow_event_type") == "skill_reuse_applied"
        ]
        assert len(applied) == 1
        model_call = next(
            event for event in events if event["event_type"] == "model_call"
        )
        assert model_call["payload"]["kind"] == invocation_kind
        assert applied[0]["payload"]["model_invocation_kinds"] == [invocation_kind]
        assert (
            model_call["payload"]["skill_reuse_application_digest"]
            == applied[0]["payload"]["skill_reuse_application_digest"]
        )
        requested = next(
            event for event in events if event["event_type"] == "review_requested"
        )
        assert (
            requested["payload"]["skill_reuse_application_digest"]
            == applied[0]["payload"]["skill_reuse_application_digest"]
        )
    finally:
        conn.close()


def test_embedding_only_does_not_apply_reused_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, db_path = _make_model_runtime(tmp_path)
    task_id = _create_validating_reuse_task(db_path, task_id="reuse_embedding_only")

    class Evidence:
        @staticmethod
        def verify_runtime(_conn, *, task):
            return {
                "package_ref": dict(_PACKAGE_REF),
                "binding_digest": _BINDING_DIGEST,
                "skill_revision": {"name": "起落架核对方法"},
                "skill_markdown": "---\nname: landing-gear-check\n---\n",
            }

    class Gateway:
        @staticmethod
        def embed(*_args, **_kwargs):
            return {"data": [{"embedding": [0.1]}]}

    class Workflow:
        @staticmethod
        def run(context):
            context["model_gateway"].embed("reasoning", "仅做向量化")
            return {"status": "success", "outputs": []}

    runtime.skill_reuse_evidence = Evidence()
    runtime.model_gateway = Gateway()
    monkeypatch.setattr(
        "backend.app.runtime.runtime._load_workflow_module",
        lambda *_args, **_kwargs: Workflow,
    )

    result = runtime.execute(task_id)

    assert result["status"] == "failed"
    assert "未经过成功的 chat/vision 模型调用" in result["task"]["error_message"]
    conn = get_conn(db_path)
    try:
        events = repos.list_events(conn, task_id)
        assert not any(
            event["event_type"] == "agent_log"
            and event["payload"].get("workflow_event_type") == "skill_reuse_applied"
            for event in events
        )
        embed_event = next(
            event for event in events if event["event_type"] == "model_call"
        )
        assert embed_event["payload"]["kind"] == "embed"
        assert "skill_reuse_application_digest" not in embed_event["payload"]
    finally:
        conn.close()


def _create_waiting_review_task(
    tmp_path: Path,
    *,
    validation_reuse: object = None,
    request_reuse: object = None,
    include_validation_reuse: bool = True,
    include_request_reuse: bool = True,
    validation_application: object = None,
    request_application: object = None,
    include_validation_application: bool = True,
    include_request_application: bool = True,
) -> tuple[Any, str]:
    db_path = tmp_path / "review.db"
    init_db(db_path)
    conn = get_conn(db_path)
    task_id = "reuse_review_task"
    repos.create_task(
        conn,
        task_id=task_id,
        agent_id="hello_agent",
        agent_version="0.1.0",
        name="复用人签证据测试",
        created_by="工程师",
        created_by_username="engineer",
        inputs={"name": "复用人签"},
        input_file_ids=[],
        metadata={},
    )
    for status in ("queued", "validating", "running"):
        repos.set_task_status(conn, task_id, status)
    evidence_basis = {
        "package_snapshot_digest": "1" * 64,
        "task_inputs_digest": "sha256:" + "2" * 64,
        "input_file_ids": [],
        "input_files_digest": "sha256:" + "3" * 64,
    }
    execution_digest = canonical_digest(evidence_basis)
    validation_payload = {
        **evidence_basis,
        "execution_evidence_digest": execution_digest,
    }
    if include_validation_reuse is True:
        validation_payload["skill_reuse_binding_digest"] = validation_reuse
    if include_validation_application is True:
        validation_payload["skill_reuse_application_digest"] = validation_application
    repos.append_event(
        conn,
        task_id=task_id,
        agent_id="hello_agent",
        event_type="validation_started",
        level="info",
        message="开始校验输入",
        payload=validation_payload,
    )
    if isinstance(validation_reuse, str) and isinstance(validation_application, str):
        repos.append_event(
            conn,
            task_id=task_id,
            agent_id="hello_agent",
            event_type="agent_log",
            level="info",
            message="已实证应用复用 Skill Package",
            payload={
                "workflow_event_type": "skill_reuse_applied",
                "skill_reuse_binding_digest": validation_reuse,
                "skill_reuse_application_digest": validation_application,
            },
        )
    repos.set_task_status(conn, task_id, "waiting_review")
    request_payload = {"execution_evidence_digest": execution_digest}
    if include_request_reuse is True:
        request_payload["skill_reuse_binding_digest"] = request_reuse
    if include_request_application is True:
        request_payload["skill_reuse_application_digest"] = request_application
    repos.append_event(
        conn,
        task_id=task_id,
        agent_id="hello_agent",
        event_type="review_requested",
        level="info",
        message="任务需要人工审核放行",
        payload=request_payload,
    )
    return conn, task_id


def test_review_approval_copies_matching_reuse_binding_digest(tmp_path: Path) -> None:
    conn, task_id = _create_waiting_review_task(
        tmp_path,
        validation_reuse=_BINDING_DIGEST,
        request_reuse=_BINDING_DIGEST,
        validation_application=_APPLICATION_DIGEST,
        request_application=_APPLICATION_DIGEST,
    )
    try:
        task, _sample_rows = repos.apply_human_review(
            conn,
            task_id,
            action="approve",
            reviewer="工程师",
            comment=None,
        )
        assert task["status"] == "completed"
        approved = next(
            event
            for event in repos.list_events(conn, task_id)
            if event["event_type"] == "review_approved"
        )
        assert approved["payload"]["skill_reuse_binding_digest"] == _BINDING_DIGEST
        assert (
            approved["payload"]["skill_reuse_application_digest"] == _APPLICATION_DIGEST
        )
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("validation_reuse", "request_reuse", "include_validation", "include_request"),
    [
        (_BINDING_DIGEST, None, True, False),
        (_BINDING_DIGEST, "sha256:" + "c" * 64, True, True),
        ("not-a-digest", "not-a-digest", True, True),
    ],
)
def test_review_approval_rejects_invalid_reuse_chain_but_human_rejection_remains_available(
    tmp_path: Path,
    validation_reuse: object,
    request_reuse: object,
    include_validation: bool,
    include_request: bool,
) -> None:
    conn, task_id = _create_waiting_review_task(
        tmp_path,
        validation_reuse=validation_reuse,
        request_reuse=request_reuse,
        include_validation_reuse=include_validation,
        include_request_reuse=include_request,
        validation_application=_APPLICATION_DIGEST,
        request_application=_APPLICATION_DIGEST,
    )
    try:
        with pytest.raises(ReviewEvidenceUnavailableError, match="Skill 复用证据"):
            repos.apply_human_review(
                conn,
                task_id,
                action="approve",
                reviewer="工程师",
                comment=None,
            )
        assert repos.get_task(conn, task_id)["status"] == "waiting_review"

        rejected_task, _sample_rows = repos.apply_human_review(
            conn,
            task_id,
            action="reject",
            reviewer="工程师",
            comment="复用证据不可验证",
        )
        assert rejected_task["status"] == "failed"
        rejected = next(
            event
            for event in repos.list_events(conn, task_id)
            if event["event_type"] == "review_rejected"
        )
        assert rejected["payload"]["execution_evidence_status"] == "unverified"
        assert "skill_reuse_binding_digest" not in rejected["payload"]
    finally:
        conn.close()
