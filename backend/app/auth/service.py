"""用户/会话服务（ADR-0019 D1/D3/D6/D7）。

conn 由调用方传入（与 repos 同风格）；时间戳 UTC ISO 8601（与 repos 同口径）。
SSO 适配缝：将来内网 AD/LDAP/反代认证**只替换 verify_credentials**，
会话签发/中间件/记名派生不动。
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from .passwords import hash_password, verify_password

SESSION_TTL = timedelta(days=7)  # 固定有效期，无滑动续期（ADR-0019 D3 最小化）
COOKIE_NAME = "flai_session"

# 与 login API 的 Pydantic 上限对齐（Codex 审 P2）：create_user 不设限会造出
# 「建得成但永远 422 登不上」的账户（登录端拒超长）。同一口径两处焊死。
USERNAME_MAX = 100
PASSWORD_MAX = 200


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _row_to_user(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "is_active": row["is_active"],
        "created_at": row["created_at"],
    }


# ── 用户 CRUD（scripts/user_admin.py 的唯一后端）──────────────────────────


def create_user(conn: sqlite3.Connection, *, username: str, display_name: str, password: str) -> dict[str, Any]:
    username = username.strip()
    display_name = display_name.strip()
    if not username or not display_name:
        raise ValueError("username 与 display_name 均不得为空白")
    # 与 login 端上限对齐（Codex 审 P2）：否则建出永远登不上的账户
    if len(username) > USERNAME_MAX:
        raise ValueError(f"username 超长（>{USERNAME_MAX}），登录端会拒绝该账户")
    if len(password) > PASSWORD_MAX:
        raise ValueError(f"密码超长（>{PASSWORD_MAX}），登录端会拒绝该账户")
    try:
        cur = conn.execute(
            "INSERT INTO users (username, display_name, password_hash, is_active, created_at)"
            " VALUES (?, ?, ?, 1, ?)",
            (username, display_name, hash_password(password), _now().isoformat()),
        )
    except sqlite3.IntegrityError as exc:
        raise ValueError(f"用户名已存在：{username}") from exc
    row = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _row_to_user(row)


def get_user_by_username(conn: sqlite3.Connection, username: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return _row_to_user(row) if row is not None else None


def list_users(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM users ORDER BY username").fetchall()
    return [_row_to_user(r) for r in rows]


def set_user_active(conn: sqlite3.Connection, username: str, active: bool) -> None:
    cur = conn.execute(
        "UPDATE users SET is_active = ? WHERE username = ?", (1 if active is True else 0, username)
    )
    if cur.rowcount == 0:
        raise ValueError(f"用户不存在：{username}")
    if active is False:
        # 停用即吊销全部活会话——停用必须立刻生效，不等 7 天自然过期
        conn.execute(
            "DELETE FROM auth_sessions WHERE user_id = (SELECT id FROM users WHERE username = ?)",
            (username,),
        )


def reset_password(conn: sqlite3.Connection, username: str, new_password: str) -> None:
    # 与 login/create 上限对齐（Codex R1 审 P2）：reset 到超长密码会吊销旧会话
    # 却让此后每次 login 撞 422，账户变砖。
    if len(new_password) > PASSWORD_MAX:
        raise ValueError(f"密码超长（>{PASSWORD_MAX}），登录端会拒绝该账户")
    cur = conn.execute(
        "UPDATE users SET password_hash = ? WHERE username = ?",
        (hash_password(new_password), username),
    )
    if cur.rowcount == 0:
        raise ValueError(f"用户不存在：{username}")
    # 改密吊销旧会话：丢失/泄露场景改密后旧登录态必须失效
    conn.execute(
        "DELETE FROM auth_sessions WHERE user_id = (SELECT id FROM users WHERE username = ?)",
        (username,),
    )


# ── 凭据校验（SSO 适配缝唯一替换点）──────────────────────────────────────


def verify_credentials(conn: sqlite3.Connection, username: str, password: str) -> dict[str, Any] | None:
    """成功返回用户 dict，失败返回 None。停用账户与错密码同码同文案
    （不泄露「账户存在但被停用」的探测信息）。"""
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row is None:
        # 用户不存在也走一次真实哈希（等时化，弱化用户名枚举的时间侧信道）
        verify_password(password, "pbkdf2_sha256$600000$" + "0" * 32 + "$" + "0" * 64)
        return None
    if verify_password(password, row["password_hash"]) is not True:
        return None
    if row["is_active"] != 1:
        return None
    return _row_to_user(row)


# ── 会话 ──────────────────────────────────────────────────────────────────


def create_session(conn: sqlite3.Connection, user_id: int) -> tuple[str, str]:
    """返回 (明文 token, expires_at)。明文只出现在 Set-Cookie，库里只存哈希。"""
    token = secrets.token_urlsafe(32)
    now = _now()
    expires_at = (now + SESSION_TTL).isoformat()
    conn.execute(
        "INSERT INTO auth_sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (_hash_token(token), user_id, now.isoformat(), expires_at),
    )
    return token, expires_at


def open_session_for_credentials(
    conn: sqlite3.Connection, username: str, password: str
) -> tuple[dict[str, Any], str] | None:
    """校验凭据并原子签发会话；失败/凭据在校验期间被改或停用 → None。

    认证走 SSO 缝 verify_credentials（ADR-0019 D7 唯一替换点，Codex R3 审 P2）——
    将来 AD/LDAP/反代认证只换它，本函数不动。

    闭合 TOCTOU（Codex R2 审 P1）：慢 PBKDF2 在锁外做（不锁写者），先抓当前凭据
    版本（password_hash），认证通过后进 BEGIN IMMEDIATE **复查该用户仍 active 且
    password_hash 未变**再插会话。与 user_admin 的 reset-password/deactivate（各自
    BEGIN IMMEDIATE）串行化：对方先提交→复查发现 hash 变/inactive→拒；我方先插→
    对方 reset 随即删掉该会话。任一交错都 fail-closed，绝不给「刚被改密/停用的
    凭据」发活会话。"""
    version_row = conn.execute(
        "SELECT password_hash FROM users WHERE username = ?", (username,)
    ).fetchone()
    user = verify_credentials(conn, username, password)  # SSO 缝：唯一认证判定点
    if user is None:
        return None
    verified_hash = version_row["password_hash"] if version_row is not None else None

    conn.execute("BEGIN IMMEDIATE")
    try:
        cur = conn.execute(
            "SELECT password_hash, is_active FROM users WHERE id = ?", (user["id"],)
        ).fetchone()
        if cur is None or cur["is_active"] != 1 or cur["password_hash"] != verified_hash:
            conn.execute("ROLLBACK")
            return None  # 校验期间凭据被改/停用——拒（fail-closed）
        token = secrets.token_urlsafe(32)
        now = _now()
        conn.execute(
            "INSERT INTO auth_sessions (token_hash, user_id, created_at, expires_at)"
            " VALUES (?, ?, ?, ?)",
            (_hash_token(token), user["id"], now.isoformat(), (now + SESSION_TTL).isoformat()),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return user, token


def get_session_user(conn: sqlite3.Connection, token: str) -> dict[str, Any] | None:
    """有效会话 → 用户 dict；过期/不存在/账户停用 → None（fail-closed 单出口）。"""
    if not token:
        return None
    row = conn.execute(
        "SELECT u.*, s.expires_at FROM auth_sessions s JOIN users u ON u.id = s.user_id"
        " WHERE s.token_hash = ?",
        (_hash_token(token),),
    ).fetchone()
    if row is None:
        return None
    if row["is_active"] != 1:
        return None
    try:
        expires = datetime.fromisoformat(row["expires_at"])
    except (ValueError, TypeError):
        return None  # 库里日期非法=会话不可信，拒
    if expires.tzinfo is None:
        # 合法会话恒为 tz-aware UTC（create_session 只写 _now().isoformat()）——
        # naive 时间戳=库损坏/人工注入，直接拒；绝不 coerce 后当有效，也绝不
        # 让 tz-naive 与 tz-aware 比较抛 TypeError 逃到中间件变 500（fail-closed）。
        return None
    if not _now() < expires:
        return None
    return _row_to_user(row)


def delete_session(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (_hash_token(token),))


def purge_expired_sessions(conn: sqlite3.Connection) -> int:
    cur = conn.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (_now().isoformat(),))
    return cur.rowcount


# ── 登录失败节流（ADR-0019 D6：进程内，单实例口径，诚实边界见 ADR）────────


class LoginThrottle:
    """按 username 限速：窗口内尝试 ≥ max_failures → 锁 lock_seconds。
    进程内存实现；实例挂 app.state（不做模块级全局，测试互不污染）。

    并发安全（Codex 审 P1）：check-then-act 在锁外做时，同一 username 的并发
    突发可全部通过 blocked() 再各自验证，实际猜测数远超 max。故改**原子
    reserve-before-verify**：`reserve()` 在 threading.Lock 内「判锁+记一次尝试」
    一步完成——慢的 PBKDF2 校验在锁外做，锁只保护 dict 微操作。成功登录
    reset 清零。任意时刻窗口内尝试恒 ≤ max。

    状态有界（Codex 审 P2）：login 匿名、username 攻击者可控，轮换随机名会
    无界撑大字典。每次 reserve 顺带 sweep 过期空条目；另设硬上限兜底。
    """

    def __init__(self, *, max_failures: int = 5, window_seconds: float = 900.0,
                 lock_seconds: float = 900.0, max_tracked: int = 10_000,
                 max_concurrent_verify: int = 8, clock=time.monotonic) -> None:
        self._max = max_failures
        self._window = window_seconds
        self._lock_secs = lock_seconds
        self._max_tracked = max_tracked
        self._clock = clock
        self._mutex = threading.Lock()
        self._failures: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}
        # 全局并发验证闸（Codex R1 审 P1）：per-username 限速挡不住「轮换随机
        # username」——每个未知名仍触发一次 600k 迭代 PBKDF2，突发可占满线程池+
        # CPU。此信号量把**同时进行的昂贵校验**全局封顶，与 username 无关；满则
        # 立即 429，绝不排队（排队=把 DoS 变成延迟仍占资源）。
        self._verify_sem = threading.BoundedSemaphore(max_concurrent_verify)

    def acquire_verify_slot(self) -> bool:
        """非阻塞占一个全局校验槽；返回 False=当前并发校验已满（429）。"""
        return self._verify_sem.acquire(blocking=False)

    def release_verify_slot(self) -> None:
        self._verify_sem.release()

    def _sweep(self, now: float) -> None:
        """驱逐过期锁与空窗口条目（持锁调用）。字典超硬顶时清掉全部过期项，
        仍超顶则整体清空（宁可放宽限速也不 OOM——限速非授权闸，兜底优先）。"""
        for u in [u for u, t in self._locked_until.items() if t <= now]:
            del self._locked_until[u]
        for u in list(self._failures.keys()):
            live = [t for t in self._failures[u] if now - t < self._window]
            if live:
                self._failures[u] = live
            else:
                del self._failures[u]
        if len(self._failures) + len(self._locked_until) > self._max_tracked:
            self._failures.clear()
            self._locked_until.clear()

    def reserve(self, username: str) -> bool:
        """原子「判锁+记尝试」：返回 True=可继续验证，False=已锁定（429）。
        每次调用先记一次尝试槽——第 max+1 次并发到来时窗口已满 → 拒。"""
        with self._mutex:
            now = self._clock()
            self._sweep(now)
            until = self._locked_until.get(username)
            if until is not None and now < until:
                return False
            window = [t for t in self._failures.get(username, []) if now - t < self._window]
            if len(window) >= self._max:
                # 锁定期从**达到阈值那次尝试**起算，而非当前时刻（Codex R3 审 P2）：
                # 否则 5 次失败在 t=0、第 6 次在 t=14min 才来时会从 t=14 起锁 15min
                # （锁到 t=29），把账户多关一倍。取第 max 次（阈值）尝试时间戳 + lock。
                threshold_ts = sorted(window)[self._max - 1]
                self._locked_until[username] = threshold_ts + self._lock_secs
                self._failures.pop(username, None)
                return False
            window.append(now)
            self._failures[username] = window
            return True

    def reset(self, username: str) -> None:
        with self._mutex:
            self._failures.pop(username, None)
            self._locked_until.pop(username, None)

    def cancel_reservation(self, username: str) -> None:
        """撤销本次 reserve 记下的最近一次尝试（Codex R4 审 P2）：基础设施错误
        （连接失败/database is locked 等非凭据失败）不该计入锁定——否则 5 次瞬时
        500 把账户虚假锁 15 分钟。只在真凭据失败时保留尝试槽。"""
        with self._mutex:
            attempts = self._failures.get(username)
            if attempts:
                attempts.pop()  # 弹出最近一次（本次 reserve 追加的）
                if not attempts:
                    self._failures.pop(username, None)

    # 兼容旧测试语义的只读探针（不改变状态）：窗口内尝试是否已达上限或锁定中
    def blocked(self, username: str) -> bool:
        with self._mutex:
            now = self._clock()
            until = self._locked_until.get(username)
            if until is not None and now < until:
                return True
            window = [t for t in self._failures.get(username, []) if now - t < self._window]
            return len(window) >= self._max
