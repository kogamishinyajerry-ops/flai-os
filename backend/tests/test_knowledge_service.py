"""KnowledgeService / KnowledgeHit 测试（Wave 1 SPEC §5 witness 清单，一钥一门）。

覆盖：
1. happy path：临时 scope + 3 文档（含子目录）→ 命中，KnowledgeHit 七字段全非空，
   source 是相对 POSIX 路径，fingerprint 长 12；
2. 未注册 scope_id → KnowledgeScopeNotRegisteredError；
3. 空源目录 → KnowledgeIngestError（空语料钥匙）；
4. 缓存失效双向：新增文件后新词命中（manifest 重建钥匙）；修改已有文件后
   旧词消失、新词命中（指纹判据，非 mtime）；
5. query 全空白 → ValueError；top_k=999 等价 50（55 命中语料截到 50，不抛错）；
6. 边界 witness：零命中健康语料 → []（与空语料错误相区分的钥匙）；
7. KnowledgeHit.__post_init__ 出处四钥逐字段非空（收口 tamper T7 同款铺垫）；
8. 信任边界 witness（收口 tamper T5 铺垫）：直调 service 查 restricted scope
   照样成功——service 层不做授权是 docstring 宣称的特性声明，不是 bug。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from backend.app.config import CONTRACTS_DIR
from backend.app.core.errors import (
    KnowledgeIngestError,
    KnowledgeScopeNotRegisteredError,
)
from backend.app.knowledge.scopes import ScopeRegistry
from backend.app.knowledge.service import KnowledgeHit, KnowledgeService

_SCOPE_SCHEMA = CONTRACTS_DIR / "knowledge_scope.schema.json"


def _make_scope(tmp_path: Path, scope_id: str = "apu_docs", *, confidentiality: str = "public_internal") -> Path:
    """写一个最小合法 scope 包（file_dir/document，src/ 源目录），返回 src 目录。"""
    scope_dir = tmp_path / "knowledge" / scope_id
    scope_dir.mkdir(parents=True)
    data = {
        "scope_id": scope_id,
        "name": "测试知识范围",
        "kind": "document",
        "source": "file_dir",
        "path_or_uri": "src",
        "confidentiality": confidentiality,
        "owner": "张工",
    }
    (scope_dir / "scope.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True), encoding="utf-8"
    )
    src = scope_dir / "src"
    src.mkdir()
    return src


def _make_service(tmp_path: Path) -> KnowledgeService:
    registry = ScopeRegistry(tmp_path / "knowledge", _SCOPE_SCHEMA)
    registry.scan()
    assert registry.errors == []  # 前置：scope 包本身合法，后续失败不由注册面背锅
    return KnowledgeService(registry)


# ------------------------------------------------------------- search 主路径


def test_search_happy_path_hit_fields_complete(tmp_path):
    """witness 1：3 文档命中，七字段全非空，source 相对 POSIX 路径，指纹长 12。"""
    src = _make_scope(tmp_path)
    (src / "em_manual.md").write_text("空气起动机由涡轮驱动。", encoding="utf-8")
    (src / "mm_notes.txt").write_text("排液孔堵塞导致滑油渗漏。", encoding="utf-8")
    sub = src / "manuals"
    sub.mkdir()
    (sub / "apu_intro.md").write_text("APU 涡轮转速由 ECB 控制。", encoding="utf-8")
    service = _make_service(tmp_path)

    hits = service.search("apu_docs", "涡轮")

    assert len(hits) == 2  # em_manual 与 manuals/apu_intro 含"涡轮"，mm_notes 不含
    sources = {h.source for h in hits}
    assert sources == {"em_manual.md", "manuals/apu_intro.md"}  # 相对 POSIX 路径出处
    for h in hits:
        assert isinstance(h, KnowledgeHit)
        assert h.scope_id == "apu_docs"
        assert h.chunk_id.strip() != ""
        assert h.doc_id.strip() != ""
        assert h.text.strip() != ""
        assert h.source.strip() != ""
        assert len(h.fingerprint) == 12
        assert h.score > 0


def test_search_unregistered_scope_rejected(tmp_path):
    """witness 2：scope_id 未注册 → KnowledgeScopeNotRegisteredError（query 合法）。"""
    _make_scope(tmp_path)  # 注册面健康，唯一违规点是 scope_id 不存在
    service = _make_service(tmp_path)

    with pytest.raises(KnowledgeScopeNotRegisteredError):
        service.search("ghost_scope", "涡轮")


def test_search_empty_corpus_rejected(tmp_path):
    """witness 3：源目录存在但为空 → KnowledgeIngestError（fail-closed，
    与健康语料的零命中 [] 相区分——空语料绝不静默回空列表）。
    """
    _make_scope(tmp_path)  # src/ 存在但不放任何文档
    service = _make_service(tmp_path)

    with pytest.raises(KnowledgeIngestError) as exc_info:
        service.search("apu_docs", "涡轮")
    assert "语料为空" in str(exc_info.value)


def test_search_zero_hit_healthy_corpus_returns_empty(tmp_path):
    """witness 6（边界）：语料健康但查询词全在语料外 → []，不抛错——
    「查过了没有」与「没得查」（witness 3 的 KnowledgeIngestError）是两回事。
    """
    src = _make_scope(tmp_path)
    (src / "doc.md").write_text("空气起动机由涡轮驱动。", encoding="utf-8")
    service = _make_service(tmp_path)

    assert service.search("apu_docs", "液压舵机") == []


# --------------------------------------------------------------- 缓存失效双向

# 压舱文档：让语料 ≥3 篇且与各查询词零重叠。BM25 复刻件在 1-2 篇语料下全词表
# idf ≤ 0（参考实现的小语料退化，bm25.py golden G2 钉死的行为），score>0 过滤
# 会吞掉一切命中——witness 语料必须让查询词 n=1、N≥3 拿到正 idf，别赌地板符号。
_BALLAST = {
    "ballast1.md": "滑油温度传感器校准记录。",
    "ballast2.md": "燃油流量计维护手册。",
}


def _fill_ballast(src: Path) -> None:
    for name, text in _BALLAST.items():
        (src / name).write_text(text, encoding="utf-8")


def test_cache_rebuild_on_new_file(tmp_path):
    """witness 4a：首查建缓存后**新增**含独特词的文档 → 再查该词命中
    （若 manifest 失效判据被削，旧索引查不到新词，本 witness 必红）。
    """
    src = _make_scope(tmp_path)
    _fill_ballast(src)
    (src / "a.md").write_text("空气起动机由涡轮驱动。", encoding="utf-8")
    service = _make_service(tmp_path)
    assert len(service.search("apu_docs", "涡轮")) == 1  # 前置：首查命中并暖缓存

    (src / "b.md").write_text("防冰活门位于引气管路。", encoding="utf-8")
    hits = service.search("apu_docs", "防冰活门")

    assert len(hits) == 1
    assert hits[0].source == "b.md"


def test_cache_rebuild_on_modified_file(tmp_path):
    """witness 4b：首查建缓存后**改写**已有文档 → 旧词消失、新词命中
    （manifest 用内容指纹非 mtime：同名文件内容变即重建）。
    """
    src = _make_scope(tmp_path)
    _fill_ballast(src)
    (src / "a.md").write_text("空气起动机由涡轮驱动。", encoding="utf-8")
    service = _make_service(tmp_path)
    assert len(service.search("apu_docs", "空气起动机")) == 1  # 前置：旧词命中并暖缓存

    (src / "a.md").write_text("引气调节器由 ECB 控制。", encoding="utf-8")

    assert service.search("apu_docs", "空气起动机") == []  # 旧词随旧内容消失
    hits = service.search("apu_docs", "引气调节器")
    assert len(hits) == 1
    assert hits[0].source == "a.md"


# ------------------------------------------------------------- 入参门与截断


def test_search_blank_query_rejected(tmp_path):
    """witness 5a：query 全空白 → ValueError（scope 已注册且语料健康，一钥一门）。"""
    src = _make_scope(tmp_path)
    (src / "doc.md").write_text("空气起动机由涡轮驱动。", encoding="utf-8")
    service = _make_service(tmp_path)

    with pytest.raises(ValueError):
        service.search("apu_docs", "   ")


def test_search_top_k_capped_at_50(tmp_path):
    """witness 5b：55 篇全含查询词的语料，top_k=999 → 恰好 50 条且不抛错。

    每篇附唯一序号词使全词表 average_idf 为正，负 idf 地板后查询词得分仍 > 0
    （score>0 过滤不背锅，截断门是唯一被测对象）。
    """
    src = _make_scope(tmp_path)
    for i in range(55):
        (src / f"doc{i:02d}.md").write_text(f"涡轮 效率 序号{i:02d}", encoding="utf-8")
    service = _make_service(tmp_path)

    hits = service.search("apu_docs", "涡轮", top_k=999)

    assert len(hits) == 50
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)  # 截断保留的是分数最高的前 50


# ------------------------------------------- KnowledgeHit 出处四钥（T7 同款）


def _hit_kwargs(**overrides):
    kwargs = {
        "scope_id": "apu_docs",
        "chunk_id": "doc#0",
        "doc_id": "doc",
        "text": "空气起动机由涡轮驱动。",
        "source": "doc.md",
        "fingerprint": "abcdef012345",
        "score": 1.0,
    }
    kwargs.update(overrides)
    return kwargs


@pytest.mark.parametrize("field", ["scope_id", "chunk_id", "source", "fingerprint"])
def test_knowledge_hit_rejects_blank_provenance_field(field):
    """witness 7：出处四钥任一为空白串 → 构造期 ValueError（一钥一门：其余字段合法）。"""
    with pytest.raises(ValueError) as exc_info:
        KnowledgeHit(**_hit_kwargs(**{field: "  "}))
    assert field in str(exc_info.value)


def test_knowledge_hit_valid_construction_ok():
    """witness 7 边界：四钥齐备 → 正常构造（门不咬合法出处）。"""
    hit = KnowledgeHit(**_hit_kwargs())
    assert hit.fingerprint == "abcdef012345"


# --------------------------------------------------- 信任边界（T5 铺垫）


def test_direct_service_call_bypasses_authorization(tmp_path):
    """witness 8（边界，T5 铺垫）：restricted 密级 scope，不经任何 agent 白名单/
    密级门，直调 service 照样取到数——白名单只存在于 runtime._KnowledgeContext
    层，service 层无门是 docstring 宣称的信任边界（诚实记录，不假装有门）。
    """
    src = _make_scope(tmp_path, "secret_docs", confidentiality="restricted")
    _fill_ballast(src)  # 语料 ≥3 篇保证正 idf（见 _BALLAST 注释）
    (src / "secret.md").write_text("涉密件号台账段落。", encoding="utf-8")
    service = _make_service(tmp_path)

    hits = service.search("secret_docs", "涉密")

    assert len(hits) == 1
    assert hits[0].scope_id == "secret_docs"
    assert hits[0].source == "secret.md"


def test_search_rejects_nonpositive_top_k(tmp_path):
    """witness（反方审观察 c）：top_k<1 显式 ValueError——负值若放行会走负切片
    静默丢高分命中（丢数据的 fail-open）。仅参数门一钥，不触达 scope 解析。"""
    _make_scope(tmp_path)
    service = _make_service(tmp_path)
    with pytest.raises(ValueError, match="top_k"):
        service.search("apu_docs", "任意查询", top_k=0)
    with pytest.raises(ValueError, match="top_k"):
        service.search("apu_docs", "任意查询", top_k=-1)
