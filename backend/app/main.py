"""FLAi-OS FastAPI 应用装配：create_app() 工厂 + uvicorn 入口 app。

lifespan 里做四件事：确保目录存在→init_db→bootstrap.assemble（三注册表 scan +
knowledge 对账 + sync_to_db，与 Job Runner 共享同一装配路径，ADR-0015）→
把共享对象挂 app.state，供各 api/*.py 路由通过 request.app.state 取用。
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .api import agents as agents_api
from .api import auth as auth_api
from .api import conversations as conversations_api
from .api import feedback as feedback_api
from .api import files as files_api
from .api import governance as governance_api
from .api import stats as stats_api
from .api import tasks as tasks_api
from .auth.middleware import AuthGateMiddleware
from .auth.service import LoginThrottle
from .bootstrap import assemble
from .logging_setup import configure_logging, reset_logging
from .runtime.conversation import ConversationService
from .runtime.runtime import AgentRuntime
from .storage.db import get_conn, init_db


def create_app(
    *,
    agents_dir: Path | None = None,
    tools_dir: Path | None = None,
    contracts_dir: Path | None = None,
    knowledge_dir: Path | None = None,
    db_path: Path | str | None = None,
    uploads_dir: Path | None = None,
    task_runs_dir: Path | None = None,
    frontend_dist_dir: Path | None = None,
) -> FastAPI:
    agents_dir = Path(agents_dir) if agents_dir is not None else config.AGENTS_DIR
    tools_dir = Path(tools_dir) if tools_dir is not None else config.TOOLS_DIR
    contracts_dir = Path(contracts_dir) if contracts_dir is not None else config.CONTRACTS_DIR
    knowledge_dir = Path(knowledge_dir) if knowledge_dir is not None else config.KNOWLEDGE_DIR
    db_path = Path(db_path) if db_path is not None else config.DB_PATH
    uploads_dir = Path(uploads_dir) if uploads_dir is not None else config.UPLOADS_DIR
    task_runs_dir = Path(task_runs_dir) if task_runs_dir is not None else config.TASK_RUNS_DIR
    frontend_dist_dir = (
        Path(frontend_dist_dir) if frontend_dist_dir is not None else config.FRONTEND_DIST_DIR
    )

    def conn_factory() -> sqlite3.Connection:
        return get_conn(db_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        for d in (db_path.parent, uploads_dir, task_runs_dir):
            d.mkdir(parents=True, exist_ok=True)
        # 进程日志 + 审计留痕（ADR-0023）：log_dir 派生 db_path.parent/logs——
        # 生产落 data/logs，测试落 tmp（per-test 隔离，零 conftest 改动，D3）。
        configure_logging(db_path.parent / "logs", process_tag="api")
        # try/finally 覆盖 configure 之后全部启动过程 + yield（Codex R0 P2-2）：
        # init_db/assemble/body 任一失败也必 reset_logging，绝不残留 handler/文件句柄。
        try:
            init_db(db_path)

            asm = assemble(
                agents_dir=agents_dir,
                tools_dir=tools_dir,
                contracts_dir=contracts_dir,
                knowledge_dir=knowledge_dir,
                conn_factory=conn_factory,
            )
            runtime = AgentRuntime(
                asm.agent_registry, asm.tool_registry, asm.model_gateway, conn_factory,
                task_runs_dir, knowledge_service=asm.knowledge_service, uploads_dir=uploads_dir,
                scope_registry=asm.scope_registry,  # ADR-0021 知识轴派生分级用
            )
            conversation_service = ConversationService(
                asm.agent_registry, asm.model_gateway, conn_factory, uploads_dir=uploads_dir,
            )

            app.state.agent_registry = asm.agent_registry
            app.state.tool_registry = asm.tool_registry
            app.state.scope_registry = asm.scope_registry
            app.state.knowledge_service = asm.knowledge_service
            app.state.model_gateway = asm.model_gateway
            app.state.runtime = runtime
            app.state.conversation_service = conversation_service
            app.state.conn_factory = conn_factory
            app.state.db_path = db_path
            app.state.uploads_dir = uploads_dir
            app.state.task_runs_dir = task_runs_dir
            app.state.agents_dir = agents_dir

            yield
        finally:
            # 退出复位（ADR-0023 D5）：移除本 app 所挂 handler + 恢复 logger 原态，
            # 杜绝跨测试泄漏（测试 with TestClient 退出即清）；生产仅进程退出时触发。
            reset_logging()

    app = FastAPI(title="FLAi-OS Backend", lifespan=lifespan)
    app.state.login_throttle = LoginThrottle()  # 进程内节流（ADR-0019 D6），实例随 app

    # 中间件栈序（后 add 者在外层）：会话门先 add（内层），CORS 后 add（外层）——
    # 401 响应也必须带 CORS 头，否则浏览器只报跨域、看不到「未登录」真话。
    app.add_middleware(AuthGateMiddleware, conn_factory=conn_factory)

    # M2 前端本机开发用任意端口，只放开 localhost。
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://localhost(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "agents": len(app.state.agent_registry.list()),
            "tools": len(app.state.tool_registry.list()),
            "llm_base_url_set": bool(os.environ.get("FLAI_LLM_BASE_URL")),
            "llm_api_key_set": bool(os.environ.get("FLAI_LLM_API_KEY")),
            "llm_model_reasoning_set": bool(os.environ.get("FLAI_LLM_MODEL_REASONING")),
            # B2 运行进程代际标记（ADR-0021/Codex R0-P1）：部署自检门据此见证
            # 「活着的进程」跑的是分级轴代码——只查 DB 列会漏掉「库已迁移但服务
            # 重启失败仍是旧进程」的假 PASS。仍是布尔位，不含数据。
            "classification_axis": True,
            # 迁移 #9 运行进程代际标记（Codex 治理审 P2 同款范式）：见证「活着的
            # API 进程」跑的是带 created_by_username 写入的代码。部署版本偏斜（worker/
            # 脚本已跑迁移、API 仍旧码）时旧 API 无此位 → 部署自检 FAIL，operator
            # 据此知 API 未重启，避免旧 API 静默造无归因 user 任务混入 legacy NULL 群。
            "created_by_username_axis": True,
            # 库身份指纹（Codex R1 审 P2）：自检门比对「服务实际连的库」与
            # 「探针检查的库」是否同一——FLAI_DB_PATH 两侧不一致时，探针查
            # 有账户的库 A、服务连空库 B，全部 PASS 却无人能登录。路径哈希
            # 不透出路径本身（opaque）；symlink 等价路径会误报不一致，错误
            # 方向是多拦（fail-closed 可接受）。
            "db_identity": hashlib.sha256(
                str(db_path.resolve()).encode("utf-8")
            ).hexdigest()[:16],
        }

    app.include_router(auth_api.router)
    app.include_router(agents_api.router)
    app.include_router(tasks_api.router)
    app.include_router(files_api.router)
    app.include_router(feedback_api.router)
    app.include_router(conversations_api.router)
    app.include_router(governance_api.router)
    app.include_router(stats_api.router)

    # M2 静态托管：frontend/dist 存在才注册（内网 Windows 免 node 部署；
    # 开发期 vite proxy 场景 dist 不在，静态路由整体缺席，行为与 M1 一致）。
    index_html = frontend_dist_dir / "index.html"
    if index_html.is_file():
        assets_dir = frontend_dist_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa_fallback(full_path: str) -> FileResponse:
            """SPA catch-all：真实静态文件按文件回，其余路径回 index.html
            （vue-router history 模式深链刷新）。/api/* 未匹配到路由的一律
            如实 404 JSON，绝不用 index.html 掩盖接口不存在。"""
            lowered = full_path.lower()
            if lowered == "api" or lowered.startswith("api/"):
                raise HTTPException(status_code=404, detail=f"接口不存在：/{full_path}")
            candidate = (frontend_dist_dir / full_path) if full_path else None
            if (
                candidate is not None
                and candidate.is_file()
                and candidate.resolve().is_relative_to(frontend_dist_dir.resolve())
            ):
                return FileResponse(candidate)
            return FileResponse(index_html)

    return app


app = create_app()
