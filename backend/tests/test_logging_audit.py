"""进程日志基建 + 认证/访问审计留痕（ADR-0023 + Codex R0 P1-3/P3-3 硬化）。

验收：审计事件以 **JSON Lines** 落 audit.log（注入安全）、字段白名单（drop 非白名单）、
业务 logger 落进程日志、logging_setup 纯 stdlib。tamper（删 download 403 的
audit_event → 断言 FAIL）在 review-record 记手工见证。

日志路径派生 app.state.db_path.parent/logs（ADR-0023 D3）——测试 db 在 tmp，
故 audit.log 天然 per-test 隔离。app_env 的 seed_and_login 已产生一次登录成功
事件，故 audit.log 在测试起点即非空。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from backend.app.logging_setup import audit_event, configure_logging, reset_logging

from conftest import TEST_USERNAME


def _audit_records(app) -> list[dict]:
    """解析 audit.log 的 JSON Lines 为结构化记录（P3-3：解析单条记录而非子串搜索）。"""
    path = Path(app.state.db_path).parent / "logs" / "audit.log"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def _upload(client, *, classification: str):
    return client.post(
        "/api/files/upload",
        files={"file": ("secret.txt", b"payload", "text/plain")},
        data={"classification": classification},
    )


def test_logging_setup_is_stdlib_only_and_writes(tmp_path):
    """纯 stdlib 单元：configure_logging 独立于 app 即可把审计/业务日志落文件；
    JSON Lines 格式 + 白名单 drop（非白名单字段不落库，只留一条 dropped 告警）。"""
    log_dir = tmp_path / "logs"
    configure_logging(log_dir, process_tag="unit")
    try:
        # reason 在白名单、secret 不在——secret 必被 drop（绝不记 secret 由构造保证）。
        audit_event("probe", actor="tester", outcome="ok", reason="unit", secret="password123")
        logging.getLogger("backend.app.demo").info("hello-app-log")

        audit_path = log_dir / "audit.log"
        app_log = log_dir / "flai-os-unit.log"
        assert audit_path.exists() is True
        records = [json.loads(l) for l in audit_path.read_text("utf-8").splitlines() if l.strip()]
        probe = [r for r in records if r.get("action") == "probe"]
        assert len(probe) == 1
        assert {k: v for k, v in probe[0].items() if k != "ts"} == {
            "action": "probe", "outcome": "ok", "actor": "tester", "reason": "unit"
        }
        assert "ts" in probe[0]  # 自含时间戳（audit.log 是自足 JSONL）
        # 非白名单 secret 及其值绝不落库（键值都不在任何记录里）。
        assert "password123" not in audit_path.read_text("utf-8")
        assert "secret" not in probe[0]
        # drop 告警只记键名不记值。
        dropped = [r for r in records if r.get("action") == "audit_field_dropped"]
        assert len(dropped) == 1 and dropped[0]["dropped_keys"] == ["secret"]
        # 业务 logger 的 INFO 经 root 落进程日志（此前无 root 配置=全丢弃）。
        assert app_log.exists() is True
        assert "hello-app-log" in app_log.read_text("utf-8")
    finally:
        reset_logging()


def test_audit_event_is_injection_safe(tmp_path):
    """P1-3：actor 含 CR/LF/空格/`=` 不能伪造额外审计行（日志注入）。JSON Lines
    把换行转义在字符串内，单条记录恒单行；伪造内容不产生第二条可解析的假记录。"""
    log_dir = tmp_path / "logs"
    configure_logging(log_dir, process_tag="unit")
    try:
        forged = 'attacker\naction=login outcome=success actor=admin'
        audit_event("login", actor=forged, outcome="failure", reason="bad-credentials")
        records = [
            json.loads(l)
            for l in (log_dir / "audit.log").read_text("utf-8").splitlines() if l.strip()
        ]
        logins = [r for r in records if r.get("action") == "login"]
        assert len(logins) == 1  # 恰一条，注入没造出第二条
        assert logins[0]["actor"] == forged  # 换行原样保存在 JSON 字符串内
        assert logins[0]["outcome"] == "failure"
        # 绝无 actor=admin 的伪造成功记录
        assert not any(r.get("outcome") == "success" and r.get("actor") == "admin" for r in records)
    finally:
        reset_logging()


def test_login_success_is_audited(app_env):
    _client, app = app_env
    records = _audit_records(app)  # fixture 已登录一次
    assert any(
        r["action"] == "login" and r["outcome"] == "success" and r["actor"] == TEST_USERNAME
        for r in records
    )


def test_login_failure_is_audited(app_env):
    client, app = app_env
    resp = client.post("/api/auth/login", json={"username": TEST_USERNAME, "password": "wrong-pw"})
    assert resp.status_code == 401
    records = _audit_records(app)
    assert any(
        r["action"] == "login" and r["outcome"] == "failure" and r.get("reason") == "bad-credentials"
        for r in records
    )
    # 绝不记密码明文（ADR-0023 D6）——JSON 里任何字段都不含它。
    audit_text = (Path(app.state.db_path).parent / "logs" / "audit.log").read_text("utf-8")
    assert "wrong-pw" not in audit_text


def test_sensitive_download_denied_is_audited(app_env):
    client, app = app_env
    file_id = _upload(client, classification="sensitive").json()["id"]
    download = client.get(f"/api/files/{file_id}/download")
    assert download.status_code == 403
    records = _audit_records(app)
    hit = [
        r for r in records
        if r.get("action") == "sensitive_download_denied" and r.get("file_id") == file_id
    ]
    assert len(hit) >= 1
    assert hit[0]["classification"] == "sensitive"
    # actor 是唯一 username（P2-4），display_name 作附加字段。
    assert hit[0]["actor"] == TEST_USERNAME
    assert "display_name" in hit[0]


def test_internal_download_is_not_audited_as_denied(app_env):
    """internal 文件正常下载不产生 denied 审计（避免假阳性淹没真信号）。"""
    client, app = app_env
    file_id = _upload(client, classification="internal").json()["id"]
    download = client.get(f"/api/files/{file_id}/download")
    assert download.status_code == 200
    records = _audit_records(app)
    assert not any(
        r.get("action") == "sensitive_download_denied" and r.get("file_id") == file_id
        for r in records
    )
