"""协作运行时 resolver（§3.3）+ E2E 三链 + tamper T1-T6。

resolver 是任务状态的纯确定性函数——大部分 tamper 在 resolver 层直接操纵上游状态测，
无需真实 LLM（fleet 无确定性+review-gated agent）。人签闸（T1）测的是 resolver 把
waiting_review 当"未就绪"；"waiting_review→completed 只人工"由状态机保证（他处已测）。

- T1 人签闸：上游 waiting_review → 下游不入队；上游 completed → 下游入队。
- T2 失败传播：上游 failed/cancelled → 下游 created→cancelled(reason=upstream_failed)。
- T3 污点合成：sensitive 上游产物经管道入下游 input → 下游派生 sensitive。
- T5 resolver 确定性：一趟 resolve 前后 model_calls 行数不变（无 LLM）。
- T6 绑定收口：只拷 depends_on 内上游的 output，不盗其他任务产物。
主链/失败链 E2E 用真实 runtime + hello_agent（确定性）跑全程。
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from backend.app.jobs.runner import JobRunner, resolve_dependencies_once
from backend.app.model_gateway.gateway import ModelGateway
from backend.app.runtime.registry import AgentRegistry
from backend.app.runtime.runtime import AgentRuntime, _task_input_classification
from backend.app.storage import repos
from backend.app.storage.db import get_conn, init_db
from backend.app.tools.registry import ToolRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]

_PATHS = {
    "waiting_review": ["queued", "validating", "running", "waiting_review"],
    "completed_reviewed": ["queued", "validating", "running", "waiting_review", "completed"],
    "completed_auto": ["queued", "validating", "running", "analyzing", "completed"],
    "failed": ["queued", "validating", "failed"],
    "cancelled": ["cancelled"],
}


@pytest.fixture()
def dbf(tmp_path):
    db_path = tmp_path / "flai_os.db"
    init_db(db_path)
    return lambda: get_conn(db_path)


def _mk(conn, task_id, *, depends_on=None, inputs=None):
    return repos.create_task(
        conn, task_id=task_id, agent_id="hello_agent", agent_version="0.1.0",
        name=task_id, created_by="tester", inputs=inputs or {}, input_file_ids=[], metadata={},
        depends_on=depends_on,
    )


def _drive(conn, task_id, key):
    for s in _PATHS[key]:
        repos.set_task_status(conn, task_id, s)


def _attach_output(conn, task_id, *, classification="internal", name="out.txt"):
    fid = str(uuid.uuid4())
    repos.create_file(
        conn, file_id=fid, task_id=task_id, kind="output", filename=name,
        path=f"/tmp/{fid}_{name}", size_bytes=1, sha256="a" * 64, classification=classification,
    )
    task = repos.get_task(conn, task_id)
    repos.set_task_outputs(conn, task_id, (task["output_file_ids"] or []) + [fid])
    return fid


# ── 基本机制：上游全完成 → 管道 + 入队 ─────────────────────────────────────

def test_enqueue_when_all_upstream_completed(dbf):
    conn = dbf()
    try:
        _mk(conn, "up")
        f1 = _attach_output(conn, "up", name="a.txt")
        _drive(conn, "up", "completed_reviewed")
        _mk(conn, "down", depends_on=["up"])
        assert repos.get_task(conn, "down")["status"] == "created"
    finally:
        conn.close()

    advanced = resolve_dependencies_once(dbf)
    assert advanced == 1

    conn = dbf()
    try:
        down = repos.get_task(conn, "down")
        assert down["status"] == "queued"
        assert f1 in down["input_file_ids"]  # 上游产物已管道入下游 input
    finally:
        conn.close()


# ── T1 人签闸：上游 waiting_review → 不入队；completed → 入队 ────────────────

def test_T1_waiting_review_upstream_blocks_then_completed_releases(dbf):
    conn = dbf()
    try:
        _mk(conn, "up")
        _attach_output(conn, "up")
        _drive(conn, "up", "waiting_review")  # 停在人签闸
        _mk(conn, "down", depends_on=["up"])
    finally:
        conn.close()

    assert resolve_dependencies_once(dbf) == 0
    conn = dbf()
    try:
        assert repos.get_task(conn, "down")["status"] == "created"  # 未签 → 下游卡住
        repos.set_task_status(conn, "up", "completed")  # 模拟人工放行 waiting_review→completed
    finally:
        conn.close()

    assert resolve_dependencies_once(dbf) == 1
    conn = dbf()
    try:
        assert repos.get_task(conn, "down")["status"] == "queued"  # 签后 → 下游就绪
    finally:
        conn.close()


# ── T2 失败传播：上游 failed/cancelled → 下游级联 cancelled ─────────────────

@pytest.mark.parametrize("upstream_end", ["failed", "cancelled"])
def test_T2_failed_upstream_cancels_downstream(dbf, upstream_end):
    conn = dbf()
    try:
        _mk(conn, "up")
        _drive(conn, "up", upstream_end)
        _mk(conn, "down", depends_on=["up"])
    finally:
        conn.close()

    assert resolve_dependencies_once(dbf) == 1
    conn = dbf()
    try:
        down = repos.get_task(conn, "down")
        assert down["status"] == "cancelled"  # fail-closed：绝不在失败上游上执行
        events = repos.list_events(conn, "down")
        cancel_ev = [e for e in events if e["event_type"] == "task_cancelled"]
        assert cancel_ev and cancel_ev[0]["payload"].get("reason") == "upstream_failed"
    finally:
        conn.close()


# ── T3 污点合成：sensitive 上游产物经管道 → 下游派生 sensitive ──────────────

def test_T3_taint_composes_through_pipe(dbf):
    conn = dbf()
    try:
        _mk(conn, "up")
        _attach_output(conn, "up", classification="sensitive", name="secret.csv")
        _drive(conn, "up", "completed_reviewed")
        _mk(conn, "down", depends_on=["up"])
    finally:
        conn.close()

    resolve_dependencies_once(dbf)
    conn = dbf()
    try:
        down = repos.get_task(conn, "down")
        assert down["status"] == "queued"
        # resolver 不写 data_classification；执行期既有派生读 input 文件污点得 sensitive
        assert _task_input_classification(conn, down) == "sensitive"
    finally:
        conn.close()


# ── T5 resolver 确定性：无 model_gateway 调用（model_calls 行数不变）───────

def test_T5_resolver_makes_no_model_calls(dbf):
    conn = dbf()
    try:
        _mk(conn, "up")
        _attach_output(conn, "up")
        _drive(conn, "up", "completed_reviewed")
        _mk(conn, "down", depends_on=["up"])
        before = conn.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0]
    finally:
        conn.close()

    resolve_dependencies_once(dbf)
    conn = dbf()
    try:
        after = conn.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0]
        assert after == before  # resolver 是纯确定性，绝不调 LLM
    finally:
        conn.close()


# ── T6 绑定收口：只拷 depends_on 内上游产物，不盗其他任务 ───────────────────

def test_T6_only_pipes_declared_upstream_outputs(dbf):
    conn = dbf()
    try:
        _mk(conn, "up_a")
        f_a = _attach_output(conn, "up_a", name="a.txt")
        _drive(conn, "up_a", "completed_reviewed")
        _mk(conn, "up_c")  # 无关的第三方任务
        f_c = _attach_output(conn, "up_c", name="c.txt")
        _drive(conn, "up_c", "completed_reviewed")
        _mk(conn, "down", depends_on=["up_a"])  # 只依赖 up_a
    finally:
        conn.close()

    resolve_dependencies_once(dbf)
    conn = dbf()
    try:
        down = repos.get_task(conn, "down")
        assert f_a in down["input_file_ids"]      # 声明的上游产物拷入
        assert f_c not in down["input_file_ids"]  # 未声明的第三方产物绝不盗
    finally:
        conn.close()


# ── 缺失上游（无删除 API，防御性）→ fail-closed cancel ─────────────────────

def test_missing_upstream_cancels_fail_closed(dbf):
    conn = dbf()
    try:
        _mk(conn, "down", depends_on=["ghost_never_existed"])
    finally:
        conn.close()

    resolve_dependencies_once(dbf)
    conn = dbf()
    try:
        assert repos.get_task(conn, "down")["status"] == "cancelled"
    finally:
        conn.close()


# ── E2E 主链：真实 runtime 跑 A→B 全程 ─────────────────────────────────────

@pytest.fixture()
def runtime_env(tmp_path):
    db_path = tmp_path / "flai_os.db"
    init_db(db_path)
    agent_registry = AgentRegistry(REPO_ROOT / "agents", REPO_ROOT / "contracts" / "agent.schema.json")
    agent_registry.scan()
    tool_registry = ToolRegistry(REPO_ROOT / "tools_impl", REPO_ROOT / "contracts" / "tool.schema.json")
    tool_registry.scan()
    conn = get_conn(db_path)
    try:
        agent_registry.sync_to_db(conn)
    finally:
        conn.close()

    def conn_factory():
        return get_conn(db_path)

    model_gateway = ModelGateway(
        REPO_ROOT / "backend" / "app" / "model_gateway" / "profiles.yaml", conn_factory=conn_factory
    )
    runtime = AgentRuntime(
        agent_registry, tool_registry, model_gateway, conn_factory, tmp_path / "task_runs"
    )
    return {"conn_factory": conn_factory, "runtime": runtime}


def test_E2E_main_chain_a_then_b(runtime_env):
    """A(hello) 跑完 → resolver 入队 B(hello, depends_on A) → B 跑完。全程真实 runtime。"""
    cf = runtime_env["conn_factory"]
    runner = JobRunner(runtime_env["runtime"], cf)

    conn = cf()
    try:
        _mk(conn, "chain_a", inputs={"name": "上游"})
        repos.set_task_status(conn, "chain_a", "queued")
        _mk(conn, "chain_b", depends_on=["chain_a"], inputs={"name": "下游"})
    finally:
        conn.close()

    # A 执行到完成（hello 确定性、非 review-gated → analyzing→completed）
    assert runner.run_once() is True
    conn = cf()
    try:
        assert repos.get_task(conn, "chain_a")["status"] == "completed"
        assert repos.get_task(conn, "chain_b")["status"] == "created"  # B 仍等
    finally:
        conn.close()

    # resolver 入队 B，再 run_once 拾取执行
    assert resolve_dependencies_once(cf) == 1
    conn = cf()
    try:
        assert repos.get_task(conn, "chain_b")["status"] == "queued"
    finally:
        conn.close()
    assert runner.run_once() is True
    conn = cf()
    try:
        assert repos.get_task(conn, "chain_b")["status"] == "completed"  # 全链跑通
    finally:
        conn.close()


def test_E2E_failure_chain_a_fails_b_cancelled(runtime_env):
    """A failed → resolver 级联 cancel B，B 绝不执行。"""
    cf = runtime_env["conn_factory"]
    conn = cf()
    try:
        _mk(conn, "fail_a")
        _drive(conn, "fail_a", "failed")
        _mk(conn, "fail_b", depends_on=["fail_a"])
    finally:
        conn.close()

    assert resolve_dependencies_once(cf) == 1
    conn = cf()
    try:
        assert repos.get_task(conn, "fail_b")["status"] == "cancelled"
    finally:
        conn.close()
