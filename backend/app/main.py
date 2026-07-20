"""FLAi-OS FastAPI 应用装配：create_app() 工厂 + uvicorn 入口 app。

lifespan 里做四件事：确保目录存在→init_db→bootstrap.assemble（三注册表 scan +
knowledge 对账 + sync_to_db，与 Job Runner 共享同一装配路径，ADR-0015）→
把共享对象挂 app.state，供各 api/*.py 路由通过 request.app.state 取用。
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .api import agents as agents_api
from .api import auth as auth_api
from .api import conversations as conversations_api
from .api import design_promotions as design_promotions_api
from .api import feedback as feedback_api
from .api import files as files_api
from .api import governance as governance_api
from .api import knowledge as knowledge_api
from .api import me as me_api
from .api import search as search_api
from .api import stats as stats_api
from .api import tasks as tasks_api
from .api import teams as teams_api
from .auth.middleware import AuthGateMiddleware
from .auth.service import LoginThrottle
from .bootstrap import assemble
from .logging_setup import configure_logging, reset_logging
from .runtime.conversation import ConversationService
from .runtime.jerryagent_adapter import (
    build_agent_execution_router,
    build_jerryagent_facts_reader,
)
from .runtime.runtime import AgentRuntime
from .design_promotion.service import DesignPromotionService
from .design_promotion.targets import TargetRegistry
from .storage import repos
from .storage.db import get_conn, init_db
from .storage.execution_binding_schema import (
    EXECUTION_BINDING_SCHEMA_WITNESS_KEYS as _EXECUTION_BINDING_SCHEMA_WITNESS_KEYS,
)
from .storage.execution_binding_schema import (
    execution_binding_schema_witnesses as _execution_binding_schema_witnesses,
)
from .storage.conversation_lifecycle_schema import (
    CONVERSATION_LIFECYCLE_SCHEMA_WITNESS_KEYS as _CONVERSATION_LIFECYCLE_SCHEMA_WITNESS_KEYS,
)
from .storage.conversation_lifecycle_schema import (
    conversation_lifecycle_schema_witnesses as _conversation_lifecycle_schema_witnesses,
)
from .storage.p23_schema import (
    P23_SCHEMA_WITNESS_KEYS as _P23_SCHEMA_WITNESS_KEYS,
)
from .storage.p23_schema import p23_schema_witnesses as _p23_schema_witnesses
from .storage.review_route_schema import (
    REVIEW_ROUTE_SCHEMA_WITNESS_KEYS as _REVIEW_ROUTE_SCHEMA_WITNESS_KEYS,
)
from .storage.review_route_schema import (
    review_route_schema_witnesses as _review_route_schema_witnesses,
)
from .storage.outcome_schema import (
    OUTCOME_SCHEMA_WITNESS_KEYS as _OUTCOME_SCHEMA_WITNESS_KEYS,
)
from .storage.outcome_schema import (
    outcome_schema_witnesses as _outcome_schema_witnesses,
)
from .storage.review_schema import (
    JUDGMENT_SCHEMA_WITNESS_KEYS as _JUDGMENT_SCHEMA_WITNESS_KEYS,
)
from .storage.review_schema import (
    judgment_schema_witnesses as _judgment_schema_witnesses,
)
from .storage.design_promotion_schema import (
    DESIGN_PROMOTION_SCHEMA_WITNESS_KEYS as _DESIGN_PROMOTION_SCHEMA_WITNESS_KEYS,
)
from .storage.design_promotion_schema import (
    design_promotion_schema_witnesses as _design_promotion_schema_witnesses,
)

_WORKER_STALE_S = 60  # 与 deploy_selfcheck 同口径：心跳超 60s 视为 worker 已死/挂起


def _worker_freshness(conn: sqlite3.Connection) -> dict[str, object]:
    """P0-M2†（导入准入门）：worker 心跳新鲜度（复用 worker_heartbeats 表）。
    naive/畸形时间戳一律 fail-closed 判不新鲜（宁误报死，不假报活）。"""
    hb = repos.get_worker_heartbeat(conn)
    if hb is None:
        return {
            "present": False,
            "fresh": False,
            "age_s": None,
            "generation": None,
            "execution_bindings": None,
        }
    generation = hb.get("generation")
    execution_bindings = hb.get("execution_bindings")
    try:
        beat_time = datetime.fromisoformat(str(hb.get("last_beat_at")))
    except (ValueError, TypeError):
        return {"present": True, "fresh": False, "age_s": None,
                "generation": generation, "execution_bindings": execution_bindings,
                "reason": "timestamp_malformed"}
    if beat_time.tzinfo is None:
        return {"present": True, "fresh": False, "age_s": None,
                "generation": generation, "execution_bindings": execution_bindings,
                "reason": "naive_timestamp"}
    age = (datetime.now(timezone.utc) - beat_time).total_seconds()
    fresh = -5.0 <= age <= float(_WORKER_STALE_S)
    return {
        "present": True,
        "fresh": fresh,
        "age_s": round(age, 1),
        "generation": generation,
        "execution_bindings": execution_bindings,
    }


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
    design_target_root: Path | None = None,
    design_promotion_runtime_dir: Path | None = None,
    design_targets: TargetRegistry | None = None,
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
    design_target_root = (
        Path(design_target_root)
        if design_target_root is not None
        else config.REPO_ROOT
    )
    design_promotion_runtime_dir = (
        Path(design_promotion_runtime_dir)
        if design_promotion_runtime_dir is not None
        else config.DATA_DIR / "design_promotions"
    )
    # No production target/frame matrix is guessed.  Deployments must inject a
    # closed registry after provisioning exact current PNG references; the
    # default empty registry fails comparison creation explicitly.
    design_targets = design_targets if design_targets is not None else TargetRegistry()

    def conn_factory() -> sqlite3.Connection:
        return get_conn(db_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        config.assert_local_db_path(db_path)  # P0-B2：DB 必须本地固定盘，否则 fail-closed 拒启
        for d in (
            db_path.parent,
            uploads_dir,
            task_runs_dir,
            design_promotion_runtime_dir,
        ):
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
            execution_router = build_agent_execution_router()
            jerryagent_facts_reader = build_jerryagent_facts_reader()
            runtime = AgentRuntime(
                asm.agent_registry, asm.tool_registry, asm.model_gateway, conn_factory,
                task_runs_dir, knowledge_service=asm.knowledge_service, uploads_dir=uploads_dir,
                scope_registry=asm.scope_registry,  # ADR-0021 知识轴派生分级用
                execution_router=execution_router,
            )
            conversation_service = ConversationService(
                asm.agent_registry, asm.model_gateway, conn_factory, uploads_dir=uploads_dir,
            )

            def apply_design_human_review(
                conn: sqlite3.Connection, **kwargs: object
            ) -> dict[str, object]:
                task, _sample_rows = repos.apply_human_review_in_transaction(
                    conn,
                    str(kwargs["task_id"]),
                    decision_id=str(kwargs["decision_id"]),
                    action=str(kwargs["action"]),
                    reviewer_display_name=str(kwargs["reviewer_display_name"]),
                    reviewer_username=str(kwargs["reviewer_username"]),
                    reason_code=(
                        str(kwargs["reason_code"])
                        if kwargs.get("reason_code") is not None
                        else None
                    ),
                    comment=(
                        str(kwargs["comment"])
                        if kwargs.get("comment") is not None
                        else None
                    ),
                )
                return task

            design_promotion_service = DesignPromotionService(
                conn_factory=conn_factory,
                task_runs_dir=task_runs_dir,
                target_root=design_target_root,
                promotion_runtime_dir=design_promotion_runtime_dir,
                targets=design_targets,
                human_review_applier=apply_design_human_review,
            )

            app.state.agent_registry = asm.agent_registry
            app.state.tool_registry = asm.tool_registry
            app.state.scope_registry = asm.scope_registry
            app.state.knowledge_service = asm.knowledge_service
            app.state.model_gateway = asm.model_gateway
            app.state.runtime = runtime
            app.state.execution_router = execution_router
            app.state.jerryagent_facts_reader = jerryagent_facts_reader
            app.state.conversation_service = conversation_service
            app.state.design_promotion_service = design_promotion_service
            app.state.conn_factory = conn_factory
            app.state.db_path = db_path
            app.state.uploads_dir = uploads_dir
            app.state.task_runs_dir = task_runs_dir
            app.state.agents_dir = agents_dir
            app.state.design_target_root = design_target_root
            app.state.design_promotion_runtime_dir = design_promotion_runtime_dir

            yield
        finally:
            runtime = getattr(app.state, "runtime", None)
            if runtime is not None:
                runtime.close()
            facts_reader = getattr(app.state, "jerryagent_facts_reader", None)
            if facts_reader is not None:
                facts_reader.close()
            # 退出复位（ADR-0023 D5）：移除本 app 所挂 handler + 恢复 logger 原态，
            # 杜绝跨测试泄漏（测试 with TestClient 退出即清）；生产仅进程退出时触发。
            reset_logging()

    app = FastAPI(title="FLAi-OS Backend", lifespan=lifespan)
    app.state.login_throttle = LoginThrottle()  # 进程内节流（ADR-0019 D6），实例随 app
    # P2.4 cursor 是短生命周期 UI 分页凭证。单实例部署进程内随机 HMAC key
    # 阻止客户端改写 snapshot/keyset；服务重启后旧 cursor 响亮 422，重新搜索即可。
    app.state.search_cursor_signing_key = secrets.token_bytes(32)

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
        try:
            conn = conn_factory()
            try:
                p23_schema_witnesses = _p23_schema_witnesses(conn)
                execution_binding_schema_witnesses = (
                    _execution_binding_schema_witnesses(conn)
                )
                conversation_lifecycle_schema_witnesses = (
                    _conversation_lifecycle_schema_witnesses(conn)
                )
                review_route_schema_witnesses = _review_route_schema_witnesses(conn)
                judgment_schema_witnesses = _judgment_schema_witnesses(conn)
                outcome_schema_witnesses = _outcome_schema_witnesses(conn)
                design_promotion_schema_witnesses = (
                    _design_promotion_schema_witnesses(conn)
                )
            finally:
                conn.close()
        except sqlite3.Error:
            p23_schema_witnesses = {
                key: False for key in _P23_SCHEMA_WITNESS_KEYS
            }
            execution_binding_schema_witnesses = {
                key: False for key in _EXECUTION_BINDING_SCHEMA_WITNESS_KEYS
            }
            conversation_lifecycle_schema_witnesses = {
                key: False
                for key in _CONVERSATION_LIFECYCLE_SCHEMA_WITNESS_KEYS
            }
            review_route_schema_witnesses = {
                key: False for key in _REVIEW_ROUTE_SCHEMA_WITNESS_KEYS
            }
            judgment_schema_witnesses = {
                key: False for key in _JUDGMENT_SCHEMA_WITNESS_KEYS
            }
            outcome_schema_witnesses = {
                key: False for key in _OUTCOME_SCHEMA_WITNESS_KEYS
            }
            design_promotion_schema_witnesses = {
                key: False for key in _DESIGN_PROMOTION_SCHEMA_WITNESS_KEYS
            }
        return {
            "status": "ok",
            "agents": len(app.state.agent_registry.list()),
            "tools": len(app.state.tool_registry.list()),
            "llm_base_url_set": bool(os.environ.get("FLAI_LLM_BASE_URL")),
            "llm_api_key_set": bool(os.environ.get("FLAI_LLM_API_KEY")),
            "llm_model_reasoning_set": bool(os.environ.get("FLAI_LLM_MODEL_REASONING")),
            # 配置见证，不冒充侧车在线：真实 identity/revision 仅在任务执行的
            # preflight 与不可变 agent_log receipt 中确立。
            "agent_layer_axis": True,
            "agent_layer": {
                "contract": "flai.agent-layer.v1",
                "bindings": [
                    {"adapter": adapter, "contract_version": contract}
                    for adapter, contract in sorted(app.state.execution_router.bindings)
                ],
                "jerryagent_configured": (
                    ("jerryagent_sidecar", "flai.agent-layer.v1")
                    in app.state.execution_router.bindings
                ),
                "runtime_attested": False,
                "schema_witnesses": execution_binding_schema_witnesses,
            },
            # B2 运行进程代际标记（ADR-0021/Codex R0-P1）：部署自检门据此见证
            # 「活着的进程」跑的是分级轴代码——只查 DB 列会漏掉「库已迁移但服务
            # 重启失败仍是旧进程」的假 PASS。仍是布尔位，不含数据。
            "classification_axis": True,
            # 迁移 #9 运行进程代际标记（Codex 治理审 P2 同款范式）：见证「活着的
            # API 进程」跑的是带 created_by_username 写入的代码。部署版本偏斜（worker/
            # 脚本已跑迁移、API 仍旧码）时旧 API 无此位 → 部署自检 FAIL，operator
            # 据此知 API 未重启，避免旧 API 静默造无归因 user 任务混入 legacy NULL 群。
            "created_by_username_axis": True,
            # P2.3 专属活进程代际：不复用更早的 task username 轴。
            # schema witnesses 每次从服务实际连接的库读取，只证明三张表的
            # identity/约束/索引/触发器合同，不宣称存量 owner 或 Question 数据完整。
            "structured_question_axis": True,
            # P2.6 活进程代际：会话 status 与 visibility 正交，所有 lifecycle
            # mutation 经 CAS + append-only ledger。具体投影、表、trigger 与存量链
            # 由 served-DB exact witnesses 证明，布尔代际本身不作完整性声明。
            "conversation_lifecycle_axis": True,
            # P2.4 活进程代际：精确 owner、稳定消息/产物地址、服务端有界搜索已接线。
            # 这不是 DB schema 完整性见证，只用于阻断新 QuickSwitcher 连上旧 API。
            "search_addressing_axis": True,
            # P2.5 活进程代际：点名只是路由，不是签发权限。列/索引/guard
            # 必须另由 exact served-DB witnesses 证明。
            "named_review_inbox_axis": True,
            # M4 前判断资产化代际：活 API 已接结构化人签账本。具体表、索引与只追加
            # trigger 必须另由 exact schema witnesses 证明，不能只凭此布尔位假绿。
            "judgment_capture_axis": True,
            # ADR-0036 活 API 代际 + exact served-DB schema 双见证。worker 侧
            # pipeline writer 另由 WORKER_GENERATION 心跳咬合，拒绝新 API/DB 配旧 worker。
            "outcome_telemetry_axis": True,
            "outcome_telemetry_generation": config.OUTCOME_TELEMETRY_GENERATION,
            # P2.8 only witnesses this disabled-sensitive trial generation and
            # its exact ledgers.  It does not claim a live Open Design daemon,
            # role enforcement, declassification, or provisioned target matrix.
            "design_promotion_axis": True,
            "design_promotion_generation": config.DESIGN_PROMOTION_GENERATION,
            "p23_schema_witnesses": p23_schema_witnesses,
            "conversation_lifecycle_schema_witnesses": (
                conversation_lifecycle_schema_witnesses
            ),
            "review_route_schema_witnesses": review_route_schema_witnesses,
            "judgment_schema_witnesses": judgment_schema_witnesses,
            "outcome_schema_witnesses": outcome_schema_witnesses,
            "design_promotion_schema_witnesses": (
                design_promotion_schema_witnesses
            ),
            # T2/#5 不可变快照代际标记（Codex R0 审 P1 同款范式）：见证「活着的 API
            # 进程」跑的是 enqueue 冻结快照的代码。分离部署偏斜（DB 已迁移出 eval_snapshots
            # 表、worker 已更新，API 仍是 T1 旧码不冻结）时旧 API 无此位 → 部署自检 FAIL，
            # operator 据此知 API 未重启；否则旧 API 入队无 handle 的 run、worker 回退活磁盘，
            # 不可变保证静默失效。仍是布尔位，不含数据。
            "eval_snapshot_axis": True,
            # 库身份指纹（Codex R1 审 P2）：自检门比对「服务实际连的库」与
            # 「探针检查的库」是否同一——FLAI_DB_PATH 两侧不一致时，探针查
            # 有账户的库 A、服务连空库 B，全部 PASS 却无人能登录。路径哈希
            # 不透出路径本身（opaque）；symlink 等价路径会误报不一致，错误
            # 方向是多拦（fail-closed 可接受）。
            "db_identity": hashlib.sha256(
                str(db_path.resolve()).encode("utf-8")
            ).hexdigest()[:16],
        }

    @app.get("/api/readyz")
    def readyz() -> JSONResponse:
        """P0-M2†（导入准入门）：就绪探针——worker 心跳新鲜才 200，过期/缺失/畸形 503
        （不再假 200）。外部 uptime 监控轮此端点即知 worker 死活；/api/health 仍是 API
        存活探针（恒 200）。单 worker 串行下一条死 worker=全部门队列静默停摆，此端点把
        MTTD 从数小时压到一个轮询周期。"""
        conn = conn_factory()
        try:
            wf = _worker_freshness(conn)
            p23_schema_witnesses = _p23_schema_witnesses(conn)
            execution_binding_schema_witnesses = (
                _execution_binding_schema_witnesses(conn)
            )
            conversation_lifecycle_schema_witnesses = (
                _conversation_lifecycle_schema_witnesses(conn)
            )
            review_route_schema_witnesses = _review_route_schema_witnesses(conn)
            judgment_schema_witnesses = _judgment_schema_witnesses(conn)
            outcome_schema_witnesses = _outcome_schema_witnesses(conn)
            design_promotion_schema_witnesses = (
                _design_promotion_schema_witnesses(conn)
            )
        finally:
            conn.close()
        p23_schema_ready = all(
            p23_schema_witnesses.get(key) is True
            for key in _P23_SCHEMA_WITNESS_KEYS
        )
        execution_binding_schema_ready = all(
            execution_binding_schema_witnesses.get(key) is True
            for key in _EXECUTION_BINDING_SCHEMA_WITNESS_KEYS
        )
        conversation_lifecycle_schema_ready = all(
            conversation_lifecycle_schema_witnesses.get(key) is True
            for key in _CONVERSATION_LIFECYCLE_SCHEMA_WITNESS_KEYS
        )
        review_route_schema_ready = all(
            review_route_schema_witnesses.get(key) is True
            for key in _REVIEW_ROUTE_SCHEMA_WITNESS_KEYS
        )
        judgment_schema_ready = all(
            judgment_schema_witnesses.get(key) is True
            for key in _JUDGMENT_SCHEMA_WITNESS_KEYS
        )
        outcome_schema_ready = all(
            outcome_schema_witnesses.get(key) is True
            for key in _OUTCOME_SCHEMA_WITNESS_KEYS
        )
        design_promotion_schema_ready = all(
            design_promotion_schema_witnesses.get(key) is True
            for key in _DESIGN_PROMOTION_SCHEMA_WITNESS_KEYS
        )
        worker_generation_ready = (
            wf.get("generation") == config.WORKER_GENERATION
        )
        api_execution_bindings = repos.canonical_worker_execution_bindings(
            app.state.execution_router.bindings
        )
        worker_execution_bindings_ready = (
            wf.get("execution_bindings") == api_execution_bindings
        )
        wf["generation_ready"] = worker_generation_ready
        wf["expected_generation"] = config.WORKER_GENERATION
        wf["execution_bindings_ready"] = worker_execution_bindings_ready
        wf["expected_execution_bindings"] = api_execution_bindings
        ready = (
            wf["fresh"] is True
            and worker_generation_ready is True
            and worker_execution_bindings_ready is True
            and execution_binding_schema_ready is True
            and p23_schema_ready is True
            and conversation_lifecycle_schema_ready is True
            and review_route_schema_ready is True
            and judgment_schema_ready is True
            and outcome_schema_ready is True
            and design_promotion_schema_ready is True
        )
        return JSONResponse(
            {
                "status": "ready" if ready is True else "degraded",
                "worker": wf,
                "agent_layer_axis": True,
                "agent_layer": {
                    "runtime_generation": True,
                    "contract": "flai.agent-layer.v1",
                    "bindings": api_execution_bindings,
                    "worker_bindings": wf.get("execution_bindings"),
                    "worker_binding_ready": worker_execution_bindings_ready,
                    "schema_ready": execution_binding_schema_ready,
                    "schema_witnesses": execution_binding_schema_witnesses,
                },
                "structured_question_axis": True,
                "conversation_lifecycle_axis": True,
                "search_addressing_axis": True,
                "named_review_inbox_axis": True,
                "judgment_capture_axis": True,
                "outcome_telemetry_axis": True,
                "outcome_telemetry_generation": config.OUTCOME_TELEMETRY_GENERATION,
                "design_promotion_axis": True,
                "design_promotion_generation": config.DESIGN_PROMOTION_GENERATION,
                "p23": {
                    "runtime_generation": True,
                    "schema_ready": p23_schema_ready,
                    "schema_witnesses": p23_schema_witnesses,
                },
                "conversation_lifecycle": {
                    "runtime_generation": True,
                    "schema_ready": conversation_lifecycle_schema_ready,
                    "schema_witnesses": conversation_lifecycle_schema_witnesses,
                },
                "named_review_inbox": {
                    "runtime_generation": True,
                    "schema_ready": review_route_schema_ready,
                    "schema_witnesses": review_route_schema_witnesses,
                },
                "judgment_capture": {
                    "runtime_generation": True,
                    "schema_ready": judgment_schema_ready,
                    "schema_witnesses": judgment_schema_witnesses,
                },
                "outcome_telemetry": {
                    "runtime_generation": True,
                    "generation": config.OUTCOME_TELEMETRY_GENERATION,
                    "schema_ready": outcome_schema_ready,
                    "schema_witnesses": outcome_schema_witnesses,
                    "worker_generation_ready": worker_generation_ready,
                },
                "design_promotion": {
                    "runtime_generation": True,
                    "generation": config.DESIGN_PROMOTION_GENERATION,
                    "schema_ready": design_promotion_schema_ready,
                    "schema_witnesses": design_promotion_schema_witnesses,
                },
            },
            status_code=200 if ready is True else 503,
        )

    app.include_router(auth_api.router)
    app.include_router(agents_api.router)
    app.include_router(tasks_api.router)
    app.include_router(files_api.router)
    app.include_router(feedback_api.router)
    app.include_router(conversations_api.router)
    app.include_router(design_promotions_api.router)
    app.include_router(governance_api.router)
    app.include_router(stats_api.router)
    app.include_router(me_api.router)
    app.include_router(search_api.router)
    app.include_router(knowledge_api.router)
    app.include_router(teams_api.router)

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
