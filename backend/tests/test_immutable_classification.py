"""不可变任务级分级 + 单 chokepoint 内容门（ADR-0025）自证 witness。

闭合 Codex R1-A（遮蔽面不全：error_message/message + 三漏端点）与 R1-B（read 期重派生
漂移 / 无 files-samples 行的 sensitive 任务 / 存量未回填）。覆盖 ADR-0025 验收 1-8：
工具污点轴（保留自 ADR-0024）→ 执行期落库 → 单 chokepoint → 全端点封闭 → 回填 → NULL 兜底。

纪律：全端点封闭走真实 TestClient；漂移 witness 证「读列不重派生」；tamper 见证在
review-record（改 gate 为重派生 / 撤某端点接线 → 对应断言 RED）。
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml
from fastapi.testclient import TestClient

from conftest import seed_and_login, seed_user, login
from backend.app.api import classification_gate as cgate
from backend.app.main import create_app
from backend.app.runtime.runtime import _task_data_classification, _tool_taint_classification
from backend.app.storage import repos
from backend.app.storage.db import get_conn, init_db

REPO_ROOT = Path(__file__).resolve().parents[2]


class _StubToolRegistry:
    def __init__(self, tools: dict[str, dict[str, Any]]) -> None:
        self._tools = tools

    def get(self, tool_id: str) -> dict[str, Any] | None:
        return self._tools.get(tool_id)


# ── 1. 工具污点轴（保留自 ADR-0024，架构无关） ─────────────────────────────

def test_tool_taint_matrix() -> None:
    tainting = _StubToolRegistry({
        "recon": {"output_classification": "sensitive"},
        "calc": {"output_classification": "internal"},
    })
    assert _tool_taint_classification({"tools": ["recon"]}, tainting) == "sensitive"
    assert _tool_taint_classification({"tools": ["calc", "recon"]}, tainting) == "sensitive"
    assert _tool_taint_classification({"tools": ["calc"]}, tainting) == "internal"
    assert _tool_taint_classification({"tools": []}, tainting) == "internal"


def test_tool_taint_defense_in_depth() -> None:
    """已加载工具非显式 internal（缺字段/坏值）→ fail-closed sensitive。"""
    assert _tool_taint_classification({"tools": ["x"]}, _StubToolRegistry({"x": {}})) == "sensitive"
    assert _tool_taint_classification(
        {"tools": ["x"]}, _StubToolRegistry({"x": {"output_classification": "weird"}})
    ) == "sensitive"


def test_tool_taint_absent_or_no_registry_internal() -> None:
    """affirmative-only：registry=None 或工具未加载 → 不贡献污点（其 call 本 fail-closed）。"""
    assert _tool_taint_classification({"tools": ["recon"]}, None) == "internal"
    assert _tool_taint_classification(
        {"tools": ["ghost"]}, _StubToolRegistry({"recon": {"output_classification": "sensitive"}})
    ) == "internal"


def test_monitor_agent_real_contract_derives_sensitive() -> None:
    """真契约锚：真实 monitor_adapter_recon/tool.yaml 声明 sensitive → 挂它的 agent
    经工具轴派生 sensitive（读真 yaml，非 stub）。"""
    tool_yaml = yaml.safe_load(
        (REPO_ROOT / "tools_impl" / "monitor_adapter_recon" / "tool.yaml").read_text("utf-8")
    )
    assert tool_yaml["output_classification"] == "sensitive"
    reg = _StubToolRegistry({"monitor_adapter_recon": tool_yaml})
    assert _tool_taint_classification({"tools": ["monitor_adapter_recon"]}, reg) == "sensitive"


# ── 2. 单 chokepoint 判定（classification_gate，读落库列不重派生） ──────────

def _mktask(conn, task_id: str, *, classification, status: str = "completed",
            err: str | None = None, agent_id: str = "hello_agent"):
    repos.create_task(conn, task_id=task_id, agent_id=agent_id, agent_version="0.1.0",
                      name="t", created_by="u", inputs={})
    conn.execute(
        "UPDATE tasks SET status=?, data_classification=?, error_message=? WHERE id=?",
        (status, classification, err, task_id),
    )


def test_is_sensitive_reads_persisted_column(tmp_path: Path) -> None:
    db = tmp_path / "d.db"; init_db(db)
    conn = get_conn(db)
    try:
        _mktask(conn, "s1", classification="sensitive")
        _mktask(conn, "i1", classification="internal")
        assert cgate.is_sensitive_task(conn, repos.get_task(conn, "s1")) is True
        assert cgate.is_sensitive_task(conn, repos.get_task(conn, "i1")) is False
    finally:
        conn.close()


def test_is_sensitive_null_fallback_failclosed(tmp_path: Path) -> None:
    """NULL（未回填/竞态）→ fail-closed：有派生内容行即封，无则放。不看注册表（不重派生）。"""
    db = tmp_path / "d.db"; init_db(db)
    conn = get_conn(db)
    try:
        _mktask(conn, "n_empty", classification=None)  # NULL 且无内容
        _mktask(conn, "n_content", classification=None)  # NULL 但有 tool_run
        repos.record_tool_run(conn, task_id="n_content", tool_id="t", tool_version="1",
                              mock=True, status="success", input_json={"x": 1}, started_at="2026-07-12T00:00:00+00:00")
        assert cgate.is_sensitive_task(conn, repos.get_task(conn, "n_empty")) is False
        assert cgate.is_sensitive_task(conn, repos.get_task(conn, "n_content")) is True
        # NULL 但任务自身有 error_message → 封
        _mktask(conn, "n_err", classification=None, status="failed", err="外部工具泄漏文本")
        assert cgate.is_sensitive_task(conn, repos.get_task(conn, "n_err")) is True
    finally:
        conn.close()


def test_redact_helpers() -> None:
    rows = [{"id": 1, "output": {"secret": "x"}, "error_message": "leak", "tool_id": "t"}]
    red = cgate.redact_rows(rows, cgate.TOOL_RUN_CONTENT_KEYS)
    assert red[0]["output"] is None and red[0]["error_message"] is None
    assert red[0]["content_withheld"] is True and red[0]["tool_id"] == "t"  # 元数据留存
    assert rows[0]["output"] == {"secret": "x"}  # 不改原
    task = {"id": "t", "status": "failed", "error_message": "leak"}
    rt = cgate.redact_task_row(task)
    assert rt["error_message"] is None and rt["content_withheld"] is True and rt["status"] == "failed"


# ── 3. 执行期落库不可变分级（D1）+ 漂移 witness（R1-B 闭合） ────────────────

def _sensitive_tool_agent_env(tmp_path: Path):
    """copytree hello_agent + 追加 monitor_adapter_recon（污点工具，workflow 不调它，
    纯静态污点），返回真 app。hello workflow 真调 mock_echo→任务可 completed。"""
    agents_dir = tmp_path / "agents"; agents_dir.mkdir()
    pkg = agents_dir / "taint_agent"
    shutil.copytree(REPO_ROOT / "agents" / "hello_agent", pkg,
                    ignore=shutil.ignore_patterns("__pycache__"))
    manifest = yaml.safe_load((pkg / "agent.yaml").read_text("utf-8"))
    manifest["id"] = "taint_agent"
    manifest["tools"] = [*(manifest.get("tools") or []), "monitor_adapter_recon"]
    manifest["knowledge"] = {"enabled": False, "scopes": []}
    (pkg / "agent.yaml").write_text(yaml.safe_dump(manifest, allow_unicode=True), "utf-8")
    db_path = tmp_path / "flai_os.db"
    app = create_app(
        agents_dir=agents_dir, tools_dir=REPO_ROOT / "tools_impl",
        contracts_dir=REPO_ROOT / "contracts", db_path=db_path,
        uploads_dir=tmp_path / "uploads", task_runs_dir=tmp_path / "task_runs",
    )
    return app, db_path


def _run(app, client, agent_id: str, inputs: dict) -> str:
    created = client.post("/api/tasks", json={"agent_id": agent_id, "inputs": inputs})
    assert created.status_code == 200, created.text
    task_id = created.json()["id"]
    conn = app.state.conn_factory()
    try:
        repos.claim_next_queued(conn)
    finally:
        conn.close()
    result = app.state.runtime.execute(task_id)
    assert result["status"] == "completed", result
    return task_id


def test_execution_persists_sensitive_and_survives_tool_unload(tmp_path: Path) -> None:
    """D1+R1-B：挂污点工具的 agent 跑完 → tasks.data_classification 落库 'sensitive'；
    **卸载该工具后**（模拟工具下线/降级），gate 仍判 sensitive（读落库列不重派生）。
    此前 read 期重派生会把它漂移解封成 internal 外泄。"""
    app, db_path = _sensitive_tool_agent_env(tmp_path)
    with TestClient(app) as client:
        seed_and_login(client, db_path)
        task_id = _run(app, client, "taint_agent", {"name": "污点"})
        conn = app.state.conn_factory()
        try:
            task = repos.get_task(conn, task_id)
            assert task["data_classification"] == "sensitive", "执行期未落库 sensitive"
            # 漂移 witness：卸载工具（清空注册表），gate 读落库列仍判 sensitive。
            app.state.tool_registry._tools.clear()
            assert cgate.is_sensitive_task(conn, repos.get_task(conn, task_id)) is True, (
                "工具卸载后任务被漂移解封——read 期重派生的 R1-B 洞未闭合"
            )
        finally:
            conn.close()


def test_internal_agent_persists_internal(tmp_path: Path) -> None:
    """无污点工具/无 sensitive 输入/无知识 → 执行期落库 internal（不误封既有 agent）。"""
    db_path = tmp_path / "flai_os.db"
    app = create_app(
        agents_dir=REPO_ROOT / "agents", tools_dir=REPO_ROOT / "tools_impl",
        contracts_dir=REPO_ROOT / "contracts", db_path=db_path,
        uploads_dir=tmp_path / "uploads", task_runs_dir=tmp_path / "task_runs",
    )
    with TestClient(app) as client:
        seed_and_login(client, db_path)
        task_id = _run(app, client, "hello_agent", {"name": "内部"})
        conn = app.state.conn_factory()
        try:
            assert repos.get_task(conn, task_id)["data_classification"] == "internal"
        finally:
            conn.close()


# ── 4. 全端点封闭（R1-A 闭合）：sensitive 任务 8 端点内容+错误文本全遮蔽 ────

def _seed_task_full_content(app, db_path, *, classification: str) -> str:
    """建一个带全套派生内容的任务：tool_runs/model_calls/samples/events + error_message。"""
    task_id = "full-" + classification[:3]
    conn = get_conn(db_path)
    try:
        _mktask(conn, task_id, classification=classification, status="failed",
                err="外部工具 grounding_failures 泄漏文本")
        repos.record_tool_run(conn, task_id=task_id, tool_id="monitor_adapter_recon",
                              tool_version="0.1.1", mock=False, status="failed",
                              input_json={"sample_run_dir": "/外部/机密/run"},
                              output_json={"draft": "机密侦察证据"},
                              raw_input_path="/外部/in", raw_output_path="/外部/out",
                              error_message="工具错误含外部路径 /外部/机密", started_at="2026-07-12T00:00:00+00:00")
        repos.record_model_call(conn, task_id=task_id, model_profile="reasoning",
                                model_name="glm", status="failed",
                                request_summary="含机密的请求", response_summary="含机密的响应",
                                error_message="模型错误含机密")
        repos.record_sample(conn, task_id=task_id, agent_id="a", agent_version="0.1.0",
                            input_json={"x": "机密输入"}, output_json={"y": "机密输出"},
                            raw_input_path="/外部/s_in", raw_output_path="/外部/s_out",
                            validation_status="failed", classification=classification)
        repos.append_event(conn, task_id=task_id, agent_id="test_agent", event_type="tool_failed",
                           level="error", message="tool_failed：外部 grounding_failures 明文",
                           payload={"tool_id": "monitor_adapter_recon", "input": {"dir": "/外部/机密"}})
    finally:
        conn.close()
    return task_id


def test_sensitive_task_all_endpoints_seal_content() -> None:
    """R1-A 头号 witness：sensitive 任务的 8 个任务派生端点内容载荷 + 错误文本列全遮蔽。"""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        db_path = tdp / "flai_os.db"
        app = create_app(
            agents_dir=REPO_ROOT / "agents", tools_dir=REPO_ROOT / "tools_impl",
            contracts_dir=REPO_ROOT / "contracts", db_path=db_path,
            uploads_dir=tdp / "up", task_runs_dir=tdp / "runs",
        )
        with TestClient(app) as client:
            seed_and_login(client, db_path)
            tid = _seed_task_full_content(app, db_path, classification="sensitive")

            # (1) GET /tasks/{id} + (2) GET /tasks + (3) POST sim-run-ref → error_message 遮蔽
            got = client.get(f"/api/tasks/{tid}").json()
            assert got["error_message"] is None and got["content_withheld"] is True
            listed = [t for t in client.get("/api/tasks?origin=all").json() if t["id"] == tid]
            assert listed and listed[0]["error_message"] is None and listed[0]["content_withheld"] is True
            sim = client.post(f"/api/tasks/{tid}/sim-run-ref",
                              json={"module": "m", "run_id": "r"}).json()
            assert sim["error_message"] is None and sim["content_withheld"] is True

            # (4) tool_runs → input/output/raw/error_message 全 None
            tr = client.get(f"/api/tasks/{tid}/tool_runs").json()[0]
            assert tr["input"] is None and tr["output"] is None and tr["error_message"] is None
            assert tr["raw_input_path"] is None and tr["content_withheld"] is True
            assert tr["tool_id"] == "monitor_adapter_recon"  # 元数据留存

            # (5) model_calls → summaries + error_message None，token/model 元数据留
            mc = client.get(f"/api/tasks/{tid}/model_calls").json()[0]
            assert mc["request_summary"] is None and mc["response_summary"] is None
            assert mc["error_message"] is None and mc["content_withheld"] is True
            assert mc["model_profile"] == "reasoning"

            # (6) samples → input/output/raw None
            sm = client.get(f"/api/tasks/{tid}/samples").json()[0]
            assert sm["input"] is None and sm["output"] is None and sm["raw_input_path"] is None
            assert sm["content_withheld"] is True

            # (7) events → message + payload 遮蔽（Codex R1-A：event.message 承载工具内容）
            evs = client.get(f"/api/tasks/{tid}/events").json()
            leak = [e for e in evs if e.get("event_type") == "tool_failed"]
            assert leak and leak[0]["message"] is None and leak[0]["payload"] is None
            assert leak[0]["content_withheld"] is True

            # 全响应正文里绝无任一机密串
            import json as _json
            for ep in (f"/api/tasks/{tid}", "/api/tasks?origin=all",
                       f"/api/tasks/{tid}/tool_runs", f"/api/tasks/{tid}/model_calls",
                       f"/api/tasks/{tid}/samples", f"/api/tasks/{tid}/events"):
                body = _json.dumps(client.get(ep).json(), ensure_ascii=False)
                assert "机密" not in body and "grounding_failures" not in body, f"{ep} 泄漏"


def test_internal_task_endpoints_not_redacted() -> None:
    """internal 任务不受门影响（不误伤）：内容原样返回，无 content_withheld。"""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        db_path = tdp / "flai_os.db"
        app = create_app(
            agents_dir=REPO_ROOT / "agents", tools_dir=REPO_ROOT / "tools_impl",
            contracts_dir=REPO_ROOT / "contracts", db_path=db_path,
            uploads_dir=tdp / "up", task_runs_dir=tdp / "runs",
        )
        with TestClient(app) as client:
            seed_and_login(client, db_path)
            tid = _seed_task_full_content(app, db_path, classification="internal")
            got = client.get(f"/api/tasks/{tid}").json()
            assert got.get("content_withheld") is not True
            tr = client.get(f"/api/tasks/{tid}/tool_runs").json()[0]
            assert tr["output"] == {"draft": "机密侦察证据"}  # 原样（internal 不封）
            assert tr.get("content_withheld") is not True


# ── 5. 存量回填矩阵（D4） ──────────────────────────────────────────────────

def test_backfill_matrix(tmp_path: Path) -> None:
    db = tmp_path / "d.db"; init_db(db)
    conn = get_conn(db)
    try:
        # a) 终态 + sensitive sample → sensitive
        _mktask(conn, "a", classification=None, status="completed")
        repos.record_sample(conn, task_id="a", agent_id="x", agent_version="1",
                            input_json={}, validation_status="success", classification="sensitive")
        # b) 终态 + tool_runs 引用 sensitive 工具、无 files/samples → sensitive（R1-B 关键场景）
        _mktask(conn, "b", classification=None, status="failed")
        repos.record_tool_run(conn, task_id="b", tool_id="monitor_adapter_recon",
                              tool_version="0.1.1", mock=False, status="failed", input_json={}, started_at="2026-07-12T00:00:00+00:00")
        # c) 终态 + 仅 internal 工具 → internal（不误封）
        _mktask(conn, "c", classification=None, status="completed")
        repos.record_tool_run(conn, task_id="c", tool_id="mock_echo", tool_version="1",
                              mock=True, status="success", input_json={}, started_at="2026-07-12T00:00:00+00:00")
        # d) 非终态（created）→ 留 NULL（执行期落库）
        _mktask(conn, "d", classification=None, status="created")

        n = repos.backfill_task_data_classification(conn, ["monitor_adapter_recon"])
        assert n == 3  # a/b/c 终态回填；d 非终态不计
        assert repos.get_task(conn, "a")["data_classification"] == "sensitive"
        assert repos.get_task(conn, "b")["data_classification"] == "sensitive"
        assert repos.get_task(conn, "c")["data_classification"] == "internal"
        assert repos.get_task(conn, "d")["data_classification"] is None
        # 幂等：再跑一次 no-op
        assert repos.backfill_task_data_classification(conn, ["monitor_adapter_recon"]) == 0
    finally:
        conn.close()


# ── 6. 会话聚合 model_calls 端点封闭（R1-A 补漏：第 9 端点） ──────────────────

def test_conversation_model_calls_seal_by_task() -> None:
    """R1-A 补漏 witness：`GET /conversations/{id}/model_calls` 跨成员任务聚合 model_calls，
    sensitive 任务的 request/response_summary/error_message 遮蔽；internal 任务 + task_id=NULL
    的会话级编排调用不误封。此前该端点原样返回=whack-a-mole 漏堵的第 9 端点。
    tamper：撤 conversations.py 的 cgate.redact_model_calls_by_task 接线 → 本测试 RED。"""
    import json as _json
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        db_path = tdp / "flai_os.db"
        app = create_app(
            agents_dir=REPO_ROOT / "agents", tools_dir=REPO_ROOT / "tools_impl",
            contracts_dir=REPO_ROOT / "contracts", db_path=db_path,
            uploads_dir=tdp / "up", task_runs_dir=tdp / "runs",
        )
        with TestClient(app) as client:
            seed_and_login(client, db_path)
            conn = get_conn(db_path)
            try:
                repos.create_conversation(conn, conversation_id="c1", agent_id="a", created_by="u")
                _mktask(conn, "st", classification="sensitive", status="failed", err="e")
                _mktask(conn, "it", classification="internal", status="completed")
                repos.record_model_call(conn, task_id="st", conversation_id="c1",
                                        model_profile="reasoning", model_name="glm", status="failed",
                                        request_summary="机密请求", response_summary="机密响应",
                                        error_message="机密错误含 grounding_failures")
                repos.record_model_call(conn, task_id="it", conversation_id="c1",
                                        model_profile="reasoning", model_name="glm", status="success",
                                        request_summary="普通请求", response_summary="普通响应")
                # 会话级编排调用（task_id=None）：导引路由官自身摘要，非工具产出，不遮蔽
                repos.record_model_call(conn, conversation_id="c1",
                                        model_profile="orchestrator", model_name="glm", status="success",
                                        request_summary="路由摘要", response_summary="路由结果")
            finally:
                conn.close()

            rows = client.get("/api/conversations/c1/model_calls").json()
            by_task: dict[Any, list[dict[str, Any]]] = {}
            for r in rows:
                by_task.setdefault(r.get("task_id"), []).append(r)

            # sensitive 任务行：summary/error 遮蔽 + content_withheld；元数据留存
            s = by_task["st"][0]
            assert s["request_summary"] is None and s["response_summary"] is None
            assert s["error_message"] is None and s["content_withheld"] is True
            assert s["model_profile"] == "reasoning"
            # internal 任务行：原样（不误封）
            i = by_task["it"][0]
            assert i["request_summary"] == "普通请求" and i.get("content_withheld") is not True
            # 会话级编排调用（task_id=None）：原样
            o = by_task[None][0]
            assert o["request_summary"] == "路由摘要" and o.get("content_withheld") is not True
            # 全响应正文无任一机密串泄漏
            assert "机密" not in _json.dumps(rows, ensure_ascii=False)


# ── 7. Codex R0 补漏 witness（P1-2 首写不可变 / P1-4 event 兜底 / P1-1 子行 / P1-3 未知工具） ──

def test_setter_immutable_first_write_wins(tmp_path: Path) -> None:
    """P1-2：set_task_data_classification 是 CAS 首写——已落库值不可变。二次调用（模拟
    二次 execute 按当前注册表重算）不覆盖，且返回**既有持久值**供 runtime 复用。
    tamper：把 setter 改回无条件 UPDATE → 第二个断言（仍 sensitive）RED。"""
    db = tmp_path / "d.db"; init_db(db)
    conn = get_conn(db)
    try:
        _mktask(conn, "t", classification=None, status="running")  # 列 NULL
        assert repos.set_task_data_classification(conn, "t", "sensitive") == "sensitive"
        # 二次以不同值调用 → 不覆盖，返回既有 sensitive（漂移换入口的 R1-B 复现被堵）
        assert repos.set_task_data_classification(conn, "t", "internal") == "sensitive"
        assert repos.get_task(conn, "t")["data_classification"] == "sensitive"
    finally:
        conn.close()


def test_null_fallback_by_content_rows_not_benign_events(tmp_path: Path) -> None:
    """P1-4 复核口径：NULL 兜底认**权威内容行**（tool_runs/model_calls/samples/files）+
    error_message，**不认**派生事件轨迹。承载外部数据的事件必伴生内容行（tool_failed↔
    tool_runs / model_call↔model_calls），故内容行足以兜住；而良性事件（feedback_received）
    单独落在未执行 NULL 任务上时**不得误封**（否则内部任务的用户反馈被遮，实测打回 4 例）。"""
    db = tmp_path / "d.db"; init_db(db)
    conn = get_conn(db)
    try:
        # a) NULL + model_call 内容行（外部摘要）→ 封（内容行兜住）
        _mktask(conn, "mc", classification=None, status="failed")
        repos.record_model_call(conn, task_id="mc", model_profile="reasoning", status="failed",
                                request_summary="外部机密摘要")
        assert cgate.is_sensitive_task(conn, repos.get_task(conn, "mc")) is True
        # b) NULL + 仅良性事件（feedback_received），无内容行 → **不误封**
        _mktask(conn, "fb", classification=None, status="completed")
        repos.append_event(conn, task_id="fb", agent_id="hello_agent",
                           event_type="feedback_received", level="info", message="用户反馈：good")
        assert cgate.is_sensitive_task(conn, repos.get_task(conn, "fb")) is False
    finally:
        conn.close()


def test_backfill_upgrades_child_rows(tmp_path: Path) -> None:
    """P1-1：回填把父任务升 sensitive 时，其误落 internal 的子 files/samples 一并升
    sensitive（下载门/固化门检子行，非父列）。tamper：删回填步骤 4 → 子行仍 internal，
    file/sample 断言 RED。"""
    db = tmp_path / "d.db"; init_db(db)
    conn = get_conn(db)
    try:
        _mktask(conn, "m", classification=None, status="completed")
        repos.record_tool_run(conn, task_id="m", tool_id="monitor_adapter_recon",
                              tool_version="0.1.1", mock=False, status="success", input_json={},
                              started_at="2026-07-12T00:00:00+00:00")
        repos.create_file(conn, file_id="f1", task_id="m", kind="output", filename="draft.json",
                          path="/x/draft.json", size_bytes=1, sha256="a", classification="internal")
        repos.record_sample(conn, task_id="m", agent_id="a", agent_version="0.1.0",
                            input_json={}, validation_status="success", classification="internal")
        repos.backfill_task_data_classification(conn, ["monitor_adapter_recon"],
                                                ["monitor_adapter_recon"])
        assert repos.get_task(conn, "m")["data_classification"] == "sensitive"
        assert conn.execute("SELECT classification FROM files WHERE id='f1'").fetchone()[0] == "sensitive"
        assert conn.execute(
            "SELECT classification FROM samples WHERE task_id='m'"
        ).fetchone()[0] == "sensitive"
    finally:
        conn.close()


def test_backfill_unknown_tool_failclosed(tmp_path: Path) -> None:
    """P1-3：tool_run 引用当前注册表不认识的工具（卸载/改名）→ fail-closed sensitive；
    引用已知 internal 工具 → internal（不误封）。"""
    db = tmp_path / "d.db"; init_db(db)
    conn = get_conn(db)
    try:
        _mktask(conn, "u", classification=None, status="completed")
        repos.record_tool_run(conn, task_id="u", tool_id="ghost_removed_tool", tool_version="1",
                              mock=True, status="success", input_json={},
                              started_at="2026-07-12T00:00:00+00:00")
        _mktask(conn, "k", classification=None, status="completed")
        repos.record_tool_run(conn, task_id="k", tool_id="mock_echo", tool_version="1",
                              mock=True, status="success", input_json={},
                              started_at="2026-07-12T00:00:00+00:00")
        repos.backfill_task_data_classification(
            conn, [], ["monitor_adapter_recon", "mock_echo"]
        )
        assert repos.get_task(conn, "u")["data_classification"] == "sensitive"  # 未知→封
        assert repos.get_task(conn, "k")["data_classification"] == "internal"   # 已知 internal→放
    finally:
        conn.close()


# ── 8. 端点补齐 witness（P2-2 review/cancel · P2-3 会话 tasks 端点） ─────────────

def _seal_endpoint_app(tmp_path: Path):
    db_path = tmp_path / "flai_os.db"
    app = create_app(
        agents_dir=REPO_ROOT / "agents", tools_dir=REPO_ROOT / "tools_impl",
        contracts_dir=REPO_ROOT / "contracts", db_path=db_path,
        uploads_dir=tmp_path / "up", task_runs_dir=tmp_path / "runs",
    )
    return app, db_path


def test_conversation_tasks_endpoint_seals(tmp_path: Path) -> None:
    """P2-3（Codex：8 端点表里的会话 tasks 此前无断言）：GET /conversations/{id}/tasks
    逐行遮蔽 sensitive 任务的 error_message。"""
    app, db_path = _seal_endpoint_app(tmp_path)
    with TestClient(app) as client:
        seed_and_login(client, db_path)
        conn = get_conn(db_path)
        try:
            repos.create_conversation(conn, conversation_id="cv", agent_id="a", created_by="u")
            _mktask(conn, "cs", classification="sensitive", status="failed", err="机密错误文本")
            conn.execute("UPDATE tasks SET conversation_id='cv' WHERE id='cs'")
        finally:
            conn.close()
        rows = client.get("/api/conversations/cv/tasks").json()
        row = [t for t in rows if t["id"] == "cs"][0]
        assert row["error_message"] is None and row["content_withheld"] is True


def test_review_and_cancel_seal_sensitive_task_row(tmp_path: Path) -> None:
    """P2-2：POST /tasks/{id}/review 与 /cancel 的响应任务行统一过门（sensitive→封 error_message）
    ——防「GET 封、mutation 漏」。以强制 sensitive 状态作防御性 witness（自然链路 error_message
    非外部内容，此处证「所有任务响应出场面一致封闭」的结构承诺）。"""
    app, db_path = _seal_endpoint_app(tmp_path)
    with TestClient(app) as client:
        seed_and_login(client, db_path)
        conn = get_conn(db_path)
        try:
            _mktask(conn, "rv", classification="sensitive", status="waiting_review", err=None)
            _mktask(conn, "cx", classification="sensitive", status="queued", err="机密取消前文本")
        finally:
            conn.close()
        # review reject → 响应任务行 error_message 遮蔽（reject_reason 亦经门）
        rv = client.post("/api/tasks/rv/review", json={"action": "reject", "comment": "no"}).json()
        assert rv.get("content_withheld") is True and rv["error_message"] is None
        # cancel → 响应任务行遮蔽
        cx = client.post("/api/tasks/cx/cancel").json()
        assert cx.get("content_withheld") is True and cx["error_message"] is None


# ── 9. Codex R1 witness 强度补强（端到端下载 403 · 写侧 wrapper 阻断） ──────────

def test_backfill_child_upgrade_blocks_real_download(tmp_path: Path) -> None:
    """P1-1 端到端（Codex R1）：不只断言子行列变 sensitive，而是真打 GET /files/{id}/download
    ——回填前 internal 不 403（文件缺→404），回填升子行后 sensitive → **真 403**。
    tamper：删回填步骤 4 子行升级 → 子行留 internal → 下载不 403 → 断言 RED。"""
    app, db_path = _seal_endpoint_app(tmp_path)
    with TestClient(app) as client:
        seed_and_login(client, db_path)
        conn = get_conn(db_path)
        try:
            _mktask(conn, "md", classification=None, status="completed")
            repos.record_tool_run(conn, task_id="md", tool_id="monitor_adapter_recon",
                                  tool_version="0.1.1", mock=False, status="success", input_json={},
                                  started_at="2026-07-12T00:00:00+00:00")
            repos.create_file(conn, file_id="fd", task_id="md", kind="output",
                              filename="draft.json", path="/nonexistent/draft.json",
                              size_bytes=1, sha256="a", classification="internal")
        finally:
            conn.close()
        # 回填前：internal → 过分级门（文件缺→非 403）
        assert client.get("/api/files/fd/download").status_code != 403
        conn = get_conn(db_path)
        try:
            repos.backfill_task_data_classification(conn, ["monitor_adapter_recon"],
                                                    ["monitor_adapter_recon"])
        finally:
            conn.close()
        # 回填后：子行升 sensitive → 下载门真 403
        assert client.get("/api/files/fd/download").status_code == 403


def test_job_wrapper_blocks_conversation_attribution(tmp_path: Path) -> None:
    """P1-5 写侧（Codex R1）：经 _ModelGatewayContext.chat 传 conversation_id，落库 model_call
    的 conversation_id 恒 NULL——wrapper `_sanitize` 剔除归因 kwargs，双归因行**造不出来**（读门
    之外的写侧纵深）。tamper：`_sanitize` 改成原样返回 kwargs → conversation_id 落库非 NULL → RED。"""
    from backend.app.runtime.runtime import _ModelGatewayContext
    db = tmp_path / "d.db"; init_db(db)
    conn = get_conn(db)
    try:
        _mktask(conn, "taskx", classification="sensitive", status="running")

        class _RecordingGateway:
            def chat(self, profile, messages, *, task_id=None, conversation_id=None,
                     agent_id=None, **kw):
                return repos.record_model_call(
                    conn, task_id=task_id, conversation_id=conversation_id, agent_id=agent_id,
                    model_profile=profile, status="success", request_summary="外部机密",
                )

        ctx = _ModelGatewayContext(_RecordingGateway(), conn, "taskx", "hello_agent")
        # workflow 试图把本 task 的模型调用归因到某会话
        ctx.chat("reasoning", [], conversation_id="sneaky-conv")
        row = conn.execute(
            "SELECT task_id, conversation_id FROM model_calls WHERE task_id='taskx'"
        ).fetchone()
        assert row[0] == "taskx"        # task 归因保留
        assert row[1] is None           # conversation 归因被剔除 → 无双归因行
    finally:
        conn.close()


def test_conversation_wrapper_blocks_task_attribution(tmp_path: Path) -> None:
    """P1-5 对称写侧（Codex R1 镜像）：会话 wrapper 同样钉死归因——workflow 塞 task_id 被剔除，
    落库 model_call 的 task_id 恒 NULL（只归因 conversation），双归因行两个方向都造不出。
    tamper：`_ConversationGatewayContext._ids` 改回 setdefault → task_id 落库非 NULL → RED。"""
    from backend.app.runtime.conversation import _ConversationGatewayContext
    db = tmp_path / "d.db"; init_db(db)
    conn = get_conn(db)
    try:
        repos.create_conversation(conn, conversation_id="cv2", agent_id="hello_agent", created_by="u")

        class _RecordingGateway:
            def chat(self, profile, messages, *, task_id=None, conversation_id=None,
                     agent_id=None, **kw):
                return repos.record_model_call(
                    conn, task_id=task_id, conversation_id=conversation_id, agent_id=agent_id,
                    model_profile=profile, status="success", request_summary="会话摘要",
                )

        ctx = _ConversationGatewayContext(_RecordingGateway(), "cv2", "hello_agent")
        ctx.chat("reasoning", [], task_id="sneaky-task")  # workflow 试图归因到某任务
        row = conn.execute(
            "SELECT task_id, conversation_id FROM model_calls WHERE conversation_id='cv2'"
        ).fetchone()
        assert row[1] == "cv2"          # conversation 归因保留
        assert row[0] is None           # task 归因被剔除 → 无双归因行
    finally:
        conn.close()
