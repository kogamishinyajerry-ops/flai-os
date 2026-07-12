"""后端测试共享夹具。

ADR-0019（真鉴权）后测试世界的登录纪律（loop-auditor F6）：
- seed_user 只建 users 行（= scripts/user_admin.py create 的测试等价物）；
- **会话必须走真实 POST /api/auth/login 换真实 Set-Cookie**——绝不直插
  auth_sessions 行、绝不 monkeypatch 短路中间件（那是活在测试里的 AUTH_OFF，
  ADR-0019 D9 明文拒绝的模式）。结构检查见 test_m11_auth.py。
- 经 API 写入的记名字段（created_by/reviewer/…）一律等于 TEST_DISPLAY_NAME。
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.auth import service as auth_service
from backend.app.main import create_app
from backend.app.storage.db import get_conn

REPO_ROOT = Path(__file__).resolve().parents[2]

TEST_USERNAME = "test_engineer"
TEST_PASSWORD = "test-password-123"
TEST_DISPLAY_NAME = "测试工程师"


def seed_user(db_path, *, username: str = TEST_USERNAME,
              display_name: str = TEST_DISPLAY_NAME, password: str = TEST_PASSWORD):
    """建测试账户（库须已 init——在 TestClient 进入 lifespan 之后调用）。"""
    conn = get_conn(db_path)
    try:
        return auth_service.create_user(
            conn, username=username, display_name=display_name, password=password
        )
    finally:
        conn.close()


def login(client: TestClient, *, username: str = TEST_USERNAME, password: str = TEST_PASSWORD):
    """真实登录（F6）：cookie 由 TestClient 从真实 Set-Cookie 记住，后续请求自动携带。"""
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"测试登录失败：{resp.status_code} {resp.text}"
    return resp


def seed_and_login(client: TestClient, db_path) -> None:
    seed_user(db_path)
    login(client)


@pytest.fixture()
def app_env(tmp_path):
    db_path = tmp_path / "flai_os.db"
    uploads_dir = tmp_path / "uploads"
    task_runs_dir = tmp_path / "task_runs"
    app = create_app(
        agents_dir=REPO_ROOT / "agents",
        tools_dir=REPO_ROOT / "tools_impl",
        contracts_dir=REPO_ROOT / "contracts",
        db_path=db_path,
        uploads_dir=uploads_dir,
        task_runs_dir=task_runs_dir,
    )
    with TestClient(app) as client:
        seed_and_login(client, db_path)
        yield client, app
