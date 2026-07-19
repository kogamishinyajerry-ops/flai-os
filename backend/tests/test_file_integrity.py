"""File Store 消费前完整性闸常驻回归。"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from backend.app.core.errors import FileIntegrityError
from backend.app.storage import file_integrity
from backend.app.storage.file_integrity import open_verified_file


def _write_stored(root: Path, data: bytes) -> Path:
    path = root / "file_1" / "payload.bin"
    path.parent.mkdir(parents=True)
    path.write_bytes(data)
    return path


def test_verified_handle_is_rewound_and_survives_path_replacement(tmp_path: Path) -> None:
    """校验后消费同一句柄：POSIX 路径换绑后仍读到已验 inode，而非新路径内容。"""
    root = tmp_path / "uploads"
    original = b"registered payload"
    path = _write_stored(root, original)
    handle = open_verified_file(
        path,
        allowed_root=root,
        expected_size=len(original),
        expected_sha256=hashlib.sha256(original).hexdigest(),
    )
    try:
        assert handle.tell() == 0
        if os.name != "nt":
            moved = path.with_suffix(".moved")
            path.rename(moved)
            path.write_bytes(b"replacement bytes")
        assert handle.read() == original
    finally:
        handle.close()


def test_same_size_tamper_fails_sha256_gate(tmp_path: Path) -> None:
    root = tmp_path / "uploads"
    original = b"trusted-A"
    tampered = b"forged--B"
    assert len(original) == len(tampered), "本测试必须锁定同尺寸替换威胁"
    path = _write_stored(root, original)
    path.write_bytes(tampered)

    with pytest.raises(FileIntegrityError, match="sha256"):
        open_verified_file(
            path,
            allowed_root=root,
            expected_size=len(original),
            expected_sha256=hashlib.sha256(original).hexdigest(),
        )


def test_dangling_symlink_is_integrity_failure_not_missing(tmp_path: Path) -> None:
    root = tmp_path / "uploads"
    root.mkdir()
    path = root / "file_1" / "payload.bin"
    path.parent.mkdir()
    try:
        path.symlink_to(root / "does-not-exist.bin")
    except (OSError, NotImplementedError):
        pytest.skip("当前平台/权限不支持创建符号链接")

    with pytest.raises(FileIntegrityError, match="符号链接"):
        open_verified_file(
            path,
            allowed_root=root,
            expected_size=1,
            expected_sha256=hashlib.sha256(b"x").hexdigest(),
        )


def test_path_outside_authoritative_root_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "uploads"
    root.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"x")

    with pytest.raises(FileIntegrityError, match="逃出"):
        open_verified_file(
            outside,
            allowed_root=root,
            expected_size=1,
            expected_sha256=hashlib.sha256(b"x").hexdigest(),
        )


@pytest.mark.skipif(
    getattr(os, "O_NONBLOCK", 0) == 0,
    reason="host does not expose a non-blocking open flag",
)
def test_posix_open_is_nonblocking_before_regular_file_fstat(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "uploads"
    payload = b"registered payload"
    path = _write_stored(root, payload)
    original_open = os.open
    observed_flags: list[int] = []

    def tracking_open(target: str | bytes | os.PathLike[str], flags: int, *args, **kwargs):
        observed_flags.append(flags)
        return original_open(target, flags, *args, **kwargs)

    monkeypatch.setattr(file_integrity.os, "open", tracking_open)

    handle = open_verified_file(
        path,
        allowed_root=root,
        expected_size=len(payload),
        expected_sha256=hashlib.sha256(payload).hexdigest(),
    )
    handle.close()

    assert observed_flags
    assert observed_flags[-1] & os.O_NONBLOCK
