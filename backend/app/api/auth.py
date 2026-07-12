"""鉴权接口（ADR-0019）：login / logout / me。

- login 在 default-deny 中间件 allowlist 内（不然没人能登录）；
  logout/me 在门内——无会话打 me 就该 401，这本身是登录态探针。
- 凭据错误与账户停用同码同文案（不泄露账户存在性）；节流 429。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ..auth import service
from ..logging_setup import audit_event

router = APIRouter(prefix="/api/auth", tags=["auth"])

_COOKIE_MAX_AGE = int(service.SESSION_TTL.total_seconds())


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
    throttle = request.app.state.login_throttle
    username = body.username.strip()
    # 顺序：全局并发闸 → per-username 限速 → 校验（Codex R2 审 P2）。全局闸必须
    # 先于 reserve——否则「服务繁忙 429」也会占掉一次尝试槽，真实账户被 5 次
    # 繁忙响应锁死 15 分钟（无一次真正查密码=虚假锁定）。繁忙分支不记尝试。
    if throttle.acquire_verify_slot() is not True:
        raise HTTPException(status_code=429, detail="登录服务繁忙，请稍后再试")
    try:
        # 原子 reserve-before-verify（Codex 审 P1）：并发突发在慢 PBKDF2 前各自
        # 占尝试槽，第 max+1 次必被锁——check-then-act 竞态不存在。
        if throttle.reserve(username) is not True:
            audit_event("login", actor=username, outcome="throttled", reason="rate-limited")
            raise HTTPException(status_code=429, detail="尝试次数过多，请 15 分钟后再试")
        try:
            conn = request.app.state.conn_factory()
        except Exception:
            # 连接层失败=基础设施错误，非凭据失败——撤销本次尝试槽（Codex R4 审 P2），
            # 否则瞬时故障期的 500 会把账户虚假锁定 15 分钟。
            throttle.cancel_reservation(username)
            raise
        try:
            # 原子校验+签发（Codex R2 审 P1）：闭合「校验后、插会话前凭据被改/
            # 停用」的 TOCTOU——open_session_for_credentials 在写锁内复查凭据。
            try:
                result = service.open_session_for_credentials(conn, username, body.password)
            except Exception:
                # 校验/签发过程的意外异常（database is locked 等基础设施错误）撤销
                # 尝试槽再上抛——只有真凭据失败（result is None）才保留槽（Codex R4 审 P2）。
                throttle.cancel_reservation(username)
                raise
            if result is None:
                # 尝试槽已在 reserve 记下，失败无需再记（这正是并发绕过的修复点）
                audit_event("login", actor=username, outcome="failure", reason="bad-credentials")
                raise HTTPException(status_code=401, detail="用户名或密码错误")
            user, token = result
            throttle.reset(username)
            # 过期会话清理是机会性的，与登录成败解耦（Codex R4 审 P2）：会话已提交、
            # cookie 尚未下发，若清理撞另一写者的 busy timeout 抛错，会 500 掉一次
            # 已成功的登录并留下客户端拿不到 token 的孤儿会话行。清理失败不致命。
            try:
                service.purge_expired_sessions(conn)
            except Exception:
                pass  # 孤儿过期行由下次登录/恢复清理，绝不拖累本次成功登录
        finally:
            conn.close()
    finally:
        throttle.release_verify_slot()
    audit_event("login", actor=user["username"], outcome="success")
    # Secure=False 如实声明：内网 HTTP 明文部署，传输层加密在部署层（ADR-0019 D3）
    response.set_cookie(
        service.COOKIE_NAME, token, max_age=_COOKIE_MAX_AGE,
        httponly=True, samesite="lax", path="/",
    )
    return {"username": user["username"], "display_name": user["display_name"]}


@router.post("/logout")
def logout(request: Request, response: Response) -> dict[str, str]:
    token = request.cookies.get(service.COOKIE_NAME, "")
    conn = request.app.state.conn_factory()
    try:
        service.delete_session(conn, token)  # 服务端即时作废，非仅清 cookie
    finally:
        conn.close()
    audit_event("logout", actor=request.state.user["username"], outcome="success")
    response.delete_cookie(service.COOKIE_NAME, path="/")
    return {"detail": "已退出登录"}


@router.get("/me")
def me(request: Request) -> dict[str, Any]:
    user = request.state.user  # default-deny 中间件已验证并注入；无会话到不了这里
    return {"username": user["username"], "display_name": user["display_name"]}
