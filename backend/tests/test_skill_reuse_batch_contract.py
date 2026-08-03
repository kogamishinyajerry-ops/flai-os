from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.api.tasks import BatchTaskItem, _batch_request_fingerprint
from backend.app.storage import repos
from backend.tests.test_m6_guide_conversation import _open_conversation


def _reuse_ref(**overrides: object) -> dict[str, object]:
    ref: dict[str, object] = {
        "schema_version": "skill_reuse_ref.v1",
        "package_id": "skill_package_" + "a" * 24,
        "package_version": "0.1.0",
        "package_digest": "sha256:" + "b" * 64,
        "candidate_digest": "sha256:" + "c" * 64,
        "skill_digest": "sha256:" + "d" * 64,
        "skill_name": "起落架控制逻辑核对：可复用方法",
        "matched_agent_id": "hello_agent",
        "review_state": "approved",
        "match_policy_version": "skill_reuse_match.v1",
        "match_basis_digest": "sha256:" + "e" * 64,
    }
    ref.update(overrides)
    return ref


def _resolved_reuse(ref: dict[str, object]) -> dict[str, object]:
    return {
        "ref": dict(ref),
        "package": {
            "schema_version": "skill_package_revision.v1",
            "id": ref["package_id"],
            "name": "起落架控制逻辑核对 Skill Package",
            "version": ref["package_version"],
            "package_digest": ref["package_digest"],
            "state": "approved",
            "source": {
                "candidate_id": "asset_candidate_" + "1" * 24,
                "candidate_digest": ref["candidate_digest"],
                "bundle_digest": "sha256:" + "1" * 64,
                "skill_digest": ref["skill_digest"],
                "acceptance_event_digest": "sha256:" + "2" * 64,
                "task_id": "task_source",
                "agent_id": "hello_agent",
                "initiated_by_username": "test_engineer",
            },
            "files": [],
            "storage_relpath": "skill-packages/quarantine/example",
            "review": {"action": "approve"},
            "reuse_eligible": True,
            "isolation": {},
            "formation_evidence": {},
            "created_at": "2026-08-02T00:00:00+00:00",
            "updated_at": "2026-08-02T00:00:00+00:00",
        },
        "skill_revision": {
            "schema_version": "skill_draft.v1",
            "status": "draft",
            "operationalizes_task_pattern_digest": "sha256:" + "3" * 64,
            "name": ref["skill_name"],
            "description": "复用方法",
            "when_to_use": ["同类任务"],
            "when_not_to_use": ["边界不明"],
            "inputs": ["任务材料"],
            "outputs": ["核对结果"],
            "instructions": ["执行核对"],
            "verification": ["核验证据"],
            "human_boundaries": ["人是唯一签发者"],
            "suggested_id": "landing_gear_check",
            "content_digest": ref["skill_digest"],
        },
        "skill_markdown": "---\nname: landing-gear-check\n---\n执行核对。",
    }


def _persist_reuse_recommendation(
    app,
    conversation_id: str,
    ref: dict[str, object],
    *,
    agents: list[dict[str, object]] | None = None,
) -> None:
    """Persist the trusted Guide plan that the batch must reconcile exactly."""
    conn = app.state.conn_factory()
    try:
        repos.set_conversation_recommendation(
            conn,
            conversation_id,
            {
                "decision": "orchestrate",
                "analysis": "按已审核方法执行",
                "goal": "完成工程任务",
                "workflow": "单任务执行并核对证据",
                "agents": agents
                or [
                    {
                        "agent_id": "hello_agent",
                        "role": "执行",
                        "rationale": "唯一匹配",
                        "prefilled_inputs": {"name": "受控复用"},
                    }
                ],
                "skill_reuse": ref,
            },
        )
    finally:
        conn.close()


@pytest.mark.parametrize(
    "override",
    [
        {"schema_version": 1},
        {"package_id": "skill_package_not-a-digest"},
        {"package_version": "01.0.0"},
        {"package_digest": "b" * 64},
        {"candidate_digest": "sha256:" + "G" * 64},
        {"skill_digest": "sha256:" + "d" * 63},
        {"skill_name": "   "},
        {"matched_agent_id": "Hello-Agent"},
        {"review_state": "pending_review"},
        {"match_policy_version": "skill_reuse_match.v2"},
        {"match_basis_digest": "sha256:" + "e" * 65},
        {"unexpected": "field"},
    ],
)
def test_batch_skill_package_ref_rejects_noncanonical_or_extra_fields(
    override: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        BatchTaskItem(
            agent_id="hello_agent",
            skill_package_ref=_reuse_ref(**override),
        )


def test_batch_operation_fingerprint_binds_the_implicit_skill_ref() -> None:
    without_ref = BatchTaskItem(agent_id="hello_agent")
    with_ref = BatchTaskItem(
        agent_id="hello_agent",
        skill_package_ref=_reuse_ref(),
    )
    changed_match_basis = BatchTaskItem(
        agent_id="hello_agent",
        skill_package_ref=_reuse_ref(match_basis_digest="sha256:" + "f" * 64),
    )

    def fingerprint(item: BatchTaskItem) -> str:
        return _batch_request_fingerprint(
            items=[item],
            conversation_id="conv_example",
            pinned_versions=None,
            pinned_package_digests=None,
        )

    assert fingerprint(with_ref) != fingerprint(without_ref)
    assert fingerprint(with_ref) != fingerprint(changed_match_basis)


def test_batch_reuse_ref_fails_closed_when_evidence_service_is_unavailable(
    app_env, monkeypatch
) -> None:
    client, app = app_env
    conversation_id = _open_conversation(client)
    _persist_reuse_recommendation(app, conversation_id, _reuse_ref())
    monkeypatch.setattr(app.state, "skill_reuse_evidence", None, raising=False)
    conn = app.state.conn_factory()
    try:
        before = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    finally:
        conn.close()

    response = client.post(
        "/api/tasks/batch",
        json={
            "conversation_id": conversation_id,
            "items": [
                {
                    "agent_id": "hello_agent",
                    "inputs": {"name": "不可落库"},
                    "skill_package_ref": _reuse_ref(),
                }
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "skill_package_reuse_invalid"
    conn = app.state.conn_factory()
    try:
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == before
    finally:
        conn.close()


def test_batch_reuse_ref_requires_a_main_conversation(app_env, monkeypatch) -> None:
    client, app = app_env

    class MustNotResolve:
        @staticmethod
        def resolve_for_task(*_args, **_kwargs):
            raise AssertionError("无主对话时不应查询包")

    monkeypatch.setattr(
        app.state, "skill_reuse_evidence", MustNotResolve(), raising=False
    )
    conn = app.state.conn_factory()
    try:
        before = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    finally:
        conn.close()

    response = client.post(
        "/api/tasks/batch",
        json={
            "items": [
                {
                    "agent_id": "hello_agent",
                    "inputs": {"name": "不可落库"},
                    "skill_package_ref": _reuse_ref(),
                }
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "skill_package_reuse_invalid"
    conn = app.state.conn_factory()
    try:
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == before
    finally:
        conn.close()


def test_batch_persists_revalidated_ref_and_inserts_binding_after_task(
    app_env, monkeypatch
) -> None:
    client, app = app_env
    conversation_id = _open_conversation(client)
    ref = _reuse_ref()
    _persist_reuse_recommendation(app, conversation_id, ref)

    class EvidenceStub:
        inserted: list[dict[str, object]] = []

        @staticmethod
        def resolve_for_task(
            _conn, *, ref, username: str, agent_id: str
        ) -> dict[str, object]:
            assert username == "test_engineer"
            assert agent_id == "hello_agent"
            return _resolved_reuse(ref)

        @staticmethod
        def build_binding(
            *,
            task_id: str,
            conversation_id: str,
            username: str,
            agent_id: str,
            resolved,
        ) -> dict[str, object]:
            return {
                "task_id": task_id,
                "conversation_id": conversation_id,
                "username": username,
                "agent_id": agent_id,
                "ref": resolved["ref"],
                "binding_digest": "sha256:" + "9" * 64,
            }

        def insert_binding(self, conn, record) -> None:
            # FK-safe ordering is part of the seam: task row must already exist,
            # while the enclosing batch transaction is still open.
            assert conn.execute(
                "SELECT 1 FROM tasks WHERE id = ?", (record["task_id"],)
            ).fetchone()
            self.inserted.append(dict(record))

    evidence = EvidenceStub()
    monkeypatch.setattr(app.state, "skill_reuse_evidence", evidence, raising=False)
    monkeypatch.setattr(
        "backend.app.api.tasks.skill_reuse_application_mode",
        lambda _agent: "deterministic_receipt",
    )

    response = client.post(
        "/api/tasks/batch",
        json={
            "conversation_id": conversation_id,
            "items": [
                {
                    "agent_id": "hello_agent",
                    "inputs": {"name": "受控复用"},
                    "skill_package_ref": ref,
                }
            ],
        },
    )

    assert response.status_code == 200, response.text
    task = response.json()["tasks"][0]
    assert task["metadata"]["skill_package_ref"] == ref
    assert task["metadata"]["skill_reuse_binding_digest"] == "sha256:" + "9" * 64
    assert evidence.inserted[0]["task_id"] == task["id"]


def test_batch_rejects_profile_none_without_declared_reuse_capability_before_task_write(
    app_env, monkeypatch
) -> None:
    client, app = app_env
    conversation_id = _open_conversation(client)
    ref = _reuse_ref()
    _persist_reuse_recommendation(app, conversation_id, ref)

    class EvidenceStub:
        inserted = False

        @staticmethod
        def resolve_for_task(_conn, *, ref, username: str, agent_id: str):
            assert username == "test_engineer"
            assert agent_id == "hello_agent"
            return _resolved_reuse(ref)

        @staticmethod
        def build_binding(*, task_id, conversation_id, username, agent_id, resolved):
            return {
                "task_id": task_id,
                "conversation_id": conversation_id,
                "username": username,
                "agent_id": agent_id,
                "ref": resolved["ref"],
                "binding_digest": "sha256:" + "9" * 64,
            }

        def insert_binding(self, _conn, _record) -> None:
            self.inserted = True

    evidence = EvidenceStub()
    monkeypatch.setattr(app.state, "skill_reuse_evidence", evidence, raising=False)
    conn = app.state.conn_factory()
    try:
        before = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    finally:
        conn.close()

    response = client.post(
        "/api/tasks/batch",
        json={
            "conversation_id": conversation_id,
            "items": [
                {
                    "agent_id": "hello_agent",
                    "inputs": {"name": "不得创建"},
                    "skill_package_ref": ref,
                }
            ],
        },
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "skill_package_reuse_incompatible"
    assert evidence.inserted is False
    conn = app.state.conn_factory()
    try:
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == before
    finally:
        conn.close()


def test_batch_reuse_ref_must_exactly_match_current_persisted_recommendation(
    app_env, monkeypatch
) -> None:
    client, app = app_env
    conversation_id = _open_conversation(client)
    trusted_ref = _reuse_ref()
    _persist_reuse_recommendation(app, conversation_id, trusted_ref)

    class MustNotResolve:
        called = False

        def resolve_for_task(self, *_args, **_kwargs):
            self.called = True
            raise AssertionError("伪造 work-segment basis 必须在包解析前被拒绝")

    evidence = MustNotResolve()
    monkeypatch.setattr(app.state, "skill_reuse_evidence", evidence, raising=False)
    conn = app.state.conn_factory()
    try:
        before = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    finally:
        conn.close()

    response = client.post(
        "/api/tasks/batch",
        json={
            "conversation_id": conversation_id,
            "items": [
                {
                    "agent_id": "hello_agent",
                    "inputs": {"name": "不可落库"},
                    "skill_package_ref": _reuse_ref(
                        match_basis_digest="sha256:" + "f" * 64
                    ),
                }
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "skill_package_reuse_invalid"
    assert evidence.called is False
    conn = app.state.conn_factory()
    try:
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == before
    finally:
        conn.close()


def test_batch_cannot_silently_omit_persisted_skill_reuse_ref(app_env) -> None:
    client, app = app_env
    conversation_id = _open_conversation(client)
    _persist_reuse_recommendation(app, conversation_id, _reuse_ref())
    conn = app.state.conn_factory()
    try:
        before = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    finally:
        conn.close()

    response = client.post(
        "/api/tasks/batch",
        json={
            "conversation_id": conversation_id,
            "items": [
                {
                    "agent_id": "hello_agent",
                    "inputs": {"name": "旧客户端静默漏掉复用引用"},
                }
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "skill_package_reuse_invalid"
    conn = app.state.conn_factory()
    try:
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == before
    finally:
        conn.close()


@pytest.mark.parametrize("duplicate_surface", ["plan", "batch"])
def test_batch_reuse_requires_one_matched_agent_in_plan_and_one_bound_item(
    app_env, monkeypatch, duplicate_surface: str
) -> None:
    client, app = app_env
    conversation_id = _open_conversation(client)
    ref = _reuse_ref()
    planned_agents = None
    items = [
        {
            "agent_id": "hello_agent",
            "inputs": {"name": "第一项"},
            "skill_package_ref": ref,
        }
    ]
    if duplicate_surface == "plan":
        planned_agents = [
            {"agent_id": "hello_agent"},
            {"agent_id": "hello_agent"},
        ]
    else:
        items.append(
            {
                "agent_id": "hello_agent",
                "inputs": {"name": "同批伪独立项"},
                "skill_package_ref": ref,
            }
        )
    _persist_reuse_recommendation(
        app,
        conversation_id,
        ref,
        agents=planned_agents,
    )

    class MustNotResolve:
        called = False

        def resolve_for_task(self, *_args, **_kwargs):
            self.called = True
            raise AssertionError("计划/批次重复必须在包解析前被拒绝")

    evidence = MustNotResolve()
    monkeypatch.setattr(app.state, "skill_reuse_evidence", evidence, raising=False)
    conn = app.state.conn_factory()
    try:
        before = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    finally:
        conn.close()

    response = client.post(
        "/api/tasks/batch",
        json={"conversation_id": conversation_id, "items": items},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "skill_package_reuse_invalid"
    assert evidence.called is False
    conn = app.state.conn_factory()
    try:
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == before
    finally:
        conn.close()
