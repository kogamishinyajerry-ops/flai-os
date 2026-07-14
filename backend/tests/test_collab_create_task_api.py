"""协作运行时 create_task API（§3.5）：depends_on 校验 + 条件短路。

- T7 命门：depends_on 非空 → 任务滞留 created（不自动入队），resolver 才看得到。
- T4：depends_on 引用不存在任务 → 404 fail-closed（DAG-by-construction）。
- T6-create：input_binding 引用 depends_on 之外任务 → 422（越权拒）。
- 控制组：无 depends_on → 照常 P2-4 原子 created→queued（短路不破常规路径）。
"""

from __future__ import annotations


def _mk(client, name, **extra):
    body = {"agent_id": "hello_agent", "name": name, "inputs": {"name": name}}
    body.update(extra)
    return client.post("/api/tasks", json=body)


def test_no_dependency_task_still_auto_enqueues(app_env):
    client, _ = app_env
    r = _mk(client, "solo")
    assert r.status_code == 200
    assert r.json()["status"] == "queued"  # P2-4 原子入队保持


def test_T7_dependent_task_stays_created(app_env):
    client, _ = app_env
    up = _mk(client, "up").json()
    r = _mk(client, "down", depends_on=[up["id"]])
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "created"  # 滞留 created，不自动入队
    assert body["depends_on"] == [up["id"]]


def test_T4_nonexistent_dependency_rejected(app_env):
    client, _ = app_env
    r = _mk(client, "orphan", depends_on=["task_does_not_exist"])
    assert r.status_code == 404  # DAG-by-construction：只能依赖已存在任务


def test_T6_create_input_binding_stray_reference_rejected(app_env):
    client, _ = app_env
    up = _mk(client, "up").json()
    other = _mk(client, "other").json()
    # input_binding 引用 other，但 depends_on 只含 up → 越权，拒
    r = _mk(
        client, "down",
        depends_on=[up["id"]],
        input_binding={"from_tasks": [other["id"]]},
    )
    assert r.status_code == 422


def test_output_file_cannot_be_directly_referenced_as_input(app_env):
    """安全边界 tamper：kind=output 产物经 create_task 直引 → 422。

    与 _open_input_files 的 task_runs_dir 放宽配对：outputs 唯一入口是 resolver 管道，
    直引旁路必拒，否则放宽即沦为直读任意任务产物。"""
    import uuid
    from backend.app.storage import repos
    client, app = app_env
    up = _mk(client, "up").json()
    conn = app.state.conn_factory()
    try:
        fid = f"file_{uuid.uuid4().hex}"
        repos.create_file(
            conn, file_id=fid, task_id=up["id"], kind="output", filename="secret.csv",
            path=f"/tmp/{fid}", size_bytes=1, sha256="a" * 64, classification="sensitive",
        )
    finally:
        conn.close()
    r = _mk(client, "thief", input_file_ids=[fid])
    assert r.status_code == 422  # output 直引旁路被结构性挡住


def test_uploaded_input_file_can_be_referenced(app_env):
    """正控（证 guard 非空咬合）：kind=input 上传件直引 → 放行入队。"""
    import uuid
    from backend.app.storage import repos
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        fid = f"file_{uuid.uuid4().hex}"
        repos.create_file(
            conn, file_id=fid, task_id=None, kind="input", filename="upload.csv",
            path=f"/tmp/{fid}", size_bytes=1, sha256="b" * 64, classification="internal",
        )
    finally:
        conn.close()
    r = _mk(client, "legit", input_file_ids=[fid])
    assert r.status_code == 200  # 上传件是合法直引，guard 不误拒
    assert r.json()["status"] == "queued"


def test_dependent_task_not_claimed_by_worker(app_env):
    """滞留 created 的依赖任务不进 worker 候选集（claim 只取 queued）。"""
    client, app = app_env
    up = _mk(client, "up").json()
    down = _mk(client, "down", depends_on=[up["id"]]).json()
    from backend.app.storage import repos
    conn = app.state.conn_factory()
    try:
        claimed = repos.claim_next_queued(conn)
    finally:
        conn.close()
    # 候选是 up（queued），绝不是 down（created）
    assert claimed is not None and claimed["id"] == up["id"]
    assert down["status"] == "created"
