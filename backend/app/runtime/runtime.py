"""Agent Runtime：驱动单个任务从 validating 走完整生命周期（docs/05）。

状态机口径说明（偏离 M1 接口契约文字、以 docs/05 + 已交付 statemachine.py 为准，
详见本文件末尾模块级注释）：`running` 成功收尾时**不**直接转 `completed`，
而是先经 `analyzing` 再转 `completed`——docs/05 §2 强制规则原文：
「`running` 不得跳过 `analyzing` 直接进入 `completed`……即使 Agent 没有独立的
"分析"业务逻辑（如 hello_agent），也必须显式迁移，不得省略」，且
`backend/app/core/statemachine.py` 的 TRANSITIONS 里 `running` 集合本就不含
`completed`（该文件已由地基路先行交付并如此实现，若走"running 直转 completed"
会被 `assert_transition` 拒绝，技术上也走不通）。
"""

from __future__ import annotations

import hashlib
import importlib.util
import logging
import re
import sqlite3
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Callable

from ..core.errors import FileIntegrityError, KnowledgeScopeDeniedError, ToolNotAllowedError
from ..storage import repos
from ..storage.file_integrity import open_verified_file

logger = logging.getLogger(__name__)

# event.schema.json 的 event_type 枚举（供折叠判断参考；本文件不据此做「豁免」——
# ADR-0008 原文「workflow 自定义事件统一折叠为 agent_log」是无条件折叠，见
# `_WorkflowEventLogger.log()`，这里留作文档标注用途）。
_EVENT_ENUM = frozenset(
    {
        "task_created", "validation_started", "validation_failed", "case_generated",
        "tool_started", "tool_finished", "tool_failed", "model_call",
        "review_requested", "review_approved", "review_rejected", "summary_generated",
        "task_completed", "task_failed", "task_cancelled", "feedback_received",
        "knowledge_search", "warning", "error", "agent_log",
    }
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class _WorkflowEventLogger:
    """context["event_logger"]：workflow.py 唯一可见的事件出口。

    ADR-0008：「workflow 自定义事件统一折叠为 agent_log」——无条件折叠，
    原始类型进 payload.workflow_event_type，事件枚举不因业务 Agent 膨胀。
    """

    def __init__(self, conn: sqlite3.Connection, task_id: str, agent_id: str) -> None:
        self._conn = conn
        self._task_id = task_id
        self._agent_id = agent_id

    def log(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        payload = dict(payload or {})
        payload["workflow_event_type"] = event_type
        repos.append_event(
            self._conn,
            task_id=self._task_id,
            agent_id=self._agent_id,
            event_type="agent_log",
            level="info",
            message=f"workflow 上报事件：{event_type}",
            payload=payload,
        )


class _ToolRegistryContext:
    """context["tool_registry"]：包一层，自动带 conn/task_id，前后发 tool_started/finished|failed。

    P1-A default-deny：构造时锁定 agent.yaml.tools 白名单（frozenset），call()
    第一步先查白名单——工具即使已在 Tool Registry 注册，不在本 Agent 白名单内
    一律拒绝并留 tool_failed 事件（任务书铁律：新注册工具绝不自动扩大存量
    Agent 的权限面）。
    """

    def __init__(
        self,
        tool_registry: Any,
        conn: sqlite3.Connection,
        task_id: str,
        agent_id: str,
        allowed_tools: frozenset[str],
    ) -> None:
        self._tool_registry = tool_registry
        self._conn = conn
        self._task_id = task_id
        self._agent_id = agent_id
        self._allowed_tools = allowed_tools

    def call(self, tool_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if tool_id not in self._allowed_tools:
            message = (
                f"工具 {tool_id} 不在 Agent {self._agent_id} 的 agent.yaml.tools 白名单内，"
                "default-deny 拒绝调用"
            )
            repos.append_event(
                self._conn, task_id=self._task_id, agent_id=self._agent_id,
                event_type="tool_failed", level="error",
                message=message,
                payload={"tool_id": tool_id, "denied": "not_in_agent_whitelist"},
            )
            raise ToolNotAllowedError(message)

        repos.append_event(
            self._conn, task_id=self._task_id, agent_id=self._agent_id,
            event_type="tool_started", level="info",
            message=f"开始调用工具 {tool_id}", payload={"tool_id": tool_id, "input": payload},
        )
        try:
            result = self._tool_registry.call(tool_id, payload, conn=self._conn, task_id=self._task_id)
        except Exception as exc:
            repos.append_event(
                self._conn, task_id=self._task_id, agent_id=self._agent_id,
                event_type="tool_failed", level="error",
                message=f"工具 {tool_id} 调用失败：{exc}", payload={"tool_id": tool_id, "error": str(exc)},
            )
            raise
        # P2-2：工具契约的可恢复失败（status:"failed"，不抛异常）如实记 tool_failed，
        # 不得误报 tool_finished 让时间轴显示成功。判定用 == 比较，不用 truthiness。
        if result.get("status") == "failed":
            error_summary = str(result.get("error_message") or "")[:200]
            repos.append_event(
                self._conn, task_id=self._task_id, agent_id=self._agent_id,
                event_type="tool_failed", level="error",
                message=f"工具 {tool_id} 返回失败态：{error_summary or '无 error_message'}",
                payload={
                    "tool_id": tool_id,
                    "output_status": result.get("status"),
                    "error": error_summary,
                },
            )
            return result
        repos.append_event(
            self._conn, task_id=self._task_id, agent_id=self._agent_id,
            event_type="tool_finished", level="info",
            message=f"工具 {tool_id} 调用完成", payload={"tool_id": tool_id, "output_status": result.get("status")},
        )
        return result


class _ModelGatewayContext:
    """context["model_gateway"]：包一层，自动带 task_id/agent_id。

    model_calls **表**落库由 Gateway 自身负责；但任务时间轴的 model_call **事件**
    是本层职责（P2-1：「无事件=没发生」——模型调用成败必须在任务事件流可见，
    不能只藏在 model_calls 表里）。成功发 info 级 model_call；上游抛异常发
    error 级 model_call 后原样 re-raise，绝不吞异常。
    """

    def __init__(self, model_gateway: Any, conn: sqlite3.Connection, task_id: str, agent_id: str) -> None:
        self._model_gateway = model_gateway
        self._conn = conn
        self._task_id = task_id
        self._agent_id = agent_id

    # 归因键由 wrapper 钉死，workflow 不得经 kwargs 透传/覆写（Codex R0 P1-5）：尤其
    # conversation_id——job 模型调用只归因 task，透传它会在 model_calls 造「同时带
    # task_id + conversation_id」双归因行，经 GET /conversations/{id}/model_calls 旁路
    # 遮蔽门泄漏 sensitive summary。task_id/agent_id 同理（否则与显式实参重复致 TypeError）。
    _FORBIDDEN_ATTR_KWARGS = ("task_id", "agent_id", "conversation_id")

    def _sanitize(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in kwargs.items() if k not in self._FORBIDDEN_ATTR_KWARGS}

    def _call(self, kind: str, profile: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        try:
            result = fn()
        except Exception as exc:
            repos.append_event(
                self._conn, task_id=self._task_id, agent_id=self._agent_id,
                event_type="model_call", level="error",
                message=f"模型调用失败（{kind}，profile={profile}）：{exc}",
                payload={"profile": profile, "kind": kind, "error": str(exc)[:500]},
            )
            raise
        repos.append_event(
            self._conn, task_id=self._task_id, agent_id=self._agent_id,
            event_type="model_call", level="info",
            message=f"模型调用完成（{kind}，profile={profile}）",
            payload={"profile": profile, "kind": kind},
        )
        return result

    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        safe = self._sanitize(kwargs)
        return self._call(
            "chat", profile,
            lambda: self._model_gateway.chat(
                profile, messages, task_id=self._task_id, agent_id=self._agent_id, **safe
            ),
        )

    def embed(self, profile: str, text: str, **kwargs: Any) -> dict[str, Any]:
        safe = self._sanitize(kwargs)
        return self._call(
            "embed", profile,
            lambda: self._model_gateway.embed(
                profile, text, task_id=self._task_id, agent_id=self._agent_id, **safe
            ),
        )

    def vision(self, profile: str, image_path: str, prompt: str, **kwargs: Any) -> dict[str, Any]:
        safe = self._sanitize(kwargs)
        return self._call(
            "vision", profile,
            lambda: self._model_gateway.vision(
                profile, image_path, prompt, task_id=self._task_id, agent_id=self._agent_id, **safe
            ),
        )


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _task_input_classification(conn: sqlite3.Connection, task: dict[str, Any]) -> str:
    """任务级派生分级（ADR-0021 D3 污点传播）：产物/样本继承此值。

    三个 fail-closed 分支：无输入文件 → internal（无污点源）；输入记录缺失 →
    sensitive（出处不可考，宁严勿洗白）；任一记录分级非 internal（含未知坏值，
    allowlist 判定）→ sensitive。无条件基于 task.input_file_ids 现查 DB，不依赖
    _open_input_files 副作用（设计审 F6：schema 校验先失败时 verified_files 恒空）。
    """
    file_ids = task.get("input_file_ids") or []
    if not file_ids:
        return "internal"
    rows = repos.list_files_by_ids(conn, file_ids)
    if len(rows) != len(file_ids):
        return "sensitive"
    if all(row.get("classification") == "internal" for row in rows) is True:
        return "internal"
    return "sensitive"


def _knowledge_classification(agent: dict[str, Any], scope_registry: Any) -> str:
    """知识轴派生分级（ADR-0021 D3/Codex R0-P1）：绑 restricted 知识库的 Agent
    能把检索文本写进产物——无输入文件也携带受限内容，文件污点轴测不到。

    allowlist：scope 密级 public_internal/department → internal（department
    语义=部门内部，与 internal 定义重合）；restricted/未知密级/未注册 scope/
    registry 缺失 → sensitive（fail-closed，与 scopes.py 静态门的兜底拒绝同向）。
    knowledge.enabled 非字面 True 不构成访问面（同 reconcile_agent_scopes 口径）。
    """
    knowledge = agent.get("knowledge") or {}
    if knowledge.get("enabled") is not True:
        return "internal"
    for scope_id in knowledge.get("scopes") or []:
        scope = scope_registry.get(scope_id) if scope_registry is not None else None
        conf = None if scope is None else scope.get("confidentiality")
        if conf not in ("public_internal", "department"):
            return "sensitive"
    return "internal"


def _tool_taint_classification(agent: dict[str, Any], tool_registry: Any) -> str:
    """工具污点轴（ADR-0024，兑现 ADR-0021:194-198 声明的激活硬前置）：agent 的
    allowed_tools 里任一工具 tool.yaml 声明 output_classification=sensitive → 任务
    产物 sensitive。工具是真正碰外部不可考数据的单元（monitor_adapter_recon 读
    外部真实 run 目录、把侦察证据拷进产物），污点跟随该单元——任何未来 agent 挂
    该工具都自动继承，不靠单个 agent 作者记得声明。

    静态 fail-closed 过近似：「agent 被授予该工具」即污染，不追踪本次是否真调用——
    宁严勿洗白，与文件/知识轴同向。

    纵深 fail-closed（Codex R0 P2-1）：output_classification 已是 tool.schema.json
    的 required 字段，故**每个已加载工具必有显式值**（漏声明的 tool.yaml 注册期即被
    拒）。对已加载工具判定「非显式 internal（含 sensitive/坏值/极端情形缺失）一律
    sensitive」——比「仅 ==sensitive 才升级」更防漏。tool_registry 缺失或工具未加载
    → 该工具不贡献污点（工具未加载时其 call 本就 fail-closed，产不出洗白产物）。
    """
    if tool_registry is None:
        return "internal"
    for tool_id in agent.get("tools") or []:
        tool = tool_registry.get(tool_id)
        if tool is None:
            continue  # 工具未加载：其调用 fail-closed 产不出数据，不贡献污点
        if tool.get("output_classification") != "internal":
            return "sensitive"  # 已加载工具非显式 internal → fail-closed sensitive
    return "internal"


def _task_data_classification(
    conn: sqlite3.Connection,
    task: dict[str, Any],
    agent: dict[str, Any],
    scope_registry: Any,
    tool_registry: Any,
) -> str:
    """任务级派生分级 = 文件污点轴 ∨ 知识轴 ∨ 工具污点轴（任一 sensitive 即 sensitive）。

    ADR-0025：此纯函数只**计算**分级；落库与不可变性由 AgentRuntime.execute 在执行期
    调一次 + repos.set_task_data_classification 承担。read 期一律读落库列，绝不调本函数
    重派生（否则工具卸载/降级会让历史 sensitive 任务漂移解封，Codex R1-B）。
    """
    if _task_input_classification(conn, task) != "internal":
        return "sensitive"
    if _knowledge_classification(agent, scope_registry) != "internal":
        return "sensitive"
    if _tool_taint_classification(agent, tool_registry) != "internal":
        return "sensitive"
    return "internal"


def _load_workflow_module(agent_id: str, workflow_path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(f"flai_agent_{agent_id}_workflow", workflow_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 workflow.py：{workflow_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _KnowledgeContext:
    """context["knowledge"]：agent.yaml knowledge.enabled is True 时唯一的知识检索入口。

    default-deny 白名单在本层（与 _ToolRegistryContext 同构，ADR-0015）：scope 不在
    agent.yaml knowledge.scopes 白名单内一律拒绝并留 knowledge_search 事件——即使
    该 scope 已在 Scope Registry 注册（新注册 scope 绝不自动扩大存量 Agent 的可见面）。
    KnowledgeService 自身不做授权判定（信任边界见 service.py docstring），绕过本层
    直调 service 无白名单保护。命中/未命中/拒绝/失败均落 knowledge_search 事件
    （docs/06 §7：知识调用不得只在应用日志留痕）。
    """

    def __init__(
        self,
        knowledge_service: Any,
        conn: sqlite3.Connection,
        task_id: str,
        agent_id: str,
        allowed_scopes: frozenset[str],
    ) -> None:
        self._knowledge_service = knowledge_service
        self._conn = conn
        self._task_id = task_id
        self._agent_id = agent_id
        self._allowed_scopes = allowed_scopes

    def search(self, scope_id: str, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        if scope_id not in self._allowed_scopes:
            message = (
                f"scope {scope_id} 不在 Agent {self._agent_id} 的 agent.yaml "
                "knowledge.scopes 白名单内，default-deny 拒绝检索"
            )
            repos.append_event(
                self._conn, task_id=self._task_id, agent_id=self._agent_id,
                event_type="knowledge_search", level="error", message=message,
                payload={"scope_id": scope_id, "denied": "not_in_agent_scopes"},
            )
            raise KnowledgeScopeDeniedError(message)
        try:
            hits = self._knowledge_service.search(scope_id, query, top_k=top_k)
        except Exception as exc:
            repos.append_event(
                self._conn, task_id=self._task_id, agent_id=self._agent_id,
                event_type="knowledge_search", level="error",
                message=f"知识检索失败（scope={scope_id}）：{exc}",
                payload={"scope_id": scope_id, "query": query[:500], "error": str(exc)[:500]},
            )
            raise
        repos.append_event(
            self._conn, task_id=self._task_id, agent_id=self._agent_id,
            event_type="knowledge_search", level="info",
            message=f"知识检索完成（scope={scope_id}，命中 {len(hits)}）",
            payload={
                "scope_id": scope_id, "query": query[:500], "top_k": top_k,
                "hit_count": len(hits), "hit_chunk_ids": [h.chunk_id for h in hits],
            },
        )
        # KnowledgeHit(frozen dataclass) → dict：workflow 侧拿纯数据，出处字段
        # （source/fingerprint）随行携带，展示层必须透出（docs/06 §4）。
        return [asdict(h) for h in hits]


class AgentRuntime:
    """驱动单个任务从 validating 走完整生命周期：校验 -> running -> (analyzing) -> 终态。"""

    def __init__(
        self,
        agent_registry: Any,
        tool_registry: Any,
        model_gateway: Any,
        conn_factory: Callable[[], sqlite3.Connection],
        task_runs_dir: str | Path,
        *,
        knowledge_service: Any | None = None,
        uploads_dir: str | Path | None = None,
        scope_registry: Any | None = None,
    ) -> None:
        self.agent_registry = agent_registry
        self.tool_registry = tool_registry
        self.model_gateway = model_gateway
        self.conn_factory = conn_factory
        self.task_runs_dir = Path(task_runs_dir)
        # 由 create_app 注入权威 uploads 根；默认值仅保留旧直构调用的兼容性，
        # 按项目既有 data/{task_runs,uploads} 兄弟目录布局推导。
        self.uploads_dir = (
            Path(uploads_dir) if uploads_dir is not None else self.task_runs_dir.parent / "uploads"
        )
        # ADR-0015：可为 None（纯工具/结构化 Agent 场景不需要）；但 Agent 声明
        # knowledge.enabled 而这里为 None 时任务必须诚实失败，见 _execute 1b。
        self.knowledge_service = knowledge_service
        # ADR-0021 知识轴派生用；None 时知识轴对 enabled Agent 一律 fail-closed
        # 判 sensitive（_knowledge_classification 的 registry 缺失分支）。
        self.scope_registry = scope_registry

    def execute(self, task_id: str) -> dict[str, Any]:
        """驱动任务 task_id（调用前须已处于 validating 态）走完生命周期，返回最终 task dict。"""
        conn = self.conn_factory()
        try:
            return self._execute(conn, task_id)
        finally:
            conn.close()

    def _execute(self, conn: sqlite3.Connection, task_id: str) -> dict[str, Any]:
        task = repos.get_task(conn, task_id)
        if task is None:
            return {"status": "failed", "error_message": f"任务不存在：{task_id}"}

        agent_id = task["agent_id"]
        agent = self.agent_registry.get(agent_id)
        if agent is None:
            repos.set_task_status(conn, task_id, "failed", error_message=f"Agent 未注册：{agent_id}")
            repos.append_event(
                conn, task_id=task_id, agent_id=agent_id, event_type="task_failed",
                level="error", message=f"Agent 未注册：{agent_id}",
            )
            return {"status": "failed", "task": repos.get_task(conn, task_id)}

        pkg_dir = self.agent_registry.package_dir(agent_id)

        # ADR-0025：执行期算一次任务级分级（文件∨知识∨工具三轴）并**落库为不可变列**。
        # 落在产出任何内容（产物/样本/tool_runs/事件正文/error_message）之前，故每条
        # 派生行都被已落库的分级覆盖。read 期一律读此列，绝不重派生——工具事后卸载/
        # 降级不改已落库值（闭 Codex R1-B 漂移）。后续产物/样本沿用同一 data_classification。
        # CAS 首写落库；用**返回的持久值**（首写=本次算值；二次 execute=既有落库值）定
        # 后续产物/样本分级——保「产物分级==落库任务级分级」即便二次 execute（Codex R0 P1-2）。
        data_classification = repos.set_task_data_classification(
            conn, task_id,
            _task_data_classification(conn, task, agent, self.scope_registry, self.tool_registry),
        )

        # 1) 输入校验
        repos.append_event(
            conn, task_id=task_id, agent_id=agent_id, event_type="validation_started",
            level="info", message="开始校验输入",
        )
        verified_files: list[tuple[dict[str, Any], BinaryIO]] = []
        try:
            self._validate_inputs(pkg_dir, agent, task["inputs"])
            verified_files = self._open_input_files(conn, task)
        except Exception as exc:
            repos.append_event(
                conn, task_id=task_id, agent_id=agent_id, event_type="validation_failed",
                level="error", message=f"输入校验未通过：{exc}",
            )
            repos.set_task_status(conn, task_id, "failed", error_message=f"输入校验未通过：{exc}")
            repos.append_event(
                conn, task_id=task_id, agent_id=agent_id, event_type="task_failed",
                level="error", message=f"输入校验未通过：{exc}",
            )
            self._record_failure_sample(conn, task, agent, f"输入校验未通过：{exc}", data_classification)
            return {"status": "failed", "task": repos.get_task(conn, task_id)}

        # 1b) knowledge 服务可用性（ADR-0015 fail-closed）：Agent 声明了
        # knowledge.enabled 而 Runtime 未装配 KnowledgeService = 装配缺陷，
        # 诚实失败——绝不静默给一个"查不到任何东西"的假 knowledge 入口。
        if (agent.get("knowledge") or {}).get("enabled") is True and self.knowledge_service is None:
            self._close_verified_files(verified_files)
            msg = (
                f"Agent {agent_id} 声明 knowledge.enabled 但 Runtime 未装配 "
                "KnowledgeService（装配缺陷，fail-closed 拒绝执行）"
            )
            repos.append_event(
                conn, task_id=task_id, agent_id=agent_id, event_type="validation_failed",
                level="error", message=msg,
            )
            repos.set_task_status(conn, task_id, "failed", error_message=msg)
            repos.append_event(
                conn, task_id=task_id, agent_id=agent_id, event_type="task_failed",
                level="error", message=msg,
            )
            self._record_failure_sample(conn, task, agent, msg, data_classification)
            return {"status": "failed", "task": repos.get_task(conn, task_id)}

        # 2) 进入 running，构建 context 并调用 workflow.run()
        output_dir = self.task_runs_dir / task_id / "output"
        try:
            repos.set_task_status(conn, task_id, "running")
            output_dir.mkdir(parents=True, exist_ok=True)
        except BaseException:
            # workflow try/finally 尚未开始；状态迁移/建目录任一失败也必须释放
            # 已验输入句柄，不能让 worker 长跑时逐任务泄漏 fd。
            self._close_verified_files(verified_files)
            raise

        try:
            context = self._build_context(
                conn,
                task,
                agent,
                pkg_dir,
                output_dir,
                [row for row, _handle in verified_files],
            )
            workflow_module = _load_workflow_module(agent_id, pkg_dir / "workflow.py")
            result = workflow_module.run(context)
        except Exception as exc:
            error_message = f"{exc.__class__.__name__}: {exc}"
            repos.set_task_status(conn, task_id, "failed", error_message=error_message)
            repos.append_event(
                conn, task_id=task_id, agent_id=agent_id, event_type="task_failed",
                level="error", message=f"workflow 执行异常：{error_message}",
            )
            self._record_failure_sample(conn, task, agent, error_message, data_classification)
            return {"status": "failed", "task": repos.get_task(conn, task_id)}
        finally:
            self._close_verified_files(verified_files)

        if not isinstance(result, dict) or result.get("status") != "success":
            error_message = (result or {}).get("error_message", "workflow 返回失败态") if isinstance(result, dict) else "workflow 返回值非法"
            repos.set_task_status(conn, task_id, "failed", error_message=error_message)
            repos.append_event(
                conn, task_id=task_id, agent_id=agent_id, event_type="task_failed",
                level="error", message=error_message,
            )
            self._record_failure_sample(conn, task, agent, error_message, data_classification)
            return {"status": "failed", "task": repos.get_task(conn, task_id)}

        # 3) 成功：注册产物 + 样本沉淀（产物/样本继承任务级派生分级=文件∨知识∨工具
        # 三轴，ADR-0021 D3 + Codex R0-P1 + ADR-0024/0025）。复用执行期已算并落库的
        # data_classification（不重算，保产物/样本与落库任务级分级一致）。
        output_file_ids = self._register_outputs(
            conn, task_id, output_dir, classification=data_classification
        )
        repos.set_task_outputs(conn, task_id, output_file_ids)

        # sim_run_ref 回填（P3.2 接缝，spec §4.3）：workflow 成功输出
        # outputs[0].sim_run_ref（"module@run_id"）→ 回填 task.metadata.sim_run_ref
        # （与 POST /tasks/{id}/sim-run-ref 人工关联同一 setter，metadata 标注非
        # 状态迁移，不破「人是唯一签发者」）。标注非承重：畸形/回填失败只记
        # warning 事件不摧毁已成功的任务——错误方向必须是「少标注」。
        self._backfill_sim_run_ref(conn, task_id, agent_id, result)

        # M10/ADR-0018 origin 白名单：只有用户任务落样。eval 跑批的输入本来就是
        # 评测集，回灌样本库=循环喂养（评测数据冒充生产数据资产）；未知 origin
        # 一律不落——错误方向必须是「少收一条」而非「污染资产」。
        if (
            agent.get("data_asset", {}).get("collect_samples") is True
            and task.get("origin") == "user"
        ):
            repos.record_sample(
                conn,
                task_id=task_id,
                agent_id=agent_id,
                agent_version=task["agent_version"],
                input_json=task["inputs"],
                output_json=result,
                validation_status="success",
                classification=data_classification,
            )

        # 宪法「安全 gate 判定一律 is True/is False」+ fail-closed（审计 P2）：
        # 仅当 agent.yaml **显式声明 False** 才跳过人工审核；缺失/畸形（schema 之外
        # 的任何原因）一律走 waiting_review——错误方向必须是「多审」而非「漏审」。
        # 此前的 truthiness 判定在字段缺失时默认跳审（fail-open），安全依赖了
        # agent.schema.json 的 required 耦合而非 gate 自证。
        requires_review = (agent.get("workflow") or {}).get("requires_human_review")
        if requires_review is not False:
            repos.set_task_status(conn, task_id, "waiting_review")
            try:
                repos.append_event(
                    conn, task_id=task_id, agent_id=agent_id, event_type="review_requested",
                    level="info", message="任务需要人工审核放行",
                )
            except Exception:
                logger.exception(
                    "任务 %s 已安全落在 waiting_review；仅缺少展示性 review_requested 事件，"
                    "继续正常返回等待人工放行",
                    task_id,
                )
            return {"status": "waiting_review", "task": repos.get_task(conn, task_id)}

        # docs/05 §2 强制规则：running 不得跳过 analyzing 直接进 completed。
        repos.set_task_status(conn, task_id, "analyzing")
        repos.set_task_status(conn, task_id, "completed")
        repos.append_event(
            conn, task_id=task_id, agent_id=agent_id, event_type="task_completed",
            level="info", message="任务完成",
        )
        return {"status": "completed", "task": repos.get_task(conn, task_id)}

    def _backfill_sim_run_ref(
        self, conn: sqlite3.Connection, task_id: str, agent_id: str, result: dict[str, Any]
    ) -> None:
        """workflow outputs[0].sim_run_ref（"module@run_id"）→ metadata.sim_run_ref。

        格式门：module 须 ^[a-z][a-z0-9_]*$、run_id 须 ^\\d{8}-\\d{6}$（与
        cfd_solve_launch/hub run_discovery 同一白名单语义）；畸形不回填、记
        warning 事件继续——标注失败绝不摧毁已成功的任务。"""
        outputs = result.get("outputs") or []
        first = outputs[0] if outputs and isinstance(outputs[0], dict) else {}
        ref = first.get("sim_run_ref")
        if not isinstance(ref, str) or not ref:
            return  # 无声明即无事发生（绝大多数 agent 走这里）
        module, sep, run_id = ref.partition("@")
        if (
            sep != "@"
            or re.fullmatch(r"[a-z][a-z0-9_]*", module) is None
            or re.fullmatch(r"[0-9]{8}-[0-9]{6}", run_id) is None
        ):
            repos.append_event(
                conn, task_id=task_id, agent_id=agent_id, event_type="agent_log",
                level="warning",
                message=f"sim_run_ref 畸形，不回填：{ref!r}（须 module@YYYYMMDD-HHMMSS）",
                payload={"workflow_event_type": "sim_run_ref_malformed", "sim_run_ref": ref},
            )
            return
        try:
            repos.set_task_sim_run_ref(conn, task_id, module=module, run_id=run_id)
        except Exception:
            logger.exception(
                "任务 %s sim_run_ref 回填失败（标注非承重，任务保持成功态）", task_id
            )

    def _record_failure_sample(
        self, conn: sqlite3.Connection, task: dict[str, Any], agent: dict[str, Any],
        error_message: str, data_classification: str,
    ) -> None:
        """失败任务的样本沉淀（ADR-0013，§18-Q7「每次失败能沉淀」的最小落点）。

        collect_samples 型 Agent 的失败输入同样是数据资产——它们是未来评测集反例
        的直接素材（validation_status='failed' 供下游筛选，accepted_by_engineer
        留 NULL：失败任务不经人工放行，不冒充已定标数据）。此前只有成功路径沉淀，
        失败即蒸发。完整 Memory 子系统仍是 V0.2 槽位，此处不冒充。
        """
        # 同成功路径的 origin 白名单（M10/ADR-0018）：eval 跑批的失败是评测结论
        # 的一部分（记在 eval_runs.case_results），不是生产失败样本。
        if (
            agent.get("data_asset", {}).get("collect_samples") is True
            and task.get("origin") == "user"
        ):
            repos.record_sample(
                conn,
                task_id=task["id"],
                agent_id=task["agent_id"],
                agent_version=task["agent_version"],
                input_json=task["inputs"],
                output_json={"error_message": error_message},
                validation_status="failed",
                # ADR-0025：复用执行期已算并落库的 data_classification（文件∨知识∨工具
                # 三轴）——与任务级落库分级、成功产物分级三者一致。此前每处重算
                # （ADR-0021 F6 修的是「据 verified_files 推导会误判」，改现查 DB；
                # 现进一步统一为「执行期算一次、处处复用」，杜绝多点重算的漂移面）。
                classification=data_classification,
            )

    def _validate_inputs(self, pkg_dir: Path, agent: dict[str, Any], inputs: dict[str, Any]) -> None:
        import json

        from jsonschema import validate as jsonschema_validate

        schema_name = agent.get("input", {}).get("schema")
        if not schema_name:
            return
        schema_path = pkg_dir / schema_name
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema_validate(inputs, schema)

    def _open_input_files(
        self, conn: sqlite3.Connection, task: dict[str, Any]
    ) -> list[tuple[dict[str, Any], BinaryIO]]:
        """校验所有签发输入并持有句柄至 workflow 返回；任一失败即整体拒绝执行。"""
        verified: list[tuple[dict[str, Any], BinaryIO]] = []
        try:
            for file_id in task.get("input_file_ids", []):
                record = repos.get_file(conn, file_id)
                if record is None:
                    raise FileIntegrityError(
                        f"输入文件完整性校验失败：file_id={file_id}，File Store 无登记记录"
                    )
                try:
                    handle = open_verified_file(
                        record["path"],
                        allowed_root=self.uploads_dir,
                        expected_size=record["size_bytes"],
                        expected_sha256=record["sha256"],
                    )
                except (FileNotFoundError, FileIntegrityError) as exc:
                    raise FileIntegrityError(
                        f"输入文件完整性校验失败：file_id={file_id}，{exc}"
                    ) from exc

                # 既有工具公共契约只接收带真实后缀的 path（例如 openpyxl 会按
                # `.xlsx` 后缀预检），不能替换成 `/dev/fd/N`。句柄仍持有到 workflow
                # 结束，保证本层校验对象稳定；path 型工具二次打开的残余窗口需在
                # 后续工具契约升级为流/句柄时彻底消除，本批不改公共接口。
                verified.append((dict(record), handle))
            return verified
        except BaseException:
            self._close_verified_files(verified)
            raise

    @staticmethod
    def _close_verified_files(files: list[tuple[dict[str, Any], BinaryIO]]) -> None:
        for _record, handle in files:
            handle.close()

    def _build_context(
        self,
        conn: sqlite3.Connection,
        task: dict[str, Any],
        agent: dict[str, Any],
        pkg_dir: Path,
        output_dir: Path,
        files: list[dict[str, Any]],
    ) -> dict[str, Any]:
        agent_id = task["agent_id"]
        allowed_tools = frozenset(agent.get("tools") or [])
        context: dict[str, Any] = {
            "task": task,
            "inputs": task["inputs"],
            "files": files,
            "model_gateway": _ModelGatewayContext(self.model_gateway, conn, task["id"], agent_id),
            "tool_registry": _ToolRegistryContext(
                self.tool_registry, conn, task["id"], agent_id, allowed_tools
            ),
            "event_logger": _WorkflowEventLogger(conn, task["id"], agent_id),
            "output_dir": str(output_dir),
            "agent_config": agent,
        }
        # ADR-0015：knowledge 键仅在 enabled is True 时存在（default-deny：
        # 未声明的 Agent 连入口都拿不到，而不是拿到一个"空"入口）。
        # 服务未装配的情形已在 _execute 1b fail-closed，此处 service 必非 None。
        if (agent.get("knowledge") or {}).get("enabled") is True:
            context["knowledge"] = _KnowledgeContext(
                self.knowledge_service, conn, task["id"], agent_id,
                frozenset((agent.get("knowledge") or {}).get("scopes") or []),
            )
        return context

    def _register_outputs(
        self, conn: sqlite3.Connection, task_id: str, output_dir: Path, *, classification: str
    ) -> list[str]:
        file_ids: list[str] = []
        if not output_dir.is_dir():
            return file_ids
        for path in sorted(output_dir.rglob("*")):
            if not path.is_file():
                continue
            file_id = str(uuid.uuid4())
            repos.create_file(
                conn,
                file_id=file_id,
                task_id=task_id,
                kind="output",
                filename=path.name,
                path=str(path),
                size_bytes=path.stat().st_size,
                sha256=_sha256_file(path),
                # 污点传播（ADR-0021 D3）：产物继承任务级派生分级，跑一次任务
                # 不能把 sensitive 输入洗白成 internal 产物。uploaded_by 留
                # NULL 如实——产物非人工标注场景。
                classification=classification,
            )
            file_ids.append(file_id)
        return file_ids
