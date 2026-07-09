"""多格式文档 → Chunk 语料（Knowledge 内核摄取层，ADR-0015）。

上游出处：COMAC_FDE core/ingest.py（收编复制适配，不 import 该仓）。与上游的刻意差异：
- csv 用 encoding="utf-8-sig"（真实语料常带 BOM，utf-8 会把 ﻿ 混进首列名）；
- docx 惰性 import，缺 python-docx 时抛 KnowledgeIngestError（可选依赖，诚实报错）；
- 全部失败路径统一 KnowledgeIngestError（fail-closed：未知后缀/PDF 一律 raise，
  绝不静默跳过——静默缺片会被误读为"语料里没有"）；
- ingest_dir 递归 rglob（上游为单层 iterdir），source=相对源目录的 POSIX 相对路径。

已知限制：doc_id 取文件 stem，同 stem 不同路径的文件允许共存，此时 chunk_id
（f"{doc_id}#{i}"）会跨文件碰撞不唯一；唯一定位以 source+fingerprint 为准。
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path

from ..core.errors import KnowledgeIngestError

MAX_CHARS = 800


@dataclass(frozen=True)
class Chunk:
    """单个检索单元。source+fingerprint 是出处双钥，构造期即固化（frozen）。

    __post_init__ 强制出处双钥非空：frozen 只防已构造实例被改，非空校验把
    docs/06 §4「无出处禁止进入上下文」从调用链约定升级为类型层强制
    （loop-auditor Mode A Finding 3）。注意边界：这仍不能阻止拿着真格式
    假内容来构造——防的是漏填/空串，不是恶意伪造。
    """

    doc_id: str  # 源文件 stem
    chunk_id: str  # f"{doc_id}#{i}"，i 从 0 起（同 stem 文件间可碰撞，见模块 docstring）
    text: str
    source: str  # 相对 scope 源目录的 POSIX 相对路径（如 "manuals/em.md"）
    fingerprint: str  # sha256(文件字节)[:12]

    def __post_init__(self) -> None:
        if not (isinstance(self.source, str) and self.source.strip()):
            raise ValueError("Chunk.source 出处不得为空（docs/06 §4）")
        if not (isinstance(self.fingerprint, str) and self.fingerprint.strip()):
            raise ValueError("Chunk.fingerprint 出处指纹不得为空（docs/06 §4）")


def _fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def _merge(paras: list[str], doc_id: str, source: str, fp: str) -> list[Chunk]:
    """段落贪心合并：strip 后非空段依序拼接至 ≤MAX_CHARS，超限另起新 chunk。"""
    merged: list[str] = []
    buf = ""
    for p in paras:
        p = p.strip()
        if not p:
            continue
        if buf and len(buf) + len(p) + 1 > MAX_CHARS:
            merged.append(buf)
            buf = p
        else:
            buf = f"{buf}\n{p}" if buf else p
    if buf:
        merged.append(buf)
    return [Chunk(doc_id, f"{doc_id}#{i}", t, source, fp) for i, t in enumerate(merged)]


def ingest_path(path: Path, *, source: str) -> list[Chunk]:
    """单文件 → list[Chunk]。source 由调用方显式传入（服务层给相对路径作出处）。

    空内容文件（全空白 txt、无行 xlsx）返回 []——空文件≠坏文件，空语料由
    service 层统一拒绝；格式不支持/可选依赖缺失则抛 KnowledgeIngestError。
    """
    path = Path(path)
    suffix = path.suffix.lower()
    doc_id, fp = path.stem, _fingerprint(path)
    if suffix in {".txt", ".md"}:
        paras = path.read_text(encoding="utf-8").split("\n\n")
    elif suffix == ".csv":
        # utf-8-sig：带 BOM 时剥掉 ﻿，无 BOM 时与 utf-8 等价（FDE retro 教训）。
        with path.open(encoding="utf-8-sig") as f:
            paras = ["; ".join(f"{k}={v}" for k, v in row.items()) for row in csv.DictReader(f)]
    elif suffix == ".xlsx":
        from openpyxl import load_workbook

        ws = load_workbook(path, read_only=True).active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        header = [str(c) for c in rows[0]]
        paras = ["; ".join(f"{h}={c}" for h, c in zip(header, r)) for r in rows[1:]]
    elif suffix == ".docx":
        try:
            import docx
        except ImportError as exc:
            raise KnowledgeIngestError(
                "python-docx 未安装，docx 解析不可用（可选依赖，离线环境见 README）"
            ) from exc
        paras = [p.text for p in docx.Document(str(path)).paragraphs]
    elif suffix == ".pdf":
        raise KnowledgeIngestError("PDF 解析未接入（待内网侦察，诚实拒绝不静默跳过）")
    else:
        raise KnowledgeIngestError(
            f"不支持的格式: {suffix}（scope 源目录必须只含受支持格式，fail-closed 不静默跳过）"
        )
    return _merge(paras, doc_id, source, fp)


def ingest_dir(dir_path: Path) -> list[Chunk]:
    """目录（递归）→ list[Chunk]。

    - rglob 全量遍历，跳过任一路径分量以点开头的文件/目录（.hidden、.git/ 等）；
    - 按相对 POSIX 路径字符串排序，保证跨平台稳定顺序（索引缓存 manifest 依赖此序）；
    - source = 相对 dir_path 的 POSIX 路径（Windows 反斜杠不进出处字段）。
    """
    dir_path = Path(dir_path)
    rel_paths: list[Path] = []
    for p in dir_path.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(dir_path)
        if any(part.startswith(".") for part in rel.parts):
            continue
        rel_paths.append(rel)
    chunks: list[Chunk] = []
    for rel in sorted(rel_paths, key=lambda r: r.as_posix()):
        chunks.extend(ingest_path(dir_path / rel, source=rel.as_posix()))
    return chunks
