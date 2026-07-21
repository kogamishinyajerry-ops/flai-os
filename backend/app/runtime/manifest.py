"""Agent 执行包的跨派发/执行规范化绑定。

``agent_manifest_digest`` 的名字为兼容既有任务 metadata 保留，但其承重语义是
完整执行快照：规范化 ``agent.yaml`` 对象 + 实际引用的 workflow/prompt/schema
文件路径与内容。Registry 在 scan 时捕获一次不可变字节，派发与 Runtime 均只绑定
该快照；不能把 digest 校验完后再回头读取活目录。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MANIFEST_PIN_VERSION = "agent_manifest_pin.v2"
EXECUTION_FILES_DIGEST_VERSION = "agent_execution_files.v1"


def _canonical_manifest_json(manifest: dict[str, Any]) -> str:
    return json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def referenced_execution_files(manifest: dict[str, Any]) -> tuple[str, ...]:
    """返回会影响当前包执行的实际引用文件（与 M10 包核心指纹同一边界）。"""
    names = ["prompt.md"]
    for ref in (
        (manifest.get("workflow") or {}).get("entrypoint"),
        (manifest.get("input") or {}).get("schema"),
        (manifest.get("output") or {}).get("schema"),
    ):
        if isinstance(ref, str) and ref:
            names.append(ref)
    return tuple(sorted(set(names)))


def capture_execution_files(
    manifest: dict[str, Any], package_dir: str | Path
) -> tuple[tuple[str, bytes], ...]:
    """从包根捕获执行文件；越界、缺失、目录或读取失败一律抛错。

    返回 tuple[path, immutable bytes]，使 Registry 发布后不再依赖活目录字节。
    """
    root = Path(package_dir).resolve(strict=True)
    captured: list[tuple[str, bytes]] = []
    for rel_name in referenced_execution_files(manifest):
        relative = Path(rel_name)
        if relative.is_absolute():
            raise ValueError(f"Agent 执行文件必须位于包内：{rel_name!r}")
        candidate = root / relative
        resolved = candidate.resolve(strict=True)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Agent 执行文件逃出包根：{rel_name!r}") from exc
        if not candidate.is_file():
            raise ValueError(f"Agent 执行文件不是常规文件：{rel_name!r}")
        captured.append((rel_name, candidate.read_bytes()))
    return tuple(captured)


def _execution_file_records(
    package_files: tuple[tuple[str, bytes], ...]
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    files: list[dict[str, Any]] = []
    for rel_name, content in sorted(package_files, key=lambda item: item[0]):
        if rel_name in seen:
            raise ValueError(f"Agent 执行快照含重复路径：{rel_name!r}")
        seen.add(rel_name)
        files.append(
            {
                "path": rel_name,
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    return files


def canonical_execution_files_digest(
    package_files: tuple[tuple[str, bytes], ...]
) -> str:
    """计算 agent.yaml 声明的执行文件代际摘要（不含 manifest，避免自引用）。"""
    encoded = json.dumps(
        {
            "contract": EXECUTION_FILES_DIGEST_VERSION,
            "files": _execution_file_records(package_files),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def canonical_manifest_digest(
    manifest: dict[str, Any], package_files: tuple[tuple[str, bytes], ...]
) -> str:
    """计算规范化执行快照摘要；调用方必须显式提供已捕获文件字节。"""
    encoded = json.dumps(
        {
            "contract": MANIFEST_PIN_VERSION,
            "manifest": manifest,
            "files": _execution_file_records(package_files),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class AgentExecutionSnapshot:
    """Registry 单次 scan 发布的不可变执行视图。"""

    agent_id: str
    package_dir: Path
    manifest_json: str
    package_files: tuple[tuple[str, bytes], ...]
    digest: str

    @property
    def manifest(self) -> dict[str, Any]:
        # 每次返回新对象，调用方无法改写 Registry 内快照。
        return json.loads(self.manifest_json)

    def read_file(self, rel_name: str) -> bytes:
        for captured_name, content in self.package_files:
            if captured_name == rel_name:
                return content
        raise FileNotFoundError(f"执行快照未捕获文件：{rel_name}")


def build_execution_snapshot(
    manifest: dict[str, Any], package_dir: str | Path
) -> AgentExecutionSnapshot:
    files = capture_execution_files(manifest, package_dir)
    declared_digest = manifest.get("execution_digest")
    actual_digest = canonical_execution_files_digest(files)
    if declared_digest != actual_digest:
        raise ValueError(
            "agent.yaml execution_digest 与实际 prompt/workflow/schema 字节不一致："
            f"declared={declared_digest!r}, actual={actual_digest!r}"
        )
    return AgentExecutionSnapshot(
        agent_id=str(manifest.get("id") or ""),
        package_dir=Path(package_dir),
        manifest_json=_canonical_manifest_json(manifest),
        package_files=files,
        digest=canonical_manifest_digest(manifest, files),
    )
