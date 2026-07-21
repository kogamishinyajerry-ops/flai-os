"""受限导引计划派发：把已校验的安全单 Agent 计划原子物化为真实任务。

这个模块只替代机械的“去创建任务/提交”动作，不触碰人工 review：它永不调用
review API、永不写 ``review_approved``，也不把任务标成 completed。任何无法由
确定性规则证明安全的计划都返回可见 blocker，并保持零任务。
"""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from ..auth.authorization import agent_is_callable, role_can_access_agent
from ..storage import repos


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _issue(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **details}


def _execution(
    *,
    request_id: str,
    status: str,
    plan_digest: str | None,
    issues: list[dict[str, Any]] | None = None,
    task_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "mode": "safe_auto",
        "request_id": request_id,
        "status": status,
        "plan_digest": plan_digest,
        "task_ids": task_ids or [],
        "issues": issues or [],
        "replayed": False,
    }


def _load_input_schema(registry: Any, agent_id: str) -> dict[str, Any] | None:
    package_dir = registry.package_dir(agent_id)
    if package_dir is None:
        return None
    schema_path = Path(package_dir) / "input_schema.json"
    try:
        loaded = json.loads(schema_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            return None
        Draft202012Validator.check_schema(loaded)
    except (OSError, json.JSONDecodeError, RecursionError, SchemaError):
        return None
    return loaded


def _required_fields_missing(schema: dict[str, Any], inputs: dict[str, Any]) -> list[str]:
    required = schema.get("required")
    if not isinstance(required, list):
        return []
    return sorted(name for name in required if isinstance(name, str) and name not in inputs)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"JSON 对象含重复键：{key}")
        value[key] = item
    return value


def _reject_nonfinite_json(value: str) -> Any:
    raise ValueError(f"JSON 不允许非有限数：{value}")


def _balanced_container_end(content: str, start: int) -> int | None:
    """返回一个 JSON 容器的边界；畸形外层仍整体跳过，绝不再扫描其嵌套对象。"""
    opening = content[start]
    expected = "}" if opening == "{" else "]"
    stack = [expected]
    in_string = False
    escaped = False
    for index in range(start + 1, len(content)):
        char = content[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            stack.append("}")
        elif char == "[":
            stack.append("]")
        elif char in ("}", "]"):
            if not stack or char != stack[-1]:
                # 错配说明外层语义已不可可靠恢复；若从错配点后继续扫描，会把仍在
                # 畸形外壳里的嵌套 inputs 误当顶层授权。None 令调用方拒绝余下全文。
                return None
            stack.pop()
            if not stack:
                return index + 1
    return None


def _top_level_json_values(content: str) -> list[Any]:
    """解析文本中的非嵌套 JSON 容器；外层语义对象不会泄漏其内部对象。"""
    decoder = json.JSONDecoder(
        object_pairs_hook=_unique_object,
        parse_constant=_reject_nonfinite_json,
    )
    values: list[Any] = []
    index = 0
    while index < len(content):
        starts = [
            position
            for position in (content.find("{", index), content.find("[", index))
            if position >= 0
        ]
        if not starts:
            break
        start = min(starts)
        try:
            candidate, consumed = decoder.raw_decode(content[start:])
        except (json.JSONDecodeError, RecursionError, ValueError):
            end = _balanced_container_end(content, start)
            if end is None:
                break
            index = end
            continue
        values.append(candidate)
        index = start + consumed
    return values


def _has_explicit_input_mapping(inputs: dict[str, Any], content: str) -> bool:
    """用户必须显式给出与计划输入完全相同的 JSON 对象。

    只做“所有叶值出现在全文”会丢失字段/结构关系：模型可交换 system_name 与
    states 仍通过。这里由标准库 JSON 解析器恢复用户亲自声明的键值结构，再做深
    相等；LLM 只能搬运，不能替用户决定字段归属。允许 ``{"inputs": {...}}``
    作为带外层说明的等价 envelope。
    """
    for candidate in _top_level_json_values(content):
        if _canonical_digest(candidate) == _canonical_digest(inputs):
            return True
        if isinstance(candidate, dict) and _canonical_digest(
            candidate.get("inputs")
        ) == _canonical_digest(inputs):
            return True
    return False


class GuidePlanDispatch:
    """后端唯一 safe-auto admission seam；调用者负责外层 SQLite 事务。"""

    def __init__(self, agent_registry: Any) -> None:
        self._registry = agent_registry

    @staticmethod
    def _is_safe_auto_agent(agent: dict[str, Any], actor_role: str) -> bool:
        automation = agent.get("automation") or {}
        return (
            agent_is_callable(agent, mode="job")
            and automation.get("session_execution") is True
            and automation.get("effect") == "none"
            and agent.get("tools") == []
            and (agent.get("input") or {}).get("type") == "params"
            and role_can_access_agent(agent, actor_role)
        )

    def eligible_agent_ids(self, actor_role: str) -> set[str]:
        """供导引提示标注当前主体真实可自动执行的候选；派发时仍会权威复查。"""
        return {
            agent["id"]
            for agent in self._registry.list()
            if isinstance(agent.get("id"), str)
            and self._is_safe_auto_agent(agent, actor_role)
        }

    def dispatch_in_transaction(
        self,
        conn: sqlite3.Connection,
        *,
        conversation_id: str,
        recommendation: dict[str, Any] | None,
        request_id: str,
        actor_display_name: str,
        actor_username: str,
        actor_role: str,
        current_user_content: str,
        has_attachments: bool,
    ) -> dict[str, Any]:
        if not conn.in_transaction:
            raise RuntimeError("GuidePlanDispatch 必须在 ConversationService 事务内调用")
        if recommendation is None:
            return _execution(
                request_id=request_id,
                status="awaiting_plan",
                plan_digest=None,
                issues=[_issue("PLAN_NOT_READY", "导引仍在澄清，尚无可执行计划")],
            )

        plan_digest = _canonical_digest(recommendation)
        if recommendation.get("decision") != "orchestrate":
            return _execution(
                request_id=request_id,
                status="refused",
                plan_digest=plan_digest,
                issues=[_issue("PLAN_REFUSED", "导引已明确拒绝，未创建任务")],
            )

        agents = recommendation.get("agents")
        if not isinstance(agents, list) or len(agents) != 1:
            return _execution(
                request_id=request_id,
                status="blocked_conflict",
                plan_digest=plan_digest,
                issues=[
                    _issue(
                        "EXECUTABLE_GRAPH_REQUIRED",
                        "多 Agent 计划尚无机器可读依赖图，不能从 workflow 文本猜执行顺序",
                    )
                ],
            )
        if (
            recommendation.get("dropped_agents") != []
            or recommendation.get("capped") is not False
        ):
            return _execution(
                request_id=request_id,
                status="blocked_conflict",
                plan_digest=plan_digest,
                issues=[
                    _issue("PLAN_DEGRADED", "计划发生剥离或截断，禁止自动执行残缺方案")
                ],
            )

        planned = agents[0]
        agent_id = planned.get("agent_id")
        if not isinstance(agent_id, str):
            return _execution(
                request_id=request_id,
                status="blocked_conflict",
                plan_digest=plan_digest,
                issues=[_issue("AGENT_ID_INVALID", "计划缺少合法 Agent id")],
            )
        if planned.get("stripped_fields") != []:
            return _execution(
                request_id=request_id,
                status="blocked_input",
                plan_digest=plan_digest,
                issues=[
                    _issue(
                        "INPUT_FIELDS_STRIPPED",
                        "计划含被剥离的非法输入，禁止静默降级后执行",
                        agent_id=agent_id,
                        fields=planned.get("stripped_fields"),
                    )
                ],
            )

        registered_agent = self._registry.get(agent_id)
        agent = copy.deepcopy(registered_agent) if isinstance(registered_agent, dict) else None
        if (
            agent is None
            or not agent_is_callable(agent, mode="job")
        ):
            return _execution(
                request_id=request_id,
                status="blocked_conflict",
                plan_digest=plan_digest,
                issues=[
                    _issue("AGENT_UNAVAILABLE", "Agent 已不可执行或版本状态发生变化", agent_id=agent_id)
                ],
            )

        inputs = planned.get("prefilled_inputs")
        inputs = inputs if isinstance(inputs, dict) else {}
        schema = _load_input_schema(self._registry, agent_id)
        if schema is None:
            return _execution(
                request_id=request_id,
                status="blocked_input",
                plan_digest=plan_digest,
                issues=[
                    _issue("INPUT_SCHEMA_UNAVAILABLE", "无法读取完整输入契约", agent_id=agent_id)
                ],
            )
        missing = _required_fields_missing(schema, inputs)
        if missing:
            return _execution(
                request_id=request_id,
                status="blocked_input",
                plan_digest=plan_digest,
                issues=[
                    _issue(
                        "MISSING_REQUIRED_INPUT",
                        "计划缺少必填输入，请在当前会话补充",
                        agent_id=agent_id,
                        fields=missing,
                    )
                ],
            )
        errors = sorted(Draft202012Validator(schema).iter_errors(inputs), key=lambda e: list(e.path))
        if errors:
            return _execution(
                request_id=request_id,
                status="blocked_input",
                plan_digest=plan_digest,
                issues=[
                    _issue(
                        "INPUT_SCHEMA_INVALID",
                        "完整输入未通过 Agent 契约",
                        agent_id=agent_id,
                        fields=[".".join(str(p) for p in error.path) or "$" for error in errors[:8]],
                    )
                ],
            )

        # 附件当前只有会话级集合，尚无 per-agent 绑定与所有权 envelope。即使模型
        # 产出了真实 agent_id，也保持零任务，封住已知附件回显注入残余。
        if has_attachments is not False:
            return _execution(
                request_id=request_id,
                status="blocked_source",
                plan_digest=plan_digest,
                issues=[
                    _issue(
                        "ATTACHMENT_BINDING_REQUIRED",
                        "含附件的计划尚无安全的逐 Agent 绑定与来源授权，未自动执行",
                    )
                ],
            )

        if not _has_explicit_input_mapping(inputs, current_user_content):
            return _execution(
                request_id=request_id,
                status="blocked_source",
                plan_digest=plan_digest,
                issues=[
                    _issue(
                        "UNVERIFIED_INPUT_SOURCE",
                        "计划输入未与用户显式 JSON 字段映射完全一致；请在当前会话直接提供输入对象，禁止让模型决定字段归属",
                        agent_id=agent_id,
                    )
                ],
            )

        allowed = self._is_safe_auto_agent(agent, actor_role)
        if not allowed:
            return _execution(
                request_id=request_id,
                status="blocked_policy",
                plan_digest=plan_digest,
                issues=[
                    _issue(
                        "AGENT_NOT_AUTO_EXECUTABLE",
                        "Agent 未声明无副作用自动执行能力，或当前认证角色不在执行权限内",
                        agent_id=agent_id,
                        actor_role=actor_role,
                    )
                ],
            )

        planned_version = planned.get("agent_version")
        current_version = agent.get("version")
        if not isinstance(planned_version, str) or planned_version != current_version:
            return _execution(
                request_id=request_id,
                status="blocked_conflict",
                plan_digest=plan_digest,
                issues=[
                    _issue(
                        "AGENT_VERSION_DRIFT",
                        "计划未锁定当前 Agent 版本或版本已漂移",
                        agent_id=agent_id,
                    )
                ],
            )

        latest_agent = self._registry.get(agent_id)
        if (
            latest_agent is None
            or latest_agent != agent
            or not self._is_safe_auto_agent(latest_agent, actor_role)
            or latest_agent.get("version") != planned_version
        ):
            return _execution(
                request_id=request_id,
                status="blocked_conflict",
                plan_digest=plan_digest,
                issues=[
                    _issue(
                        "AGENT_MANIFEST_DRIFT",
                        "Agent manifest 在计划校验期间发生变化；请基于当前版本重新生成方案",
                        agent_id=agent_id,
                    )
                ],
            )

        task_id = f"task_{uuid.uuid4().hex}"
        automation_meta = {
            "mode": "safe_auto",
            "request_id": request_id,
            "plan_digest": plan_digest,
            "initiated_by_username": actor_username,
            "authorized_role": actor_role,
            "materialized_by": "guide_plan_dispatch",
            "created_via": "authenticated_conversation_turn",
        }
        repos.create_task(
            conn,
            task_id=task_id,
            agent_id=agent_id,
            agent_version=current_version,
            name=f"{agent.get('name') or agent_id} · 自动执行",
            created_by=actor_display_name,
            created_by_username=actor_username,
            inputs=inputs,
            input_file_ids=[],
            metadata={"automation": automation_meta},
            conversation_id=conversation_id,
        )
        task = repos.set_task_status_in_transaction(conn, task_id, "queued")
        repos.append_event(
            conn,
            task_id=task_id,
            agent_id=agent_id,
            event_type="task_created",
            level="info",
            message=f"任务已由会话授权自动创建：agent={agent_id}",
            payload={
                "created_by": actor_display_name,
                "created_by_username": actor_username,
                "created_via": "guide_plan_dispatch",
                "status_from": "created",
                "status_to": task["status"],
                "depends_on": [],
                "request_id": request_id,
                "plan_digest": plan_digest,
            },
        )
        return _execution(
            request_id=request_id,
            status="dispatched",
            plan_digest=plan_digest,
            task_ids=[task_id],
        )
