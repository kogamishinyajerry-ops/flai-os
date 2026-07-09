"""ToolRegistry 测试（docs/03 / ADR-0008）：先注册再调用、契约 fail-closed、超时诚实标注。

覆盖：
- 扫描真实 tools_impl/ 找到 mock_echo；
- 坏 tool.yaml 进 .errors 不炸整个 Registry；
- 重复 id 硬错（tmp 目录造两个同 id）；
- 未注册工具 .call() 抛错；
- 入参非法 → failed tool_run 落库 + 抛 ToolInputInvalidError；
- 出参契约外 → fail-closed，抛 ToolOutputInvalidError；
- 成功调用 tool_runs.mock 如实为 1/True；
- 超时路径（tmp 造 sleep 工具，timeout=1）→ failed tool_run + 诚实 error_message + 抛 TimeoutError。
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml

from backend.app.config import CONTRACTS_DIR, TOOLS_DIR
from backend.app.core.errors import (
    DuplicateAgentIdError,
    ToolExecutionError,
    ToolInputInvalidError,
    ToolNotRegisteredError,
    ToolOutputInvalidError,
)
from backend.app.storage import db as db_mod
from backend.app.storage import repos
from backend.app.tools.registry import ToolRegistry

TOOL_SCHEMA_PATH = CONTRACTS_DIR / "tool.schema.json"


@pytest.fixture()
def db_conn(tmp_path) -> sqlite3.Connection:
    db_path = tmp_path / "registry_test.db"
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    yield conn
    conn.close()


def _write_tool_yaml(
    dir_path: Path,
    *,
    tool_id: str,
    entrypoint: str,
    mock: bool = False,
    timeout_seconds: int = 10,
    input_schema: dict[str, Any] | None = None,
    output_schema: dict[str, Any] | None = None,
) -> None:
    input_schema = input_schema or {
        "type": "object",
        "required": ["message"],
        "properties": {"message": {"type": "string"}},
        "additionalProperties": False,
    }
    output_schema = output_schema or {
        "type": "object",
        "required": ["status"],
        "properties": {"status": {"type": "string", "enum": ["success", "failed"]}},
        "additionalProperties": False,
    }
    data = {
        "id": tool_id,
        "name": tool_id,
        "version": "0.1.0",
        "type": "python_adapter",
        "mock": mock,
        "description": "测试用工具包，仅供 ToolRegistry 单测使用",
        "entrypoint": entrypoint,
        "input_schema": input_schema,
        "output_schema": output_schema,
        "runtime": {"timeout_seconds": timeout_seconds, "max_parallel_jobs": 1, "retry": 0},
        "safety": {"require_workspace_isolation": False, "allow_shell_command": False, "save_raw_files": False},
        "owner": {"maintainer": "TBD", "business_owner": "TBD"},
    }
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / "tool.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


# ── scan() ───────────────────────────────────────────────────────────────

def test_scan_real_tools_dir_finds_mock_echo() -> None:
    registry = ToolRegistry(TOOLS_DIR, TOOL_SCHEMA_PATH)
    registry.scan()
    ids = {t["id"] for t in registry.list()}
    assert "mock_echo" in ids
    assert registry.get("mock_echo") is not None


def test_scan_excludes_invalid_tool_yaml_without_crashing(tmp_path) -> None:
    good_dir = tmp_path / "good_tool"
    _write_tool_yaml(good_dir, tool_id="good_tool", entrypoint="good_tool.adapter:run")

    bad_dir = tmp_path / "bad_tool"
    bad_dir.mkdir()
    (bad_dir / "tool.yaml").write_text("id: bad_tool\n# 缺少大量必填字段（runtime/safety/owner 等）\n", encoding="utf-8")

    registry = ToolRegistry(tmp_path, TOOL_SCHEMA_PATH)
    registry.scan()  # 不应抛异常

    assert registry.get("good_tool") is not None
    assert registry.get("bad_tool") is None
    assert len(registry.errors) == 1
    assert "bad_tool" in registry.errors[0]["dir"]


def test_scan_duplicate_tool_id_raises(tmp_path) -> None:
    _write_tool_yaml(tmp_path / "dup_a", tool_id="dup_tool", entrypoint="dup_a.adapter:run")
    _write_tool_yaml(tmp_path / "dup_b", tool_id="dup_tool", entrypoint="dup_b.adapter:run")

    registry = ToolRegistry(tmp_path, TOOL_SCHEMA_PATH)
    with pytest.raises(DuplicateAgentIdError):
        registry.scan()


# ── call(): 未注册 ─────────────────────────────────────────────────────────

def test_call_unregistered_tool_raises(tmp_path) -> None:
    registry = ToolRegistry(tmp_path, TOOL_SCHEMA_PATH)
    registry.scan()
    with pytest.raises(ToolNotRegisteredError):
        registry.call("no_such_tool", {})


# ── call(): 入参非法 fail-closed ───────────────────────────────────────────

def test_call_invalid_input_records_failed_tool_run_and_raises(db_conn) -> None:
    registry = ToolRegistry(TOOLS_DIR, TOOL_SCHEMA_PATH)
    registry.scan()
    task_id = f"task_{uuid.uuid4().hex[:8]}"

    with pytest.raises(ToolInputInvalidError):
        registry.call("mock_echo", {}, conn=db_conn, task_id=task_id)  # 缺必填 message

    runs = repos.list_tool_runs(db_conn, task_id)
    assert len(runs) == 1
    assert runs[0]["status"] == "failed"
    assert runs[0]["tool_id"] == "mock_echo"
    assert runs[0]["error_message"]


# ── call(): 出参契约外 fail-closed ─────────────────────────────────────────

def test_call_output_schema_violation_is_fail_closed(tmp_path, monkeypatch, db_conn) -> None:
    tool_dir = tmp_path / "bad_output_tool_pkg"
    tool_dir.mkdir()
    (tool_dir / "adapter.py").write_text(
        "def run(payload, context=None):\n"
        "    return {'status': 'not_a_valid_status'}\n",
        encoding="utf-8",
    )
    _write_tool_yaml(tool_dir, tool_id="bad_output_tool", entrypoint="bad_output_tool_pkg.adapter:run")
    monkeypatch.syspath_prepend(str(tmp_path))

    registry = ToolRegistry(tmp_path, TOOL_SCHEMA_PATH)
    registry.scan()

    task_id = f"task_{uuid.uuid4().hex[:8]}"
    with pytest.raises(ToolOutputInvalidError):
        registry.call("bad_output_tool", {"message": "hi"}, conn=db_conn, task_id=task_id)

    runs = repos.list_tool_runs(db_conn, task_id)
    assert len(runs) == 1
    assert runs[0]["status"] == "failed"
    assert runs[0]["error_message"]


# ── call(): entrypoint 坏靶（P2-3）成败皆落库 ──────────────────────────────

def test_call_broken_entrypoint_module_records_failed_tool_run_and_raises(tmp_path, db_conn) -> None:
    """P2-3：entrypoint 指向不存在的模块——import 失败也是一次失败调用，
    tool_runs 必须有 failed 行（此前 import 抛在 _record 之前，永远无痕）。
    """
    _write_tool_yaml(
        tmp_path / "ghost_tool_pkg",
        tool_id="ghost_tool",
        entrypoint="no_such_module_xyz_flai.adapter:run",
    )
    registry = ToolRegistry(tmp_path, TOOL_SCHEMA_PATH)
    registry.scan()
    assert registry.get("ghost_tool") is not None  # yaml 合法，注册成功

    task_id = f"task_{uuid.uuid4().hex[:8]}"
    with pytest.raises(ToolExecutionError):
        registry.call("ghost_tool", {"message": "hi"}, conn=db_conn, task_id=task_id)

    runs = repos.list_tool_runs(db_conn, task_id)
    assert len(runs) == 1
    assert runs[0]["status"] == "failed"
    assert "entrypoint 解析失败" in runs[0]["error_message"]


def test_call_broken_entrypoint_func_records_failed_tool_run_and_raises(tmp_path, monkeypatch, db_conn) -> None:
    """P2-3 变体：模块存在但函数名写错（getattr 抛 AttributeError）——同样落库+抛。"""
    tool_dir = tmp_path / "typo_func_pkg"
    tool_dir.mkdir()
    (tool_dir / "adapter.py").write_text(
        "def run(payload, context=None):\n    return {'status': 'success'}\n",
        encoding="utf-8",
    )
    _write_tool_yaml(tool_dir, tool_id="typo_func_tool", entrypoint="typo_func_pkg.adapter:no_such_func")
    monkeypatch.syspath_prepend(str(tmp_path))

    registry = ToolRegistry(tmp_path, TOOL_SCHEMA_PATH)
    registry.scan()

    task_id = f"task_{uuid.uuid4().hex[:8]}"
    with pytest.raises(ToolExecutionError):
        registry.call("typo_func_tool", {"message": "hi"}, conn=db_conn, task_id=task_id)

    runs = repos.list_tool_runs(db_conn, task_id)
    assert len(runs) == 1
    assert runs[0]["status"] == "failed"
    assert "entrypoint 解析失败" in runs[0]["error_message"]


# ── call(): 成功调用 mock 字段如实入库 ─────────────────────────────────────

def test_call_success_records_mock_true_honestly(db_conn) -> None:
    registry = ToolRegistry(TOOLS_DIR, TOOL_SCHEMA_PATH)
    registry.scan()
    task_id = f"task_{uuid.uuid4().hex[:8]}"

    result = registry.call("mock_echo", {"message": {"a": 1}}, conn=db_conn, task_id=task_id)
    assert result["status"] == "success"
    assert result["echoed"] == {"a": 1}

    runs = repos.list_tool_runs(db_conn, task_id)
    assert len(runs) == 1
    assert runs[0]["mock"] is True  # mock_echo 的 tool.yaml 声明 mock: true，必须如实入库
    assert runs[0]["status"] == "success"


def test_call_without_conn_skips_db_write() -> None:
    """conn=None 时跳过落库（纯库内自测用），不应报错。"""
    registry = ToolRegistry(TOOLS_DIR, TOOL_SCHEMA_PATH)
    registry.scan()
    result = registry.call("mock_echo", {"message": {"x": 1}})
    assert result["status"] == "success"


# ── call(): 超时诚实标注 ───────────────────────────────────────────────────

def test_call_timeout_records_failed_with_honest_error_message(tmp_path, monkeypatch, db_conn) -> None:
    tool_dir = tmp_path / "slow_tool_pkg"
    tool_dir.mkdir()
    (tool_dir / "adapter.py").write_text(
        "import time\n"
        "def run(payload, context=None):\n"
        "    time.sleep(5)\n"
        "    return {'status': 'success'}\n",
        encoding="utf-8",
    )
    _write_tool_yaml(tool_dir, tool_id="slow_tool", entrypoint="slow_tool_pkg.adapter:run", timeout_seconds=1)
    monkeypatch.syspath_prepend(str(tmp_path))

    registry = ToolRegistry(tmp_path, TOOL_SCHEMA_PATH)
    registry.scan()

    task_id = f"task_{uuid.uuid4().hex[:8]}"
    with pytest.raises(TimeoutError):
        registry.call("slow_tool", {"message": "hi"}, conn=db_conn, task_id=task_id)

    runs = repos.list_tool_runs(db_conn, task_id)
    assert len(runs) == 1
    assert runs[0]["status"] == "failed"
    # 诚实标注：不能假装线程已被干净终止（ADR-0008 决策3）
    assert "线程" in runs[0]["error_message"] or "超时" in runs[0]["error_message"]
