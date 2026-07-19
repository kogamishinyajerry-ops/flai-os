"""File Store 消费前完整性闸：以同一只读句柄完成校验并交给调用方消费。"""

from __future__ import annotations

import errno
import hashlib
import hmac
import os
import stat
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from ..core.errors import FileIntegrityError

_CHUNK_SIZE = 1024 * 1024


def _is_link_or_reparse_point(path: Path) -> bool:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode):
        return True
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


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


def _verify_open_descriptor(
    fd: int,
    *,
    display_path: Path,
    expected_size: int,
    expected_digest: str,
) -> BinaryIO:
    try:
        handle = os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise
    try:
        actual = os.fstat(handle.fileno())
        if not stat.S_ISREG(actual.st_mode):
            raise FileIntegrityError(f"磁盘对象不是普通文件：{display_path}")
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


def open_verified_file(
    path: str | Path,
    *,
    allowed_root: str | Path,
    expected_size: int,
    expected_sha256: str,
) -> BinaryIO:
    """打开并校验 File Store 对象，成功时把同一句柄 seek(0) 后交给消费方。

    POSIX 使用 ``O_NOFOLLOW`` 原子拒绝最终路径分量为符号链接，并用
    ``O_NONBLOCK`` 避免检查后换绑为 FIFO 时在 ``fstat`` 前阻塞。Windows 没有
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
        if _is_link_or_reparse_point(file_path):
            raise FileIntegrityError(f"拒绝符号链接或重解析点文件：{file_path}")
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise FileIntegrityError(f"文件路径无法安全检查：{file_path}") from exc

    _resolved_inside_root(file_path, root_path)

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    flags = (
        os.O_RDONLY
        | nofollow
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        fd = os.open(file_path, flags)
    except FileNotFoundError:
        raise
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise FileIntegrityError(f"拒绝符号链接文件：{file_path}") from exc
        raise FileIntegrityError(f"文件无法安全打开：{file_path}") from exc

    return _verify_open_descriptor(
        fd,
        display_path=file_path,
        expected_size=expected_size,
        expected_digest=expected_digest,
    )


def open_verified_relative_file(
    relative_path: str | PurePosixPath,
    *,
    allowed_root: str | Path,
    expected_size: int,
    expected_sha256: str,
) -> BinaryIO:
    """Open a portable relative file without following any POSIX path component.

    POSIX walks from an opened root directory with ``dir_fd`` and
    ``O_NOFOLLOW`` on every component, closing the parent-symlink race left by a
    normal path-based ``open``.  Windows lacks these directory-fd primitives;
    it falls back to :func:`open_verified_file` and retains that function's
    documented narrow race boundary.
    """

    text = str(relative_path)
    pure = PurePosixPath(text)
    if (
        "\\" in text
        or ":" in text
        or pure.is_absolute()
        or not pure.parts
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise FileIntegrityError("相对文件路径非法")

    root_path = Path(allowed_root)
    display_path = root_path.joinpath(*pure.parts)
    try:
        if _is_link_or_reparse_point(root_path):
            raise FileIntegrityError(f"拒绝符号链接或重解析点根目录：{root_path}")
        candidate = root_path
        for part in pure.parts:
            candidate = candidate / part
            if _is_link_or_reparse_point(candidate):
                raise FileIntegrityError(
                    f"拒绝包含符号链接或重解析点的路径：{display_path}"
                )
    except FileNotFoundError:
        raise
    except FileIntegrityError:
        raise
    except OSError as exc:
        raise FileIntegrityError(f"文件路径无法安全检查：{display_path}") from exc
    supports_dir_fd = (
        os.name != "nt"
        and os.open in os.supports_dir_fd
        and getattr(os, "O_DIRECTORY", 0) != 0
        and getattr(os, "O_NOFOLLOW", 0) != 0
    )
    if supports_dir_fd is not True:
        return open_verified_file(
            display_path,
            allowed_root=root_path,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
        )

    expected_size, expected_digest = _validate_expected_metadata(
        expected_size,
        expected_sha256,
    )
    common_flags = (
        getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | common_flags
    file_flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | common_flags
    directory_fds: list[int] = []
    try:
        current_fd = os.open(root_path, directory_flags)
        directory_fds.append(current_fd)
        for part in pure.parts[:-1]:
            current_fd = os.open(part, directory_flags, dir_fd=current_fd)
            directory_fds.append(current_fd)
        try:
            file_fd = os.open(pure.parts[-1], file_flags, dir_fd=current_fd)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise FileIntegrityError(f"拒绝符号链接文件：{display_path}") from exc
            raise FileIntegrityError(f"文件无法安全打开：{display_path}") from exc
    except FileIntegrityError:
        raise
    except OSError as exc:
        raise FileIntegrityError(f"文件路径无法按目录句柄安全打开：{display_path}") from exc
    finally:
        for directory_fd in reversed(directory_fds):
            os.close(directory_fd)

    return _verify_open_descriptor(
        file_fd,
        display_path=display_path,
        expected_size=expected_size,
        expected_digest=expected_digest,
    )
