"""启动期 L1 promotion attestation 的外部行为验收（GH #3）。

测试只穿过真实 ``create_app`` lifespan、活 registry、health 与 audit.log：
不调用 attestation 私有实现，不 mock Registry/SQLite。这样拆掉启动门后，
无 promotion 的 L1 会重新出现在活 registry，测试必须变红。
"""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from fastapi.testclient import TestClient

from backend.app import config
from backend.app.governance.eval_runner import (
    compute_digest,
    freeze_eval_snapshot,
    load_eval_cases,
)
from backend.app.governance.signer_provenance import (
    SERVER_CLI,
    SignerContext,
)
from backend.app.jobs.runner import _build_default_runner
from backend.app.main import create_app
from backend.app.runtime.package_snapshot import (
    SNAPSHOT_CONTRACT,
    capture_agent_package,
)
from backend.app.storage import repos
from backend.app.storage.db import get_conn, init_db


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ID = "startup_attestation_probe"
AGENT_VERSION = "1.2.3"
CONTROL_AGENT_ID = "startup_l0_control"


def _valid_promotion_checks(package_dir: Path) -> dict[str, dict[str, object]]:
    package_snapshot = capture_agent_package(package_dir)
    return {
        "transition_supported": {"ok": True},
        "min_eval_coverage": {"ok": True},
        "eval_evidence": {"ok": True},
        "changelog_nonempty": {"ok": True},
        "feedback_channel": {"ok": True},
        "manual_confirmation": {"ok": True},
        "package_snapshot": {
            "ok": True,
            "contract": SNAPSHOT_CONTRACT,
            "digest": package_snapshot.digest,
            "file_count": package_snapshot.file_count,
        },
    }


def _write_agent(
    agents_dir: Path,
    *,
    agent_id: str = AGENT_ID,
    maturity: str = "L1",
    status: str = "draft",
) -> None:
    """从真实 Golden Sample 复制合法包，只改本测试需要的治理身份字段。"""

    package_dir = agents_dir / agent_id
    shutil.copytree(REPO_ROOT / "agents" / "hello_agent", package_dir)
    yaml_path = package_dir / "agent.yaml"
    manifest = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "id": agent_id,
            "name": "启动签发核对探针",
            "version": AGENT_VERSION,
            "status": status,
            "maturity": maturity,
            "summary": "测试启动期 registry 与 promotions 审计记录是否严格对账。",
        }
    )
    if status in {"trial", "released"}:
        manifest["owner"] = {
            "department": "二所",
            "maintainer": "测试维护人",
            "business_reviewer": "测试审核人",
        }
    yaml_path.write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _make_app(tmp_path: Path, *, include_l0_control: bool = False):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _write_agent(agents_dir)
    if include_l0_control is True:
        _write_agent(agents_dir, agent_id=CONTROL_AGENT_ID, maturity="L0")
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    db_path = tmp_path / "flai_os.db"
    app = _app_from_existing_paths(tmp_path)
    return app, db_path


def _app_from_existing_paths(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    knowledge_dir = tmp_path / "knowledge"
    db_path = tmp_path / "flai_os.db"
    return create_app(
        agents_dir=agents_dir,
        tools_dir=REPO_ROOT / "tools_impl",
        contracts_dir=REPO_ROOT / "contracts",
        knowledge_dir=knowledge_dir,
        db_path=db_path,
        uploads_dir=tmp_path / "uploads",
        task_runs_dir=tmp_path / "task_runs",
        frontend_dist_dir=tmp_path / "frontend-dist",
    )


def _seed_promotion(db_path: Path, **overrides: object) -> None:
    init_db(db_path)
    package_dir = db_path.parent / "agents" / AGENT_ID
    yaml_path = package_dir / "agent.yaml"
    l1_yaml = yaml_path.read_text(encoding="utf-8")
    assert l1_yaml.count("maturity: L1") == 1
    l0_yaml = l1_yaml.replace("maturity: L1", "maturity: L0")
    yaml_path.write_text(l0_yaml, encoding="utf-8")
    try:
        manifest = yaml.safe_load(l0_yaml)
        approved, _drafts, broken = load_eval_cases(package_dir)
        assert broken == []
        digest = compute_digest(approved, package_dir, manifest)
        assert digest is not None
        fixture_registry = SimpleNamespace(
            get=lambda requested_id: manifest if requested_id == AGENT_ID else None,
            package_dir=lambda _requested_id: package_dir,
        )
        conn = get_conn(db_path)
        try:
            snapshot_handle = freeze_eval_snapshot(
                conn,
                agent_registry=fixture_registry,
                agent_id=AGENT_ID,
            )
        finally:
            conn.close()
    finally:
        # 模拟真实提交：eval 对 L0 取证，promotion 随后只把 maturity 行写成 L1。
        yaml_path.write_text(l1_yaml, encoding="utf-8")
    conn = get_conn(db_path)
    try:
        repos.create_eval_run(
            conn,
            run_id="eval-startup-attestation",
            agent_id=AGENT_ID,
            agent_version=AGENT_VERSION,
            triggered_by="测试签发人",
            snapshot_handle=snapshot_handle,
        )
        repos.finish_eval_run(
            conn,
            "eval-startup-attestation",
            status="completed",
            total=len(approved),
            passed=len(approved),
            failed=0,
            skipped=0,
            case_results=[
                {
                    "case_file": case["_file"],
                    "verdict": "passed",
                    "detail": "fixture 全绿",
                }
                for case in approved
            ],
            draft_cases=[],
            eval_cases_digest=digest,
        )
    finally:
        conn.close()
    values: dict[str, object] = {
        "agent_id": AGENT_ID,
        "agent_version": AGENT_VERSION,
        "from_maturity": "L0",
        "to_maturity": "L1",
        "eval_run_id": "eval-startup-attestation",
        "checks": _valid_promotion_checks(package_dir),
        "confirmations": {"exception_paths_handled": True},
        "signer": SignerContext.from_server_cli("测试签发人"),
    }
    if "confirmed_by" in overrides:
        values["signer"] = SignerContext.from_server_cli(
            str(overrides.pop("confirmed_by"))
        )
    values.update(overrides)
    conn = get_conn(db_path)
    try:
        repos.record_promotion(conn, **values)
        conn.commit()
    finally:
        conn.close()


def _audit_records(db_path: Path) -> list[dict]:
    audit_path = db_path.parent / "logs" / "audit.log"
    if audit_path.exists() is not True:
        return []
    return [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_l1_without_promotion_is_not_published_and_is_loud(tmp_path: Path) -> None:
    app, db_path = _make_app(tmp_path)

    with TestClient(app) as client:
        assert app.state.agent_registry.get(AGENT_ID) is None
        assert any(
            AGENT_ID in error["error"] and "promotion" in error["error"]
            for error in app.state.agent_registry.errors
        )

        conn = sqlite3.connect(db_path)
        try:
            projected = conn.execute(
                "SELECT id FROM agents WHERE id = ?", (AGENT_ID,)
            ).fetchall()
        finally:
            conn.close()
        assert projected == [], "attestation 必须先于 sync_to_db，首次投影不能写入漂移 L1"

        health = client.get("/api/health").json()
        assert health["promotion_attestation_axis"] is True
        assert health["promotion_attestation_ok"] is False
        assert health["promotion_attestation_rejected_count"] == 1

        rejected = [
            record
            for record in _audit_records(db_path)
            if record.get("action") == "promotion_attestation"
            and record.get("outcome") == "rejected"
            and record.get("agent_id") == AGENT_ID
        ]
        assert len(rejected) == 1
        assert rejected[0]["agent_version"] == AGENT_VERSION
        assert rejected[0]["maturity"] == "L1"


def test_l1_with_exact_promotion_is_published(tmp_path: Path) -> None:
    app, db_path = _make_app(tmp_path)
    _seed_promotion(db_path)

    with TestClient(app) as client:
        registered = app.state.agent_registry.get(AGENT_ID)
        assert registered is not None
        assert registered["maturity"] == "L1"

        health = client.get("/api/health").json()
        assert health["promotion_attestation_axis"] is True
        assert health["promotion_signer_provenance_generation"] == (
            config.PROMOTION_SIGNER_PROVENANCE_GENERATION
        )
        assert health["promotion_attestation_ok"] is True
        assert health["promotion_attestation_rejected_count"] == 0
        assert not any(
            record.get("action") == "promotion_attestation"
            and record.get("agent_id") == AGENT_ID
            for record in _audit_records(db_path)
        )


def test_legacy_promotion_is_readable_but_cannot_attest_l1(tmp_path: Path) -> None:
    """迁移后的历史行保留审计可读性，但绝不冒充有认证来源的启动证明。"""
    app, db_path = _make_app(tmp_path)
    _seed_promotion(db_path)
    conn = get_conn(db_path)
    try:
        conn.execute(
            "UPDATE promotions SET signer_source = 'legacy_unverified',"
            " signer_user_id = NULL, signer_username = NULL,"
            " signer_session_hash = NULL"
        )
        readable = repos.list_promotions(conn, AGENT_ID)
        assert readable[0]["confirmed_by"] == "测试签发人"
        assert readable[0]["signer_source"] == "legacy_unverified"
    finally:
        conn.close()

    with TestClient(app) as client:
        assert app.state.agent_registry.get(AGENT_ID) is None
        health = client.get("/api/health").json()
        assert health["promotion_attestation_ok"] is False
        assert health["promotion_attestation_rejected_count"] == 1


@pytest.mark.parametrize(
    "mutation",
    ["missing-workflow", "workflow-symlink"],
)
def test_restarted_invalid_promoted_package_is_rejected_and_health_red(
    tmp_path: Path, mutation: str
) -> None:
    app, db_path = _make_app(tmp_path)
    _seed_promotion(db_path)
    with TestClient(app) as client:
        assert app.state.agent_registry.get(AGENT_ID) is not None
        assert client.get("/api/health").json()["promotion_attestation_ok"] is True

    workflow_path = tmp_path / "agents" / AGENT_ID / "workflow.py"
    workflow_path.unlink()
    if mutation == "workflow-symlink":
        outside = tmp_path / "outside-workflow.py"
        outside.write_text(
            "def run(context):\n"
            "    return {'status': 'success', 'outputs': ['outside']}\n",
            encoding="utf-8",
        )
        try:
            workflow_path.symlink_to(outside)
        except (NotImplementedError, OSError) as exc:
            pytest.skip(f"当前平台不能创建 symlink：{exc}")

    restarted = _app_from_existing_paths(tmp_path)
    with TestClient(restarted) as client:
        assert restarted.state.agent_registry.get(AGENT_ID) is None
        health = client.get("/api/health").json()
        assert health["promotion_attestation_ok"] is False
        assert health["promotion_attestation_rejected_count"] == 1

    rejected = [
        record
        for record in _audit_records(db_path)
        if record.get("action") == "promotion_attestation"
        and record.get("outcome") == "rejected"
        and record.get("agent_id") == AGENT_ID
        and record.get("reason") == "missing-or-invalid-package-snapshot"
    ]
    assert len(rejected) == 1


def test_health_reads_attestation_records_from_one_snapshot(tmp_path: Path) -> None:
    """health 的 ok/count 必须来自同一次列表快照，不能两次 len 撕裂。"""

    app, _db_path = _make_app(tmp_path)

    class _ChangingLengthList(list):
        calls = 0

        def __len__(self) -> int:
            self.calls += 1
            return 0 if self.calls == 1 else 1

    with TestClient(app) as client:
        records = _ChangingLengthList()
        app.state.promotion_attestation_records = records
        health = client.get("/api/health").json()

    assert records.calls == 1
    assert health["promotion_attestation_ok"] is True
    assert health["promotion_attestation_rejected_count"] == 0


@pytest.mark.parametrize(
    "override",
    [
        {"agent_version": "9.9.9"},
        {"from_maturity": "L1"},
        {"to_maturity": "L0"},
        {"checks": {}},
        {"checks": {"anything": {"ok": True}}},
        {"eval_run_id": ""},
        {"eval_run_id": "missing-eval"},
        {"confirmations": {"exception_paths_handled": 1}},
        {"confirmations": {"exception_paths_handled": "true"}},
    ],
    ids=[
        "wrong-version",
        "wrong-source",
        "wrong-target",
        "empty-checks",
        "invented-check",
        "blank-eval-reference",
        "missing-eval-reference",
        "integer-confirmation",
        "string-confirmation",
    ],
)
def test_only_strict_promotion_fields_attest(
    tmp_path: Path, override: dict[str, object]
) -> None:
    app, db_path = _make_app(tmp_path)
    _seed_promotion(db_path, **override)

    with TestClient(app) as client:
        assert app.state.agent_registry.get(AGENT_ID) is None
        health = client.get("/api/health").json()
        assert health["promotion_attestation_ok"] is False
        assert health["promotion_attestation_rejected_count"] == 1


@pytest.mark.parametrize(
    "updates",
    [
        {"confirmed_by": "   "},
        {"signer_source": "unknown_source"},
        {
            "signer_source": "authenticated_session",
            "signer_user_id": None,
            "signer_username": "engineer",
            "signer_session_hash": "0" * 64,
        },
        {
            "signer_source": "authenticated_session",
            "signer_user_id": 0,
            "signer_username": "engineer",
            "signer_session_hash": "0" * 64,
        },
        {
            "signer_source": "authenticated_session",
            "signer_user_id": 1,
            "signer_username": " ",
            "signer_session_hash": "0" * 64,
        },
        {
            "signer_source": "authenticated_session",
            "signer_user_id": 1,
            "signer_username": "engineer",
            "signer_session_hash": "NOT-A-SHA256",
        },
        {
            "signer_source": "server_cli",
            "signer_user_id": 1,
            "signer_username": None,
            "signer_session_hash": None,
        },
        {"signer_source": "legacy_unverified"},
    ],
    ids=[
        "blank-display",
        "unknown-source",
        "auth-missing-user-id",
        "auth-nonpositive-user-id",
        "auth-blank-username",
        "auth-invalid-hash",
        "cli-mixed-auth-fields",
        "legacy-unverified",
    ],
)
def test_malformed_signer_provenance_cannot_attest_l1(
    tmp_path: Path,
    updates: dict[str, object],
) -> None:
    app, db_path = _make_app(tmp_path)
    _seed_promotion(db_path)
    conn = get_conn(db_path)
    try:
        assignments = ", ".join(f"{column} = ?" for column in updates)
        conn.execute(
            f"UPDATE promotions SET {assignments}",
            tuple(updates.values()),
        )
    finally:
        conn.close()

    with TestClient(app) as client:
        assert app.state.agent_registry.get(AGENT_ID) is None
        health = client.get("/api/health").json()
        assert health["promotion_attestation_ok"] is False
        assert health["promotion_attestation_rejected_count"] == 1


@pytest.mark.parametrize("truthy_ok", [1, "true"], ids=["integer", "string"])
def test_each_promotion_check_ok_requires_literal_boolean_true(
    tmp_path: Path, truthy_ok: object
) -> None:
    """完整合法 checks 只污染一个 ok；拒绝必须由 strict bool 本身咬住。"""

    app, db_path = _make_app(tmp_path)
    checks: dict[str, dict[str, object]] = _valid_promotion_checks(
        tmp_path / "agents" / AGENT_ID
    )
    checks["eval_evidence"]["ok"] = truthy_ok
    _seed_promotion(db_path, checks=checks)

    with TestClient(app) as client:
        assert app.state.agent_registry.get(AGENT_ID) is None
        health = client.get("/api/health").json()
        assert health["promotion_attestation_ok"] is False
        assert health["promotion_attestation_rejected_count"] == 1


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("agent_id", "different-agent"),
        ("agent_version", "9.9.9"),
        ("status", "error"),
        ("total", 0),
        ("passed", 0),
        ("failed", 1),
        ("skipped", 1),
        ("eval_cases_digest", "tampered-digest"),
    ],
    ids=[
        "different-agent",
        "different-version",
        "not-completed",
        "empty-run",
        "incomplete-pass-count",
        "failed-case",
        "skipped-case",
        "stale-package-digest",
    ],
)
def test_referenced_eval_must_be_matching_green_evidence(
    tmp_path: Path, column: str, value: object
) -> None:
    app, db_path = _make_app(tmp_path)
    _seed_promotion(db_path)
    conn = get_conn(db_path)
    try:
        assert column in {
            "agent_id",
            "agent_version",
            "status",
            "total",
            "passed",
            "failed",
            "skipped",
            "eval_cases_digest",
        }
        conn.execute(
            f"UPDATE eval_runs SET {column} = ? WHERE id = ?",
            (value, "eval-startup-attestation"),
        )
        conn.commit()
    finally:
        conn.close()

    with TestClient(app) as client:
        assert app.state.agent_registry.get(AGENT_ID) is None
        health = client.get("/api/health").json()
        assert health["promotion_attestation_ok"] is False
        assert health["promotion_attestation_rejected_count"] == 1


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-handle",
        "missing-row",
        "digest-mismatch",
        "content-tamper",
        "payload-byte-tamper-rehashed",
    ],
)
def test_referenced_eval_requires_immutable_snapshot_binding(
    tmp_path: Path, mutation: str
) -> None:
    app, db_path = _make_app(tmp_path)
    _seed_promotion(db_path)
    conn = get_conn(db_path)
    try:
        if mutation == "missing-handle":
            conn.execute(
                "UPDATE eval_runs SET snapshot_handle = NULL WHERE id = ?",
                ("eval-startup-attestation",),
            )
        elif mutation == "missing-row":
            conn.execute(
                "UPDATE eval_runs SET snapshot_handle = ? WHERE id = ?",
                ("snap_missing", "eval-startup-attestation"),
            )
        elif mutation == "digest-mismatch":
            conn.execute(
                "UPDATE eval_snapshots SET eval_cases_digest = ?",
                ("tampered-digest",),
            )
        elif mutation == "content-tamper":
            conn.execute(
                "UPDATE eval_snapshots SET content_json = content_json || ' '"
            )
        else:
            snapshot = conn.execute(
                "SELECT * FROM eval_snapshots"
            ).fetchone()
            assert snapshot is not None
            content = json.loads(snapshot["content_json"])
            content["files"]["prompt.md"] = base64.b64encode(
                b"tampered snapshot prompt"
            ).decode("ascii")
            content_json = json.dumps(
                content, ensure_ascii=False, sort_keys=True
            )
            handle = (
                "snap_"
                + hashlib.sha256(content_json.encode("utf-8")).hexdigest()
            )
            conn.execute(
                """
                INSERT INTO eval_snapshots
                    (handle, agent_id, agent_version, eval_cases_digest,
                     content_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    handle,
                    snapshot["agent_id"],
                    snapshot["agent_version"],
                    snapshot["eval_cases_digest"],
                    content_json,
                    snapshot["created_at"],
                ),
            )
            conn.execute(
                "UPDATE eval_runs SET snapshot_handle = ? WHERE id = ?",
                (handle, "eval-startup-attestation"),
            )
        conn.commit()
    finally:
        conn.close()

    with TestClient(app) as client:
        assert app.state.agent_registry.get(AGENT_ID) is None
        health = client.get("/api/health").json()
        assert health["promotion_attestation_ok"] is False
        assert health["promotion_attestation_rejected_count"] == 1


@pytest.mark.parametrize(
    "case_results",
    [
        [],
        [{"case_file": "case_001.json", "verdict": "passed"}],
        [
            {"case_file": "case_001.json", "verdict": "failed"},
            {"case_file": "case_002.json", "verdict": "passed"},
            {"case_file": "case_003.json", "verdict": "passed"},
        ],
        [
            {"case_file": "case_001.json", "verdict": "passed"},
            {"case_file": "case_001.json", "verdict": "passed"},
            {"case_file": "case_001.json", "verdict": "passed"},
        ],
    ],
    ids=[
        "empty",
        "shorter-than-total",
        "verdict-count-mismatch",
        "duplicate-case-files",
    ],
)
def test_referenced_eval_case_results_must_match_all_four_counts(
    tmp_path: Path, case_results: list[dict[str, object]]
) -> None:
    app, db_path = _make_app(tmp_path)
    _seed_promotion(db_path)
    conn = get_conn(db_path)
    try:
        conn.execute(
            "UPDATE eval_runs SET case_results_json = ? WHERE id = ?",
            (
                json.dumps(case_results, ensure_ascii=False),
                "eval-startup-attestation",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    with TestClient(app) as client:
        assert app.state.agent_registry.get(AGENT_ID) is None
        health = client.get("/api/health").json()
        assert health["promotion_attestation_ok"] is False
        assert health["promotion_attestation_rejected_count"] == 1


@pytest.mark.parametrize(
    "mutation",
    [
        "malformed-snapshot-time",
        "naive-snapshot-time",
        "snapshot-after-run-start",
        "run-finished-before-start",
        "promotion-before-run-finished",
    ],
)
def test_promotion_attestation_requires_strict_evidence_timeline(
    tmp_path: Path, mutation: str
) -> None:
    app, db_path = _make_app(tmp_path)
    _seed_promotion(db_path)
    conn = get_conn(db_path)
    try:
        if mutation == "malformed-snapshot-time":
            conn.execute("UPDATE eval_snapshots SET created_at = 'not-a-time'")
        elif mutation == "naive-snapshot-time":
            conn.execute(
                "UPDATE eval_snapshots SET created_at = '2026-07-26T12:00:00'"
            )
        elif mutation == "snapshot-after-run-start":
            conn.execute(
                "UPDATE eval_snapshots SET created_at = '2099-01-01T00:00:00+00:00'"
            )
        elif mutation == "run-finished-before-start":
            conn.execute(
                "UPDATE eval_runs SET finished_at = '2000-01-01T00:00:00+00:00' "
                "WHERE id = ?",
                ("eval-startup-attestation",),
            )
        else:
            conn.execute(
                "UPDATE promotions SET created_at = '2000-01-01T00:00:00+00:00'"
            )
        conn.commit()
    finally:
        conn.close()

    with TestClient(app) as client:
        assert app.state.agent_registry.get(AGENT_ID) is None
        health = client.get("/api/health").json()
        assert health["promotion_attestation_ok"] is False
        assert health["promotion_attestation_rejected_count"] == 1


@pytest.mark.parametrize(
    "checks_json",
    ["{", ("[" * 10000) + ("]" * 10000)],
    ids=["syntax-error", "excessive-nesting"],
)
def test_malformed_promotion_json_isolates_only_the_l1(
    tmp_path: Path, checks_json: str
) -> None:
    app, db_path = _make_app(tmp_path, include_l0_control=True)
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        conn.execute(
            """
            INSERT INTO promotions
                (agent_id, agent_version, from_maturity, to_maturity, eval_run_id,
                 checks_json, confirmations_json, confirmed_by, signer_source,
                 signer_user_id, signer_username, signer_session_hash, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                AGENT_ID,
                AGENT_VERSION,
                "L0",
                "L1",
                "eval-malformed",
                checks_json,
                '{"exception_paths_handled": true}',
                "测试签发人",
                "server_cli",
                None,
                None,
                None,
                "2026-07-26T00:00:00+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    with TestClient(app) as client:
        assert app.state.agent_registry.get(AGENT_ID) is None
        assert app.state.agent_registry.get(CONTROL_AGENT_ID) is not None
        health = client.get("/api/health").json()
        assert health["promotion_attestation_ok"] is False
        assert health["promotion_attestation_rejected_count"] == 1


def test_status_trial_is_not_the_l1_maturity_axis(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _write_agent(
        agents_dir,
        agent_id=CONTROL_AGENT_ID,
        maturity="L0",
        status="trial",
    )
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    db_path = tmp_path / "flai_os.db"
    app = create_app(
        agents_dir=agents_dir,
        tools_dir=REPO_ROOT / "tools_impl",
        contracts_dir=REPO_ROOT / "contracts",
        knowledge_dir=knowledge_dir,
        db_path=db_path,
        uploads_dir=tmp_path / "uploads",
        task_runs_dir=tmp_path / "task_runs",
        frontend_dist_dir=tmp_path / "frontend-dist",
    )

    with TestClient(app) as client:
        assert app.state.agent_registry.get(CONTROL_AGENT_ID) is not None
        assert client.get("/api/health").json()["promotion_attestation_ok"] is True


def test_worker_uses_the_same_startup_attestation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _write_agent(agents_dir)
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    db_path = tmp_path / "data" / "flai_os.db"
    monkeypatch.setattr(config, "AGENTS_DIR", agents_dir)
    monkeypatch.setattr(config, "TOOLS_DIR", REPO_ROOT / "tools_impl")
    monkeypatch.setattr(config, "CONTRACTS_DIR", REPO_ROOT / "contracts")
    monkeypatch.setattr(config, "KNOWLEDGE_DIR", knowledge_dir)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "UPLOADS_DIR", tmp_path / "data" / "uploads")
    monkeypatch.setattr(config, "TASK_RUNS_DIR", tmp_path / "data" / "task_runs")
    monkeypatch.setattr(config, "DB_PATH", db_path)
    db_path.parent.mkdir(parents=True)

    from backend.app.jobs.runner import run_worker_forever

    eval_poller_started = False

    def _unexpected_eval_poller():
        nonlocal eval_poller_started
        eval_poller_started = True
        raise AssertionError("attestation 拒载后不得启动 eval poller")

    with pytest.raises(RuntimeError, match="promotion attestation"):
        run_worker_forever(
            _build_default_runner,
            lambda: get_conn(db_path),
            tmp_path / "data" / "worker.lock",
            eval_runner_factory=_unexpected_eval_poller,
        )

    assert eval_poller_started is False
    conn = get_conn(db_path)
    try:
        assert conn.execute(
            "SELECT id FROM agents WHERE id = ?", (AGENT_ID,)
        ).fetchall() == []
        heartbeat = repos.get_worker_heartbeat(conn)
    finally:
        conn.close()
    assert heartbeat is not None
    assert json.loads(heartbeat["detail"]) == {
        "promotion_attestation_axis": True,
        "promotion_attestation_ok": False,
        "promotion_attestation_rejected_count": 1,
    }


def test_worker_clean_assembly_writes_strict_green_attestation_heartbeat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _write_agent(agents_dir, maturity="L0")
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    db_path = tmp_path / "data" / "flai_os.db"
    monkeypatch.setattr(config, "AGENTS_DIR", agents_dir)
    monkeypatch.setattr(config, "TOOLS_DIR", REPO_ROOT / "tools_impl")
    monkeypatch.setattr(config, "CONTRACTS_DIR", REPO_ROOT / "contracts")
    monkeypatch.setattr(config, "KNOWLEDGE_DIR", knowledge_dir)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "UPLOADS_DIR", tmp_path / "data" / "uploads")
    monkeypatch.setattr(config, "TASK_RUNS_DIR", tmp_path / "data" / "task_runs")
    monkeypatch.setattr(config, "DB_PATH", db_path)

    runner = _build_default_runner()
    runner.beat()

    conn = get_conn(db_path)
    try:
        heartbeat = repos.get_worker_heartbeat(conn)
    finally:
        conn.close()
    assert heartbeat is not None
    assert json.loads(heartbeat["detail"]) == {
        "promotion_attestation_axis": True,
        "promotion_attestation_ok": True,
        "promotion_attestation_rejected_count": 0,
    }


def test_worker_refuses_persistent_cross_process_promotion_fault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _write_agent(agents_dir, maturity="L0")
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    db_path = tmp_path / "data" / "flai_os.db"
    monkeypatch.setattr(config, "AGENTS_DIR", agents_dir)
    monkeypatch.setattr(config, "TOOLS_DIR", REPO_ROOT / "tools_impl")
    monkeypatch.setattr(config, "CONTRACTS_DIR", REPO_ROOT / "contracts")
    monkeypatch.setattr(config, "KNOWLEDGE_DIR", knowledge_dir)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "UPLOADS_DIR", tmp_path / "data" / "uploads")
    monkeypatch.setattr(config, "TASK_RUNS_DIR", tmp_path / "data" / "task_runs")
    monkeypatch.setattr(config, "DB_PATH", db_path)
    db_path.parent.mkdir(parents=True)
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        repos.record_promotion_attestation_fault(
            conn,
            detail='{"reason":"promotion-rollback-failed"}',
        )
    finally:
        conn.close()

    with pytest.raises(RuntimeError, match="promotion attestation"):
        _build_default_runner()

    conn = get_conn(db_path)
    try:
        heartbeat = repos.get_worker_heartbeat(conn)
    finally:
        conn.close()
    assert heartbeat is not None
    assert json.loads(heartbeat["detail"])[
        "promotion_attestation_ok"
    ] is False


def test_official_promotion_cli_forwards_startup_attestation_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """官方直连 CLI 必须把同次 assemble 的 sticky 拒载记录传入晋升门。"""

    import httpx

    from backend.app import bootstrap
    from backend.app.governance import eval_runner, promotion
    from backend.app.runtime import runtime as runtime_module
    from backend.app.storage import db as db_module
    from scripts import promote_agent_l1

    attestation_records = [
        {
            "agent_id": "drifted_l1",
            "agent_version": "1.0.0",
            "maturity": "L1",
            "reason": "缺少可核验 promotion",
        }
    ]
    assembly = SimpleNamespace(
        agent_registry=object(),
        tool_registry=object(),
        model_gateway=object(),
        knowledge_service=object(),
        scope_registry=object(),
        promotion_attestation_records=attestation_records,
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(sys, "argv", ["promote_agent_l1.py", AGENT_ID, "测试签发人"])
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: SimpleNamespace(status_code=401, text=""),
    )
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "flai_os.db")
    monkeypatch.setattr(db_module, "init_db", lambda _path: None)
    monkeypatch.setattr(db_module, "get_conn", lambda _path: object())
    monkeypatch.setattr(bootstrap, "assemble", lambda **_kwargs: assembly)
    monkeypatch.setattr(
        runtime_module,
        "AgentRuntime",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        eval_runner,
        "run_agent_evals",
        lambda **_kwargs: {
            "id": "eval-cli-attestation",
            "status": "completed",
            "total": 1,
            "passed": 1,
            "failed": 0,
            "skipped": 0,
            "case_results": [],
        },
    )

    def _capture_promotion(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "id": 7,
            "from_maturity": "L0",
            "to_maturity": "L1",
            "eval_run_id": "eval-cli-attestation",
        }

    monkeypatch.setattr(promotion, "promote_agent", _capture_promotion)

    assert promote_agent_l1.main() == 0
    assert captured["attestation_records"] is attestation_records
    signer = captured["signer"]
    assert isinstance(signer, SignerContext)
    assert signer.source == SERVER_CLI
    assert signer.operator_label == "测试签发人"
    assert signer.authenticated_session is None
    assert "confirmed_by" not in captured
