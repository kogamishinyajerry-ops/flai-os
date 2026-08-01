"""Guide 批量开工的版本钉死与响应丢失完整性回归。"""

from __future__ import annotations

import copy

import pytest
from fastapi import HTTPException

from backend.app.api.tasks import BatchTaskItem, run_batch_creation


def _batch_payload(*, version: str, digest: str, operation_id: str) -> dict:
    return {
        "operation_id": operation_id,
        "pinned_versions": {"hello_agent": version},
        "pinned_package_digests": {"hello_agent": digest},
        "items": [
            {
                "agent_id": "hello_agent",
                "name": "Guide 原子开工",
                "inputs": {"name": "固定输入"},
            }
        ],
    }


def test_guide_batch_rejects_pinned_version_drift_with_zero_writes(app_env):
    """Guide 校验过的版本已漂移时，整批拒绝且不能落一行任务。"""
    client, app = app_env
    snapshot = app.state.agent_registry.package_snapshot("hello_agent")
    assert snapshot is not None
    before = len(client.get("/api/tasks").json())

    response = client.post(
        "/api/tasks/batch",
        json=_batch_payload(
            version="9.9.9",
            digest=snapshot.digest,
            operation_id="guide_batch_version_drift_001",
        ),
    )

    assert response.status_code == 422, response.text
    assert "版本" in response.text
    assert len(client.get("/api/tasks").json()) == before


def test_run_batch_rechecks_all_versions_immediately_before_first_write(app_env):
    """Registry 在静态校验后热切换，写前二次读取必须咬住且整批零写入。"""
    client, app = app_env
    snapshot = app.state.agent_registry.package_snapshot("hello_agent")
    assert snapshot is not None
    current = snapshot.manifest["version"]

    class HotSwapRegistry:
        def __init__(self):
            self.reads = 0

        def get(self, agent_id):
            self.reads += 1
            agent = copy.deepcopy(app.state.agent_registry.get(agent_id))
            if self.reads >= 2:
                agent["version"] = "0.1.1"
            return agent

    before = len(client.get("/api/tasks").json())
    conn = app.state.conn_factory()
    try:
        with pytest.raises(HTTPException) as exc_info:
            run_batch_creation(
                conn=conn,
                agent_registry=HotSwapRegistry(),
                items=[BatchTaskItem(agent_id="hello_agent", inputs={"name": "x"})],
                conversation_id=None,
                created_by="测试工程师",
                created_by_username="test_engineer",
                pinned_versions={"hello_agent": current},
            )
    finally:
        conn.close()

    assert exc_info.value.status_code == 422
    assert "版本" in str(exc_info.value.detail)
    assert len(client.get("/api/tasks").json()) == before


def test_pinned_batch_persists_the_exact_validated_version(app_env):
    client, app = app_env
    snapshot = app.state.agent_registry.package_snapshot("hello_agent")
    assert snapshot is not None
    current = snapshot.manifest["version"]

    response = client.post(
        "/api/tasks/batch",
        json=_batch_payload(
            version=current,
            digest=snapshot.digest,
            operation_id="guide_batch_exact_version_001",
        ),
    )

    assert response.status_code == 200, response.text
    assert response.json()["tasks"][0]["agent_version"] == current


def test_same_operation_id_replays_committed_batch_without_duplicates(app_env):
    """第一次已 COMMIT 但响应丢失时，同 operation_id 重放只能返回原任务。"""
    client, app = app_env
    snapshot = app.state.agent_registry.package_snapshot("hello_agent")
    assert snapshot is not None
    current = snapshot.manifest["version"]
    payload = _batch_payload(
        version=current,
        digest=snapshot.digest,
        operation_id="guide_batch_response_loss_001",
    )

    committed = client.post("/api/tasks/batch", json=payload)
    assert committed.status_code == 200, committed.text
    committed_ids = [task["id"] for task in committed.json()["tasks"]]
    count_after_commit = len(client.get("/api/tasks").json())

    replay = client.post("/api/tasks/batch", json=payload)

    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert [task["id"] for task in replay.json()["tasks"]] == committed_ids
    assert len(client.get("/api/tasks").json()) == count_after_commit


def test_operation_id_reuse_with_different_payload_conflicts(app_env):
    client, app = app_env
    snapshot = app.state.agent_registry.package_snapshot("hello_agent")
    assert snapshot is not None
    current = snapshot.manifest["version"]
    payload = _batch_payload(
        version=current,
        digest=snapshot.digest,
        operation_id="guide_batch_payload_conflict_001",
    )
    committed = client.post("/api/tasks/batch", json=payload)
    assert committed.status_code == 200, committed.text
    count_after_commit = len(client.get("/api/tasks").json())

    changed = copy.deepcopy(payload)
    changed["items"][0]["inputs"]["name"] = "另一个请求"
    conflict = client.post("/api/tasks/batch", json=changed)

    assert conflict.status_code == 409, conflict.text
    assert len(client.get("/api/tasks").json()) == count_after_commit
