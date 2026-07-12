"""monitor_adapter_recon 单测（ADR-0022）。

咬合核心：fail-closed（核未配置/不可达/超时绝不假成功）+ 只读子进程调核 +
shell=False 无命令注入面 + 外部输出只解析不执行。gate 断言一律 is True/is False。

真环境用例（真调 hub 承重核）在 hub 仓存在时才跑，否则 skip——不把 CI 绑死到
监控节点仓的存在（跨仓耦合诚实标注，见 ADR-0022）。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tools_impl.monitor_adapter_recon.adapter import run

_CORE_ENV = "FLAI_MONITOR_CORE_DIR"
# 本机监控节点仓默认位置；不存在则真环境用例 skip（不硬失败）。
_HUB_DIR = Path("~/projects/sim-live-hub").expanduser()
_HUB_FIXTURE = _HUB_DIR / "tests" / "fixtures" / "structopt" / "sample_run"
_hub_available = (_HUB_DIR / "tools" / "adapter_gen.py").is_file() and _HUB_FIXTURE.is_dir()
_requires_hub = pytest.mark.skipif(not _hub_available, reason="监控节点仓 sim-live-hub 不在本机，跳过真环境用例")


# ---- fail-closed：核不可达一律 failed + core_available=false，绝不假成功 ----

def test_fail_closed_when_core_env_unset(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv(_CORE_ENV, raising=False)
    result = run({"sample_run_dir": str(tmp_path)})
    assert (result["status"] == "failed") is True
    assert (result["core_available"] is False) is True


def test_fail_closed_when_core_dir_bogus(monkeypatch, tmp_path) -> None:
    """配置了目录但其下无 tools/adapter_gen.py → 核不可达，绝不猜别的可执行。"""
    monkeypatch.setenv(_CORE_ENV, str(tmp_path))  # 空目录，无承重核
    result = run({"sample_run_dir": str(tmp_path)})
    assert (result["status"] == "failed") is True
    assert (result["core_available"] is False) is True


@_requires_hub
def test_fail_when_sample_not_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(_CORE_ENV, str(_HUB_DIR))
    result = run({"sample_run_dir": str(tmp_path / "does_not_exist")})
    assert (result["status"] == "failed") is True
    # 核可达，只是 sample 不合法——core_available 不为 False（区分两类失败）
    assert (result.get("core_available") is False) is False


@_requires_hub
def test_shell_metachars_in_sample_path_no_injection(monkeypatch) -> None:
    """shell=False + 参数列表：sample_run_dir 含 shell 元字符也只当字面路径，
    绝不执行注入命令——路径不存在 → failed，且未触发任何副作用。"""
    monkeypatch.setenv(_CORE_ENV, str(_HUB_DIR))
    evil = "/tmp/nope; touch /tmp/monitor_recon_pwned"
    result = run({"sample_run_dir": evil})
    assert (result["status"] == "failed") is True
    # 注入若生效会造出 /tmp/monitor_recon_pwned；shell=False 下绝不会
    # （字面路径不是目录 → 直接 failed，命令从不经 shell 解释）
    assert (any(Path("/tmp").glob("monitor_recon_pwned*")) is False) is True


@_requires_hub
def test_fail_closed_when_grounding_check_fails(monkeypatch, tmp_path) -> None:
    """接地自检未通过（核 rc=1 / grounding_ok=false：cited 证据对不上真源，如 recon
    与自检间文件被换）→ fail-closed，绝不转 status=success 让未接地草案进人审
    （Codex R2 审 P1）。用 monkeypatch 伪造核输出直测 wrapper 的 fail-closed 逻辑。"""
    from tools_impl.monitor_adapter_recon import adapter as _ad
    monkeypatch.setenv(_CORE_ENV, str(_HUB_DIR))
    run_dir = tmp_path / "20260712-030000-000000"
    run_dir.mkdir()
    (run_dir / "metrics.csv").write_text("iteration,x\n1,2\n", encoding="utf-8")

    class _FakeProc:
        returncode = 1
        stdout = ('{"module_name":"m","grounding_ok":false,'
                  '"grounding_failures":[{"aspect":"fake","why":"样本行未在文件中逐字找到"}],'
                  '"module_json_draft":{},"parser_stub":"","honesty_checklist":[],'
                  '"verified":{},"proposed":[],"unverified":[]}')
        stderr = ""

    monkeypatch.setattr(_ad.subprocess, "run", lambda *a, **k: _FakeProc())
    result = _ad.run({"sample_run_dir": str(run_dir)})
    assert (result["status"] == "failed") is True
    # 核可达（是接地失败，非核不可达）——两类失败要区分
    assert (result.get("core_available") is False) is False
    assert ("接地自检未通过" in result.get("error_message", "")) is True


@_requires_hub
def test_real_recon_on_hub_fixture_grounded(monkeypatch) -> None:
    """真调承重核侦察 hub structopt fixture：成功 + 接地全通过 + 草案骨架带
    未注册守卫标记（_GENERATED）。"""
    monkeypatch.setenv(_CORE_ENV, str(_HUB_DIR))
    result = run({"sample_run_dir": str(_HUB_FIXTURE), "module_name": "structopt"})
    assert (result["status"] == "success") is True
    assert (result["core_available"] is True) is True
    assert (result["grounding_ok"] is True) is True
    assert (result["grounding_failures"] == []) is True
    draft = result["draft"]
    assert ("_GENERATED" in draft["module_json_draft"]) is True
    # 三档证据结构齐全
    assert (isinstance(draft["verified"], dict)) is True
    assert (isinstance(draft["proposed"], list)) is True
    assert (isinstance(draft["unverified"], list)) is True


@_requires_hub
def test_read_only_on_sample(monkeypatch, tmp_path) -> None:
    """核对 sample 目录零写入（只读侦察实证）。"""
    monkeypatch.setenv(_CORE_ENV, str(_HUB_DIR))
    run_dir = tmp_path / "20260712-030000-000000"
    run_dir.mkdir()
    (run_dir / "metrics.csv").write_text("iteration,compliance\n1,8570.3\n", encoding="utf-8")
    before = {p.name: p.stat().st_mtime_ns for p in run_dir.iterdir()}
    result = run({"sample_run_dir": str(run_dir)})
    after = {p.name: p.stat().st_mtime_ns for p in run_dir.iterdir()}
    assert (result["status"] == "success") is True
    assert (before == after) is True                 # 零改动
    assert (len(list(run_dir.iterdir())) == 1) is True  # 无新增文件
