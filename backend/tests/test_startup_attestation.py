"""启动期 L1 promotion attestation 的外部行为验收（GH #3）。

测试只穿过真实 ``create_app`` lifespan、活 registry、health 与 audit.log：
不调用 attestation 私有实现，不 mock Registry/SQLite。这样拆掉启动门后，
无 promotion 的 L1 会重新出现在活 registry，测试必须变红。
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from backend.app import config
from backend.app.jobs.runner import _build_default_runner
from backend.app.main import create_app
from backend.app.storage import repos
from backend.app.storage.db import get_conn, init_db


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ID = "startup_attestation_probe"
AGENT_VERSION = "1.2.3"
CONTROL_AGENT_ID = "startup_l0_control"


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
    return app, db_path


def _seed_promotion(db_path: Path, **overrides: object) -> None:
    init_db(db_path)
    values: dict[str, object] = {
        "agent_id": AGENT_ID,
        "agent_version": AGENT_VERSION,
        "from_maturity": "L0",
        "to_maturity": "L1",
        "eval_run_id": "eval-startup-attestation",
        "checks": {
            "transition_supported": {"ok": True},
            "eval_evidence": {"ok": True},
            "manual_confirmation": {"ok": True},
        },
        "confirmations": {"exception_paths_handled": True},
        "confirmed_by": "测试签发人",
    }
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
        assert health["promotion_attestation_ok"] is True
        assert health["promotion_attestation_rejected_count"] == 0
        assert not any(
            record.get("action") == "promotion_attestation"
            and record.get("agent_id") == AGENT_ID
            for record in _audit_records(db_path)
        )


@pytest.mark.parametrize(
    "override",
    [
        {"agent_version": "9.9.9"},
        {"to_maturity": "L0"},
        {"checks": {}},
        {"checks": {"gate": {"ok": 1}}},
        {"checks": {"gate": {"ok": "true"}}},
        {"confirmations": {"exception_paths_handled": 1}},
        {"confirmations": {"exception_paths_handled": "true"}},
        {"confirmed_by": "   "},
    ],
    ids=[
        "wrong-version",
        "wrong-target",
        "empty-checks",
        "integer-check-ok",
        "string-check-ok",
        "integer-confirmation",
        "string-confirmation",
        "blank-signer",
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
                 checks_json, confirmations_json, confirmed_by, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
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

    runner = _build_default_runner()
    runtime = runner._runtime if hasattr(runner, "_runtime") else runner.runtime
    assert runtime.agent_registry.get(AGENT_ID) is None
    assert any(
        AGENT_ID in error["error"] and "promotion" in error["error"]
        for error in runtime.agent_registry.errors
    )
    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute(
            "SELECT id FROM agents WHERE id = ?", (AGENT_ID,)
        ).fetchall() == []
    finally:
        conn.close()
