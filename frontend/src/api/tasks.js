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

export const listTasks = ({ status, agentId } = {}) => {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (agentId) params.set("agent_id", agentId);
  const qs = params.toString();
  return request(`/api/tasks${qs ? `?${qs}` : ""}`);
};

export const getTask = (taskId) => request(`/api/tasks/${taskId}`);
export const listTaskEvents = (taskId) => request(`/api/tasks/${taskId}/events`);
export const cancelTask = (taskId) =>
  request(`/api/tasks/${taskId}/cancel`, { method: "POST" });

// 人工放行（P1-B）：reviewer 必须具名——空白签名后端 422，前端表单同样强制。
export const reviewTask = (taskId, { action, reviewer, comment }) =>
  request(`/api/tasks/${taskId}/review`, {
    method: "POST",
    json: { action, reviewer, comment: comment || null },
  });
