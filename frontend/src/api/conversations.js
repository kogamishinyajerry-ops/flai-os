import { request } from "./client";

// 导引会话（M6，ADR-0012）。会话由 ConversationService 驱动，与一次性 tasks 正交。
export const createConversation = ({ agentId, createdBy }) =>
  request("/api/conversations", {
    method: "POST",
    json: { agent_id: agentId, created_by: createdBy || "web_user" },
  });

export const getConversation = (conversationId) =>
  request(`/api/conversations/${conversationId}`);

// 单轮对话推进：返回 { message: assistant 回复(含可能的 recommendation), conversation }
export const postMessage = (conversationId, content) =>
  request(`/api/conversations/${conversationId}/messages`, {
    method: "POST",
    json: { content },
  });

// 结束会话（active→concluded）：「确认草案去创建任务」时归档会话（ADR-0013）。
export const concludeConversation = (conversationId) =>
  request(`/api/conversations/${conversationId}/conclude`, { method: "POST" });
