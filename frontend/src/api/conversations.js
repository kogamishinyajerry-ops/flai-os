import { ApiError, request, streamRequest } from "./client.js";

// 导引会话（M6，ADR-0012）。会话由 ConversationService 驱动，与一次性 tasks 正交。
// created_by 服务端从登录会话派生（ADR-0019 D5），前端不再发送。
export const createConversation = ({ agentId }) =>
  request("/api/conversations", {
    method: "POST",
    json: { agent_id: agentId },
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

// 真流式单轮推进：服务端按 NDJSON 发 start/delta/done/error。delta 是上游模型
// 的真实增量，不在前端把整包响应拆字；只有 done 携带的 canonical message
// 才代表后端原子落库成功。
export async function postMessageStream(
  conversationId,
  content,
  fileIds = [],
  // signal（流式停止钮）：调用方的 AbortSignal 透传到 fetch 层，abort 即真实
  // 断连——后端走既有断连零落库路径；主动停止与超时/断网的区分由调用方负责。
  { onStart, onDelta, signal } = {},
) {
  let completed = null;

  try {
    await streamRequest(`/api/conversations/${conversationId}/messages/stream`, {
      method: "POST",
      json: { content, file_ids: fileIds },
      timeoutMs: 180_000,
      signal,
      onEvent(event) {
        if (event.type === "start") {
          if (typeof onStart === "function") onStart(event);
          return;
        }
        if (event.type === "delta") {
          if (typeof event.text !== "string") {
            throw new ApiError(
              0,
              "流式 delta 缺少文本——保存状态未知，请刷新会话核对",
            );
          }
          if (event.text && typeof onDelta === "function") onDelta(event.text, event);
          return;
        }
        if (event.type === "done") {
          if (!event.message || !event.conversation) {
            throw new ApiError(
              0,
              "流式完成事件不完整——保存状态未知，请刷新会话核对",
            );
          }
          completed = {
            message: event.message,
            conversation: event.conversation,
          };
          return;
        }
        if (event.type === "error") {
          const detail =
            typeof event.detail === "string"
              ? event.detail
              : JSON.stringify(event.detail || "流式响应失败");
          throw new ApiError(event.status || 0, detail, {
            retryable: event.retryable,
            persisted: event.persisted,
          });
        }
        throw new ApiError(0, `未知流式事件：${event.type}`, {
          retryable: false,
        });
      },
    });
  } catch (err) {
    // canonical done 已抵达即表示服务端原子落库完成；其后的连接收尾失败不能把
    // 已保存的一轮反报成「未保存」。
    if (completed) return completed;
    throw err;
  }

  if (!completed) {
    throw new ApiError(
      0,
      "流式响应提前结束——保存状态未知，请刷新会话核对",
    );
  }
  return completed;
}

// 结束会话（active→concluded）：「确认草案去创建任务」时归档会话（ADR-0013）。
export const concludeConversation = (conversationId) =>
  request(`/api/conversations/${conversationId}/conclude`, { method: "POST" });

// 协作会话成员任务（M8/ADR-0016）：一次会话分流出的 N 个人签发任务，协作工作台
// 据此聚合展示。仅读——任务仍由人在创建页亲手签发。
export const listConversationTasks = (conversationId) =>
  request(`/api/conversations/${conversationId}/tasks`);
