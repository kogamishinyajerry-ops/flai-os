"""T3-a：ConversationService 交互运行时注入 tool_registry + knowledge（Gate2/ADR-0028）。

内核一次性扩展——交互会话 context 注入 tool_registry（default-deny 白名单=agent.yaml.tools）
+ knowledge（仅 knowledge.enabled is True 时，白名单=agent.yaml.knowledge.scopes），镜像 job
路径 ADR-0015。之后新增交互类工具/知识 Agent 零内核 diff 即可声明式取用（T3-b 证据）。

六谓词（每条写成 is True/is False，沿用 test_p0 的 tamper-witness 纪律）：
- is True：交互 context 无条件含 tool_registry 键（_ConvToolRegistryContext）。
- is False（注入门 default-deny）：未声明 knowledge 的交互 agent → 'knowledge' not in context。
- is True：声明 knowledge.enabled → context 含 knowledge 键（_ConvKnowledgeContext）。
- is False（调用期 default-deny 咬）：调不在白名单的工具 → ToolNotAllowedError（绝不进底层 call）；
  search 不在白名单的 scope → KnowledgeScopeDeniedError（绝不进底层 service.search）。
- is True（mis-wire fail-closed）：knowledge.enabled 但未装配 knowledge_service → post_message
  抛错、零消息落库、workflow 从未被调。

tamper（拆一层→对应断言变红，实证 load-bearing）：
① 删 _ConvToolRegistryContext.call 白名单行 → test_conv_tool_wrapper_default_deny 红。
② 删 _ConvKnowledgeContext.search 白名单行 → test_conv_knowledge_wrapper_default_deny 红。
③ knowledge 注入由 `if enabled is True` 改无条件 → test_..._knowledge_absent_when_undeclared 红。
④ 删 post_message mis-wire fail-closed → test_..._knowledge_service_none_failclosed 红。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import backend.app.runtime.conversation as conv_mod
from backend.app.core.errors import KnowledgeScopeDeniedError, ToolNotAllowedError
from backend.app.runtime.conversation import (
    ConversationService,
    _ConvKnowledgeContext,
    _ConvToolRegistryContext,
)
from backend.app.storage import db as db_mod
from backend.app.storage import repos


# ══ 单元：会话变体包装的 default-deny（安全核心，DRY option A：与 job 路径同 1 行）═══

class _RecordingToolRegistry:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def call(self, tool_id: str, payload: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        self.calls.append(tool_id)
        return {"status": "success", "echo": payload}


class _StubToolRegistry:
    """带 .get() 的工具注册表桩（B1 注入期安全门据元数据核对 interactive_safe/分级用）。
    call() 计数——被安全门拒的工具绝不应进 call（注入期就挡，workflow 从未被调）。"""

    def __init__(self, tools: dict[str, dict[str, Any]]) -> None:
        self._tools = tools
        self.calls: list[str] = []

    def get(self, tool_id: str) -> dict[str, Any] | None:
        return self._tools.get(tool_id)

    def call(self, tool_id: str, payload: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        self.calls.append(tool_id)
        return {"status": "success", "echo": payload}


@dataclass(frozen=True)
class _Hit:
    scope_id: str
    chunk_id: str
    doc_id: str
    text: str
    source: str
    fingerprint: str
    score: float


class _RecordingKnowledgeService:
    def __init__(self) -> None:
        self.searched: list[str] = []

    def search(self, scope_id: str, query: str, top_k: int = 5) -> list[_Hit]:
        self.searched.append(scope_id)
        return [_Hit(scope_id, "c1", "d1", "命中正文", "ecm-archive.csv", "abc123def456", 1.5)]


def test_conv_tool_wrapper_default_deny() -> None:
    """白名单内放行、白名单外 ToolNotAllowedError 且**绝不**进底层 registry.call。
    tamper：删 `if tool_id not in self._allowed_tools: raise` → 拒绝调用穿透进底层，本测试红。"""
    reg = _RecordingToolRegistry()
    ctx = _ConvToolRegistryContext(reg, "conv_x", "agent_x", frozenset({"allowed_tool"}))

    assert ctx.call("allowed_tool", {"k": 1})["status"] == "success"
    assert reg.calls == ["allowed_tool"]

    with pytest.raises(ToolNotAllowedError):
        ctx.call("other_tool", {})
    assert reg.calls == ["allowed_tool"], "default-deny 拒绝的工具绝不进底层 registry.call"


def test_conv_knowledge_wrapper_default_deny_and_provenance() -> None:
    """白名单内放行（asdict + 出处随行）、白名单外 KnowledgeScopeDeniedError 且**绝不**进底层
    service.search。tamper：删 `if scope_id not in self._allowed_scopes: raise` → 拒绝检索穿透，本测试红。"""
    svc = _RecordingKnowledgeService()
    ctx = _ConvKnowledgeContext(svc, "conv_x", "agent_x", frozenset({"allowed_scope"}))

    hits = ctx.search("allowed_scope", "查询词")
    assert svc.searched == ["allowed_scope"]
    # asdict → dict，出处四钥随行（source/fingerprint 展示层必须透出，docs/06 §4）
    assert hits[0]["source"] == "ecm-archive.csv"
    assert hits[0]["fingerprint"] == "abc123def456"
    assert hits[0]["chunk_id"] == "c1"

    with pytest.raises(KnowledgeScopeDeniedError):
        ctx.search("other_scope", "查询词")
    assert svc.searched == ["allowed_scope"], "default-deny 拒绝的 scope 绝不进底层 service.search"


# ══ 集成：post_message 注入门（default-deny 于注入门 + mis-wire fail-closed）═════════

class _StubGateway:
    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        return {"content": "stub", "finish_reason": "stop"}


class _FakeAgentRegistry:
    def __init__(self, agent: dict[str, Any], pkg_dir: Path) -> None:
        self._agent = agent
        self._pkg = pkg_dir

    def get(self, agent_id: str) -> dict[str, Any] | None:
        return self._agent if agent_id == self._agent["id"] else None

    def package_dir(self, agent_id: str) -> Path | None:
        return self._pkg if agent_id == self._agent["id"] else None

    def list(self) -> list[dict[str, Any]]:
        return [self._agent]


class _CaptureWorkflow:
    """monkeypatch _load_workflow_module 的返回：run() 捕获 context 并返回合法结果。"""

    def __init__(self) -> None:
        self.context: dict[str, Any] | None = None

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        self.context = context
        return {"assistant_message": "stub reply", "recommendation": None}


def _agent(
    agent_id: str = "stub_interactive",
    *,
    tools: list[str] | None = None,
    knowledge_enabled: bool = False,
    scopes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": agent_id,
        "status": "draft",
        "model": {"profile": "reasoning"},
        "tools": tools or [],
        "knowledge": {"enabled": knowledge_enabled, "scopes": scopes or []},
        "workflow": {"mode": "interactive", "requires_human_review": False},
    }


def _build_service(tmp_path, monkeypatch, agent, *, tool_registry, knowledge_service, capture):
    db_path = tmp_path / "conv.db"
    db_mod.init_db(db_path)

    def conn_factory():
        return db_mod.get_conn(db_path)

    svc = ConversationService(
        _FakeAgentRegistry(agent, tmp_path),
        _StubGateway(),
        conn_factory,
        tool_registry=tool_registry,
        uploads_dir=tmp_path,
        knowledge_service=knowledge_service,
    )
    monkeypatch.setattr(conv_mod, "_load_workflow_module", lambda aid, path: capture)
    return svc, conn_factory


def _open_conv(conn_factory, agent_id: str) -> str:
    conn = conn_factory()
    try:
        conv = repos.create_conversation(
            conn, conversation_id="conv_test", agent_id=agent_id, created_by="tester"
        )
    finally:
        conn.close()
    return conv["id"]


def test_tool_registry_injected_unconditionally_knowledge_absent_when_undeclared(
    tmp_path, monkeypatch
) -> None:
    """is True：交互 context 无条件含 tool_registry。is False（注入门 default-deny）：未声明
    knowledge 的交互 agent → 'knowledge' not in context（访问即 KeyError，镜像 job 905-906）。
    tamper③：knowledge 注入改无条件 → 末行断言变红。"""
    capture = _CaptureWorkflow()
    agent = _agent(knowledge_enabled=False)
    svc, cf = _build_service(
        tmp_path, monkeypatch, agent, tool_registry=object(), knowledge_service=object(), capture=capture
    )
    conv_id = _open_conv(cf, agent["id"])
    svc.post_message(conversation_id=conv_id, content="你好")

    ctx = capture.context
    assert ctx is not None
    assert isinstance(ctx["tool_registry"], _ConvToolRegistryContext), "tool_registry 无条件注入"
    assert "knowledge" not in ctx, "未声明 knowledge 的交互 agent 连键都没有（注入门 default-deny）"


def test_knowledge_injected_when_enabled(tmp_path, monkeypatch) -> None:
    """is True：声明 knowledge.enabled → context 含 knowledge 键（_ConvKnowledgeContext）+
    tool_registry 键。白名单=agent.yaml.knowledge.scopes。"""
    capture = _CaptureWorkflow()
    agent = _agent(knowledge_enabled=True, scopes=["ecm_frr_demo"])
    svc, cf = _build_service(
        tmp_path, monkeypatch, agent, tool_registry=object(), knowledge_service=object(), capture=capture
    )
    conv_id = _open_conv(cf, agent["id"])
    svc.post_message(conversation_id=conv_id, content="你好")

    ctx = capture.context
    assert ctx is not None
    assert isinstance(ctx["knowledge"], _ConvKnowledgeContext)
    assert isinstance(ctx["tool_registry"], _ConvToolRegistryContext)
    assert ctx["knowledge"]._allowed_scopes == frozenset({"ecm_frr_demo"})


def test_tool_whitelist_mirrors_agent_tools(tmp_path, monkeypatch) -> None:
    """注入的 tool_registry 白名单 = frozenset(agent.yaml.tools)——未声明工具即空白名单。
    cfd_result_read 是真数据类工具（interactive_safe=true + internal，run_id 受控句柄非裸路径），
    过 B1 注入期安全门。（不再用 excel_case_parser——R1 撤回后其 interactive_safe=false。）"""
    capture = _CaptureWorkflow()
    agent = _agent(tools=["cfd_result_read"])
    reg = _StubToolRegistry(
        {"cfd_result_read": {"interactive_safe": True, "output_classification": "internal"}}
    )
    svc, cf = _build_service(
        tmp_path, monkeypatch, agent, tool_registry=reg, knowledge_service=object(), capture=capture
    )
    conv_id = _open_conv(cf, agent["id"])
    svc.post_message(conversation_id=conv_id, content="你好")
    assert capture.context["tool_registry"]._allowed_tools == frozenset({"cfd_result_read"})


def test_knowledge_service_none_failclosed_zero_message(tmp_path, monkeypatch) -> None:
    """is True（mis-wire fail-closed）：knowledge.enabled 但未装配 KnowledgeService → post_message
    抛错、零消息落库、workflow 从未被调（镜像 runtime._execute 1b）。
    tamper④：删 post_message 的 mis-wire fail-closed → 不再抛、消息落库、本测试红。"""
    capture = _CaptureWorkflow()
    agent = _agent(knowledge_enabled=True, scopes=["ecm_frr_demo"])
    svc, cf = _build_service(
        tmp_path, monkeypatch, agent, tool_registry=object(), knowledge_service=None, capture=capture
    )
    conv_id = _open_conv(cf, agent["id"])

    with pytest.raises(RuntimeError, match="未装配 KnowledgeService"):
        svc.post_message(conversation_id=conv_id, content="你好")

    conn = cf()
    try:
        assert repos.list_messages(conn, conv_id) == [], "mis-wire 必零消息落库（抛在落库前）"
    finally:
        conn.close()
    assert capture.context is None, "fail-closed 在 workflow 调用前，workflow 绝不被调"


# ══ B1（★核心安全 fail-closed）：交互面工具安全门——只放纯数据类工具（interactive_safe）═══

def _post_expect_failclosed(svc, conv_id, cf, capture, reg, *, match: str) -> None:
    """公共断言：post_message 注入期 fail-closed 拒、零消息落库、workflow 从未被调、工具零执行。"""
    with pytest.raises(RuntimeError, match="交互面工具安全门 fail-closed"):
        svc.post_message(conversation_id=conv_id, content="起个求解")
    conn = cf()
    try:
        assert repos.list_messages(conn, conv_id) == [], "安全门 fail-closed 必零消息落库（抛在落库前）"
    finally:
        conn.close()
    assert capture.context is None, "fail-closed 在 workflow 调用前，workflow 绝不被调"
    assert reg.calls == [], "被安全门拒的工具绝不进底层 call（零执行）"


def test_interactive_side_effect_tool_failclosed_zero_message(tmp_path, monkeypatch) -> None:
    """B1 tamper①：交互 agent 声明副作用工具（cfd_solve_launch 未标 interactive_safe，缺省=拒）→
    post_message 注入期 fail-closed 拒、零消息落库、workflow 从未被调、工具零执行。
    tamper：删 post_message 的 interactive_safe 安全门 for 循环 → 不再抛、消息落库、workflow 被调，本测试红。"""
    capture = _CaptureWorkflow()
    agent = _agent(tools=["cfd_solve_launch"])
    # cfd_solve_launch 现实元数据：internal 但**无 interactive_safe 字段**（default-deny → 拒）。
    reg = _StubToolRegistry({"cfd_solve_launch": {"output_classification": "internal"}})
    svc, cf = _build_service(
        tmp_path, monkeypatch, agent, tool_registry=reg, knowledge_service=object(), capture=capture
    )
    conv_id = _open_conv(cf, agent["id"])
    _post_expect_failclosed(svc, conv_id, cf, capture, reg, match="cfd_solve_launch")


def test_interactive_sensitive_output_tool_failclosed(tmp_path, monkeypatch) -> None:
    """B1 tamper②：交互 agent 声明 sensitive 输出工具（monitor_adapter_recon）——即便误标
    interactive_safe=true，也因 output_classification=sensitive 被拒（双条件缺一即拒，sensitive
    输出会原样落会话消息泄漏）。tamper：删 output_classification==internal 那一支 → 本测试红。"""
    capture = _CaptureWorkflow()
    agent = _agent(tools=["monitor_adapter_recon"])
    reg = _StubToolRegistry(
        {"monitor_adapter_recon": {"interactive_safe": True, "output_classification": "sensitive"}}
    )
    svc, cf = _build_service(
        tmp_path, monkeypatch, agent, tool_registry=reg, knowledge_service=object(), capture=capture
    )
    conv_id = _open_conv(cf, agent["id"])
    _post_expect_failclosed(svc, conv_id, cf, capture, reg, match="monitor_adapter_recon")


def test_interactive_unregistered_tool_failclosed(tmp_path, monkeypatch) -> None:
    """B1：交互 agent 声明未注册工具（registry.get→None，无法核对 interactive_safe）→ 注入期
    fail-closed 拒（比 job 路径「延到调用期」更严：交互安全门在注入期即挡、零消息落库）。
    tamper：删 `if _tool_meta is None: raise` 那一支 → None 元数据被后续 .get 空判穿透，本测试红。"""
    capture = _CaptureWorkflow()
    agent = _agent(tools=["ghost_tool_xyz"])
    reg = _StubToolRegistry({})  # 空注册表：get 任何工具都 None
    svc, cf = _build_service(
        tmp_path, monkeypatch, agent, tool_registry=reg, knowledge_service=object(), capture=capture
    )
    conv_id = _open_conv(cf, agent["id"])
    _post_expect_failclosed(svc, conv_id, cf, capture, reg, match="ghost_tool_xyz")


def test_interactive_data_class_tool_passes(tmp_path, monkeypatch) -> None:
    """B1 阴性对照：数据类工具（interactive_safe=true + internal + 无 shell）正常放行——安全门只拒
    不该放的，绝不误伤纯数据类。放行后 tool_registry 白名单照建、workflow 正常调、user+assistant
    落库。用 cfd_result_read（真数据类；excel_case_parser R1 撤回后已 interactive_safe=false）。"""
    capture = _CaptureWorkflow()
    agent = _agent(tools=["cfd_result_read"])
    reg = _StubToolRegistry(
        {"cfd_result_read": {"interactive_safe": True, "output_classification": "internal"}}
    )
    svc, cf = _build_service(
        tmp_path, monkeypatch, agent, tool_registry=reg, knowledge_service=object(), capture=capture
    )
    conv_id = _open_conv(cf, agent["id"])
    svc.post_message(conversation_id=conv_id, content="你好")
    assert capture.context is not None, "数据类工具应放行，workflow 正常被调"
    assert capture.context["tool_registry"]._allowed_tools == frozenset({"cfd_result_read"})
    conn = cf()
    try:
        assert len(repos.list_messages(conn, conv_id)) == 2, "放行后 user+assistant 正常落库"
    finally:
        conn.close()


def test_interactive_shell_enabled_tool_failclosed_despite_safe_flags(tmp_path, monkeypatch) -> None:
    """★B1 R1-P1-3 tamper 锚（Codex R1）：工具即便 interactive_safe=true + output_classification=
    internal，只要 safety.allow_shell_command=true 也必被拒——shell 能力与交互面纯数据类构造上互斥
    （LLM 会话中途可无人签触发 shell 执行）。tamper：删 post_message 门的 allow_shell_command is True
    那一支 → shell 工具误标 interactive_safe 后被放行、workflow 被调 → 本测试红。"""
    capture = _CaptureWorkflow()
    agent = _agent(tools=["rogue_shell_tool"])
    reg = _StubToolRegistry({
        "rogue_shell_tool": {
            "interactive_safe": True,
            "output_classification": "internal",
            "safety": {"allow_shell_command": True},
        }
    })
    svc, cf = _build_service(
        tmp_path, monkeypatch, agent, tool_registry=reg, knowledge_service=object(), capture=capture
    )
    conv_id = _open_conv(cf, agent["id"])
    _post_expect_failclosed(svc, conv_id, cf, capture, reg, match="allow_shell_command")


def test_real_excel_case_parser_interactive_safe_revoked(tmp_path) -> None:
    """★R1-P1 excel 撤回回归（Codex R1）：真实 tools_impl/excel_case_parser/tool.yaml 的
    interactive_safe 必**非 true**——裸 file_path 无 File Store 容器校验，交互面直调可读任意服务端
    文件泄漏进会话。tamper：把 tool.yaml 的 interactive_safe 改回 true → 本断言红。用真 ToolRegistry
    从磁盘加载核对（非 stub）；并对照三个真安全工具仍 true（撤回外科，无误伤）。"""
    from backend.app.tools.registry import ToolRegistry

    repo_root = Path(__file__).resolve().parents[2]
    reg = ToolRegistry(repo_root / "tools_impl", repo_root / "contracts" / "tool.schema.json")
    reg.scan()
    excel = reg.get("excel_case_parser")
    assert excel is not None, "excel_case_parser 应已注册"
    assert excel.get("interactive_safe") is not True, "excel 撤回后 interactive_safe 必非 true（裸路径泄漏面）"
    for safe_id in ("cfd_result_read", "mock_echo", "performance_disk_mock"):
        meta = reg.get(safe_id)
        assert meta is not None, f"{safe_id} 应已注册"
        assert meta.get("interactive_safe") is True, f"{safe_id} 应仍 interactive_safe=true（撤回未误伤真安全工具）"


# ══ B3-P2-2：会话资源调用留痕成对（tool + knowledge 各 success/failure outcome）═════════

def test_conv_tool_paired_logging_success_and_failure(caplog) -> None:
    """B3-P2-2：工具调用 before + 成功/失败各一条留痕（Codex C3-P2-2）。
    tamper：删 call 的 try/except 失败留痕 → 失败分支无「调用失败」日志，本测试红。"""
    import logging

    class _OKReg:
        def call(self, tool_id, payload, **kw):
            return {"status": "success"}

    class _BoomReg:
        def call(self, tool_id, payload, **kw):
            raise RuntimeError("boom")

    with caplog.at_level(logging.INFO):
        _ConvToolRegistryContext(_OKReg(), "conv_x", "agent_x", frozenset({"t"})).call("t", {})
    assert "工具 t 调用开始" in caplog.text
    assert "工具 t 调用成功" in caplog.text

    caplog.clear()
    with caplog.at_level(logging.INFO):
        ctx_bad = _ConvToolRegistryContext(_BoomReg(), "conv_x", "agent_x", frozenset({"t"}))
        with pytest.raises(RuntimeError, match="boom"):
            ctx_bad.call("t", {})
    assert "工具 t 调用失败" in caplog.text, "工具调用失败必留痕（成对，此前只 before-log）"


def test_conv_knowledge_paired_logging_failure(caplog) -> None:
    """B3-P2-2：知识检索失败也留痕（此前只 after-success-log，异常无痕）。
    tamper：删 search 的 try/except 失败留痕 → 检索异常无「检索失败」日志，本测试红。"""
    import logging

    class _BoomKnow:
        def search(self, scope_id, query, top_k=5):
            raise RuntimeError("kboom")

    with caplog.at_level(logging.INFO):
        ctx = _ConvKnowledgeContext(_BoomKnow(), "conv_x", "agent_x", frozenset({"s"}))
        with pytest.raises(RuntimeError, match="kboom"):
            ctx.search("s", "q")
    assert "知识检索失败" in caplog.text, "知识检索失败必留痕（成对）"
