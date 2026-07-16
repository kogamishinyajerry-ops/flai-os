"""知识引用回源读取器（评审 N7 / ADR-0029）：带密级门的只读原文通道。

KnowledgeService 的信任边界（service.py docstring）规定：服务层零授权判定，
除 Runtime 装配外不得直接持有服务实例。本模块是**经 ADR-0029 评审新增的第二
个合法持有者**——自带密级门的只读回源读取器，供 `GET /api/knowledge/chunk`
（签发人核对 knowledge_qa 草案引用出处）使用。除本读取器与 Runtime 装配外，
直接持有 KnowledgeService 的旧禁令不变。

密级门（fail-closed，全部显式比较，兜底拒绝）：
- scope 未注册 → KnowledgeScopeNotRegisteredError（对外 404，default-deny）；
- confidentiality == "restricted" → ProvenanceAccessDeniedError（对外 403）
  ——V0.1 无角色轴，登录态区分不了 admin，宁拒不泄；角色轴落地后另议放行；
- 枚举外/缺失密级 → 同样拒（无法验证 = 拒绝，同 scopes._confidentiality_denial
  的兜底哲学）；
- public_internal / department → 放行给登录用户（M11 全站登录已强制）。
  诚实边界：department 粒度的「本部门人员」判定在 V0.1 无部门轴，放行口径=
  「任何登录用户」——与现状一致（knowledge_qa 草案产物本就对登录用户可见，
  草案里已含语料摘录），记录于 ADR-0029，不静默。

诚实边界·密级快照（Codex 治理审 R0 P1-2，ADR-0029 §D3 补记）：
- confidentiality 取自 **scope_registry 的启动期快照**（bootstrap.assemble 一次
  装配，不随运行重扫——见 bootstrap.py「结构性漂移温床」注）；而 KnowledgeService
  语料按内容指纹**自动刷新**。二者刷新生命周期不同 → 若运行中把 scope.yaml
  的 confidentiality 由 public_internal 改成 restricted **且不重启**，本门读到的是
  旧（宽松）快照、语料却已刷新为新内容，构成潜在越密级泄漏。
- 这是**平台级既有属性**，非本回源通道独有：runtime._KnowledgeContext.search 的
  白名单/密级判定同样源自该启动快照。V0.1 的运维口径=「scope 配置（含密级）在
  启动期固定，收紧密级必须重启服务才生效」，与白名单同源同纪律。
- 彻底修法（把密级策略摘要与语料 generation 原子绑定、漂移即 fail-closed）是
  **知识轴平台级加固**，排 V0.2（ADR-0029 决策点记录）；本通道 V0.1 忠实沿用
  平台唯一密级真源，不另立一套分叉判定。
"""

from __future__ import annotations

from dataclasses import dataclass

import yaml

from ..core.errors import KnowledgeScopeNotRegisteredError
from .scopes import ScopeRegistry
from .service import KnowledgeService

_ALLOWED_CONFIDENTIALITY = ("public_internal", "department")


class ProvenanceAccessDeniedError(Exception):
    """密级门拒绝回源（restricted / 未知密级）。"""


class ProvenanceAmbiguousError(Exception):
    """同 chunk_id 命中多个源文件且未带 source 消歧——拒绝猜，如实报歧义。"""

    def __init__(self, sources: list[str]) -> None:
        self.sources = sources
        super().__init__(f"chunk_id 命中 {len(sources)} 个源文件：{sources}")


@dataclass(frozen=True)
class ChunkProvenance:
    scope_id: str
    chunk_id: str
    doc_id: str
    source: str
    fingerprint: str
    text: str
    confidentiality: str


class ChunkProvenanceReader:
    """组合 ScopeRegistry（密级真值）与 KnowledgeService（语料读取）。"""

    def __init__(self, scope_registry: ScopeRegistry, knowledge_service: KnowledgeService) -> None:
        self._scope_registry = scope_registry
        self._knowledge_service = knowledge_service

    def read(self, scope_id: str, chunk_id: str, source: str | None = None) -> ChunkProvenance | None:
        scope = self._scope_registry.get(scope_id)
        if scope is None:
            raise KnowledgeScopeNotRegisteredError(
                f"knowledge scope {scope_id!r} 未在 Scope Registry 注册"
                "（default-deny：未注册即不存在）"
            )
        conf = scope.get("confidentiality")
        # 密级门取「启动快照 ∩ 盘上现值」的交集（Codex 治理审 R1 P1，fail-closed）：
        # scope_registry 是启动期快照、不重扫，而 KnowledgeService 语料按指纹自刷新——
        # 若运行中把 scope.yaml 由 public 改成 restricted 且不重启，仅凭快照会读旧
        # 宽松值、却回源已刷新的新内容=越级泄漏。这里回源时**额外从盘上重读**当前
        # 密级，快照与盘上任一为受限/不可验证即拒。「重启才生效」的运维约定不是
        # 安全 gate；本回源通道（新暴露面、调用面最广）用盘上漂移检查真正闭合，
        # 不依赖运维纪律。平台级 search 的同源属性仍排 V0.2（ADR-0029 §D6）。
        disk_conf = self._read_disk_confidentiality(scope_id)
        allowed_snapshot = conf == "public_internal" or conf == "department"
        allowed_disk = disk_conf == "public_internal" or disk_conf == "department"
        if allowed_snapshot is not True or allowed_disk is not True:
            raise ProvenanceAccessDeniedError(
                f"scope {scope_id!r} 密级不放行（快照={conf!r} 盘上={disk_conf!r}）："
                "原文回源在角色轴落地前对 restricted/未知/漂移一律拒绝（fail-closed）"
            )
        # 密级门通过才触碰语料（门先于读，与单元测试哨兵同款纪律）。
        matches = self._knowledge_service.get_chunks_by_id(scope_id, chunk_id)
        if source is not None:
            matches = [c for c in matches if c.source == source]
        if len(matches) == 0:
            return None
        if len(matches) > 1:
            raise ProvenanceAmbiguousError(sorted({c.source for c in matches}))
        c = matches[0]
        return ChunkProvenance(
            scope_id=scope_id,
            chunk_id=c.chunk_id,
            doc_id=c.doc_id,
            source=c.source,
            fingerprint=c.fingerprint,
            text=c.text,
            confidentiality=conf,
        )

    def _read_disk_confidentiality(self, scope_id: str) -> str | None:
        """从盘上 scope.yaml 现读 confidentiality（漂移检查用）。

        fail-closed：目录缺失/读失败/解析失败/顶层非 dict/无该键 一律返回 None
        （不可验证 = 视为不放行），绝不因读盘异常放宽密级判定。
        """
        scope_dir = self._scope_registry.scope_dir(scope_id)
        if scope_dir is None:
            return None
        yaml_path = scope_dir / "scope.yaml"
        try:
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError):
            return None
        if not isinstance(data, dict):
            return None
        value = data.get("confidentiality")
        return value if isinstance(value, str) else None
