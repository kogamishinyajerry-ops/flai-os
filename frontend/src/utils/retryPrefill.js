// N4a 复制为新任务（评审 N4a / 迁移 #12 retry_of）：失败任务 → 创建页预填。
// 只组装 flai_prefill 草案与路由目标，不做任何提交——预填仍需人工核对补全，
// 亲手点「提交任务」才创建（ADR-0012 同款接缝），平台绝不自动重跑。
// 输入文件复用原任务已上传的真实 fileId（File Service 行独立于任务，guide
// 附件带入同款模式）；文件名投影里没有，用如实占位名，创建页可移除。
export function buildRetryRoute(task) {
  sessionStorage.setItem(
    "flai_prefill",
    JSON.stringify({
      agent_id: task.agent_id,
      name: task.name ? `重跑 · ${task.name}` : null,
      inputs: task.inputs || {},
      files: (task.input_file_ids || []).map((id, i) => ({
        id,
        name: `原任务输入文件 ${i + 1}`,
      })),
      conversation_id: null,
      conclude_after: false,
      retry_of: task.id,
    })
  );
  return { path: "/tasks/new", query: { agent_id: task.agent_id, from: "retry" } };
}
