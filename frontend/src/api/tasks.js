import { request } from "./client";

export const createTask = ({ agentId, name, inputs, inputFileIds, createdBy }) =>
  request("/api/tasks", {
    method: "POST",
    json: {
      agent_id: agentId,
      name: name || null,
      inputs: inputs || {},
      input_file_ids: inputFileIds || [],
      created_by: createdBy || "web_user",
    },
  });

export const listTasks = ({ status, agentId, limit, offset } = {}) => {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (agentId) params.set("agent_id", agentId);
  if (limit != null) params.set("limit", String(limit));
  if (offset != null) params.set("offset", String(offset));
  const qs = params.toString();
  return request(`/api/tasks${qs ? `?${qs}` : ""}`);
};

export const getTask = (taskId) => request(`/api/tasks/${taskId}`);
// limit 对齐后端上限 5000（复核发现：合法上限内的大批量任务 ~4200 条事件，
// 若截在 2000，队尾的 summary_generated 会被切掉，TaskDetail 的批量计数标签
// 恰在最需要它的场景静默消失）。parser 行数上限 1000 → 事件量有界 <5000。
export const listTaskEvents = (taskId) => request(`/api/tasks/${taskId}/events?limit=5000`);
export const cancelTask = (taskId) =>
  request(`/api/tasks/${taskId}/cancel`, { method: "POST" });

// 人工放行（P1-B）：reviewer 必须具名——空白签名后端 422，前端表单同样强制。
export const reviewTask = (taskId, { action, reviewer, comment }) =>
  request(`/api/tasks/${taskId}/review`, {
    method: "POST",
    json: { action, reviewer, comment: comment || null },
  });
