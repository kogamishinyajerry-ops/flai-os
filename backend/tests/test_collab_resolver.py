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
import json
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
    "completed_reviewed": ["queued", "validating", "running", "waiting_review"],
    "completed_auto": ["queued", "validating", "running", "analyzing", "completed"],
    "failed": ["queued", "validating", "failed"],
    "cancelled": ["cancelled"],
}


def _register_agent_version(conn, agent_id, version="0.1.0", *, profile="none", requires_human_review=None):
    """注册最小 agent_versions manifest（K1 签发见证测试用）。profile='none'=确定性零-LLM
    Agent（其 completed 产物经 task_output_is_signed_off 的 profile=none 支合法放行）；
    profile='reasoning' 建模 LLM 型上游（需另有 review_approved 事件才算签发，否则未签）。
    本 helper 只忠实落库 manifest，不校 §3.6（测试要造违规历史行时正需绕校验）。"""
    manifest = {
        "id": agent_id, "version": version,
        "workflow": {"mode": "job"},
        "model": {"profile": profile},
    }
    if requires_human_review is not None:
        manifest["workflow"]["requires_human_review"] = requires_human_review
    conn.execute(
        "INSERT OR REPLACE INTO agent_versions (agent_id, version, yaml_json, created_at) "
        "VALUES (?,?,?,?)",
        (agent_id, version, json.dumps(manifest, ensure_ascii=False), "2026-01-01T00:00:00+00:00"),
    )


@pytest.fixture()
def dbf(tmp_path):
    db_path = tmp_path / "flai_os.db"
    init_db(db_path)
    factory = lambda: get_conn(db_path)
    # K1 签发见证（Codex 增量2审 R5-1 + loop-auditor）：resolver 机制测试的默认上游 agent
    # 注册为 profile=none（确定性）——其 completed 产物经 task_output_is_signed_off 的
    # profile=none 支放行（等价"确定性上游合法自动完成"）。需未签/review-gated 上游的测试
    # 自行注册对应 profile 或造 review_approved 事件。
    conn = factory()
    try:
        _register_agent_version(conn, "hello_agent", "0.1.0", profile="none", requires_human_review=False)
    finally:
        conn.close()
    return factory


def _mk(conn, task_id, *, depends_on=None, inputs=None, input_file_ids=None,
        agent_id="hello_agent", agent_version="0.1.0", input_binding=None):
    return repos.create_task(
        conn, task_id=task_id, agent_id=agent_id, agent_version=agent_version,
        name=task_id, created_by="tester", inputs=inputs or {},
        input_file_ids=input_file_ids or [], metadata={},
        depends_on=depends_on, input_binding=input_binding,
    )


def _drive(conn, task_id, key):
    for s in _PATHS[key]:
        repos.set_task_status(conn, task_id, s)
    if key == "completed_reviewed":
        repos.apply_human_review(
            conn,
            task_id,
            action="approve",
            reviewer="测试评审员",
            reviewer_username="test_reviewer",
            reason_code=None,
            comment="resolver fixture sign-off",
        )


def _append_pre_cutover_review_approved(conn, task_id: str) -> str:
    """Seed one exact legacy signer row plus its immutable cutover witness."""
    trigger_names = (
        "trg_structured_review_events_decision_witness",
        "trg_structured_review_events_capture_witness",
        "trg_task_review_event_witnesses_validate_insert",
    )
    trigger_sql = {
        name: conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
            (name,),
        ).fetchone()[0]
        for name in trigger_names
    }
    for name in trigger_names:
        conn.execute(f'DROP TRIGGER "{name}"')
    event_id = f"legacy-review-{uuid.uuid4().hex}"
    cur = conn.execute(
        "INSERT INTO task_events "
        "(event_id, task_id, agent_id, event_type, level, message, payload_json, created_at) "
        "VALUES (?, ?, 'hello_agent', 'review_approved', 'info', "
        "'legacy signer witness', '{}', '2026-07-19T00:00:00+00:00')",
        (event_id, task_id),
    )
    conn.execute(
        "INSERT INTO task_review_event_witnesses "
        "(event_id, event_internal_id, task_id, agent_id, event_type, level, "
        "message, payload_json, created_at, decision_id, witness_kind, schema_version) "
        "SELECT event_id, id, task_id, agent_id, event_type, level, message, "
        "payload_json, created_at, NULL, 'legacy_pre_instrumentation', 1 "
        "FROM task_events WHERE id = ?",
        (cur.lastrowid,),
    )
    for name in trigger_names:
        conn.execute(trigger_sql[name])
    return event_id


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
        repos.apply_human_review(
            conn,
            "up",
            action="approve",
            reviewer="测试评审员",
            reviewer_username="test_reviewer",
            reason_code=None,
            comment="T1 fixture sign-off",
        )
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

    # ADR-0030（批七）：B 消费 sensitive 管道产物须合法持有 sensitive 准入——
    # 消费点密级复核对 internal 缺省上限会如实拒执行（那是另一条测试的职责，
    # test_b7_batch_and_clearance）。本测试的对象是 ADR-0025 派生传播语义，
    # 故给本 registry 实例的 hello 显式授 sensitive（in-memory，不动包文件）。
    runtime.agent_registry.get("hello_agent")["clearance"] = {"max_data_classification": "sensitive"}

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
        # Legacy corruption fixture: modern apply_human_review correctly refuses
        # to capture a non-output manifest, so reproduce the pre-instrumentation
        # row as auto-completed plus its historical signer event.  Resolver must
        # still reject the bad file instead of trusting status/event alone.
        _drive(conn, "up", "completed_auto")
        _append_pre_cutover_review_approved(conn, "up")
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


# ── R2-1 eval/user 隔离（Codex 增量2审 R2）：非 user 上游 fail-closed 级联取消 ──

def test_R2_eval_upstream_cancels_downstream_at_resolver(dbf):
    """R2-1 tamper（消费侧兜底）：legacy user 任务的上游是 origin=eval（绕过创建期检查）
    → resolver fail-closed 级联取消（reason=upstream_origin_isolation）。拆 non_user 检查
    → eval 产物经管道流入 user 任务违 ADR-0018 隔离。"""
    conn = dbf()
    try:
        repos.create_task(
            conn, task_id="eval_up", agent_id="hello_agent", agent_version="0.1.0",
            name="eval", created_by="t", inputs={}, input_file_ids=[], metadata={}, origin="eval",
        )
        _attach_output(conn, "eval_up")
        _drive(conn, "eval_up", "completed_reviewed")
        _mk(conn, "down", depends_on=["eval_up"])  # _mk 建的 down 是 origin=user
    finally:
        conn.close()

    assert resolve_dependencies_once(dbf) == 1
    conn = dbf()
    try:
        down = repos.get_task(conn, "down")
        assert down["status"] == "cancelled"
        events = repos.list_events(conn, "down")
        assert any(
            e["event_type"] == "task_cancelled"
            and e["payload"].get("reason") == "upstream_origin_isolation"
            for e in events
        )
    finally:
        conn.close()


# ── R2-2 消费点 manifest + binding（Codex 增量2审 R2）：双端各自独立强制 ──

def test_R2_output_not_in_owner_manifest_rejected(runtime_env):
    """R2-2 tamper（manifest）：input_file_ids 直含某已完成依赖的 output-kind 文件，但该
    file_id 不在 owner 的 output_file_ids 清单内（legacy 直塞非产物 id）→ 消费点拒。"""
    cf = runtime_env["conn_factory"]
    runtime = runtime_env["runtime"]
    runner = JobRunner(runtime, cf)
    conn = cf()
    try:
        _mk(conn, "owner")
        stray = _real_output(runtime, conn, "owner", name="stray.txt")  # 不 set_task_outputs
        _drive(conn, "owner", "completed_reviewed")
        _mk(conn, "consumer", depends_on=["owner"], inputs={"name": "x"}, input_file_ids=[stray])
        repos.set_task_status(conn, "consumer", "queued")
    finally:
        conn.close()
    runner.run_once()
    conn = cf()
    try:
        assert repos.get_task(conn, "consumer")["status"] == "failed"  # 不在 owner manifest → 拒
    finally:
        conn.close()


def test_R2_binding_excluded_upstream_output_rejected_at_consume(runtime_env):
    """R2-2 tamper（from_tasks 排除）：depends_on=[A,B]、from_tasks=[A]，B 的 output 直塞
    input_file_ids（在 B manifest 内、B completed）→ 消费点因 from_tasks 排除 B 拒。"""
    cf = runtime_env["conn_factory"]
    runtime = runtime_env["runtime"]
    runner = JobRunner(runtime, cf)
    conn = cf()
    try:
        _mk(conn, "up_a")
        _drive(conn, "up_a", "completed_reviewed")
        _mk(conn, "up_b")
        fb = _real_output(runtime, conn, "up_b", name="b.txt")
        repos.set_task_outputs(conn, "up_b", [fb])  # fb 真在 up_b manifest 内
        _drive(conn, "up_b", "completed_reviewed")
        repos.create_task(
            conn, task_id="consumer", agent_id="hello_agent", agent_version="0.1.0",
            name="c", created_by="t", inputs={"name": "x"}, input_file_ids=[fb], metadata={},
            depends_on=["up_a", "up_b"], input_binding={"from_tasks": ["up_a"]},
        )
        repos.set_task_status(conn, "consumer", "queued")
    finally:
        conn.close()
    runner.run_once()
    conn = cf()
    try:
        assert repos.get_task(conn, "consumer")["status"] == "failed"  # B 被 from_tasks 排除 → 拒
    finally:
        conn.close()


# ── R2-3 事件与状态迁移同事务原子（Codex 增量2审 R2）：非法事件整体回滚 ──

def test_R2_enqueue_event_atomic_rollback_on_invalid_event(dbf):
    """R2-3 tamper：传非法 event_type（不在 event.schema 枚举）→ append_event 校验炸 →
    created→queued 整体 ROLLBACK，任务留 created（绝无「queued 却无 dependency_resolved
    事件」的半态）。证事件与状态迁移同事务原子。"""
    conn = dbf()
    try:
        _mk(conn, "up")
        f = _attach_output(conn, "up")
        _drive(conn, "up", "completed_reviewed")
        _mk(conn, "down", depends_on=["up"])
    finally:
        conn.close()
    conn = dbf()
    try:
        with pytest.raises(Exception):
            repos.enqueue_dependent_task(
                conn, "down", [f],
                event={
                    "agent_id": "hello_agent", "event_type": "NOT_A_REAL_EVENT_TYPE",
                    "level": "info", "message": "x", "payload": {},
                },
            )
        assert repos.get_task(conn, "down")["status"] == "created"  # 回滚，未半推进到 queued
    finally:
        conn.close()


# ── R3-1 profile:none 运行时强制无 LLM（Codex 增量2审 R3 P1，§3.6 keystone）──

def test_R3_no_model_gateway_stub_denies_all_calls():
    """R3-1 tamper（桩）：_NoModelGatewayContext 的 chat/embed/vision 一律抛
    ModelAccessDeniedError——profile:none agent 物理无 LLM。"""
    from backend.app.core.errors import ModelAccessDeniedError
    from backend.app.runtime.runtime import _NoModelGatewayContext
    ctx = _NoModelGatewayContext("evil_none_agent")
    for call in (
        lambda: ctx.chat("reasoning", []),
        lambda: ctx.embed("reasoning", "x"),
        lambda: ctx.vision("reasoning", "/p", "prompt"),
    ):
        with pytest.raises(ModelAccessDeniedError):
            call()


def test_R3_build_context_gates_gateway_by_profile(runtime_env):
    """R3-1 tamper（注入）：_build_context 按声明 profile 选 gateway——none（含缺省）→ 抛异常
    桩，非 none → 功能 gateway。拆条件注入 → none agent 拿功能 gateway 可绕人签闸调 LLM+
    自动 completed+经 resolver 传未签发判决（§3.6 keystone 被击穿）。"""
    from backend.app.runtime.runtime import _ModelGatewayContext, _NoModelGatewayContext
    runtime = runtime_env["runtime"]
    conn = runtime_env["conn_factory"]()
    try:
        task = {"agent_id": "x", "id": "t", "inputs": {}}
        d = Path("/tmp")
        none_ctx = runtime._build_context(conn, task, {"model": {"profile": "none"}, "tools": []}, d, d, [])
        default_ctx = runtime._build_context(conn, task, {"tools": []}, d, d, [])  # 缺省 profile
        real_ctx = runtime._build_context(conn, task, {"model": {"profile": "reasoning"}, "tools": []}, d, d, [])
        assert isinstance(none_ctx["model_gateway"], _NoModelGatewayContext)
        assert isinstance(default_ctx["model_gateway"], _NoModelGatewayContext)  # 缺省=none
        assert isinstance(real_ctx["model_gateway"], _ModelGatewayContext)
    finally:
        conn.close()


# ── R3-2 级联取消诊断可见（Codex 增量2审 R3 P2）：落 internal 不被分级门遮蔽 ──

def test_R3_cascade_cancel_sets_internal_classification(dbf):
    """R3-2 tamper：级联取消任务落 data_classification=internal（非 NULL），系统取消诊断经
    分级门可见、不被 fail-closed 当 sensitive 遮蔽。拆 COALESCE → NULL → 诊断被遮蔽。"""
    conn = dbf()
    try:
        _mk(conn, "up")
        _drive(conn, "up", "failed")
        _mk(conn, "down", depends_on=["up"])
    finally:
        conn.close()
    resolve_dependencies_once(dbf)
    conn = dbf()
    try:
        down = repos.get_task(conn, "down")
        assert down["status"] == "cancelled"
        assert down["data_classification"] == "internal"  # 非 NULL → 诊断经分级门可见
    finally:
        conn.close()


# ── R3-3 resolver 独立节流（Codex 增量2审 R3 P2）：间隔内不重跑 ──

def test_R3_resolve_if_due_throttles(runtime_env, monkeypatch):
    """R3-3 tamper：_resolve_if_due 按间隔节流——间隔内三连调用只真解析一次（防就绪队列
    长时对无变化阻塞集重扫）。拆节流 → 三次全跑。"""
    import backend.app.jobs.runner as runner_mod
    calls = {"n": 0}
    monkeypatch.setattr(runner_mod, "resolve_dependencies_once", lambda cf: calls.__setitem__("n", calls["n"] + 1))
    runner = runner_mod.JobRunner(runtime_env["runtime"], runtime_env["conn_factory"])
    runner._resolve_if_due()  # 首次：跑
    runner._resolve_if_due()  # 间隔内：跳过
    runner._resolve_if_due()  # 仍间隔内：跳过
    assert calls["n"] == 1


# ── R4-1 人签路径原子性（Codex 增量2审 R4 P1）：迁移+样本标签+signer 事件同事务 ──

def test_R4_apply_human_review_atomic_happy_path(dbf):
    """R4-1：apply_human_review(approve) 原子落 waiting_review→completed 迁移 + signer 事件。
    迁移后 review_approved 事件与状态同批可见（非分两次提交）。"""
    conn = dbf()
    try:
        _mk(conn, "t")
        _drive(conn, "t", "waiting_review")
        task, sample_rows = repos.apply_human_review(
            conn,
            "t",
            action="approve",
            reviewer="张三",
            reviewer_username="zhangsan",
            reason_code=None,
            comment=None,
        )
        assert task["status"] == "completed"
        assert sample_rows == 0  # 本任务无样本
        assert any(e["event_type"] == "review_approved" for e in repos.list_events(conn, "t"))
    finally:
        conn.close()


def test_R4_review_event_failure_rolls_back_transition(dbf, monkeypatch):
    """R4-1 tamper：signer 事件写入失败 → waiting_review→completed 迁移**整体 ROLLBACK**，
    任务留 waiting_review、无 review_approved 事件。证「无事件=没发生」在人签路径原子——
    绝无 status=completed 却无 signer 事件的半态（resolver 只看 status 会放行未签发下游）。
    拆原子（迁移先独立 COMMIT，如旧 set_task_status 路径）→ 迁移残留 completed → RED。"""
    conn = dbf()
    try:
        _mk(conn, "t")
        _drive(conn, "t", "waiting_review")
        sample = repos.record_sample(
            conn,
            task_id="t",
            agent_id="a",
            agent_version="1.0.0",
            input_json={},
            output_json={},
            accepted_by_engineer=None,
            classification="internal",
        )

        def _boom(*a, **k):
            raise RuntimeError("signer 事件写入炸")

        monkeypatch.setattr(repos, "append_event", _boom)
        with pytest.raises(RuntimeError):
            repos.apply_human_review(
                conn,
                "t",
                action="approve",
                reviewer="张三",
                reviewer_username="zhangsan",
                reason_code=None,
                comment=None,
            )
        monkeypatch.undo()

        t = repos.get_task(conn, "t")
        assert t["status"] == "waiting_review"  # 回滚：绝未半推进到 completed
        assert not any(
            e["event_type"] == "review_approved" for e in repos.list_events(conn, "t")
        )
        assert repos.get_human_decision(conn, "t") is None
        assert repos.get_sample(conn, sample["id"])["accepted_by_engineer"] is None
    finally:
        conn.close()


# ── R4-2 候选集列投影（Codex 增量2审 R4 P2）：绝不 materialize/解码 256KB inputs ──

def test_R4_candidate_query_projects_columns_only(dbf):
    """R4-2 tamper：list_created_dependent_tasks 只投影 resolver 消费的 4 列
    （id/agent_id/depends_on/input_binding）——即便任务 inputs 极大也绝不解码入候选负载。
    返回 dict 恰含这四键、不含 inputs。拆回 SELECT *+_decode_task → 冒出 inputs 键 → RED。"""
    conn = dbf()
    try:
        _mk(conn, "down", depends_on=["up"], inputs={"blob": "x" * 200_000})
        cands = repos.list_created_dependent_tasks(conn)
        assert len(cands) == 1
        c = cands[0]
        assert set(c.keys()) == {"id", "agent_id", "depends_on", "input_binding"}
        assert "inputs" not in c  # 大 inputs 绝未 materialize
        assert c["depends_on"] == ["up"]  # depends_on 仍正确解码
        assert c["input_binding"] is None
    finally:
        conn.close()


# ══ 设计级巡查收口批（Codex R5 + loop-auditor）：K1 签发维 / K2 消费侧 origin / R1 隔离 ══

# ── K1 签发维 provenance（R5-1 + loop-auditor）：completed 谓词换持久签发见证，双点 fail-closed ──

def test_K1_unsigned_completed_upstream_cancels_downstream(dbf):
    """K1 tamper（resolver 侧）：LLM 型（profile=reasoning）上游到 completed 但**无 review_approved
    事件**（模拟 legacy pre-§3.6 自动放行/未签）→ task_output_is_signed_off False → resolver
    fail-closed 级联取消下游（未签 LLM 判决绝不越依赖边界）。拆签发见证（恒 True）→ 反而入队。"""
    conn = dbf()
    try:
        _register_agent_version(conn, "llm_up_agent", "0.1.0", profile="reasoning", requires_human_review=True)
        _mk(conn, "llm_up", agent_id="llm_up_agent")
        _attach_output(conn, "llm_up")
        _drive(conn, "llm_up", "completed_auto")  # 自动完成路径，无人签、无 review_approved
        _mk(conn, "down", depends_on=["llm_up"])
    finally:
        conn.close()
    resolve_dependencies_once(dbf)
    conn = dbf()
    try:
        down = repos.get_task(conn, "down")
        assert down["status"] == "cancelled"  # 未签上游 → fail-closed 取消
        assert any(
            e["payload"].get("reason") == "upstream_unsigned" for e in repos.list_events(conn, "down")
        )
    finally:
        conn.close()


def test_K1_signed_via_review_approved_releases(dbf):
    """K1 正控：review-gated LLM 上游经 apply_human_review 人签（造持久 review_approved 事件）→
    task_output_is_signed_off 经事件支放行 → resolver 入队下游。证签发见证正路可通。"""
    conn = dbf()
    try:
        _register_agent_version(conn, "llm_up_agent", "0.1.0", profile="reasoning", requires_human_review=True)
        _mk(conn, "llm_up", agent_id="llm_up_agent")
        _attach_output(conn, "llm_up")
        _drive(conn, "llm_up", "waiting_review")  # LLM 型停人签闸
        repos.apply_human_review(
            conn,
            "llm_up",
            action="approve",
            reviewer="张三",
            reviewer_username="zhangsan",
            reason_code=None,
            comment=None,
        )
        _mk(conn, "down", depends_on=["llm_up"])
    finally:
        conn.close()
    assert resolve_dependencies_once(dbf) == 1  # 已签 → 入队
    conn = dbf()
    try:
        assert repos.get_task(conn, "down")["status"] == "queued"
    finally:
        conn.close()


def test_K1_version_flip_keys_on_locked_version(dbf):
    """K1 版本翻转 tamper：任务锁 agent_version=1（profile=reasoning，未签），当前 registry 已发
    version=2（profile=none）。task_output_is_signed_off 键于任务**锁定的 v1** 历史 manifest →
    未签拒；绝不被"当前版本=none"反向欺骗放行。naive「查当前 registry」修法在此 RED。"""
    conn = dbf()
    try:
        _register_agent_version(conn, "flip_agent", "1", profile="reasoning", requires_human_review=True)
        _register_agent_version(conn, "flip_agent", "2", profile="none")  # 当前版本已修正为确定性
        _mk(conn, "flip_up", agent_id="flip_agent", agent_version="1")  # 任务跑在历史 v1
        _attach_output(conn, "flip_up")
        _drive(conn, "flip_up", "completed_auto")  # v1 下自动完成、未签
        _mk(conn, "down", depends_on=["flip_up"])
    finally:
        conn.close()
    resolve_dependencies_once(dbf)
    conn = dbf()
    try:
        assert repos.get_task(conn, "down")["status"] == "cancelled"  # 键 v1 未签 → 拒（非被 v2=none 欺骗）
    finally:
        conn.close()


def test_K1_consume_side_unsigned_output_rejected(runtime_env):
    """K1 消费侧 tamper（loop-auditor 逮的孪生洞）：上游 completed 但未签（profile=reasoning 无
    review_approved），其 output 已直含消费者 input_file_ids（绕 resolver，模拟 legacy）→ 执行期
    消费点 K1 拒 → failed。resolver 生产侧修不到此路径（input_file_ids 已直含），故消费侧双点同
    守。拆消费侧 K1 签发见证 → 绕过消费者反而 completed。"""
    cf = runtime_env["conn_factory"]
    runtime = runtime_env["runtime"]
    runner = JobRunner(runtime, cf)
    conn = cf()
    try:
        _register_agent_version(conn, "llm_producer", "0.1.0", profile="reasoning", requires_human_review=True)
        _mk(conn, "llm_up", agent_id="llm_producer")
        fid = _real_output(runtime, conn, "llm_up")
        repos.set_task_outputs(conn, "llm_up", [fid])
        _drive(conn, "llm_up", "completed_auto")  # completed 但无 review_approved（未签）
        # 消费者给**有效** inputs（name）——非空见证的命门：否则消费者会因缺输入 failed，
        # 与 K1 无关而假绿（tamper 关 K1 仍 failed）。给全输入 → 唯一 failed 因即 K1 消费点拒。
        _mk(conn, "consumer", depends_on=["llm_up"], inputs={"name": "x"}, input_file_ids=[fid])
        repos.set_task_status(conn, "consumer", "queued")
    finally:
        conn.close()
    runner.run_once()
    conn = cf()
    try:
        c = repos.get_task(conn, "consumer")
        assert c["status"] == "failed"  # K1 消费侧签发见证拒
        assert "签发见证" in (c.get("error_message") or "")  # 且失败因确是 K1（非缺输入等）
    finally:
        conn.close()


# ── K2 消费侧 origin 隔离（loop-auditor）：resolver/create_task 都校，消费点补齐 ──

def test_K2_consume_side_eval_origin_output_rejected(runtime_env):
    """K2 消费侧 tamper：上游 origin=eval（用 profile=none agent 故过 K1 签发见证），其 output 已
    直含 user 消费者 input_file_ids（绕 resolver+create_task 双挡，模拟 legacy/直写）→ 消费点 K2
    origin 隔离拒 → failed（ADR-0018 防样本库污染）。拆消费侧 K2 → eval 内容流入 user 任务。"""
    cf = runtime_env["conn_factory"]
    runtime = runtime_env["runtime"]
    runner = JobRunner(runtime, cf)
    conn = cf()
    try:
        _register_agent_version(conn, "eval_det_agent", "0.1.0", profile="none", requires_human_review=False)  # 确定性→过 K1
        repos.create_task(
            conn, task_id="eval_up", agent_id="eval_det_agent", agent_version="0.1.0",
            name="eval_up", created_by="t", inputs={}, input_file_ids=[], metadata={}, origin="eval",
        )
        fid = _real_output(runtime, conn, "eval_up")
        repos.set_task_outputs(conn, "eval_up", [fid])
        _drive(conn, "eval_up", "completed_auto")
        # 有效 inputs（非空见证命门，同 K1 消费侧）→ 唯一 failed 因即 K2 origin 隔离
        _mk(conn, "user_consumer", depends_on=["eval_up"], inputs={"name": "x"}, input_file_ids=[fid])
        repos.set_task_status(conn, "user_consumer", "queued")
    finally:
        conn.close()
    runner.run_once()
    conn = cf()
    try:
        c = repos.get_task(conn, "user_consumer")
        assert c["status"] == "failed"  # K2 origin 隔离拒
        assert "隔离轴" in (c.get("error_message") or "")  # 且失败因确是 K2（非缺输入/K1）
    finally:
        conn.close()


# ── R1 resolver per-candidate 隔离（R5-3 + loop-auditor）：毒丸 quarantine 不掀翻整趟 ──

def test_R1_poison_binding_quarantined_valid_proceeds(dbf):
    """R1 tamper（R5-3 canonical）：畸形 input_binding.from_tasks 非 list（直调 repos 绕 API
    Pydantic，模拟 legacy/直写）令 membership 检查抛 TypeError。**毒丸候选被 quarantine
    （created→cancelled），同趟合法候选照常入队不被饿死**。拆 per-candidate try/except →
    毒丸掀翻整趟 pass → 合法候选滞留 created（RED）。"""
    conn = dbf()
    try:
        _mk(conn, "up")
        _attach_output(conn, "up")
        _drive(conn, "up", "completed_reviewed")
        _mk(conn, "poison", depends_on=["up"], input_binding={"from_tasks": 1})  # 毒丸：非 list
        _mk(conn, "valid", depends_on=["up"])  # 合法候选，依赖同一 completed 上游
    finally:
        conn.close()
    resolve_dependencies_once(dbf)
    conn = dbf()
    try:
        assert repos.get_task(conn, "poison")["status"] == "cancelled"  # 毒丸隔离
        assert any(
            e["payload"].get("reason") == "poison_candidate_quarantined"
            for e in repos.list_events(conn, "poison")
        )
        assert repos.get_task(conn, "valid")["status"] == "queued"  # 合法候选未被饿死（隔离生效）
    finally:
        conn.close()


def test_R1_poison_scalar_depends_on_quarantined(dbf):
    """R1 兄弟：depends_on 持久为 JSON 标量（直写绕 API；候选查询 filter != '[]' 放行）→
    `for uid in 5` 抛 TypeError。证隔离对**不同抛点**（非仅 from_tasks）皆通用——毒丸 quarantine，
    resolver 不炸。"""
    conn = dbf()
    try:
        repos.create_task(
            conn, task_id="poison_scalar", agent_id="hello_agent", agent_version="0.1.0",
            name="poison_scalar", created_by="t", inputs={}, input_file_ids=[], metadata={},
            depends_on=5,  # 非 list 标量（直写模拟 legacy）
        )
    finally:
        conn.close()
    resolve_dependencies_once(dbf)  # 不应抛
    conn = dbf()
    try:
        assert repos.get_task(conn, "poison_scalar")["status"] == "cancelled"  # 毒丸隔离取消
    finally:
        conn.close()


# ══ 命中即审收口（安全边界异源实现审逮出我 sweep 代码 3 P1）：谓词收紧/版本权威/隔离窄化 ══

def test_hitreview_R1_degenerate_manifest_fails_closed(dbf):
    """命中即审 R1 tamper：签发见证收紧——manifest 有 profile=none 但 requires_human_review
    **缺失**（半/退化 manifest）绝不当自动签发放行。仅显式 profile=='none'+rhr is False 才放行。
    拆收紧（回 profile in (None,'none')）→ 半 manifest 被当 none 放行、下游入队 RED（fail-open）。"""
    conn = dbf()
    try:
        _register_agent_version(conn, "half_agent", "0.1.0", profile="none")  # rhr 缺失=退化
        _mk(conn, "half_up", agent_id="half_agent")
        _attach_output(conn, "half_up")
        _drive(conn, "half_up", "completed_auto")  # 无 review_approved
        _mk(conn, "down", depends_on=["half_up"])
    finally:
        conn.close()
    resolve_dependencies_once(dbf)
    conn = dbf()
    try:
        # rhr 非显式 False → 未确立自动签发资格 → fail-closed 取消（收紧前会 fail-open 入队）
        assert repos.get_task(conn, "down")["status"] == "cancelled"
        assert any(
            e["payload"].get("reason") == "upstream_unsigned" for e in repos.list_events(conn, "down")
        )
    finally:
        conn.close()


def test_hitreview_R2_agent_version_drift_fails_task(runtime_env):
    """命中即审 R2 tamper：任务锁定 agent_version 异于当前注册版本（跨升级窗口 drift）→ _execute
    fail-closed 拒执行（provenance 权威性=K1 签发见证前提：task.agent_version 恒等真跑版本）。
    拆版本检查 → 任务在异版本上照跑 completed RED（有效 inputs 命门保非空）。"""
    cf = runtime_env["conn_factory"]
    runtime = runtime_env["runtime"]
    runner = JobRunner(runtime, cf)
    conn = cf()
    try:
        # hello_agent 当前注册 0.1.0；锁定不存在的旧版本 0.0.9 模拟 drift。给有效 inputs（name）
        # 使拆检查后能真 completed（否则缺输入 failed=假绿）。
        _mk(conn, "drift_task", agent_id="hello_agent", agent_version="0.0.9", inputs={"name": "x"})
        repos.set_task_status(conn, "drift_task", "queued")
    finally:
        conn.close()
    runner.run_once()
    conn = cf()
    try:
        t = repos.get_task(conn, "drift_task")
        assert t["status"] == "failed"  # 版本漂移 → fail-closed
        assert "版本漂移" in (t.get("error_message") or "")  # 且失败因确是版本检查
        assert t["data_classification"] == "internal"  # final-confirm P2：诊断经分级门可见非遮蔽
    finally:
        conn.close()


def test_finalconfirm_open_set_poison_shapes_quarantined(dbf):
    """final-confirm P1：**毒丸集是开集**——input_binding 非 dict（AttributeError）、depends_on 元素
    非 str（sqlite3.ProgrammingError）等前版白名单 (TypeError,KeyError,ValueError) 漏掉的毒丸，
    黑名单-瞬时结构下一律 quarantine、不掀翻整趟。拆回白名单 → 这些毒丸重新饿死后续候选 RED。"""
    conn = dbf()
    try:
        _mk(conn, "up")
        _attach_output(conn, "up")
        _drive(conn, "up", "completed_reviewed")
        # 毒丸①：input_binding 是 list（非 dict）→ binding.get 抛 AttributeError
        _mk(conn, "poison_attr", depends_on=["up"], input_binding=["x"])
        # 毒丸②：depends_on 元素是 dict（非 str）→ get_task 绑定抛 sqlite3.ProgrammingError
        repos.create_task(
            conn, task_id="poison_prog", agent_id="hello_agent", agent_version="0.1.0",
            name="poison_prog", created_by="t", inputs={}, input_file_ids=[], metadata={},
            depends_on=[{}],
        )
        _mk(conn, "zvalid", depends_on=["up"])  # 合法候选（id 序在毒丸后），验不被饿死
    finally:
        conn.close()
    resolve_dependencies_once(dbf)  # 不应抛（毒丸各自 quarantine，非 operational）
    conn = dbf()
    try:
        assert repos.get_task(conn, "poison_attr")["status"] == "cancelled"  # AttributeError 毒丸隔离
        assert repos.get_task(conn, "poison_prog")["status"] == "cancelled"  # ProgrammingError 毒丸隔离
        assert repos.get_task(conn, "zvalid")["status"] == "queued"  # 合法候选未被饿死
    finally:
        conn.close()


def test_hitreview_R3_operational_error_not_quarantined(dbf, monkeypatch):
    """命中即审 R3 tamper：候选处理遇 operational 错误（sqlite3.OperationalError 瞬时故障）绝不
    当毒丸 cancel（那会永久误杀合法任务），而上抛至 _resolve_if_due 兜底待下 tick 重试。任务
    留 created。拆窄化 except（回 except Exception）→ 合法任务被误 quarantine cancel RED。"""
    import sqlite3 as _sqlite3
    import backend.app.jobs.runner as runner_mod

    conn = dbf()
    try:
        _mk(conn, "up")
        _attach_output(conn, "up")
        _drive(conn, "up", "completed_reviewed")
        _mk(conn, "victim", depends_on=["up"])
    finally:
        conn.close()

    def _boom(_conn, _task):
        raise _sqlite3.OperationalError("database is locked")  # 瞬时 operational 故障

    monkeypatch.setattr(runner_mod, "_resolve_one_candidate", _boom)
    with pytest.raises(_sqlite3.OperationalError):  # 上抛而非吞（窄化 except 不捕 operational）
        resolve_dependencies_once(dbf)
    monkeypatch.undo()

    conn = dbf()
    try:
        assert repos.get_task(conn, "victim")["status"] == "created"  # 未被误 cancel，留待重试
    finally:
        conn.close()
