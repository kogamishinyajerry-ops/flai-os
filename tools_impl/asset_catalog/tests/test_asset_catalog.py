# -*- coding: utf-8 -*-
"""asset_catalog 工具单测(ADR-0028)。

覆盖:真清单装配 / 确定性(同输入同输出 + tie-break 字典序)/ 大小写归一 /
零命中是合法 success(与"清单不可读"必须是两个可区分事实)/ fail-closed
全家族(缺文件/畸形 YAML/非法 status/缺字段/重复 id)/ top_k 边界。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from tools_impl.asset_catalog.adapter import run  # noqa: E402


@pytest.fixture(autouse=True)
def _default_catalog(monkeypatch):
    """缺省用真仓清单;个别用例再覆盖 FLAI_ASSET_CATALOG_PATH。"""
    monkeypatch.delenv("FLAI_ASSET_CATALOG_PATH", raising=False)


def _write_catalog(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "assets.yaml"
    p.write_text(body, encoding="utf-8")
    return p


_MINI_CATALOG = """
version: 9
updated: "2026-07-15"
assets:
  - id: alpha_tool
    name: 甲工具
    status: live
    kind: external_project
    keywords: [出图, 匹配]
    honest_note: 甲注
  - id: beta_tool
    name: 乙工具
    status: validated
    kind: methodology
    keywords: [出图, 匹配]
    honest_note: 乙注
"""


def test_list_real_catalog_ok() -> None:
    out = run({"action": "list"})
    assert out["status"] == "success"
    assert out["catalog_version"] >= 1
    assert len(out["assets"]) >= 10, "真仓清单不应少于 10 条家底"
    for item in out["assets"]:
        for field in ("id", "name", "status", "kind", "honest_note"):
            assert str(item[field]).strip() != "", f"{item.get('id')} 缺 {field}"


def test_match_real_catalog_hits_intel_kb() -> None:
    text = "每周都要查与商发往来的 ECM,人工翻历史档案找先例,希望输入关键词检索"
    out = run({"action": "match", "text": text, "top_k": 6})
    assert out["status"] == "success"
    ids = [a["id"] for a in out["assets"]]
    assert "engine_intel_kb" in ids, f"情报库应命中,实际:{ids}"
    top = out["assets"][0]
    assert top["score"] >= 2
    assert len(top["matched_keywords"]) == top["score"], "命中词列表必须与分数一致(可解释性)"


def test_match_deterministic_same_input_same_output() -> None:
    payload = {"action": "match", "text": "ECM 检索 历史 案例 出图", "top_k": 8}
    assert run(payload) == run(payload), "确定性:同输入必须逐字节同输出"


def test_match_tiebreak_lexicographic(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FLAI_ASSET_CATALOG_PATH", str(_write_catalog(tmp_path, _MINI_CATALOG)))
    out = run({"action": "match", "text": "需要出图和匹配", "top_k": 5})
    assert out["status"] == "success"
    assert [a["id"] for a in out["assets"]] == ["alpha_tool", "beta_tool"], "同分必须按 id 字典序"


def test_match_case_insensitive() -> None:
    out = run({"action": "match", "text": "帮我查 ecm 相关历史", "top_k": 6})
    assert out["status"] == "success"
    assert "engine_intel_kb" in [a["id"] for a in out["assets"]], "ECM 关键词须大小写归一命中"


def test_match_zero_hits_is_success_not_failure(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FLAI_ASSET_CATALOG_PATH", str(_write_catalog(tmp_path, _MINI_CATALOG)))
    out = run({"action": "match", "text": "完全不相干的一段话", "top_k": 5})
    assert out["status"] == "success"
    assert out["assets"] == [], "零命中是合法结果(家底里没有),绝不能报 failed(家底不可读)"


def test_missing_file_fails_closed(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FLAI_ASSET_CATALOG_PATH", str(tmp_path / "no_such.yaml"))
    out = run({"action": "match", "text": "ECM", "top_k": 3})
    assert out["status"] == "failed"
    assert "不存在" in out["error_message"]


def test_malformed_yaml_fails_closed(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(
        "FLAI_ASSET_CATALOG_PATH",
        str(_write_catalog(tmp_path, "assets: [unclosed\n  - broken")),
    )
    out = run({"action": "list"})
    assert out["status"] == "failed"
    assert "解析失败" in out["error_message"]


def test_invalid_status_fails_closed(monkeypatch, tmp_path) -> None:
    bad = _MINI_CATALOG.replace("status: live", "status: shipped")
    monkeypatch.setenv("FLAI_ASSET_CATALOG_PATH", str(_write_catalog(tmp_path, bad)))
    out = run({"action": "list"})
    assert out["status"] == "failed"
    assert "status 非法" in out["error_message"]


def test_missing_required_field_fails_closed(monkeypatch, tmp_path) -> None:
    bad = _MINI_CATALOG.replace("    honest_note: 甲注\n", "")
    monkeypatch.setenv("FLAI_ASSET_CATALOG_PATH", str(_write_catalog(tmp_path, bad)))
    out = run({"action": "list"})
    assert out["status"] == "failed"
    assert "honest_note" in out["error_message"]


def test_duplicate_id_fails_closed(monkeypatch, tmp_path) -> None:
    bad = _MINI_CATALOG.replace("id: beta_tool", "id: alpha_tool")
    monkeypatch.setenv("FLAI_ASSET_CATALOG_PATH", str(_write_catalog(tmp_path, bad)))
    out = run({"action": "list"})
    assert out["status"] == "failed"
    assert "重复" in out["error_message"]


def test_top_k_boundary_and_type(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FLAI_ASSET_CATALOG_PATH", str(_write_catalog(tmp_path, _MINI_CATALOG)))
    out = run({"action": "match", "text": "出图", "top_k": 1})
    assert out["status"] == "success" and len(out["assets"]) == 1
    assert run({"action": "match", "text": "出图", "top_k": True})["status"] == "failed", \
        "bool 是 int 子类,必须显式拒绝(canon:truthiness 家族坑)"


def test_unknown_action_fails() -> None:
    out = run({"action": "delete"})
    assert out["status"] == "failed"
    assert "action" in out["error_message"]
