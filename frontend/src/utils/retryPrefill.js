// 失败任务不再复制进字段表单。工程师回到原始对话，用文字或附件说明失败现象；
// 系统基于会话上下文重新路由。retry_of 是系统审计血缘，不是用户要填写的参数；
// 保留它供 Guide 下一次自动编排写回新任务。没有会话血缘的历史任务回到新对话。
// 本函数只构造导航目标，不写本地草案、不偷带 Agent/参数，也绝不自动重跑。
export function buildRetryRoute(task) {
  const conversationId =
    typeof task?.conversation_id === "string" ? task.conversation_id.trim() : "";
  const retryOf = typeof task?.id === "string" ? task.id.trim() : "";
  const query = {};
  if (conversationId) query.c = conversationId;
  if (retryOf) query.retry_of = retryOf;
  return Object.keys(query).length ? { path: "/", query } : { path: "/" };
}
