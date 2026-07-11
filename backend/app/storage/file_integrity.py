"""File Store 消费前完整性闸：以同一只读句柄完成校验并交给调用方消费。"""

from __future__ import annotations

import errno
import hashlib
import hmac
import os
import stat
from pathlib import Path
from typing import BinaryIO

from ..core.errors import FileIntegrityError

_CHUNK_SIZE = 1024 * 1024


def _resolved_inside_root(path: Path, allowed_root: Path) -> None:
    """要求磁盘对象真实路径位于权威根内；根绝不从待验证 record.path 反推。"""
    try:
        root = allowed_root.resolve(strict=True)
    except OSError as exc:
        raise FileIntegrityError(f"文件存储根目录不可用：{allowed_root}") from exc

    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise FileIntegrityError(f"文件路径无法安全解析：{path}") from exc

    if resolved != root and root not in resolved.parents:
        raise FileIntegrityError(f"文件路径逃出允许的存储根目录：{path}")


def _validate_expected_metadata(expected_size: int, expected_sha256: str) -> tuple[int, str]:
    if isinstance(expected_size, bool) or not isinstance(expected_size, int) or expected_size < 0:
        raise FileIntegrityError("登记的文件大小非法")
    digest = str(expected_sha256 or "").lower()
    if len(digest) != 64:
        raise FileIntegrityError("登记的 sha256 指纹非法")
    try:
        bytes.fromhex(digest)
    except ValueError as exc:
        raise FileIntegrityError("登记的 sha256 指纹非法") from exc
    return expected_size, digest


def open_verified_file(
    path: str | Path,
    *,
    allowed_root: str | Path,
    expected_size: int,
    expected_sha256: str,
) -> BinaryIO:
    """打开并校验 File Store 对象，成功时把同一句柄 seek(0) 后交给消费方。

    POSIX 使用 ``O_NOFOLLOW`` 原子拒绝最终路径分量为符号链接。Windows 没有
    等价 flag，只能在 ``open`` 前用 ``lstat`` 拒绝链接；这仍存在极窄的检查/打开
    竞态，是平台能力差异，不能宣称与 POSIX 同等原子性。
    """
    file_path = Path(path)
    root_path = Path(allowed_root)
    expected_size, expected_digest = _validate_expected_metadata(
        expected_size, expected_sha256
    )

    # 所有平台先 lstat，确保 dangling symlink 也按完整性问题（而非“普通缺失”）
    # 分类。POSIX 真正抵御 lstat→open 竞态的仍是下方 O_NOFOLLOW；Windows 缺少
    # 对等原子 flag，只能依赖这次前置检查，差异如实保留在函数注释中。
    try:
        if stat.S_ISLNK(file_path.lstat().st_mode):
            raise FileIntegrityError(f"拒绝符号链接文件：{file_path}")
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise FileIntegrityError(f"文件路径无法安全检查：{file_path}") from exc

    _resolved_inside_root(file_path, root_path)

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    flags = os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(file_path, flags)
    except FileNotFoundError:
        raise
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise FileIntegrityError(f"拒绝符号链接文件：{file_path}") from exc
        raise FileIntegrityError(f"文件无法安全打开：{file_path}") from exc

    try:
        handle = os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise
    try:
        actual = os.fstat(handle.fileno())
        if not stat.S_ISREG(actual.st_mode):
            raise FileIntegrityError(f"磁盘对象不是普通文件：{file_path}")
        if actual.st_size != expected_size:
            raise FileIntegrityError(
                f"文件大小不匹配：登记={expected_size}，磁盘={actual.st_size}"
            )

        digest = hashlib.sha256()
        for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
        actual_digest = digest.hexdigest()
        if not hmac.compare_digest(actual_digest, expected_digest):
            raise FileIntegrityError(
                f"文件 sha256 不匹配：登记={expected_digest}，磁盘={actual_digest}"
            )

        handle.seek(0)
        return handle
    except BaseException:
        handle.close()
        raise
