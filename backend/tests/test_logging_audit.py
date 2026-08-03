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
import uuid
from pathlib import Path

from backend.app.logging_setup import audit_event, configure_logging, reset_logging
from backend.app.storage import repos
from backend.app.storage.db import get_conn

from conftest import TEST_DISPLAY_NAME, TEST_USERNAME


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


def test_sample_acknowledgement_audit_fields_are_allowlisted_without_secret_spill(
    tmp_path,
) -> None:
    """sample/case/curation/signer 可对账；误传 token 仍只能记键名。"""
    log_dir = tmp_path / "logs"
    configure_logging(log_dir, process_tag="unit")
    try:
        audit_event(
            "sample_acknowledgement",
            actor="requester",
            outcome="idempotent_replay",
            agent_id="hello_agent",
            sample_id=17,
            case_file="case_004_from_sample.json",
            curation="draft",
            acknowledged_by_username="first_signer",
            token="must-not-leak",
        )
        path = log_dir / "audit.log"
        records = [
            json.loads(line)
            for line in path.read_text("utf-8").splitlines()
            if line.strip()
        ]
        event = [
            record
            for record in records
            if record.get("action") == "sample_acknowledgement"
        ]
        assert len(event) == 1
        assert {key: value for key, value in event[0].items() if key != "ts"} == {
            "action": "sample_acknowledgement",
            "outcome": "idempotent_replay",
            "actor": "requester",
            "agent_id": "hello_agent",
            "sample_id": 17,
            "case_file": "case_004_from_sample.json",
            "curation": "draft",
            "acknowledged_by_username": "first_signer",
        }
        dropped = [
            record
            for record in records
            if record.get("action") == "audit_field_dropped"
        ]
        assert len(dropped) == 1
        assert dropped[0]["dropped_keys"] == ["token"]
        assert "must-not-leak" not in path.read_text("utf-8")
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


# ── 治理签发审计（M12-2c）：人工放行/拒绝是「人是唯一签发者」红线的落点 ──────

def _make_waiting_review_task(app, *, created_by: str) -> str:
    """直接经 repos 把任务驱到 waiting_review（走合法状态机转移，非直插畸形态）。
    agent_id 无外键约束，用固定串即可；review 端点只按状态与身份判定。"""
    task_id = "t-" + uuid.uuid4().hex[:8]
    conn = get_conn(app.state.db_path)
    try:
        repos.create_task(
            conn, task_id=task_id, agent_id="fta_agent", agent_version="0.1.0",
            name="audit-signoff-test", created_by=created_by,
            created_by_username=TEST_USERNAME, inputs={},
        )
        for st in ("queued", "validating", "running", "waiting_review"):
            repos.set_task_status(conn, task_id, st)
        execution_evidence_digest = (
            "sha256:7b9e93d01e34197b15ed6fddaad515525f8745b78d5203966251f6a80ca6ed58"
        )
        for event_type, message in (
            ("validation_started", "开始校验输入"),
            ("review_requested", "任务需要人工审核放行"),
        ):
            payload = {"execution_evidence_digest": execution_evidence_digest}
            if event_type == "validation_started":
                payload = {
                    "package_snapshot_digest": "1" * 64,
                    "task_inputs_digest": "sha256:" + "2" * 64,
                    "input_file_ids": [],
                    "input_files_digest": "sha256:" + "3" * 64,
                    **payload,
                }
            repos.append_event(
                conn,
                task_id=task_id,
                agent_id="fta_agent",
                event_type=event_type,
                level="info",
                message=message,
                payload=payload,
            )
    finally:
        conn.close()
    return task_id


def test_task_approval_is_audited_as_signoff(app_env):
    """批准放行落 audit.log：action=task_review/outcome=approved/actor=唯一 username。
    创建者显示名==签发者显示名 → 近似自审标记 self_review=True。"""
    client, app = app_env
    task_id = _make_waiting_review_task(app, created_by=TEST_DISPLAY_NAME)
    resp = client.post(f"/api/tasks/{task_id}/review", json={"action": "approve"})
    assert resp.status_code == 200, resp.text
    hit = [r for r in _audit_records(app)
           if r.get("action") == "task_review" and r.get("task_id") == task_id]
    assert len(hit) == 1, "每次签发恰一条审计"
    r = hit[0]
    assert r["outcome"] == "approved"
    assert r["actor"] == TEST_USERNAME  # 唯一身份（P2-4）
    assert r["created_by"] == TEST_DISPLAY_NAME
    assert r["self_review"] is True  # is True，不认 truthy


def test_task_rejection_by_owner_is_audited_as_self_review(app_env):
    """V1 owner_signoff 拒绝亦落审计；稳定 username 证明 owner 自签。

    即使 legacy display_name 与当前展示名不一致，也不得推翻稳定 owner 轴。
    reject comment 是用户自由文本，非白名单字段 → 绝不入 audit.log（防注入/secret 回流）。"""
    client, app = app_env
    task_id = _make_waiting_review_task(app, created_by="另一位工程师")
    resp = client.post(
        f"/api/tasks/{task_id}/review", json={"action": "reject", "comment": "不合格-secret-xyz"}
    )
    assert resp.status_code == 200, resp.text
    hit = [r for r in _audit_records(app)
           if r.get("action") == "task_review" and r.get("task_id") == task_id]
    assert len(hit) == 1
    r = hit[0]
    assert r["outcome"] == "rejected"
    assert r["self_review"] is True
    assert r["self_review_basis"] == "username"
    assert r["created_by"] == "另一位工程师"
    audit_text = (Path(app.state.db_path).parent / "logs" / "audit.log").read_text("utf-8")
    assert "不合格-secret-xyz" not in audit_text, "自由文本 comment 绝不入审计轴"
