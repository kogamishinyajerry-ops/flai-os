import { request } from "./client";

// 导引会话（M6，ADR-0012）。会话由 ConversationService 驱动，与一次性 tasks 正交。
// created_by 服务端从登录会话派生（ADR-0019 D5），前端不再发送。
export const createConversation = ({ agentId, requestId = null, expectedPrincipal = null }) =>
  request("/api/conversations", {
    method: "POST",
    json: {
      agent_id: agentId,
      ...(requestId ? { request_id: requestId } : {}),
      ...(expectedPrincipal ? { expected_principal: expectedPrincipal } : {}),
    },
  });

export const getConversation = (conversationId) =>
  request(`/api/conversations/${conversationId}`);

// 会话列表（M8 协作工作台首页用来罗列协作会话）。
export const listConversations = ({ createdBy, limit, offset } = {}) => {
  const params = new URLSearchParams();
  if (createdBy) params.set("created_by", createdBy);
  if (limit != null) params.set("limit", String(limit));
  if (offset != null) params.set("offset", String(offset));
  const qs = params.toString();
  return request(`/api/conversations${qs ? `?${qs}` : ""}`);
};

// 单轮对话推进：GuidePage 默认显式请求 safe_auto；requestId 是稳定幂等键，
// 网络丢响应后重试不会重复调用模型或创建任务。其它调用方可保留 plan_only。
// fileIds（M7）：已上传附件 id 列表（≤5，先经 /api/files/upload），内容渲染由内核做。
export const postMessage = (
  conversationId,
  content,
  fileIds = [],
  { executionMode = "plan_only", requestId = null, expectedPrincipal = null } = {}
) =>
  request(`/api/conversations/${conversationId}/messages`, {
    method: "POST",
    json: {
      content,
      file_ids: fileIds,
      execution_mode: executionMode,
      ...(requestId ? { request_id: requestId } : {}),
      ...(expectedPrincipal ? { expected_principal: expectedPrincipal } : {}),
    },
  });

// 结束会话（active→concluded）：「确认草案去创建任务」时归档会话（ADR-0013）。
export const concludeConversation = (conversationId) =>
  request(`/api/conversations/${conversationId}/conclude`, { method: "POST" });

// 协作会话成员任务：包含人工创建与 safe_auto 后端物化的真实任务。仅读；
// waiting_review 的最终签发仍只能由真人完成。
export const listConversationTasks = (conversationId) =>
  request(`/api/conversations/${conversationId}/tasks`);
