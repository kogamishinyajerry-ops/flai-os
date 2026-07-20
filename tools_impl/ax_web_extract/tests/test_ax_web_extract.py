"""ax_web_extract 的离线契约测试。

所有行为从 ToolRegistry.call 公共接缝观察；测试不访问网络，也不依赖本机安装 ax。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from backend.app.config import AGENTS_DIR, CONTRACTS_DIR, TOOLS_DIR
from backend.app.core.errors import ToolInputInvalidError, ToolOutputInvalidError
from backend.app.storage import db as db_mod
from backend.app.storage import repos
from backend.app.tools.registry import ToolRegistry

pytestmark = pytest.mark.skipif(
    os.name == "nt",
    reason=(
        "ADR-0030 L0 uses a POSIX executable fake only; Windows ax .exe packaging and "
        "target-machine verification remain an explicit production gate"
    ),
)


def _registry() -> ToolRegistry:
    registry = ToolRegistry(TOOLS_DIR, CONTRACTS_DIR / "tool.schema.json")
    registry.scan()
    return registry


def _write_fake_ax(
    tmp_path: Path,
    *,
    version: str = "0.1.18",
    fetch_sleep: float = 0,
    derive_exit: int = 0,
    derive_stdout_size: int = 0,
    final_url: str | None = None,
    http_status: int = 200,
    ok_value: object = True,
) -> tuple[Path, str]:
    binary = tmp_path / "fake-ax"
    body = b"<html><body><article><h1>Fixture title</h1></article></body></html>"
    binary.write_text(
        f"#!{sys.executable}\n"
        "import json\n"
        "import pathlib\n"
        "import sys\n"
        "import time\n"
        f"VERSION = {version!r}\n"
        f"BODY = {body!r}\n"
        f"FETCH_SLEEP = {fetch_sleep!r}\n"
        f"DERIVE_EXIT = {derive_exit!r}\n"
        f"DERIVE_STDOUT_SIZE = {derive_stdout_size!r}\n"
        f"FINAL_URL = {final_url!r}\n"
        f"HTTP_STATUS = {http_status!r}\n"
        f"OK_VALUE = {ok_value!r}\n"
        "args = sys.argv[1:]\n"
        "if args == ['--version']:\n"
        "    print(VERSION)\n"
        "    raise SystemExit(0)\n"
        "if '--output' not in args:\n"
        "    if DERIVE_STDOUT_SIZE:\n"
        "        print('x' * DERIVE_STDOUT_SIZE, end='')\n"
        "    if DERIVE_EXIT:\n"
        "        print('fixture derive failed', file=sys.stderr)\n"
        "        raise SystemExit(DERIVE_EXIT)\n"
        "    if '--outline' in args:\n"
        "        print('    3  article.card')\n"
        "        print('    3  article.card > h2')\n"
        "        raise SystemExit(0)\n"
        "    if '--locate' in args:\n"
        "        print(json.dumps([{'selector': 'article.card > h2', 'match': 'Fixture title'}]))\n"
        "        raise SystemExit(0)\n"
        "    if '--row' in args:\n"
        "        print(json.dumps([{'title': 'Fixture title'}]))\n"
        "        print('1 rows extracted', file=sys.stderr)\n"
        "        raise SystemExit(0)\n"
        "    raise SystemExit(9)\n"
        "url = args[0]\n"
        "if FETCH_SLEEP:\n"
        "    time.sleep(FETCH_SLEEP)\n"
        "out = pathlib.Path(args[args.index('--output') + 1])\n"
        "out.write_bytes(BODY)\n"
        "target = FINAL_URL or url\n"
        "print(json.dumps({'status': HTTP_STATUS, 'ok': OK_VALUE, 'url': target, "
        "'redirected': target != url, 'ms': 7, 'saved': str(out), 'bytes': len(BODY)}))\n",
        encoding="utf-8",
    )
    binary.chmod(0o700)
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    return binary, digest


def _enable_fake_ax(monkeypatch, tmp_path: Path, **fake_kwargs) -> Path:
    binary, digest = _write_fake_ax(tmp_path, **fake_kwargs)
    monkeypatch.setenv("FLAI_AX_BIN", str(binary))
    monkeypatch.setenv("FLAI_AX_BIN_SHA256", digest)
    monkeypatch.setenv("FLAI_AX_ALLOWED_ORIGINS", "https://fixture.invalid")
    monkeypatch.setenv("FLAI_AX_NETWORK_POLICY_ID", "l0-fixture-only")
    return binary


def _tool_context(output_dir: Path) -> dict[str, object]:
    return {"output_dir": str(output_dir), "ax_l0_fixture_mode": True}


def test_registered_tool_is_fail_closed_when_execution_not_enabled(monkeypatch, tmp_path) -> None:
    _enable_fake_ax(monkeypatch, tmp_path)
    monkeypatch.setenv("FLAI_AX_LIVE_ENABLED", "1")  # 旧式 env 开关也不得解锁 L0。
    registry = _registry()

    tool = registry.get("ax_web_extract")
    assert tool is not None
    assert tool["output_classification"] == "sensitive"
    for manifest in AGENTS_DIR.glob("*/agent.yaml"):
        agent = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        assert "ax_web_extract" not in (agent.get("tools") or []), manifest
    result = registry.call(
        "ax_web_extract",
        {"operation": "fetch", "url": "https://fixture.invalid/page"},
        tool_context={"output_dir": str(tmp_path)},
    )

    assert result["status"] == "failed"
    assert result["error_code"] == "activation_disabled"
    assert "fixture" in result["error_message"]
    assert not (tmp_path / "ax").exists()


def test_fetch_writes_pinned_raw_response_and_provenance_manifest(monkeypatch, tmp_path) -> None:
    binary = _enable_fake_ax(monkeypatch, tmp_path)
    output_dir = tmp_path / "task-output"

    result = _registry().call(
        "ax_web_extract",
        {"operation": "fetch", "url": "https://fixture.invalid/page"},
        task_id="task_ax_fixture",
        tool_context=_tool_context(output_dir),
    )

    assert result["status"] == "success"
    assert result["ax_version"] == "0.1.18"
    assert result["ax_binary_sha256"] == hashlib.sha256(binary.read_bytes()).hexdigest()
    assert result["network_policy_id"] == "l0-fixture-only"
    assert result["requested_url"] == "https://fixture.invalid/page"
    assert result["final_url"] == "https://fixture.invalid/page"
    assert result["http_status"] == 200
    assert result["ok"] is True
    assert result["redirected"] is False

    raw_path = Path(result["raw_output_path"])
    manifest_path = Path(result["manifest_path"])
    assert raw_path.is_relative_to(output_dir)
    assert manifest_path.is_relative_to(output_dir)
    assert raw_path.read_bytes().startswith(b"<html>")
    assert result["sha256"] == hashlib.sha256(raw_path.read_bytes()).hexdigest()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "flai.ax-source-manifest.v0.1"
    assert manifest["task_id"] == "task_ax_fixture"
    assert manifest["ax_binary_sha256"] == result["ax_binary_sha256"]
    assert manifest["network_policy_id"] == "l0-fixture-only"
    assert manifest["sha256"] == result["sha256"]
    assert manifest["raw_output_path"] == str(raw_path)
    assert os.path.samefile(manifest_path.parent, raw_path.parent)


def test_signed_or_credential_query_is_rejected_and_redacted_before_subprocess(
    monkeypatch, tmp_path
) -> None:
    _enable_fake_ax(monkeypatch, tmp_path)
    output_dir = tmp_path / "task-output"
    secret = "must-not-enter-task-evidence"
    db_path = tmp_path / "invalid-input.db"
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        with pytest.raises(ToolInputInvalidError) as error:
            _registry().call(
                "ax_web_extract",
                {
                    "operation": "fetch",
                    "url": f"https://fixture.invalid/page?token={secret}",
                },
                conn=conn,
                task_id="task_ax_invalid_input",
                tool_context=_tool_context(output_dir),
            )
        runs = repos.list_tool_runs(conn, "task_ax_invalid_input")
    finally:
        conn.close()

    assert secret not in str(error.value)
    assert len(runs) == 1
    assert runs[0]["input"] == {
        "_redacted": True,
        "input_keys": ["operation", "url"],
    }
    assert secret not in runs[0]["error_message"]
    assert not (output_dir / "ax").exists()


@pytest.mark.parametrize(
    "payload",
    [
        {"operation": "fetch", "url": "http://fixture.invalid/page"},
        {
            "operation": "fetch",
            "url": "https://fixture.invalid/page",
            "headers": {"authorization": "secret"},
        },
    ],
)
def test_input_contract_rejects_non_https_and_caller_supplied_headers(
    monkeypatch, tmp_path, payload
) -> None:
    _enable_fake_ax(monkeypatch, tmp_path)
    with pytest.raises(ToolInputInvalidError):
        _registry().call(
            "ax_web_extract",
            payload,
            tool_context=_tool_context(tmp_path / "task-output"),
        )


def test_l0_input_contract_rejects_real_hosts_before_subprocess(
    monkeypatch, tmp_path
) -> None:
    _enable_fake_ax(monkeypatch, tmp_path)
    output_dir = tmp_path / "task-output"

    with pytest.raises(ToolInputInvalidError):
        _registry().call(
            "ax_web_extract",
            {"operation": "fetch", "url": "https://example.com/page"},
            tool_context=_tool_context(output_dir),
        )

    assert not (output_dir / "ax").exists()


def test_binary_hash_mismatch_fails_before_execution(monkeypatch, tmp_path) -> None:
    _enable_fake_ax(monkeypatch, tmp_path)
    monkeypatch.setenv("FLAI_AX_BIN_SHA256", "0" * 64)

    result = _registry().call(
        "ax_web_extract",
        {"operation": "fetch", "url": "https://fixture.invalid/page"},
        tool_context=_tool_context(tmp_path / "task-output"),
    )

    assert result["status"] == "failed"
    assert result["error_code"] == "binary_untrusted"


def test_unsupported_ax_version_fails_closed(monkeypatch, tmp_path) -> None:
    _enable_fake_ax(monkeypatch, tmp_path, version="0.1.17")

    result = _registry().call(
        "ax_web_extract",
        {"operation": "fetch", "url": "https://fixture.invalid/page"},
        tool_context=_tool_context(tmp_path / "task-output"),
    )

    assert result["status"] == "failed"
    assert result["error_code"] == "version_mismatch"


def test_inner_fetch_timeout_and_byte_limit_are_fail_closed(monkeypatch, tmp_path) -> None:
    _enable_fake_ax(monkeypatch, tmp_path, fetch_sleep=2)
    timed_out = _registry().call(
        "ax_web_extract",
        {
            "operation": "fetch",
            "url": "https://fixture.invalid/slow",
            "timeout_seconds": 1,
        },
        tool_context=_tool_context(tmp_path / "slow-output"),
    )
    assert timed_out["status"] == "failed"
    assert timed_out["error_code"] == "fetch_timeout"

    _enable_fake_ax(monkeypatch, tmp_path)
    oversized = _registry().call(
        "ax_web_extract",
        {
            "operation": "fetch",
            "url": "https://fixture.invalid/large",
            "max_bytes": 8,
        },
        tool_context=_tool_context(tmp_path / "large-output"),
    )
    assert oversized["status"] == "failed"
    assert oversized["error_code"] == "raw_output_oversized"
    assert Path(oversized["raw_output_path"]).is_file()
    oversized_manifest = json.loads(
        Path(oversized["manifest_path"]).read_text(encoding="utf-8")
    )
    assert oversized_manifest["status"] == "failed"
    assert oversized_manifest["error_code"] == "raw_output_oversized"


def test_cross_origin_redirect_persists_failed_raw_evidence(monkeypatch, tmp_path) -> None:
    _enable_fake_ax(monkeypatch, tmp_path, final_url="https://blocked.invalid/private")
    db_path = tmp_path / "redirect-failure.db"
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        result = _registry().call(
            "ax_web_extract",
            {"operation": "fetch", "url": "https://fixture.invalid/page"},
            conn=conn,
            task_id="task_ax_redirect_failure",
            tool_context=_tool_context(tmp_path / "task-output"),
        )
        runs = repos.list_tool_runs(conn, "task_ax_redirect_failure")
    finally:
        conn.close()

    assert result["status"] == "failed"
    assert result["error_code"] == "redirect_not_allowed"
    assert Path(result["raw_output_path"]).is_file()
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["error_code"] == "redirect_not_allowed"
    assert runs[0]["status"] == "failed"
    assert runs[0]["raw_output_path"] == result["raw_output_path"]


@pytest.mark.parametrize(
    "fake_kwargs",
    [
        {"ok_value": 1},
        {"http_status": -1},
    ],
)
def test_fetch_report_requires_real_boolean_and_http_status_range(
    monkeypatch, tmp_path, fake_kwargs
) -> None:
    _enable_fake_ax(monkeypatch, tmp_path, **fake_kwargs)

    result = _registry().call(
        "ax_web_extract",
        {"operation": "fetch", "url": "https://fixture.invalid/page"},
        tool_context=_tool_context(tmp_path / "task-output"),
    )

    assert result["status"] == "failed"
    assert result["error_code"] == "report_invalid"


@pytest.mark.parametrize(
    "invalid_output",
    [
        {"status": "failed"},
        {
            "status": "failed",
            "error_code": "fixture_failure",
            "error_message": "fixture",
            "raw_output_path": "/tmp/unbound-evidence",
        },
        {
            "status": "success",
            "operation": "fetch",
            "run_id": "fixture",
            "ax_version": "0.1.18",
            "ax_binary_sha256": "0" * 64,
            "network_policy_id": "l0-fixture-only",
            "requested_url": "https://fixture.invalid/page",
            "final_url": "https://fixture.invalid/page",
            "http_status": 200,
            "ok": False,
            "redirected": False,
            "fetched_at": "2026-07-21T00:00:00Z",
            "elapsed_ms": 1,
            "byte_count": 1,
            "sha256": "0" * 64,
            "raw_output_path": "/tmp/raw",
            "manifest_path": "/tmp/manifest",
            "truncated": False,
        },
    ],
)
def test_output_schema_rejects_unbound_failures_and_contradictory_success(
    monkeypatch, tmp_path, invalid_output
) -> None:
    from tools_impl.ax_web_extract import adapter as ax_adapter

    monkeypatch.setattr(ax_adapter, "run", lambda payload, context=None: invalid_output)

    with pytest.raises(ToolOutputInvalidError):
        _registry().call(
            "ax_web_extract",
            {"operation": "fetch", "url": "https://fixture.invalid/page"},
            tool_context=_tool_context(tmp_path / "task-output"),
        )


def test_registry_rejects_nonexistent_success_manifest_path(monkeypatch, tmp_path) -> None:
    from tools_impl.ax_web_extract import adapter as ax_adapter

    output_dir = tmp_path / "task-output"
    output_dir.mkdir()
    raw_path = output_dir / "response.body"
    raw_path.write_bytes(b"fixture")
    output = {
        "status": "success",
        "operation": "fetch",
        "run_id": "fixture",
        "ax_version": "0.1.18",
        "ax_binary_sha256": "0" * 64,
        "network_policy_id": "l0-fixture-only",
        "requested_url": "https://fixture.invalid/page",
        "final_url": "https://fixture.invalid/page",
        "http_status": 200,
        "ok": True,
        "redirected": False,
        "fetched_at": "2026-07-21T00:00:00Z",
        "elapsed_ms": 1,
        "byte_count": raw_path.stat().st_size,
        "sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        "raw_output_path": str(raw_path),
        "manifest_path": str(output_dir / "missing-manifest.json"),
        "truncated": False,
    }
    monkeypatch.setattr(ax_adapter, "run", lambda payload, context=None: output)

    with pytest.raises(ToolOutputInvalidError, match="manifest_path"):
        _registry().call(
            "ax_web_extract",
            {"operation": "fetch", "url": "https://fixture.invalid/page"},
            tool_context=_tool_context(output_dir),
        )


def test_operation_contract_rejects_fields_that_would_be_silently_ignored(
    monkeypatch, tmp_path
) -> None:
    _enable_fake_ax(monkeypatch, tmp_path)
    with pytest.raises(ToolInputInvalidError):
        _registry().call(
            "ax_web_extract",
            {
                "operation": "fetch",
                "url": "https://fixture.invalid/page",
                "selector": "article",
            },
            tool_context=_tool_context(tmp_path / "task-output"),
        )


def test_success_persists_raw_output_path_in_tool_run(monkeypatch, tmp_path) -> None:
    _enable_fake_ax(monkeypatch, tmp_path)
    db_path = tmp_path / "ax-tool-run.db"
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        result = _registry().call(
            "ax_web_extract",
            {"operation": "fetch", "url": "https://fixture.invalid/page"},
            conn=conn,
            task_id="task_ax_provenance",
            tool_context=_tool_context(tmp_path / "task-output"),
        )
        runs = repos.list_tool_runs(conn, "task_ax_provenance")
    finally:
        conn.close()

    assert result["status"] == "success"
    assert len(runs) == 1
    assert runs[0]["input"] == {
        "_redacted": True,
        "input_keys": ["operation", "url"],
    }
    assert runs[0]["raw_output_path"] == result["raw_output_path"]


def test_extract_fetches_once_then_parses_the_pinned_local_snapshot(monkeypatch, tmp_path) -> None:
    _enable_fake_ax(monkeypatch, tmp_path)

    result = _registry().call(
        "ax_web_extract",
        {
            "operation": "extract",
            "url": "https://fixture.invalid/page",
            "selector": "article",
            "row": "title=h1",
        },
        task_id="task_ax_extract",
        tool_context=_tool_context(tmp_path / "task-output"),
    )

    assert result["status"] == "success"
    assert result["operation"] == "extract"
    assert result["data"] == [{"title": "Fixture title"}]
    assert result["truncated"] is False
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["operation"] == "extract"
    assert manifest["extraction"] == {
        "selector": "article",
        "row": "title=h1",
        "limit": 25,
        "budget_tokens": 1000,
    }
    assert Path(manifest["extracted_output_path"]).is_file()


def test_discover_normalizes_outline_from_the_pinned_local_snapshot(monkeypatch, tmp_path) -> None:
    _enable_fake_ax(monkeypatch, tmp_path)

    result = _registry().call(
        "ax_web_extract",
        {"operation": "discover", "url": "https://fixture.invalid/page"},
        task_id="task_ax_discover",
        tool_context=_tool_context(tmp_path / "task-output"),
    )

    assert result["status"] == "success"
    assert result["operation"] == "discover"
    assert result["data"] == {
        "mode": "outline",
        "lines": ["3  article.card", "3  article.card > h2"],
    }


def test_discover_with_needle_returns_located_selectors(monkeypatch, tmp_path) -> None:
    _enable_fake_ax(monkeypatch, tmp_path)

    result = _registry().call(
        "ax_web_extract",
        {
            "operation": "discover",
            "url": "https://fixture.invalid/page",
            "needle": "Fixture title",
        },
        task_id="task_ax_locate",
        tool_context=_tool_context(tmp_path / "task-output"),
    )

    assert result["status"] == "success"
    assert result["data"] == {
        "mode": "locate",
        "hits": [{"selector": "article.card > h2", "match": "Fixture title"}],
    }


def test_fetch_and_derive_share_one_total_timeout_budget(monkeypatch, tmp_path) -> None:
    from tools_impl.ax_web_extract import adapter as ax_adapter

    _enable_fake_ax(monkeypatch, tmp_path)
    clock = [100.0]
    observed_timeouts: list[float] = []

    def _deterministic_invoke(binary, args, *, cwd, timeout):
        observed_timeouts.append(timeout)
        if args == ["--version"]:
            clock[0] += 0.4
            return subprocess.CompletedProcess(args, 0, stdout="0.1.18\n", stderr="")
        if "--output" in args:
            clock[0] += 1.1
            raw_path = Path(args[args.index("--output") + 1])
            raw_path.write_bytes(b"<html><body>fixture</body></html>")
            report = {
                "status": 200,
                "ok": True,
                "url": args[0],
                "redirected": False,
                "ms": 7,
                "saved": str(raw_path),
            }
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=json.dumps(report),
                stderr="",
            )
        clock[0] += 0.6
        raise subprocess.TimeoutExpired(args, timeout)

    monkeypatch.setattr(ax_adapter.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(ax_adapter, "_invoke", _deterministic_invoke)

    result = _registry().call(
        "ax_web_extract",
        {
            "operation": "extract",
            "url": "https://fixture.invalid/page",
            "selector": "article",
            "timeout_seconds": 2,
        },
        tool_context=_tool_context(tmp_path / "task-output"),
    )

    assert result["status"] == "failed"
    assert result["error_code"] == "extract_timeout"
    assert observed_timeouts == pytest.approx([2.0, 1.6, 0.5])
    assert Path(result["raw_output_path"]).is_file()


def test_extract_failure_persists_raw_evidence_and_failure_manifest(monkeypatch, tmp_path) -> None:
    _enable_fake_ax(monkeypatch, tmp_path, derive_exit=7, derive_stdout_size=256_001)
    db_path = tmp_path / "extract-failure.db"
    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        result = _registry().call(
            "ax_web_extract",
            {
                "operation": "extract",
                "url": "https://fixture.invalid/page",
                "selector": "article",
            },
            conn=conn,
            task_id="task_ax_extract_failure",
            tool_context=_tool_context(tmp_path / "task-output"),
        )
        runs = repos.list_tool_runs(conn, "task_ax_extract_failure")
    finally:
        conn.close()

    assert result["status"] == "failed"
    assert result["error_code"] == "extract_failed"
    assert Path(result["raw_output_path"]).is_file()
    assert Path(result["extracted_output_path"]).is_file()
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["error_code"] == "extract_failed"
    assert manifest["truncated"] is True
    assert Path(result["extracted_output_path"]).stat().st_size == 256_000
    assert runs[0]["status"] == "failed"
    assert runs[0]["raw_output_path"] == result["raw_output_path"]
