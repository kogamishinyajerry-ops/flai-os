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
from backend.app.jobs.runner import JobRunner, _HEARTBEAT_INTERVAL_SECONDS
from backend.app.main import _WORKER_STALE_S, _worker_freshness
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


def test_b2_get_conn_boundary_rejects_unc() -> None:
    """P1-1（Codex 命中即审）：get_conn 单一 open 边界也强制——任何 CLI（init_db/
    user_admin/deploy_selfcheck）经此开 UNC 路径必被拦，不只依赖各启动点 assert。
    tamper：删 get_conn 里的 assert_local_db_path 调用 → 本测试变红。"""
    with pytest.raises(ValueError, match="P0-B2"):
        db_mod.get_conn("//share/nope.db")


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


# ══ P0-N2 放宽（T3-a/ADR-0028）：交互声明放行 + 畸形拦截由别处保住 ══════════
# N2 注册期无条件拒载已退休——能力已由 ConversationService 注入布线（tool_registry+knowledge
# default-deny，见 runtime/conversation.py）。畸形拦截**不依赖 N2**，差分式非侵入见证证明真正
# 的守门者仍在（兼作常驻回归）：
#  · reconcile_agent_scopes（knowledge/scopes.py）是 scope 守门者：scan-alone 放行未注册 scope 的
#    交互 agent、scan+reconcile 才 deregister → reconcile load-bearing
#    （test_n2_relaxed_interactive_unregistered_scope_deregistered）；
#  · 调用期 ToolNotRegisteredError（backend/app/tools/registry.py:108-109）是 tool 守门者：会话白名单
#    放行的不存在工具在 call 期诚实抛，与 job 路径对称、绝非静默成功
#    （test_n2_relaxed_interactive_nonexistent_tool_calltime_rejected）。

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


def _scope_registry():
    from backend.app.knowledge.scopes import ScopeRegistry

    sr = ScopeRegistry(config.KNOWLEDGE_DIR, CONTRACTS_DIR / "knowledge_scope.schema.json")
    sr.scan()
    return sr


def test_n2_relaxed_interactive_with_tools_registers(tmp_path: Path) -> None:
    """N2 放宽：交互 Agent 声明**已注册**工具 → 注册期放行（原无条件拒载已退休）。
    能力已由 ConversationService 注入（tool_registry default-deny 白名单），合法声明流通。"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    pkg = _clone("guide_agent", agents_dir)
    _patch_yaml(pkg, tools=["excel_case_parser"])  # interactive + 真实工具
    reg = _scan(agents_dir)
    assert reg.get("guide_agent") is not None, "N2 放宽后合法交互工具声明必须放行"
    assert not any("N2" in str(e) for e in reg.errors), "不应有 N2 拒载残留"


def test_n2_relaxed_interactive_legal_knowledge_registers(tmp_path: Path) -> None:
    """N2 放宽：交互 Agent 声明**已注册且密级兼容**的 scope（ecm_frr_demo=public_internal，
    visibility=all 兼容）→ 经 scan+reconcile 注册通过。"""
    from backend.app.knowledge.scopes import reconcile_agent_scopes

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    pkg = _clone("guide_agent", agents_dir)
    _patch_yaml(pkg, **{"knowledge.enabled": True, "knowledge.scopes": ["ecm_frr_demo"]})
    reg = _scan(agents_dir)
    assert reg.get("guide_agent") is not None  # scan 放行
    reconcile_agent_scopes(reg, _scope_registry())
    assert reg.get("guide_agent") is not None, "合法 scope（public_internal+兼容 visibility）reconcile 后仍注册"


def test_n2_relaxed_interactive_unregistered_scope_deregistered(tmp_path: Path) -> None:
    """畸形-scope 拦截由 reconcile_agent_scopes 保住（非 N2）：交互 Agent 声明未注册 scope →
    scan 放行（证 N2 已退休），scan+reconcile 才 deregister（证 reconcile 是 load-bearing 守门者）。
    tamper：拆 reconcile 的 `if scope is None` 分支 → 末行断言变红。"""
    from backend.app.knowledge.scopes import reconcile_agent_scopes

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    pkg = _clone("guide_agent", agents_dir)
    _patch_yaml(pkg, **{"knowledge.enabled": True, "knowledge.scopes": ["does_not_exist_scope"]})
    reg = _scan(agents_dir)
    assert reg.get("guide_agent") is not None, "N2 退休：注册期不再拒交互+knowledge 声明"
    reconcile_agent_scopes(reg, _scope_registry())
    assert reg.get("guide_agent") is None, "未注册 scope 的交互 agent 必被 reconcile deregister（default-deny）"


def test_n2_relaxed_interactive_nonexistent_tool_calltime_rejected() -> None:
    """畸形-tool 拦截由调用期 ToolNotRegisteredError 保住（非 N2）：会话白名单放行 agent 声明的
    工具，但不存在的工具在 tool_registry.call 期诚实抛（backend/app/tools/registry.py:108-109），
    与 job 路径对称、绝非静默成功（假绿死罪）。差分见证：已注册工具不抛该错。"""
    from backend.app.core.errors import ToolNotRegisteredError
    from backend.app.runtime.conversation import _ConvToolRegistryContext
    from backend.app.tools.registry import ToolRegistry

    tool_reg = ToolRegistry(config.TOOLS_DIR, CONTRACTS_DIR / "tool.schema.json")
    tool_reg.scan()

    # 白名单放行不存在的工具（agent 声明了它）→ 调用期 registration 闸诚实拒
    ctx_bad = _ConvToolRegistryContext(tool_reg, "conv_x", "some_agent", frozenset({"nonexistent_tool"}))
    with pytest.raises(ToolNotRegisteredError):
        ctx_bad.call("nonexistent_tool", {})

    # 差分对照：真实已注册工具在白名单内 → 绝不抛 ToolNotRegisteredError（证 registration 闸
    # 有判别力、不误伤真工具；入参契约等其他失败可接受，只证不是"未注册"）。
    assert tool_reg.get("excel_case_parser") is not None, "前置：excel_case_parser 应已注册"
    ctx_ok = _ConvToolRegistryContext(tool_reg, "conv_x", "some_agent", frozenset({"excel_case_parser"}))
    try:
        ctx_ok.call("excel_case_parser", {})
    except ToolNotRegisteredError:
        pytest.fail("已注册工具不应抛 ToolNotRegisteredError（registration 闸误伤真工具）")
    except Exception:
        pass  # 入参契约等其他失败可接受


def test_n2_clean_interactive_registers(tmp_path: Path) -> None:
    """正控：合规交互包（tools=[]/knowledge.enabled=false）照常注册。"""
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


# ══ P1-3（Codex 命中即审）：心跳独立于任务执行 ═══════════════════════════════
# daemon 每 _HEARTBEAT_INTERVAL 调 runner.beat()，长 job（B3 允许 120s）不饿死心跳。
# tamper：去掉 daemon / 间隔调 ≥ 陈旧窗 → 长 job 期 readyz 假 503（集成级，此处守机制）。

def test_p1_3_heartbeat_interval_under_stale_window() -> None:
    """静态不变量：心跳间隔 < readyz 陈旧窗——否则 daemon 发得再勤也追不上长 job，仍假 503。"""
    assert _HEARTBEAT_INTERVAL_SECONDS < _WORKER_STALE_S


def test_p1_3_beat_freshens_heartbeat(tmp_path: Path) -> None:
    """JobRunner.beat()（心跳 daemon 每 tick 调它）真写出新鲜心跳——daemon 据此在长 job
    期间维持 readyz 新鲜。beat 只用 conn_factory，无需真 runtime。"""
    p = tmp_path / "hb.db"
    db_mod.init_db(p)
    JobRunner(None, lambda: db_mod.get_conn(p)).beat()
    conn = db_mod.get_conn(p)
    try:
        wf = _worker_freshness(conn)
    finally:
        conn.close()
    assert wf["present"] is True and wf["fresh"] is True


# ══ P0-B3 gate_verdict fail-closed（Codex 命中即审 P1-4/P1-5）═══════════════════
# tamper：gate_verdict 去掉 n_fail>0 分支 → survivorship 测试变红（幸存者假绿被放行）。

def test_b3_gate_verdict_pass() -> None:
    m = _load_latency_script()
    ok, _msg = m.gate_verdict(5, [10.0, 20.0, 30.0, 40.0, 50.0], timeout_s=1.0)  # p99=50ms<1s
    assert ok is True


def test_b3_gate_verdict_survivorship_indeterminate() -> None:
    """P1-4：19 快幸存 + 1 超时被排除 → 不可从幸存者算 p99 宣称通过（fail-closed）。"""
    m = _load_latency_script()
    ok, msg = m.gate_verdict(20, [10.0] * 19, timeout_s=120.0)  # n_fail=1（20-19）
    assert ok is False and "indeterminate" in msg


def test_b3_gate_verdict_p99_over_fails() -> None:
    m = _load_latency_script()
    ok, _msg = m.gate_verdict(3, [10.0, 20.0, 5000.0], timeout_s=1.0)  # p99=5s>1s
    assert ok is False


def test_b3_gate_verdict_zero_samples_fails() -> None:
    m = _load_latency_script()
    ok, _msg = m.gate_verdict(0, [], timeout_s=120.0)
    assert ok is False
