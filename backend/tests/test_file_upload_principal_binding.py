"""Safe-auto attachment uploads bind to the durable browser principal snapshot."""

from __future__ import annotations

import json
from urllib.parse import quote

import pytest
from conftest import TEST_ROLE, TEST_USERNAME, login, seed_user
from starlette.formparsers import MultiPartParser


def _principal_header(payload: object) -> dict[str, str]:
    return {
        "X-FLAI-Expected-Principal": quote(
            json.dumps(payload, ensure_ascii=False),
            safe="",
        )
    }


def test_cookie_drift_rejects_before_multipart_parse_disk_or_database(
    app_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, app = app_env
    expected = client.get("/api/auth/me")
    assert expected.status_code == 200, expected.text
    assert expected.json()["username"] == TEST_USERNAME

    seed_user(
        app.state.db_path,
        username="other_engineer",
        display_name="另一位工程师",
        password="other-password-123",
        role="admin",
    )
    login(client, username="other_engineer", password="other-password-123")

    multipart_parsed = False

    async def reject_multipart_parse(_self):
        nonlocal multipart_parsed
        multipart_parsed = True
        raise AssertionError("principal drift must be rejected before multipart parsing")

    monkeypatch.setattr(MultiPartParser, "parse", reject_multipart_parse)

    response = client.post(
        "/api/files/upload",
        files={"file": ("evidence.txt", b"must never reach disk")},
        headers=_principal_header({"username": TEST_USERNAME, "role": TEST_ROLE}),
    )

    assert response.status_code == 409, response.text
    assert multipart_parsed is False
    assert response.json() == {
        "detail": "认证主体与持久化自动执行意图不一致，已拒绝请求"
    }
    assert not app.state.uploads_dir.exists() or list(app.state.uploads_dir.rglob("*")) == []
    conn = app.state.conn_factory()
    try:
        assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0
    finally:
        conn.close()


def test_malformed_or_oversized_expected_principal_header_is_422_before_multipart(
    app_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, app = app_env
    multipart_parsed = False

    async def reject_multipart_parse(_self):
        nonlocal multipart_parsed
        multipart_parsed = True
        raise AssertionError("malformed header must be rejected before multipart parsing")

    monkeypatch.setattr(MultiPartParser, "parse", reject_multipart_parse)
    headers = [
        {"X-FLAI-Expected-Principal": quote("[" * 5000, safe="")},
        _principal_header({"username": TEST_USERNAME, "role": []}),
    ]
    for header in headers:
        response = client.post(
            "/api/files/upload",
            files={"file": ("evidence.txt", b"must never be parsed")},
            headers=header,
        )
        assert response.status_code == 422, response.text
        assert response.json() == {"detail": "expected principal header 格式非法"}
    assert multipart_parsed is False
    assert not app.state.uploads_dir.exists() or list(app.state.uploads_dir.rglob("*")) == []
    conn = app.state.conn_factory()
    try:
        assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0
    finally:
        conn.close()
