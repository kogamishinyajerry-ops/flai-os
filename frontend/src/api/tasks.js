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
// 分页拉取到取尽（ADR-0013 审计修复）：此前单页 5000 封顶，但 parser 契约上限
// max_rows=5000 时批量任务可产 ~2 万事件——尾部的 summary_generated/task_completed
// 恰在最需要它的场景被静默截断。页大小 2000 对齐后端默认；短尾页即终止。
export const listTaskEvents = async (taskId) => {
  const pageSize = 2000;
  const all = [];
  for (let offset = 0; ; offset += pageSize) {
    const page = await request(`/api/tasks/${taskId}/events?limit=${pageSize}&offset=${offset}`);
    all.push(...page);
    if (page.length < pageSize) return all;
  }
};
export const cancelTask = (taskId) =>
  request(`/api/tasks/${taskId}/cancel`, { method: "POST" });

// 人工放行（P1-B）：reviewer 必须具名——空白签名后端 422，前端表单同样强制。
export const reviewTask = (taskId, { action, reviewer, comment }) =>
  request(`/api/tasks/${taskId}/review`, {
    method: "POST",
    json: { action, reviewer, comment: comment || null },
  });
