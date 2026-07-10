"""chunking 摄取层测试（Wave 1 SPEC §2 witness 清单，一钥一门）。

覆盖：
1. txt 三段落贪心合并 ≤800（首段独立成 chunk，第 2+3 段合并）；
2. csv 带 UTF-8 BOM → 首列名不含 BOM（utf-8-sig 专属钥匙）；
3. xlsx header+2 数据行 → 2 chunk 文本含 h=c；
4. docx 缺 python-docx → KnowledgeIngestError（sys.modules patch，
   本机装没装 python-docx 都强制走 ImportError 分支）；
5. pdf → KnowledgeIngestError（诚实拒绝不静默跳过）；
6. 未知后缀 .png → KnowledgeIngestError（fail-closed 钥匙）；
7. ingest_dir 递归 + 跳过点前缀文件/目录 + 按相对 POSIX 路径排序稳定；
8. fingerprint 内容寻址：同内容相同、改一字节即变；
9. 边界 witness：全空白 txt → []（空文件≠坏文件，空语料由 service 层拒绝）。

codex Wave1-R1 增补（一钥一门）：
11. symlink 越界 → 硬拒整次摄取；域内 symlink 不误伤；
12. 指纹与正文绑定同一字节快照（出处双钥不脱钩）；
13. 超长单段先硬切再合并，chunk 上界 800 不被击穿且正文无损。
"""

from __future__ import annotations

import sys

import pytest

from backend.app.core.errors import KnowledgeIngestError
from backend.app.knowledge.chunking import MAX_CHARS, ingest_dir, ingest_path


def test_txt_paragraph_merge(tmp_path):
    """witness 1：首段 790 字符独占 chunk，第 2+3 段（100+100）贪心合并。"""
    p1, p2, p3 = "a" * 790, "b" * 100, "c" * 100
    f = tmp_path / "doc.txt"
    f.write_text(f"{p1}\n\n{p2}\n\n{p3}", encoding="utf-8")
    chunks = ingest_path(f, source="doc.txt")
    assert len(chunks) == 2
    assert chunks[0].text == p1
    assert chunks[1].text == f"{p2}\n{p3}"
    assert [c.chunk_id for c in chunks] == ["doc#0", "doc#1"]
    assert all(c.doc_id == "doc" and c.source == "doc.txt" for c in chunks)
    assert all(len(c.text) <= MAX_CHARS for c in chunks)


def test_csv_utf8_bom_not_in_header(tmp_path):
    """witness 2：写入 BOM 前缀字节，首列名必须干净（utf-8-sig 钥匙）。"""
    f = tmp_path / "rows.csv"
    f.write_bytes("﻿部件,故障\nAPU,排液孔堵塞\n".encode("utf-8"))
    chunks = ingest_path(f, source="rows.csv")
    assert len(chunks) == 1
    assert "部件=APU" in chunks[0].text
    assert "故障=排液孔堵塞" in chunks[0].text
    assert "﻿" not in chunks[0].text


def test_xlsx_header_plus_two_rows(tmp_path):
    """witness 3：header+2 数据行 → 2 chunk（行长 502 使其不被贪心合并）。"""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["h"])
    ws.append(["c" * 500])
    ws.append(["c" * 500])
    f = tmp_path / "table.xlsx"
    wb.save(f)
    chunks = ingest_path(f, source="table.xlsx")
    assert len(chunks) == 2
    assert all("h=c" in c.text for c in chunks)


def test_docx_missing_dependency_raises(tmp_path, monkeypatch):
    """witness 4：sys.modules["docx"]=None 强制 import 抛 ImportError——
    本机装没装 python-docx 该分支都必须可测且报错含依赖名。"""
    f = tmp_path / "note.docx"
    f.write_bytes(b"placeholder")  # import 检查先于解析，文件内容无关紧要
    monkeypatch.setitem(sys.modules, "docx", None)
    with pytest.raises(KnowledgeIngestError, match="python-docx"):
        ingest_path(f, source="note.docx")


def test_pdf_rejected(tmp_path):
    """witness 5：PDF 未接入 → 显式拒绝。"""
    f = tmp_path / "manual.pdf"
    f.write_bytes(b"%PDF-1.4")
    with pytest.raises(KnowledgeIngestError, match="PDF"):
        ingest_path(f, source="manual.pdf")


def test_unknown_suffix_rejected(tmp_path):
    """witness 6：未知后缀 fail-closed raise，不静默跳过。"""
    f = tmp_path / "diagram.png"
    f.write_bytes(b"\x89PNG")
    with pytest.raises(KnowledgeIngestError, match="不支持的格式"):
        ingest_path(f, source="diagram.png")


def test_ingest_dir_recursive_skip_dotted_sorted(tmp_path):
    """witness 7：递归收 sub/、跳过 .hidden 与 .git/ 内文件、按相对 POSIX 路径排序。"""
    (tmp_path / "b.txt").write_text("bravo 内容", encoding="utf-8")
    (tmp_path / "a.txt").write_text("alpha 内容", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.md").write_text("charlie 内容", encoding="utf-8")
    (tmp_path / ".hidden.txt").write_text("点前缀文件", encoding="utf-8")
    git = tmp_path / ".git"
    git.mkdir()
    (git / "config.txt").write_text("点前缀目录内文件", encoding="utf-8")
    chunks = ingest_dir(tmp_path)
    assert [c.source for c in chunks] == ["a.txt", "b.txt", "sub/c.md"]
    assert all("点前缀" not in c.text for c in chunks)


def test_fingerprint_content_addressed(tmp_path):
    """witness 8：fingerprint 只随文件字节变——同内容相同，改一字节即变。"""
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("同一份内容", encoding="utf-8")
    b.write_text("同一份内容", encoding="utf-8")
    fp_a = ingest_path(a, source="a.txt")[0].fingerprint
    fp_b = ingest_path(b, source="b.txt")[0].fingerprint
    assert fp_a == fp_b
    assert len(fp_a) == 12
    b.write_bytes("同一份内容".encode("utf-8") + b"!")
    assert ingest_path(b, source="b.txt")[0].fingerprint != fp_a


def test_blank_txt_returns_empty(tmp_path):
    """witness 9（边界）：全空白 txt → []，不抛错（空文件≠坏文件）。"""
    f = tmp_path / "blank.txt"
    f.write_text("\n\n   \n\n\t\n", encoding="utf-8")
    assert ingest_path(f, source="blank.txt") == []


def test_symlink_escape_rejected_inside_allowed(tmp_path):
    """witness 11（codex Wave1-R1 P1）：源目录内 symlink 指向目录外文件 →
    KnowledgeIngestError 硬拒整次摄取（fail-closed 不静默跳过——静默跳过会把
    越界文件伪装成"语料里没有"）；指向目录内的 symlink 不受影响（收容不误伤）。"""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("仓外敏感内容", encoding="utf-8")
    scope = tmp_path / "scope"
    scope.mkdir()
    (scope / "legit.md").write_text("合法语料段落", encoding="utf-8")
    (scope / "leak.md").symlink_to(outside / "secret.md")

    with pytest.raises(KnowledgeIngestError, match="逃逸出源目录"):
        ingest_dir(scope)

    # 收容不误伤：撤掉越界链接、放一个域内 symlink → 摄取正常且不含仓外内容
    (scope / "leak.md").unlink()
    (scope / "alias.md").symlink_to(scope / "legit.md")
    chunks = ingest_dir(scope)
    assert {c.source for c in chunks} == {"legit.md", "alias.md"}
    assert all("仓外敏感内容" not in c.text for c in chunks)


def test_fingerprint_bound_to_parsed_snapshot(tmp_path, monkeypatch):
    """witness 12（codex Wave1-R1 P2）：指纹与正文出自同一字节快照——把
    read_bytes 钉成固定快照后，正文与指纹都必须来自该快照。旧实现指纹读一次、
    解析再开一次文件，间隙内源文件被替换会产生「正文 A + 指纹 B」的出处脱钩
    （引用指向的不再是产生该正文的那份文件）。"""
    import hashlib
    from pathlib import Path

    f = tmp_path / "live.md"
    f.write_text("磁盘上的另一份内容", encoding="utf-8")
    snapshot = "快照那一刻的正文".encode("utf-8")
    monkeypatch.setattr(Path, "read_bytes", lambda self: snapshot)

    chunks = ingest_path(f, source="live.md")
    assert len(chunks) == 1
    assert chunks[0].text == "快照那一刻的正文", "正文必须来自指纹所指的那份字节"
    assert chunks[0].fingerprint == hashlib.sha256(snapshot).hexdigest()[:12]


def test_oversized_single_paragraph_split(tmp_path):
    """witness 13（codex Wave1-R1 P2）：无空行超长单段（2500 字符）→ 先按
    MAX_CHARS 硬切再合并——所有 chunk ≤800 且正文无损可拼回。超长 CSV/xlsx
    行与本例同走 _merge 共享路径。"""
    body = "甲" * 2500
    f = tmp_path / "long.md"
    f.write_text(body, encoding="utf-8")
    chunks = ingest_path(f, source="long.md")
    assert len(chunks) == 4  # 800×3 + 100
    assert all(len(c.text) <= MAX_CHARS for c in chunks)
    assert "".join(c.text for c in chunks) == body, "硬切只分块不丢字"


def test_chunk_empty_provenance_rejected():
    """witness 10（Finding 3）：出处双钥空串在构造期即拒——source 与 fingerprint
    各自独立成钥（一次只违反一条）。"""
    from backend.app.knowledge.chunking import Chunk

    with pytest.raises(ValueError, match="source"):
        Chunk("d", "d#0", "文本", "", "abc123def456")
    with pytest.raises(ValueError, match="fingerprint"):
        Chunk("d", "d#0", "文本", "manuals/em.md", "  ")
