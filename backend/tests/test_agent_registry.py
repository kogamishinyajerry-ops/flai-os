"""AgentRegistry 测试：真实 agents/ 扫描 + tmp 造缺件包 + 重复 id 硬错 + sync_to_db 幂等。"""

from __future__ import annotations

import shutil
import threading
from pathlib import Path

import pytest

from backend.app.config import AGENTS_DIR, CONTRACTS_DIR
from backend.app.core.errors import DuplicateAgentIdError
from backend.app.runtime.registry import AgentRegistry
from backend.app.storage.db import get_conn, init_db

_AGENT_SCHEMA = CONTRACTS_DIR / "agent.schema.json"


def _copy_hello_agent(dest: Path) -> Path:
    shutil.copytree(AGENTS_DIR / "hello_agent", dest)
    return dest


def test_scan_registers_real_hello_agent() -> None:
    registry = AgentRegistry(AGENTS_DIR, _AGENT_SCHEMA)
    registry.scan()
    agent = registry.get("hello_agent")
    assert agent is not None
    assert agent["name"].startswith("Hello Agent")
    assert registry.package_dir("hello_agent") == AGENTS_DIR / "hello_agent"
    assert any(a["id"] == "hello_agent" for a in registry.list())
    assert registry.errors == []


def test_scan_marks_package_missing_workflow_as_invalid(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    broken = _copy_hello_agent(agents_dir / "broken_agent")
    (broken / "workflow.py").unlink()

    registry = AgentRegistry(agents_dir, _AGENT_SCHEMA)
    registry.scan()

    assert registry.get("hello_agent") is None
    assert len(registry.errors) == 1
    assert "workflow.py" in registry.errors[0]["error"]
    assert str(broken) == registry.errors[0]["path"]


@pytest.mark.parametrize("first_write", ["workflow", "manifest"])
def test_scan_rejects_stable_torn_execution_generation(
    tmp_path: Path, first_write: str
) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    package_dir = agents_dir / "control_logic_agent"
    shutil.copytree(AGENTS_DIR / "control_logic_agent", package_dir)
    yaml_path = package_dir / "agent.yaml"
    workflow_path = package_dir / "workflow.py"
    original_yaml = yaml_path.read_text(encoding="utf-8")
    if first_write == "workflow":
        workflow_path.write_text(
            "def run(context):\n"
            "    return {'status': 'success', 'outputs': [{'generation': 'new'}]}\n",
            encoding="utf-8",
        )
    else:
        yaml_path.write_text(
            original_yaml.replace(
                "execution_digest: sha256:3b2361937c187131eb3424261a6aa1accf23bb2f4cf80f2b3aeaaef8a25c83e1",
                f"execution_digest: sha256:{'0' * 64}",
            ),
            encoding="utf-8",
        )
    registry = AgentRegistry(agents_dir, _AGENT_SCHEMA)
    registry.scan()

    assert registry.get("control_logic_agent") is None
    assert registry.execution_snapshot("control_logic_agent") is None
    assert len(registry.errors) == 1
    assert "execution_digest" in registry.errors[0]["error"]


def test_scan_rejects_safe_auto_agent_without_execution_generation(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    package_dir = agents_dir / "control_logic_agent"
    shutil.copytree(AGENTS_DIR / "control_logic_agent", package_dir)
    yaml_path = package_dir / "agent.yaml"
    yaml_path.write_text(
        "\n".join(
            line for line in yaml_path.read_text(encoding="utf-8").splitlines()
            if not line.startswith("execution_digest:")
        ) + "\n",
        encoding="utf-8",
    )

    registry = AgentRegistry(agents_dir, _AGENT_SCHEMA)
    registry.scan()

    assert registry.get("control_logic_agent") is None
    assert registry.execution_snapshot("control_logic_agent") is None
    assert len(registry.errors) == 1
    assert "execution_digest" in registry.errors[0]["error"]


def test_scan_marks_package_missing_readme_as_invalid(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    broken = _copy_hello_agent(agents_dir / "broken_agent")
    (broken / "README.md").unlink()

    registry = AgentRegistry(agents_dir, _AGENT_SCHEMA)
    registry.scan()

    assert registry.get("hello_agent") is None
    assert len(registry.errors) == 1
    assert "README.md" in registry.errors[0]["error"]


def test_scan_marks_trial_status_with_tbd_maintainer_as_invalid(tmp_path: Path) -> None:
    """P2-7：status=trial 且 owner.maintainer 仍为 TBD——agent.schema.json 注释早已
    承诺的强制校验，必须被 Registry 排除进 errors，不得注册。
    """
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    broken = _copy_hello_agent(agents_dir / "trial_tbd_agent")
    yaml_path = broken / "agent.yaml"
    text = yaml_path.read_text(encoding="utf-8")
    text = text.replace("id: hello_agent", "id: trial_tbd_agent")
    text = text.replace("status: draft", "status: trial")
    yaml_path.write_text(text, encoding="utf-8")
    assert "maintainer: TBD" in text  # hello_agent 样板本就 TBD，未额外改动即命中

    registry = AgentRegistry(agents_dir, _AGENT_SCHEMA)
    registry.scan()

    assert registry.get("trial_tbd_agent") is None
    assert len(registry.errors) == 1
    assert "TBD" in registry.errors[0]["error"]


def test_scan_marks_trial_status_with_tbd_business_reviewer_as_invalid(tmp_path: Path) -> None:
    """同上，但命中的是 business_reviewer=TBD（另一半字段也要校验，不只查 maintainer）。"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    broken = _copy_hello_agent(agents_dir / "trial_tbd_reviewer_agent")
    yaml_path = broken / "agent.yaml"
    text = yaml_path.read_text(encoding="utf-8")
    text = text.replace("id: hello_agent", "id: trial_tbd_reviewer_agent")
    text = text.replace("status: draft", "status: released")
    text = text.replace("maintainer: TBD", "maintainer: 张工")
    yaml_path.write_text(text, encoding="utf-8")
    assert "business_reviewer: TBD" in text

    registry = AgentRegistry(agents_dir, _AGENT_SCHEMA)
    registry.scan()

    assert registry.get("trial_tbd_reviewer_agent") is None
    assert len(registry.errors) == 1
    assert "TBD" in registry.errors[0]["error"]


def test_scan_draft_status_with_tbd_is_allowed(tmp_path: Path) -> None:
    """反面对照：status=draft（非 trial/released）时 TBD 是合法状态，不应被排除
    ——否则 hello_agent 自身这个 Golden Sample 就会先被自己的规则误伤。
    """
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _copy_hello_agent(agents_dir / "draft_tbd_agent")
    yaml_path = agents_dir / "draft_tbd_agent" / "agent.yaml"
    text = yaml_path.read_text(encoding="utf-8").replace("id: hello_agent", "id: draft_tbd_agent")
    yaml_path.write_text(text, encoding="utf-8")

    registry = AgentRegistry(agents_dir, _AGENT_SCHEMA)
    registry.scan()

    assert registry.get("draft_tbd_agent") is not None
    assert registry.errors == []


def test_scan_marks_invalid_category_enum_as_invalid(tmp_path: Path) -> None:
    """P3-2：agent.yaml 里 category 用了 schema 枚举外的乱写值——必须被排除进 errors，
    不得注册也不得让 scan() 整体崩溃。
    """
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    broken = _copy_hello_agent(agents_dir / "bad_category_agent")
    yaml_path = broken / "agent.yaml"
    text = yaml_path.read_text(encoding="utf-8")
    text = text.replace("id: hello_agent", "id: bad_category_agent")
    text = text.replace("category: tool_automation", "category: 乱写枚举")
    yaml_path.write_text(text, encoding="utf-8")

    registry = AgentRegistry(agents_dir, _AGENT_SCHEMA)
    registry.scan()

    assert registry.get("bad_category_agent") is None
    assert len(registry.errors) == 1
    assert "agent.schema.json" in registry.errors[0]["error"] or "category" in registry.errors[0]["error"]


def test_scan_duplicate_id_raises_hard_error(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _copy_hello_agent(agents_dir / "hello_agent_a")
    _copy_hello_agent(agents_dir / "hello_agent_b")

    registry = AgentRegistry(agents_dir, _AGENT_SCHEMA)
    with pytest.raises(DuplicateAgentIdError):
        registry.scan()


def test_sync_to_db_then_rescan_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "flai_os.db"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        registry = AgentRegistry(AGENTS_DIR, _AGENT_SCHEMA)
        registry.scan()
        registry.sync_to_db(conn)

        rows = conn.execute("SELECT * FROM agents WHERE id = ?", ("hello_agent",)).fetchall()
        assert len(rows) == 1
        assert rows[0]["version"] == "0.1.0"

        versions = conn.execute(
            "SELECT * FROM agent_versions WHERE agent_id = ?", ("hello_agent",)
        ).fetchall()
        assert len(versions) == 1

        # 重扫 + 重同步：幂等，不产生第二行/第二版本。
        registry.scan()
        registry.sync_to_db(conn)
        rows2 = conn.execute("SELECT * FROM agents WHERE id = ?", ("hello_agent",)).fetchall()
        assert len(rows2) == 1
        versions2 = conn.execute(
            "SELECT * FROM agent_versions WHERE agent_id = ?", ("hello_agent",)
        ).fetchall()
        assert len(versions2) == 1
    finally:
        conn.close()


def test_stable_view_blocks_adopt_until_reader_releases() -> None:
    live = AgentRegistry(AGENTS_DIR, _AGENT_SCHEMA)
    shadow = AgentRegistry(AGENTS_DIR, _AGENT_SCHEMA)
    live.scan()
    shadow.scan()
    started = threading.Event()
    adopted = threading.Event()

    def publish() -> None:
        started.set()
        live.adopt(shadow)
        adopted.set()

    with live.stable_view():
        thread = threading.Thread(target=publish)
        thread.start()
        assert started.wait(1)
        assert not adopted.wait(0.1)

    assert adopted.wait(1)
    thread.join(timeout=1)
    assert not thread.is_alive()
