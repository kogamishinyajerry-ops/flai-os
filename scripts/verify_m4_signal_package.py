#!/usr/bin/env python3
"""Evaluate an exact M4 signal package without changing roadmap or deploy state."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import stat
import sys
import tempfile
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.governance.m4_signal_gate import evaluate_signal_package  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fail-closed M4 scheduling-signal gate. This does not prove N10, "
            "authorize deployment, or change the roadmap."
        )
    )
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument(
        "--report",
        type=Path,
        help="Optional JSON report path; parent directory must already exist.",
    )
    return parser


def _path_comparison_parts(path: Path) -> tuple[str, ...]:
    """Conservative cross-platform key for case/Unicode/trailing-dot aliases."""

    return tuple(
        unicodedata.normalize("NFKC", part).rstrip(" .").casefold()
        for part in path.parts
    )


def _same_path_alias(left: Path, right: Path) -> bool:
    return _path_comparison_parts(left) == _path_comparison_parts(right)


def _inside_or_equal(candidate: Path, root: Path) -> bool:
    candidate_parts = _path_comparison_parts(candidate)
    root_parts = _path_comparison_parts(root)
    return candidate_parts[: len(root_parts)] == root_parts


def _same_existing_file(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except (FileNotFoundError, OSError):
        return False


def _report_target_error(report: Path, package: Path, evidence_root: Path) -> str | None:
    """Keep derived output physically separate from every gate input."""

    try:
        report_lexical = Path(os.path.abspath(report))
        package_lexical = Path(os.path.abspath(package))
        root_lexical = Path(os.path.abspath(evidence_root))
        report_resolved = report.resolve(strict=False)
        package_resolved = package.resolve(strict=False)
        root_resolved = evidence_root.resolve(strict=False)
    except OSError as exc:
        return f"report path cannot be resolved safely: {exc}"
    if (
        _same_path_alias(report_lexical, package_lexical)
        or _same_path_alias(report_resolved, package_resolved)
        or _same_existing_file(report, package)
    ):
        return "report path must not overwrite the input package"
    if _inside_or_equal(report_lexical, root_lexical) or _inside_or_equal(
        report_resolved, root_resolved
    ):
        return "report path must stay outside the evidence root"
    return None


def _write_report_atomically(path: Path, rendered: str) -> None:
    """Replace only the named output entry; never follow a final symlink/hardlink."""

    supports_directory_fd = (
        os.name != "nt"
        and os.open in os.supports_dir_fd
        and getattr(os, "O_DIRECTORY", 0) != 0
        and getattr(os, "O_NOFOLLOW", 0) != 0
    )
    if supports_directory_fd:
        directory_flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
        parent_fd = os.open(path.parent, directory_flags)
        temporary_name: str | None = None
        temporary_fd = -1
        try:
            if stat.S_ISDIR(os.fstat(parent_fd).st_mode) is not True:
                raise OSError("report parent is not a directory")
            create_flags = (
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0)
            )
            for _ in range(16):
                candidate = f".{path.name}.{secrets.token_hex(8)}.tmp"
                try:
                    temporary_fd = os.open(
                        candidate,
                        create_flags,
                        0o600,
                        dir_fd=parent_fd,
                    )
                except FileExistsError:
                    continue
                temporary_name = candidate
                break
            if temporary_name is None:
                raise OSError("unable to allocate a unique report temp file")
            with os.fdopen(
                temporary_fd,
                "w",
                encoding="utf-8",
                newline="\n",
            ) as handle:
                temporary_fd = -1
                handle.write(rendered)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(
                temporary_name,
                path.name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            temporary_name = None
            return
        finally:
            if temporary_fd >= 0:
                os.close(temporary_fd)
            if temporary_name is not None:
                try:
                    os.unlink(temporary_name, dir_fd=parent_fd)
                except FileNotFoundError:
                    pass
            os.close(parent_fd)

    fd, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            fd = -1
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if fd >= 0:
            os.close(fd)
        temporary_path.unlink(missing_ok=True)


def _stable_report_target(path: Path) -> Path:
    parent = path.parent.resolve(strict=True)
    if parent.is_dir() is not True:
        raise OSError("report parent is not a directory")
    return parent / path.name


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report_target: Path | None = None
    if args.report is not None:
        target_error = _report_target_error(
            args.report,
            args.package,
            args.evidence_root,
        )
        if target_error is not None:
            print(f"M4 gate report path rejected: {target_error}", file=sys.stderr)
            return 1
        try:
            report_target = _stable_report_target(args.report)
        except OSError as exc:
            print(f"M4 gate report path rejected: {exc}", file=sys.stderr)
            return 1
        target_error = _report_target_error(
            report_target,
            args.package,
            args.evidence_root,
        )
        if target_error is not None:
            print(f"M4 gate report path rejected: {target_error}", file=sys.stderr)
            return 1
    report = evaluate_signal_package(args.package, args.evidence_root)
    rendered = json.dumps(
        report.as_dict(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    if report_target is not None:
        try:
            target_error = _report_target_error(
                report_target,
                args.package,
                args.evidence_root,
            )
            if target_error is not None:
                print(
                    f"M4 gate report path rejected before write: {target_error}",
                    file=sys.stderr,
                )
                return 1
            _write_report_atomically(report_target, rendered)
        except OSError as exc:
            print(f"M4 gate report write failed: {exc}", file=sys.stderr)
            return 1
    sys.stdout.write(rendered)
    return 0 if report.complete is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
