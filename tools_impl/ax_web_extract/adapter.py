"""ax_web_extract L0 adapter。

L0 只允许测试夹具执行。生产 Runtime 不注入 fixture witness，因此环境变量不能把
本适配器变成真实联网入口；生产出站能力必须走后续独立 ADR 和可执行网络策略。
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import re
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .input_builder import build_derive_args, build_fetch_args
from .output_parser import parse_derived_output, parse_fetch_report

_FIXTURE_CONTEXT_KEY = "ax_l0_fixture_mode"
_FIXTURE_POLICY_ID = "l0-fixture-only"
_BIN_ENV = "FLAI_AX_BIN"
_BIN_SHA_ENV = "FLAI_AX_BIN_SHA256"
_ORIGINS_ENV = "FLAI_AX_ALLOWED_ORIGINS"
_NETWORK_POLICY_ENV = "FLAI_AX_NETWORK_POLICY_ID"
_SUPPORTED_AX_VERSION = "0.1.18"
_FIXTURE_URLS = frozenset(
    {
        "https://fixture.invalid/page",
        "https://fixture.invalid/slow",
        "https://fixture.invalid/large",
    }
)
_VERSION_TIMEOUT_S = 3.0
_DEFAULT_TIMEOUT_S = 10
_DEFAULT_MAX_BYTES = 1_000_000
_DEFAULT_LIMIT = 25
_DEFAULT_BUDGET_TOKENS = 1_000
_MAX_EXTRACTED_BYTES = 256_000
_MAX_DIAGNOSTIC_CHARS = 2_000
_SHA256_RE = re.compile(r"[a-f0-9]{64}")


def _fail(code: str, message: str) -> dict[str, Any]:
    return {"status": "failed", "error_code": code, "error_message": message}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _origin(url: str, *, fixture_only: bool) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("只允许带主机名的 HTTPS URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL 不得内嵌用户名或凭证")
    if parsed.query or parsed.fragment:
        raise ValueError("L0 URL 不得带 query 或 fragment，避免秘密进入任务证据")
    host = parsed.hostname.lower().rstrip(".")
    if fixture_only is True and not host.endswith(".invalid"):
        raise ValueError("L0 fixture 模式只允许 RFC 保留的 .invalid 主机名")
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError("localhost 不在 ax Web 工具边界内")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and address.is_global is not True:
        raise ValueError("非公网 IP 字面量被拒绝")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("URL 端口非法") from exc
    return f"https://{host}" + (f":{port}" if port not in (None, 443) else "")


def _allowed_origins() -> set[str]:
    raw = os.environ.get(_ORIGINS_ENV, "")
    origins: set[str] = set()
    for item in raw.split(","):
        candidate = item.strip()
        if not candidate:
            continue
        parsed = urlsplit(candidate)
        if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError(f"{_ORIGINS_ENV} 只能列 origin，不能带路径/查询/片段")
        origins.add(_origin(candidate, fixture_only=True))
    if not origins:
        raise ValueError(f"{_ORIGINS_ENV} 未配置任何 .invalid HTTPS origin")
    return origins


def _network_policy_id() -> str:
    policy_id = os.environ.get(_NETWORK_POLICY_ENV, "")
    if policy_id != _FIXTURE_POLICY_ID:
        raise ValueError(
            f"L0 只接受 {_NETWORK_POLICY_ENV}={_FIXTURE_POLICY_ID!r}；"
            "该标签不是生产网络授权"
        )
    return policy_id


def _pinned_binary() -> tuple[Path, str]:
    raw = os.environ.get(_BIN_ENV)
    expected = (os.environ.get(_BIN_SHA_ENV) or "").lower()
    if not raw:
        raise ValueError(f"{_BIN_ENV} 未配置")
    binary = Path(raw).expanduser()
    if not binary.is_absolute():
        raise ValueError(f"{_BIN_ENV} 必须是绝对路径")
    if binary.is_symlink() or not binary.is_file():
        raise ValueError(f"{_BIN_ENV} 必须指向普通文件且不能是符号链接")
    if _SHA256_RE.fullmatch(expected) is None:
        raise ValueError(f"{_BIN_SHA_ENV} 必须是 64 位小写 SHA-256")
    actual = _sha256_file(binary)
    if hmac.compare_digest(actual, expected) is not True:
        raise ValueError(f"ax 二进制 SHA-256 不匹配（expected={expected}, actual={actual}）")
    return binary, actual


def _subprocess_env(home: Path) -> dict[str, str]:
    # L0 不继承代理、令牌或用户 HOME。真实出站的代理/证书合同留给 L1。
    allowed = (
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "LANG",
        "LC_ALL",
    )
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    return env


def _invoke(
    binary: Path,
    args: list[str],
    *,
    cwd: Path,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(binary), *args],
        cwd=str(cwd),
        env=_subprocess_env(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        shell=False,
        check=False,
    )


def _write_private(path: Path, text: str) -> None:
    """先写同目录私有临时文件，再原子替换权威证据。"""
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt":
            temporary.chmod(0o600)
        temporary.replace(path)
        if os.name != "nt":
            path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _discard_run_dir(run_dir: Path) -> None:
    """只清理由本次调用新建、尚未登记为证据的精确目录。"""
    shutil.rmtree(run_dir, ignore_errors=True)


def _remaining(deadline: float) -> float:
    return deadline - time.monotonic()


def _truncate_utf8(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _persist_failure(
    *,
    run_dir: Path,
    raw_path: Path,
    task_id: str | None,
    error_code: str,
    error_message: str,
    evidence: dict[str, Any],
    manifest_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """原始 body 已存在时，失败也必须生成可咬合的权威 manifest。"""
    manifest_path = run_dir / "source-manifest.json"
    manifest = {
        "schema_version": "flai.ax-source-manifest.v0.1",
        "tool_id": "ax_web_extract",
        "tool_version": "0.1.0",
        "task_id": task_id,
        "status": "failed",
        "error_code": error_code,
        "error_message": error_message,
        **evidence,
    }
    if manifest_extra:
        manifest.update(manifest_extra)
    try:
        _write_private(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    except OSError as exc:
        _discard_run_dir(run_dir)
        return _fail("evidence_write_failed", f"失败证据清单无法落盘：{exc}")
    return {
        "status": "failed",
        "error_code": error_code,
        "error_message": error_message,
        **evidence,
        "raw_output_path": str(raw_path),
        "manifest_path": str(manifest_path),
    }


def run(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    tool_context = context or {}
    if tool_context.get(_FIXTURE_CONTEXT_KEY) is not True:
        return _fail(
            "activation_disabled",
            "L0 只允许测试夹具执行；生产 Runtime 不提供 ax_l0_fixture_mode witness",
        )

    try:
        allowed_origins = _allowed_origins()
        requested_url = str(payload["url"])
        if requested_url not in _FIXTURE_URLS:
            raise ValueError("L0 URL 不在固定 fixture 集合")
        requested_origin = _origin(requested_url, fixture_only=True)
        network_policy_id = _network_policy_id()
    except (KeyError, ValueError) as exc:
        return _fail("url_policy_invalid", str(exc))
    if requested_origin not in allowed_origins:
        return _fail("origin_not_allowed", "请求 origin 不在 L0 fixture allowlist")

    output_dir_raw = tool_context.get("output_dir")
    if not isinstance(output_dir_raw, str) or not output_dir_raw:
        return _fail("workspace_missing", "可信 tool_context.output_dir 缺失，拒绝落原始证据")
    output_dir = Path(output_dir_raw).expanduser()
    if not output_dir.is_absolute():
        return _fail("workspace_invalid", "tool_context.output_dir 必须是绝对路径")
    output_dir = output_dir.resolve()

    timeout_seconds = int(payload.get("timeout_seconds", _DEFAULT_TIMEOUT_S))
    deadline = time.monotonic() + timeout_seconds
    try:
        binary, binary_sha256 = _pinned_binary()
    except (OSError, ValueError) as exc:
        return _fail("binary_untrusted", str(exc))
    if _remaining(deadline) <= 0:
        return _fail("version_timeout", "ax 调用总预算在版本校验前已耗尽")

    run_id = uuid.uuid4().hex
    run_dir = output_dir / "ax" / run_id
    try:
        run_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
        if os.name != "nt":
            run_dir.chmod(0o700)
    except OSError as exc:
        return _fail("workspace_unavailable", f"无法建立 ax 调用目录：{exc}")

    version_timeout = min(_VERSION_TIMEOUT_S, _remaining(deadline))
    if version_timeout <= 0:
        _discard_run_dir(run_dir)
        return _fail("version_timeout", "ax 调用总预算在版本校验前已耗尽")
    try:
        version_proc = _invoke(binary, ["--version"], cwd=run_dir, timeout=version_timeout)
    except subprocess.TimeoutExpired:
        _discard_run_dir(run_dir)
        return _fail("version_timeout", "ax --version 超过本次调用剩余总预算")
    except OSError as exc:
        _discard_run_dir(run_dir)
        return _fail("binary_start_failed", f"ax --version 启动失败：{exc}")
    version = (version_proc.stdout or "").strip()
    if version_proc.returncode != 0 or version != _SUPPORTED_AX_VERSION:
        _discard_run_dir(run_dir)
        return _fail(
            "version_mismatch",
            f"只支持 ax {_SUPPORTED_AX_VERSION}，实得 rc={version_proc.returncode}, version={version!r}",
        )

    operation = str(payload["operation"])
    max_bytes = int(payload.get("max_bytes", _DEFAULT_MAX_BYTES))
    limit = int(payload.get("limit", _DEFAULT_LIMIT))
    budget_tokens = int(payload.get("budget_tokens", _DEFAULT_BUDGET_TOKENS))
    raw_path = run_dir / "response.body"
    fetched_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    fetch_timeout = _remaining(deadline)
    if fetch_timeout <= 0:
        _discard_run_dir(run_dir)
        return _fail("fetch_timeout", "ax 调用总预算在获取前已耗尽")
    try:
        proc = _invoke(
            binary,
            build_fetch_args(
                url=str(payload["url"]),
                raw_path=raw_path,
                max_bytes=max_bytes,
                timeout_seconds=fetch_timeout,
            ),
            cwd=run_dir,
            timeout=fetch_timeout,
        )
    except subprocess.TimeoutExpired:
        _discard_run_dir(run_dir)
        return _fail("fetch_timeout", f"ax 获取超过 {timeout_seconds}s 调用总预算")
    except OSError as exc:
        _discard_run_dir(run_dir)
        return _fail("fetch_start_failed", f"ax 获取进程启动失败：{exc}")

    try:
        _write_private(run_dir / "fetch.stdout.json", (proc.stdout or "")[:_MAX_DIAGNOSTIC_CHARS])
        _write_private(run_dir / "fetch.stderr.txt", (proc.stderr or "")[:_MAX_DIAGNOSTIC_CHARS])
    except OSError as exc:
        _discard_run_dir(run_dir)
        return _fail("evidence_write_failed", f"ax 获取诊断无法落盘：{exc}")
    if raw_path.is_symlink() or not raw_path.is_file():
        _discard_run_dir(run_dir)
        return _fail("raw_output_missing", "ax 未产生预期的普通原始响应文件")
    try:
        byte_count = raw_path.stat().st_size
        digest = _sha256_file(raw_path)
    except OSError as exc:
        _discard_run_dir(run_dir)
        return _fail("raw_output_invalid", f"原始响应不可读：{exc}")

    task_id_raw = tool_context.get("task_id")
    task_id = task_id_raw if isinstance(task_id_raw, str) else None
    evidence: dict[str, Any] = {
        "operation": operation,
        "run_id": run_id,
        "ax_version": version,
        "ax_binary_sha256": binary_sha256,
        "network_policy_id": network_policy_id,
        "requested_url": requested_url,
        "fetched_at": fetched_at,
        "byte_count": byte_count,
        "sha256": digest,
        "raw_output_path": str(raw_path),
        "truncated": False,
    }

    if byte_count > max_bytes:
        return _persist_failure(
            run_dir=run_dir,
            raw_path=raw_path,
            task_id=task_id,
            error_code="raw_output_oversized",
            error_message=f"原始响应 {byte_count} bytes 超过调用上限 {max_bytes}",
            evidence=evidence,
        )

    if proc.returncode != 0:
        return _persist_failure(
            run_dir=run_dir,
            raw_path=raw_path,
            task_id=task_id,
            error_code="fetch_failed",
            error_message=f"ax 获取失败（rc={proc.returncode}）：{(proc.stderr or '').strip()[:500]}",
            evidence=evidence,
        )
    try:
        report = parse_fetch_report(proc.stdout or "")
    except ValueError as exc:
        return _persist_failure(
            run_dir=run_dir,
            raw_path=raw_path,
            task_id=task_id,
            error_code="report_invalid",
            error_message=str(exc),
            evidence=evidence,
        )
    try:
        saved = Path(str(report.get("saved", ""))).resolve()
        expected_saved = raw_path.resolve()
    except OSError as exc:
        return _persist_failure(
            run_dir=run_dir,
            raw_path=raw_path,
            task_id=task_id,
            error_code="report_invalid",
            error_message=f"ax saved 路径不可解析：{exc}",
            evidence=evidence,
        )
    if saved != expected_saved:
        return _persist_failure(
            run_dir=run_dir,
            raw_path=raw_path,
            task_id=task_id,
            error_code="report_invalid",
            error_message="ax 报告的 saved 路径与受控输出路径不一致",
            evidence=evidence,
        )

    final_url = report.get("url")
    if not isinstance(final_url, str):
        return _persist_failure(
            run_dir=run_dir,
            raw_path=raw_path,
            task_id=task_id,
            error_code="report_invalid",
            error_message="ax 报告缺少 final URL",
            evidence=evidence,
        )
    if final_url not in _FIXTURE_URLS:
        return _persist_failure(
            run_dir=run_dir,
            raw_path=raw_path,
            task_id=task_id,
            error_code="redirect_not_allowed",
            error_message="最终 URL 不在固定 L0 fixture 集合",
            evidence=evidence,
        )
    try:
        final_origin = _origin(final_url, fixture_only=True)
    except ValueError as exc:
        return _persist_failure(
            run_dir=run_dir,
            raw_path=raw_path,
            task_id=task_id,
            error_code="redirect_policy_invalid",
            error_message=f"最终 URL 非法：{exc}",
            evidence=evidence,
        )
    if final_origin not in allowed_origins:
        return _persist_failure(
            run_dir=run_dir,
            raw_path=raw_path,
            task_id=task_id,
            error_code="redirect_not_allowed",
            error_message="最终 origin 不在 L0 fixture allowlist",
            evidence=evidence,
        )
    evidence["final_url"] = final_url

    http_status = report.get("status")
    ok = report.get("ok")
    redirected = report.get("redirected")
    elapsed_ms = report.get("ms")
    if (
        not isinstance(http_status, int)
        or isinstance(http_status, bool)
        or not 100 <= http_status <= 599
        or not isinstance(redirected, bool)
        or not isinstance(elapsed_ms, int)
        or isinstance(elapsed_ms, bool)
        or elapsed_ms < 0
        or not isinstance(ok, bool)
    ):
        return _persist_failure(
            run_dir=run_dir,
            raw_path=raw_path,
            task_id=task_id,
            error_code="report_invalid",
            error_message="ax 报告的 status/ok/redirected/ms 类型不合法",
            evidence=evidence,
        )
    evidence.update(
        {
            "http_status": http_status,
            "ok": ok,
            "redirected": redirected,
            "elapsed_ms": elapsed_ms,
        }
    )
    if ok is not True:
        return _persist_failure(
            run_dir=run_dir,
            raw_path=raw_path,
            task_id=task_id,
            error_code="http_error",
            error_message=f"上游返回 HTTP {http_status}，候选证据不判成功",
            evidence=evidence,
        )

    data: Any = None
    extracted_output_path: Path | None = None
    extraction_sha256: str | None = None
    truncated = False
    extraction_manifest: dict[str, Any] | None = None
    if operation in ("discover", "extract"):
        extract_args, output_is_json = build_derive_args(
            operation=operation,
            payload=payload,
            raw_path=raw_path,
            limit=limit,
            budget_tokens=budget_tokens,
        )
        extract_timeout = _remaining(deadline)
        if extract_timeout <= 0:
            return _persist_failure(
                run_dir=run_dir,
                raw_path=raw_path,
                task_id=task_id,
                error_code="extract_timeout",
                error_message=f"ax 本地抽取超过 {timeout_seconds}s 调用总预算",
                evidence=evidence,
            )
        try:
            extract_proc = _invoke(binary, extract_args, cwd=run_dir, timeout=extract_timeout)
        except subprocess.TimeoutExpired:
            return _persist_failure(
                run_dir=run_dir,
                raw_path=raw_path,
                task_id=task_id,
                error_code="extract_timeout",
                error_message=f"ax 本地抽取超过 {timeout_seconds}s 调用总预算",
                evidence=evidence,
            )
        except OSError as exc:
            return _persist_failure(
                run_dir=run_dir,
                raw_path=raw_path,
                task_id=task_id,
                error_code="extract_start_failed",
                error_message=f"ax 本地抽取进程启动失败：{exc}",
                evidence=evidence,
            )
        extracted_stdout = extract_proc.stdout or ""
        extracted_stderr = extract_proc.stderr or ""
        extracted_output_path = run_dir / (
            f"{operation}.stdout.json" if output_is_json else f"{operation}.stdout.txt"
        )
        truncated_stdout = _truncate_utf8(extracted_stdout, _MAX_EXTRACTED_BYTES)
        try:
            _write_private(extracted_output_path, truncated_stdout)
            _write_private(
                run_dir / "extract.stderr.txt",
                extracted_stderr[:_MAX_DIAGNOSTIC_CHARS],
            )
            extraction_sha256 = _sha256_file(extracted_output_path)
        except OSError as exc:
            return _persist_failure(
                run_dir=run_dir,
                raw_path=raw_path,
                task_id=task_id,
                error_code="evidence_write_failed",
                error_message=f"ax 抽取诊断无法落盘：{exc}",
                evidence=evidence,
            )
        evidence_with_extract = {
            **evidence,
            "extracted_output_path": str(extracted_output_path),
            "extraction_sha256": extraction_sha256,
            "truncated": len(extracted_stdout.encode("utf-8")) > _MAX_EXTRACTED_BYTES,
        }
        if extract_proc.returncode != 0:
            return _persist_failure(
                run_dir=run_dir,
                raw_path=raw_path,
                task_id=task_id,
                error_code="extract_failed",
                error_message=(
                    f"ax 本地抽取失败（rc={extract_proc.returncode}）："
                    f"{extracted_stderr.strip()[:500]}"
                ),
                evidence=evidence_with_extract,
            )
        if evidence_with_extract["truncated"] is True:
            return _persist_failure(
                run_dir=run_dir,
                raw_path=raw_path,
                task_id=task_id,
                error_code="extract_output_oversized",
                error_message=f"ax 抽取输出超过 {_MAX_EXTRACTED_BYTES} bytes 平台上限",
                evidence=evidence_with_extract,
            )
        try:
            data, truncated = parse_derived_output(
                operation=operation,
                output_is_json=output_is_json,
                stdout=extracted_stdout,
                stderr=extracted_stderr,
            )
        except ValueError as exc:
            return _persist_failure(
                run_dir=run_dir,
                raw_path=raw_path,
                task_id=task_id,
                error_code="extract_output_invalid",
                error_message=str(exc),
                evidence=evidence_with_extract,
            )
        evidence.update(evidence_with_extract)
        evidence["truncated"] = truncated
        if operation == "extract":
            extraction_manifest = {
                "selector": str(payload["selector"]),
                "row": payload.get("row"),
                "limit": limit,
                "budget_tokens": budget_tokens,
            }
        else:
            extraction_manifest = {
                "mode": "locate" if isinstance(payload.get("needle"), str) else "outline",
                "needle": payload.get("needle"),
                "limit": limit,
                "budget_tokens": budget_tokens,
            }

    manifest_path = run_dir / "source-manifest.json"
    manifest = {
        "schema_version": "flai.ax-source-manifest.v0.1",
        "tool_id": "ax_web_extract",
        "tool_version": "0.1.0",
        "task_id": task_id,
        "status": "success",
        **evidence,
    }
    if extraction_manifest is not None:
        manifest["extraction"] = extraction_manifest
    try:
        _write_private(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    except OSError as exc:
        return _persist_failure(
            run_dir=run_dir,
            raw_path=raw_path,
            task_id=task_id,
            error_code="evidence_write_failed",
            error_message=f"成功证据清单无法落盘：{exc}",
            evidence=evidence,
        )
    result: dict[str, Any] = {
        "status": "success",
        **evidence,
        "manifest_path": str(manifest_path),
    }
    if extracted_output_path is not None:
        result["data"] = data
    return result
