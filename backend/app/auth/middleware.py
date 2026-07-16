"""default-deny 会话门（ADR-0019 D4）。

纯 ASGI 中间件（不经 BaseHTTPMiddleware）：不缓冲响应体，files.py 的
Range 下载响应与未来流式端点零影响。

覆盖面与放行面：
- `/api/*` 一律要求有效会话（含读接口）——新增路由默认落在门内，
  忘配置=被拒而非裸奔（fail-closed）。
- allowlist 仅 (POST, /api/auth/login) + (GET, /api/health)，精确匹配
  （带尾斜杠/大小写变体不在名单内=拒；大小写变体本就匹配不到 FastAPI 路由）。
- OPTIONS 只放行**真 preflight**（Origin + Access-Control-Request-Method
  双头齐全，由外层 CORSMiddleware 应答，不触达处理器）；裸 OPTIONS 落回
  默认拒绝——否则成为免鉴权的路由枚举探测面（loop-auditor F1）。
- 非 `/api/*`（静态资产 + SPA fallback）放行——登录页本身要能加载；
  数据面全部在 /api 下，SPA 回落只回 index.html/静态文件。
"""

from __future__ import annotations

import json
from http.cookies import SimpleCookie
from typing import Any, Callable

import anyio.to_thread

from .service import COOKIE_NAME, get_session_user

_ALLOWLIST = {("POST", "/api/auth/login"), ("GET", "/api/health"), ("GET", "/api/readyz")}

# FastAPI 把 schema/docs 注册在 /api 之外（Codex 审 P2）——不纳入门则未登录
# 者可拉取全量路由清单+请求模型，与「default-deny 防路由枚举」自相矛盾。
# 这几路要求有效会话（登录开发者仍可用 /docs）。
_PROTECTED_NON_API = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


class AuthGateMiddleware:
    def __init__(self, app: Any, conn_factory: Callable[[], Any]) -> None:
        self.app = app
        self._conn_factory = conn_factory

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # 应用内相对路径归一化（Codex 治理审 R1 P1，实测咬合）：ASGI 子挂载
        # （Starlette Mount("/prefix", app)）下，子 app 收到的 scope["path"] 含挂载
        # 前缀（"/prefix/api/..."）而前缀落在 root_path。若直接按裸 path 判 startswith
        # "/api/"，挂载后匿名请求会被误判为非 /api 面而放行——path-based 门不是
        # fail-closed。这里先剥掉 root_path 取应用内相对路径，任何挂载前缀下 /api
        # 面都稳定落在门内。root_path 为空（当前直服部署）时行为不变。
        raw_path: str = scope.get("path", "")
        root_path: str = scope.get("root_path", "") or ""
        if root_path and raw_path.startswith(root_path):
            path = raw_path[len(root_path):] or "/"
        else:
            path = raw_path
        method: str = scope.get("method", "").upper()
        guarded = path == "/api" or path.startswith("/api/") or path in _PROTECTED_NON_API
        if not guarded:
            await self.app(scope, receive, send)
            return
        if (method, path) in _ALLOWLIST:
            await self.app(scope, receive, send)
            return
        if method == "OPTIONS" and self._is_cors_preflight(scope):
            await self.app(scope, receive, send)
            return

        user = None
        token = self._session_token(scope)
        if token:
            # 同步 SQLite（连接+PRAGMA+查询）放到工作线程做（Codex R1 审 P2）：
            # 中间件跑在事件循环线程，锁争用/慢盘时同步 DB 调用会冻住所有 HTTP/
            # 静态/health 流量（不像 FastAPI 同步 handler 会被自动 offload）。
            user = await anyio.to_thread.run_sync(self._lookup_user, token)
        if user is None:
            body = json.dumps({"detail": "未登录或会话已过期"}, ensure_ascii=False).encode("utf-8")
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            })
            await send({"type": "http.response.body", "body": body})
            return

        # starlette Request.state 背靠 scope["state"]——处理器经 request.state.user 取用
        scope.setdefault("state", {})["user"] = user
        await self.app(scope, receive, send)

    def _lookup_user(self, token: str) -> Any:
        conn = self._conn_factory()
        try:
            return get_session_user(conn, token)
        finally:
            conn.close()

    @staticmethod
    def _is_cors_preflight(scope: Any) -> bool:
        """真 preflight 谓词（F1）：Origin 与 Access-Control-Request-Method 双头
        共存才算。裸 OPTIONS（缺任一头）不享受放行。"""
        names = {name for name, _ in scope.get("headers", [])}
        return (b"origin" in names) and (b"access-control-request-method" in names)

    @staticmethod
    def _session_token(scope: Any) -> str:
        for name, value in scope.get("headers", []):
            if name == b"cookie":
                jar = SimpleCookie()
                try:
                    jar.load(value.decode("latin-1"))
                except Exception:
                    return ""  # cookie 头畸形=没有凭据，拒（fail-closed），不 500
                morsel = jar.get(COOKIE_NAME)
                return morsel.value if morsel is not None else ""
        return ""
