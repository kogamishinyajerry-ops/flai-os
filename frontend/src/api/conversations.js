import { request } from "./client.js";

// 导引会话（M6，ADR-0012）。会话由 ConversationService 驱动，与一次性 tasks 正交。
// created_by 服务端从登录会话派生（ADR-0019 D5），前端不再发送。
export const createConversation = ({ agentId }) =>
  request("/api/conversations", {
    method: "POST",
    json: { agent_id: agentId },
  });

export const getConversation = (conversationId) =>
  request(`/api/conversations/${conversationId}`, { cache: "no-store" });

// 会话列表（M8 协作工作台首页用来罗列协作会话）。
export const listConversations = ({ createdBy, limit, offset } = {}) => {
  const params = new URLSearchParams();
  if (createdBy) params.set("created_by", createdBy);
  if (limit != null) params.set("limit", String(limit));
  if (offset != null) params.set("offset", String(offset));
  const qs = params.toString();
  return request(`/api/conversations${qs ? `?${qs}` : ""}`);
};

// 单轮对话推进：返回 { message: assistant 回复(含可能的 recommendation), conversation }
// fileIds（M7）：已上传附件 id 列表（≤5，先经 /api/files/upload），内容渲染由内核做。
export const postMessage = (conversationId, content, fileIds = []) =>
  request(`/api/conversations/${conversationId}/messages`, {
    method: "POST",
    json: { content, file_ids: fileIds },
    // 慢操作显式超时（批次五 C1）：内网 LLM 推理「一两分钟」是在案诚实口径
    // （GuidePage 30s 提示语），180s=口径+余量后硬止血，失败走既有回滚+还稿路。
    timeoutMs: 180_000,
  });

// P2.3 结构化澄清的唯一写入口。它与任务评审完全正交：客户端只提交冻结问题
// 的 revision、稳定 submission_id 与回答 payload；署名由服务端登录身份派生。
// submission_id 在不确定失败后保持不变，让服务端可以如实返回幂等重放结果。
export const answerQuestion = (conversationId, questionId, body) =>
  request(`/api/conversations/${conversationId}/questions/${questionId}/answer`, {
    method: "POST",
    json: body,
    // 回答会继续触发一次模型推理，沿用普通消息的内网慢操作上限。
    timeoutMs: 180_000,
  });

// 结束会话（active→concluded）：「确认草案去创建任务」时归档会话（ADR-0013）。
export const concludeConversation = (conversationId) =>
  request(`/api/conversations/${conversationId}/conclude`, { method: "POST" });

// 协作会话成员任务（M8/ADR-0016）：一次会话分流出的 N 个人签发任务，协作工作台
// 据此聚合展示。仅读——任务仍由人在创建页亲手签发。
export const listConversationTasks = (conversationId) =>
  request(`/api/conversations/${conversationId}/tasks`, { cache: "no-store" });
