"""完整 Agent Package 不可变快照的文件系统安全边界。"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.runtime import package_snapshot as snapshot_mod
from backend.app.runtime.package_snapshot import (
    PackageSnapshotError,
    capture_agent_package,
)


def _package(tmp_path: Path) -> Path:
    package_dir = tmp_path / "agent"
    package_dir.mkdir()
    (package_dir / "agent.yaml").write_text(
        "id: snapshot_probe\nversion: 1.0.0\n",
        encoding="utf-8",
    )
    (package_dir / "workflow.py").write_text(
        "def run(context):\n    return {'status': 'success', 'outputs': []}\n",
        encoding="utf-8",
    )
    return package_dir


def test_capture_materializes_complete_nested_tree_and_cleans_up(
    tmp_path: Path,
) -> None:
    package_dir = _package(tmp_path)
    nested = package_dir / "data" / "fixtures"
    nested.mkdir(parents=True)
    payload = b"\x00full-package-bytes\xff"
    (nested / "case.bin").write_bytes(payload)
    (package_dir / "empty-dir").mkdir()
    generated = package_dir / "__pycache__"
    generated.mkdir()
    (generated / "workflow.cpython-313.pyc").write_bytes(b"generated")

    snapshot = capture_agent_package(package_dir)

    assert snapshot.manifest["id"] == "snapshot_probe"
    assert "data/fixtures/case.bin" in dict(snapshot.files)
    assert "empty-dir" in snapshot.directories
    assert all("__pycache__" not in path for path, _payload in snapshot.files)
    with snapshot.materialized() as frozen_dir:
        materialized_path = frozen_dir
        assert (frozen_dir / "data" / "fixtures" / "case.bin").read_bytes() == payload
        assert (frozen_dir / "empty-dir").is_dir()
        assert (frozen_dir / "__pycache__").exists() is False
    assert materialized_path.exists() is False


def test_capture_rejects_symlink_anywhere(tmp_path: Path) -> None:
    package_dir = _package(tmp_path)
    target = package_dir / "data.txt"
    target.write_text("payload", encoding="utf-8")
    link = package_dir / "data-link.txt"
    try:
        link.symlink_to(target.name)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"当前平台不能创建 symlink：{exc}")

    with pytest.raises(PackageSnapshotError, match="symlink"):
        capture_agent_package(package_dir)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="平台不支持 FIFO")
def test_capture_rejects_non_regular_entry(tmp_path: Path) -> None:
    package_dir = _package(tmp_path)
    fifo = package_dir / "runtime.pipe"
    os.mkfifo(fifo)

    with pytest.raises(PackageSnapshotError, match="non-regular"):
        capture_agent_package(package_dir)


def test_capture_rejects_change_between_two_full_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_dir = _package(tmp_path)
    workflow_path = package_dir / "workflow.py"
    real_capture_once = snapshot_mod._capture_once
    calls = 0

    def _capture_then_mutate(source: Path):
        nonlocal calls
        captured = real_capture_once(source)
        calls += 1
        if calls == 1:
            workflow_path.write_text(
                "def run(context):\n"
                "    return {'status': 'success', 'outputs': ['changed']}\n",
                encoding="utf-8",
            )
        return captured

    monkeypatch.setattr(snapshot_mod, "_capture_once", _capture_then_mutate)

    with pytest.raises(PackageSnapshotError, match="changed during snapshot capture"):
        capture_agent_package(package_dir)
    assert calls == 2


def test_capture_rejects_case_insensitive_path_collision(tmp_path: Path) -> None:
    package_dir = _package(tmp_path)
    (package_dir / "Data.txt").write_text("A", encoding="utf-8")
    (package_dir / "data.txt").write_text("B", encoding="utf-8")
    colliding_names = [
        path.name
        for path in package_dir.iterdir()
        if path.name.casefold() == "data.txt"
    ]
    if len(colliding_names) < 2:
        pytest.skip("当前测试文件系统大小写不敏感，无法构造碰撞")

    with pytest.raises(PackageSnapshotError, match="case-insensitive path collision"):
        capture_agent_package(package_dir)


def test_capture_rejects_package_over_single_file_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_dir = _package(tmp_path)
    (package_dir / "oversized.bin").write_bytes(b"1234")
    monkeypatch.setattr(
        snapshot_mod,
        "_MAX_SINGLE_FILE_BYTES",
        3,
        raising=False,
    )

    with pytest.raises(PackageSnapshotError, match="single-file byte budget"):
        capture_agent_package(package_dir)


def test_capture_rejects_package_over_total_byte_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_dir = _package(tmp_path)
    monkeypatch.setattr(
        snapshot_mod,
        "_MAX_TOTAL_BYTES",
        8,
        raising=False,
    )

    with pytest.raises(PackageSnapshotError, match="total byte budget"):
        capture_agent_package(package_dir)


def test_capture_rejects_package_over_entry_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_dir = _package(tmp_path)
    (package_dir / "third.txt").write_text("third", encoding="utf-8")
    monkeypatch.setattr(
        snapshot_mod,
        "_MAX_ENTRIES",
        2,
        raising=False,
    )

    with pytest.raises(PackageSnapshotError, match="entry budget"):
        capture_agent_package(package_dir)


def test_capture_rejects_package_over_depth_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_dir = _package(tmp_path)
    nested = package_dir / "level-one"
    nested.mkdir()
    (nested / "level-two.txt").write_text("deep", encoding="utf-8")
    monkeypatch.setattr(
        snapshot_mod,
        "_MAX_PATH_DEPTH",
        1,
        raising=False,
    )

    with pytest.raises(PackageSnapshotError, match="path depth budget"):
        capture_agent_package(package_dir)


def test_reparse_attribute_is_recognized_on_every_platform() -> None:
    fake_stat = SimpleNamespace(
        st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT
    )
    assert snapshot_mod._is_reparse_point(fake_stat) is True


@pytest.mark.skipif(os.name != "nt", reason="Windows junction witness")
def test_capture_rejects_windows_junction(tmp_path: Path) -> None:
    package_dir = _package(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "payload.txt").write_text("outside", encoding="utf-8")
    junction = package_dir / "junction"
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        check=True,
        capture_output=True,
        text=True,
    )

    with pytest.raises(PackageSnapshotError, match="reparse"):
        capture_agent_package(package_dir)
