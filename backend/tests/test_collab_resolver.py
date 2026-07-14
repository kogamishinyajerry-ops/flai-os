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

import hashlib
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


def _mk(conn, task_id, *, depends_on=None, inputs=None, input_file_ids=None):
    return repos.create_task(
        conn, task_id=task_id, agent_id="hello_agent", agent_version="0.1.0",
        name=task_id, created_by="tester", inputs=inputs or {},
        input_file_ids=input_file_ids or [], metadata={},
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


def test_E2E_taint_chain_sensitive_upstream_derives_downstream(runtime_env):
    """E2E 污点链（契约 §6 第三链，真 runtime 全程）：sensitive 输入 → A 真跑派生
    sensitive 产物 → resolver 管道 → B 真 runtime 从 task_runs_dir 开上游 output
    （走 kind-based root 放宽）→ B 执行期派生 sensitive → B 产物亦 sensitive。

    一条链同时压：kind=input 根（A 读 uploads）+ kind=output 根（B 读 task_runs，
    本增量放宽）+ 污点合成（ADR-0025 CAS 落库）+ 分级沿产物传播。下载 403 由既有
    ADR-0025 下载门读此 classification 列覆盖，此处断言承载列=sensitive。"""
    cf = runtime_env["conn_factory"]
    runtime = runtime_env["runtime"]
    runner = JobRunner(runtime, cf)

    # A 的 sensitive 输入：真字节落 uploads_dir/{fid}/input.txt，可过 _open_input_files 校验
    in_fid = str(uuid.uuid4())
    payload = "机密上游输入\n".encode("utf-8")
    in_path = runtime.uploads_dir / in_fid / "input.txt"
    in_path.parent.mkdir(parents=True, exist_ok=True)
    in_path.write_bytes(payload)

    conn = cf()
    try:
        repos.create_file(
            conn, file_id=in_fid, task_id=None, kind="input", filename="input.txt",
            path=str(in_path), size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(), classification="sensitive",
        )
        _mk(conn, "taint_a", inputs={"name": "上游"}, input_file_ids=[in_fid])
        repos.set_task_status(conn, "taint_a", "queued")
        _mk(conn, "taint_b", depends_on=["taint_a"], inputs={"name": "下游"})
    finally:
        conn.close()

    # A 真 runtime 执行 → 读 sensitive 输入派生 sensitive → 产 sensitive output
    assert runner.run_once() is True
    conn = cf()
    try:
        a = repos.get_task(conn, "taint_a")
        assert a["status"] == "completed"
        assert a["data_classification"] == "sensitive"
        a_outputs = a["output_file_ids"]
        assert a_outputs, "A 应产出 hello_output.json"
        assert all(repos.get_file(conn, f)["classification"] == "sensitive" for f in a_outputs)
    finally:
        conn.close()

    # resolver 把 A 的 sensitive output 管道入 B 的 input
    assert resolve_dependencies_once(cf) == 1
    conn = cf()
    try:
        b = repos.get_task(conn, "taint_b")
        assert b["status"] == "queued"
        assert set(a_outputs) <= set(b["input_file_ids"])  # 上游 sensitive 产物已入下游 input
    finally:
        conn.close()

    # B 真 runtime 执行：从 task_runs_dir 开上游 output（kind-based root）→ 派生 sensitive
    assert runner.run_once() is True
    conn = cf()
    try:
        b = repos.get_task(conn, "taint_b")
        assert b["status"] == "completed"
        assert b["data_classification"] == "sensitive"  # 污点经管道跨任务合成
        assert b["output_file_ids"], "B 应产出 hello_output.json"
        assert all(
            repos.get_file(conn, f)["classification"] == "sensitive"
            for f in b["output_file_ids"]
        )  # 分级沿产物继续传播，下载门读此列 → 403
    finally:
        conn.close()


# ── P1-1 消费点 provenance（Codex 增量2审）：output 只能来自 depends_on 声明且 completed 上游 ──

def _real_output(runtime, conn, owner_task, *, name="out.txt", classification="internal"):
    """在 task_runs_dir/{owner}/output/ 落真字节 output 文件并登记，返回 file_id。"""
    out_dir = runtime.task_runs_dir / owner_task / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = f"{owner_task}:{name}\n".encode("utf-8")
    path = out_dir / name
    path.write_bytes(payload)
    fid = str(uuid.uuid4())
    repos.create_file(
        conn, file_id=fid, task_id=owner_task, kind="output", filename=name,
        path=str(path), size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(), classification=classification,
    )
    return fid


def test_provenance_undeclared_output_rejected_at_consume(runtime_env):
    """P1-1 tamper（第一支）：直引非 depends_on 声明的他人 output（模拟旧 API/混版无
    kind guard 的绕过任务）→ 执行期消费点拒 → 任务 failed。拆 provenance 校验 → 绕过
    任务反而 completed。"""
    cf = runtime_env["conn_factory"]
    runtime = runtime_env["runtime"]
    runner = JobRunner(runtime, cf)
    conn = cf()
    try:
        _mk(conn, "producer")
        fid = _real_output(runtime, conn, "producer")
        repos.set_task_outputs(conn, "producer", [fid])
        _drive(conn, "producer", "completed_reviewed")
        # 绕过任务：直塞 producer 的 output 入 input_file_ids，但 depends_on 为空
        _mk(conn, "bypass", inputs={"name": "x"}, input_file_ids=[fid])
        repos.set_task_status(conn, "bypass", "queued")
    finally:
        conn.close()
    runner.run_once()
    conn = cf()
    try:
        assert repos.get_task(conn, "bypass")["status"] == "failed"  # 未声明依赖 → 消费点拒
    finally:
        conn.close()


def test_provenance_uncompleted_upstream_output_rejected(runtime_env):
    """P1-1 tamper（第二支）：output 的 owner 在 depends_on 但停在 waiting_review（未过
    人签闸）→ 消费点拒。防「产物在上游 waiting_review 期已存在被抢先消费」绕人签。"""
    cf = runtime_env["conn_factory"]
    runtime = runtime_env["runtime"]
    runner = JobRunner(runtime, cf)
    conn = cf()
    try:
        _mk(conn, "pending")
        fid = _real_output(runtime, conn, "pending")
        repos.set_task_outputs(conn, "pending", [fid])
        _drive(conn, "pending", "waiting_review")  # 停在人签闸，未 completed
        # consumer 声明依赖 pending（provenance 第一支满足）但手动强推 queued 绕过 resolver
        _mk(conn, "consumer", depends_on=["pending"], inputs={"name": "x"}, input_file_ids=[fid])
        repos.set_task_status(conn, "consumer", "queued")
    finally:
        conn.close()
    runner.run_once()
    conn = cf()
    try:
        assert repos.get_task(conn, "consumer")["status"] == "failed"  # 上游未 completed → 拒
    finally:
        conn.close()


# ── P2-3 input_binding 兑现（Codex 增量2审）：非空 from_tasks 只拷声明的上游产物 ──

def test_input_binding_filters_piped_upstreams(dbf):
    """P2-3 tamper：depends_on=[A,B] + input_binding.from_tasks=[A] → resolver 只拷 A 产物、
    不拷 B（调用方显式排除，含可能的 sensitive）。拆 binding 过滤 → B 产物也被拷入 → RED。"""
    conn = dbf()
    try:
        _mk(conn, "bind_a")
        f_a = _attach_output(conn, "bind_a", name="a.txt")
        _drive(conn, "bind_a", "completed_reviewed")
        _mk(conn, "bind_b")
        f_b = _attach_output(conn, "bind_b", name="b.txt")
        _drive(conn, "bind_b", "completed_reviewed")
        repos.create_task(
            conn, task_id="bind_down", agent_id="hello_agent", agent_version="0.1.0",
            name="bind_down", created_by="tester", inputs={}, input_file_ids=[], metadata={},
            depends_on=["bind_a", "bind_b"], input_binding={"from_tasks": ["bind_a"]},
        )
    finally:
        conn.close()

    assert resolve_dependencies_once(dbf) == 1
    conn = dbf()
    try:
        down = repos.get_task(conn, "bind_down")
        assert down["status"] == "queued"
        assert f_a in down["input_file_ids"]      # 绑定的 A 产物拷入
        assert f_b not in down["input_file_ids"]  # 未绑定的 B 产物不拷（尊重 binding）
    finally:
        conn.close()


# ── R1-2 生产侧管道 id 校验（Codex 增量2审 R1）：非 registered kind=output 属该上游即拒 ──

def test_R1_invalid_piped_output_id_cancels_downstream(dbf):
    """R1-2 tamper：上游 output_file_ids 混入非 registered-output 的 id（如 kind=input，
    模拟 legacy/陈旧行）→ resolver 生产侧 fail-closed 级联取消下游，绝不喂入未注册文件
    绕消费侧 provenance。拆生产侧校验 → 坏 id 被拷入下游 input → 后续消费才炸/绕过。"""
    conn = dbf()
    try:
        _mk(conn, "up")
        bad_fid = str(uuid.uuid4())
        repos.create_file(  # kind=input 却被塞进 up 的 output_file_ids
            conn, file_id=bad_fid, task_id=None, kind="input", filename="wrong.txt",
            path=f"/tmp/{bad_fid}", size_bytes=1, sha256="a" * 64, classification="internal",
        )
        repos.set_task_outputs(conn, "up", [bad_fid])
        _drive(conn, "up", "completed_reviewed")
        _mk(conn, "down", depends_on=["up"])
    finally:
        conn.close()

    assert resolve_dependencies_once(dbf) == 1
    conn = dbf()
    try:
        down = repos.get_task(conn, "down")
        assert down["status"] == "cancelled"  # 生产侧完整性校验拒
        events = repos.list_events(conn, "down")
        assert any(
            e["event_type"] == "task_cancelled"
            and e["payload"].get("reason") == "upstream_output_integrity"
            for e in events
        )
    finally:
        conn.close()


# ── R1-4 未知 kind fail-closed（Codex 增量2审 R1）：非 input/output 记录拒消费 ──

def test_R1_unknown_file_kind_rejected_at_consume(runtime_env):
    """R1-4 tamper：input_file_ids 含 kind 非 input/output 的记录 → 执行期 fail-closed 拒
    （绝不默认当上传件开 uploads_dir）。**真实可开文件落 uploads_dir**（sha256/size 匹配）
    使非空咬合：拆未知 kind 分支（else→uploads_dir）会把它当上传成功开→任务 completed；
    有 fail-closed 时未知 kind 直接拒→failed。"""
    cf = runtime_env["conn_factory"]
    runtime = runtime_env["runtime"]
    runner = JobRunner(runtime, cf)
    weird_fid = str(uuid.uuid4())
    payload = b"weird kind payload\n"
    p = runtime.uploads_dir / weird_fid / "input.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(payload)
    conn = cf()
    try:
        repos.create_file(
            conn, file_id=weird_fid, task_id=None, kind="weird", filename="input.txt",
            path=str(p), size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(), classification="internal",
        )
        _mk(conn, "weird_task", inputs={"name": "x"}, input_file_ids=[weird_fid])
        repos.set_task_status(conn, "weird_task", "queued")
    finally:
        conn.close()
    runner.run_once()
    conn = cf()
    try:
        assert repos.get_task(conn, "weird_task")["status"] == "failed"  # 未知 kind fail-closed
    finally:
        conn.close()
