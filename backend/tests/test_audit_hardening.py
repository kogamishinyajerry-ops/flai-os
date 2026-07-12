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


def test_review_gate_fail_closed_when_flag_missing(app_env) -> None:
    """requires_human_review 字段缺失（schema 之外的任何原因）→ 必须走
    waiting_review 而非静默 completed——错误方向只能是「多审」不能是「漏审」。
    此前 truthiness 判定下缺失即跳审（fail-open）。"""
    client, app = app_env
    agent = app.state.agent_registry.get("hello_agent")
    assert agent["workflow"]["requires_human_review"] is False  # 前置：正常态显式 False
    removed = agent["workflow"].pop("requires_human_review")
    try:
        task = _create_and_run(client, app, "hello_agent", {"name": "缺字段场景"})
        assert task["status"] == "waiting_review", (
            f"字段缺失必须 fail-closed 进 waiting_review，实得 {task['status']}"
        )
    finally:
        agent["workflow"]["requires_human_review"] = removed  # 还原，避免串扰


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
    assert "ModelUpstreamError" in samples[0]["output"]["error_message"]
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
