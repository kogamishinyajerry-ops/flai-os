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

密级判定=启动快照 ∩ 盘上现值（Codex 治理审 R0 P1-2 → R1 P1 双门 → R2 P1 诚实收窄）：
- confidentiality 快照取自 scope_registry（bootstrap 一次装配、不重扫），语料按
  指纹自刷新；单凭快照会在「运行中收紧密级但不重启」时读旧宽松值却回源新内容。
- 故本门**回源时额外从盘上现读** confidentiality（_read_disk_confidentiality，
  读/解析失败一律返回 None＝不可验证＝拒），与快照取交集：任一受限/未知/漂移即拒。
- **闭合范围（诚实标注）**：此双门闭合的是**运营漂移窗口**（改配置未重启、随后
  请求），这是现实运维场景。它**不是原子的**——盘读与语料读之间仍有理论 TOCTOU
  （精确计时的并发 config-flip 可穿窗）。返回的 confidentiality 标签用盘上现值
  （比旧快照准）。真正原子闭合（密级策略 generation × 语料快照同锁/同代际绑定）
  是知识轴平台级工作，排 V0.2（ADR-0029 §D6）；平台级 _KnowledgeContext.search
  的同源快照属性本次不改。不声称「消除所有 TOCTOU」，只声称「闭合运营漂移」。
"""

from __future__ import annotations

from dataclasses import dataclass

import yaml

from ..core.errors import KnowledgeScopeNotRegisteredError
from .scopes import ScopeRegistry
from .service import KnowledgeService

_ALLOWED_CONFIDENTIALITY = ("public_internal", "department")
# scope.yaml 现读的字节上限（漂移检查用）：正常仅几百字节，64KiB 足够且杜绝
# 超大配置读放大（Codex 治理审 R2 P2）。
_SCOPE_YAML_MAX_BYTES = 64 * 1024


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
        # 密级门取「启动快照 ∩ 盘上现值」的交集（Codex 治理审 R1 P1 → R2 P1 诚实收窄）：
        # scope_registry 是启动期快照、不重扫，而 KnowledgeService 语料按指纹自刷新——
        # 仅凭快照会在「运行中把 scope.yaml 由 public 改成 restricted 且不重启」时读旧
        # 宽松值、却回源已刷新的新内容。这里回源时**额外从盘上重读**当前密级，快照
        # 与盘上任一为受限/不可验证即拒。
        # 【诚实边界，R2 P1】此双门**闭合的是运营漂移窗口**（改了配置未重启，随后请求）——
        # 这是现实运维场景。它**不是原子的**：盘读（此处）与语料读（下方 get_chunks_by_id）
        # 之间仍有理论 TOCTOU（精确计时的并发 config-flip 可穿窗）。真正原子闭合=把密级
        # 策略 generation 与语料快照在同一锁/不可变代际下绑定，是知识轴平台级工作，排
        # V0.2（ADR-0029 §D6）。不声称「已消除所有 TOCTOU」，只声称「闭合运营漂移」。
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
            # 返回**盘上现值**而非启动快照标签（Codex 治理审 R2 P1）：门已保证盘上
            # 密级 ∈ 允许集，用它比旧快照更准（snapshot=public 盘上=department 的
            # 允许集内漂移下，标签如实反映当前密级）。
            confidentiality=disk_conf,
        )

    def _read_disk_confidentiality(self, scope_id: str) -> str | None:
        """从盘上 scope.yaml 现读 confidentiality（漂移检查用）。

        fail-closed：目录缺失/读失败/解析失败/资源异常/顶层非 dict/无该键 一律返回
        None（不可验证 = 视为不放行），绝不因读盘异常放宽密级判定。

        资源自保（Codex 治理审 R2 P2）：先按字节上限截读（scope.yaml 正常仅几百字节，
        64KiB 足够），杜绝超大配置文件的读放大；解析异常收容面含 ValueError（超长
        整数）/RecursionError（深层 flow YAML）等 PyYAML 资源型异常，一律 → None，
        绝不穿透成 500。"""
        scope_dir = self._scope_registry.scope_dir(scope_id)
        if scope_dir is None:
            return None
        yaml_path = scope_dir / "scope.yaml"
        try:
            with open(yaml_path, "rb") as fh:
                raw = fh.read(_SCOPE_YAML_MAX_BYTES + 1)
            if len(raw) > _SCOPE_YAML_MAX_BYTES:
                return None  # 异常巨大的 scope.yaml：拒绝解析（fail-closed）
            data = yaml.safe_load(raw.decode("utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError, ValueError, RecursionError):
            return None
        if not isinstance(data, dict):
            return None
        value = data.get("confidentiality")
        return value if isinstance(value, str) else None
