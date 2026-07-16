"""知识引用回源（评审 N7 / ADR-0029）测试：ChunkProvenanceReader 密级门 + API 端点。

两层钥匙：
- 单元层（真 ScopeRegistry + 真 KnowledgeService + tmp 语料）：密级门四态
  （public_internal/department 放行、restricted 拒、枚举外拒）、歧义如实报、
  source 消歧、缺 chunk 回 None、门先于读（拒绝路径绝不触碰语料）；
- API 层（真 app + 真登录，conftest F6 纪律）：状态码映射
  200/401/403/404/409 与响应七字段形状。

「枚举外密级」一格说明：ScopeRegistry 对 schema 违规 scope 根本不注册，真注册
表里造不出枚举外密级——该分支防的是**未来 schema 枚举扩张而门未同步**的静默
放行。故用最小 stub 注册表单测门本身（如实标注：stub 仅此一格，其余全真件），
并用「service 被触碰即炸」的哨兵证明门先于读。
"""

from __future__ import annotations

from typing import Any, Iterator

import pytest
import yaml
from conftest import REPO_ROOT, seed_and_login
from fastapi.testclient import TestClient

from backend.app.core.errors import KnowledgeScopeNotRegisteredError
from backend.app.knowledge.provenance import (
    ChunkProvenanceReader,
    ProvenanceAccessDeniedError,
    ProvenanceAmbiguousError,
)
from backend.app.knowledge.scopes import ScopeRegistry
from backend.app.knowledge.service import KnowledgeService
from backend.app.main import create_app

_SCOPE_SCHEMA = REPO_ROOT / "contracts" / "knowledge_scope.schema.json"


def _write_scope(
    knowledge_dir, scope_id: str, docs: dict[str, str], *, confidentiality: str
) -> None:
    scope = knowledge_dir / scope_id
    (scope / "docs").mkdir(parents=True)
    (scope / "scope.yaml").write_text(
        yaml.safe_dump(
            {
                "scope_id": scope_id,
                "name": f"provenance 测试 {scope_id}",
                "kind": "document",
                "source": "file_dir",
                "path_or_uri": "docs",
                "confidentiality": confidentiality,
                "owner": "n7-test",
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    for name, text in docs.items():
        path = scope / "docs" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _build_knowledge_dir(tmp_path):
    knowledge_dir = tmp_path / "knowledge"
    # ≥4 篇文档惯例（BM25 idf 退化教训）；chunk_id 可预测 = f"{stem}#0"。
    _write_scope(knowledge_dir, "pub_scope", {
        "em.md": "短舱排液孔堵塞的处置：先查排液孔是否有异物，再对照 EM 手册章节。",
        "ecm.md": "历史 ECM 记录：滑油滤压差告警多与滤芯堵塞相关。",
        "ballast1.md": "起动机更换后需要进行台架测试验证转速指标。",
        "ballast2.md": "燃油系统例行维护包括滤芯更换与管路目视检查。",
    }, confidentiality="public_internal")
    _write_scope(knowledge_dir, "dept_scope", {
        "dept.md": "部门级语料：试验台排期与设备保养记录。",
    }, confidentiality="department")
    _write_scope(knowledge_dir, "sec_scope", {
        "secret.md": "受限语料占位（内容本身无敏感信息，密级标签才是被测对象）。",
    }, confidentiality="restricted")
    # 同 stem 不同子目录 → 同 chunk_id"manual#0"（doc_id 取 stem 的已知碰撞）。
    _write_scope(knowledge_dir, "amb_scope", {
        "a/manual.md": "甲版本手册：适用于 A 构型短舱。",
        "b/manual.md": "乙版本手册：适用于 B 构型短舱。",
    }, confidentiality="public_internal")
    _write_scope(knowledge_dir, "empty_scope", {}, confidentiality="public_internal")
    # 损坏 .xlsx：注册合法、confidentiality public，但建索引时 openpyxl 抛
    # zipfile.BadZipFile → 端点应映射 503（Codex 治理审 R2 P2），不裸抛 500。
    # 需 ≥1 可解析文档陪同以过空语料门前的摄取（这里坏文件本身触发损坏族异常）。
    _write_scope(knowledge_dir, "corrupt_scope", {
        "ok.md": "一段正常可解析的语料，用于陪同损坏文件进入摄取。",
    }, confidentiality="public_internal")
    (knowledge_dir / "corrupt_scope" / "docs" / "broken.xlsx").write_bytes(
        b"PK\x03\x04 this is not a real xlsx zip container"
    )
    # source=mcp：注册合法（schema 允许）但 resolve_source_dir 判「未接入」→
    # 端点应映射 503（Codex 治理审 R0 P2 异常映射补全），不再裸抛 500 泄栈。
    mcp_scope = knowledge_dir / "mcp_scope"
    mcp_scope.mkdir(parents=True)
    (mcp_scope / "scope.yaml").write_text(
        yaml.safe_dump({
            "scope_id": "mcp_scope", "name": "mcp 未接入", "kind": "document",
            "source": "mcp", "path_or_uri": "mcp://placeholder",
            "confidentiality": "public_internal", "owner": "n7-test",
        }, allow_unicode=True),
        encoding="utf-8",
    )
    return knowledge_dir


# ───────────────────────── 单元层：密级门与歧义 ─────────────────────────


@pytest.fixture()
def reader_env(tmp_path) -> ChunkProvenanceReader:
    registry = ScopeRegistry(_build_knowledge_dir(tmp_path), _SCOPE_SCHEMA)
    registry.scan()
    return ChunkProvenanceReader(registry, KnowledgeService(registry))


def test_unregistered_scope_raises(reader_env) -> None:
    with pytest.raises(KnowledgeScopeNotRegisteredError):
        reader_env.read("ghost_scope", "em#0")


def test_public_internal_allowed_full_provenance(reader_env) -> None:
    p = reader_env.read("pub_scope", "em#0")
    assert p is not None
    assert (p.scope_id, p.chunk_id, p.doc_id, p.source) == (
        "pub_scope", "em#0", "em", "em.md",
    )
    assert "排液孔" in p.text
    assert len(p.fingerprint) == 12
    assert p.confidentiality == "public_internal"


def test_department_allowed(reader_env) -> None:
    p = reader_env.read("dept_scope", "dept#0")
    assert p is not None
    assert p.confidentiality == "department"


def test_restricted_denied_fail_closed(reader_env) -> None:
    with pytest.raises(ProvenanceAccessDeniedError) as exc_info:
        reader_env.read("sec_scope", "secret#0")
    assert "restricted" in str(exc_info.value)


def test_unknown_confidentiality_denied_before_touching_corpus() -> None:
    """枚举外密级同拒，且门先于读——见模块 docstring 对 stub 的如实标注。"""

    class _StubRegistry:
        def get(self, scope_id: str) -> dict[str, Any]:
            return {"scope_id": scope_id, "confidentiality": "secret_new_enum"}

        def scope_dir(self, scope_id: str):
            return None  # 盘上不可读 → disk_conf=None → 同拒（fail-closed）

    class _TrippedService:
        def get_chunks_by_id(self, *args: Any, **kwargs: Any) -> None:
            raise AssertionError("密级门必须先于语料读取拦截（门后才准触碰 service）")

    reader = ChunkProvenanceReader(_StubRegistry(), _TrippedService())  # type: ignore[arg-type]
    with pytest.raises(ProvenanceAccessDeniedError):
        reader.read("any_scope", "any#0")


def test_confidentiality_drift_tightened_on_disk_denied(tmp_path) -> None:
    """Codex 治理审 R1 P1：启动快照=public 但盘上 scope.yaml 已收紧为 restricted
    且未重启 → 回源必拒（盘上漂移检查闭合越级泄漏，不靠「重启才生效」运维约定）。"""
    knowledge_dir = _build_knowledge_dir(tmp_path)
    registry = ScopeRegistry(knowledge_dir, _SCOPE_SCHEMA)
    registry.scan()  # 快照此刻 pub_scope=public_internal
    reader = ChunkProvenanceReader(registry, KnowledgeService(registry))
    assert reader.read("pub_scope", "em#0") is not None  # 漂移前正常放行

    # 盘上把密级收紧为 restricted，但不重扫 registry（模拟运行中改配置未重启）。
    yaml_path = knowledge_dir / "pub_scope" / "scope.yaml"
    import yaml as _yaml
    data = _yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    data["confidentiality"] = "restricted"
    yaml_path.write_text(_yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    with pytest.raises(ProvenanceAccessDeniedError):
        reader.read("pub_scope", "em#0")  # 快照 public、盘上 restricted → 拒


def test_missing_chunk_returns_none(reader_env) -> None:
    assert reader_env.read("pub_scope", "em#99") is None


def test_ambiguous_raises_with_sorted_sources(reader_env) -> None:
    with pytest.raises(ProvenanceAmbiguousError) as exc_info:
        reader_env.read("amb_scope", "manual#0")
    assert exc_info.value.sources == ["a/manual.md", "b/manual.md"]


def test_ambiguous_disambiguated_by_source(reader_env) -> None:
    p = reader_env.read("amb_scope", "manual#0", source="b/manual.md")
    assert p is not None
    assert p.source == "b/manual.md"
    assert "乙版本" in p.text


def test_source_mismatch_returns_none(reader_env) -> None:
    assert reader_env.read("amb_scope", "manual#0", source="c/manual.md") is None


# ───────────────────────── API 层：状态码映射与形状 ─────────────────────────


@pytest.fixture()
def api_env(tmp_path) -> Iterator[tuple[TestClient, Any]]:
    app = create_app(
        agents_dir=REPO_ROOT / "agents",
        tools_dir=REPO_ROOT / "tools_impl",
        contracts_dir=REPO_ROOT / "contracts",
        knowledge_dir=_build_knowledge_dir(tmp_path),
        db_path=tmp_path / "flai_os.db",
        uploads_dir=tmp_path / "uploads",
        task_runs_dir=tmp_path / "task_runs",
    )
    with TestClient(app) as client:
        seed_and_login(client, tmp_path / "flai_os.db")
        yield client, app


def _read(client: TestClient, **params: str):
    return client.get("/api/knowledge/chunk", params=params)


def test_api_happy_200_seven_fields(api_env) -> None:
    client, _app = api_env
    resp = _read(client, scope_id="pub_scope", chunk_id="em#0")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {
        "scope_id", "chunk_id", "doc_id", "source", "fingerprint", "text",
        "confidentiality",
    }
    assert body["chunk_id"] == "em#0"
    assert "排液孔" in body["text"]


def test_api_unregistered_scope_404(api_env) -> None:
    client, _app = api_env
    assert _read(client, scope_id="ghost_scope", chunk_id="em#0").status_code == 404


def test_api_missing_chunk_404_honest_detail(api_env) -> None:
    client, _app = api_env
    resp = _read(client, scope_id="pub_scope", chunk_id="em#99")
    assert resp.status_code == 404
    # 诚实口径：回源读的是当前语料，绝不冒充「检索时点一定不存在」。
    assert "当前语料" in resp.json()["detail"]


def test_api_restricted_403(api_env) -> None:
    client, _app = api_env
    assert _read(client, scope_id="sec_scope", chunk_id="secret#0").status_code == 403


def test_api_ambiguous_409_then_source_disambiguates(api_env) -> None:
    client, _app = api_env
    resp = _read(client, scope_id="amb_scope", chunk_id="manual#0")
    assert resp.status_code == 409
    assert "a/manual.md" in resp.json()["detail"]
    ok = _read(client, scope_id="amb_scope", chunk_id="manual#0", source="a/manual.md")
    assert ok.status_code == 200
    assert ok.json()["source"] == "a/manual.md"


def test_api_empty_corpus_409(api_env) -> None:
    client, _app = api_env
    resp = _read(client, scope_id="empty_scope", chunk_id="x#0")
    assert resp.status_code == 409
    assert "语料为空" in resp.json()["detail"]


def test_api_unavailable_source_503_no_500(api_env) -> None:
    """Codex 治理审 R0 P2：source=mcp（未接入）应映射 503，绝不裸抛 500 泄栈/路径。"""
    client, _app = api_env
    resp = _read(client, scope_id="mcp_scope", chunk_id="x#0")
    assert resp.status_code == 503, resp.text
    # 泛化文案，不外发内部路径细节。
    assert "mcp://" not in resp.json()["detail"]


def test_api_corrupt_office_file_503_no_500(api_env) -> None:
    """Codex 治理审 R2 P2：损坏 .xlsx（zipfile.BadZipFile）应映射 503，不裸抛 500。"""
    client, _app = api_env
    resp = _read(client, scope_id="corrupt_scope", chunk_id="ok#0")
    assert resp.status_code == 503, resp.text


def test_api_unregistered_detail_does_not_echo_scope_id(api_env) -> None:
    """P2：未注册 404 文案泛化，不回显 scope_id（防登录用户枚举受限知识域）。"""
    resp = _read(api_env[0], scope_id="ghost_enum_probe", chunk_id="x#0")
    assert resp.status_code == 404
    assert "ghost_enum_probe" not in resp.json()["detail"]


def test_api_restricted_detail_does_not_echo_confidentiality(api_env) -> None:
    """P2：restricted 403 文案不回显具体密级值 repr。"""
    resp = _read(api_env[0], scope_id="sec_scope", chunk_id="secret#0")
    assert resp.status_code == 403
    assert "'restricted'" not in resp.json()["detail"]


def test_api_long_chunk_id_not_422(api_env) -> None:
    """Codex 治理审 R0 P3：>200 字符的合法 chunk_id 不再被 API 固定 422（上限已提至 512）。
    命中与否由语料定（这里预期 404 miss），但绝不是 422 参数拒绝。"""
    long_id = "x" * 260 + "#0"
    resp = _read(api_env[0], scope_id="pub_scope", chunk_id=long_id)
    assert resp.status_code != 422, resp.text


def test_api_unauthenticated_401(api_env) -> None:
    _client, app = api_env
    anon = TestClient(app)  # 同 test_m11_auth._anon：共享 app 状态、独立 cookie jar
    assert anon.get(
        "/api/knowledge/chunk", params={"scope_id": "pub_scope", "chunk_id": "em#0"}
    ).status_code == 401


def test_api_blank_scope_422(api_env) -> None:
    client, _app = api_env
    assert _read(client, scope_id="", chunk_id="em#0").status_code == 422
