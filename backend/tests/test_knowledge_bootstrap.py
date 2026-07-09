"""bootstrap 共享装配的双进程路径 witness（loop-auditor Mode A Finding 1）。

结构性风险：API 进程（main.create_app）与 Job Runner 进程（runner._build_default_runner）
若各自手写装配，knowledge 对账（reconcile）只加一处另一处就是半扇门。本文件
用同一个"密级违规" Agent 包分别走两条真实装配路径，断言两边都把它拒在注册表外；
另钉一条顺序契约 witness：deregister 必须先于 sync_to_db（DB agents 表无违规行）。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import yaml
from fastapi.testclient import TestClient

from backend.app import config
from backend.app.jobs.runner import _build_default_runner
from backend.app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "contracts"


def _write_violating_agent(agents_dir: Path) -> None:
    """密级静态门违规包：restricted scope × visibility=department_trial。

    一钥一门：scope 本身已注册（排除"未注册 scope"那条门背锅），违反的只有
    密级矩阵这一条。"""
    pkg = agents_dir / "conf_violator"
    (pkg / "eval_cases").mkdir(parents=True)
    manifest = {
        "id": "conf_violator",
        "name": "密级违规探针",
        "version": "0.1.0",
        "status": "draft",
        "maturity": "L0",
        "category": "knowledge_qa",
        "summary": "bootstrap 双路径 witness 探针：restricted scope 配 department_trial。",
        "owner": {"department": "二所", "maintainer": "TBD", "business_reviewer": "TBD"},
        "model": {"profile": "none"},
        "knowledge": {"enabled": True, "scopes": ["restricted_scope"]},
        "tools": [],
        "input": {"type": "params", "schema": "input_schema.json"},
        "output": {"formats": [".json"], "schema": "output_schema.json"},
        "workflow": {"entrypoint": "workflow.py", "mode": "job", "requires_human_review": False},
        "permissions": {"visibility": "department_trial", "allowed_roles": ["admin"]},
        "logging": {
            "save_inputs": True, "save_outputs": True, "save_tool_logs": True,
            "save_model_calls": True, "save_feedback": True,
        },
        "data_asset": {"collect_samples": False},
        "limitations": ["测试探针。"],
    }
    (pkg / "agent.yaml").write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
    (pkg / "workflow.py").write_text("def run(context):\n    return {'status': 'success', 'outputs': []}\n", encoding="utf-8")
    (pkg / "input_schema.json").write_text(json.dumps({"type": "object"}), encoding="utf-8")
    (pkg / "output_schema.json").write_text(json.dumps({"type": "object"}), encoding="utf-8")
    for name in ("prompt.md", "README.md", "changelog.md"):
        (pkg / name).write_text("witness 探针。", encoding="utf-8")
    (pkg / "eval_cases" / "case_001.json").write_text("{}", encoding="utf-8")


def _write_restricted_scope(knowledge_dir: Path) -> None:
    scope = knowledge_dir / "restricted_scope"
    (scope / "docs").mkdir(parents=True)
    (scope / "scope.yaml").write_text(yaml.safe_dump({
        "scope_id": "restricted_scope",
        "name": "受限范围",
        "kind": "document",
        "source": "file_dir",
        "path_or_uri": "docs",
        "confidentiality": "restricted",
        "owner": "e2e",
    }, allow_unicode=True), encoding="utf-8")
    (scope / "docs" / "doc.md").write_text("受限内容。", encoding="utf-8")


def _make_env(tmp_path: Path) -> dict[str, Path]:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _write_violating_agent(agents_dir)
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    knowledge_dir = tmp_path / "knowledge"
    _write_restricted_scope(knowledge_dir)
    return {"agents": agents_dir, "tools": tools_dir, "knowledge": knowledge_dir}


def test_api_path_deregisters_and_db_has_no_row(tmp_path) -> None:
    """路径 A（create_app）：违规 Agent 注册表不可见 + errors 留痕 +
    **DB agents 表无该行**（deregister 先于 sync_to_db 的顺序契约 witness）。"""
    env = _make_env(tmp_path)
    db_path = tmp_path / "flai_os.db"
    app = create_app(
        agents_dir=env["agents"], tools_dir=env["tools"], contracts_dir=CONTRACTS_DIR,
        knowledge_dir=env["knowledge"], db_path=db_path,
        uploads_dir=tmp_path / "uploads", task_runs_dir=tmp_path / "task_runs",
    )
    with TestClient(app):
        registry = app.state.agent_registry
        assert registry.get("conf_violator") is None
        assert any("密级" in e["error"] for e in registry.errors)
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute("SELECT id FROM agents WHERE id='conf_violator'").fetchall()
        finally:
            conn.close()
        assert rows == []


def test_runner_path_deregisters_via_same_bootstrap(tmp_path, monkeypatch) -> None:
    """路径 B（_build_default_runner）：monkeypatch config 默认路径到 tmp 后走
    worker 真实装配入口，违规 Agent 同样被拒，knowledge_service 已接线。"""
    env = _make_env(tmp_path)
    monkeypatch.setattr(config, "AGENTS_DIR", env["agents"])
    monkeypatch.setattr(config, "TOOLS_DIR", env["tools"])
    monkeypatch.setattr(config, "CONTRACTS_DIR", CONTRACTS_DIR)
    monkeypatch.setattr(config, "KNOWLEDGE_DIR", env["knowledge"])
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "UPLOADS_DIR", tmp_path / "data" / "uploads")
    monkeypatch.setattr(config, "TASK_RUNS_DIR", tmp_path / "data" / "task_runs")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "data" / "flai_os.db")

    runner = _build_default_runner()
    runtime: Any = runner._runtime if hasattr(runner, "_runtime") else runner.runtime
    assert runtime.agent_registry.get("conf_violator") is None
    assert any("密级" in e["error"] for e in runtime.agent_registry.errors)
    assert runtime.knowledge_service is not None
