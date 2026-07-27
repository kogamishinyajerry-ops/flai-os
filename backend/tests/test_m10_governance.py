"""M10 治理闭环的 ADR-0018 红线测试。"""

from __future__ import annotations

import builtins
import hashlib
import json
import shutil
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

from conftest import (
    TEST_DISPLAY_NAME,
    TEST_USERNAME,
    login,
    seed_and_login,
    seed_user,
)

from backend.app.governance.signer_provenance import (
    SignerContext,
)
from backend.app.main import create_app
from backend.app.storage import repos


REPO = Path(__file__).resolve().parents[2]
_MISSING = object()


def _server_cli_signer(label: str = "王工") -> SignerContext:
    return SignerContext.from_server_cli(label)


@dataclass
class GovernanceEnv:
    client: TestClient
    app: Any
    agents_dir: Path

    @property
    def governed_dir(self) -> Path:
        return self.agents_dir / "governed_agent"

    @property
    def governed_cases_dir(self) -> Path:
        return self.governed_dir / "eval_cases"


def _base_cases() -> dict[str, dict[str, Any]]:
    return {
        "case_001.json": {
            "case_id": "case_001",
            "inputs": {"name": "世界"},
            "checks": [{"kind": "status_is", "value": "waiting_review"}],
        },
        "case_002.json": {
            "case_id": "case_002",
            "inputs": {},
            "checks": [{"kind": "status_is", "value": "failed"}],
        },
        "case_003.json": {
            "case_id": "case_003",
            "inputs": {"name": 1},
            "checks": [{"kind": "status_is", "value": "failed"}],
        },
    }


def _write_eval_cases(
    env_or_agents_dir: GovernanceEnv | Path,
    cases: dict[str, dict[str, Any]],
    *,
    agent_id: str = "governed_agent",
) -> Path:
    agents_dir = (
        env_or_agents_dir.agents_dir
        if isinstance(env_or_agents_dir, GovernanceEnv)
        else env_or_agents_dir
    )
    cases_dir = agents_dir / agent_id / "eval_cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    for path in cases_dir.glob("*.json"):
        path.unlink()
    for filename, case in cases.items():
        (cases_dir / filename).write_text(
            json.dumps(case, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return cases_dir


@pytest.fixture()
def governance_env(tmp_path: Path) -> Iterator[GovernanceEnv]:
    """构造完全位于 tmp_path 的 hello/governed Agent 包与应用状态。"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    shutil.copytree(REPO / "agents" / "hello_agent", agents_dir / "hello_agent")
    shutil.copytree(REPO / "agents" / "hello_agent", agents_dir / "governed_agent")

    yaml_path = agents_dir / "governed_agent" / "agent.yaml"
    yaml_text = yaml_path.read_text(encoding="utf-8")
    assert yaml_text.count("id: hello_agent") == 1
    assert yaml_text.count("requires_human_review: false") == 1
    assert "collect_samples: true" in yaml_text
    yaml_path.write_text(
        yaml_text.replace("id: hello_agent", "id: governed_agent").replace(
            "requires_human_review: false",
            "requires_human_review: true",
        )
        # ADR-0030 创建时点密级准入门：m11 分级传播测试要喂 sensitive/缺失记录
        # 输入给本 agent，须显式持有 sensitive 准入才合法过门（缺省 internal 会
        # 在创建期 400，传播链路根本跑不起来）。
        + "\nclearance:\n  max_data_classification: sensitive\n",
        encoding="utf-8",
    )
    _write_eval_cases(agents_dir, _base_cases())

    db_path = tmp_path / "flai_os.db"
    app = create_app(
        agents_dir=agents_dir,
        tools_dir=REPO / "tools_impl",
        contracts_dir=REPO / "contracts",
        db_path=db_path,
        uploads_dir=tmp_path / "uploads",
        task_runs_dir=tmp_path / "task_runs",
    )
    with TestClient(app) as client:
        seed_and_login(client, db_path)
        yield GovernanceEnv(client=client, app=app, agents_dir=agents_dir)


def _drain_eval_run(
    env: GovernanceEnv, run_id: str, *, timeout_s: float = 30.0
) -> dict[str, Any]:
    """把一条 queued eval-run 用 EvalRunner 驱动到终态并返回（T1 异步队列，GH #2）。

    治理逻辑测试不关心 eval 跑批「同步还是异步」，只关心触发后产出的终态证据对不对；
    本 helper 把「入队→worker 排空到终态」封在一处，既有各测试的断言语义原样保留。"""
    from backend.app.governance.eval_worker import EvalRunner

    worker = EvalRunner(
        agent_registry=env.app.state.agent_registry,
        runtime=env.app.state.runtime,
        conn_factory=env.app.state.conn_factory,
        uploads_dir=env.app.state.uploads_dir,
        task_runs_dir=env.app.state.task_runs_dir,
        quota=2,
        poll_interval=0.02,
    )
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        worker.run_once()
        conn = env.app.state.conn_factory()
        try:
            run = repos.get_eval_run(conn, run_id)
        finally:
            conn.close()
        if run is not None and run["status"] not in ("queued", "running"):
            return run
        time.sleep(0.05)
    raise AssertionError(f"eval-run {run_id} 未在 {timeout_s}s 内到终态")


def _run_eval(env: GovernanceEnv, agent_id: str = "governed_agent") -> dict[str, Any]:
    response = env.client.post(
        f"/api/agents/{agent_id}/eval-runs",
        json={},
    )
    assert response.status_code == 202, response.text  # T1：入队立即返回 queued
    queued = response.json()
    assert queued["status"] == "queued"
    assert queued["triggered_by"] == TEST_DISPLAY_NAME
    return _drain_eval_run(env, queued["id"])


def _create_and_execute_user_task(
    env: GovernanceEnv,
    *,
    name: str = "用户任务",
    agent_id: str = "governed_agent",
) -> tuple[str, dict[str, Any]]:
    created = env.client.post(
        "/api/tasks",
        json={
            "agent_id": agent_id,
            "inputs": {"name": name},
        },
    )
    assert created.status_code == 200, created.text
    task_id = created.json()["id"]

    conn = env.app.state.conn_factory()
    try:
        claimed = repos.claim_next_queued(conn)
    finally:
        conn.close()
    assert claimed is not None
    assert claimed["id"] == task_id

    result = env.app.state.runtime.execute(task_id)
    return task_id, result


def _samples_for_task(env: GovernanceEnv, task_id: str) -> list[dict[str, Any]]:
    conn = env.app.state.conn_factory()
    try:
        return repos.list_samples(conn, task_id)
    finally:
        conn.close()


def _sample_count(env: GovernanceEnv) -> int:
    conn = env.app.state.conn_factory()
    try:
        return int(conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0])
    finally:
        conn.close()


def _audit_records(env: GovernanceEnv) -> list[dict[str, Any]]:
    path = Path(env.app.state.db_path).parent / "logs" / "audit.log"
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _reviewed_sample(
    env: GovernanceEnv,
    *,
    action: str,
) -> tuple[str, dict[str, Any]]:
    task_id, result = _create_and_execute_user_task(env)
    assert result["status"] == "waiting_review"
    reviewed = env.client.post(
        f"/api/tasks/{task_id}/review",
        json={"action": action, "comment": "M10 测试"},
    )
    assert reviewed.status_code == 200, reviewed.text
    samples = _samples_for_task(env, task_id)
    assert len(samples) == 1
    return task_id, samples[0]


def _fix_sample(
    env: GovernanceEnv,
    sample_id: int,
):
    return env.client.post(
        "/api/agents/governed_agent/eval-cases",
        json={"sample_id": sample_id},
    )


def _acknowledge_sample(
    env: GovernanceEnv,
    sample_id: int,
    payload: dict[str, Any] | None = None,
):
    return env.client.post(
        f"/api/samples/{sample_id}/acknowledge",
        json={} if payload is None else payload,
    )


def _seed_matching_case(
    env: GovernanceEnv,
    sample: dict[str, Any],
    *,
    curation: str = "draft",
    acknowledged_by_username: str | None = None,
    acknowledged_at: str | None = None,
) -> Path:
    """写一条与 sample 匹配的历史 case，供双域 provenance 负测使用。"""
    cases_dir = env.agents_dir / sample["agent_id"] / "eval_cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    provenance: dict[str, Any] = {
        "sample_id": sample["id"],
        "task_id": sample["task_id"],
        "agent_version": sample["agent_version"],
        "fixed_by": "历史策展者",
        "fixed_at": "2026-07-01T00:00:00+00:00",
    }
    if acknowledged_by_username is not None:
        provenance["acknowledged_by_username"] = acknowledged_by_username
        provenance["acknowledged_at"] = acknowledged_at
    case = {
        "case_id": "case_001",
        "curation": curation,
        "inputs": sample["input"],
        "checks": [{"kind": "status_is", "value": "completed"}],
        "provenance": provenance,
    }
    path = cases_dir / "case_001_from_sample.json"
    path.write_text(
        json.dumps(case, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _promote(
    env: GovernanceEnv,
    eval_run_id: str,
    *,
    confirmations: Any = _MISSING,
):
    payload: dict[str, Any] = {
        "to_maturity": "L1",
        "eval_run_id": eval_run_id,
    }
    if confirmations is not _MISSING:
        payload["confirmations"] = confirmations
    return env.client.post("/api/agents/governed_agent/promote", json=payload)


def _rejection_checks(response) -> dict[str, Any]:
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["detail"]["message"] == "晋升条件未全部满足"
    return body["detail"]["checks"]


def test_runner_all_green_records_eval_tasks(governance_env: GovernanceEnv) -> None:
    """验证全绿 run 精确计数、非空 digest 与逐 case 的 eval-origin 真实任务证据。"""
    run = _run_eval(governance_env)

    assert run["status"] == "completed"
    assert (run["total"], run["passed"], run["failed"], run["skipped"]) == (3, 3, 0, 0)
    assert isinstance(run["eval_cases_digest"], str)
    assert len(run["eval_cases_digest"]) == 64
    assert len(run["case_results"]) == 3

    conn = governance_env.app.state.conn_factory()
    try:
        for result in run["case_results"]:
            assert result["task_id"].startswith("task_")
            task = repos.get_task(conn, result["task_id"])
            assert task is not None
            assert task["origin"] == "eval"
    finally:
        conn.close()


def test_synchronous_eval_path_freezes_immutable_snapshot(
    governance_env: GovernanceEnv,
) -> None:
    """官方 promote CLI 使用的同步 eval 路径也必须产出 snapshot_handle。"""

    from backend.app.governance.eval_runner import run_agent_evals

    run = run_agent_evals(
        conn_factory=governance_env.app.state.conn_factory,
        agent_registry=governance_env.app.state.agent_registry,
        runtime=governance_env.app.state.runtime,
        uploads_dir=governance_env.app.state.uploads_dir,
        task_runs_dir=governance_env.app.state.task_runs_dir,
        agent_id="governed_agent",
        triggered_by=TEST_DISPLAY_NAME,
    )
    assert isinstance(run["snapshot_handle"], str)
    assert run["snapshot_handle"].startswith("snap_")
    conn = governance_env.app.state.conn_factory()
    try:
        snapshot = repos.get_eval_snapshot(conn, run["snapshot_handle"])
    finally:
        conn.close()
    assert snapshot is not None
    assert snapshot["eval_cases_digest"] == run["eval_cases_digest"]


def test_runner_counts_wrong_oracle_as_failed(governance_env: GovernanceEnv) -> None:
    """验证新增错误期望值会被 oracle 咬合并如实计为一个 failed case。"""
    cases = _base_cases()
    cases["case_004_wrong_oracle.json"] = {
        "case_id": "case_004",
        "inputs": {"name": "错误期望"},
        "checks": [{"kind": "status_is", "value": "completed"}],
    }
    _write_eval_cases(governance_env, cases)

    run = _run_eval(governance_env)

    assert (run["total"], run["passed"], run["failed"], run["skipped"]) == (4, 3, 1, 0)
    wrong = next(
        item for item in run["case_results"] if item["case_file"] == "case_004_wrong_oracle.json"
    )
    assert wrong["verdict"] == "failed"
    assert wrong["task_id"].startswith("task_")


def test_runner_unknown_agent_returns_404(governance_env: GovernanceEnv) -> None:
    """验证对不存在 Agent 触发 eval run 时 API fail-closed 返回 404。"""
    response = governance_env.client.post(
        "/api/agents/nope/eval-runs",
        json={},
    )

    assert response.status_code == 404


def test_empty_eval_cases_are_not_green_or_promotable(
    governance_env: GovernanceEnv,
) -> None:
    """验证空 eval_cases 的 run 为 total=0 且不能作为晋升证据。"""
    _write_eval_cases(governance_env, {})

    run = _run_eval(governance_env)

    assert (run["total"], run["passed"], run["failed"], run["skipped"]) == (0, 0, 0, 0)
    assert run["eval_cases_digest"] is None
    is_green = run["total"] > 0 and run["failed"] == 0 and run["skipped"] == 0
    assert is_green is False

    checks = _rejection_checks(
        _promote(
            governance_env,
            run["id"],
            confirmations={"exception_paths_handled": True},
        )
    )
    assert checks["min_eval_coverage"]["ok"] is False
    assert checks["eval_evidence"]["ok"] is False


def test_case_without_checks_is_skipped_not_passed(
    governance_env: GovernanceEnv,
) -> None:
    """验证无 checks 的 case 只计 skipped 且绝不计 passed。"""
    _write_eval_cases(
        governance_env,
        {
            "case_001_no_checks.json": {
                "case_id": "case_001",
                "inputs": {"name": "不可判"},
            }
        },
    )

    run = _run_eval(governance_env)

    assert (run["total"], run["passed"], run["failed"], run["skipped"]) == (1, 0, 0, 1)
    result = run["case_results"][0]
    assert result["verdict"] == "skipped"
    assert "task_id" not in result


@pytest.mark.parametrize(
    ("check", "detail_fragment"),
    [
        ({"kind": "nope"}, "未识别的 check kind"),
        (
            {"kind": "output_field", "file": "hello_output.json", "op": "exists"},
            "缺必填字段 'path'",
        ),
    ],
    ids=["unknown-kind", "missing-required-field"],
)
def test_invalid_check_configuration_fails_closed(
    governance_env: GovernanceEnv,
    check: dict[str, Any],
    detail_fragment: str,
) -> None:
    """验证未知 kind 与必填字段缺失都计 failed 而不是 skipped。"""
    _write_eval_cases(
        governance_env,
        {
            "case_001_bad_check.json": {
                "case_id": "case_001",
                "inputs": {"name": "坏断言"},
                "checks": [check],
            }
        },
    )

    run = _run_eval(governance_env)

    assert (run["total"], run["passed"], run["failed"], run["skipped"]) == (1, 0, 1, 0)
    result = run["case_results"][0]
    assert result["verdict"] == "failed"
    assert result["task_id"].startswith("task_")
    assert result["checks"][0]["ok"] is False
    assert detail_fragment in result["checks"][0]["detail"]


def test_draft_case_is_reported_but_not_executed(
    governance_env: GovernanceEnv,
) -> None:
    """验证 curation=draft 的 case 不执行、不计数并只出现在 draft_cases。"""
    cases = _base_cases()
    cases["case_004_draft.json"] = {
        "case_id": "case_004",
        "curation": "draft",
        "inputs": {"name": "草稿"},
        "checks": [{"kind": "status_is", "value": "waiting_review"}],
    }
    _write_eval_cases(governance_env, cases)

    run = _run_eval(governance_env)

    assert (run["total"], run["passed"], run["failed"], run["skipped"]) == (3, 3, 0, 0)
    assert all(
        item["case_file"] != "case_004_draft.json" for item in run["case_results"]
    ) is True
    draft = next(
        item for item in run["draft_cases"] if item["case_file"] == "case_004_draft.json"
    )
    assert "task_id" not in draft

    conn = governance_env.app.state.conn_factory()
    try:
        eval_task_count = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE origin = 'eval'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert eval_task_count == 3


def test_interactive_agent_cases_are_all_skipped(
    governance_env: GovernanceEnv,
) -> None:
    """验证复制到 tmp 的 interactive guide_agent 全部 case skipped 并附原因。"""
    shutil.copytree(
        REPO / "agents" / "guide_agent",
        governance_env.agents_dir / "guide_agent",
    )
    governance_env.app.state.agent_registry.scan()
    assert governance_env.app.state.agent_registry.errors == []

    run = _run_eval(governance_env, "guide_agent")

    assert run["total"] > 0
    assert run["passed"] == 0
    assert run["failed"] == 0
    assert run["skipped"] == run["total"]
    assert all(item["verdict"] == "skipped" for item in run["case_results"]) is True
    assert all("task_id" not in item for item in run["case_results"]) is True
    assert all("interactive" in item["detail"] for item in run["case_results"]) is True


def test_worker_never_claims_queued_eval_task(
    governance_env: GovernanceEnv,
) -> None:
    """验证 origin=eval 的 queued 任务不在 claim_next_queued 候选集中。"""
    conn = governance_env.app.state.conn_factory()
    try:
        repos.create_task(
            conn,
            task_id="task_eval_queued",
            agent_id="governed_agent",
            agent_version="0.1.0",
            name="eval witness",
            created_by="测试工程师",
            inputs={"name": "隔离"},
            origin="eval",
        )
        repos.set_task_status(conn, "task_eval_queued", "queued")
        claimed = repos.claim_next_queued(conn)
        queued = repos.get_task(conn, "task_eval_queued")
    finally:
        conn.close()

    assert claimed is None
    assert queued is not None
    assert queued["status"] == "queued"
    assert queued["origin"] == "eval"


def test_eval_tasks_do_not_collect_samples_but_user_task_does(
    governance_env: GovernanceEnv,
) -> None:
    """验证 collect_samples Agent 的 eval 执行零落样而同 Agent 用户任务恰落一条。"""
    _run_eval(governance_env)
    assert _sample_count(governance_env) == 0

    task_id, result = _create_and_execute_user_task(governance_env)

    assert result["status"] == "waiting_review"
    assert _sample_count(governance_env) == 1
    samples = _samples_for_task(governance_env, task_id)
    assert len(samples) == 1
    assert samples[0]["accepted_by_engineer"] is None


def test_task_list_origin_filters_keep_eval_out_of_default_view(
    governance_env: GovernanceEnv,
) -> None:
    """验证任务列表默认仅 user、origin=eval 仅 eval、origin=all 返回二者全集。"""
    run = _run_eval(governance_env)
    eval_ids = {item["task_id"] for item in run["case_results"]}
    created = governance_env.client.post(
        "/api/tasks",
        json={
            "agent_id": "governed_agent",
            "inputs": {"name": "列表见证"},
        },
    )
    assert created.status_code == 200
    user_id = created.json()["id"]

    default_rows = governance_env.client.get("/api/tasks").json()
    eval_rows = governance_env.client.get("/api/tasks?origin=eval").json()
    all_rows = governance_env.client.get("/api/tasks?origin=all").json()

    assert {row["id"] for row in default_rows} == {user_id}
    assert all(row["origin"] == "user" for row in default_rows) is True
    assert {row["id"] for row in eval_rows} == eval_ids
    assert all(row["origin"] == "eval" for row in eval_rows) is True
    assert {row["id"] for row in all_rows} == eval_ids | {user_id}


def test_sample_acknowledgement_from_session_creates_one_draft_and_updates_shared_counter(
    governance_env: GovernanceEnv,
) -> None:
    """Issue #4：无需 task review 的完成样本可由认证人逐条认可。

    认可必须把稳定 username 落到 sample/case provenance，并 ensure 恰好一个
    curation=draft case；公开计数与 Eval/Promotion 共用 curation 两态口径。
    draft 只进入候选计数，绝不冒充 approved 晋升覆盖。
    """
    hello_cases = governance_env.agents_dir / "hello_agent" / "eval_cases"
    for path in hello_cases.glob("*.json"):
        path.unlink()

    task_id, result = _create_and_execute_user_task(
        governance_env,
        name="无需整单审核的样本",
        agent_id="hello_agent",
    )
    assert result["status"] == "completed"
    sample = _samples_for_task(governance_env, task_id)[0]
    assert sample["accepted_by_engineer"] is None

    before = governance_env.client.get(
        "/api/agents/hello_agent/curated_cases_count"
    )
    assert before.status_code == 200
    assert before.json()["count"] == 0

    first = _acknowledge_sample(governance_env, sample["id"])

    assert first.status_code == 200, first.text
    acknowledged = first.json()
    assert acknowledged["sample_id"] == sample["id"]
    assert acknowledged["agent_id"] == "hello_agent"
    assert acknowledged["curation"] == "draft"
    assert acknowledged["acknowledged_by_username"] == TEST_USERNAME
    assert acknowledged["acknowledged_by_username"] != TEST_DISPLAY_NAME

    samples = governance_env.client.get(f"/api/tasks/{task_id}/samples")
    assert samples.status_code == 200
    projected = samples.json()[0]
    assert projected["accepted_by_engineer"] is True
    assert projected["acknowledged_by_username"] == TEST_USERNAME
    assert projected["acknowledged_at"] == acknowledged["acknowledged_at"]

    counter = governance_env.client.get(
        "/api/agents/hello_agent/curated_cases_count"
    )
    assert counter.status_code == 200
    assert counter.json() == {
        "agent_id": "hello_agent",
        "count": 1,
        "approved": 0,
        "draft": 1,
        "broken": 0,
    }

    case_path = hello_cases / acknowledged["case_file"]
    case = json.loads(case_path.read_text(encoding="utf-8"))
    assert case["curation"] == "draft"
    assert case["provenance"]["sample_id"] == sample["id"]
    assert case["provenance"]["acknowledged_by_username"] == TEST_USERNAME
    assert case["provenance"]["acknowledged_at"] == acknowledged["acknowledged_at"]

    second = _acknowledge_sample(governance_env, sample["id"])
    assert second.status_code == 200, second.text
    assert second.json() == acknowledged
    assert len(list(hello_cases.glob("case_*_from_sample.json"))) == 1
    assert governance_env.client.get(
        "/api/agents/hello_agent/curated_cases_count"
    ).json()["draft"] == 1
    audit = [
        record
        for record in _audit_records(governance_env)
        if record.get("action") == "sample_acknowledgement"
        and record.get("sample_id") == sample["id"]
    ]
    assert [record["outcome"] for record in audit] == [
        "acknowledged",
        "idempotent_replay",
    ]
    assert {record["actor"] for record in audit} == {TEST_USERNAME}
    assert all(
        record["acknowledged_by_username"] == TEST_USERNAME
        and record["agent_id"] == "hello_agent"
        and record["case_file"] == acknowledged["case_file"]
        and record["curation"] == "draft"
        for record in audit
    ) is True
    dropped = [
        record
        for record in _audit_records(governance_env)
        if record.get("action") == "audit_field_dropped"
    ]
    assert not any(
        {
            "sample_id",
            "case_file",
            "curation",
            "acknowledged_by_username",
        }
        & set(record.get("dropped_keys") or [])
        for record in dropped
    )


def test_sample_acknowledgement_requires_auth_and_rejects_client_actor(
    governance_env: GovernanceEnv,
) -> None:
    """未登录拒绝；登录者也不能从请求体伪造 actor。两次失败均不得留下半认可。"""
    hello_cases = governance_env.agents_dir / "hello_agent" / "eval_cases"
    for path in hello_cases.glob("*.json"):
        path.unlink()
    task_id, result = _create_and_execute_user_task(
        governance_env,
        name="认证边界样本",
        agent_id="hello_agent",
    )
    assert result["status"] == "completed"
    sample = _samples_for_task(governance_env, task_id)[0]

    anonymous = TestClient(governance_env.app)
    try:
        unauthenticated = anonymous.post(
            f"/api/samples/{sample['id']}/acknowledge",
            json={},
        )
    finally:
        anonymous.close()
    assert unauthenticated.status_code == 401

    forged = _acknowledge_sample(
        governance_env,
        sample["id"],
        payload={"actor": "mallory"},
    )
    assert forged.status_code == 422

    projected = _samples_for_task(governance_env, task_id)[0]
    assert projected["accepted_by_engineer"] is None
    assert projected.get("acknowledged_by_username") is None
    assert list(hello_cases.glob("case_*_from_sample.json")) == []


def test_sample_acknowledgement_rejects_untrusted_case_only_signer(
    governance_env: GovernanceEnv,
) -> None:
    """DB 尚未签发时，裸 case provenance 不能反向成为认证身份来源。"""
    hello_cases = governance_env.agents_dir / "hello_agent" / "eval_cases"
    for path in hello_cases.glob("*.json"):
        path.unlink()
    task_id, result = _create_and_execute_user_task(
        governance_env,
        name="case-only 冒名",
        agent_id="hello_agent",
    )
    assert result["status"] == "completed"
    sample = _samples_for_task(governance_env, task_id)[0]
    case_path = _seed_matching_case(
        governance_env,
        sample,
        acknowledged_by_username="mallory",
        acknowledged_at="2026-07-01T01:02:03+00:00",
    )
    before = case_path.read_bytes()

    response = _acknowledge_sample(governance_env, sample["id"])

    assert response.status_code == 409
    assert case_path.read_bytes() == before
    projected = _samples_for_task(governance_env, task_id)[0]
    assert projected["accepted_by_engineer"] is None
    assert projected["acknowledged_by_username"] is None
    assert not any(
        record.get("action") == "sample_acknowledgement"
        and record.get("sample_id") == sample["id"]
        for record in _audit_records(governance_env)
    )


@pytest.mark.parametrize("curation_state", ["draft", "approved"])
def test_sample_acknowledgement_rejects_unsigned_existing_case_for_reconciliation(
    governance_env: GovernanceEnv,
    curation_state: str,
) -> None:
    """历史 unsigned case 不能被在线请求改写；须由人工迁移对账。"""
    hello_cases = governance_env.agents_dir / "hello_agent" / "eval_cases"
    for path in hello_cases.glob("*.json"):
        path.unlink()
    task_id, result = _create_and_execute_user_task(
        governance_env,
        name=f"历史 {curation_state} case 补签",
        agent_id="hello_agent",
    )
    assert result["status"] == "completed"
    sample = _samples_for_task(governance_env, task_id)[0]
    case_path = _seed_matching_case(
        governance_env,
        sample,
        curation=curation_state,
    )
    before = case_path.read_bytes()

    response = _acknowledge_sample(governance_env, sample["id"])

    assert response.status_code == 409
    assert case_path.read_bytes() == before
    projected = _samples_for_task(governance_env, task_id)[0]
    assert projected["accepted_by_engineer"] is None
    assert projected["acknowledged_by_username"] is None
    assert projected["acknowledged_at"] is None


def test_sample_acknowledgement_cannot_overwrite_task_rejection(
    governance_env: GovernanceEnv,
) -> None:
    """既有人工 reject=false 是签发事实；sample ack 不得把它静默翻成 true。"""
    _task_id, sample = _reviewed_sample(governance_env, action="reject")
    assert sample["accepted_by_engineer"] is False
    before = set(governance_env.governed_cases_dir.glob("*.json"))

    response = _acknowledge_sample(governance_env, sample["id"])

    assert response.status_code == 409
    projected = _samples_for_task(governance_env, sample["task_id"])[0]
    assert projected["accepted_by_engineer"] is False
    assert projected.get("acknowledged_by_username") is None
    assert set(governance_env.governed_cases_dir.glob("*.json")) == before


def test_sample_acknowledgement_cannot_bypass_waiting_review(
    governance_env: GovernanceEnv,
) -> None:
    """逐 sample API 不是 task 人工放行旁路：waiting_review 必须原样停住。"""
    task_id, result = _create_and_execute_user_task(governance_env)
    assert result["status"] == "waiting_review"
    sample = _samples_for_task(governance_env, task_id)[0]
    before = set(governance_env.governed_cases_dir.glob("*.json"))

    response = _acknowledge_sample(governance_env, sample["id"])

    assert response.status_code == 422
    projected = _samples_for_task(governance_env, task_id)[0]
    assert projected["accepted_by_engineer"] is None
    assert projected["acknowledged_by_username"] is None
    assert set(governance_env.governed_cases_dir.glob("*.json")) == before


def test_concurrent_sample_acknowledgements_freeze_exactly_one_username(
    governance_env: GovernanceEnv,
) -> None:
    """两个同显示名账户并发认可：两请求幂等成功，但首次 username 永久胜出。"""
    hello_cases = governance_env.agents_dir / "hello_agent" / "eval_cases"
    for path in hello_cases.glob("*.json"):
        path.unlink()
    task_id, result = _create_and_execute_user_task(
        governance_env,
        name="并发认可",
        agent_id="hello_agent",
    )
    assert result["status"] == "completed"
    sample = _samples_for_task(governance_env, task_id)[0]

    other_username = "other_ack_reviewer"
    other_password = "other-ack-password"
    seed_user(
        governance_env.app.state.db_path,
        username=other_username,
        display_name=TEST_DISPLAY_NAME,
        password=other_password,
    )
    first_client = TestClient(governance_env.app)
    second_client = TestClient(governance_env.app)
    login(first_client)
    login(
        second_client,
        username=other_username,
        password=other_password,
    )
    barrier = threading.Barrier(2)
    responses: list[Any] = [None, None]

    def acknowledge(index: int, client: TestClient) -> None:
        barrier.wait(timeout=10)
        responses[index] = client.post(
            f"/api/samples/{sample['id']}/acknowledge",
            json={},
        )

    threads = [
        threading.Thread(target=acknowledge, args=(0, first_client)),
        threading.Thread(target=acknowledge, args=(1, second_client)),
    ]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
        assert all(thread.is_alive() is False for thread in threads)
    finally:
        first_client.close()
        second_client.close()

    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    actor = responses[0].json()["acknowledged_by_username"]
    assert actor in {TEST_USERNAME, other_username}
    assert actor != TEST_DISPLAY_NAME
    projected = _samples_for_task(governance_env, task_id)[0]
    assert projected["acknowledged_by_username"] == actor
    matching = list(hello_cases.glob("case_*_from_sample.json"))
    assert len(matching) == 1
    case = json.loads(matching[0].read_text(encoding="utf-8"))
    assert case["provenance"]["acknowledged_by_username"] == actor
    audit = [
        record
        for record in _audit_records(governance_env)
        if record.get("action") == "sample_acknowledgement"
        and record.get("sample_id") == sample["id"]
    ]
    acknowledged = [
        record for record in audit if record["outcome"] == "acknowledged"
    ]
    replayed = [
        record for record in audit if record["outcome"] == "idempotent_replay"
    ]
    assert len(acknowledged) == len(replayed) == 1
    assert acknowledged[0]["actor"] == actor
    assert replayed[0]["actor"] == (
        other_username if actor == TEST_USERNAME else TEST_USERNAME
    )
    assert all(
        record["acknowledged_by_username"] == actor
        and record["case_file"] == responses[0].json()["case_file"]
        for record in audit
    ) is True


def test_sample_acknowledgement_db_failure_before_publish_leaves_no_draft_and_retries(
    governance_env: GovernanceEnv,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DB CAS 先失败时不得触盘；恢复后同一请求可收敛成功。"""
    from backend.app.governance import curation

    hello_cases = governance_env.agents_dir / "hello_agent" / "eval_cases"
    for path in hello_cases.glob("*.json"):
        path.unlink()
    task_id, result = _create_and_execute_user_task(
        governance_env,
        name="补偿恢复",
        agent_id="hello_agent",
    )
    assert result["status"] == "completed"
    sample = _samples_for_task(governance_env, task_id)[0]
    real_acknowledge = repos.acknowledge_sample_once

    def fail_db_write(*_args, **_kwargs):
        raise RuntimeError("injected sample acknowledgement DB failure")

    monkeypatch.setattr(repos, "acknowledge_sample_once", fail_db_write)
    with pytest.raises(RuntimeError, match="injected"):
        curation.acknowledge_sample(
            conn_factory=governance_env.app.state.conn_factory,
            agent_registry=governance_env.app.state.agent_registry,
            sample_id=sample["id"],
            actor_username=TEST_USERNAME,
        )
    after_failure = _samples_for_task(governance_env, task_id)[0]
    assert after_failure["accepted_by_engineer"] is None
    assert after_failure["acknowledged_by_username"] is None
    assert list(hello_cases.glob("case_*_from_sample.json")) == []

    monkeypatch.setattr(repos, "acknowledge_sample_once", real_acknowledge)
    recovered = _acknowledge_sample(governance_env, sample["id"])
    assert recovered.status_code == 200, recovered.text
    assert len(list(hello_cases.glob("case_*_from_sample.json"))) == 1


def test_sample_acknowledgement_create_race_never_deletes_competing_case(
    governance_env: GovernanceEnv,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """独占创建输掉竞争时，本调用没有文件所有权，补偿绝不能 unlink 对手。"""
    from backend.app.governance import curation

    hello_cases = governance_env.agents_dir / "hello_agent" / "eval_cases"
    for path in hello_cases.glob("*.json"):
        path.unlink()
    task_id, result = _create_and_execute_user_task(
        governance_env,
        name="跨进程创建竞争",
        agent_id="hello_agent",
    )
    assert result["status"] == "completed"
    sample = _samples_for_task(governance_env, task_id)[0]
    target = hello_cases / "case_001_from_sample.json"
    competitor = b'{"competitor":"owns-this-file"}\n'
    real_link = curation.os.link

    def racing_link(source, destination, *args, **kwargs):
        if Path(destination) == target:
            target.write_bytes(competitor)
            raise FileExistsError("competitor won after scan")
        return real_link(source, destination, *args, **kwargs)

    monkeypatch.setattr(curation.os, "link", racing_link)
    with pytest.raises(FileExistsError, match="competitor won"):
        curation.acknowledge_sample(
            conn_factory=governance_env.app.state.conn_factory,
            agent_registry=governance_env.app.state.agent_registry,
            sample_id=sample["id"],
            actor_username=TEST_USERNAME,
        )

    assert target.read_bytes() == competitor
    assert list(hello_cases.glob(".*.tmp")) == []
    projected = _samples_for_task(governance_env, task_id)[0]
    assert projected["accepted_by_engineer"] is None
    assert projected["acknowledged_by_username"] is None


def test_sample_acknowledgement_preserves_existing_broken_failure_evidence(
    governance_env: GovernanceEnv,
) -> None:
    """包内已有坏 case 时认可 fail-closed，绝不能叠加新文件或删证据。"""
    hello_cases = governance_env.agents_dir / "hello_agent" / "eval_cases"
    for path in hello_cases.glob("*.json"):
        path.unlink()
    broken_path = hello_cases / "case_001_from_sample.json"
    broken_bytes = b"{not-json\n"
    broken_path.write_bytes(broken_bytes)
    task_id, result = _create_and_execute_user_task(
        governance_env,
        name="保留 broken blocker",
        agent_id="hello_agent",
    )
    assert result["status"] == "completed"
    sample = _samples_for_task(governance_env, task_id)[0]

    response = _acknowledge_sample(governance_env, sample["id"])

    assert response.status_code == 409
    assert broken_path.read_bytes() == broken_bytes
    assert list(hello_cases.glob("case_*_from_sample.json")) == [broken_path]
    projected = _samples_for_task(governance_env, task_id)[0]
    assert projected["accepted_by_engineer"] is None
    assert projected["acknowledged_by_username"] is None
    assert governance_env.client.get(
        "/api/agents/hello_agent/curated_cases_count"
    ).json() == {
        "agent_id": "hello_agent",
        "count": 1,
        "approved": 0,
        "draft": 0,
        "broken": 1,
    }


def test_sample_acknowledgement_temp_cleanup_failure_keeps_published_result(
    governance_env: GovernanceEnv,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Windows sharing violation 不得把已发布 case 误报成失败。"""
    from backend.app.governance import curation

    hello_cases = governance_env.agents_dir / "hello_agent" / "eval_cases"
    for path in hello_cases.glob("*.json"):
        path.unlink()
    task_id, result = _create_and_execute_user_task(
        governance_env,
        name="临时文件清理失败",
        agent_id="hello_agent",
    )
    assert result["status"] == "completed"
    sample = _samples_for_task(governance_env, task_id)[0]
    real_unlink = curation.os.unlink
    blocked_temps: list[Path] = []

    def fail_temp_cleanup(path, *args, **kwargs):
        candidate = Path(path)
        if candidate.parent == hello_cases and candidate.suffix == ".tmp":
            blocked_temps.append(candidate)
            raise PermissionError("simulated Windows sharing violation")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(curation.os, "unlink", fail_temp_cleanup)
    acknowledged = curation.acknowledge_sample(
        conn_factory=governance_env.app.state.conn_factory,
        agent_registry=governance_env.app.state.agent_registry,
        sample_id=sample["id"],
        actor_username=TEST_USERNAME,
    )

    assert acknowledged.created is True
    assert acknowledged.record["acknowledged_by_username"] == TEST_USERNAME
    targets = list(hello_cases.glob("case_*_from_sample.json"))
    assert len(targets) == 1
    case = json.loads(targets[0].read_text(encoding="utf-8"))
    assert case["provenance"]["acknowledged_by_username"] == TEST_USERNAME
    assert len(blocked_temps) == 1
    assert blocked_temps[0].exists()
    assert "case 临时文件清理失败" in caplog.text
    projected = _samples_for_task(governance_env, task_id)[0]
    assert projected["accepted_by_engineer"] is True
    assert projected["acknowledged_by_username"] == TEST_USERNAME


def test_sample_acknowledgement_commit_failure_preserves_case_for_reconciliation(
    governance_env: GovernanceEnv,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """发布后 COMMIT 失败时不做破坏性补偿，保留 case-only 待人工对账。"""
    from backend.app.governance import curation

    hello_cases = governance_env.agents_dir / "hello_agent" / "eval_cases"
    for path in hello_cases.glob("*.json"):
        path.unlink()
    task_id, result = _create_and_execute_user_task(
        governance_env,
        name="提交失败待核",
        agent_id="hello_agent",
    )
    assert result["status"] == "completed"
    sample = _samples_for_task(governance_env, task_id)[0]
    real_conn_factory = governance_env.app.state.conn_factory

    class CommitFailingConnection:
        def __init__(self, real: Any) -> None:
            self._real = real

        def execute(self, sql: str, *args: Any, **kwargs: Any):
            if " ".join(sql.split()).upper() == "COMMIT":
                raise sqlite3.OperationalError("injected COMMIT failure")
            return self._real.execute(sql, *args, **kwargs)

        def __getattr__(self, name: str) -> Any:
            return getattr(self._real, name)

    def failing_conn_factory() -> CommitFailingConnection:
        return CommitFailingConnection(real_conn_factory())

    with pytest.raises(sqlite3.OperationalError, match="injected COMMIT failure"):
        curation.acknowledge_sample(
            conn_factory=failing_conn_factory,
            agent_registry=governance_env.app.state.agent_registry,
            sample_id=sample["id"],
            actor_username=TEST_USERNAME,
        )

    projected = _samples_for_task(governance_env, task_id)[0]
    assert projected["accepted_by_engineer"] is None
    assert projected["acknowledged_by_username"] is None
    targets = list(hello_cases.glob("case_*_from_sample.json"))
    assert len(targets) == 1
    preserved = targets[0].read_bytes()
    case = json.loads(preserved)
    assert case["curation"] == "draft"
    assert case["provenance"]["acknowledged_by_username"] == TEST_USERNAME
    assert "case 已发布但 DB 未提交" in caplog.text

    retry = _acknowledge_sample(governance_env, sample["id"])
    assert retry.status_code == 409
    assert targets[0].read_bytes() == preserved


def test_sample_acknowledgement_missing_registry_package_fails_before_touch(
    governance_env: GovernanceEnv,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Registry id 仍在但 source_dir 不可取时，返回治理冲突而不是裸 500。"""
    hello_cases = governance_env.agents_dir / "hello_agent" / "eval_cases"
    for path in hello_cases.glob("*.json"):
        path.unlink()
    task_id, result = _create_and_execute_user_task(
        governance_env,
        name="package source missing",
        agent_id="hello_agent",
    )
    assert result["status"] == "completed"
    sample = _samples_for_task(governance_env, task_id)[0]
    registry = governance_env.app.state.agent_registry
    real_package_dir = registry.package_dir

    def missing_package(agent_id: str):
        if agent_id == "hello_agent":
            return None
        return real_package_dir(agent_id)

    monkeypatch.setattr(registry, "package_dir", missing_package)
    response = _acknowledge_sample(governance_env, sample["id"])

    assert response.status_code == 409
    projected = _samples_for_task(governance_env, task_id)[0]
    assert projected["accepted_by_engineer"] is None
    assert projected["acknowledged_by_username"] is None
    assert list(hello_cases.glob("*.json")) == []


@pytest.mark.parametrize("writer", ["acknowledge", "fix"])
def test_live_package_curation_is_rejected_after_l1_promotion(
    governance_env: GovernanceEnv,
    writer: str,
) -> None:
    """L1 包已绑定晋升快照后，任何 curation 写回都必须在触盘前拒绝。"""
    task_id, sample = _reviewed_sample(governance_env, action="approve")
    run = _run_eval(governance_env)
    promoted = _promote(
        governance_env,
        run["id"],
        confirmations={"exception_paths_handled": True},
    )
    assert promoted.status_code == 200, promoted.text
    before_files = {
        path.name: path.read_bytes()
        for path in governance_env.governed_cases_dir.glob("*.json")
    }
    snapshot = governance_env.app.state.agent_registry.package_snapshot(
        "governed_agent"
    )
    assert snapshot is not None
    snapshot_digest = snapshot.digest
    conn = governance_env.app.state.conn_factory()
    try:
        promotion_count = conn.execute(
            "SELECT COUNT(*) FROM promotions WHERE agent_id = 'governed_agent'"
        ).fetchone()[0]
    finally:
        conn.close()

    if writer == "acknowledge":
        response = _acknowledge_sample(governance_env, sample["id"])
    else:
        response = _fix_sample(governance_env, sample["id"])

    assert response.status_code == 409
    assert {
        path.name: path.read_bytes()
        for path in governance_env.governed_cases_dir.glob("*.json")
    } == before_files
    projected = _samples_for_task(governance_env, task_id)[0]
    assert projected["acknowledged_by_username"] is None
    assert (
        governance_env.app.state.agent_registry.package_snapshot(
            "governed_agent"
        ).digest
        == snapshot_digest
    )
    conn = governance_env.app.state.conn_factory()
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM promotions WHERE agent_id = 'governed_agent'"
        ).fetchone()[0] == promotion_count
    finally:
        conn.close()


@pytest.mark.parametrize("writer", ["acknowledge", "fix"])
def test_live_package_curation_respects_promotion_operation_latch(
    governance_env: GovernanceEnv,
    writer: str,
) -> None:
    """promotion pending/fault latch 存在时，curation 只读它且原样 409。"""
    if writer == "acknowledge":
        task_id, result = _create_and_execute_user_task(
            governance_env,
            name="pending latch acknowledge",
            agent_id="hello_agent",
        )
        assert result["status"] == "completed"
        sample = _samples_for_task(governance_env, task_id)[0]
        cases_dir = governance_env.agents_dir / "hello_agent" / "eval_cases"
    else:
        task_id, sample = _reviewed_sample(governance_env, action="approve")
        cases_dir = governance_env.governed_cases_dir
    before_files = {
        path.name: path.read_bytes()
        for path in cases_dir.glob("*.json")
    }
    pending_detail = json.dumps(
        {
            "axis": "promotion_attestation",
            "ok": False,
            "reason": "test-pending-operation",
        },
        sort_keys=True,
    )
    conn = governance_env.app.state.conn_factory()
    try:
        assert repos.record_promotion_attestation_fault(
            conn,
            detail=pending_detail,
        ) is True
    finally:
        conn.close()

    try:
        if writer == "acknowledge":
            response = _acknowledge_sample(governance_env, sample["id"])
        else:
            response = _fix_sample(governance_env, sample["id"])
        conn = governance_env.app.state.conn_factory()
        try:
            latch = repos.get_promotion_attestation_fault(conn)
        finally:
            conn.close()
        assert latch is not None
        assert latch["detail"] == pending_detail
    finally:
        conn = governance_env.app.state.conn_factory()
        try:
            repos.clear_promotion_attestation_fault(
                conn,
                expected_detail=pending_detail,
            )
        finally:
            conn.close()

    assert response.status_code == 409
    assert {
        path.name: path.read_bytes()
        for path in cases_dir.glob("*.json")
    } == before_files
    projected = _samples_for_task(governance_env, task_id)[0]
    assert projected["acknowledged_by_username"] is None


def test_acknowledged_draft_uses_shared_curation_source_without_faking_promotion_coverage(
    governance_env: GovernanceEnv,
) -> None:
    """2 approved + 1 acknowledged draft 仍不足晋升；counter 与 gate 同源不同态。"""
    cases = _base_cases()
    cases.pop("case_003.json")
    _write_eval_cases(governance_env, cases)
    _task_id, sample = _reviewed_sample(governance_env, action="approve")

    acknowledged = _acknowledge_sample(governance_env, sample["id"])
    assert acknowledged.status_code == 200, acknowledged.text
    counter = governance_env.client.get(
        "/api/agents/governed_agent/curated_cases_count"
    ).json()
    assert counter == {
        "agent_id": "governed_agent",
        "count": 3,
        "approved": 2,
        "draft": 1,
        "broken": 0,
    }

    run = _run_eval(governance_env)
    assert (run["total"], run["passed"]) == (2, 2)
    assert [item["case_file"] for item in run["draft_cases"]] == [
        acknowledged.json()["case_file"]
    ]

    checks = _rejection_checks(
        _promote(
            governance_env,
            run["id"],
            confirmations={"exception_paths_handled": True},
        )
    )
    assert checks["min_eval_coverage"]["ok"] is False
    assert checks["eval_evidence"]["ok"] is True


def test_approved_sample_is_fixed_as_real_draft_case(
    governance_env: GovernanceEnv,
) -> None:
    """验证用户任务经人工 approve 后可固化为带 provenance 与 completed check 的 draft 文件。"""
    task_id, sample = _reviewed_sample(governance_env, action="approve")
    assert sample["task_id"] == task_id
    assert sample["accepted_by_engineer"] is True

    response = _fix_sample(governance_env, sample["id"])

    assert response.status_code == 200, response.text
    case_path = governance_env.governed_cases_dir / response.json()["case_file"]
    assert case_path.is_file() is True
    case = json.loads(case_path.read_text(encoding="utf-8"))
    assert case["curation"] == "draft"
    assert case["provenance"]["sample_id"] == sample["id"]
    assert case["provenance"]["task_id"] == task_id
    assert case["provenance"]["fixed_by"] == TEST_DISPLAY_NAME
    assert {"kind": "status_is", "value": "completed"} in case["checks"]


def test_fixing_same_sample_twice_returns_409(
    governance_env: GovernanceEnv,
) -> None:
    """验证同一认可 sample 重复固化时返回 409 且不生成第二份 case。"""
    _, sample = _reviewed_sample(governance_env, action="approve")
    first = _fix_sample(governance_env, sample["id"])
    assert first.status_code == 200

    second = _fix_sample(governance_env, sample["id"])

    assert second.status_code == 409
    assert first.json()["case_file"] in second.json()["detail"]
    matching = []
    for path in governance_env.governed_cases_dir.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if (data.get("provenance") or {}).get("sample_id") == sample["id"]:
            matching.append(path)
    assert len(matching) == 1


def test_unapproved_sample_cannot_be_fixed(
    governance_env: GovernanceEnv,
) -> None:
    """验证 waiting_review 且尚未 approve 的 sample 固化请求返回 422。"""
    task_id, result = _create_and_execute_user_task(governance_env)
    assert result["status"] == "waiting_review"
    sample = _samples_for_task(governance_env, task_id)[0]
    assert sample["accepted_by_engineer"] is None

    response = _fix_sample(governance_env, sample["id"])

    assert response.status_code == 422


def test_rejected_sample_cannot_be_fixed(
    governance_env: GovernanceEnv,
) -> None:
    """验证人工 reject 后 accepted=False 的 sample 固化请求返回 422。"""
    _, sample = _reviewed_sample(governance_env, action="reject")
    assert sample["accepted_by_engineer"] is False

    response = _fix_sample(governance_env, sample["id"])

    assert response.status_code == 422


def test_promotion_happy_path_updates_yaml_projection_and_audit_record(
    governance_env: GovernanceEnv,
) -> None:
    """验证全绿证据通过五门后晋升 L1 并写回 YAML、API 投影与审计记录。"""
    # 同显示名的另一账户 + 当前账户的另一活会话，钉死“当前 cookie 精确绑定”：
    # 不能按 display_name 猜用户，也不能随便取该用户任一 session。
    decoy_user = seed_user(
        governance_env.app.state.db_path,
        username="same_display_decoy",
        display_name=TEST_DISPLAY_NAME,
        password="decoy-password",
    )
    decoy_client = TestClient(governance_env.app)
    login(
        decoy_client,
        username="same_display_decoy",
        password="decoy-password",
    )
    decoy_client.close()
    other_session_client = TestClient(governance_env.app)
    login(other_session_client)
    other_token = other_session_client.cookies.get("flai_session")
    assert other_token
    other_session_client.close()

    run = _run_eval(governance_env)

    response = _promote(
        governance_env,
        run["id"],
        confirmations={"exception_paths_handled": True},
    )

    assert response.status_code == 200, response.text
    promotion = response.json()
    assert promotion["from_maturity"] == "L0"
    assert promotion["to_maturity"] == "L1"
    assert promotion["confirmed_by"] == TEST_DISPLAY_NAME
    assert promotion["signer_source"] == "authenticated_session"
    assert promotion["signer_username"] == TEST_USERNAME
    assert promotion["signer_session_bound"] is True
    assert "signer_session_hash" not in promotion
    yaml_text = (governance_env.governed_dir / "agent.yaml").read_text(encoding="utf-8")
    assert "\nmaturity: L1\n" in f"\n{yaml_text}\n"

    projected = governance_env.client.get("/api/agents/governed_agent")
    assert projected.status_code == 200
    assert projected.json()["maturity"] == "L1"

    listed = governance_env.client.get("/api/agents/governed_agent/promotions")
    assert listed.status_code == 200
    records = listed.json()
    assert len(records) == 1
    assert all(item["ok"] is True for item in records[0]["checks"].values()) is True
    assert "平台级提供" in records[0]["checks"]["feedback_channel"]["detail"]

    conn = governance_env.app.state.conn_factory()
    try:
        raw = conn.execute(
            "SELECT checks_json, signer_source, signer_user_id, signer_username,"
            " signer_session_hash FROM promotions WHERE id = ?",
            (records[0]["id"],),
        ).fetchone()
    finally:
        conn.close()
    assert "平台级提供" in raw["checks_json"]
    assert raw["signer_source"] == "authenticated_session"
    assert raw["signer_user_id"] > 0
    assert raw["signer_user_id"] != decoy_user["id"]
    assert raw["signer_username"] == TEST_USERNAME
    current_token = governance_env.client.cookies.get("flai_session")
    assert current_token
    assert raw["signer_session_hash"] == hashlib.sha256(
        current_token.encode()
    ).hexdigest()
    assert raw["signer_session_hash"] != hashlib.sha256(
        other_token.encode()
    ).hexdigest()
    assert "signer_session_hash" not in records[0]


def test_authenticated_promotion_remains_valid_after_logout_and_restart(
    governance_env: GovernanceEnv,
) -> None:
    """真实 HTTP 签发→logout 删 session→新 app 启动，历史事实仍可核验。"""
    run = _run_eval(governance_env)
    promoted = _promote(
        governance_env,
        run["id"],
        confirmations={"exception_paths_handled": True},
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["signer_session_bound"] is True
    token = governance_env.client.cookies.get("flai_session")
    assert token
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    logout = governance_env.client.post("/api/auth/logout")
    assert logout.status_code == 200
    conn = governance_env.app.state.conn_factory()
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM auth_sessions WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()[0] == 0
    finally:
        conn.close()

    restarted = create_app(
        agents_dir=governance_env.agents_dir,
        tools_dir=REPO / "tools_impl",
        contracts_dir=REPO / "contracts",
        db_path=governance_env.app.state.db_path,
        uploads_dir=governance_env.app.state.uploads_dir,
        task_runs_dir=governance_env.app.state.task_runs_dir,
    )
    with TestClient(restarted) as restarted_client:
        registered = restarted.state.agent_registry.get("governed_agent")
        assert registered is not None
        assert registered["maturity"] == "L1"
        health = restarted_client.get("/api/health").json()
        assert health["promotion_attestation_ok"] is True
        assert health["promotion_attestation_rejected_count"] == 0


def test_promotion_rejects_fewer_than_three_approved_cases(
    governance_env: GovernanceEnv,
) -> None:
    """验证 approved eval case 只剩两个时 min_eval_coverage 门拒绝晋升。"""
    cases = _base_cases()
    cases.pop("case_003.json")
    _write_eval_cases(governance_env, cases)
    run = _run_eval(governance_env)
    assert (run["total"], run["passed"]) == (2, 2)

    checks = _rejection_checks(
        _promote(
            governance_env,
            run["id"],
            confirmations={"exception_paths_handled": True},
        )
    )

    assert checks["min_eval_coverage"]["ok"] is False
    assert checks["eval_evidence"]["ok"] is True


def test_promotion_rejects_all_happy_path_coverage(
    governance_env: GovernanceEnv,
) -> None:
    """验证三个全 happy-path case 因缺少 status_is failed 路径而拒绝晋升。"""
    happy_cases = {
        f"case_{index:03d}.json": {
            "case_id": f"case_{index:03d}",
            "inputs": {"name": f"正常路{index}"},
            "checks": [{"kind": "status_is", "value": "waiting_review"}],
        }
        for index in range(1, 4)
    }
    _write_eval_cases(governance_env, happy_cases)
    run = _run_eval(governance_env)
    assert (run["total"], run["passed"]) == (3, 3)

    checks = _rejection_checks(
        _promote(
            governance_env,
            run["id"],
            confirmations={"exception_paths_handled": True},
        )
    )

    assert checks["min_eval_coverage"]["ok"] is False
    assert checks["eval_evidence"]["ok"] is True


def test_promotion_rejects_unknown_eval_run_id(
    governance_env: GovernanceEnv,
) -> None:
    """验证不存在的 eval_run_id 不能充当晋升证据。"""
    checks = _rejection_checks(
        _promote(
            governance_env,
            "eval_missing",
            confirmations={"exception_paths_handled": True},
        )
    )

    assert checks["min_eval_coverage"]["ok"] is True
    assert checks["eval_evidence"]["ok"] is False


@pytest.mark.parametrize("not_green_kind", ["failed", "skipped"])
def test_promotion_rejects_non_green_eval_evidence(
    governance_env: GovernanceEnv,
    not_green_kind: str,
) -> None:
    """验证含 failed 或 skipped 的 eval run 均不能通过 eval_evidence 门。"""
    cases = _base_cases()
    if not_green_kind == "failed":
        cases["case_004_not_green.json"] = {
            "case_id": "case_004",
            "inputs": {"name": "错误期望"},
            "checks": [{"kind": "status_is", "value": "completed"}],
        }
    else:
        cases["case_004_not_green.json"] = {
            "case_id": "case_004",
            "inputs": {"name": "不可判"},
        }
    _write_eval_cases(governance_env, cases)
    run = _run_eval(governance_env)
    assert run[not_green_kind] == 1

    checks = _rejection_checks(
        _promote(
            governance_env,
            run["id"],
            confirmations={"exception_paths_handled": True},
        )
    )

    assert checks["min_eval_coverage"]["ok"] is True
    assert checks["eval_evidence"]["ok"] is False


def test_promotion_rejects_agent_version_changed_after_run(
    governance_env: GovernanceEnv,
) -> None:
    """验证 run 后 registry 当前版本变化会使旧版本 eval 证据失效。"""
    run = _run_eval(governance_env)
    yaml_path = governance_env.governed_dir / "agent.yaml"
    yaml_text = yaml_path.read_text(encoding="utf-8")
    assert yaml_text.count("version: 0.1.0") == 1
    yaml_path.write_text(
        yaml_text.replace("version: 0.1.0", "version: 0.1.1"),
        encoding="utf-8",
    )
    governance_env.app.state.agent_registry.scan()
    assert governance_env.app.state.agent_registry.errors == []
    assert governance_env.app.state.agent_registry.get("governed_agent")["version"] == "0.1.1"

    checks = _rejection_checks(
        _promote(
            governance_env,
            run["id"],
            confirmations={"exception_paths_handled": True},
        )
    )

    assert checks["eval_evidence"]["ok"] is False
    assert "版本一致=False" in checks["eval_evidence"]["detail"]


def test_promotion_rejects_eval_case_digest_tampering(
    governance_env: GovernanceEnv,
) -> None:
    """验证 run 后任一 approved case 内容改变会因 digest 不一致拒绝晋升。"""
    run = _run_eval(governance_env)
    case_path = governance_env.governed_cases_dir / "case_001.json"
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["description"] = "run 后篡改"
    case_path.write_text(
        json.dumps(case, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    checks = _rejection_checks(
        _promote(
            governance_env,
            run["id"],
            confirmations={"exception_paths_handled": True},
        )
    )

    assert checks["min_eval_coverage"]["ok"] is True
    assert checks["eval_evidence"]["ok"] is False
    assert "digest 一致（内容自评测以来未变）=False" in checks["eval_evidence"]["detail"]


@pytest.mark.parametrize("changelog_state", ["missing", "blank"])
def test_promotion_rejects_missing_or_blank_changelog(
    governance_env: GovernanceEnv,
    changelog_state: str,
) -> None:
    """验证 changelog.md 缺失或仅空白时 changelog_nonempty 门拒绝晋升。"""
    run = _run_eval(governance_env)
    changelog_path = governance_env.governed_dir / "changelog.md"
    if changelog_state == "missing":
        changelog_path.unlink()
    else:
        changelog_path.write_text(" \n\t", encoding="utf-8")

    checks = _rejection_checks(
        _promote(
            governance_env,
            run["id"],
            confirmations={"exception_paths_handled": True},
        )
    )

    assert checks["eval_evidence"]["ok"] is True
    assert checks["changelog_nonempty"]["ok"] is False


@pytest.mark.parametrize(
    ("confirmation_kind", "confirmations"),
    [
        ("missing", _MISSING),
        ("false", {"exception_paths_handled": False}),
        ("string", {"exception_paths_handled": "true"}),
        ("integer", {"exception_paths_handled": 1}),
    ],
    ids=["missing", "false", "string-true", "integer-one"],
)
def test_promotion_manual_confirmation_is_strict_boolean_true(
    governance_env: GovernanceEnv,
    confirmation_kind: str,
    confirmations: Any,
) -> None:
    """验证确认项缺失、false、字符串 true 与整数 1 均令 manual_confirmation 为 false。"""
    run = _run_eval(governance_env)
    response = _promote(
        governance_env,
        run["id"],
        confirmations=confirmations,
    )

    checks = _rejection_checks(response)

    assert confirmation_kind in {"missing", "false", "string", "integer"}
    assert checks["manual_confirmation"]["ok"] is False
    assert all(
        checks[name]["ok"] is True
        for name in (
            "transition_supported",
            "min_eval_coverage",
            "eval_evidence",
            "changelog_nonempty",
            "feedback_channel",
        )
    ) is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("confirmed_by", "冒名者"),
        ("signer_source", "server_cli"),
        ("signer_user_id", 999),
        ("signer_username", "forged"),
        ("signer_session_hash", "0" * 64),
        ("signer", {"source": "server_cli", "operator_label": "冒名者"}),
    ],
    ids=[
        "confirmed-by",
        "source",
        "user-id",
        "username",
        "session-hash",
        "nested-signer",
    ],
)
def test_promotion_rejects_client_signer_provenance_fields(
    governance_env: GovernanceEnv,
    field: str,
    value: Any,
) -> None:
    """客户端不能选择或覆盖任何签发来源字段；均由认证适配层派生。"""
    run = _run_eval(governance_env)

    body = {
        "to_maturity": "L1",
        "eval_run_id": run["id"],
        "confirmations": {"exception_paths_handled": True},
        field: value,
    }
    forged = governance_env.client.post(
        "/api/agents/governed_agent/promote",
        json=body,
    )
    assert forged.status_code == 422


def test_promotion_revalidates_exact_session_inside_final_transaction(
    governance_env: GovernanceEnv,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """入门认证后、最终事务前吊销精确会话：拒绝签发并完整补偿磁盘/投影。"""
    from backend.app.governance import promotion as promotion_mod

    run = _run_eval(governance_env)
    yaml_path = governance_env.governed_dir / "agent.yaml"
    changelog_path = governance_env.governed_dir / "changelog.md"
    yaml_before = yaml_path.read_text(encoding="utf-8")
    changelog_before = changelog_path.read_text(encoding="utf-8")
    token = governance_env.client.cookies.get("flai_session")
    assert token
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    real_build_shadow = promotion_mod._build_reconciled_shadow
    revoked = False

    def _revoke_after_first_shadow(*args: Any, **kwargs: Any):
        nonlocal revoked
        result = real_build_shadow(*args, **kwargs)
        if revoked is False:
            conn = governance_env.app.state.conn_factory()
            try:
                deleted = conn.execute(
                    "DELETE FROM auth_sessions WHERE token_hash = ?",
                    (token_hash,),
                )
                assert deleted.rowcount == 1
            finally:
                conn.close()
            revoked = True
        return result

    monkeypatch.setattr(
        promotion_mod,
        "_build_reconciled_shadow",
        _revoke_after_first_shadow,
    )
    response = _promote(
        governance_env,
        run["id"],
        confirmations={"exception_paths_handled": True},
    )

    assert response.status_code == 422
    checks = response.json()["detail"]["checks"]
    assert checks["signer_session_revalidation"]["ok"] is False
    assert yaml_path.read_text(encoding="utf-8") == yaml_before
    assert changelog_path.read_text(encoding="utf-8") == changelog_before
    assert governance_env.app.state.agent_registry.get("governed_agent")[
        "maturity"
    ] == "L0"
    conn = governance_env.app.state.conn_factory()
    try:
        assert conn.execute("SELECT COUNT(*) FROM promotions").fetchone()[0] == 0
        assert conn.execute(
            "SELECT maturity FROM agents WHERE id = 'governed_agent'"
        ).fetchone()["maturity"] == "L0"
        assert repos.get_promotion_attestation_fault(conn) is None
    finally:
        conn.close()


def test_promotion_rejects_session_expiring_during_final_projection_sync(
    governance_env: GovernanceEnv,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BEGIN IMMEDIATE 只能挡吊销写，不能冻结时钟；签发时点必须仍早于 expiry。"""
    from backend.app.auth import service as auth_service

    run = _run_eval(governance_env)
    clock = {"now": datetime.now(timezone.utc)}
    expires = clock["now"] + timedelta(seconds=1)
    token = governance_env.client.cookies.get("flai_session")
    assert token
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    conn = governance_env.app.state.conn_factory()
    try:
        conn.execute(
            "UPDATE auth_sessions SET expires_at = ? WHERE token_hash = ?",
            (expires.isoformat(), token_hash),
        )
    finally:
        conn.close()

    monkeypatch.setattr(auth_service, "_now", lambda: clock["now"])
    monkeypatch.setattr(repos, "_now_iso", lambda: clock["now"].isoformat())
    registry_type = type(governance_env.app.state.agent_registry)
    real_sync = registry_type.sync_to_db
    advanced = False

    def _sync_then_expire(self: Any, conn: sqlite3.Connection) -> None:
        nonlocal advanced
        real_sync(self, conn)
        if advanced is False and self.get("governed_agent")["maturity"] == "L1":
            clock["now"] = expires
            advanced = True

    monkeypatch.setattr(registry_type, "sync_to_db", _sync_then_expire)
    response = _promote(
        governance_env,
        run["id"],
        confirmations={"exception_paths_handled": True},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["checks"]["signer_session_revalidation"][
        "ok"
    ] is False
    conn = governance_env.app.state.conn_factory()
    try:
        assert conn.execute("SELECT COUNT(*) FROM promotions").fetchone()[0] == 0
    finally:
        conn.close()
    assert governance_env.app.state.agent_registry.get("governed_agent")[
        "maturity"
    ] == "L0"


def test_promotion_rejects_l1_to_l1_transition(
    governance_env: GovernanceEnv,
) -> None:
    """验证已晋升 L1 的 Agent 再申请 L1 时 transition_supported 门拒绝。"""
    run = _run_eval(governance_env)
    first = _promote(
        governance_env,
        run["id"],
        confirmations={"exception_paths_handled": True},
    )
    assert first.status_code == 200, first.text

    checks = _rejection_checks(
        _promote(
            governance_env,
            run["id"],
            confirmations={"exception_paths_handled": True},
        )
    )

    assert checks["transition_supported"]["ok"] is False
    records = governance_env.client.get(
        "/api/agents/governed_agent/promotions"
    ).json()
    assert len(records) == 1


# ── R1 复审故障注入回归（异源审 F1-F4） ─────────────────────────────────

def test_promotion_rolls_back_yaml_when_audit_record_fails(
    governance_env: GovernanceEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F2：审计记录落库失败时，yaml/changelog/投影必须恢复原状——绝不留
    「磁盘已 L1 却无 promotions 审计记录」的半提交。"""
    from backend.app.governance import promotion as promotion_mod

    run = _run_eval(governance_env)
    yaml_path = governance_env.governed_dir / "agent.yaml"
    changelog_path = governance_env.governed_dir / "changelog.md"
    yaml_before = yaml_path.read_text(encoding="utf-8")
    changelog_before = changelog_path.read_text(encoding="utf-8")

    def _boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("注入：审计记录写入失败")

    monkeypatch.setattr(promotion_mod.repos, "record_promotion", _boom)
    with pytest.raises(RuntimeError, match="审计记录写入失败"):
        promotion_mod.promote_agent(
            conn_factory=governance_env.app.state.conn_factory,
            agent_registry=governance_env.app.state.agent_registry,
            scope_registry=governance_env.app.state.scope_registry,
            agent_id="governed_agent",
            to_maturity="L1",
            eval_run_id=run["id"],
            confirmations={"exception_paths_handled": True},
            signer=_server_cli_signer(),
            attestation_records=[],
        )

    assert yaml_path.read_text(encoding="utf-8") == yaml_before
    assert changelog_path.read_text(encoding="utf-8") == changelog_before
    agent = governance_env.client.get("/api/agents/governed_agent").json()
    assert agent["maturity"] == "L0"
    assert governance_env.client.get("/api/agents/governed_agent/promotions").json() == []
    # R2 残余：不只信内存投影，直查 agents 表确认 DB 投影也回到 L0
    conn = governance_env.app.state.conn_factory()
    try:
        row = conn.execute(
            "SELECT maturity FROM agents WHERE id = 'governed_agent'"
        ).fetchone()
        assert row is not None and row["maturity"] == "L0"
        prow = conn.execute("SELECT COUNT(*) AS n FROM promotions").fetchone()
        assert prow["n"] == 0
    finally:
        conn.close()


def test_promotion_rollback_failure_sets_sticky_attestation_fault(
    governance_env: GovernanceEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """提交失败且补偿写盘也失败时，health 必须 sticky-fail，不能保留假绿。"""

    from backend.app.governance import promotion as promotion_mod

    run = _run_eval(governance_env)
    yaml_path = governance_env.governed_dir / "agent.yaml"
    original_open = builtins.open
    yaml_write_count = 0

    def _fail_restore_write(file: Any, *args: Any, **kwargs: Any):
        nonlocal yaml_write_count
        mode = args[0] if args else kwargs.get("mode", "r")
        candidate = Path(file) if isinstance(file, (str, Path)) else None
        if candidate == yaml_path and mode == "w":
            yaml_write_count += 1
            if yaml_write_count == 2:
                raise OSError("注入：补偿恢复 agent.yaml 失败")
        return original_open(file, *args, **kwargs)

    def _fail_record(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("注入：promotion 审计提交失败")

    monkeypatch.setattr(builtins, "open", _fail_restore_write)
    monkeypatch.setattr(promotion_mod.repos, "record_promotion", _fail_record)

    with pytest.raises(RuntimeError, match="审计提交失败"):
        promotion_mod.promote_agent(
            conn_factory=governance_env.app.state.conn_factory,
            agent_registry=governance_env.app.state.agent_registry,
            scope_registry=governance_env.app.state.scope_registry,
            agent_id="governed_agent",
            to_maturity="L1",
            eval_run_id=run["id"],
            confirmations={"exception_paths_handled": True},
            signer=_server_cli_signer(),
            attestation_records=(
                governance_env.app.state.promotion_attestation_records
            ),
        )

    assert yaml_write_count == 2
    faults = governance_env.app.state.promotion_attestation_records
    assert len(faults) == 1
    assert faults[0]["agent_id"] == "governed_agent"
    assert faults[0]["reason"] == "promotion-rollback-failed"
    conn = governance_env.app.state.conn_factory()
    try:
        persistent_fault = repos.get_promotion_attestation_fault(conn)
    finally:
        conn.close()
    assert persistent_fault is not None
    assert json.loads(persistent_fault["detail"])["reason"] == (
        "promotion-rollback-failed"
    )
    # 模拟原 CLI 进程退出/另一 API 进程无该内存 list：共享 DB latch 仍令 health 红。
    governance_env.app.state.promotion_attestation_records = []
    health = governance_env.client.get("/api/health").json()
    assert health["promotion_attestation_ok"] is False
    assert health["promotion_attestation_rejected_count"] == 1


def test_promotion_requires_persistent_pending_latch_before_disk_write(
    governance_env: GovernanceEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """共享 DB 只读时必须在首次 YAML 手术前失败。

    若等提交/回滚失败后才尝试写 fault latch，同一个只读故障会令 latch 也写不进，
    磁盘却已经进入过 L1 半提交窗口。
    """

    from backend.app.governance import promotion as promotion_mod

    run = _run_eval(governance_env)
    yaml_path = governance_env.governed_dir / "agent.yaml"
    yaml_before = yaml_path.read_text(encoding="utf-8")
    probe = governance_env.app.state.conn_factory()
    try:
        db_path = Path(probe.execute("PRAGMA database_list").fetchone()["file"])
    finally:
        probe.close()

    def _read_only_conn_factory() -> sqlite3.Connection:
        conn = sqlite3.connect(
            f"file:{db_path}?mode=ro",
            uri=True,
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    original_open = builtins.open
    yaml_write_count = 0

    def _count_yaml_writes(file: Any, *args: Any, **kwargs: Any):
        nonlocal yaml_write_count
        mode = args[0] if args else kwargs.get("mode", "r")
        candidate = Path(file) if isinstance(file, (str, Path)) else None
        if candidate == yaml_path and mode == "w":
            yaml_write_count += 1
        return original_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _count_yaml_writes)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        promotion_mod.promote_agent(
            conn_factory=_read_only_conn_factory,
            agent_registry=governance_env.app.state.agent_registry,
            scope_registry=governance_env.app.state.scope_registry,
            agent_id="governed_agent",
            to_maturity="L1",
            eval_run_id=run["id"],
            confirmations={"exception_paths_handled": True},
            signer=_server_cli_signer(),
            attestation_records=[],
        )

    assert yaml_write_count == 0
    assert yaml_path.read_text(encoding="utf-8") == yaml_before
    assert governance_env.client.get(
        "/api/agents/governed_agent/promotions"
    ).json() == []


def test_stale_registry_cannot_repeat_promotion_after_latch_aba(
    governance_env: GovernanceEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """两个进程各持一份 L0 registry：B 在 latch 前暂停，A 完成并清 latch；
    B 随后虽能重新拿到同一 latch，也必须在首次触盘前用新鲜磁盘+DB 拒绝。
    """

    from backend.app.governance import promotion as promotion_mod

    run = _run_eval(governance_env)
    conn = governance_env.app.state.conn_factory()
    try:
        repos.record_promotion(
            conn,
            agent_id="governed_agent",
            agent_version="0.1.0",
            from_maturity="L0",
            to_maturity="L1",
            eval_run_id=run["id"],
            checks={"historical": {"ok": True}},
            confirmations={"exception_paths_handled": True},
            signer=_server_cli_signer("历史签发人"),
        )
        baseline_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM promotions
            WHERE agent_id = 'governed_agent' AND agent_version = '0.1.0'
              AND from_maturity = 'L0' AND to_maturity = 'L1'
            """
        ).fetchone()[0]
        db_maturity = conn.execute(
            "SELECT maturity FROM agents WHERE id = 'governed_agent'"
        ).fetchone()["maturity"]
    finally:
        conn.close()
    assert baseline_count == 1
    assert db_maturity == "L0"

    live_registry = governance_env.app.state.agent_registry
    stale_registry = type(live_registry)(
        live_registry.agents_dir,
        live_registry.schema_path,
    )
    stale_registry.scan()
    assert stale_registry.get("governed_agent")["maturity"] == "L0"

    stale_entered_latch = threading.Event()
    allow_stale_latch = threading.Event()
    original_latch = promotion_mod.repos.record_promotion_attestation_fault
    original_open = builtins.open
    stale_disk_writes: list[tuple[str, str]] = []

    def _block_stale_latch(*args: Any, **kwargs: Any):
        if threading.current_thread().name == "stale-promoter":
            stale_entered_latch.set()
            if allow_stale_latch.wait(timeout=5.0) is not True:
                raise TimeoutError("测试未及时放行 stale promoter latch")
        return original_latch(*args, **kwargs)

    def _observe_stale_writes(file: Any, *args: Any, **kwargs: Any):
        mode = args[0] if args else kwargs.get("mode", "r")
        candidate = Path(file) if isinstance(file, (str, Path)) else None
        if (
            threading.current_thread().name == "stale-promoter"
            and candidate
            in {
                governance_env.governed_dir / "agent.yaml",
                governance_env.governed_dir / "changelog.md",
            }
            and mode in {"w", "a"}
        ):
            stale_disk_writes.append((candidate.name, mode))
        return original_open(file, *args, **kwargs)

    monkeypatch.setattr(
        promotion_mod.repos,
        "record_promotion_attestation_fault",
        _block_stale_latch,
    )
    monkeypatch.setattr(builtins, "open", _observe_stale_writes)
    stale_result: dict[str, Any] = {}

    def _run_stale_promotion() -> None:
        try:
            stale_result["record"] = promotion_mod._promote_agent_locked(
                conn_factory=governance_env.app.state.conn_factory,
                agent_registry=stale_registry,
                scope_registry=governance_env.app.state.scope_registry,
                agent_id="governed_agent",
                to_maturity="L1",
                eval_run_id=run["id"],
                confirmations={"exception_paths_handled": True},
                signer=_server_cli_signer("B 工程师"),
                attestation_records=[],
            )
        except Exception as exc:  # 线程边界：由主线程断言精确异常
            stale_result["error"] = exc

    stale_thread = threading.Thread(
        target=_run_stale_promotion,
        daemon=True,
        name="stale-promoter",
    )
    stale_thread.start()
    assert stale_entered_latch.wait(timeout=5.0) is True

    response_a = _promote(
        governance_env,
        run["id"],
        confirmations={"exception_paths_handled": True},
    )
    assert response_a.status_code == 200, response_a.text
    yaml_after_a = (
        governance_env.governed_dir / "agent.yaml"
    ).read_text(encoding="utf-8")
    changelog_after_a = (
        governance_env.governed_dir / "changelog.md"
    ).read_text(encoding="utf-8")

    allow_stale_latch.set()
    stale_thread.join(timeout=5.0)
    assert stale_thread.is_alive() is False
    assert isinstance(
        stale_result.get("error"),
        promotion_mod.PromotionRejected,
    )
    assert "record" not in stale_result
    assert stale_disk_writes == []
    assert (
        governance_env.governed_dir / "agent.yaml"
    ).read_text(encoding="utf-8") == yaml_after_a
    assert (
        governance_env.governed_dir / "changelog.md"
    ).read_text(encoding="utf-8") == changelog_after_a

    conn = governance_env.app.state.conn_factory()
    try:
        promotion_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM promotions
            WHERE agent_id = 'governed_agent' AND agent_version = '0.1.0'
              AND from_maturity = 'L0' AND to_maturity = 'L1'
            """
        ).fetchone()[0]
        persistent_fault = repos.get_promotion_attestation_fault(conn)
    finally:
        conn.close()
    assert promotion_count == baseline_count + 1
    assert persistent_fault is None


def test_promotion_rejects_referenced_schema_changed_after_run(
    governance_env: GovernanceEnv,
) -> None:
    """F3：digest 哈希 agent 配置实际引用的 schema 文件——run 后改
    input_schema.json（版本号不动）必须令旧全绿证据失效。"""
    run = _run_eval(governance_env)
    schema_path = governance_env.governed_dir / "input_schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["description"] = "run 后被改"
    schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")

    checks = _rejection_checks(
        _promote(governance_env, run["id"], confirmations={"exception_paths_handled": True})
    )
    assert checks["eval_evidence"]["ok"] is False
    assert "digest" in checks["eval_evidence"]["detail"]


def test_promotion_revalidates_package_bytes_before_publishing_l1(
    governance_env: GovernanceEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """初次 digest 后并发改 prompt，发布边界必须重验并回滚，不能按 id 全豁免。"""

    run = _run_eval(governance_env)
    yaml_path = governance_env.governed_dir / "agent.yaml"
    prompt_path = governance_env.governed_dir / "prompt.md"
    yaml_before = yaml_path.read_text(encoding="utf-8")
    prompt_before = prompt_path.read_text(encoding="utf-8")
    entered_yaml_boundary = threading.Event()
    allow_yaml_read = threading.Event()
    original_open = builtins.open
    blocked_once = False

    def _blocking_open(file: Any, *args: Any, **kwargs: Any):
        nonlocal blocked_once
        mode = args[0] if args else kwargs.get("mode", "r")
        candidate = Path(file) if isinstance(file, (str, Path)) else None
        if (
            blocked_once is False
            and candidate == yaml_path
            and mode == "r"
        ):
            blocked_once = True
            entered_yaml_boundary.set()
            if allow_yaml_read.wait(timeout=5.0) is not True:
                raise TimeoutError("测试未及时放行 YAML 读取")
        return original_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _blocking_open)
    result: dict[str, Any] = {}

    def _request_promotion() -> None:
        result["response"] = _promote(
            governance_env,
            run["id"],
            confirmations={"exception_paths_handled": True},
        )

    request_thread = threading.Thread(target=_request_promotion, daemon=True)
    request_thread.start()
    assert entered_yaml_boundary.wait(timeout=5.0) is True
    prompt_path.write_text(
        prompt_before + "\n并发注入：这段 prompt 未经本次 eval。\n",
        encoding="utf-8",
    )
    allow_yaml_read.set()
    request_thread.join(timeout=5.0)

    assert request_thread.is_alive() is False
    checks = _rejection_checks(result["response"])
    assert checks["eval_evidence"]["ok"] is False
    assert yaml_path.read_text(encoding="utf-8") == yaml_before
    assert prompt_path.read_text(encoding="utf-8") != prompt_before
    assert governance_env.client.get("/api/agents/governed_agent").json()[
        "maturity"
    ] == "L0"
    assert governance_env.client.get(
        "/api/agents/governed_agent/promotions"
    ).json() == []


def test_promotion_publishes_frozen_package_when_live_dir_changes_at_audit_boundary(
    governance_env: GovernanceEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """最终门禁后的并发 A→B 不能令审计 A、Registry/Runtime 却发布活目录 B。"""

    run = _run_eval(governance_env)
    workflow_path = governance_env.governed_dir / "workflow.py"
    marker_path = governance_env.governed_dir / "live_b_executed.marker"
    live_b_source = (
        "from pathlib import Path\n\n"
        "def run(context):\n"
        f"    Path({str(marker_path)!r}).write_text("
        "'live B executed', encoding='utf-8')\n"
        "    return {'status': 'success', 'outputs': []}\n"
    )
    entered_audit_boundary = threading.Event()
    mutation_done = threading.Event()
    real_record_promotion = repos.record_promotion

    def _publish_live_b() -> None:
        if entered_audit_boundary.wait(timeout=5.0) is not True:
            return
        workflow_path.write_text(live_b_source, encoding="utf-8")
        mutation_done.set()

    def _record_after_concurrent_mutation(*args: Any, **kwargs: Any):
        entered_audit_boundary.set()
        if mutation_done.wait(timeout=5.0) is not True:
            raise TimeoutError("测试未及时完成最终门禁后的活目录 A→B 修改")
        return real_record_promotion(*args, **kwargs)

    monkeypatch.setattr(repos, "record_promotion", _record_after_concurrent_mutation)
    writer = threading.Thread(target=_publish_live_b, daemon=True)
    writer.start()

    response = _promote(
        governance_env,
        run["id"],
        confirmations={"exception_paths_handled": True},
    )
    writer.join(timeout=5.0)

    assert writer.is_alive() is False
    assert mutation_done.is_set() is True
    assert response.status_code == 200, response.text
    assert workflow_path.read_text(encoding="utf-8") == live_b_source

    task_id, result = _create_and_execute_user_task(governance_env)
    assert result["status"] == "waiting_review"
    assert marker_path.exists() is False
    assert result["task"]["output_file_ids"]

    package_check = response.json()["checks"]["package_snapshot"]
    assert package_check["ok"] is True
    assert package_check["contract"] == "agent_package_snapshot.v1"
    registry_snapshot = governance_env.app.state.agent_registry.package_snapshot(
        "governed_agent"
    )
    assert registry_snapshot is not None
    assert registry_snapshot.digest == package_check["digest"]
    conn = governance_env.app.state.conn_factory()
    try:
        validation_event = next(
            event
            for event in repos.list_events(conn, task_id)
            if event["event_type"] == "validation_started"
        )
    finally:
        conn.close()
    assert validation_event["payload"]["package_snapshot_digest"] == (
        package_check["digest"]
    )

    conn = governance_env.app.state.conn_factory()
    try:
        database_file = conn.execute("PRAGMA database_list").fetchone()["file"]
    finally:
        conn.close()
    restart_root = governance_env.agents_dir.parent
    restarted_app = create_app(
        agents_dir=governance_env.agents_dir,
        tools_dir=REPO / "tools_impl",
        contracts_dir=REPO / "contracts",
        db_path=Path(database_file),
        uploads_dir=restart_root / "restart-uploads",
        task_runs_dir=restart_root / "restart-task-runs",
    )
    with TestClient(restarted_app) as restarted_client:
        login(restarted_client)
        assert restarted_client.get("/api/agents/governed_agent").status_code == 404
        health = restarted_client.get("/api/health").json()
        assert health["promotion_attestation_axis"] is True
        assert health["promotion_attestation_ok"] is False
        assert health["promotion_attestation_rejected_count"] >= 1


def test_eval_run_invalidated_when_package_changes_during_run(
    governance_env: GovernanceEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F3：执行期间评测集/包内容变化 → run 收口 status='error'，digest 置空，
    不构成晋升证据（起终点指纹复核接线的确定性验证）。"""
    from backend.app.governance import eval_runner as runner_mod

    real_compute = runner_mod.compute_digest
    calls = {"n": 0}

    def _drifting(*args: Any, **kwargs: Any):
        calls["n"] += 1
        value = real_compute(*args, **kwargs)
        # 调用序：①enqueue 冻结快照（T2/#5）②run 起点 ③run 后复核。仅第三次（后复核）
        # 返回漂移值，模拟「起点采样后、执行期间」内容被改 → 起终点指纹不一致 → 证据作废。
        return f"{value}-drift" if calls["n"] >= 3 else value

    monkeypatch.setattr(runner_mod, "compute_digest", _drifting)
    response = governance_env.client.post(
        "/api/agents/governed_agent/eval-runs", json={}
    )
    assert response.status_code == 202, response.text  # T1：入队 + worker 排空
    run = _drain_eval_run(governance_env, response.json()["id"])
    assert run["status"] == "error"
    assert run["eval_cases_digest"] is None
    assert any("证据作废" in (c.get("detail") or "") for c in run["case_results"])

    checks = _rejection_checks(
        _promote(governance_env, run["id"], confirmations={"exception_paths_handled": True})
    )
    assert checks["eval_evidence"]["ok"] is False


def test_eval_task_reaches_terminal_failed_when_runtime_raises(
    governance_env: GovernanceEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F4：runtime.execute 炸掉时 eval 任务必须终态化 failed，绝不留
    validating/running 非终态孤儿；case 如实记 failed。"""
    from backend.app.runtime.runtime import AgentRuntime

    def _explode(self: Any, task_id: str) -> None:
        raise RuntimeError("注入：执行炸裂")

    # T2/#5：快照执行会克隆 runtime（换快照绑定注册表定位材化包），实例级 patch 不传到
    # 克隆体——patch 类方法让原 runtime 与克隆体的 execute 都注入失败，覆盖真实执行路径。
    monkeypatch.setattr(AgentRuntime, "execute", _explode)
    run = _run_eval(governance_env)
    assert run["failed"] >= 1
    exploded = [c for c in run["case_results"] if "runtime.execute 异常" in (c.get("detail") or "")]
    assert exploded, run["case_results"]
    conn = governance_env.app.state.conn_factory()
    try:
        for item in exploded:
            task = repos.get_task(conn, item["task_id"])
            assert task is not None
            assert task["status"] == "failed"
    finally:
        conn.close()


def test_running_eval_does_not_execute_later_cases_when_fault_arrives_at_claim_begin(
    governance_env: GovernanceEnv,
) -> None:
    """run 已开始后新建 persistent fault：后续 case 可如实 failed，但绝不执行。

    fault 精确插入第二个 case 已 queued、``claim_task`` 的 ``BEGIN IMMEDIATE``
    即将执行之时。若裁决只在事务外预查，或 ``claim_task`` 完全不查 fault，第二个
    case 仍会进入 validating 并调用 runtime.execute，本测试必须稳定 RED。
    """
    from backend.app.governance import eval_runner as runner_mod

    run_id = "eval_fault_after_first_case"
    agent = governance_env.app.state.agent_registry.get("governed_agent")
    assert agent is not None
    conn = governance_env.app.state.conn_factory()
    try:
        repos.create_eval_run(
            conn,
            run_id=run_id,
            agent_id="governed_agent",
            agent_version=str(agent["version"]),
            triggered_by="tester",
            status="running",
        )
    finally:
        conn.close()

    state: dict[str, Any] = {
        "first_executed": False,
        "claim_begin_interposed": False,
        "fault_inserted": False,
        "callback_errors": [],
        "executed_task_ids": [],
    }
    rival = governance_env.app.state.conn_factory()

    class _RecordingRuntime:
        def execute(self, task_id: str) -> dict[str, Any]:
            result = governance_env.app.state.runtime.execute(task_id)
            state["executed_task_ids"].append(task_id)
            if len(state["executed_task_ids"]) == 1:
                state["first_executed"] = True
            return result

    def racing_conn_factory():
        racing_conn = governance_env.app.state.conn_factory()
        queued_transition_seen = False

        def trace(statement: str) -> None:
            nonlocal queued_transition_seen
            if state["first_executed"] is not True:
                return
            normalized = " ".join(statement.upper().split())
            if normalized.startswith("UPDATE TASKS SET STATUS = 'QUEUED'"):
                queued_transition_seen = True
            elif (
                normalized.startswith("BEGIN IMMEDIATE")
                and queued_transition_seen
                and state["claim_begin_interposed"] is False
            ):
                state["claim_begin_interposed"] = True
                try:
                    state["fault_inserted"] = repos.record_promotion_attestation_fault(
                        rival,
                        detail='{"reason":"test-in-flight-eval-case-claim"}',
                    )
                except Exception as exc:  # trace callback 异常会被 sqlite 吞掉
                    state["callback_errors"].append(exc)

        racing_conn.set_trace_callback(trace)
        return racing_conn

    try:
        run = runner_mod.execute_eval_run(
            run_id=run_id,
            conn_factory=racing_conn_factory,
            agent_registry=governance_env.app.state.agent_registry,
            runtime=_RecordingRuntime(),
            uploads_dir=governance_env.app.state.uploads_dir,
            task_runs_dir=governance_env.app.state.task_runs_dir,
        )
    finally:
        rival.close()

    conn = governance_env.app.state.conn_factory()
    try:
        eval_tasks = repos.list_tasks(
            conn, agent_id="governed_agent", origin="eval", limit=20
        )
        persistent_fault = repos.get_promotion_attestation_fault(conn)
    finally:
        conn.close()

    tasks_by_case = {
        task["metadata"]["eval_case_file"]: task
        for task in eval_tasks
        if task["metadata"].get("eval_case_file") in _base_cases()
    }
    results_by_case = {
        result["case_file"]: result
        for result in run["case_results"]
        if result["case_file"] in _base_cases()
    }

    assert state["first_executed"] is True
    assert state["claim_begin_interposed"] is True
    assert state["fault_inserted"] is True
    assert state["callback_errors"] == []
    assert persistent_fault is not None
    assert set(tasks_by_case) == set(_base_cases())
    assert state["executed_task_ids"] == [tasks_by_case["case_001.json"]["id"]]
    assert tasks_by_case["case_001.json"]["status"] != "queued"
    for case_file in ("case_002.json", "case_003.json"):
        assert tasks_by_case[case_file]["status"] == "queued"
        assert results_by_case[case_file]["verdict"] == "failed"
        assert "认领失败" in results_by_case[case_file]["detail"]
    assert run["status"] == "completed"
    assert run["passed"] == 1
    assert run["failed"] == 2


def test_rejected_agents_not_resurrected_by_promotion(
    tmp_path: Path,
) -> None:
    """F1/P1-2：启动期被静态门拒绝的 Agent，任意其他 Agent 晋升触发的
    重扫（影子+全门对账+原子发布）后仍必须不可见。"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    shutil.copytree(REPO / "agents" / "hello_agent", agents_dir / "hello_agent")
    shutil.copytree(REPO / "agents" / "hello_agent", agents_dir / "governed_agent")
    shutil.copytree(REPO / "agents" / "hello_agent", agents_dir / "violator_agent")
    shutil.copytree(REPO / "agents" / "hello_agent", agents_dir / "unattested_agent")

    gov_yaml = agents_dir / "governed_agent" / "agent.yaml"
    gov_yaml.write_text(
        gov_yaml.read_text(encoding="utf-8")
        .replace("id: hello_agent", "id: governed_agent")
        .replace("requires_human_review: false", "requires_human_review: true"),
        encoding="utf-8",
    )
    vio_yaml = agents_dir / "violator_agent" / "agent.yaml"
    vio_text = (
        vio_yaml.read_text(encoding="utf-8")
        .replace("id: hello_agent", "id: violator_agent")
        .replace("  enabled: false\n  scopes: []", '  enabled: true\n  scopes:\n    - ghost_scope')
    )
    assert "ghost_scope" in vio_text
    vio_yaml.write_text(vio_text, encoding="utf-8")
    unattested_yaml = agents_dir / "unattested_agent" / "agent.yaml"
    unattested_yaml.write_text(
        unattested_yaml.read_text(encoding="utf-8")
        .replace("id: hello_agent", "id: unattested_agent")
        .replace("maturity: L0", "maturity: L1"),
        encoding="utf-8",
    )
    _write_eval_cases(agents_dir, _base_cases())

    db_path = tmp_path / "flai_os.db"
    app = create_app(
        agents_dir=agents_dir,
        tools_dir=REPO / "tools_impl",
        contracts_dir=REPO / "contracts",
        db_path=db_path,
        uploads_dir=tmp_path / "uploads",
        task_runs_dir=tmp_path / "task_runs",
    )
    with TestClient(app) as client:
        seed_and_login(client, db_path)
        # 启动对账已注销 scope 违规者与无 promotion 证明的 L1。
        ids = {a["id"] for a in client.get("/api/agents").json()}
        assert "violator_agent" not in ids
        assert "unattested_agent" not in ids
        env = GovernanceEnv(client=client, app=app, agents_dir=agents_dir)
        run = _run_eval(env)
        response = _promote(env, run["id"], confirmations={"exception_paths_handled": True})
        assert response.status_code == 200, response.text
        # 晋升重扫后：两个被拒者都不能复活，唯独本次已过门的 governed 可在
        # 审计行同事务落库前作为明确的 in-flight 例外进入影子 registry。
        ids_after = {a["id"] for a in client.get("/api/agents").json()}
        assert "violator_agent" not in ids_after
        assert "unattested_agent" not in ids_after
        assert client.get("/api/agents/violator_agent").status_code == 404
        assert client.get("/api/agents/unattested_agent").status_code == 404
        assert client.get("/api/agents/governed_agent").json()["maturity"] == "L1"


def test_inflight_l1_is_not_published_before_audit_commit(
    governance_env: GovernanceEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """卡住真正 COMMIT：提交前并发读者只能看见 L0 且审计行不可见。"""

    run = _run_eval(governance_env)
    entered_commit = threading.Event()
    allow_commit = threading.Event()
    original_conn_factory = governance_env.app.state.conn_factory

    class _CommitBlockingConnection:
        def __init__(self, real: Any) -> None:
            self._real = real
            self._contains_promotion_insert = False

        def execute(self, sql: str, *args: Any, **kwargs: Any):
            normalized = " ".join(sql.split()).upper()
            if normalized.startswith("INSERT INTO PROMOTIONS"):
                self._contains_promotion_insert = True
            if normalized == "COMMIT" and self._contains_promotion_insert is True:
                entered_commit.set()
                if allow_commit.wait(timeout=5.0) is not True:
                    raise TimeoutError("测试未及时放行 promotion COMMIT")
            return self._real.execute(sql, *args, **kwargs)

        def __getattr__(self, name: str) -> Any:
            return getattr(self._real, name)

    def _blocking_conn_factory() -> _CommitBlockingConnection:
        return _CommitBlockingConnection(original_conn_factory())

    monkeypatch.setattr(
        governance_env.app.state,
        "conn_factory",
        _blocking_conn_factory,
    )
    result: dict[str, Any] = {}

    def _request_promotion() -> None:
        result["response"] = _promote(
            governance_env,
            run["id"],
            confirmations={"exception_paths_handled": True},
        )

    request_thread = threading.Thread(target=_request_promotion, daemon=True)
    request_thread.start()
    assert entered_commit.wait(timeout=5.0) is True
    try:
        observed = governance_env.client.get("/api/agents/governed_agent")
        assert observed.status_code == 200
        assert observed.json()["maturity"] == "L0"
        assert governance_env.client.get(
            "/api/agents/governed_agent/promotions"
        ).json() == []
    finally:
        allow_commit.set()
        request_thread.join(timeout=5.0)

    assert request_thread.is_alive() is False
    response = result["response"]
    assert response.status_code == 200, response.text
    assert governance_env.client.get("/api/agents/governed_agent").json()[
        "maturity"
    ] == "L1"
    assert len(
        governance_env.client.get(
            "/api/agents/governed_agent/promotions"
        ).json()
    ) == 1


def test_runtime_attestation_rejection_updates_health(
    governance_env: GovernanceEnv,
) -> None:
    """运行期重扫拒载必须跨进程 sticky-fail，且 worker 不得继续 claim。"""

    from backend.app.jobs.runner import JobRunner

    initial_health = governance_env.client.get("/api/health").json()
    assert initial_health["promotion_attestation_ok"] is True
    assert initial_health["promotion_attestation_rejected_count"] == 0

    drifted_yaml = governance_env.agents_dir / "hello_agent" / "agent.yaml"
    yaml_text = drifted_yaml.read_text(encoding="utf-8")
    assert yaml_text.count("maturity: L0") == 1
    drifted_yaml.write_text(
        yaml_text.replace("maturity: L0", "maturity: L1"),
        encoding="utf-8",
    )

    run = _run_eval(governance_env)
    queued = governance_env.client.post(
        "/api/tasks",
        json={
            "agent_id": "governed_agent",
            "inputs": {"name": "持久故障后不得 claim"},
        },
    )
    assert queued.status_code == 200, queued.text
    assert queued.json()["status"] == "queued"
    queued_task_id = queued.json()["id"]

    response = _promote(
        governance_env,
        run["id"],
        confirmations={"exception_paths_handled": True},
    )
    checks = _rejection_checks(response)
    assert checks["runtime_attestation"]["ok"] is False
    assert governance_env.client.get("/api/agents/hello_agent").status_code == 404
    assert governance_env.client.get("/api/agents/governed_agent").json()[
        "maturity"
    ] == "L0"
    assert governance_env.client.get(
        "/api/agents/governed_agent/promotions"
    ).json() == []

    health = governance_env.client.get("/api/health").json()
    assert health["promotion_attestation_ok"] is False
    assert health["promotion_attestation_rejected_count"] == 1

    conn = governance_env.app.state.conn_factory()
    try:
        persistent_fault = repos.get_promotion_attestation_fault(conn)
    finally:
        conn.close()
    assert persistent_fault is not None
    assert json.loads(persistent_fault["detail"])["reason"] == (
        "promotion-runtime-attestation-rejected"
    )

    # 模拟独立 worker/API 进程没有本进程内 rejection list；共享 DB 故障仍须
    # 令 health/readyz 红，并在 claim 之前挡住已排队工作。
    governance_env.app.state.promotion_attestation_records = []
    cross_process_health = governance_env.client.get("/api/health").json()
    assert cross_process_health["promotion_attestation_ok"] is False
    assert cross_process_health["promotion_attestation_rejected_count"] == 1
    readyz = governance_env.client.get("/api/readyz")
    assert readyz.status_code == 503
    assert readyz.json()["worker"]["reason"] == (
        "persistent_promotion_attestation_fault"
    )

    independent_worker = JobRunner(
        governance_env.app.state.runtime,
        governance_env.app.state.conn_factory,
        promotion_attestation_records=[],
    )
    assert independent_worker.run_once() is False
    queued_after = governance_env.client.get(
        f"/api/tasks/{queued_task_id}"
    ).json()
    assert queued_after["status"] == "queued"


def test_runtime_attestation_fault_update_failure_preserves_pending_latch(
    governance_env: GovernanceEnv,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """持久故障升级失败时，补偿成功也不得把原 pending latch 清成绿。"""

    drifted_yaml = governance_env.agents_dir / "hello_agent" / "agent.yaml"
    drifted_yaml.write_text(
        drifted_yaml.read_text(encoding="utf-8").replace(
            "maturity: L0",
            "maturity: L1",
        ),
        encoding="utf-8",
    )
    run = _run_eval(governance_env)

    monkeypatch.setattr(
        repos,
        "update_promotion_attestation_fault",
        lambda *args, **kwargs: False,
    )
    checks = _rejection_checks(
        _promote(
            governance_env,
            run["id"],
            confirmations={"exception_paths_handled": True},
        )
    )
    assert checks["runtime_attestation"]["ok"] is False

    governance_env.app.state.promotion_attestation_records = []
    conn = governance_env.app.state.conn_factory()
    try:
        persistent_fault = repos.get_promotion_attestation_fault(conn)
    finally:
        conn.close()
    assert persistent_fault is not None
    assert json.loads(persistent_fault["detail"])["reason"] == (
        "promotion-operation-pending"
    )
    assert governance_env.client.get("/api/health").json()[
        "promotion_attestation_ok"
    ] is False
    readyz = governance_env.client.get("/api/readyz")
    assert readyz.status_code == 503
    assert readyz.json()["worker"]["reason"] == (
        "persistent_promotion_attestation_fault"
    )


def test_restore_rescan_rejection_persists_fault_before_latch_clear(
    governance_env: GovernanceEnv,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """首次重扫干净、补偿重扫才拒载时，也必须跨进程闭锁。"""

    from backend.app.governance import promotion as promotion_mod

    run = _run_eval(governance_env)
    drifted_yaml = governance_env.agents_dir / "hello_agent" / "agent.yaml"

    def _drift_then_fail_record(*args: Any, **kwargs: Any) -> None:
        drifted_yaml.write_text(
            drifted_yaml.read_text(encoding="utf-8").replace(
                "maturity: L0",
                "maturity: L1",
            ),
            encoding="utf-8",
        )
        raise RuntimeError("注入：审计提交失败后出现运行期拒载")

    monkeypatch.setattr(
        promotion_mod.repos,
        "record_promotion",
        _drift_then_fail_record,
    )
    with pytest.raises(RuntimeError, match="审计提交失败后出现运行期拒载"):
        promotion_mod.promote_agent(
            conn_factory=governance_env.app.state.conn_factory,
            agent_registry=governance_env.app.state.agent_registry,
            scope_registry=governance_env.app.state.scope_registry,
            agent_id="governed_agent",
            to_maturity="L1",
            eval_run_id=run["id"],
            confirmations={"exception_paths_handled": True},
            signer=_server_cli_signer(),
            attestation_records=(
                governance_env.app.state.promotion_attestation_records
            ),
        )

    governance_env.app.state.promotion_attestation_records = []
    conn = governance_env.app.state.conn_factory()
    try:
        persistent_fault = repos.get_promotion_attestation_fault(conn)
    finally:
        conn.close()
    assert persistent_fault is not None
    assert json.loads(persistent_fault["detail"])["reason"] == (
        "promotion-runtime-attestation-rejected"
    )
    assert governance_env.client.get("/api/agents/governed_agent").json()[
        "maturity"
    ] == "L0"
    assert governance_env.client.get(
        "/api/agents/governed_agent/promotions"
    ).json() == []
    assert governance_env.client.get("/api/health").json()[
        "promotion_attestation_ok"
    ] is False
    readyz = governance_env.client.get("/api/readyz")
    assert readyz.status_code == 503
    assert readyz.json()["worker"]["reason"] == (
        "persistent_promotion_attestation_fault"
    )


def test_digest_covers_custom_named_schema(tmp_path: Path) -> None:
    """F3 残余：digest 必须哈希 agent 配置**实际引用**的 schema 文件名——
    用 custom_input.json（非默认名）建包，run 后改它，旧全绿证据必须失效。
    （默认名测试对写死默认名的旧实现也会绿，咬不住这条。）"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    shutil.copytree(REPO / "agents" / "hello_agent", agents_dir / "hello_agent")
    shutil.copytree(REPO / "agents" / "hello_agent", agents_dir / "governed_agent")
    gov = agents_dir / "governed_agent"
    # registry 强制件要求 input_schema.json 在场；runtime 却读配置名——custom
    # 与默认名共存、配置指向 custom，正是「改 custom 逃出旧指纹」的攻击形态
    shutil.copyfile(gov / "input_schema.json", gov / "custom_input.json")
    yaml_path = gov / "agent.yaml"
    yaml_text = (
        yaml_path.read_text(encoding="utf-8")
        .replace("id: hello_agent", "id: governed_agent")
        .replace("requires_human_review: false", "requires_human_review: true")
        .replace("schema: input_schema.json", "schema: custom_input.json")
    )
    assert "custom_input.json" in yaml_text
    yaml_path.write_text(yaml_text, encoding="utf-8")
    _write_eval_cases(agents_dir, _base_cases())

    db_path = tmp_path / "flai_os.db"
    app = create_app(
        agents_dir=agents_dir,
        tools_dir=REPO / "tools_impl",
        contracts_dir=REPO / "contracts",
        db_path=db_path,
        uploads_dir=tmp_path / "uploads",
        task_runs_dir=tmp_path / "task_runs",
    )
    with TestClient(app) as client:
        seed_and_login(client, db_path)
        env = GovernanceEnv(client=client, app=app, agents_dir=agents_dir)
        run = _run_eval(env)
        assert run["status"] == "completed" and run["failed"] == 0

        schema_path = gov / "custom_input.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema["description"] = "run 后被改（自定义名）"
        schema_path.write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")

        checks = _rejection_checks(
            _promote(env, run["id"], confirmations={"exception_paths_handled": True})
        )
        assert checks["eval_evidence"]["ok"] is False
        assert "digest" in checks["eval_evidence"]["detail"]


def test_eval_run_error_when_post_run_recheck_raises(
    governance_env: GovernanceEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F3 残余：终点复核自身抛异常（并发删除/权限）→ run 收口 status='error'
    （证据作废），绝不 500 留永久 running 僵尸。"""
    from backend.app.governance import eval_runner as runner_mod

    real_load = runner_mod.load_eval_cases
    calls = {"n": 0}

    def _flaky(pkg_dir: Path):
        calls["n"] += 1
        if calls["n"] >= 2:  # 第二次=终点复核
            raise OSError("注入：复核期目录不可读")
        return real_load(pkg_dir)

    monkeypatch.setattr(runner_mod, "load_eval_cases", _flaky)
    response = governance_env.client.post(
        "/api/agents/governed_agent/eval-runs", json={}
    )
    assert response.status_code == 202, response.text  # T1：入队 + worker 排空
    run = _drain_eval_run(governance_env, response.json()["id"])
    assert run["status"] == "error"
    assert run["eval_cases_digest"] is None
    conn = governance_env.app.state.conn_factory()
    try:
        row = conn.execute(
            "SELECT status FROM eval_runs WHERE id = ?", (run["id"],)
        ).fetchone()
        assert row["status"] == "error"
    finally:
        conn.close()
