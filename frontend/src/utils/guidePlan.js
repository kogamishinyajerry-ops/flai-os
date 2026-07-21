// Guide 计划的唯一前端 roster / task 投影：版本化 DAG 优先，legacy agents[] 兼容。
// 只读后端给出的结构，不从 workflow 文本、Agent 名称或任务先后关系猜节点或边。

export const GUIDE_DAG_CONTRACT = "guide_dag.v1";


export function isGuideDagPlan(plan) {
  return plan?.contract === GUIDE_DAG_CONTRACT;
}


export function isLegacyGuidePlan(plan) {
  return Boolean(
    plan?.decision === "orchestrate" &&
    plan.contract === undefined &&
    Array.isArray(plan.agents),
  );
}


export function guidePlanAgents(plan) {
  if (!plan || plan.decision !== "orchestrate") return [];
  if (isGuideDagPlan(plan)) return Array.isArray(plan.nodes) ? plan.nodes : [];
  if (isLegacyGuidePlan(plan)) return plan.agents;
  return [];
}


export function guidePlanAllowsManualCreate(plan) {
  return isLegacyGuidePlan(plan);
}


function emptyIndex(mode, reason = "") {
  return {
    mode,
    valid: reason === "",
    reason,
    byNodeId: new Map(),
    byAgentId: new Map(),
    claimedTaskIds: new Set(),
  };
}


function invalidDag(reason) {
  return emptyIndex("dag", reason);
}


function indexLegacyTasks(plan, tasks) {
  const index = emptyIndex("legacy");
  const rosterAgentIds = new Set(
    guidePlanAgents(plan)
      .map((agent) => agent?.agent_id)
      .filter((agentId) => typeof agentId === "string" && agentId.length > 0),
  );

  for (const task of tasks) {
    if (!task || !rosterAgentIds.has(task.agent_id)) continue;
    const grouped = index.byAgentId.get(task.agent_id) || [];
    grouped.push(task);
    index.byAgentId.set(task.agent_id, grouped);
    if (typeof task.id === "string" && task.id.length > 0) {
      index.claimedTaskIds.add(task.id);
    }
  }
  return index;
}


function indexDagTasks(plan, tasks) {
  const nodes = guidePlanAgents(plan);
  if (nodes.length < 1 || nodes.length > 5) {
    return invalidDag("版本化 DAG 必须包含 1 至 5 个节点");
  }
  const execution = plan?.execution;
  if (!execution || execution.status !== "dispatched") {
    return invalidDag("版本化 DAG 缺少已派发执行回执");
  }
  if (execution.graph_version !== GUIDE_DAG_CONTRACT) {
    return invalidDag("版本化 DAG 的 graph_version 不可验证");
  }
  if (!Array.isArray(execution.node_tasks)) {
    return invalidDag("版本化 DAG 缺少 node_tasks 权威映射");
  }

  const nodesById = new Map();
  for (const node of nodes) {
    if (
      !node ||
      typeof node.node_id !== "string" ||
      node.node_id.length === 0 ||
      typeof node.agent_id !== "string" ||
      node.agent_id.length === 0 ||
      nodesById.has(node.node_id)
    ) {
      return invalidDag("版本化 DAG 节点标识不完整或重复");
    }
    nodesById.set(node.node_id, node);
  }

  if (execution.node_tasks.length !== nodesById.size) {
    return invalidDag("版本化 DAG 的 node_tasks 未完整覆盖全部节点");
  }

  const bindingByNodeId = new Map();
  const boundTaskIds = new Set();
  for (const binding of execution.node_tasks) {
    if (
      !binding ||
      typeof binding.node_id !== "string" ||
      typeof binding.task_id !== "string" ||
      binding.task_id.length === 0 ||
      bindingByNodeId.has(binding.node_id) ||
      boundTaskIds.has(binding.task_id)
    ) {
      return invalidDag("版本化 DAG 的 node_id/task_id 映射不完整或重复");
    }
    const node = nodesById.get(binding.node_id);
    if (!node) return invalidDag("版本化 DAG 的 node_tasks 包含未知节点");
    if (binding.agent_id !== node.agent_id) {
      return invalidDag("版本化 DAG 的节点 Agent 与任务映射不一致");
    }
    bindingByNodeId.set(binding.node_id, binding);
    boundTaskIds.add(binding.task_id);
  }

  for (const nodeId of nodesById.keys()) {
    if (!bindingByNodeId.has(nodeId)) {
      return invalidDag("版本化 DAG 的 node_tasks 未完整覆盖全部节点");
    }
  }

  const taskById = new Map();
  for (const task of tasks) {
    if (!task || typeof task.id !== "string" || task.id.length === 0) continue;
    if (taskById.has(task.id)) {
      return invalidDag("会话任务列表含重复 task_id，无法验证 DAG 映射");
    }
    taskById.set(task.id, task);
  }

  const index = emptyIndex("dag");
  for (const [nodeId, binding] of bindingByNodeId) {
    index.claimedTaskIds.add(binding.task_id);
    const task = taskById.get(binding.task_id);
    if (!task) {
      index.byNodeId.set(nodeId, []);
      continue;
    }
    if (task.agent_id !== nodesById.get(nodeId).agent_id) {
      return invalidDag("权威 task_id 对应的任务 Agent 与 DAG 节点不一致");
    }
    index.byNodeId.set(nodeId, [task]);
  }
  return index;
}


export function indexGuidePlanTasks(plan, tasks = []) {
  const normalizedTasks = Array.isArray(tasks) ? tasks : [];
  if (isGuideDagPlan(plan)) return indexDagTasks(plan, normalizedTasks);
  if (isLegacyGuidePlan(plan)) return indexLegacyTasks(plan, normalizedTasks);
  return emptyIndex("unsupported", "未知版本的 Guide 计划禁止回退到 legacy 任务匹配");
}


export function guidePlanTaskMappingIssue(plan, tasks = []) {
  if (plan?.execution?.status !== "dispatched") return "";
  const index = indexGuidePlanTasks(plan, tasks);
  return index.valid
    ? ""
    : index.reason || "版本化 Guide 计划的任务映射不可验证";
}


export function tasksForGuidePlanAgent(index, agent) {
  if (!index?.valid || !agent) return [];
  if (index.mode === "dag") return index.byNodeId.get(agent.node_id) || [];
  return index.byAgentId.get(agent.agent_id) || [];
}
