import { request } from "./client";

// created_by 服务端从登录会话派生（ADR-0019 D5），前端不再发送任何身份文本。
export const createTask = ({ agentId, name, inputs, inputFileIds, conversationId }) =>
  request("/api/tasks", {
    method: "POST",
    json: {
      agent_id: agentId,
      name: name || null,
      inputs: inputs || {},
      input_file_ids: inputFileIds || [],
      // M8：由导引协作会话产出的任务带上会话 id，归到协作工作台的同一次会话下。
      conversation_id: conversationId || null,
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
// offset 起点（Codex R1-P2）：详情页 2s 轮询若每次从 0 全量重翻，事件越多轮询
// 越重；事件表 append-only 且按 id ASC 排序，偏移稳定——轮询方传入已持有的
// 条数，只拉自己没有的尾段。
export const listTaskEvents = async (taskId, { offset = 0 } = {}) => {
  const pageSize = 2000;
  const all = [];
  for (let cursor = offset; ; cursor += pageSize) {
    const page = await request(`/api/tasks/${taskId}/events?limit=${pageSize}&offset=${cursor}`);
    all.push(...page);
    if (page.length < pageSize) return all;
  }
};
export const cancelTask = (taskId) =>
  request(`/api/tasks/${taskId}/cancel`, { method: "POST" });

// 人工放行（P1-B）。签发者=登录会话身份，服务端派生（ADR-0019 D5），前端不发。
export const reviewTask = (taskId, { action, comment }) =>
  request(`/api/tasks/${taskId}/review`, {
    method: "POST",
    json: { action, comment: comment || null },
  });

// 工具调用明细（只读端点，工作态氛围展示用）。
export const listToolRuns = (taskId) => request(`/api/tasks/${taskId}/tool_runs`);

// 模型调用留痕（只读端点，消耗诚实披露用；字段=model_profile/model_name/status/
// token_usage，token_usage 上游未回报时为 null，绝不补 0）。
export const listModelCalls = (taskId) => request(`/api/tasks/${taskId}/model_calls`);

// 产物文件只读元数据投影（批B P1 修复，字段=id/filename/size_bytes/data_classification，
// 绝不含 path/内容）——DeliveryCard 产物条用它取代逐个 fetchOutputFile 全量拉 blob。
export const listOutputFiles = (taskId) => request(`/api/tasks/${taskId}/output_files`);
