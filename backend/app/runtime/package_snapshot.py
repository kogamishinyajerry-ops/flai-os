"""Immutable, content-addressed snapshots of complete Agent Package trees.

The authoring directory is mutable by design.  Runtime publication is not: one
captured object is carried through validation, audit, Registry and execution.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

import yaml


SNAPSHOT_CONTRACT = "agent_package_snapshot.v1"
_IGNORED_DIR_NAMES = frozenset({"__pycache__"})
_IGNORED_FILE_NAMES = frozenset({".DS_Store"})
_IGNORED_FILE_SUFFIXES = frozenset({".pyc", ".pyo"})
# Agent Package 是代码/契约/小型 eval fixture，不是 CFD 原始结果仓。限制在捕获
# 边界执行，避免误放大文件或深树让启动/并发任务发生无界内存与磁盘放大。
_MAX_ENTRIES = 4_096
_MAX_SINGLE_FILE_BYTES = 16 * 1024 * 1024
_MAX_TOTAL_BYTES = 64 * 1024 * 1024
_MAX_PATH_DEPTH = 32


class PackageSnapshotError(ValueError):
    """The package cannot be captured as one stable, safe byte tree."""


@dataclass(frozen=True, slots=True)
class _CapturedTree:
    root_signature: tuple[int, int, int, int, int, int]
    directories: tuple[tuple[str, tuple[int, int, int, int, int, int]], ...]
    files: tuple[
        tuple[str, bytes, tuple[int, int, int, int, int, int]], ...
    ]


@dataclass(frozen=True, slots=True)
class AgentPackageSnapshot:
    """A complete immutable Agent Package plus its versioned content identity."""

    digest: str
    manifest_json: str
    directories: tuple[str, ...]
    files: tuple[tuple[str, bytes], ...]

    @property
    def manifest(self) -> dict[str, Any]:
        parsed = json.loads(self.manifest_json)
        if not isinstance(parsed, dict):  # defensive invariant check
            raise PackageSnapshotError("snapshot manifest is not an object")
        return copy.deepcopy(parsed)

    @property
    def file_count(self) -> int:
        return len(self.files)

    @contextmanager
    def materialized(self, *, parent: Path | None = None) -> Iterator[Path]:
        """Restore into a new private directory and remove it on context exit."""

        parent_path: Path | None = None
        if parent is not None:
            parent_path = Path(parent)
            parent_path.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="flai-agent-package-",
            dir=str(parent_path) if parent_path is not None else None,
        ) as raw_dir:
            root = Path(raw_dir)
            for relative in self.directories:
                destination = _contained_destination(root, relative)
                destination.mkdir(parents=True, exist_ok=False)
                _chmod_if_supported(destination, 0o700)
            for relative, payload in self.files:
                destination = _contained_destination(root, relative)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("xb") as handle:
                    handle.write(payload)
                _chmod_if_supported(destination, 0o600)
            yield root


def capture_agent_package(package_dir: Path) -> AgentPackageSnapshot:
    """Capture the whole package twice and reject any torn or unsafe tree."""

    source = Path(package_dir)
    first = _capture_once(source)
    second = _capture_once(source)
    if first != second:
        raise PackageSnapshotError(f"{source} changed during snapshot capture")

    directories = tuple(path for path, _signature in first.directories)
    files = tuple((path, payload) for path, payload, _signature in first.files)
    file_map = dict(files)
    manifest_bytes = file_map.get("agent.yaml")
    if manifest_bytes is None:
        raise PackageSnapshotError(f"{source} is missing agent.yaml")
    try:
        manifest = yaml.safe_load(manifest_bytes.decode("utf-8"))
    except (UnicodeError, yaml.YAMLError, RecursionError) as exc:
        raise PackageSnapshotError(f"{source} agent.yaml cannot be parsed: {exc}") from exc
    if not isinstance(manifest, dict):
        raise PackageSnapshotError(f"{source} agent.yaml top level must be an object")

    try:
        manifest_json = json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise PackageSnapshotError(
            f"{source} agent.yaml cannot be represented as canonical JSON: {exc}"
        ) from exc
    digest = _snapshot_digest(directories, files)
    return AgentPackageSnapshot(
        digest=digest,
        manifest_json=manifest_json,
        directories=directories,
        files=files,
    )


def _capture_once(source: Path) -> _CapturedTree:
    try:
        root_before = source.lstat()
    except OSError as exc:
        raise PackageSnapshotError(f"cannot inspect package root {source}: {exc}") from exc
    if stat.S_ISLNK(root_before.st_mode):
        raise PackageSnapshotError(f"package root must not be a symlink: {source}")
    if _is_reparse_point(root_before):
        raise PackageSnapshotError(
            f"package root must not be a Windows reparse point: {source}"
        )
    if not stat.S_ISDIR(root_before.st_mode):
        raise PackageSnapshotError(f"package root is not a directory: {source}")

    directories: list[tuple[str, tuple[int, int, int, int, int, int]]] = []
    files: list[
        tuple[str, bytes, tuple[int, int, int, int, int, int]]
    ] = []
    seen_casefolded: dict[str, str] = {}
    entry_count = 0
    total_bytes = 0

    def walk(directory: Path, relative_parent: PurePosixPath) -> None:
        nonlocal entry_count, total_bytes
        try:
            with os.scandir(directory) as iterator:
                entries = []
                for entry in iterator:
                    entry_count += 1
                    if entry_count > _MAX_ENTRIES:
                        raise PackageSnapshotError(
                            f"package exceeds entry budget {_MAX_ENTRIES}"
                        )
                    entries.append(entry)
                entries.sort(key=lambda item: item.name)
        except OSError as exc:
            raise PackageSnapshotError(f"cannot scan package directory {directory}: {exc}") from exc
        for entry in entries:
            relative_path = relative_parent / entry.name
            relative = relative_path.as_posix()
            _validate_relative_path(relative)
            if len(relative_path.parts) > _MAX_PATH_DEPTH:
                raise PackageSnapshotError(
                    f"package path depth budget {_MAX_PATH_DEPTH} exceeded: {relative}"
                )
            folded = relative.casefold()
            existing = seen_casefolded.get(folded)
            if existing is not None and existing != relative:
                raise PackageSnapshotError(
                    f"case-insensitive path collision: {existing!r} and {relative!r}"
                )
            seen_casefolded[folded] = relative

            try:
                before = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise PackageSnapshotError(f"cannot inspect {relative}: {exc}") from exc
            if stat.S_ISLNK(before.st_mode):
                raise PackageSnapshotError(f"symlink is forbidden in package: {relative}")
            if _is_reparse_point(before):
                raise PackageSnapshotError(
                    f"Windows reparse point is forbidden in package: {relative}"
                )
            if stat.S_ISDIR(before.st_mode):
                if entry.name in _IGNORED_DIR_NAMES:
                    continue
                signature = _stat_signature(before)
                directories.append((relative, signature))
                walk(Path(entry.path), relative_path)
                try:
                    after = Path(entry.path).lstat()
                except OSError as exc:
                    raise PackageSnapshotError(
                        f"cannot re-inspect directory {relative}: {exc}"
                    ) from exc
                if _is_reparse_point(after):
                    raise PackageSnapshotError(
                        f"package directory changed to Windows reparse point: {relative}"
                    )
                if _stat_signature(after) != signature:
                    raise PackageSnapshotError(
                        f"package directory changed during capture: {relative}"
                    )
                continue
            if not stat.S_ISREG(before.st_mode):
                raise PackageSnapshotError(
                    f"non-regular package entry is forbidden: {relative}"
                )
            if (
                entry.name in _IGNORED_FILE_NAMES
                or Path(entry.name).suffix in _IGNORED_FILE_SUFFIXES
            ):
                continue
            if before.st_size > _MAX_SINGLE_FILE_BYTES:
                raise PackageSnapshotError(
                    f"package file exceeds single-file byte budget "
                    f"{_MAX_SINGLE_FILE_BYTES}: {relative}"
                )
            if total_bytes + before.st_size > _MAX_TOTAL_BYTES:
                raise PackageSnapshotError(
                    f"package exceeds total byte budget {_MAX_TOTAL_BYTES}: {relative}"
                )
            payload, signature = _read_stable_regular_file(
                Path(entry.path),
                relative,
                before,
                max_bytes=min(
                    _MAX_SINGLE_FILE_BYTES,
                    _MAX_TOTAL_BYTES - total_bytes,
                ),
            )
            total_bytes += len(payload)
            files.append((relative, payload, signature))

    walk(source, PurePosixPath())
    try:
        root_after = source.lstat()
    except OSError as exc:
        raise PackageSnapshotError(f"cannot re-inspect package root {source}: {exc}") from exc
    if _is_reparse_point(root_after):
        raise PackageSnapshotError(
            f"package root changed to Windows reparse point: {source}"
        )
    root_signature = _stat_signature(root_before)
    if _stat_signature(root_after) != root_signature:
        raise PackageSnapshotError(f"{source} changed during snapshot capture")
    return _CapturedTree(
        root_signature=root_signature,
        directories=tuple(directories),
        files=tuple(files),
    )


def _read_stable_regular_file(
    path: Path,
    relative: str,
    before: os.stat_result,
    *,
    max_bytes: int,
) -> tuple[bytes, tuple[int, int, int, int, int, int]]:
    flags = os.O_RDONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise PackageSnapshotError(f"cannot open package file {relative}: {exc}") from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise PackageSnapshotError(
                f"package file changed to non-regular entry: {relative}"
            )
        chunks: list[bytes] = []
        captured_bytes = 0
        while True:
            remaining = max_bytes + 1 - captured_bytes
            if remaining <= 0:
                raise PackageSnapshotError(
                    f"package file exceeds capture byte budget {max_bytes}: {relative}"
                )
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            captured_bytes += len(chunk)
            if captured_bytes > max_bytes:
                raise PackageSnapshotError(
                    f"package file exceeds capture byte budget {max_bytes}: {relative}"
                )
        after_read = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    try:
        after_path = path.lstat()
    except OSError as exc:
        raise PackageSnapshotError(f"cannot re-inspect package file {relative}: {exc}") from exc
    if _is_reparse_point(after_path):
        raise PackageSnapshotError(
            f"package file changed to Windows reparse point: {relative}"
        )
    signature = _stat_signature(before)
    if (
        _stat_signature(opened) != signature
        or _stat_signature(after_read) != signature
        or _stat_signature(after_path) != signature
    ):
        raise PackageSnapshotError(f"package file changed during capture: {relative}")
    payload = b"".join(chunks)
    if len(payload) != before.st_size:
        raise PackageSnapshotError(f"package file size changed during capture: {relative}")
    return payload, signature


def _snapshot_digest(
    directories: tuple[str, ...],
    files: tuple[tuple[str, bytes], ...],
) -> str:
    records: list[dict[str, Any]] = [
        {"kind": "directory", "path": relative} for relative in directories
    ]
    records.extend(
        {
            "kind": "file",
            "path": relative,
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        for relative, payload in files
    )
    canonical = json.dumps(
        {"contract": SNAPSHOT_CONTRACT, "entries": records},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _stat_signature(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _is_reparse_point(value: Any) -> bool:
    """Windows junction/symlink/other reparse points must never be traversed."""

    attributes = int(getattr(value, "st_file_attributes", 0) or 0)
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return (attributes & reparse_flag) != 0


def _validate_relative_path(relative: str) -> None:
    candidate = PurePosixPath(relative)
    if (
        not relative
        or "\\" in relative
        or candidate.is_absolute()
        or any(part in ("", ".", "..") for part in candidate.parts)
    ):
        raise PackageSnapshotError(f"unsafe package path: {relative!r}")


def _contained_destination(root: Path, relative: str) -> Path:
    _validate_relative_path(relative)
    destination = root.joinpath(*PurePosixPath(relative).parts)
    try:
        destination.relative_to(root)
    except ValueError as exc:  # defensive; parts validation already excludes traversal
        raise PackageSnapshotError(f"snapshot path escapes materialization root: {relative}") from exc
    return destination


def _chmod_if_supported(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except OSError:
        if os.name != "nt":
            raise
