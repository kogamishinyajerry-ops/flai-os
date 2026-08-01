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

from ..core.errors import (
    FileIntegrityError,
    KnowledgeScopeDeniedError,
    ModelAccessDeniedError,
    ToolNotAllowedError,
)
from ..storage import repos
from ..storage.file_integrity import open_verified_file
from .package_snapshot import AgentPackageSnapshot, SNAPSHOT_CONTRACT

logger = logging.getLogger(__name__)

_PACKAGE_SNAPSHOT_DIGEST_METADATA_KEY = "package_snapshot_digest"
_SHA256_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")

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
        tool_context: dict[str, Any] | None = None,
    ) -> None:
        self._tool_registry = tool_registry
        self._conn = conn
        self._task_id = task_id
        self._agent_id = agent_id
        self._allowed_tools = allowed_tools
        # #8/R2-1：任务级注入 adapter 的只读上下文（eval 任务的材化 fixture 根），
        # 令「工具读外部活态」的工具（cfd_result_read）在评测里读冻结产物而非全局 env。
        self._tool_context = tool_context

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
            result = self._tool_registry.call(
                tool_id, payload, conn=self._conn, task_id=self._task_id,
                tool_context=self._tool_context,
            )
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


class _NoModelGatewayContext:
    """profile:none Agent 的 model_gateway 桩（Codex 增量2审 R3 P1）：chat/embed/vision 一律
    fail-closed 抛 ModelAccessDeniedError。§3.6 注册期不变量豁免 profile:none job 于「判决型
    必 review-gated」——该豁免只有 runtime **真的不让 none agent 调 LLM** 时才成立，否则声明
    none 即可绕人签闸调 LLM、自动 completed、经 resolver 把未签发判决传下游。此桩把「声明
    profile:none」钉成「运行时物理无 LLM」，让声明与强制名实一致。非 none profile 的 job 已被
    §3.6 强制 requires_human_review:true（受人签闸兜底），故仍给功能 _ModelGatewayContext。"""

    def __init__(self, agent_id: str) -> None:
        self._agent_id = agent_id

    def _deny(self, kind: str) -> None:
        raise ModelAccessDeniedError(
            f"Agent {self._agent_id!r} 声明 model.profile=none（不调 LLM）却尝试模型调用（{kind}）"
            "——profile:none 运行时强制无 LLM（§3.6 判决⟹人签 keystone）；需 LLM 请声明真实 "
            "profile 且 requires_human_review:true"
        )

    def chat(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self._deny("chat")

    def embed(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self._deny("embed")

    def vision(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self._deny("vision")


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
                "hit_count": len(hits),
                # hit_chunk_ids 保留（既有消费方/测试锚）；hit_citations 携出处四钥
                # （Codex 治理审 R1 P2）：签发面据此带 source 消歧同 stem 碰撞、比对
                # fingerprint 漂移，使 N7 一键回源对碰撞项也可核（否则永远停在 409）。
                "hit_chunk_ids": [h.chunk_id for h in hits],
                "hit_citations": [
                    {"chunk_id": h.chunk_id, "source": h.source, "fingerprint": h.fingerprint}
                    for h in hits
                ],
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
            task = repos.get_task(conn, task_id)
            snapshot_getter = getattr(self.agent_registry, "package_snapshot", None)
            snapshot = (
                snapshot_getter(task["agent_id"])
                if task is not None and callable(snapshot_getter)
                else None
            )
            if snapshot is None:
                return self._execute(
                    conn,
                    task_id,
                    package_snapshot=None,
                    package_dir=None,
                )
            with snapshot.materialized(
                parent=self.task_runs_dir / task_id
            ) as package_dir:
                return self._execute(
                    conn,
                    task_id,
                    package_snapshot=snapshot,
                    package_dir=package_dir,
                )
        finally:
            conn.close()

    def _execute(
        self,
        conn: sqlite3.Connection,
        task_id: str,
        *,
        package_snapshot: AgentPackageSnapshot | None,
        package_dir: Path | None,
    ) -> dict[str, Any]:
        task = repos.get_task(conn, task_id)
        if task is None:
            return {"status": "failed", "error_message": f"任务不存在：{task_id}"}

        agent_id = task["agent_id"]
        if package_snapshot is None or package_dir is None:
            message = f"Agent 未注册或缺少不可变包快照：{agent_id}"
            repos.set_task_data_classification(conn, task_id, "internal")
            repos.set_task_status(conn, task_id, "failed", error_message=message)
            repos.append_event(
                conn, task_id=task_id, agent_id=agent_id, event_type="task_failed",
                level="error", message=message,
            )
            return {"status": "failed", "task": repos.get_task(conn, task_id)}
        agent = package_snapshot.manifest

        # Guide/batch 创建期把用户确认过的精确 Agent 包摘要钉在 metadata；只要
        # 任务携带该钉，执行期就必须在任何输入校验、workflow 加载、工具调用或
        # 产物写入前复核。agent_version 不足以识别「同版本换包」，而 Registry
        # rescan 会发布新的不可变快照，所以必须比较本次实际执行快照的 digest。
        # 未携带该字段的旧任务/单建任务保持兼容；携带但格式非法也按漂移失败，
        # 避免空串、非规范摘要等值被当成未启用 gate。
        metadata = task.get("metadata")
        if (
            isinstance(metadata, dict)
            and _PACKAGE_SNAPSHOT_DIGEST_METADATA_KEY in metadata
        ):
            pinned_package_digest = metadata.get(
                _PACKAGE_SNAPSHOT_DIGEST_METADATA_KEY
            )
            digest_matches = (
                isinstance(pinned_package_digest, str)
                and _SHA256_DIGEST_RE.fullmatch(pinned_package_digest) is not None
                and pinned_package_digest == package_snapshot.digest
            )
            if digest_matches is not True:
                msg = (
                    "Agent 包快照摘要漂移或无效：任务锁定 "
                    f"package_snapshot_digest={pinned_package_digest!r}，当前注册包摘要="
                    f"{package_snapshot.digest!r}——拒绝执行同版本换包或未规范钉；"
                    "请重新核对方案并创建任务"
                )
                repos.set_task_data_classification(conn, task_id, "internal")
                repos.set_task_status(conn, task_id, "failed", error_message=msg)
                repos.append_event(
                    conn,
                    task_id=task_id,
                    agent_id=agent_id,
                    event_type="task_failed",
                    level="error",
                    message=msg,
                )
                return {"status": "failed", "task": repos.get_task(conn, task_id)}

        # Codex 命中即审 R2 P1（K1 签发见证的前提）：_execute 只使用本次一次取得的
        # Registry package snapshot，而 task.agent_version 是创建期锁定值（tasks.py 建时
        # = 当时当前版本）。跨升级窗口二者可 drift——任务实际跑当前版本而
        # task.agent_version 停旧值，则 K1 签发见证（键 task.agent_version
        # 历史 manifest）检的不是真跑版本，判据失真。fail-closed 拒版本漂移 → task.agent_version 恒等
        # 真跑版本，K1 键之即权威（provenance 诚实：绝不静默在异于锁定版本上执行；跨升级排队任务
        # 失败、由用户对新版本重建，优于悄悄跑异版本产出错误归因的产物）。
        if agent.get("version") != task["agent_version"]:
            msg = (
                f"Agent 版本漂移：任务锁定 agent_version={task['agent_version']!r} 但当前注册 "
                f"{agent.get('version')!r}——拒在异于锁定版本上执行（跨升级窗口 provenance 权威性，"
                "K1 签发见证前提）；请对当前版本重建任务"
            )
            # final-confirm P2：本分支在 set_task_data_classification 前触发，任务分级留 NULL→
            # classification_gate 当 sensitive 遮蔽 drift 诊断（含"请重建"指引），用户无法诊断。
            # drift 是固定系统消息、非敏感用户内容，CAS 落 internal 使诊断经分级门可见（同 R3-2
            # 级联取消；set_task_data_classification 是 CAS-on-NULL，未执行任务恒 NULL 故等价落 internal）。
            repos.set_task_data_classification(conn, task_id, "internal")
            repos.set_task_status(conn, task_id, "failed", error_message=msg)
            repos.append_event(
                conn, task_id=task_id, agent_id=agent_id, event_type="task_failed",
                level="error", message=msg,
            )
            return {"status": "failed", "task": repos.get_task(conn, task_id)}

        # 批八 loop-auditor F1：执行期 disabled 兜底。此前只重查「仍注册+版本漂移」
        # ——滞留 created 的依赖任务在等待窗口内 agent 被禁用（版本不变）仍会执行，
        # summon/create 时点的 disabled gate 形同虚设一半。禁用即诚实失败不硬跑
        # （镜像 conversation.post_message 的既有语义）。
        if agent.get("status") == "disabled":
            msg = f"Agent 已下线，拒绝执行：{agent_id}——任务创建后成员被禁用，请改派或重建"
            repos.set_task_data_classification(conn, task_id, "internal")
            repos.set_task_status(conn, task_id, "failed", error_message=msg)
            repos.append_event(
                conn, task_id=task_id, agent_id=agent_id, event_type="task_failed",
                level="error", message=msg,
            )
            return {"status": "failed", "task": repos.get_task(conn, task_id)}

        pkg_dir = package_dir

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
            payload={
                "package_snapshot_contract": SNAPSHOT_CONTRACT,
                "package_snapshot_digest": package_snapshot.digest,
            },
        )
        verified_files: list[tuple[dict[str, Any], BinaryIO]] = []
        try:
            self._validate_inputs(pkg_dir, agent, task["inputs"])
            verified_files = self._open_input_files(conn, task, agent)
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
        self,
        conn: sqlite3.Connection,
        task: dict[str, Any],
        agent: dict[str, Any],
    ) -> list[tuple[dict[str, Any], BinaryIO]]:
        """按本次包快照校验输入并持有句柄；任一失败即整体拒绝执行。"""
        verified: list[tuple[dict[str, Any], BinaryIO]] = []
        file_ids = task.get("input_file_ids", [])
        input_contract = agent.get("input") or {}
        input_type = input_contract.get("type")
        allowed_extensions: tuple[str, ...] = ()

        # 创建期只看直提交附件；resolver 会在依赖完成后改写最终 input_file_ids。
        # 此处消费同一次 package_snapshot 取得的 manifest（调用方的 agent），在
        # workflow/tool/output 前对最终集合重做数量/后缀契约。只约束 manifest 声明：
        # kind/provenance/完整性仍由下方既有 gate 独立强制，故合法上游 output 可消费。
        if input_type == "none" and len(file_ids) != 0:
            raise FileIntegrityError(
                "最终输入文件契约校验失败：input.type=none 必须有 0 个附件，"
                f"实际 {len(file_ids)} 个"
            )
        if input_type == "file_upload":
            if len(file_ids) != 1:
                raise FileIntegrityError(
                    "最终输入文件契约校验失败：input.type=file_upload 必须且只能有 "
                    f"1 个附件，实际 {len(file_ids)} 个"
                )
            raw_extensions = input_contract.get("allowed_extensions")
            if (
                not isinstance(raw_extensions, list)
                or len(raw_extensions) == 0
                or len(raw_extensions) > 32
            ):
                raise FileIntegrityError(
                    "最终输入文件契约校验失败：file_upload.allowed_extensions "
                    "声明缺失或不合法"
                )
            normalized_extensions: list[str] = []
            for raw_extension in raw_extensions:
                if not isinstance(raw_extension, str):
                    raise FileIntegrityError(
                        "最终输入文件契约校验失败：file_upload.allowed_extensions "
                        "声明不合法"
                    )
                extension = raw_extension.strip().lower()
                if not extension.startswith(".") or not 2 <= len(extension) <= 16:
                    raise FileIntegrityError(
                        "最终输入文件契约校验失败：file_upload.allowed_extensions "
                        "声明不合法"
                    )
                if extension not in normalized_extensions:
                    normalized_extensions.append(extension)
            allowed_extensions = tuple(normalized_extensions)

        # 批七 3-lens P1：消费点密级复核（ADR-0030）——创建时点 gate 只见直提交
        # 文件；带 depends_on 的下游任务创建时 input_file_ids=[]（材料级=public 恒
        # 过门），resolver 事后把上游产物（可能 sensitive）管道注入 input_file_ids。
        # 与 K1/K2/provenance 同款「生产侧+消费侧双端强制」：消费动作上对**管道
        # 注入的产物（kind=output）**重跑同一判定函数，低密级上限 Agent 绝不吃到
        # 越级产物。边界如实声明：直提交输入（kind=input）由创建门全 API 路径判
        # 定（create/batch 同函数），此处不重判——避免把 ADR-0025 存量派生语义
        # （repos 直写的传播链测试/legacy 行）追溯性打失败；记录缺失走下方逐文件
        # 完整性校验的精确报错，不被 derive 的「缺失=sensitive」兜底遮蔽。
        from ..api import classification_gate as cgate

        _piped_ids = []
        for _fid in file_ids:
            _rec = repos.get_file(conn, _fid)
            if _rec is not None and _rec.get("kind") == "output":
                _piped_ids.append(_fid)
        if _piped_ids:
            _allowed, _material_level, _agent_max = cgate.agent_clearance_allows(
                conn, agent, _piped_ids
            )
            if _allowed is False:
                raise FileIntegrityError(
                    f"输入材料密级复核失败：管道注入产物材料级「{_material_level}」超出该 Agent"
                    f"密级准入上限「{_agent_max}」——上游产物同受 ADR-0030 约束（消费点复核，fail-closed）"
                )
        try:
            for file_id in file_ids:
                record = repos.get_file(conn, file_id)
                if record is None:
                    raise FileIntegrityError(
                        f"输入文件完整性校验失败：file_id={file_id}，File Store 无登记记录"
                    )
                if input_type == "file_upload":
                    filename = record.get("filename")
                    if not isinstance(filename, str) or not filename.lower().endswith(
                        allowed_extensions
                    ):
                        raise FileIntegrityError(
                            "最终输入文件扩展名不符合已钉死的 Agent 包契约："
                            f"{filename!r}，允许 {list(allowed_extensions)}"
                        )
                # 权威根按文件 kind 选（协作运行时 §3.3 管道跨信任边界）：上传输入
                # 在 uploads_dir，上游产物（管道进来的 kind=output）在 task_runs_dir——
                # 二者都是**装配注入**的权威根，根由 DB 的 kind 字段选、绝不从待验 path
                # 反推（R4 原则不破）；选定根后 open_verified_file 仍做 O_NOFOLLOW 拒
                # symlink + resolve-inside-root + sha256/size 全套校验。
                kind = record.get("kind")
                if kind == "output":
                    # 消费点 provenance 校验（Codex 增量2审 P1-1）：output 文件只能来自
                    # 本任务 depends_on 声明**且已 completed**的上游（=resolver 管道的正当
                    # 来源）。创建期 input_file_ids allowlist 只挡新 API 建的任务；旧 API 建
                    # 的（或前滚 rollout 窗口混版）任务的 input_file_ids 可能已直含他人 output
                    # ——本处结构校验把「产物只经 review-gated resolver 管道注入」钉在消费
                    # 动作上，不依赖创建期单点，堵死绕过 resolver + 人签闸消费未签发产物。
                    dep = task.get("depends_on") or []
                    owner_id = record.get("task_id")
                    if owner_id not in dep:
                        raise FileIntegrityError(
                            f"输入文件完整性校验失败：file_id={file_id} 是任务 {owner_id!r} 的产物，"
                            "但本任务未在 depends_on 声明其为依赖——产物只能经依赖 resolver 管道注入，"
                            "不得绕过依赖链直引"
                        )
                    owner = repos.get_task(conn, owner_id)
                    owner_status = owner["status"] if owner is not None else "missing"
                    if owner_status != "completed":
                        raise FileIntegrityError(
                            f"输入文件完整性校验失败：上游任务 {owner_id!r} 状态={owner_status}（非 completed）"
                            "——产物未过人工签发闸（waiting_review→completed 只人工）不可被下游消费"
                        )
                    # K1 签发维 provenance（Codex 增量2审 R5-1 + loop-auditor）：completed 只证
                    # 时序不证人签。legacy pre-§3.6（或版本翻转前）任务可能已自动 completed、无人签
                    # =未签 LLM 判决；其 input_file_ids 若已直含产物（绕 resolver）只撞本消费点，故
                    # resolver 生产侧修不到。双见证 fail-closed（review_approved 事件 ∨ 该任务锁定
                    # agent_version 的 manifest profile=none），与 runner._resolve_one_candidate 同守。
                    if not repos.task_output_is_signed_off(conn, owner):
                        raise FileIntegrityError(
                            f"输入文件完整性校验失败：上游任务 {owner_id!r} 已 completed 但无签发见证"
                            "（未签 LLM 判决 / agent_version manifest 不可确立）——未过人工签发闸的产物"
                            "不可被下游消费（K1 签发维 provenance，fail-closed）"
                        )
                    # K2 消费侧 origin 隔离（loop-auditor 巡查）：resolver（runner）与 create_task
                    # （tasks.py）都校上游 origin=='user'，独消费点漏——legacy/直写任务 input_file_ids
                    # 已直含某 eval 任务产物且满足 depends_on+completed+manifest+binding 时，此处会开
                    # eval 内容入 user 任务→user-origin sample gate 污染样本库（ADR-0018）。补齐兜底。
                    if owner.get("origin") != "user":
                        raise FileIntegrityError(
                            f"输入文件完整性校验失败：上游任务 {owner_id!r} origin={owner.get('origin')!r}"
                            "（非 user，跨 eval/user 隔离轴）——eval 产物绝不经依赖链流入 user 任务"
                            "（ADR-0018 防样本库污染，K2 消费侧兜底）"
                        )
                    # Codex 增量2审 R2 P2：provenance 还须校（a）file_id 真在 owner 的
                    # output_file_ids manifest 内（非仅"owner 是已完成依赖"——legacy 任务
                    # input_file_ids 直含某已完成依赖的**非产物** id 时前两关放行）；（b）owner
                    # 被本任务 input_binding.from_tasks 选中（否则被显式排除的产物、含 sensitive，
                    # 仍能在消费点被读）。生产侧（resolver）+ 消费侧双端各自独立强制 binding+manifest。
                    if file_id not in (owner.get("output_file_ids") or []):
                        raise FileIntegrityError(
                            f"输入文件完整性校验失败：file_id={file_id} 不在上游 {owner_id!r} 的 "
                            "output_file_ids 产物清单内——非该上游 registered 产物，拒消费"
                        )
                    _binding = task.get("input_binding") or {}
                    _from_tasks = _binding.get("from_tasks") or None
                    if _from_tasks is not None and owner_id not in _from_tasks:
                        raise FileIntegrityError(
                            f"输入文件完整性校验失败：file_id={file_id} 的上游 {owner_id!r} 被本任务 "
                            "input_binding.from_tasks 显式排除——不得消费绑定排除的产物"
                        )
                    allowed_root = self.task_runs_dir
                elif kind == "input":
                    allowed_root = self.uploads_dir
                else:
                    # Codex 增量2审 R1 P2：只有 input/output 两类合法权威根。legacy/future
                    # 未知 kind 绝不默认当上传件开（原 ternary else 分支静默落 uploads_dir=
                    # fail-open）——未知类型 fail-closed 拒消费，杜绝无法归类的记录被当输入喂入。
                    raise FileIntegrityError(
                        f"输入文件完整性校验失败：file_id={file_id} kind={kind!r} 非 input/output"
                        "——未知文件类型 fail-closed 拒绝消费（绝不默认当上传件开）"
                    )
                try:
                    handle = open_verified_file(
                        record["path"],
                        allowed_root=allowed_root,
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
        # Codex 增量2审 R3 P1：按声明 profile 强制 gateway 访问。profile:none（含缺省）→ 抛异常
        # 桩，物理封死 LLM 调用，令 §3.6「none job 豁免 review-gate」的豁免名实一致；非 none
        # profile 的 job 已被 §3.6 强制 rhr:true（人签闸兜底）→ 功能 gateway。
        _profile = (agent.get("model") or {}).get("profile")
        _gateway = (
            _NoModelGatewayContext(agent_id)
            if _profile in (None, "none")
            else _ModelGatewayContext(self.model_gateway, conn, task["id"], agent_id)
        )
        # #8/R2-1：eval 任务（origin='eval'）把材化快照的 fixture 根经任务级 context 注入
        # 「工具读外部活态」的工具（如 cfd_result_read），令其读**冻结**产物而非全局
        # $FLAI_CFD_CASE_DIR 活态——「评的就是晋升的那版」对这类 agent 也成立。snapshot 路径
        # 下 pkg_dir=材化目录 → fixture 根=<materialized>/eval_cases/fixtures。普通任务
        # （origin≠eval）不注入，工具回退活 env，真实 CFD 运行语义不变；无 fixtures 目录也不注入。
        eval_tool_context: dict[str, Any] | None = None
        if task.get("origin") == "eval":
            _fixtures = pkg_dir / "eval_cases" / "fixtures"
            if _fixtures.is_dir():
                eval_tool_context = {"eval_fixtures_dir": str(_fixtures)}
        context: dict[str, Any] = {
            "task": task,
            "inputs": task["inputs"],
            "files": files,
            "model_gateway": _gateway,
            "tool_registry": _ToolRegistryContext(
                self.tool_registry, conn, task["id"], agent_id, allowed_tools,
                tool_context=eval_tool_context,
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
