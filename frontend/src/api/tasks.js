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
// limit 显式传 2000（=后端默认值，行为不变）：分页口径显式化，超长时间轴
// 的截断点在前端代码里可见，而不是隐在后端默认里。
export const listTaskEvents = (taskId) => request(`/api/tasks/${taskId}/events?limit=2000`);
export const cancelTask = (taskId) =>
  request(`/api/tasks/${taskId}/cancel`, { method: "POST" });

// 人工放行（P1-B）：reviewer 必须具名——空白签名后端 422，前端表单同样强制。
export const reviewTask = (taskId, { action, reviewer, comment }) =>
  request(`/api/tasks/${taskId}/review`, {
    method: "POST",
    json: { action, reviewer, comment: comment || null },
  });
