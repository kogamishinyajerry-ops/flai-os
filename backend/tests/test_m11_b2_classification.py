"""M11-B2 数据分级标记轴（ADR-0021）验收 witness。

覆盖 ADR-0021 验收标准 1-10（#11 internal 回归=既有全量测试套本身）：
上传契约/下载门 allowlist/迁移 #6 回填/污点传播四态（分支①②③+缺失记录）/
固化门双 witness（自然链路+DB 直插未来态）/失败样本传播（F6）。

纪律：传播 witness 走真跑链路（API 上传 → 任务 → runtime.execute），不打桩；
固化门自然链路 witness 必须断言拒绝理由是**分级语义**文案（非「含输入文件」
技术门文案）——门序（D5）是本轴的承重设计，文案断言即门序 witness。
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pytest
import yaml
from fastapi.testclient import TestClient

from conftest import TEST_DISPLAY_NAME, seed_and_login

from backend.app.main import create_app
from backend.app.runtime.runtime import (
    _knowledge_classification,
    _task_input_classification,
)
from backend.app.storage import repos
from backend.app.storage.db import get_conn, init_db

REPO_ROOT = Path(__file__).resolve().parents[2]

# 复用 M10 治理测试的环境构造（governed_agent：collect_samples=true +
# requires_human_review=true）与任务/审核/固化 helpers——同一条治理链路，
# 本文件只叠加分级轴断言。pytest 从模块命名空间解析被 import 的 fixture。
from test_m10_governance import (  # noqa: F401
    GovernanceEnv,
    _fix_sample,
    _reviewed_sample,
    _samples_for_task,
    governance_env,
)


def _upload(
    env: GovernanceEnv, *, classification: str | None = None, content: bytes = b"payload"
) -> Any:
    data = {} if classification is None else {"classification": classification}
    return env.client.post(
        "/api/files/upload",
        files={"file": ("input.txt", content, "text/plain")},
        data=data,
    )


def _create_and_run_task(
    env: GovernanceEnv, *, inputs: dict[str, Any], input_file_ids: list[str]
) -> tuple[str, dict[str, Any]]:
    created = env.client.post(
        "/api/tasks",
        json={
            "agent_id": "governed_agent",
            "inputs": inputs,
            "input_file_ids": input_file_ids,
        },
    )
    assert created.status_code == 200, created.text
    task_id = created.json()["id"]
    conn = env.app.state.conn_factory()
    try:
        claimed = repos.claim_next_queued(conn)
    finally:
        conn.close()
    assert claimed is not None and claimed["id"] == task_id
    result = env.app.state.runtime.execute(task_id)
    return task_id, result


def _file_rows_for_task(env: GovernanceEnv, task_id: str) -> list[dict[str, Any]]:
    conn = env.app.state.conn_factory()
    try:
        rows = conn.execute(
            "SELECT * FROM files WHERE task_id = ? AND kind = 'output'", (task_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _set_file_classification(env: GovernanceEnv, file_id: str, value: str) -> None:
    """DB 直插坏值/未来态构造（witness 用，绕过 API 契约是本测试的手段而非漏洞）。"""
    conn = env.app.state.conn_factory()
    try:
        cur = conn.execute(
            "UPDATE files SET classification = ? WHERE id = ?", (value, file_id)
        )
        assert cur.rowcount == 1
    finally:
        conn.close()


# ── 验收 #1：上传缺省/声明 + 下载门 + uploaded_by ────────────────────────


def test_upload_default_internal_download_ok_and_uploaded_by(
    governance_env: GovernanceEnv,
) -> None:
    resp = _upload(governance_env)
    assert resp.status_code == 200, resp.text
    record = resp.json()
    assert record["classification"] == "internal"
    assert record["uploaded_by"] == TEST_DISPLAY_NAME

    download = governance_env.client.get(f"/api/files/{record['id']}/download")
    assert download.status_code == 200
    assert download.content == b"payload"


def test_upload_sensitive_download_403(governance_env: GovernanceEnv) -> None:
    resp = _upload(governance_env, classification="sensitive")
    assert resp.status_code == 200, resp.text
    record = resp.json()
    assert record["classification"] == "sensitive"

    download = governance_env.client.get(f"/api/files/{record['id']}/download")
    assert download.status_code == 403
    assert "分级" in download.json()["detail"]


# ── 验收 #2：非法值 422 不入库不落盘（F7）─────────────────────────────────


def test_upload_illegal_classification_rejected_no_disk_no_db(
    governance_env: GovernanceEnv,
) -> None:
    uploads_dir: Path = governance_env.app.state.uploads_dir
    before_dirs = set(uploads_dir.glob("*")) if uploads_dir.is_dir() else set()

    resp = _upload(governance_env, classification="public")
    assert resp.status_code == 422
    assert "classification" in resp.json()["detail"]

    after_dirs = set(uploads_dir.glob("*")) if uploads_dir.is_dir() else set()
    assert after_dirs == before_dirs, "非法分级值不得产生任何落盘目录（孤儿 blob）"
    conn = governance_env.app.state.conn_factory()
    try:
        n = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    finally:
        conn.close()
    assert n == 0


# ── 验收 #3：DB 坏值下载门 allowlist ─────────────────────────────────────


def test_db_bad_classification_value_download_403(
    governance_env: GovernanceEnv,
) -> None:
    record = _upload(governance_env).json()
    _set_file_classification(governance_env, record["id"], "weird")

    download = governance_env.client.get(f"/api/files/{record['id']}/download")
    assert download.status_code == 403, "未知分级值必须 fail-closed（allowlist internal）"


# ── 验收 #4：迁移 #6 存量回填 + 幂等 ─────────────────────────────────────


def test_legacy_db_migration_backfills_internal(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    # pre-ADR-0021 存量表形态（无 classification/uploaded_by），各插一行存量数据
    conn.execute(
        """CREATE TABLE files (
            id TEXT PRIMARY KEY, task_id TEXT, kind TEXT NOT NULL,
            filename TEXT NOT NULL, path TEXT NOT NULL,
            size_bytes INTEGER NOT NULL, sha256 TEXT NOT NULL, created_at TEXT NOT NULL)"""
    )
    conn.execute(
        "INSERT INTO files VALUES ('f1', NULL, 'input', 'a.txt', '/x/a.txt', 1, 'aa', '2026-01-01')"
    )
    conn.execute(
        """CREATE TABLE samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
            agent_id TEXT NOT NULL, agent_version TEXT NOT NULL,
            tool_id TEXT, tool_version TEXT, case_id TEXT,
            input_json TEXT NOT NULL, output_json TEXT,
            raw_input_path TEXT, raw_output_path TEXT,
            validation_status TEXT, accepted_by_engineer INTEGER, created_at TEXT NOT NULL)"""
    )
    conn.execute(
        "INSERT INTO samples (task_id, agent_id, agent_version, input_json, created_at)"
        " VALUES ('t1', 'a1', '0.1.0', '{}', '2026-01-01')"
    )
    conn.commit()
    conn.close()

    init_db(db_path)
    init_db(db_path)  # 幂等：重复启动不炸

    conn = get_conn(db_path)
    try:
        f = conn.execute("SELECT classification, uploaded_by FROM files WHERE id='f1'").fetchone()
        assert f["classification"] == "internal", "存量文件必须回填 internal（如实标注）"
        assert f["uploaded_by"] is None, "存量行 uploaded_by 留 NULL（自报时代数据不冒充有追溯）"
        s = conn.execute("SELECT classification FROM samples WHERE task_id='t1'").fetchone()
        assert s["classification"] == "internal"
    finally:
        conn.close()


# ── 验收 #5：传播分支①真跑链路（sensitive 输入 → 产物/样本 → 下载 403）────


def test_propagation_sensitive_input_taints_outputs_and_samples(
    governance_env: GovernanceEnv,
) -> None:
    file_id = _upload(governance_env, classification="sensitive").json()["id"]
    task_id, result = _create_and_run_task(
        governance_env, inputs={"name": "分级"}, input_file_ids=[file_id]
    )
    assert result["status"] == "waiting_review", result

    outputs = _file_rows_for_task(governance_env, task_id)
    assert len(outputs) >= 1, "governed_agent 应产出至少一个产物文件（链路前提）"
    assert all(row["classification"] == "sensitive" for row in outputs) is True, (
        "sensitive 输入的任务产物不得洗白为 internal"
    )
    for row in outputs:
        assert row["uploaded_by"] is None, "runtime 产物非人工标注场景，uploaded_by 留 NULL"
        download = governance_env.client.get(f"/api/files/{row['id']}/download")
        assert download.status_code == 403, "sensitive 产物下载必须被 D4 门拒绝"

    samples = _samples_for_task(governance_env, task_id)
    assert len(samples) == 1
    assert samples[0]["classification"] == "sensitive"


# ── 验收 #6：缺失输入记录 fail-closed ────────────────────────────────────


def test_missing_input_record_derives_sensitive(governance_env: GovernanceEnv) -> None:
    conn = governance_env.app.state.conn_factory()
    try:
        derived = _task_input_classification(conn, {"input_file_ids": ["ghost-id"]})
    finally:
        conn.close()
    assert derived == "sensitive", "记录缺失=出处不可考，必须宁严勿洗白"

    # 真跑链路：不存在的 file_id → 输入完整性校验失败 → failed，失败样本仍 sensitive
    task_id, result = _create_and_run_task(
        governance_env, inputs={"name": "缺失"}, input_file_ids=["ghost-id"]
    )
    assert result["status"] == "failed"
    samples = _samples_for_task(governance_env, task_id)
    assert len(samples) == 1
    assert samples[0]["classification"] == "sensitive"


# ── 验收 #7：传播分支②（坏值输入 → 派生 sensitive）───────────────────────


def test_propagation_unknown_value_input_derives_sensitive(
    governance_env: GovernanceEnv,
) -> None:
    file_id = _upload(governance_env).json()["id"]
    _set_file_classification(governance_env, file_id, "weird")

    task_id, result = _create_and_run_task(
        governance_env, inputs={"name": "坏值"}, input_file_ids=[file_id]
    )
    assert result["status"] == "waiting_review", result
    outputs = _file_rows_for_task(governance_env, task_id)
    assert len(outputs) >= 1
    assert all(row["classification"] == "sensitive" for row in outputs) is True
    assert _samples_for_task(governance_env, task_id)[0]["classification"] == "sensitive"


# ── 验收 #8：传播分支③正向（无输入文件 → 显式 internal）──────────────────


def test_no_input_files_outputs_and_samples_internal(
    governance_env: GovernanceEnv,
) -> None:
    task_id, result = _create_and_run_task(
        governance_env, inputs={"name": "无文件"}, input_file_ids=[]
    )
    assert result["status"] == "waiting_review", result
    outputs = _file_rows_for_task(governance_env, task_id)
    assert len(outputs) >= 1
    assert all(row["classification"] == "internal" for row in outputs) is True
    assert _samples_for_task(governance_env, task_id)[0]["classification"] == "internal"

    # internal 产物下载放行（#1 之外再钉一次「分支③不误伤」）
    download = governance_env.client.get(f"/api/files/{outputs[0]['id']}/download")
    assert download.status_code == 200


# ── 验收 #9：固化门双 witness ────────────────────────────────────────────


def test_curation_natural_chain_sensitive_sample_rejected_by_classification_gate(
    governance_env: GovernanceEnv,
) -> None:
    """9a 端到端自然链路：sensitive 输入 → 样本 → approve → 固化 422。

    拒绝理由必须是**分级语义**文案——若命中「含输入文件」技术门文案，说明
    门序（ADR-0021 D5：分级门在旧门之前）被破坏，本测试即咬。
    """
    file_id = _upload(governance_env, classification="sensitive").json()["id"]
    task_id, result = _create_and_run_task(
        governance_env, inputs={"name": "固化"}, input_file_ids=[file_id]
    )
    assert result["status"] == "waiting_review"
    reviewed = governance_env.client.post(
        f"/api/tasks/{task_id}/review", json={"action": "approve", "comment": "B2 测试"}
    )
    assert reviewed.status_code == 200, reviewed.text
    sample = _samples_for_task(governance_env, task_id)[0]
    assert sample["accepted_by_engineer"] is True
    assert sample["classification"] == "sensitive"

    before = set(governance_env.governed_cases_dir.glob("*.json"))
    resp = _fix_sample(governance_env, sample["id"])
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert "分级" in detail and "非 internal" in detail, (
        f"拒绝理由必须是分级门文案（门序 witness），实得：{detail!r}"
    )
    assert set(governance_env.governed_cases_dir.glob("*.json")) == before, (
        "拒绝固化后包目录不得有新文件落盘"
    )


def test_curation_db_injected_sensitive_sample_rejected(
    governance_env: GovernanceEnv,
) -> None:
    """9b 未来改级态（DB 直插构造）：无输入文件的 sensitive 样本同样被拒。"""
    _, sample = _reviewed_sample(governance_env, action="approve")
    conn = governance_env.app.state.conn_factory()
    try:
        cur = conn.execute(
            "UPDATE samples SET classification='sensitive' WHERE id = ?", (sample["id"],)
        )
        assert cur.rowcount == 1
    finally:
        conn.close()

    before = set(governance_env.governed_cases_dir.glob("*.json"))
    resp = _fix_sample(governance_env, sample["id"])
    assert resp.status_code == 422
    assert "分级" in resp.json()["detail"]
    assert set(governance_env.governed_cases_dir.glob("*.json")) == before


# ── 知识轴（Codex R0-P1）：restricted 知识库派生产物不得洗白 ──────────────


class _StubScopeRegistry:
    def __init__(self, scopes: dict[str, dict[str, Any]]) -> None:
        self._scopes = scopes

    def get(self, scope_id: str) -> dict[str, Any] | None:
        return self._scopes.get(scope_id)


@pytest.mark.parametrize(
    ("enabled", "conf", "expected"),
    [
        (True, "restricted", "sensitive"),
        (True, "department", "internal"),
        (True, "public_internal", "internal"),
        (True, "weird_level", "sensitive"),  # 未知密级 fail-closed
        (False, "restricted", "internal"),  # enabled 非 True 不构成访问面
    ],
)
def test_knowledge_classification_matrix(enabled: bool, conf: str, expected: str) -> None:
    agent = {"knowledge": {"enabled": enabled, "scopes": ["s1"]}}
    registry = _StubScopeRegistry({"s1": {"scope_id": "s1", "confidentiality": conf}})
    assert _knowledge_classification(agent, registry) == expected


def test_knowledge_classification_unregistered_scope_and_missing_registry() -> None:
    agent = {"knowledge": {"enabled": True, "scopes": ["ghost"]}}
    assert _knowledge_classification(agent, _StubScopeRegistry({})) == "sensitive"
    assert _knowledge_classification(agent, None) == "sensitive"


@contextmanager
def _knowledge_env(tmp_path: Path, *, confidentiality: str) -> Iterator[tuple[TestClient, Any]]:
    """真链路环境 builder：hello 系 job Agent 绑指定密级知识库（无输入文件）。

    workflow 本身不检索——派生只看 agent.yaml 声明 + scope 密级，这正是
    Codex R0-P1 的攻击面：能接触 restricted 语料的 Agent，其一切产物都
    必须按可能携带受限内容处理，不依赖「它这次真的检索了没有」。
    """
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    pkg = agents_dir / "knowledge_taint_agent"
    shutil.copytree(
        REPO_ROOT / "agents" / "hello_agent", pkg,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    manifest = yaml.safe_load((pkg / "agent.yaml").read_text(encoding="utf-8"))
    manifest["id"] = "knowledge_taint_agent"
    manifest["knowledge"] = {"enabled": True, "scopes": ["witness_scope"]}
    (pkg / "agent.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8"
    )

    knowledge_dir = tmp_path / "knowledge"
    scope = knowledge_dir / "witness_scope"
    (scope / "docs").mkdir(parents=True)
    (scope / "scope.yaml").write_text(yaml.safe_dump({
        "scope_id": "witness_scope",
        "name": f"{confidentiality} 密级 witness 语料（tmp）",
        "kind": "document",
        "source": "file_dir",
        "path_or_uri": "docs",
        "confidentiality": confidentiality,
        "owner": "test",
    }, allow_unicode=True), encoding="utf-8")
    (scope / "docs" / "doc.md").write_text("witness 语料占位。", encoding="utf-8")

    db_path = tmp_path / "flai_os.db"
    app = create_app(
        agents_dir=agents_dir,
        tools_dir=REPO_ROOT / "tools_impl",
        contracts_dir=REPO_ROOT / "contracts",
        knowledge_dir=knowledge_dir,
        db_path=db_path,
        uploads_dir=tmp_path / "uploads",
        task_runs_dir=tmp_path / "task_runs",
    )
    with TestClient(app) as client:
        seed_and_login(client, db_path)
        yield client, app


@pytest.fixture()
def knowledge_taint_env(tmp_path: Path) -> Iterator[tuple[TestClient, Any]]:
    with _knowledge_env(tmp_path, confidentiality="restricted") as pair:
        yield pair


def test_restricted_knowledge_agent_outputs_and_samples_sensitive(
    knowledge_taint_env: tuple[TestClient, Any],
) -> None:
    """真跑链路：restricted 知识 Agent（零输入文件）→ 产物/样本 sensitive，
    产物下载 403——文件污点轴之外的第二条洗白通道被知识轴封死。"""
    client, app = knowledge_taint_env
    created = client.post(
        "/api/tasks",
        json={"agent_id": "knowledge_taint_agent", "inputs": {"name": "受限"}},
    )
    assert created.status_code == 200, created.text
    task_id = created.json()["id"]
    conn = app.state.conn_factory()
    try:
        claimed = repos.claim_next_queued(conn)
    finally:
        conn.close()
    assert claimed is not None and claimed["id"] == task_id
    result = app.state.runtime.execute(task_id)
    assert result["status"] == "completed", result

    conn = app.state.conn_factory()
    try:
        outputs = [
            dict(r) for r in conn.execute(
                "SELECT * FROM files WHERE task_id = ? AND kind='output'", (task_id,)
            ).fetchall()
        ]
        samples = repos.list_samples(conn, task_id)
    finally:
        conn.close()
    assert len(outputs) >= 1
    assert all(row["classification"] == "sensitive" for row in outputs) is True, (
        "restricted 知识 Agent 的产物被洗白成 internal（Codex R0-P1 回归）"
    )
    download = client.get(f"/api/files/{outputs[0]['id']}/download")
    assert download.status_code == 403
    assert len(samples) == 1
    assert samples[0]["classification"] == "sensitive"


def test_health_exposes_classification_axis_marker(
    governance_env: GovernanceEnv,
) -> None:
    """运行进程 B2 代际标记（Codex R0-P1 部署门配套）：health 自报布尔位。"""
    payload = governance_env.client.get("/api/health").json()
    assert payload.get("classification_axis") is True


# ── Codex R1 审 findings 的 witness ──────────────────────────────────────


def test_public_internal_knowledge_agent_stays_internal(tmp_path: Path) -> None:
    """R1-P1 反向 witness：public_internal 知识 Agent 产物必须是 internal 且可
    下载——若 scope_registry 漏接线（registry None → 全判 sensitive），本测试咬
    「过度限制」回归（出厂 knowledge_qa_agent 的正常下载会 403）。"""
    with _knowledge_env(tmp_path, confidentiality="public_internal") as (client, app):
        created = client.post(
            "/api/tasks",
            json={"agent_id": "knowledge_taint_agent", "inputs": {"name": "公开"}},
        )
        assert created.status_code == 200, created.text
        task_id = created.json()["id"]
        conn = app.state.conn_factory()
        try:
            claimed = repos.claim_next_queued(conn)
        finally:
            conn.close()
        assert claimed is not None and claimed["id"] == task_id
        result = app.state.runtime.execute(task_id)
        assert result["status"] == "completed", result

        conn = app.state.conn_factory()
        try:
            outputs = [
                dict(r) for r in conn.execute(
                    "SELECT * FROM files WHERE task_id = ? AND kind='output'", (task_id,)
                ).fetchall()
            ]
        finally:
            conn.close()
        assert len(outputs) >= 1
        assert all(row["classification"] == "internal" for row in outputs) is True, (
            "public_internal 知识 Agent 的产物被误判 sensitive——scope_registry 接线断了"
        )
        download = client.get(f"/api/files/{outputs[0]['id']}/download")
        assert download.status_code == 200


def test_worker_path_runtime_wires_scope_registry(tmp_path: Path, monkeypatch) -> None:
    """R1-P1 wiring witness：独立 worker 进程的 _build_default_runner 构造的
    runtime 必须带 scope_registry——只修 create_app 会漏掉生产执行主路径。"""
    from backend.app import config as config_mod
    from backend.app.jobs import runner as runner_mod

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    shutil.copytree(
        REPO_ROOT / "agents" / "hello_agent", agents_dir / "hello_agent",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    monkeypatch.setattr(config_mod, "AGENTS_DIR", agents_dir)
    monkeypatch.setattr(config_mod, "TOOLS_DIR", REPO_ROOT / "tools_impl")
    monkeypatch.setattr(config_mod, "CONTRACTS_DIR", REPO_ROOT / "contracts")
    monkeypatch.setattr(config_mod, "KNOWLEDGE_DIR", tmp_path / "knowledge")
    monkeypatch.setattr(config_mod, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config_mod, "UPLOADS_DIR", tmp_path / "data" / "uploads")
    monkeypatch.setattr(config_mod, "TASK_RUNS_DIR", tmp_path / "data" / "task_runs")
    monkeypatch.setattr(config_mod, "DB_PATH", tmp_path / "data" / "flai_os.db")

    runner = runner_mod._build_default_runner()
    assert runner._runtime.scope_registry is not None, (
        "worker 路径的 AgentRuntime 缺 scope_registry——知识轴在生产执行路径失效"
    )


def test_promote_script_wires_scope_registry() -> None:
    """R1-P1 wiring pin：promote_agent_l1.py 的 AgentRuntime 构造必须传
    scope_registry（文本钉——脚本主函数不宜在测试中整体执行）。"""
    text = (REPO_ROOT / "scripts" / "promote_agent_l1.py").read_text(encoding="utf-8")
    assert "scope_registry=asm.scope_registry" in text


def test_worker_heartbeat_upsert_and_generation(governance_env: GovernanceEnv) -> None:
    """R1-P1 心跳机制：单行 upsert（started_at 保留、generation 覆写）。"""
    from backend.app.jobs.runner import WORKER_GENERATION, JobRunner

    conn = governance_env.app.state.conn_factory()
    try:
        repos.beat_worker_heartbeat(conn, generation="old-gen", detail="pid=1")
        first = repos.get_worker_heartbeat(conn)
        assert first is not None and first["generation"] == "old-gen"

        runner = JobRunner(governance_env.app.state.runtime, governance_env.app.state.conn_factory)
        runner.beat()

        second = repos.get_worker_heartbeat(conn)
        assert second["generation"] == WORKER_GENERATION, "beat 必须覆写代际字符串"
        assert second["started_at"] == first["started_at"], "started_at 首次值必须保留"
        assert second["execution_bindings"] == [
            {
                "adapter": "native_python",
                "contract_version": "native.workflow.v1",
            }
        ]
        n = conn.execute("SELECT COUNT(*) FROM worker_heartbeats").fetchone()[0]
        assert n == 1, "固定 worker_id 单行 upsert，不得增长"
    finally:
        conn.close()


def test_job_runner_heartbeat_uses_the_actual_router_binding_set(
    governance_env: GovernanceEnv,
) -> None:
    from backend.app.jobs.runner import JobRunner

    class _Router:
        bindings = frozenset(
            {
                ("native_python", "native.workflow.v1"),
                ("jerryagent_sidecar", "flai.agent-layer.v1"),
            }
        )

    class _Runtime:
        execution_router = _Router()

    runner = JobRunner(_Runtime(), governance_env.app.state.conn_factory)
    runner.beat()

    conn = governance_env.app.state.conn_factory()
    try:
        heartbeat = repos.get_worker_heartbeat(conn)
    finally:
        conn.close()
    assert heartbeat is not None
    assert heartbeat["execution_bindings"] == [
        {
            "adapter": "jerryagent_sidecar",
            "contract_version": "flai.agent-layer.v1",
        },
        {
            "adapter": "native_python",
            "contract_version": "native.workflow.v1",
        },
    ]


def test_list_files_by_ids_survives_huge_id_list(governance_env: GovernanceEnv) -> None:
    """R1-P2：33000 个 id 一把梭会撞 SQLite 绑定变量上限（OperationalError），
    分批后必须正常返回；顺序保持与缺位静默语义不变。"""
    conn = governance_env.app.state.conn_factory()
    try:
        huge = [f"ghost-{i}" for i in range(33000)]
        assert repos.list_files_by_ids(conn, huge) == []

        # 跨批次正确性：三个真实文件散布在不同批次位置，顺序保持
        real_ids = []
        for i in range(3):
            fid = f"real-{i}"
            repos.create_file(
                conn, file_id=fid, kind="input", filename=f"f{i}.txt",
                path=f"/x/f{i}.txt", size_bytes=1, sha256="aa",
                classification="internal",
            )
            real_ids.append(fid)
        mixed = ["ghost-a"] + real_ids[:1] + [f"ghost-{i}" for i in range(600)] \
            + real_ids[1:] + ["ghost-z"]
        rows = repos.list_files_by_ids(conn, mixed)
        assert [r["id"] for r in rows] == real_ids
    finally:
        conn.close()


def test_beat_does_not_propagate_conn_factory_failure(governance_env: GovernanceEnv) -> None:
    """R2-P1：conn_factory 瞬时故障必须被 beat() 吞掉（记日志不上抛）——否则
    经 _beat_if_due 逃逸 run_forever 直接杀 worker，与心跳契约矛盾。"""
    from backend.app.jobs.runner import JobRunner

    def boom() -> Any:
        raise sqlite3.OperationalError("unable to open database file")

    runner = JobRunner(governance_env.app.state.runtime, boom)
    # 不抛即通过；顺带确认 _beat_if_due（run_forever 路径的调用点）也不抛
    runner.beat()
    runner._beat_if_due()


def test_deploy_selfcheck_probe_is_stdlib_only(governance_env: GovernanceEnv) -> None:
    """R2-P2：部署自检探针号称免应用依赖——其模块级不得从 jobs.runner 导入
    （连带拉 repos→jsonschema）。结构钉：WORKER_GENERATION 必来自 config。"""
    from backend.app import config as config_mod

    src = (REPO_ROOT / "scripts" / "deploy_selfcheck.py").read_text(encoding="utf-8")
    assert "from backend.app.jobs.runner import" not in src, (
        "探针从 jobs.runner 导入会连带拉 jsonschema，破坏 stdlib-only 承诺"
    )
    assert "from backend.app import config" in src
    # 代际常量单一事实源在 config，探针与 runner 同源
    assert hasattr(config_mod, "WORKER_GENERATION")


def test_health_db_identity_matches_served_db(governance_env: GovernanceEnv) -> None:
    """R1-P2：health.db_identity = 服务所连库路径的 sha256 前 16 位（opaque），
    与部署自检门探针侧同一算法——两侧 FLAI_DB_PATH 不一致时自检必咬。"""
    payload = governance_env.client.get("/api/health").json()
    expected = hashlib.sha256(
        str(Path(governance_env.app.state.db_path).resolve()).encode("utf-8")
    ).hexdigest()[:16]
    assert payload.get("db_identity") == expected


# ── 验收 #10：失败样本传播不依赖 verified_files（F6）─────────────────────


def test_schema_failure_sample_keeps_sensitive_classification(
    governance_env: GovernanceEnv,
) -> None:
    """schema 校验先失败（name 非法类型）→ _open_input_files 未跑成，
    失败样本的派生必须仍从 DB 现查得到 sensitive，而非误判 internal。"""
    file_id = _upload(governance_env, classification="sensitive").json()["id"]
    task_id, result = _create_and_run_task(
        governance_env, inputs={"name": 1}, input_file_ids=[file_id]
    )
    assert result["status"] == "failed"
    samples = _samples_for_task(governance_env, task_id)
    assert len(samples) == 1
    assert samples[0]["validation_status"] == "failed"
    assert samples[0]["classification"] == "sensitive", (
        "schema 失败路径的失败样本被误判 internal（F6 回归）"
    )
