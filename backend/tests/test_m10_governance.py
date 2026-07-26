"""M10 治理闭环的 ADR-0018 红线测试。"""

from __future__ import annotations

import json
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

from conftest import TEST_DISPLAY_NAME, seed_and_login

from backend.app.main import create_app
from backend.app.storage import repos


REPO = Path(__file__).resolve().parents[2]
_MISSING = object()


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
) -> tuple[str, dict[str, Any]]:
    created = env.client.post(
        "/api/tasks",
        json={
            "agent_id": "governed_agent",
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
        raw_checks = conn.execute(
            "SELECT checks_json FROM promotions WHERE id = ?",
            (records[0]["id"],),
        ).fetchone()["checks_json"]
    finally:
        conn.close()
    assert "平台级提供" in raw_checks


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


def test_promotion_rejects_client_confirmed_by_and_derives_session_identity(
    governance_env: GovernanceEnv,
) -> None:
    """confirmed_by 已删除：显式发送字段 422；省略时由会话身份记名。"""
    run = _run_eval(governance_env)

    forged = governance_env.client.post(
        "/api/agents/governed_agent/promote",
        json={
            "to_maturity": "L1",
            "eval_run_id": run["id"],
            "confirmations": {"exception_paths_handled": True},
            "confirmed_by": "",
        },
    )
    assert forged.status_code == 422

    honest = _promote(
        governance_env,
        run["id"],
        confirmations={"exception_paths_handled": True},
    )
    assert honest.status_code == 200, honest.text
    assert honest.json()["confirmed_by"] == TEST_DISPLAY_NAME


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
            confirmed_by="王工",
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
    """审计事务提交前，任何并发读者都只能看见原 L0 活表。"""

    run = _run_eval(governance_env)
    entered_record = threading.Event()
    allow_record = threading.Event()
    original_record = repos.record_promotion

    def _blocked_record(*args: Any, **kwargs: Any) -> dict[str, Any]:
        entered_record.set()
        if allow_record.wait(timeout=5.0) is not True:
            raise TimeoutError("测试未及时放行 promotion 审计提交")
        return original_record(*args, **kwargs)

    monkeypatch.setattr(repos, "record_promotion", _blocked_record)
    result: dict[str, Any] = {}

    def _request_promotion() -> None:
        result["response"] = _promote(
            governance_env,
            run["id"],
            confirmations={"exception_paths_handled": True},
        )

    request_thread = threading.Thread(target=_request_promotion, daemon=True)
    request_thread.start()
    assert entered_record.wait(timeout=5.0) is True
    try:
        observed = governance_env.client.get("/api/agents/governed_agent")
        assert observed.status_code == 200
        assert observed.json()["maturity"] == "L0"
    finally:
        allow_record.set()
        request_thread.join(timeout=5.0)

    assert request_thread.is_alive() is False
    response = result["response"]
    assert response.status_code == 200, response.text
    assert governance_env.client.get("/api/agents/governed_agent").json()[
        "maturity"
    ] == "L1"


def test_runtime_attestation_rejection_updates_health(
    governance_env: GovernanceEnv,
) -> None:
    """启动后出现的磁盘漂移必须在下一次重扫令 health sticky-fail。"""

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
    response = _promote(
        governance_env,
        run["id"],
        confirmations={"exception_paths_handled": True},
    )
    assert response.status_code == 200, response.text
    assert governance_env.client.get("/api/agents/hello_agent").status_code == 404

    health = governance_env.client.get("/api/health").json()
    assert health["promotion_attestation_ok"] is False
    assert health["promotion_attestation_rejected_count"] == 1


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
