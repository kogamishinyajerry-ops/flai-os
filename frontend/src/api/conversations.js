import { request } from "./client.js";
import { validateConversationListProjection } from "../utils/conversationRuntimeCore.js";

const TITLE_CONTROL = /[\u0000-\u001f\u007f-\u009f]/;

function lifecycleRevisionBody(lifecycleRevision) {
  if (!Number.isInteger(lifecycleRevision) || lifecycleRevision < 0) {
    throw new TypeError("conversation lifecycle revision must be a non-negative integer");
  }
  return { lifecycle_revision: lifecycleRevision };
}

function canonicalConversationTitle(title) {
  if (
    typeof title !== "string"
    || title.length < 1
    || title.length > 60
    || title !== title.trim()
    || TITLE_CONTROL.test(title)
  ) {
    throw new TypeError("conversation title must be canonical text between 1 and 60 characters");
  }
  return title;
}

// 导引会话（M6，ADR-0012）。会话由 ConversationService 驱动，与一次性 tasks 正交。
// created_by 服务端从登录会话派生（ADR-0019 D5），前端不再发送。
export const createConversation = ({ agentId }) =>
  request("/api/conversations", {
    method: "POST",
    json: { agent_id: agentId },
  });

export const getConversation = (conversationId) =>
  request(`/api/conversations/${conversationId}`, { cache: "no-store" });

// 会话列表：可见与已归档是正交投影，调用方必须按 visibility 明确取权威清单。
export const listConversations = ({ visibility = "visible", createdBy, limit, offset } = {}) => {
  if (visibility !== "visible" && visibility !== "archived") {
    throw new TypeError("conversation visibility must be visible or archived");
  }
  const params = new URLSearchParams();
  params.set("visibility", visibility);
  if (createdBy) params.set("created_by", createdBy);
  if (limit != null) params.set("limit", String(limit));
  if (offset != null) params.set("offset", String(offset));
  const qs = params.toString();
  return request(`/api/conversations${qs ? `?${qs}` : ""}`, { cache: "no-store" })
    .then(validateConversationListProjection);
};

// 会话标题只有人可改；revision 是客户端刚读取的 CAS 投影，冲突由调用面刷新后明示。
export const renameConversation = (conversationId, { lifecycleRevision, title }) => {
  const json = {
    ...lifecycleRevisionBody(lifecycleRevision),
    title: canonicalConversationTitle(title),
  };
  return request(`/api/conversations/${conversationId}/title`, {
    method: "PATCH",
    json,
  });
};

// 归档只改变可见性，不结束会话；该动作不可逆。
export const archiveConversation = (conversationId, { lifecycleRevision }) =>
  request(`/api/conversations/${conversationId}/archive`, {
    method: "POST",
    json: lifecycleRevisionBody(lifecycleRevision),
  });

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

// 结束会话只改变 active→concluded；与归档可见性正交。
export const concludeConversation = (conversationId, { lifecycleRevision }) =>
  request(`/api/conversations/${conversationId}/conclude`, {
    method: "POST",
    json: lifecycleRevisionBody(lifecycleRevision),
  });

// 协作会话成员任务（M8/ADR-0016）：一次会话分流出的 N 个人签发任务，协作工作台
// 据此聚合展示。仅读——任务仍由人在创建页亲手签发。
export const listConversationTasks = (conversationId) =>
  request(`/api/conversations/${conversationId}/tasks`, { cache: "no-store" });

// Agent 事实投影：这是会话成员任务的完整只读快照，不是增量事件流。
// FLAi 任务依赖与人签来自本机治理账本；JerryAgent 只补充经过后端收窄、
// 去自由文本的 runtime/subagent 事实。调用方不得直接访问 sidecar。
export const getConversationAgentFacts = (conversationId) =>
  request(`/api/conversations/${conversationId}/agent-facts`, { cache: "no-store" });
