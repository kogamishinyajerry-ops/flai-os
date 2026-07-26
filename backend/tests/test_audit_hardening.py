"""ADR-0013 审计硬化的跨切面回归。

覆盖（对应审计 findings）：
- 人工审核 gate fail-closed：字段缺失不再默认跳审（此前 truthiness fail-open，
  安全依赖 agent.schema.json required 耦合而非 gate 自证）。
- 失败样本沉淀（§18-Q7 最小落点）：collect_samples 型 Agent 的失败任务也落
  samples 行（validation_status='failed'）。
- 追溯读 API（§18-Q5 收口）：tool_runs / model_calls / samples 三只读端点。
- inputs 大小上限（DoS 面）。
- 工具契约：output_schema.required 缺 status 的 tool.yaml 注册期即拒（fail-open
  潜伏路径的契约层封堵）。
- M4 红线冻结：performance_disk_agent 换真实工具时 requires_human_review 必须
  已显式 True——「真实工程数值必须人工签发」不能只活在注释里。
- 上传入库失败清理已落盘 blob（孤儿文件）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import pytest
import yaml
from fastapi.testclient import TestClient

from backend.app.jobs.runner import JobRunner
from backend.app.runtime.package_snapshot import capture_agent_package
from backend.app.storage import repos
from backend.app.tools.registry import ToolRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]

_LLM_ENV_VARS = ("FLAI_LLM_BASE_URL", "FLAI_LLM_API_KEY", "FLAI_LLM_MODEL_REASONING", "FLAI_LLM_MODEL_FAST")


@pytest.fixture(autouse=True)
def _clean_llm_env(monkeypatch):
    for var in _LLM_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture()
def client(app_env) -> Iterator[TestClient]:
    c, _ = app_env
    yield c


def _create_and_run(client: TestClient, app, agent_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
    resp = client.post(
        "/api/tasks", json={"agent_id": agent_id, "inputs": inputs}
    )
    assert resp.status_code == 200, resp.text
    task_id = resp.json()["id"]
    runner = JobRunner(app.state.runtime, app.state.conn_factory)
    assert runner.run_once() is True
    return client.get(f"/api/tasks/{task_id}").json()


# ── 人工审核 gate fail-closed（宪法「安全 gate 判定一律 is True/is False」）──


def test_review_gate_fail_closed_when_flag_missing(
    app_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """requires_human_review 字段缺失（schema 之外的任何原因）→ 必须走
    waiting_review 而非静默 completed——错误方向只能是「多审」不能是「漏审」。
    此前 truthiness 判定下缺失即跳审（fail-open）。"""
    client, app = app_env
    registry = app.state.agent_registry
    published = registry.package_snapshot("hello_agent")
    assert published is not None
    assert (
        published.manifest["workflow"]["requires_human_review"] is False
    )  # 前置：正常态显式 False
    with published.materialized() as package_dir:
        yaml_path = package_dir / "agent.yaml"
        malformed = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        malformed["workflow"].pop("requires_human_review")
        yaml_path.write_text(
            yaml.safe_dump(malformed, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        malformed_snapshot = capture_agent_package(package_dir)

    real_snapshot_getter = registry.package_snapshot
    monkeypatch.setattr(
        registry,
        "package_snapshot",
        lambda agent_id: (
            malformed_snapshot
            if agent_id == "hello_agent"
            else real_snapshot_getter(agent_id)
        ),
    )

    task = _create_and_run(client, app, "hello_agent", {"name": "缺字段场景"})
    assert task["status"] == "waiting_review", (
        f"字段缺失必须 fail-closed 进 waiting_review，实得 {task['status']}"
    )


def test_review_gate_explicit_false_still_completes(app_env) -> None:
    """显式 False 才跳审：hello_agent 正常路径仍直达 completed（gate 不多拦）。"""
    client, app = app_env
    task = _create_and_run(client, app, "hello_agent", {"name": "正常路径"})
    assert task["status"] == "completed"


# ── 失败样本沉淀（§18-Q7 最小落点，ADR-0013 决策 7）─────────────────────────


def test_failure_sample_recorded_for_collect_samples_agent(app_env) -> None:
    """fta（collect_samples=true）无 key 失败 → samples 落 1 行
    validation_status='failed'，accepted_by_engineer 留 NULL（不冒充已定标）。"""
    client, app = app_env
    inputs = {
        "top_event": "供电完全丧失",
        "system_description": "双通道供电系统",
        "components": ["发电机A", "发电机B"],
    }
    task = _create_and_run(client, app, "fta_agent", inputs)
    assert task["status"] == "failed"

    samples = client.get(f"/api/tasks/{task['id']}/samples").json()
    assert len(samples) == 1
    assert samples[0]["validation_status"] == "failed"
    assert samples[0]["accepted_by_engineer"] is None
    assert "ModelConfigError" in samples[0]["output"]["error_message"]  # 缺 env=配置错子类
    assert samples[0]["input"] == inputs, "失败输入必须原样沉淀（未来评测反例素材）"


def test_validation_failure_also_records_sample(app_env) -> None:
    """输入校验失败同样沉淀（表单填错本身就是高价值反例数据）。"""
    client, app = app_env
    task = _create_and_run(client, app, "fta_agent", {"top_event": "只有顶事件"})
    assert task["status"] == "failed"
    samples = client.get(f"/api/tasks/{task['id']}/samples").json()
    assert len(samples) == 1 and samples[0]["validation_status"] == "failed"


# ── 追溯读 API（§18-Q5 收口）───────────────────────────────────────────────


def test_trace_read_apis_expose_versions(app_env) -> None:
    client, app = app_env
    task = _create_and_run(client, app, "hello_agent", {"name": "追溯"})
    assert task["status"] == "completed"
    task_id = task["id"]

    runs = client.get(f"/api/tasks/{task_id}/tool_runs").json()
    assert len(runs) >= 1
    assert runs[0]["tool_id"] == "mock_echo"
    assert runs[0]["tool_version"], "tool_runs 必须携带工具版本（Q5：输出可追溯到工具版本）"
    assert runs[0]["mock"] is True

    # hello 无 LLM：model_calls 为空数组（端点可用，不 404）
    assert client.get(f"/api/tasks/{task_id}/model_calls").json() == []

    # 未知任务三端点一律 404
    for ep in ("tool_runs", "model_calls", "samples"):
        assert client.get(f"/api/tasks/task_missing/{ep}").status_code == 404


def test_tool_runs_summary_bounded_counts(app_env) -> None:
    """批次二 Codex R0-P2 + 批次四 Codex R1-P2：/tasks/{id}/tool_runs/summary
    回 total/mock_count 两个计数 + by_tool 按工具分解（行数=distinct 工具数，
    有界聚合），绝不带 input/output/raw_path 内容键——核验段与 WorkLog mock
    徽的数据面按需最小化。与真实 run（hello_agent 的 mock_echo，mock=1）对账。"""
    client, app = app_env
    task = _create_and_run(client, app, "hello_agent", {"name": "计数投影"})
    assert task["status"] == "completed"

    # 多工具/多 run 夹具（Codex R2-P3）：真实 run（mock_echo，mock=1）之外再种
    # 第二个工具两条非 mock run——「行数=distinct 工具数」必须在多工具态机械成立，
    # 单工具单 run 夹具证不了分组唯一性。
    conn = app.state.conn_factory()
    try:
        for i in range(2):
            repos.record_tool_run(
                conn,
                task_id=task["id"],
                tool_id="probe_tool_b",
                tool_version="0.0.1",
                mock=False,
                status="success",
                input_json={},
                started_at=f"2026-07-16T00:00:0{i}+00:00",
                finished_at=f"2026-07-16T00:00:0{i + 1}+00:00",
            )
        conn.commit()
    finally:
        conn.close()

    summary = client.get(f"/api/tasks/{task['id']}/tool_runs/summary").json()
    runs = client.get(f"/api/tasks/{task['id']}/tool_runs").json()
    assert set(summary.keys()) == {"total", "mock_count", "by_tool"}, "计数投影绝不外带内容键"
    assert summary["total"] == len(runs) >= 3
    assert summary["mock_count"] == sum(1 for r in runs if r["mock"] is True) >= 1
    # by_tool：逐条只含 tool_id+两计数（元数据，无内容键）；与全量行按工具对账；
    # tool_id 严格唯一（重复返回同一聚合行必炸）且集合与全量行一致（≥2 工具）。
    tool_ids = [e["tool_id"] for e in summary["by_tool"]]
    assert len(tool_ids) == len(set(tool_ids)) >= 2, "by_tool 行数必须=distinct 工具数"
    assert set(tool_ids) == {r["tool_id"] for r in runs}
    for entry in summary["by_tool"]:
        assert set(entry.keys()) == {"tool_id", "total", "mock_count"}, "by_tool 绝不外带内容键"
        tool_rows = [r for r in runs if r["tool_id"] == entry["tool_id"]]
        assert entry["total"] == len(tool_rows) >= 1
        assert entry["mock_count"] == sum(1 for r in tool_rows if r["mock"] is True)
    probe_entry = next(e for e in summary["by_tool"] if e["tool_id"] == "probe_tool_b")
    assert probe_entry == {"tool_id": "probe_tool_b", "total": 2, "mock_count": 0}
    # 全局计数=分组求和（单查一致快照的派生关系）。
    assert summary["total"] == sum(e["total"] for e in summary["by_tool"])
    assert summary["mock_count"] == sum(e["mock_count"] for e in summary["by_tool"])

    # 零 run 任务：0/0/空表（不 404——任务在，计数就是 0）；未知任务 404。
    created = client.post("/api/tasks", json={"agent_id": "hello_agent", "inputs": {"name": "零run"}}).json()
    assert client.get(f"/api/tasks/{created['id']}/tool_runs/summary").json() == {
        "total": 0, "mock_count": 0, "by_tool": [],
    }
    assert client.get("/api/tasks/task_missing/tool_runs/summary").status_code == 404


def test_output_files_endpoint_projects_metadata_no_leak(app_env) -> None:
    """批B P1 修复：/tasks/{id}/output_files 只投影
    [{id, filename, size_bytes, data_classification}]，绝不含 path/sha256/uploaded_by。
    hello_agent 产出的 internal 文件 + 手工插入的 sensitive 文件都要能看见——分级本身
    是元数据（前端据此决定要不要渲染下载链接），真下载仍走 /files/{id}/download 原
    分级门，本端点不代管下载授权。"""
    client, app = app_env
    task = _create_and_run(client, app, "hello_agent", {"name": "产物投影"})
    assert task["status"] == "completed"
    task_id = task["id"]
    assert task["output_file_ids"], "hello_agent 必须产出至少一个文件"
    internal_file_id = task["output_file_ids"][0]

    # 手工插入一个 sensitive 分级产物并挂到同一任务，模拟受限产物场景。
    conn = app.state.conn_factory()
    try:
        sensitive_file = repos.create_file(
            conn,
            file_id="file_sensitive_test",
            task_id=task_id,
            kind="output",
            filename="受限产物.csv",
            path="/nonexistent/受限产物.csv",
            size_bytes=42,
            sha256="0" * 64,
            classification="sensitive",
        )
        repos.set_task_outputs(conn, task_id, [*task["output_file_ids"], sensitive_file["id"]])
    finally:
        conn.close()

    projection = client.get(f"/api/tasks/{task_id}/output_files").json()
    assert len(projection) == 2
    by_id = {row["id"]: row for row in projection}

    assert by_id[internal_file_id]["data_classification"] == "internal"
    assert by_id["file_sensitive_test"]["data_classification"] == "sensitive"
    assert by_id["file_sensitive_test"]["filename"] == "受限产物.csv"
    assert by_id["file_sensitive_test"]["size_bytes"] == 42

    # 绝不泄漏 path/sha256/uploaded_by/kind——投影只允许这四个约定字段。
    for row in projection:
        assert set(row.keys()) == {"id", "filename", "size_bytes", "data_classification"}

    assert client.get("/api/tasks/task_missing/output_files").status_code == 404


# ── 单卡交付摘要（治理审 R1 P1 修复）──────────────────────────────────────


def test_delivery_summary_aggregates_model_calls_and_batch(app_env) -> None:
    """混合 token known/missing/failed 的 model_calls + 一条 summary_generated
    agent_log 事件 → 聚合精确。tamper：拆掉 token 折算/status 分支任一维，
    夹具里对应的反例行会让断言必红。"""
    client, app = app_env
    task = _create_and_run(client, app, "hello_agent", {"name": "交付摘要"})
    task_id = task["id"]

    conn = app.state.conn_factory()
    try:
        # 4 条 model_calls：成功+total_tokens known / 成功+prompt+completion known /
        # 成功+token_usage 缺失(unknown) / 失败(status=failed，不计入 ok，token 也可能缺)。
        repos.record_model_call(
            conn, task_id=task_id, model_profile="reasoning", status="success",
            token_usage_json={"total_tokens": 100},
        )
        repos.record_model_call(
            conn, task_id=task_id, model_profile="reasoning", status="success",
            token_usage_json={"prompt_tokens": 20, "completion_tokens": 5},
        )
        repos.record_model_call(
            conn, task_id=task_id, model_profile="reasoning", status="success",
            token_usage_json=None,
        )
        repos.record_model_call(
            conn, task_id=task_id, model_profile="reasoning", status="failed",
            token_usage_json=None,
        )
        repos.append_event(
            conn, task_id=task_id, event_type="agent_log", level="info",
            message="批量收尾", payload={"workflow_event_type": "summary_generated", "ok_count": 7, "failed_count": 2},
        )
    finally:
        conn.close()

    body = client.get(f"/api/tasks/{task_id}/delivery_summary").json()
    assert body["mc_total"] == 4
    assert body["mc_ok"] == 3
    assert body["mc_failed"] == 1
    assert body["token_sum"] == 125  # 100 + (20+5)
    assert body["token_known"] == 2
    assert body["token_missing"] == 2
    assert body["batch_ok"] == 7
    assert body["batch_failed"] == 2


def test_delivery_summary_no_batch_event_returns_null(app_env) -> None:
    """非批量 Agent 任务（hello_agent 不发 summary_generated）→ batch_ok/failed
    诚实返回 null，不冒充有批量结果；无 model_calls 时 mc_total=0 且不算 0 token。"""
    client, app = app_env
    task = _create_and_run(client, app, "hello_agent", {"name": "非批量"})
    body = client.get(f"/api/tasks/{task['id']}/delivery_summary").json()
    assert body["mc_total"] == 0
    assert body["mc_ok"] == 0
    assert body["mc_failed"] == 0
    assert body["token_known"] == 0
    assert body["token_missing"] == 0
    assert body["batch_ok"] is None
    assert body["batch_failed"] is None


def test_delivery_summary_beyond_50_event_window_stays_null(app_env) -> None:
    """有界扫描的诚实取舍（端点 docstring 明示）：summary_generated 若被 50 条
    更新的 agent_log 挤出窗口，宁缺毋错返回 null，不做无界扫描换假完整。"""
    client, app = app_env
    task = _create_and_run(client, app, "hello_agent", {"name": "超窗口"})
    task_id = task["id"]

    conn = app.state.conn_factory()
    try:
        repos.append_event(
            conn, task_id=task_id, event_type="agent_log", level="info",
            message="批量收尾", payload={"workflow_event_type": "summary_generated", "ok_count": 1, "failed_count": 0},
        )
        for i in range(50):  # 50 条更新的 agent_log 把上面那条挤出 DESC LIMIT 50 窗口
            repos.append_event(
                conn, task_id=task_id, event_type="agent_log", level="info",
                message=f"噪声事件 {i}", payload={"workflow_event_type": "noise"},
            )
    finally:
        conn.close()

    body = client.get(f"/api/tasks/{task_id}/delivery_summary").json()
    assert body["batch_ok"] is None
    assert body["batch_failed"] is None


def test_delivery_summary_unknown_task_404(app_env) -> None:
    client, _ = app_env
    assert client.get("/api/tasks/task_missing/delivery_summary").status_code == 404


# ── inputs 大小上限（DoS 面）──────────────────────────────────────────────


def test_task_inputs_size_cap_422(client: TestClient) -> None:
    big = {"blob": "x" * (300 * 1024)}
    resp = client.post("/api/tasks", json={"agent_id": "hello_agent", "inputs": big})
    assert resp.status_code == 422
    assert "上限" in resp.text


# ── 工具契约：缺 status 的 output_schema 注册期即拒 ────────────────────────


def test_tool_registry_rejects_output_schema_missing_status(tmp_path) -> None:
    """tool.schema.json（ADR-0013）强制 output_schema.required 含 status——
    漏声明的工具包在 scan 期被软拒（errors 记录，不注册），封死「缺 status
    默认 success」的 fail-open 潜伏路径的入口。"""
    good = yaml.safe_load((REPO_ROOT / "tools_impl" / "mock_tools" / "tool.yaml").read_text(encoding="utf-8"))
    bad = json.loads(json.dumps(good))  # 深拷贝
    bad["id"] = "no_status_tool"
    bad["output_schema"]["required"] = ["echoed"]  # 刻意去掉 status

    pkg = tmp_path / "no_status_tool"
    pkg.mkdir()
    (pkg / "tool.yaml").write_text(yaml.safe_dump(bad, allow_unicode=True), encoding="utf-8")

    registry = ToolRegistry(tmp_path, REPO_ROOT / "contracts" / "tool.schema.json")
    registry.scan()
    assert registry.get("no_status_tool") is None, "缺 status 契约的工具不得注册"
    assert len(registry.errors) == 1
    assert "status" in registry.errors[0]["error"]


# ── M4 红线冻结（ADR-0013 决策 6）─────────────────────────────────────────

# performance_disk_agent 当前（M3 mock 阶段）的已知工具白名单。M4 把 mock 换成
# 真实性能盘工具时本集合必然变化——届时下方断言强制 requires_human_review 已
# 显式 True，否则本测试红：真实工程数值绝不允许静默自动 completed。
_PERF_DISK_MOCK_TOOLSET = frozenset({"excel_case_parser", "performance_disk_mock", "excel_summary_writer"})


def test_m4_red_line_real_tools_require_human_review() -> None:
    data = yaml.safe_load(
        (REPO_ROOT / "agents" / "performance_disk_agent" / "agent.yaml").read_text(encoding="utf-8")
    )
    tools = frozenset(data.get("tools") or [])
    requires_review = data["workflow"]["requires_human_review"]
    if tools == _PERF_DISK_MOCK_TOOLSET:
        # mock 阶段：false 是诚实的（输出五处标注无工程意义）
        assert requires_review is False
    else:
        assert requires_review is True, (
            "M4 红线：performance_disk_agent 工具白名单已偏离 mock 集合"
            f"（现={sorted(tools)}），真实工程结论必须人工签发——"
            "requires_human_review 必须显式 true（agent.yaml 描述第 14 行的承诺）"
        )


# ── 上传入库失败清理孤儿 blob ─────────────────────────────────────────────


def test_upload_orphan_blob_cleaned_on_db_failure(app_env, monkeypatch, tmp_path) -> None:
    client, app = app_env
    uploads_dir = app.state.uploads_dir

    def boom(*args, **kwargs):
        raise RuntimeError("模拟入库失败")

    from backend.app.api import files as files_api

    monkeypatch.setattr(files_api.repos, "create_file", boom)
    with pytest.raises(RuntimeError):
        client.post("/api/files/upload", files={"file": ("orphan.txt", b"data")})

    leftovers = [p for p in Path(uploads_dir).rglob("*") if p.is_file()]
    assert leftovers == [], f"入库失败必须回收已落盘 blob，实存 {leftovers}"


# ── 迁移并发启动安全（Codex R1-P1）────────────────────────────────────────
# API 进程与 Job Runner 进程都在启动时调 init_db；对 pre-ADR-0013 存量库，
# check-then-ALTER 若不持写锁，双方可同时观察到「列缺失」，输家撞
# duplicate column name 启动失败。以下两测：一条确定性时序复现，一条真并发扫。


def _make_legacy_db(db_path) -> None:
    """造 pre-ADR-0013 老库：重建 model_calls 为不含 conversation_id 的旧形状。

    不用 `ALTER TABLE ... DROP COLUMN`（需 SQLite ≥3.35，超出仓声明的环境下限，
    Codex R2-P3）——改用任何版本都支持的 rebuild-rename（AS SELECT 丢约束无妨，
    迁移探测只看列名）。"""
    from backend.app.storage import db as db_mod

    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        legacy_cols = ", ".join(
            r[1] for r in conn.execute("PRAGMA table_info(model_calls)")
            if r[1] != "conversation_id"
        )
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(f"CREATE TABLE model_calls_legacy AS SELECT {legacy_cols} FROM model_calls")
        conn.execute("DROP TABLE model_calls")
        conn.execute("ALTER TABLE model_calls_legacy RENAME TO model_calls")
        conn.execute("COMMIT")
        cols = {r[1] for r in conn.execute("PRAGMA table_info(model_calls)")}
        assert "conversation_id" not in cols
    finally:
        conn.close()


def _model_calls_columns(db_path) -> set[str]:
    from backend.app.storage import db as db_mod

    conn = db_mod.get_conn(db_path)
    try:
        return {r[1] for r in conn.execute("PRAGMA table_info(model_calls)")}
    finally:
        conn.close()


def test_migration_survives_rival_process_altering_mid_flight(tmp_path, monkeypatch) -> None:
    """确定性复现「另一进程在探测与 ALTER 之间抢先完成迁移」的时序。

    编排（trace 卡点，严格 happens-before，无 flake）：
    - loser 线程跑真 init_db；其连接挂 trace callback，走到本列的 ALTER 语句时
      先放行 rival、再等 rival 结束才继续；
    - rival（模拟另一进程）在该卡点直接对库 ALTER 加列并提交。
    旧实现（锁外探测）：loser 恢复后 ALTER 撞 duplicate column name → init_db 崩。
    新实现（BEGIN IMMEDIATE 锁内探测）：loser 卡点时已持写锁，rival 的 ALTER 被
    锁拒之门外（短 timeout 快速失败），loser 独自完成迁移 → 无异常。
    两种实现下本测均确定性终止；仅旧实现变红——即 tamper 必咬点。
    """
    import sqlite3
    import threading

    from backend.app.storage import db as db_mod

    db_path = tmp_path / "legacy.db"
    _make_legacy_db(db_path)

    about_to_alter = threading.Event()
    rival_done = threading.Event()
    real_get_conn = db_mod.get_conn

    def instrumented_get_conn(path):
        conn = real_get_conn(path)

        def trace(stmt: str) -> None:
            if "ALTER TABLE model_calls" in stmt:
                about_to_alter.set()
                rival_done.wait(timeout=10)

        conn.set_trace_callback(trace)
        return conn

    monkeypatch.setattr(db_mod, "get_conn", instrumented_get_conn)

    loser_errors: list[Exception] = []

    def loser() -> None:
        try:
            db_mod.init_db(db_path)
        except Exception as exc:  # noqa: BLE001 —— 断言用，需捕获一切
            loser_errors.append(exc)

    t = threading.Thread(target=loser)
    t.start()
    assert about_to_alter.wait(timeout=10), "loser 未走到迁移 ALTER——测试前提失效"

    # rival：模拟另一进程的迁移。短 timeout——新实现下 loser 正持写锁，这里
    # 应当快速失败；旧实现下 loser 无锁，这里应当成功。两种结果都放行，
    # 裁决交给 loser 是否幸存。
    rival = sqlite3.connect(str(db_path), isolation_level=None, timeout=1.0)
    try:
        rival.execute("ALTER TABLE model_calls ADD COLUMN conversation_id TEXT")
    except sqlite3.OperationalError:
        pass  # 新实现：被 loser 的写锁挡住——这正是防御生效
    finally:
        rival.close()
        rival_done.set()

    t.join(timeout=15)
    assert not t.is_alive(), "loser init_db 未终止"
    assert loser_errors == [], (
        f"并发迁移下 init_db 必须幸存（锁内复查/容错），实际崩了：{loser_errors!r}"
    )
    assert "conversation_id" in _model_calls_columns(db_path)


def test_migration_concurrent_init_db_sweep(tmp_path) -> None:
    """黑盒并发扫：多线程 barrier 同发真 init_db 于同一老库，全部必须幸存。

    单轮竞态窗口窄（微秒级），固定 8 轮 × 3 线程作为常驻回归网——新实现下
    确定性全绿（写锁串行化）；配合上面的确定性时序测互为表里。
    """
    import threading

    from backend.app.storage import db as db_mod

    for round_no in range(8):
        db_path = tmp_path / f"legacy_{round_no}.db"
        _make_legacy_db(db_path)
        barrier = threading.Barrier(3)
        errors: list[Exception] = []

        def racer() -> None:
            barrier.wait()
            try:
                db_mod.init_db(db_path)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=racer) for _ in range(3)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(timeout=30)
        assert errors == [], f"round {round_no}: 并发 init_db 崩溃 {errors!r}"
        assert "conversation_id" in _model_calls_columns(db_path)


def test_delivery_summary_sensitive_task_suppresses_batch_fields(app_env) -> None:
    """ADR-0025 一致封闭回归（Codex R2-P1）：/events 对 sensitive 任务遮蔽
    summary_generated payload，delivery_summary 若照读事件 payload 即重开被封
    数据面。sensitive 任务：批量字段必 null（即便事件真实存在）；model_calls
    计数/token 元数据（与内容遮蔽面正交）照常返回。tamper：拆掉实现里的
    is_sensitive_task 门，本测必红。"""
    client, app = app_env
    task = _create_and_run(client, app, "hello_agent", {"name": "敏感批量"})
    task_id = task["id"]
    conn = app.state.conn_factory()
    try:
        repos.record_model_call(
            conn, task_id=task_id, model_profile="reasoning", status="success",
            token_usage_json={"total_tokens": 42},
        )
        repos.append_event(
            conn, task_id=task_id, event_type="agent_log", level="info",
            message="批量收尾", payload={"workflow_event_type": "summary_generated", "ok_count": 9, "failed_count": 1},
        )
        conn.execute(
            "UPDATE tasks SET data_classification = 'sensitive' WHERE id = ?", (task_id,)
        )
        conn.commit()
    finally:
        conn.close()

    body = client.get(f"/api/tasks/{task_id}/delivery_summary").json()
    assert body["batch_ok"] is None       # 事件存在但被门封——绝不外泄
    assert body["batch_failed"] is None
    assert body["mc_total"] == 1          # 元数据聚合不受内容遮蔽面影响
    assert body["token_sum"] == 42
