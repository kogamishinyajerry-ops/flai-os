"""受限导引计划派发：原子物化 legacy 安全单节点或版本化多 Agent DAG。

这个模块只替代机械的“去创建任务/提交”动作，不触碰人工 review：它永不调用
review API、永不写 ``review_approved``，也不把任务标成 completed。任何无法由
确定性规则证明安全的计划都返回可见 blocker，并保持零任务。
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Sequence

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from ..auth.authorization import agent_is_callable, role_can_access_agent
from ..storage import repos
from .manifest import MANIFEST_PIN_VERSION


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _bare_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _issue(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **details}


def _execution(
    *,
    request_id: str,
    status: str,
    plan_digest: str | None,
    issues: list[dict[str, Any]] | None = None,
    task_ids: list[str] | None = None,
    graph_version: str | None = None,
    graph_digest: str | None = None,
    node_tasks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result = {
        "mode": "safe_auto",
        "request_id": request_id,
        "status": status,
        "plan_digest": plan_digest,
        "task_ids": task_ids or [],
        "issues": issues or [],
        "replayed": False,
    }
    if graph_version is not None:
        result.update(
            {
                "graph_version": graph_version,
                "graph_digest": graph_digest,
                "node_tasks": node_tasks or [],
            }
        )
    return result


def _executable_graph_payload(recommendation: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract": recommendation["contract"],
        "nodes": [
            {
                "node_id": node["node_id"],
                "agent_id": node["agent_id"],
                "agent_version": node.get("agent_version"),
                "prefilled_inputs": node.get("prefilled_inputs"),
                "depends_on": node.get("depends_on"),
                "artifact_binding": node.get("artifact_binding"),
                "attachment_binding": node.get("attachment_binding"),
            }
            for node in recommendation["nodes"]
        ],
    }


def _load_input_schema(registry: Any, agent_id: str) -> dict[str, Any] | None:
    try:
        snapshot_getter = getattr(registry, "execution_snapshot", None)
        snapshot = snapshot_getter(agent_id) if callable(snapshot_getter) else None
        if snapshot is not None:
            manifest = snapshot.manifest
            schema_name = (manifest.get("input") or {}).get("schema")
            if not isinstance(schema_name, str) or not schema_name:
                return None
            loaded = json.loads(snapshot.read_file(schema_name))
        else:
            # 仅保留测试 shim/旧 Registry 的兼容读取；正式 AgentRegistry 必须走
            # 不可变 execution_snapshot，缺快照不能进入任务物化。
            package_dir = registry.package_dir(agent_id)
            if package_dir is None:
                return None
            schema_path = Path(package_dir) / "input_schema.json"
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


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"JSON 浮点数溢出为非有限值：{value}")
    return parsed


def _has_explicit_input_mapping(inputs: dict[str, Any], content: str) -> bool:
    """整条用户消息必须是计划输入本身或精确的 ``inputs`` envelope。"""
    try:
        candidate = json.loads(
            content,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonfinite_json,
            parse_float=_parse_finite_float,
        )
    except (json.JSONDecodeError, RecursionError, TypeError, ValueError):
        return False
    if not isinstance(candidate, dict):
        return False
    if _canonical_digest(candidate) == _canonical_digest(inputs):
        return True
    return (
        set(candidate) == {"inputs"}
        and isinstance(candidate.get("inputs"), dict)
        and _canonical_digest(candidate["inputs"]) == _canonical_digest(inputs)
    )


def _has_explicit_dag_input_mapping(
    nodes: list[dict[str, Any]], content: str
) -> bool:
    expected = {node["agent_id"]: node.get("prefilled_inputs") for node in nodes}
    if any(not isinstance(value, dict) for value in expected.values()):
        return False
    try:
        candidate = json.loads(
            content,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonfinite_json,
            parse_float=_parse_finite_float,
        )
    except (json.JSONDecodeError, RecursionError, TypeError, ValueError):
        return False
    if not isinstance(candidate, dict) or set(candidate) != {"inputs_by_agent"}:
        return False
    mapping = candidate.get("inputs_by_agent")
    return (
        isinstance(mapping, dict)
        and set(mapping) == set(expected)
        and all(
            _canonical_digest(mapping[agent_id]) == _canonical_digest(expected_inputs)
            for agent_id, expected_inputs in expected.items()
        )
    )


def _dag_structure_issue(recommendation: dict[str, Any]) -> dict[str, Any] | None:
    if (
        recommendation.get("dropped_agents") != []
        or recommendation.get("capped") is not False
    ):
        return _issue("PLAN_DEGRADED", "DAG 计划发生剥离或截断，禁止自动执行残缺方案")
    nodes = recommendation.get("nodes")
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 5:
        return _issue("GRAPH_NODE_COUNT_INVALID", "DAG 节点数必须为 1 到 5")
    seen_node_ids: set[str] = set()
    seen_agent_ids: set[str] = set()
    referenced_node_ids: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            return _issue("GRAPH_NODE_INVALID", "DAG 节点必须是对象")
        node_id = node.get("node_id")
        if (
            not isinstance(node_id, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", node_id) is None
            or node_id in seen_node_ids
        ):
            return _issue("GRAPH_NODE_ID_INVALID", "DAG node_id 缺失或重复")
        agent_id = node.get("agent_id")
        if not isinstance(agent_id, str) or not agent_id:
            return _issue("AGENT_ID_INVALID", "DAG 节点缺少合法 Agent id", node_id=node_id)
        if agent_id in seen_agent_ids:
            return _issue(
                "GRAPH_AGENT_DUPLICATE",
                "guide_dag.v1 不允许重复调用同一 Agent",
                agent_id=agent_id,
            )
        depends_on = node.get("depends_on")
        if (
            not isinstance(depends_on, list)
            or any(not isinstance(dep, str) for dep in depends_on)
            or len(depends_on) != len(set(depends_on))
            or any(dep not in seen_node_ids for dep in depends_on)
        ):
            return _issue(
                "GRAPH_DEPENDENCY_ORDER_INVALID",
                "DAG 依赖必须唯一且只能引用拓扑序中已经出现的节点",
                node_id=node_id,
            )
        binding = node.get("artifact_binding")
        if not isinstance(binding, dict) or set(binding) != {"mode", "from_nodes"}:
            return _issue(
                "ARTIFACT_BINDING_INVALID",
                "artifact_binding 必须显式声明 mode 与 from_nodes",
                node_id=node_id,
            )
        mode = binding.get("mode")
        from_nodes = binding.get("from_nodes")
        binding_valid = (
            isinstance(from_nodes, list)
            and all(isinstance(item, str) for item in from_nodes)
            and len(from_nodes) == len(set(from_nodes))
            and set(from_nodes).issubset(set(depends_on))
        )
        if mode == "none":
            binding_valid = binding_valid and not depends_on and from_nodes == []
        elif mode == "all":
            binding_valid = binding_valid and bool(depends_on) and from_nodes == depends_on
        elif mode == "selected":
            binding_valid = binding_valid and bool(depends_on) and bool(from_nodes)
        else:
            binding_valid = False
        if not binding_valid:
            return _issue(
                "ARTIFACT_BINDING_INVALID",
                "artifact_binding 只能选择当前节点显式 depends_on 内的来源",
                node_id=node_id,
            )
        referenced_node_ids.update(depends_on)
        seen_node_ids.add(node_id)
        seen_agent_ids.add(agent_id)
    leaves = seen_node_ids - referenced_node_ids
    if len(leaves) != 1:
        return _issue(
            "GRAPH_LEAF_COUNT_INVALID",
            "guide_dag.v1 必须恰好有一个最终叶节点",
            leaf_count=len(leaves),
        )
    return None


def _dag_attachment_admission(
    nodes: list[dict[str, Any]],
    *,
    actor_username: str,
    has_attachments: bool,
    current_file_bindings: Sequence[dict[str, Any]] | None,
    has_historical_attachments: bool,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str | None]:
    if has_historical_attachments is not False:
        return (
            _issue(
                "HISTORICAL_ATTACHMENT_SOURCE_UNBOUND",
                "历史轮附件不能作为当前 safe-auto DAG 的授权来源",
            ),
            [],
            None,
        )
    targets: list[str] = []
    for node in nodes:
        binding = node.get("attachment_binding")
        if not isinstance(binding, dict) or set(binding) != {"mode"}:
            return (
                _issue(
                    "ATTACHMENT_BINDING_MISMATCH",
                    "attachment_binding 必须严格声明 mode",
                    node_id=node["node_id"],
                ),
                [],
                None,
            )
        mode = binding.get("mode")
        if mode == "current_turn":
            targets.append(node["node_id"])
        elif mode != "none":
            return (
                _issue(
                    "ATTACHMENT_BINDING_MISMATCH",
                    "attachment_binding.mode 只允许 none 或 current_turn",
                    node_id=node["node_id"],
                ),
                [],
                None,
            )

    try:
        frozen = copy.deepcopy(list(current_file_bindings or ()))
    except (TypeError, ValueError, RecursionError):
        frozen = []
        return (
            _issue("ATTACHMENT_BINDING_MISMATCH", "当前轮附件来源证据无法冻结"),
            frozen,
            None,
        )
    valid_bindings = len(frozen) <= 5
    file_ids: list[str] = []
    for item in frozen:
        if not isinstance(item, dict) or set(item) != {
            "file_id",
            "sha256",
            "classification",
            "uploaded_by_username",
        }:
            valid_bindings = False
            continue
        file_id = item.get("file_id")
        sha256 = item.get("sha256")
        valid_bindings = valid_bindings and (
            isinstance(file_id, str)
            and 1 <= len(file_id) <= 128
            and isinstance(sha256, str)
            and re.fullmatch(r"[a-f0-9]{64}", sha256) is not None
            and item.get("classification") == "internal"
            and item.get("uploaded_by_username") == actor_username
        )
        if isinstance(file_id, str):
            file_ids.append(file_id)
    if len(file_ids) != len(set(file_ids)):
        valid_bindings = False
    if not valid_bindings:
        return (
            _issue(
                "ATTACHMENT_BINDING_MISMATCH",
                "当前轮附件证据不完整、重复、非 internal 或不属于当前主体",
            ),
            [],
            None,
        )

    if has_attachments is not False and not frozen:
        return (
            _issue(
                "ATTACHMENT_BINDING_MISMATCH",
                "请求声明含当前轮附件，但没有可持久化的来源证据",
            ),
            [],
            None,
        )
    if frozen:
        if len(targets) != 1:
            return (
                _issue(
                    "ATTACHMENT_TARGET_AMBIGUOUS",
                    "当前轮附件必须全集且仅绑定到一个 DAG 节点",
                    target_count=len(targets),
                ),
                [],
                None,
            )
        return None, frozen, targets[0]
    if targets:
        return (
            _issue(
                "ATTACHMENT_BINDING_MISMATCH",
                "DAG 声明 current_turn 附件绑定，但当前轮没有附件证据",
            ),
            [],
            None,
        )
    return None, [], None


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

    def accessible_agent_ids(self, actor_role: str) -> set[str]:
        """模型候选面只包含当前主体可发现且可调用的 job Agent。"""
        return {
            agent["id"]
            for agent in self._registry.list()
            if isinstance(agent.get("id"), str)
            and agent_is_callable(agent, mode="job")
            and role_can_access_agent(agent, actor_role)
        }

    def _validate_dag_agents(
        self, nodes: list[dict[str, Any]], actor_role: str
    ) -> tuple[
        str | None,
        dict[str, Any] | None,
        dict[str, dict[str, Any]],
        dict[str, str],
    ]:
        referenced = {
            dependency
            for node in nodes
            for dependency in node["depends_on"]
        }
        leaf_id = next(node["node_id"] for node in nodes if node["node_id"] not in referenced)
        frozen: dict[str, dict[str, Any]] = {}
        frozen_digests: dict[str, str] = {}
        for node in nodes:
            node_id = node["node_id"]
            agent_id = node["agent_id"]
            if node.get("stripped_fields") != []:
                return (
                    "blocked_input",
                    _issue(
                        "INPUT_FIELDS_STRIPPED",
                        "DAG 节点含被剥离输入，禁止执行残缺图",
                        node_id=node_id,
                        agent_id=agent_id,
                    ),
                    {},
                    {},
                )
            snapshot_getter = getattr(self._registry, "execution_snapshot", None)
            snapshot = snapshot_getter(agent_id) if callable(snapshot_getter) else None
            agent = snapshot.manifest if snapshot is not None else None
            if agent is None or not agent_is_callable(agent, mode="job"):
                return (
                    "blocked_conflict",
                    _issue(
                        "AGENT_UNAVAILABLE",
                        "DAG 节点 Agent 已不可执行",
                        node_id=node_id,
                        agent_id=agent_id,
                    ),
                    {},
                    {},
                )
            planned_version = node.get("agent_version")
            if (
                not isinstance(planned_version, str)
                or planned_version != agent.get("version")
            ):
                return (
                    "blocked_conflict",
                    _issue(
                        "AGENT_VERSION_DRIFT",
                        "DAG 节点未锁定当前 Agent 版本或版本已漂移",
                        node_id=node_id,
                        agent_id=agent_id,
                    ),
                    {},
                    {},
                )
            if not self._is_safe_auto_agent(agent, actor_role):
                return (
                    "blocked_policy",
                    _issue(
                        "AGENT_NOT_AUTO_EXECUTABLE",
                        "DAG 节点未通过 safe-auto 权限与无副作用策略",
                        node_id=node_id,
                        agent_id=agent_id,
                        actor_role=actor_role,
                    ),
                    {},
                    {},
                )
            workflow = agent.get("workflow") or {}
            if node_id != leaf_id and (
                (agent.get("model") or {}).get("profile") != "none"
                or workflow.get("requires_human_review") is not False
            ):
                return (
                    "blocked_policy",
                    _issue(
                        "PROVISIONAL_EDGE_UNSUPPORTED",
                        "非叶节点必须是零模型且无需人工审核的确定性 Agent",
                        node_id=node_id,
                        agent_id=agent_id,
                    ),
                    {},
                    {},
                )
            if node_id == leaf_id and workflow.get("requires_human_review") is not True:
                return (
                    "blocked_policy",
                    _issue(
                        "FINAL_REVIEW_REQUIRED",
                        "唯一叶节点必须显式停在人工审核，LLM 不进入最终签发链",
                        node_id=node_id,
                        agent_id=agent_id,
                    ),
                    {},
                    {},
                )
            frozen[node_id] = agent
            frozen_digests[node_id] = snapshot.digest
        return None, None, frozen, frozen_digests

    def _validate_dag_inputs(
        self, nodes: list[dict[str, Any]]
    ) -> tuple[str | None, dict[str, Any] | None]:
        for node in nodes:
            node_id = node["node_id"]
            agent_id = node["agent_id"]
            inputs = node.get("prefilled_inputs")
            if not isinstance(inputs, dict):
                return (
                    "blocked_input",
                    _issue(
                        "INPUT_SCHEMA_INVALID",
                        "DAG 节点 prefilled_inputs 必须是对象",
                        node_id=node_id,
                        agent_id=agent_id,
                    ),
                )
            schema = _load_input_schema(self._registry, agent_id)
            if schema is None:
                return (
                    "blocked_input",
                    _issue(
                        "INPUT_SCHEMA_UNAVAILABLE",
                        "无法读取 DAG 节点完整输入契约",
                        node_id=node_id,
                        agent_id=agent_id,
                    ),
                )
            missing = _required_fields_missing(schema, inputs)
            if missing:
                return (
                    "blocked_input",
                    _issue(
                        "MISSING_REQUIRED_INPUT",
                        "DAG 节点缺少必填输入",
                        node_id=node_id,
                        agent_id=agent_id,
                        fields=missing,
                    ),
                )
            errors = sorted(
                Draft202012Validator(schema).iter_errors(inputs),
                key=lambda error: list(error.path),
            )
            if errors:
                return (
                    "blocked_input",
                    _issue(
                        "INPUT_SCHEMA_INVALID",
                        "DAG 节点完整输入未通过 Agent 契约",
                        node_id=node_id,
                        agent_id=agent_id,
                        fields=[
                            ".".join(str(part) for part in error.path) or "$"
                            for error in errors[:8]
                        ],
                    ),
                )
        return None, None

    def _dag_manifests_still_match(
        self,
        nodes: list[dict[str, Any]],
        frozen_agents: dict[str, dict[str, Any]],
        frozen_digests: dict[str, str],
        actor_role: str,
    ) -> dict[str, Any] | None:
        for node in nodes:
            node_id = node["node_id"]
            agent_id = node["agent_id"]
            snapshot_getter = getattr(self._registry, "execution_snapshot", None)
            snapshot = snapshot_getter(agent_id) if callable(snapshot_getter) else None
            latest = snapshot.manifest if snapshot is not None else None
            if (
                not isinstance(latest, dict)
                or snapshot.digest != frozen_digests[node_id]
                or latest != frozen_agents[node_id]
                or not self._is_safe_auto_agent(latest, actor_role)
                or latest.get("version") != node.get("agent_version")
            ):
                return _issue(
                    "AGENT_MANIFEST_DRIFT",
                    "DAG 节点 manifest 在校验期间发生变化，请重新生成方案",
                    node_id=node_id,
                    agent_id=agent_id,
                )
        return None

    def _materialize_dag(
        self,
        conn: sqlite3.Connection,
        *,
        conversation_id: str,
        recommendation: dict[str, Any],
        request_id: str,
        actor_display_name: str,
        actor_username: str,
        actor_role: str,
        plan_digest: str,
        frozen_agents: dict[str, dict[str, Any]],
        frozen_manifest_digests: dict[str, str],
        current_file_bindings: list[dict[str, Any]],
        attachment_node_id: str | None,
    ) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = recommendation["nodes"]
        graph_digest = _bare_digest(_executable_graph_payload(recommendation))
        task_id_by_node = {
            node["node_id"]: f"task_{uuid.uuid4().hex}" for node in nodes
        }
        node_tasks: list[dict[str, Any]] = []
        for node in nodes:
            node_id = node["node_id"]
            agent_id = node["agent_id"]
            agent = frozen_agents[node_id]
            dependency_task_ids = [
                task_id_by_node[dependency] for dependency in node["depends_on"]
            ]
            source_node_ids = node["artifact_binding"]["from_nodes"]
            from_tasks = [task_id_by_node[source] for source in source_node_ids]
            node_file_bindings = (
                current_file_bindings if node_id == attachment_node_id else []
            )
            attached_sources = [
                {
                    "slot": "input_file_ids",
                    "file_id": binding["file_id"],
                    "conversation_id": conversation_id,
                    "uploaded_by_username": binding["uploaded_by_username"],
                    "sha256": binding["sha256"],
                    "classification": binding["classification"],
                    "kind": "input",
                    "task_id": None,
                }
                for binding in node_file_bindings
            ]
            source_binding = {
                "version": "task_source.v1",
                "graph_digest": graph_digest,
                "node_id": node_id,
                "request_id": request_id,
                "params": {
                    "kind": "current_turn_json",
                    "json_pointer": f"/inputs_by_agent/{agent_id}",
                    "value_digest": _bare_digest(node["prefilled_inputs"]),
                },
                "attachments": attached_sources,
            }
            automation_meta = {
                "mode": "safe_auto",
                "manifest_pin_version": MANIFEST_PIN_VERSION,
                "agent_manifest_digest": frozen_manifest_digests[node_id],
                "request_id": request_id,
                "plan_digest": plan_digest,
                "graph_version": "guide_dag.v1",
                "graph_digest": graph_digest,
                "node_id": node_id,
                "initiated_by_username": actor_username,
                "authorized_role": actor_role,
                "materialized_by": "guide_plan_dispatch",
                "created_via": "authenticated_conversation_turn",
            }
            task_id = task_id_by_node[node_id]
            task = repos.create_task(
                conn,
                task_id=task_id,
                agent_id=agent_id,
                agent_version=node["agent_version"],
                name=f"{agent.get('name') or agent_id} · 自动执行 · {node_id}",
                created_by=actor_display_name,
                created_by_username=actor_username,
                inputs=node["prefilled_inputs"],
                input_file_ids=[binding["file_id"] for binding in node_file_bindings],
                metadata={"automation": automation_meta},
                conversation_id=conversation_id,
                depends_on=dependency_task_ids,
                input_binding={"from_tasks": from_tasks},
                source_binding=source_binding,
            )
            if not dependency_task_ids:
                task = repos.set_task_status_in_transaction(conn, task_id, "queued")
            initial_status = task["status"]
            repos.append_event(
                conn,
                task_id=task_id,
                agent_id=agent_id,
                event_type="task_created",
                level="info",
                message=f"DAG 节点已由当前会话授权自动创建：node={node_id}",
                payload={
                    "created_by": actor_display_name,
                    "created_by_username": actor_username,
                    "created_via": "guide_plan_dispatch",
                    "status_from": "created",
                    "status_to": initial_status,
                    "depends_on": dependency_task_ids,
                    "input_binding": {"from_tasks": from_tasks},
                    "request_id": request_id,
                    "plan_digest": plan_digest,
                    "graph_version": "guide_dag.v1",
                    "graph_digest": graph_digest,
                    "node_id": node_id,
                },
            )
            node_tasks.append(
                {
                    "node_id": node_id,
                    "agent_id": agent_id,
                    "task_id": task_id,
                    "initial_status": initial_status,
                }
            )
        return _execution(
            request_id=request_id,
            status="dispatched",
            plan_digest=plan_digest,
            task_ids=[item["task_id"] for item in node_tasks],
            graph_version="guide_dag.v1",
            graph_digest=graph_digest,
            node_tasks=node_tasks,
        )

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
        has_attachments: bool = False,
        current_file_bindings: Sequence[dict[str, Any]] | None = None,
        has_historical_attachments: bool = False,
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

        contract = recommendation.get("contract")
        if contract is not None and contract != "guide_dag.v1":
            return _execution(
                request_id=request_id,
                status="blocked_conflict",
                plan_digest=plan_digest,
                issues=[
                    _issue(
                        "GRAPH_CONTRACT_UNSUPPORTED",
                        "DAG 计划契约版本不受支持，未创建任何任务",
                        contract=contract,
                    )
                ],
            )
        if contract == "guide_dag.v1":
            graph_issue = _dag_structure_issue(recommendation)
            if graph_issue is not None:
                return _execution(
                    request_id=request_id,
                    status="blocked_conflict",
                    plan_digest=plan_digest,
                    issues=[graph_issue],
                )
            attachment_issue, _dag_file_bindings, _dag_attachment_node_id = (
                _dag_attachment_admission(
                    recommendation["nodes"],
                    actor_username=actor_username,
                    has_attachments=has_attachments,
                    current_file_bindings=current_file_bindings,
                    has_historical_attachments=has_historical_attachments,
                )
            )
            if attachment_issue is not None:
                return _execution(
                    request_id=request_id,
                    status="blocked_source",
                    plan_digest=plan_digest,
                    issues=[attachment_issue],
                )
            (
                graph_status,
                graph_issue,
                _frozen_agents,
                _frozen_manifest_digests,
            ) = self._validate_dag_agents(recommendation["nodes"], actor_role)
            if graph_issue is not None:
                return _execution(
                    request_id=request_id,
                    status=graph_status or "blocked_conflict",
                    plan_digest=plan_digest,
                    issues=[graph_issue],
                )
            input_status, input_issue = self._validate_dag_inputs(recommendation["nodes"])
            if input_issue is not None:
                return _execution(
                    request_id=request_id,
                    status=input_status or "blocked_input",
                    plan_digest=plan_digest,
                    issues=[input_issue],
                )
            if not _has_explicit_dag_input_mapping(
                recommendation["nodes"], current_user_content
            ):
                return _execution(
                    request_id=request_id,
                    status="blocked_source",
                    plan_digest=plan_digest,
                    issues=[
                        _issue(
                            "UNVERIFIED_INPUT_SOURCE",
                            "DAG 输入必须来自当前轮顶层 inputs_by_agent，且与所有节点冻结输入逐值完全一致",
                        )
                    ],
                )
            manifest_issue = self._dag_manifests_still_match(
                recommendation["nodes"],
                _frozen_agents,
                _frozen_manifest_digests,
                actor_role,
            )
            if manifest_issue is not None:
                return _execution(
                    request_id=request_id,
                    status="blocked_conflict",
                    plan_digest=plan_digest,
                    issues=[manifest_issue],
                )
            return self._materialize_dag(
                conn,
                conversation_id=conversation_id,
                recommendation=recommendation,
                request_id=request_id,
                actor_display_name=actor_display_name,
                actor_username=actor_username,
                actor_role=actor_role,
                plan_digest=plan_digest,
                frozen_agents=_frozen_agents,
                frozen_manifest_digests=_frozen_manifest_digests,
                current_file_bindings=_dag_file_bindings,
                attachment_node_id=_dag_attachment_node_id,
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

        snapshot_getter = getattr(self._registry, "execution_snapshot", None)
        registered_snapshot = (
            snapshot_getter(agent_id) if callable(snapshot_getter) else None
        )
        if registered_snapshot is not None:
            agent = registered_snapshot.manifest
            manifest_digest = registered_snapshot.digest
        else:
            registered_agent = self._registry.get(agent_id)
            agent = copy.deepcopy(registered_agent) if isinstance(registered_agent, dict) else None
            manifest_digest = None
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
        if (
            has_attachments is not False
            or bool(current_file_bindings)
            or has_historical_attachments is not False
        ):
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

        latest_snapshot = (
            snapshot_getter(agent_id) if callable(snapshot_getter) else None
        )
        latest_agent = (
            latest_snapshot.manifest
            if latest_snapshot is not None
            else self._registry.get(agent_id)
        )
        if (
            latest_agent is None
            or latest_snapshot is None
            or latest_snapshot.digest != manifest_digest
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
            "manifest_pin_version": MANIFEST_PIN_VERSION,
            "agent_manifest_digest": manifest_digest,
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
