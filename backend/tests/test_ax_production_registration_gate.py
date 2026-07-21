"""ax production registration stays mechanically locked before its prerequisites.

These checks are platform independent and therefore run on the Windows target too;
the POSIX-only subprocess fixture tests remain in the tool package.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from backend.app.config import AGENTS_DIR, CONTRACTS_DIR, TOOLS_DIR
from backend.app.core.errors import ToolNotRegisteredError
from backend.app.tools.registry import ToolRegistry


AX_L0_ID = "ax_web_extract"


def _manifest() -> dict:
    return yaml.safe_load(
        (TOOLS_DIR / AX_L0_ID / "tool.yaml").read_text(encoding="utf-8")
    )


def _scan_one(tmp_path: Path, manifest: dict) -> ToolRegistry:
    package = tmp_path / "candidate"
    package.mkdir()
    (package / "tool.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    registry = ToolRegistry(tmp_path, CONTRACTS_DIR / "tool.schema.json")
    registry.scan()
    return registry


def test_ax_l0_exact_manifest_remains_the_only_registered_ax_tool() -> None:
    registry = ToolRegistry(TOOLS_DIR, CONTRACTS_DIR / "tool.schema.json")
    registry.scan()

    assert registry.get(AX_L0_ID) is not None
    assert [tool["id"] for tool in registry.list() if tool["id"].startswith("ax_")] == [
        AX_L0_ID
    ]
    assert registry.get(AX_L0_ID)["egress"] == {"network": "fixture_only"}


@pytest.mark.parametrize(
    ("tool_id", "entrypoint"),
    [
        ("ax_web_extract_l1", "tools_impl.ax_web_extract.adapter:run"),
        ("ax_live", "tools_impl.ax_web_extract.adapter:run"),
        ("research_web_fetch", "tools_impl.web_extract_live.adapter:run"),
    ],
)
def test_ax_l1_or_live_candidates_are_rejected_during_registry_scan(
    tmp_path: Path, tool_id: str, entrypoint: str
) -> None:
    candidate = deepcopy(_manifest())
    candidate["id"] = tool_id
    candidate["entrypoint"] = entrypoint

    registry = _scan_one(tmp_path, candidate)

    assert registry.get(tool_id) is None
    assert len(registry.errors) == 1
    error = registry.errors[0]["error"]
    assert "角色轴" in error
    assert "egress policy" in error
    assert "默认 disabled" in error


def test_renamed_production_network_adapter_is_rejected_by_declared_capability(
    tmp_path: Path,
) -> None:
    """A neutral id/entrypoint must not bypass the production egress lock."""

    candidate = deepcopy(_manifest())
    candidate["id"] = "research_web_fetch"
    candidate["entrypoint"] = "tools_impl.web_extract_live.adapter:run"
    candidate["egress"] = {"network": "production"}
    candidate["input_schema"] = {
        "type": "object",
        "required": ["url"],
        "properties": {"url": {"type": "string"}},
        "additionalProperties": False,
    }
    candidate["output_schema"] = {
        "type": "object",
        "required": ["status"],
        "properties": {
            "status": {"type": "string", "enum": ["success", "failed"]}
        },
        "additionalProperties": False,
    }

    registry = _scan_one(tmp_path, candidate)

    assert registry.get(candidate["id"]) is None
    assert len(registry.errors) == 1
    error = registry.errors[0]["error"]
    assert "production" in error
    assert "角色轴" in error
    assert "egress policy" in error
    assert "默认 disabled" in error


def test_renamed_url_adapter_cannot_hide_behind_none_egress(tmp_path: Path) -> None:
    """Defense in depth also catches a falsely downgraded minimal URL schema."""

    candidate = deepcopy(_manifest())
    candidate["id"] = "research_web_fetch"
    candidate["entrypoint"] = "tools_impl.web_extract_live.adapter:run"
    candidate["egress"] = {"network": "none"}
    candidate["input_schema"] = {
        "type": "object",
        "required": ["url"],
        "additionalProperties": True,
    }
    candidate["output_schema"] = {
        "type": "object",
        "required": ["status"],
        "properties": {
            "status": {"type": "string", "enum": ["success", "failed"]}
        },
        "additionalProperties": False,
    }

    registry = _scan_one(tmp_path, candidate)

    assert registry.get(candidate["id"]) is None
    assert len(registry.errors) == 1
    error = registry.errors[0]["error"]
    assert "联网抽取" in error
    assert "角色轴" in error
    assert "egress policy" in error


def test_fixture_only_network_mode_is_reserved_for_exact_ax_l0(tmp_path: Path) -> None:
    candidate = deepcopy(_manifest())
    candidate["id"] = "research_fixture_fetch"
    candidate["entrypoint"] = "tools_impl.research_fixture.adapter:run"

    registry = _scan_one(tmp_path, candidate)

    assert registry.get(candidate["id"]) is None
    assert len(registry.errors) == 1
    assert "fixture_only" in registry.errors[0]["error"]


def test_call_guard_rejects_an_in_memory_ax_l1_injection(tmp_path: Path) -> None:
    candidate = deepcopy(_manifest())
    candidate["id"] = "ax_web_extract_l1"
    registry = ToolRegistry(tmp_path, CONTRACTS_DIR / "tool.schema.json")
    registry._tools[candidate["id"]] = candidate  # defense-in-depth fault injection

    with pytest.raises(ToolNotRegisteredError, match="角色轴.*egress policy"):
        registry.call(candidate["id"], {})


def test_call_guard_rejects_in_memory_production_egress_injection(tmp_path: Path) -> None:
    candidate = deepcopy(_manifest())
    candidate["id"] = "research_web_fetch"
    candidate["entrypoint"] = "tools_impl.web_extract_live.adapter:run"
    candidate["egress"] = {"network": "production"}
    registry = ToolRegistry(tmp_path, CONTRACTS_DIR / "tool.schema.json")
    registry._tools[candidate["id"]] = candidate  # defense-in-depth fault injection

    with pytest.raises(ToolNotRegisteredError, match="角色轴.*egress policy"):
        registry.call(candidate["id"], {})


def test_no_agent_manifest_grants_any_ax_tool_family() -> None:
    for manifest in AGENTS_DIR.glob("*/agent.yaml"):
        agent = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        granted = agent.get("tools") or []
        assert not any(
            tool_id == "ax" or tool_id.startswith(("ax_", "ax-"))
            for tool_id in granted
        ), manifest


def test_production_unlock_order_is_role_then_egress_then_independent_l1() -> None:
    adr = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "adr"
        / "ADR-0046-ax-web-extract-subprocess-and-egress-boundary.md"
    ).read_text(encoding="utf-8")

    role_gate = adr.index("1. 先完成运行时角色轴")
    egress_gate = adr.index("2. 再完成可执行 egress policy")
    l1_gate = adr.index("3. 只有前两项均有独立验证证据后，才允许另提并开发 ax L1 生产 adapter")

    assert role_gate < egress_gate < l1_gate
    assert "L1 adapter\n   本身不是解锁信号" in adr
    assert "必须默认 disabled" in adr
    assert "egress.network` 只是能力声明，不是可执行 egress policy" in adr
