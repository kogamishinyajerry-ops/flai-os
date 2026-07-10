"""ScopeRegistry / resolve_source_dir / reconcile_agent_scopes 测试（Wave 1 SPEC §4 witness 清单，一钥一门）。

覆盖：
1. 合法 scope（file_dir/document/public_internal，相对 path_or_uri）注册成功，
   get/list/scope_dir 可用，且直填路线 resolve 正常；
2. 缺 scope.yaml → errors 软记录，不注册（附：YAML 解析失败/顶层非 dict 同路径）；
3. schema 违规（confidentiality 非法枚举）→ errors，不注册；
4. scope_id 与目录名不一致 → errors，不注册；
5. path_or_uri/path_or_uri_env xor 两方向（同时存在/两者都缺，各一钥）；
6. resolve：source=mcp / kind=engineering_experience / env 缺失（消息含变量名）/
   env 存在正常解析（允许指向 scope 外）/ 源目录不存在；
7. path_or_uri "../escape" 在 tmp_path 真目录下逃逸 → InvalidScopePackageError
   （逃逸目标真实存在，证明触发的是逃逸门而非存在性门；收口 tamper T6 铺垫，非 mock）；
8. reconcile 用真 AgentRegistry：enabled=true 引未注册 scope → deregister + 记录；
   enabled=false 引未注册 scope 不检查（边界 witness：disabled 不受咬合）；
9. 密级静态门矩阵（每格独立 witness，含"门不咬公开级"边界格）；
10. scan 幂等：两次结果一致，errors 不累积翻倍；
    附：knowledge_dir 不存在 → 空注册表非错误（SPEC §4 签名承诺的边界）。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from backend.app.config import AGENTS_DIR, CONTRACTS_DIR
from backend.app.core.errors import (
    InvalidScopePackageError,
    KnowledgeSourceUnavailableError,
)
from backend.app.knowledge.scopes import (
    ScopeRegistry,
    reconcile_agent_scopes,
    resolve_source_dir,
)
from backend.app.runtime.registry import AgentRegistry

_SCOPE_SCHEMA = CONTRACTS_DIR / "knowledge_scope.schema.json"
_AGENT_SCHEMA = CONTRACTS_DIR / "agent.schema.json"


def _write_scope(knowledge_dir: Path, dir_name: str, *, overrides=None, drop=(), with_src=True) -> Path:
    """写一个最小合法 scope 包（一钥一门：overrides 覆盖单字段、drop 删单字段）。"""
    scope_dir = knowledge_dir / dir_name
    scope_dir.mkdir(parents=True)
    data = {
        "scope_id": dir_name,
        "name": "测试知识范围",
        "kind": "document",
        "source": "file_dir",
        "path_or_uri": "src",
        "confidentiality": "public_internal",
        "owner": "张工",
    }
    data.update(overrides or {})
    for key in drop:
        data.pop(key, None)
    (scope_dir / "scope.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True), encoding="utf-8"
    )
    if with_src:
        src = scope_dir / "src"
        src.mkdir()
        (src / "doc.md").write_text("APU 手册段落", encoding="utf-8")
    return scope_dir


def _scan(knowledge_dir: Path) -> ScopeRegistry:
    registry = ScopeRegistry(knowledge_dir, _SCOPE_SCHEMA)
    registry.scan()
    return registry


def _make_agent(agents_dir: Path, agent_id: str, *, enabled: bool, scopes: list[str], visibility: str = "admin_only") -> Path:
    """复制 hello_agent 样板改 id/knowledge/permissions 字段，产出过 agent.schema.json 的最小合法包。"""
    dest = agents_dir / agent_id
    shutil.copytree(AGENTS_DIR / "hello_agent", dest)
    yaml_path = dest / "agent.yaml"
    text = yaml_path.read_text(encoding="utf-8")
    text = text.replace("id: hello_agent", f"id: {agent_id}")
    scopes_block = "".join(f"\n    - {s}" for s in scopes) if scopes else " []"
    text = text.replace(
        "knowledge:\n  enabled: false\n  scopes: []",
        f"knowledge:\n  enabled: {'true' if enabled else 'false'}\n  scopes:{scopes_block}",
    )
    text = text.replace("visibility: admin_only", f"visibility: {visibility}")
    yaml_path.write_text(text, encoding="utf-8")
    return dest


def _reconcile_setup(tmp_path: Path, *, confidentiality: str, visibility: str):
    """一个 scope（给定密级）× 一个 enabled agent（给定 visibility）→ 对账结果。"""
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    _write_scope(knowledge_dir, "dept_docs", overrides={"confidentiality": confidentiality})
    scope_registry = _scan(knowledge_dir)
    assert scope_registry.errors == []

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _make_agent(agents_dir, "probe_agent", enabled=True, scopes=["dept_docs"], visibility=visibility)
    agent_registry = AgentRegistry(agents_dir, _AGENT_SCHEMA)
    agent_registry.scan()
    assert agent_registry.get("probe_agent") is not None  # 前置：对账前已注册

    records = reconcile_agent_scopes(agent_registry, scope_registry)
    return agent_registry, records


# ---------------------------------------------------------------- scan 注册面


def test_scan_registers_valid_scope(tmp_path):
    """witness 1：合法 scope 注册成功，get/list/scope_dir 可用，直填路线 resolve 正常。"""
    knowledge_dir = tmp_path / "knowledge"
    scope_dir = _write_scope(knowledge_dir, "apu_manuals")
    registry = _scan(knowledge_dir)

    scope = registry.get("apu_manuals")
    assert scope is not None
    assert scope["scope_id"] == "apu_manuals"
    assert any(s["scope_id"] == "apu_manuals" for s in registry.list())
    assert registry.scope_dir("apu_manuals") == scope_dir
    assert registry.errors == []
    # 直填相对路径 happy path：解析到 scope 目录内的真实 src 目录。
    assert resolve_source_dir(scope, scope_dir) == (scope_dir / "src").resolve()


def test_scan_missing_scope_yaml_not_registered(tmp_path):
    """witness 2：缺 scope.yaml → errors 软记录 + 不注册，scan 不崩溃。"""
    knowledge_dir = tmp_path / "knowledge"
    (knowledge_dir / "no_yaml_scope").mkdir(parents=True)
    registry = _scan(knowledge_dir)

    assert registry.get("no_yaml_scope") is None
    assert registry.list() == []
    assert len(registry.errors) == 1
    assert registry.errors[0]["path"] == str(knowledge_dir / "no_yaml_scope")
    assert "scope.yaml" in registry.errors[0]["error"]


def test_scan_unparseable_yaml_not_registered(tmp_path):
    """witness 2 附：YAML 解析失败 → errors + 跳过（fail-closed 不注册）。"""
    knowledge_dir = tmp_path / "knowledge"
    bad = knowledge_dir / "bad_yaml_scope"
    bad.mkdir(parents=True)
    (bad / "scope.yaml").write_text("{ 未闭合的 flow mapping: [", encoding="utf-8")
    registry = _scan(knowledge_dir)

    assert registry.list() == []
    assert len(registry.errors) == 1
    assert "解析失败" in registry.errors[0]["error"]


def test_scan_non_dict_top_level_not_registered(tmp_path):
    """witness 2 附：scope.yaml 顶层是标量非 object → errors + 跳过。"""
    knowledge_dir = tmp_path / "knowledge"
    bad = knowledge_dir / "scalar_scope"
    bad.mkdir(parents=True)
    (bad / "scope.yaml").write_text("只是一个字符串", encoding="utf-8")
    registry = _scan(knowledge_dir)

    assert registry.list() == []
    assert len(registry.errors) == 1
    assert "object" in registry.errors[0]["error"]


def test_scan_undecodable_yaml_contained_others_registered(tmp_path):
    """witness 2 附（codex Wave1-R1 P2）：scope.yaml 非 UTF-8 字节 → 读取失败
    收容为单包软错误 + 跳过，**同目录其余合法 scope 照常注册**——一个坏包
    绝不炸穿 scan() 拖死整个 assemble() 启动（API 与 worker 都过 assemble）。"""
    knowledge_dir = tmp_path / "knowledge"
    _write_scope(knowledge_dir, "good_scope")
    bad = knowledge_dir / "undecodable_scope"
    bad.mkdir(parents=True)
    (bad / "scope.yaml").write_bytes(b"\xff\xfe\x00\x00 not utf-8")
    registry = _scan(knowledge_dir)

    assert registry.get("good_scope") is not None, "合法包不得被坏包连坐"
    assert registry.get("undecodable_scope") is None
    assert len(registry.errors) == 1
    assert "读取失败" in registry.errors[0]["error"]


def test_scan_schema_violation_not_registered(tmp_path):
    """witness 3：confidentiality 用枚举外乱写值 → schema 校验拒绝，不注册。"""
    knowledge_dir = tmp_path / "knowledge"
    _write_scope(knowledge_dir, "bad_conf_scope", overrides={"confidentiality": "乱写密级"})
    registry = _scan(knowledge_dir)

    assert registry.get("bad_conf_scope") is None
    assert len(registry.errors) == 1
    assert "knowledge_scope.schema.json" in registry.errors[0]["error"]


def test_scan_scope_id_dir_name_mismatch_not_registered(tmp_path):
    """witness 4：scope_id 与目录名不一致 → 两个名字都取不到（防路径混淆）。"""
    knowledge_dir = tmp_path / "knowledge"
    _write_scope(knowledge_dir, "real_dir_name", overrides={"scope_id": "other_id"})
    registry = _scan(knowledge_dir)

    assert registry.get("other_id") is None
    assert registry.get("real_dir_name") is None
    assert len(registry.errors) == 1
    assert "不一致" in registry.errors[0]["error"]


def test_scan_xor_both_present_not_registered(tmp_path):
    """witness 5a：path_or_uri 与 path_or_uri_env 同时存在 → xor 拒绝。"""
    knowledge_dir = tmp_path / "knowledge"
    _write_scope(knowledge_dir, "both_scope", overrides={"path_or_uri_env": "FLAI_TEST_SRC"})
    registry = _scan(knowledge_dir)

    assert registry.get("both_scope") is None
    assert len(registry.errors) == 1
    assert "path_or_uri" in registry.errors[0]["error"]


def test_scan_xor_both_absent_not_registered(tmp_path):
    """witness 5b：两者都缺 → xor 拒绝（另一方向，独立钥匙）。"""
    knowledge_dir = tmp_path / "knowledge"
    _write_scope(knowledge_dir, "neither_scope", drop=("path_or_uri",))
    registry = _scan(knowledge_dir)

    assert registry.get("neither_scope") is None
    assert len(registry.errors) == 1
    assert "path_or_uri" in registry.errors[0]["error"]


def test_scan_missing_knowledge_dir_is_empty_not_error(tmp_path):
    """边界 witness（SPEC §4 签名承诺）：knowledge_dir 不存在 → 空注册表，不是错误。"""
    registry = _scan(tmp_path / "does_not_exist")
    assert registry.list() == []
    assert registry.errors == []


def test_scan_idempotent_errors_not_doubled(tmp_path):
    """witness 10：scan 两次结果一致，errors 覆盖式重建不累积翻倍。"""
    knowledge_dir = tmp_path / "knowledge"
    _write_scope(knowledge_dir, "good_scope")
    (knowledge_dir / "broken_scope").mkdir()  # 缺 scope.yaml 的坏包
    registry = _scan(knowledge_dir)
    first_ids = [s["scope_id"] for s in registry.list()]
    assert first_ids == ["good_scope"]
    assert len(registry.errors) == 1

    registry.scan()
    assert [s["scope_id"] for s in registry.list()] == first_ids
    assert len(registry.errors) == 1
    assert registry.get("good_scope") is not None


# ------------------------------------------------------- resolve_source_dir


def test_resolve_source_mcp_unavailable(tmp_path):
    """witness 6a：source=mcp 未接入 → 诚实 Unavailable（不静默空结果）。"""
    knowledge_dir = tmp_path / "knowledge"
    scope_dir = _write_scope(knowledge_dir, "mcp_scope", overrides={"source": "mcp"})
    registry = _scan(knowledge_dir)
    scope = registry.get("mcp_scope")
    assert scope is not None  # 前置：注册面不拒 mcp，拒在 resolve 面

    with pytest.raises(KnowledgeSourceUnavailableError):
        resolve_source_dir(scope, scope_dir)


def test_resolve_kind_not_document_unavailable(tmp_path):
    """witness 6b：kind=engineering_experience 不由本服务承载 → Unavailable。"""
    knowledge_dir = tmp_path / "knowledge"
    scope_dir = _write_scope(
        knowledge_dir, "exp_scope", overrides={"kind": "engineering_experience"}
    )
    registry = _scan(knowledge_dir)
    scope = registry.get("exp_scope")
    assert scope is not None

    with pytest.raises(KnowledgeSourceUnavailableError):
        resolve_source_dir(scope, scope_dir)


def test_resolve_env_missing_unavailable_with_var_name(tmp_path, monkeypatch):
    """witness 6c：path_or_uri_env 变量缺失 → Unavailable，消息含变量名（部署排障）。"""
    knowledge_dir = tmp_path / "knowledge"
    scope_dir = _write_scope(
        knowledge_dir,
        "env_scope",
        overrides={"path_or_uri_env": "FLAI_TEST_KNOWLEDGE_SRC"},
        drop=("path_or_uri",),
    )
    registry = _scan(knowledge_dir)
    scope = registry.get("env_scope")
    assert scope is not None
    monkeypatch.delenv("FLAI_TEST_KNOWLEDGE_SRC", raising=False)

    with pytest.raises(KnowledgeSourceUnavailableError) as exc_info:
        resolve_source_dir(scope, scope_dir)
    assert "FLAI_TEST_KNOWLEDGE_SRC" in str(exc_info.value)


def test_resolve_env_present_resolves_outside_scope_dir(tmp_path, monkeypatch):
    """witness 6d：env 存在 → 正常解析；env 路线由部署方受控，允许指向 scope 目录外。"""
    knowledge_dir = tmp_path / "knowledge"
    scope_dir = _write_scope(
        knowledge_dir,
        "env_scope",
        overrides={"path_or_uri_env": "FLAI_TEST_KNOWLEDGE_SRC"},
        drop=("path_or_uri",),
    )
    external = tmp_path / "external_src"
    external.mkdir()
    (external / "doc.md").write_text("部署方注入的仓外语料", encoding="utf-8")
    registry = _scan(knowledge_dir)
    scope = registry.get("env_scope")
    assert scope is not None
    monkeypatch.setenv("FLAI_TEST_KNOWLEDGE_SRC", str(external))

    resolved = resolve_source_dir(scope, scope_dir)
    assert resolved == external.resolve()
    assert resolved.is_relative_to(scope_dir.resolve()) is False  # 确证解析到了 scope 外


def test_resolve_missing_source_dir_unavailable(tmp_path):
    """witness 6e：路径合法但目录不存在 → Unavailable（存在性门，独立于逃逸门）。"""
    knowledge_dir = tmp_path / "knowledge"
    scope_dir = _write_scope(
        knowledge_dir, "no_src_scope", overrides={"path_or_uri": "missing_src"}, with_src=False
    )
    registry = _scan(knowledge_dir)
    scope = registry.get("no_src_scope")
    assert scope is not None

    with pytest.raises(KnowledgeSourceUnavailableError):
        resolve_source_dir(scope, scope_dir)


def test_resolve_relative_escape_rejected(tmp_path):
    """witness 7（T6 铺垫，真目录非 mock）：path_or_uri "../escape" resolve 后逃逸出
    scope 目录 → InvalidScopePackageError。逃逸目标是真实存在的目录——存在性门
    可通过，故唯一能触发拒绝的是逃逸门（一钥一门）。
    """
    knowledge_dir = tmp_path / "knowledge"
    scope_dir = _write_scope(
        knowledge_dir, "esc_scope", overrides={"path_or_uri": "../escape"}, with_src=False
    )
    escape_target = knowledge_dir / "escape"
    escape_target.mkdir()
    (escape_target / "leak.md").write_text("scope 外的内容", encoding="utf-8")
    assert escape_target.is_dir() is True  # 前置：目标真实存在，存在性门不背锅
    registry = _scan(knowledge_dir)
    scope = registry.get("esc_scope")
    assert scope is not None  # 注册面不拒（静态看是相对路径），拒在 resolve 逃逸门

    with pytest.raises(InvalidScopePackageError):
        resolve_source_dir(scope, scope_dir)


# --------------------------------------------------- reconcile_agent_scopes


def test_reconcile_unregistered_scope_deregisters_agent(tmp_path):
    """witness 8a：enabled=true 引用未注册 scope → deregister + 返回记录 + errors 记录。"""
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    scope_registry = _scan(knowledge_dir)

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _make_agent(agents_dir, "probe_agent", enabled=True, scopes=["ghost_scope"])
    agent_registry = AgentRegistry(agents_dir, _AGENT_SCHEMA)
    agent_registry.scan()
    assert agent_registry.get("probe_agent") is not None

    records = reconcile_agent_scopes(agent_registry, scope_registry)

    assert agent_registry.get("probe_agent") is None
    assert len(records) == 1
    assert records[0]["agent_id"] == "probe_agent"
    assert records[0]["scope_id"] == "ghost_scope"
    assert any("ghost_scope" in e["error"] for e in agent_registry.errors)


def test_reconcile_disabled_agent_not_checked(tmp_path):
    """witness 8b（边界）：enabled=false 时未注册 scope 引用不检查——disabled Agent
    的 scopes 只是配置残留，不构成访问面，reconcile 不咬。
    """
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    scope_registry = _scan(knowledge_dir)

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _make_agent(agents_dir, "sleepy_agent", enabled=False, scopes=["ghost_scope"])
    agent_registry = AgentRegistry(agents_dir, _AGENT_SCHEMA)
    agent_registry.scan()
    assert agent_registry.get("sleepy_agent") is not None

    records = reconcile_agent_scopes(agent_registry, scope_registry)

    assert records == []
    assert agent_registry.get("sleepy_agent") is not None
    assert agent_registry.errors == []


def test_gate_restricted_denies_department_trial(tmp_path):
    """witness 9①：restricted × department_trial → 拒（deregister）。"""
    agent_registry, records = _reconcile_setup(
        tmp_path, confidentiality="restricted", visibility="department_trial"
    )
    assert agent_registry.get("probe_agent") is None
    assert len(records) == 1
    assert records[0]["scope_id"] == "dept_docs"


def test_gate_restricted_allows_admin_only(tmp_path):
    """witness 9②：restricted × admin_only → 过。"""
    agent_registry, records = _reconcile_setup(
        tmp_path, confidentiality="restricted", visibility="admin_only"
    )
    assert agent_registry.get("probe_agent") is not None
    assert records == []


def test_gate_department_denies_all(tmp_path):
    """witness 9③：department × all → 拒。"""
    agent_registry, records = _reconcile_setup(
        tmp_path, confidentiality="department", visibility="all"
    )
    assert agent_registry.get("probe_agent") is None
    assert len(records) == 1


def test_gate_department_allows_department_trial(tmp_path):
    """witness 9④：department × department_trial → 过。"""
    agent_registry, records = _reconcile_setup(
        tmp_path, confidentiality="department", visibility="department_trial"
    )
    assert agent_registry.get("probe_agent") is not None
    assert records == []


def test_gate_public_internal_allows_all(tmp_path):
    """witness 9⑤（边界）：public_internal × all → 过——门不咬公开级。"""
    agent_registry, records = _reconcile_setup(
        tmp_path, confidentiality="public_internal", visibility="all"
    )
    assert agent_registry.get("probe_agent") is not None
    assert records == []
