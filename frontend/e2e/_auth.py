"""e2e 登录注入（ADR-0019/M11-B1）。

真登录纪律（loop-auditor F6 同口径）：种账户（=管理员 user_admin.py create 的
测试等价物）后，**一律走真实 POST /api/auth/login 换真实 Set-Cookie**——
浏览器上下文经 context.request 登录（cookie 与页面共享 jar），直连 API 的
httpx 走 login_httpx 返回带会话的 Client。绝不直插会话行。

各套件 display_name 沿用其历史身份名（验收工程师/王工），下游对 created_by
文案的断言不变。
"""

from __future__ import annotations

from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import httpx

from backend.app.auth import service as auth_service
from backend.app.storage.db import get_conn

E2E_USERNAME = "e2e_engineer"
E2E_PASSWORD = "e2e-pass-flai"


def seed_user(db_path, display_name: str, *, username: str = E2E_USERNAME,
              password: str = E2E_PASSWORD, role: str = "admin") -> None:
    """建 e2e 账户（库须已 init——在后端 /api/health 就绪之后调用）。"""
    conn = get_conn(db_path)
    try:
        auth_service.create_user(
            conn, username=username, display_name=display_name, password=password, role=role
        )
    finally:
        conn.close()


def login_context(context, base: str, *, username: str = E2E_USERNAME,
                  password: str = E2E_PASSWORD) -> None:
    """浏览器上下文真实登录：context.request 与页面共享 cookie jar，
    登录成功后该 context 的所有页面都携带会话。"""
    resp = context.request.post(
        f"{base}/api/auth/login", data={"username": username, "password": password}
    )
    assert resp.ok, f"e2e 登录失败：{resp.status} {resp.text()}"


def login_httpx(base: str, *, username: str = E2E_USERNAME,
                password: str = E2E_PASSWORD) -> httpx.Client:
    """直连 API 用的已登录 httpx.Client（cookie jar 内置）。"""
    client = httpx.Client(base_url=base, timeout=10)
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"e2e API 登录失败：{resp.status_code} {resp.text}"
    return client
