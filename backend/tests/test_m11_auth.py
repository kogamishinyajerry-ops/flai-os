"""ADR-0019 真鉴权验收（M11-B1）：default-deny / 会话语义 / 记名认证化 witnesses。

覆盖 ADR-0019 R1 验收标准 1-8（loop-auditor F1-F6 全部落 witness）：
- F1 裸 OPTIONS 探测面：无双头 401，真 preflight 放行
- F2 结构不变量：遍历 app.routes 全部 API 路由未登录逐条 401
- F3 过期边界双侧：严格 `<` 被改 `<=`/反向必咬（service 级 monkeypatch 时钟）
- F4 会话哈希落库：token_hash == sha256(cookie 明文) 且 != 明文
- F5 锁定期内正确密码亦 429
- F6 结构检查：测试世界无 auth_sessions 直插、conftest 走真实登录端点

测试纪律（F6）：需要「过期会话」时允许 UPDATE 既有合法会话的 expires_at
（模拟时间流逝，无法真等 7 天）；绝不 INSERT 伪造会话行。
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.auth import service as auth_service
from backend.app.auth.passwords import hash_password, verify_password
from backend.app.storage.db import get_conn, init_db
from conftest import TEST_DISPLAY_NAME, TEST_PASSWORD, TEST_ROLE, TEST_USERNAME, login, seed_user

TESTS_DIR = Path(__file__).resolve().parent

_ALLOWLIST = {("POST", "/api/auth/login"), ("GET", "/api/health")}


def _anon(app) -> TestClient:
    """无 cookie 的新客户端（共享同一 app/lifespan 状态，独立 cookie jar）。"""
    return TestClient(app)


# ── AC1/F2：default-deny 结构不变量 ──────────────────────────────────────


def test_default_deny_walks_every_api_route(app_env):
    """遍历全部已挂载 API 路由未登录逐条打——单个 router 漂移/裸奔/allowlist
    被偷偷扩大（tamper：往 allowlist 加 /api/tasks）都会让本测试变红。

    走 app.openapi()["paths"]（而非 app.routes）：本版 FastAPI 把 include_router
    包成懒加载 _IncludedRouter，顶层不平展；openapi 路径表是全量平展的权威面
    （include_in_schema=False 的 SPA fallback 天然不在其中，恰好不属本门管辖）。"""
    client, app = app_env
    anon = _anon(app)
    paths = app.openapi()["paths"]
    walked = 0
    for raw_path, operations in paths.items():
        if not raw_path.startswith("/api"):
            continue
        path = re.sub(r"\{[^}]+\}", "probe", raw_path)
        for method in operations:
            method = method.upper()
            if method in {"HEAD", "OPTIONS"}:
                continue
            if (method, path) in _ALLOWLIST:
                continue
            resp = anon.request(method, path)
            assert resp.status_code == 401, (
                f"未登录 {method} {path} 应 401（default-deny），实际 {resp.status_code}"
            )
            assert resp.json()["detail"] == "未登录或会话已过期"
            walked += 1
    assert walked >= 25, f"结构不变量只走到 {walked} 条路由——路由挂载面异常收缩，防平凡绿"


def test_allowlist_is_exactly_two(app_env):
    """allowlist 白名单两项可未登录访问；带尾斜杠变体不享受放行（精确匹配）。"""
    client, app = app_env
    anon = _anon(app)
    assert anon.get("/api/health").status_code == 200
    r = anon.post("/api/auth/login", json={"username": "no_such", "password": "x"})
    assert r.status_code == 401  # 到达了处理器（凭据错），而非被中间件拦（走进了 allowlist）
    # 尾斜杠变体：FastAPI 会 307 到无斜杠，但中间件先看到 /api/health/ ——不在名单，401
    assert anon.get("/api/health/", follow_redirects=False).status_code == 401


# ── AC6/F1：裸 OPTIONS 探测面 ────────────────────────────────────────────


def test_openapi_docs_routes_are_guarded(app_env):
    """FastAPI 的 /openapi.json /docs /redoc 在 /api 之外——未登录必须 401
    （Codex 审 P2：否则未登录者拉全量路由清单+请求模型，破 default-deny）；
    登录后放行（开发者仍可用）。"""
    client, app = app_env  # client 已登录
    anon = _anon(app)
    for path in ("/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"):
        assert anon.get(path).status_code == 401, f"未登录 {path} 应 401（schema 枚举面）"
    assert client.get("/openapi.json").status_code == 200, "登录后 /openapi.json 应放行"


def test_bare_options_denied_but_real_preflight_allowed(app_env):
    client, app = app_env
    anon = _anon(app)
    assert anon.options("/api/tasks").status_code == 401, "裸 OPTIONS 必须落回默认拒绝（F1）"
    preflight = anon.options(
        "/api/tasks",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert preflight.status_code == 200, "真 preflight（双头齐全）应由 CORSMiddleware 应答"
    assert preflight.headers.get("access-control-allow-origin") == "http://localhost:5173"


# ── AC2：登录/节流/停用/登出 ─────────────────────────────────────────────


def test_login_me_roundtrip(app_env):
    client, _app = app_env  # conftest 已真实登录
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json() == {
        "username": TEST_USERNAME,
        "display_name": TEST_DISPLAY_NAME,
        "role": TEST_ROLE,
    }


def test_wrong_password_401_then_throttle_429_even_with_correct_password(app_env):
    """F5：第 5 次失败触发锁定后，携**正确密码**的第 6 次也必须 429——
    节流判定先于凭据校验，否则锁定对「猜中那一次」无效。"""
    client, app = app_env
    db_path = app.state.db_path
    seed_user(db_path, username="throttle_probe", display_name="节流探针", password="right-pw")
    anon = _anon(app)
    for _ in range(5):
        r = anon.post("/api/auth/login", json={"username": "throttle_probe", "password": "wrong"})
        assert r.status_code == 401
    locked = anon.post(
        "/api/auth/login", json={"username": "throttle_probe", "password": "right-pw"}
    )
    assert locked.status_code == 429, "锁定期内正确密码也必须 429（F5）"


def test_deactivated_user_same_detail_as_wrong_password_and_sessions_revoked(app_env):
    client, app = app_env
    db_path = app.state.db_path
    seed_user(db_path, username="leaver", display_name="离职者", password="pw-leaver")
    anon = _anon(app)
    login(anon, username="leaver", password="pw-leaver")
    assert anon.get("/api/auth/me").status_code == 200

    conn = get_conn(db_path)
    try:
        auth_service.set_user_active(conn, "leaver", False)
    finally:
        conn.close()
    # 停用即时生效：既有会话被吊销，不等 7 天自然过期
    assert anon.get("/api/auth/me").status_code == 401
    # 停用账户与错密码同码同文案（不泄露账户存在性）
    r_deactivated = anon.post("/api/auth/login", json={"username": "leaver", "password": "pw-leaver"})
    r_wrong = anon.post("/api/auth/login", json={"username": "ghost_user", "password": "x"})
    assert r_deactivated.status_code == r_wrong.status_code == 401
    assert r_deactivated.json()["detail"] == r_wrong.json()["detail"]


def test_logout_revokes_session_server_side(app_env):
    client, app = app_env
    db_path = app.state.db_path
    seed_user(db_path, username="bye_user", display_name="告别者", password="pw-bye")
    anon = _anon(app)
    login(anon, username="bye_user", password="pw-bye")
    token = anon.cookies.get("flai_session")
    assert token
    assert anon.post("/api/auth/logout").status_code == 200
    # 用旧 cookie 明文直接再打（绕过客户端 cookie jar 清除）：服务端行已删 → 401
    replay = _anon(app).get("/api/auth/me", headers={"Cookie": f"flai_session={token}"})
    assert replay.status_code == 401


def test_expired_session_401_over_http(app_env):
    """过期会话 401（HTTP 面）。F6 口径：UPDATE 合法会话的 expires_at 模拟
    时间流逝（无法真等 7 天），绝非 INSERT 伪造会话。"""
    client, app = app_env
    db_path = app.state.db_path
    seed_user(db_path, username="expired_user", display_name="过期者", password="pw-exp")
    anon = _anon(app)
    login(anon, username="expired_user", password="pw-exp")
    assert anon.get("/api/auth/me").status_code == 200
    past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    conn = get_conn(db_path)
    try:
        conn.execute(
            "UPDATE auth_sessions SET expires_at = ? WHERE user_id ="
            " (SELECT id FROM users WHERE username = 'expired_user')",
            (past,),
        )
    finally:
        conn.close()
    assert anon.get("/api/auth/me").status_code == 401


# ── AC2/F3：过期边界双侧（service 级，时钟可控） ─────────────────────────


def test_expiry_boundary_strict_less_than(app_env, monkeypatch):
    """严格 `<` 的双侧 witness：now == expires_at 恰好一刻 → 拒；
    now 略早于 expires_at → 放。`<` 被改 `<=` 或方向反转必咬。"""
    client, app = app_env
    db_path = app.state.db_path
    user = seed_user(db_path, username="edge_user", display_name="边界者", password="pw-edge")
    conn = get_conn(db_path)
    try:
        token, expires_at = auth_service.create_session(conn, user["id"])
        expires = datetime.fromisoformat(expires_at)

        monkeypatch.setattr(auth_service, "_now", lambda: expires - timedelta(seconds=1))
        assert auth_service.get_session_user(conn, token) is not None, "过期前 1 秒应有效"

        monkeypatch.setattr(auth_service, "_now", lambda: expires)
        assert auth_service.get_session_user(conn, token) is None, (
            "now == expires_at 必须拒（严格 <；改成 <= 此处必咬）"
        )
    finally:
        conn.close()


# ── AC5/F4：会话令牌哈希落库 ─────────────────────────────────────────────


def test_malformed_expires_at_fails_closed(app_env):
    """库里 expires_at 畸形（非法字符串 / naive datetime）→ get_session_user
    返回 None（拒），绝不抛异常逃到中间件变 500（fail-closed 硬化，Codex 审）。"""
    client, app = app_env
    db_path = app.state.db_path
    user = seed_user(db_path, username="malformed_user", display_name="畸形者", password="pw-mal")
    conn = get_conn(db_path)
    try:
        token, _ = auth_service.create_session(conn, user["id"])
        # ① 非法字符串
        conn.execute("UPDATE auth_sessions SET expires_at = 'not-a-date' WHERE user_id = ?", (user["id"],))
        assert auth_service.get_session_user(conn, token) is None
        # ② naive datetime（无时区）——本代码只写 tz-aware，此为库损坏/注入
        conn.execute("UPDATE auth_sessions SET expires_at = '2999-01-01T00:00:00' WHERE user_id = ?", (user["id"],))
        assert auth_service.get_session_user(conn, token) is None
    finally:
        conn.close()


def test_session_token_stored_as_sha256_not_plaintext(app_env):
    client, app = app_env
    db_path = app.state.db_path
    seed_user(db_path, username="hash_user", display_name="哈希者", password="pw-hash")
    anon = _anon(app)
    login(anon, username="hash_user", password="pw-hash")
    token = anon.cookies.get("flai_session")
    conn = get_conn(db_path)
    try:
        hashes = {row["token_hash"] for row in conn.execute("SELECT token_hash FROM auth_sessions")}
    finally:
        conn.close()
    assert token not in hashes, "cookie 明文绝不落库（F4）"
    assert hashlib.sha256(token.encode()).hexdigest() in hashes, "库中必须是 sha256(明文)"


# ── AC3：记名字段认证化 ──────────────────────────────────────────────────


def test_created_by_derived_from_session_and_forgery_rejected(app_env):
    client, _app = app_env
    forged = client.post(
        "/api/tasks", json={"agent_id": "hello_agent", "created_by": "冒名者"}
    )
    assert forged.status_code == 422, "请求体伪造 created_by 必须响亮 422（extra=forbid）"

    honest = client.post("/api/tasks", json={"agent_id": "hello_agent"})
    assert honest.status_code == 200
    assert honest.json()["created_by"] == TEST_DISPLAY_NAME, "created_by=登录身份，非自报"


def test_feedback_created_by_derived(app_env):
    client, _app = app_env
    task = client.post("/api/tasks", json={"agent_id": "hello_agent"}).json()
    forged = client.post(
        "/api/feedback",
        json={"task_id": task["id"], "rating": "good", "category": "other", "created_by": "冒名者"},
    )
    assert forged.status_code == 422
    ok = client.post(
        "/api/feedback", json={"task_id": task["id"], "rating": "good", "category": "other"}
    )
    assert ok.status_code == 200
    assert ok.json()["created_by"] == TEST_DISPLAY_NAME


# ── 密码哈希单元 witnesses ───────────────────────────────────────────────


def test_password_hash_roundtrip_and_fail_closed():
    stored = hash_password("s3cret")
    assert stored.startswith("pbkdf2_sha256$600000$")
    assert verify_password("s3cret", stored) is True
    assert verify_password("wrong", stored) is False
    # 存储损坏/格式不识别一律 False，绝不抛错放行（fail-closed）
    assert verify_password("s3cret", "") is False
    assert verify_password("s3cret", "md5$abc") is False
    assert verify_password("s3cret", "pbkdf2_sha256$notint$zz$zz") is False
    # iterations 越界一律拒，绝不喂给 pbkdf2_hmac 触发 OverflowError（Codex R4 审 P2）
    assert verify_password("s3cret", "pbkdf2_sha256$1099511627776$00$00") is False  # 超上限
    assert verify_password("s3cret", "pbkdf2_sha256$1$00$00") is False  # 低于下限
    assert verify_password("s3cret", "pbkdf2_sha256$600000$" + "0" * 300 + "$00") is False  # salt 超长
    with pytest.raises(ValueError):
        hash_password("")


def test_infra_error_does_not_consume_login_quota(app_env, monkeypatch):
    """基础设施错误（非凭据失败）撤销尝试槽（Codex R4 审 P2）：5 次瞬时 500 不得
    把真实账户虚假锁 15 分钟。打桩 open_session 抛 OperationalError 模拟 db locked。"""
    import sqlite3 as _sqlite

    client, app = app_env
    db_path = app.state.db_path
    seed_user(db_path, username="infra_probe", display_name="基础设施", password="pw-infra")
    throttle = app.state.login_throttle

    def boom(*a, **k):
        raise _sqlite.OperationalError("database is locked")

    monkeypatch.setattr(auth_service, "open_session_for_credentials", boom)
    anon = _anon(app)
    for _ in range(6):
        try:
            anon.post("/api/auth/login", json={"username": "infra_probe", "password": "pw-infra"})
        except _sqlite.OperationalError:
            pass  # TestClient 把 500 作异常透出——基础设施错误本就该 500
    assert throttle.blocked("infra_probe") is False, "基础设施 500 不得虚假锁定账户"


def test_concurrent_login_burst_bounded_to_max(app_env):
    """并发突发不得绕过限速（Codex 审 P1）：24 个线程同时以错密码打同一
    username，reserve-before-verify 保证放行进验证的 ≤ max，其余 429。
    check-then-act 竞态若复活（先全过 blocked 再各自记失败）本测试必红。"""
    import threading

    from backend.app.auth.service import LoginThrottle

    throttle = LoginThrottle(max_failures=5)
    allowed = []
    barrier = threading.Barrier(24)

    def attempt(i):
        barrier.wait()  # 尽量对齐并发起点
        if throttle.reserve("victim") is True:
            allowed.append(i)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(24)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(allowed) <= 5, f"并发放行 {len(allowed)} 次，超过 max=5——限速被并发绕过"


def test_throttle_state_bounded(app_env):
    """攻击者轮换随机 username 不得无界撑大限速字典（Codex 审 P2）。"""
    from backend.app.auth.service import LoginThrottle

    throttle = LoginThrottle(max_failures=5, max_tracked=100)
    for i in range(500):
        throttle.reserve(f"user_{i}")
    total = len(throttle._failures) + len(throttle._locked_until)
    assert total <= 100, f"限速字典涨到 {total}，超过硬顶 100"


def test_create_user_enforces_login_length_limits(app_env):
    """create_user 与 login 端上限对齐（Codex 审 P2）：否则建出永远 422
    登不上的账户。"""
    _client, app = app_env
    db_path = app.state.db_path
    conn = get_conn(db_path)
    try:
        with pytest.raises(ValueError, match="超长"):
            auth_service.create_user(conn, username="u" * 101, display_name="X", password="p")
        with pytest.raises(ValueError, match="超长"):
            auth_service.create_user(conn, username="ok", display_name="X", password="p" * 201)
    finally:
        conn.close()


def test_reset_password_enforces_length_limit(app_env):
    """reset_password 同样受 PASSWORD_MAX 约束（Codex R1 审 P2）：否则改到
    超长密码会吊销旧会话又让此后 login 撞 422，账户变砖。"""
    _client, app = app_env
    db_path = app.state.db_path
    seed_user(db_path, username="reset_probe", display_name="改密探针", password="ok-pw")
    conn = get_conn(db_path)
    try:
        with pytest.raises(ValueError, match="超长"):
            auth_service.reset_password(conn, "reset_probe", "p" * 201)
    finally:
        conn.close()


def test_global_verify_slot_caps_concurrent_verification(app_env):
    """全局并发校验闸（Codex R1 审 P1）：轮换 username 绕过 per-username 限速后，
    昂贵 PBKDF2 仍被此闸全局封顶——满槽时 acquire 立即失败（429），不排队。"""
    from backend.app.auth.service import LoginThrottle

    throttle = LoginThrottle(max_concurrent_verify=3)
    assert throttle.acquire_verify_slot() is True
    assert throttle.acquire_verify_slot() is True
    assert throttle.acquire_verify_slot() is True
    assert throttle.acquire_verify_slot() is False, "第 4 个并发校验必须被全局闸拒（不排队）"
    throttle.release_verify_slot()
    assert throttle.acquire_verify_slot() is True, "释放一个槽后可再占"


def test_open_session_rejects_credential_changed_midflight(app_env):
    """签发会话前写锁内复查凭据（Codex R2 审 P1）：模拟「校验通过后、插会话前
    密码被改」——open_session_for_credentials 复查 hash 变即拒，绝不为旧密码发
    活会话。此处直接把 verify_password 打桩为「先返回 True 再偷改库里 hash」，
    逼出 verify 与 insert 之间的窗口。"""
    _client, app = app_env
    db_path = app.state.db_path
    user = seed_user(db_path, username="toctou_user", display_name="竞态者", password="orig-pw")
    conn = get_conn(db_path)
    try:
        # 打桩：校验刚返回 True 的瞬间，模拟管理员 reset-password 改掉了 hash
        real_verify = auth_service.verify_password

        def racing_verify(pw, stored):
            ok = real_verify(pw, stored)
            if ok:
                conn.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (auth_service.hash_password("changed-pw"), user["id"]),
                )
            return ok

        before = conn.execute(
            "SELECT COUNT(*) FROM auth_sessions WHERE user_id = ?", (user["id"],)
        ).fetchone()[0]
        auth_service.verify_password = racing_verify
        try:
            result = auth_service.open_session_for_credentials(conn, "toctou_user", "orig-pw")
        finally:
            auth_service.verify_password = real_verify
        assert result is None, "凭据在校验期间被改，必须拒发会话（TOCTOU 闭合）"
        after = conn.execute(
            "SELECT COUNT(*) FROM auth_sessions WHERE user_id = ?", (user["id"],)
        ).fetchone()[0]
        assert after == before, "被改凭据绝不落新会话行"
    finally:
        conn.close()


def test_open_session_consumes_verify_credentials_seam(app_env, monkeypatch):
    """签发会话必须走 verify_credentials（ADR-0019 D7 SSO 缝，Codex R3 审 P2）：
    否则 SSO 替换 verify_credentials 不改变认证=接缝失效。打桩 verify_credentials
    返回 None→open_session 必拒（证明它真消费了该缝而非自建校验）。"""
    _client, app = app_env
    db_path = app.state.db_path
    seed_user(db_path, username="seam_user", display_name="接缝", password="pw-seam")
    conn = get_conn(db_path)
    try:
        monkeypatch.setattr(auth_service, "verify_credentials", lambda *a, **k: None)
        assert auth_service.open_session_for_credentials(conn, "seam_user", "pw-seam") is None, (
            "verify_credentials 判否时 open_session 必须拒——证明认证经由该缝"
        )
    finally:
        conn.close()


def test_lock_deadline_from_threshold_not_retry_time(app_env):
    """锁定期从达到阈值那次尝试起算，非当前时刻（Codex R3 审 P2）：5 次失败在
    t=0、第 6 次在 t=14min→应锁到 t=15 而非 t=29。用可控时钟精确验证。"""
    from backend.app.auth.service import LoginThrottle

    clock = {"t": 0.0}
    throttle = LoginThrottle(max_failures=5, window_seconds=900, lock_seconds=900,
                             clock=lambda: clock["t"])
    for _ in range(5):
        assert throttle.reserve("u") is True  # t=0 的 5 次尝试
    clock["t"] = 14 * 60  # 第 6 次在 14min
    assert throttle.reserve("u") is False  # 触发锁定
    clock["t"] = 15 * 60 + 1  # 15min 后（阈值 t=0 + 900s）
    assert throttle.reserve("u") is True, "锁应在阈值+15min 解除（t=15），而非 retry+15min（t=29）"


def test_busy_slot_does_not_consume_login_quota(app_env):
    """全局繁忙 429 不得占用尝试槽（Codex R2 审 P2）：否则真实账户被 5 次繁忙
    响应虚假锁定 15 分钟而从未查过一次密码。占满全局槽后连打 6 次，limit 计数
    应保持 0（繁忙分支先于 reserve）。"""
    client, app = app_env
    db_path = app.state.db_path
    seed_user(db_path, username="busy_victim", display_name="繁忙受害者", password="pw-busy")
    throttle = app.state.login_throttle
    # 占满全部全局校验槽，令后续 login 走繁忙 429 分支
    slots = []
    while throttle.acquire_verify_slot() is True:
        slots.append(1)
    try:
        anon = _anon(app)
        for _ in range(6):
            r = anon.post("/api/auth/login", json={"username": "busy_victim", "password": "pw-busy"})
            assert r.status_code == 429
        assert throttle.blocked("busy_victim") is False, "繁忙响应不得把真实账户锁死"
    finally:
        for _ in slots:
            throttle.release_verify_slot()
    # 槽释放后正确密码应能登入（未被虚假锁定）
    anon2 = _anon(app)
    assert anon2.post(
        "/api/auth/login", json={"username": "busy_victim", "password": "pw-busy"}
    ).status_code == 200


def test_restore_aborts_when_session_purge_fails(app_env, tmp_path, monkeypatch):
    """恢复时清会话失败必须 abort 不谎报成功（Codex R2 审 P1）：磁盘满/锁导致
    DELETE 失败时旧会话仍在，此时报成功=被盗 token 复活。真失败→return 1+坏产物
    不留盘。"""
    import sqlite3 as _sqlite

    import scripts.backup_restore as br

    client, app = app_env
    db_path = app.state.db_path
    seed_user(db_path, username="purge_fail_probe", display_name="清理失败", password="pw-pf")
    backup = tmp_path / "snap.db"
    target = tmp_path / "restored.db"
    br._online_backup(db_path, backup)

    # 打桩：DELETE FROM auth_sessions 抛非「no such table」的 OperationalError。
    # sqlite3.Connection.execute 是不可变 C 类型属性，改不了——改用 factory 子类
    # 注入（backup 走 .backup()/integrity 走 PRAGMA，只有 DELETE 被拦）。
    real_connect = _sqlite.connect

    class FailingDeleteConn(_sqlite.Connection):
        def execute(self, sql, *a, **k):
            if isinstance(sql, str) and "DELETE FROM auth_sessions" in sql:
                raise _sqlite.OperationalError("database or disk is full")
            return super().execute(sql, *a, **k)

    def fake_connect(path, *a, **k):
        k.setdefault("factory", FailingDeleteConn)
        return real_connect(path, *a, **k)

    monkeypatch.setattr(br.sqlite3, "connect", fake_connect)
    rc = br.cmd_restore(str(backup), str(target))
    assert rc == 1, "清会话失败必须 abort（return 1）"
    assert not target.exists(), "坏恢复产物（含活会话）绝不留盘"


def test_restore_purges_all_sessions(app_env, tmp_path):
    """备份恢复必须清空全部会话（Codex R1 审 P1）：逐表原样恢复会复活登出/
    停用/改密前的旧会话行，令被盗未过期 token 或已撤销凭据重新生效。"""
    import scripts.backup_restore as br

    client, app = app_env
    db_path = app.state.db_path
    # 造一个含活会话的真库快照
    seed_user(db_path, username="restore_probe", display_name="恢复探针", password="pw-r")
    anon = _anon(app)
    login(anon, username="restore_probe", password="pw-r")
    src_conn = get_conn(db_path)
    try:
        assert src_conn.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0] >= 1
    finally:
        src_conn.close()
    backup = tmp_path / "snap.db"
    target = tmp_path / "restored.db"
    # 直接用脚本的在线备份+恢复路径
    br._online_backup(db_path, backup)
    rc = br.cmd_restore(str(backup), str(target))
    assert rc == 0
    restored = get_conn(target)
    try:
        # 会话被清空（强制重登），但账户仍在（时间旅行语义保留账户）
        assert restored.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0] == 0
        assert restored.execute("SELECT COUNT(*) FROM users").fetchone()[0] >= 1
    finally:
        restored.close()


def test_duplicate_username_rejected(app_env):
    _client, app = app_env
    db_path = app.state.db_path
    conn = get_conn(db_path)
    try:
        with pytest.raises(ValueError, match="已存在"):
            auth_service.create_user(
                conn, username=TEST_USERNAME, display_name="重名", password="x"
            )
    finally:
        conn.close()


def test_legacy_users_gain_explicit_admin_role_without_losing_account(tmp_path):
    db_path = tmp_path / "legacy_users.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO users (username, display_name, password_hash, created_at) "
            "VALUES ('legacy', '存量用户', 'hash', '2026-07-20T00:00:00+00:00')"
        )
        conn.commit()
    finally:
        conn.close()

    init_db(db_path)

    migrated = get_conn(db_path)
    try:
        row = migrated.execute(
            "SELECT username, role FROM users WHERE username = 'legacy'"
        ).fetchone()
        assert dict(row) == {"username": "legacy", "role": "admin"}
    finally:
        migrated.close()


def test_role_change_revokes_existing_sessions(app_env):
    client, app = app_env
    conn = app.state.conn_factory()
    try:
        auth_service.set_user_role(conn, TEST_USERNAME, "business_user")
    finally:
        conn.close()
    assert client.get("/api/auth/me").status_code == 401


# ── AC8/F6：测试世界无旁路的结构检查 ─────────────────────────────────────


def test_no_session_insertion_backdoor_in_tests():
    """扫描全部测试源码：向 auth_sessions 直插行的 SQL 零命中（防「活在
    conftest 里的 AUTH_OFF」被日后静默引入）；conftest 必须走真实登录端点。
    注：本 docstring 刻意不写该 SQL 字面量，免得自匹配。"""
    offenders = []
    for f in TESTS_DIR.glob("*.py"):
        text = f.read_text(encoding="utf-8")
        if re.search(r"INSERT\s+INTO\s+auth_sessions", text, re.IGNORECASE):
            offenders.append(f.name)
    assert offenders == [], f"测试直插会话行=旁路后门（F6）：{offenders}"
    conftest_text = (TESTS_DIR / "conftest.py").read_text(encoding="utf-8")
    assert '"/api/auth/login"' in conftest_text, "conftest 登录注入必须走真实登录端点（F6）"
