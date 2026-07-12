"""M2 静态托管测试：frontend/dist 存在时 SPA 托管、/api 永不被 index.html 掩盖。

dist 用 tmp_path 伪造（真实 dist 是构建产物不入库），绝不碰真实 frontend/dist。
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from conftest import seed_and_login

from backend.app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]

_INDEX_MARK = "FLAI-SPA-INDEX-SENTINEL"


def _make_app(tmp_path: Path, *, with_dist: bool):
    dist = tmp_path / "dist"
    if with_dist:
        dist.mkdir()
        (dist / "index.html").write_text(
            f"<!doctype html><html><body>{_INDEX_MARK}</body></html>", encoding="utf-8"
        )
        (dist / "assets").mkdir()
        (dist / "assets" / "app.js").write_text("console.log('flai')", encoding="utf-8")
        (dist / "favicon.ico").write_bytes(b"\x00fakeicon")
    return create_app(
        agents_dir=REPO_ROOT / "agents",
        tools_dir=REPO_ROOT / "tools_impl",
        contracts_dir=REPO_ROOT / "contracts",
        db_path=tmp_path / "flai_os.db",
        uploads_dir=tmp_path / "uploads",
        task_runs_dir=tmp_path / "task_runs",
        frontend_dist_dir=dist,
    )


@pytest.fixture()
def spa_client(tmp_path) -> Iterator[TestClient]:
    with TestClient(_make_app(tmp_path, with_dist=True)) as client:
        seed_and_login(client, tmp_path / "flai_os.db")
        yield client


def test_root_serves_index(spa_client: TestClient) -> None:
    resp = spa_client.get("/")
    assert resp.status_code == 200
    assert _INDEX_MARK in resp.text


def test_deep_link_falls_back_to_index(spa_client: TestClient) -> None:
    """vue-router history 模式：/tasks/task_xxx 刷新必须回 index.html 而非 404。"""
    resp = spa_client.get("/tasks/task_deadbeef")
    assert resp.status_code == 200
    assert _INDEX_MARK in resp.text


def test_real_static_file_served_as_is(spa_client: TestClient) -> None:
    assert spa_client.get("/assets/app.js").text == "console.log('flai')"
    assert spa_client.get("/favicon.ico").content.startswith(b"\x00fakeicon")


def test_api_routes_still_win(spa_client: TestClient) -> None:
    resp = spa_client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_unknown_api_path_is_honest_404_not_index(tmp_path) -> None:
    """接口不存在必须如实 404 JSON——用 index.html 掩盖 = 前端拿 HTML 当 JSON 解析
    的假绿温床。ADR-0019 后先验未登录 401，再验登录后路由层 404。"""
    with TestClient(_make_app(tmp_path, with_dist=True)) as client:
        unauthenticated = client.get("/api/no_such_endpoint")
        assert unauthenticated.status_code == 401
        assert _INDEX_MARK not in unauthenticated.text

        seed_and_login(client, tmp_path / "flai_os.db")
        resp = client.get("/api/no_such_endpoint")
        assert resp.status_code == 404
        assert _INDEX_MARK not in resp.text
        assert "接口不存在" in resp.json()["detail"]
        # 大小写变体同样不得被 index.html 掩盖（反审 P3-1）
        upper = client.get("/API/no_such_endpoint")
        assert upper.status_code == 404
        assert _INDEX_MARK not in upper.text


def test_path_traversal_does_not_leak_files_outside_dist(spa_client: TestClient, tmp_path) -> None:
    """dist 外文件（如同级 secret.txt）绝不可经 catch-all 泄漏——resolve 前缀防护。"""
    (tmp_path / "secret.txt").write_text("TOP-SECRET", encoding="utf-8")
    for probe in ("/../secret.txt", "/..%2Fsecret.txt", "/assets/../../secret.txt"):
        resp = spa_client.get(probe)
        assert "TOP-SECRET" not in resp.text, f"穿越探针泄漏：{probe}"


def test_without_dist_no_spa_routes(tmp_path) -> None:
    """dist 不存在（开发期 vite proxy 场景）：静态路由整体缺席，/ 返回 404，
    /api 行为与 M1 完全一致。"""
    with TestClient(_make_app(tmp_path, with_dist=False)) as client:
        seed_and_login(client, tmp_path / "flai_os.db")
        assert client.get("/").status_code == 404
        assert client.get("/api/health").status_code == 200
