"""P0 导入准入门（docs/PRODUCTION-READINESS-PROGRAM.md）本机 5 项验证 + tamper 见证。

覆盖 Gate1 本机可做项（B1 真 drill / B3 内网延迟实测须目标机，不在此）：
- B2 `config.assert_local_db_path`：网络盘 fail-closed 拒启（UNC 跨平台可测）。
- B3 gateway 超时可配：构造期 `timeout_s`/`FLAI_LLM_TIMEOUT_S` → httpx.post timeout；
     采样脚本 percentile/summarize 纯函数（反空洞：工具产出可复算 p99，非手写）。
- N2 registry 交互护栏：interactive 声明 tools/knowledge → 注册期 fail-closed 拒载。
- M2† `/api/readyz`：worker 心跳新鲜 200 / 缺失·过期 503（不再假 200）。

各项 tamper 见证（拆防御→对应断言红）标在每节注释；实证咬合由 scratchpad tamper 脚本
逐一跑（拆一层→红→还原→绿），本文件是常驻正/负回归。
"""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import httpx
import pytest
import yaml

from backend.app import config
from backend.app.config import AGENTS_DIR, CONTRACTS_DIR
from backend.app.model_gateway import gateway as gateway_mod
from backend.app.model_gateway.gateway import ModelGateway
from backend.app.runtime.registry import AgentRegistry
from backend.app.storage import db as db_mod
from backend.app.storage import repos

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILES_PATH = REPO_ROOT / "backend" / "app" / "model_gateway" / "profiles.yaml"
_AGENT_SCHEMA = CONTRACTS_DIR / "agent.schema.json"


# ══ P0-B2：DB 本地盘 fail-closed 强制 ═══════════════════════════════════════
# tamper：删 config.assert_local_db_path 的 UNC 分支 → 下面两 reject 变红（网络盘被放行）。

@pytest.mark.parametrize("bad", [
    "//fileserver/share/flai_os.db",
    "\\\\fileserver\\share\\flai_os.db",
])
def test_b2_unc_path_rejected(bad: str) -> None:
    with pytest.raises(ValueError, match="P0-B2"):
        config.assert_local_db_path(bad)


def test_b2_local_path_ok(tmp_path: Path) -> None:
    config.assert_local_db_path(tmp_path / "flai_os.db")  # 不抛即通过


# ══ P0-B3：模型网关超时可配 ═══════════════════════════════════════════════
# tamper：把 gateway._post 的 timeout 回退硬编码 60 → test_b3_timeout_flows/default 变红。

def _conn_factory(tmp_path: Path):
    p = tmp_path / "gw.db"
    db_mod.init_db(p)
    return lambda: db_mod.get_conn(p)


def _capture_timeout_post(captured: dict):
    def fake_post(url, *, json, headers, timeout):
        captured["timeout"] = timeout
        transport = httpx.MockTransport(lambda req: httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "usage": {}}))
        with httpx.Client(transport=transport) as c:
            return c.post(url, json=json, headers=headers)
    return fake_post


def _set_llm_env(monkeypatch) -> None:
    monkeypatch.setenv("FLAI_LLM_BASE_URL", "https://fake-llm.internal")
    monkeypatch.setenv("FLAI_LLM_API_KEY", "fake-key")
    monkeypatch.setenv("FLAI_LLM_MODEL_REASONING", "glm-mock")


def test_b3_timeout_flows_to_httpx(tmp_path: Path, monkeypatch) -> None:
    _set_llm_env(monkeypatch)
    captured: dict = {}
    monkeypatch.setattr(gateway_mod.httpx, "post", _capture_timeout_post(captured))
    gw = ModelGateway(PROFILES_PATH, conn_factory=_conn_factory(tmp_path), timeout_s=7.5)
    gw.chat("reasoning", [{"role": "user", "content": "x"}], task_id="t_b3")
    assert captured["timeout"] == 7.5  # 硬编码 60 会令此断言红


def test_b3_default_timeout_is_config(tmp_path: Path, monkeypatch) -> None:
    _set_llm_env(monkeypatch)
    captured: dict = {}
    monkeypatch.setattr(gateway_mod.httpx, "post", _capture_timeout_post(captured))
    gw = ModelGateway(PROFILES_PATH, conn_factory=_conn_factory(tmp_path))  # 不传 timeout_s
    gw.chat("reasoning", [{"role": "user", "content": "x"}], task_id="t_b3d")
    assert captured["timeout"] == config.LLM_TIMEOUT_S  # 默认取 config env 派生值，非硬编码 60


def _load_latency_script():
    path = REPO_ROOT / "scripts" / "measure_llm_latency.py"
    spec = importlib.util.spec_from_file_location("measure_llm_latency", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_b3_percentile_nearest_rank() -> None:
    m = _load_latency_script()
    vals = [10.0, 20.0, 30.0, 40.0, 100.0]  # 已升序
    assert m.percentile(vals, 0.50) == 30.0
    assert m.percentile(vals, 0.99) == 100.0
    assert m.percentile(vals, 0.0) == 10.0


def test_b3_summarize_empty_no_fabrication() -> None:
    m = _load_latency_script()
    s = m.summarize([])
    assert s["n"] == 0 and s["p99_ms"] is None  # 空样本不伪造数字


# ══ P0-N2：交互 Agent 声明护栏 ════════════════════════════════════════════
# tamper：删 registry._load_one 的 N2 不变量 → 下面两 reject 变红（畸形交互包被接受）。

def _clone(src_id: str, agents_dir: Path, new_id: str | None = None) -> Path:
    dest = agents_dir / (new_id or src_id)
    shutil.copytree(AGENTS_DIR / src_id, dest)
    return dest


def _patch_yaml(pkg: Path, **dotted) -> None:
    data = yaml.safe_load((pkg / "agent.yaml").read_text(encoding="utf-8"))
    for path, val in dotted.items():
        node = data
        parts = path.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = val
    (pkg / "agent.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def _scan(agents_dir: Path) -> AgentRegistry:
    reg = AgentRegistry(agents_dir, _AGENT_SCHEMA)
    reg.scan()
    return reg


def test_n2_interactive_with_tools_rejected(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    pkg = _clone("guide_agent", agents_dir)
    _patch_yaml(pkg, tools=["excel_case_parser"])  # interactive + 非空 tools
    reg = _scan(agents_dir)
    assert reg.get("guide_agent") is None  # fail-closed 拒载
    assert any("interactive" in str(e) or "N2" in str(e) for e in reg.errors)


def test_n2_interactive_with_knowledge_rejected(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    pkg = _clone("guide_agent", agents_dir)
    _patch_yaml(pkg, **{"knowledge.enabled": True, "knowledge.scopes": ["department"]})
    reg = _scan(agents_dir)
    assert reg.get("guide_agent") is None
    assert any("interactive" in str(e) or "N2" in str(e) for e in reg.errors)


def test_n2_clean_interactive_registers(tmp_path: Path) -> None:
    """正控：合规交互包（tools=[]/knowledge.enabled=false）照常注册——证 N2 有判别力非全拒。"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _clone("guide_agent", agents_dir)
    reg = _scan(agents_dir)
    assert reg.get("guide_agent") is not None


# ══ P0-M2†：/api/readyz worker 心跳新鲜度 ════════════════════════════════════
# tamper：把 readyz 的 status_code 恒 200（或 fresh 恒 True）→ no_worker/stale 变红。

def test_readyz_503_when_no_worker(app_env) -> None:
    client, _app = app_env
    r = client.get("/api/readyz")
    assert r.status_code == 503  # fixture 不起 worker，无心跳 → 不就绪，不再假 200
    assert r.json()["worker"]["present"] is False


def test_readyz_200_when_fresh(app_env) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        repos.beat_worker_heartbeat(conn, generation="test-gen")
    finally:
        conn.close()
    r = client.get("/api/readyz")
    assert r.status_code == 200
    assert r.json()["worker"]["fresh"] is True


def test_readyz_503_when_stale(app_env) -> None:
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        conn.execute(
            "INSERT INTO worker_heartbeats (worker_id, generation, detail, started_at, last_beat_at) "
            "VALUES ('default', 'g', NULL, ?, ?) "
            "ON CONFLICT(worker_id) DO UPDATE SET last_beat_at = excluded.last_beat_at",
            ("2020-01-01T00:00:00+00:00", "2020-01-01T00:00:00+00:00"),
        )
    finally:
        conn.close()
    r = client.get("/api/readyz")
    assert r.status_code == 503  # 心跳过期 → 不就绪
    assert r.json()["worker"]["fresh"] is False
