"""FLAi-OS FastAPI 应用装配：create_app() 工厂 + uvicorn 入口 app。

lifespan 里做四件事：确保目录存在→init_db→两个 Registry scan+sync_to_db→
把共享对象挂 app.state，供各 api/*.py 路由通过 request.app.state 取用。
"""

from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .api import agents as agents_api
from .api import files as files_api
from .api import tasks as tasks_api
from .model_gateway.gateway import ModelGateway
from .runtime.registry import AgentRegistry
from .runtime.runtime import AgentRuntime
from .storage.db import get_conn, init_db
from .tools.registry import ToolRegistry

_PROFILES_PATH = Path(__file__).resolve().parent / "model_gateway" / "profiles.yaml"


def create_app(
    *,
    agents_dir: Path | None = None,
    tools_dir: Path | None = None,
    contracts_dir: Path | None = None,
    db_path: Path | str | None = None,
    uploads_dir: Path | None = None,
    task_runs_dir: Path | None = None,
) -> FastAPI:
    agents_dir = Path(agents_dir) if agents_dir is not None else config.AGENTS_DIR
    tools_dir = Path(tools_dir) if tools_dir is not None else config.TOOLS_DIR
    contracts_dir = Path(contracts_dir) if contracts_dir is not None else config.CONTRACTS_DIR
    db_path = Path(db_path) if db_path is not None else config.DB_PATH
    uploads_dir = Path(uploads_dir) if uploads_dir is not None else config.UPLOADS_DIR
    task_runs_dir = Path(task_runs_dir) if task_runs_dir is not None else config.TASK_RUNS_DIR

    def conn_factory() -> sqlite3.Connection:
        return get_conn(db_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        for d in (db_path.parent, uploads_dir, task_runs_dir):
            d.mkdir(parents=True, exist_ok=True)
        init_db(db_path)

        agent_registry = AgentRegistry(agents_dir, contracts_dir / "agent.schema.json")
        agent_registry.scan()
        tool_registry = ToolRegistry(tools_dir, contracts_dir / "tool.schema.json")
        tool_registry.scan()

        conn = conn_factory()
        try:
            agent_registry.sync_to_db(conn)
        finally:
            conn.close()

        model_gateway = ModelGateway(_PROFILES_PATH, conn_factory=conn_factory)
        runtime = AgentRuntime(agent_registry, tool_registry, model_gateway, conn_factory, task_runs_dir)

        app.state.agent_registry = agent_registry
        app.state.tool_registry = tool_registry
        app.state.model_gateway = model_gateway
        app.state.runtime = runtime
        app.state.conn_factory = conn_factory
        app.state.db_path = db_path
        app.state.uploads_dir = uploads_dir
        app.state.task_runs_dir = task_runs_dir

        yield

    app = FastAPI(title="FLAi-OS Backend", lifespan=lifespan)

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
        }

    app.include_router(agents_api.router)
    app.include_router(tasks_api.router)
    app.include_router(files_api.router)

    return app


app = create_app()
