// N4a 复制为新任务（评审 N4a / 迁移 #12 retry_of）：失败任务 → 创建页预填。
// 只组装 flai_prefill 草案与路由目标，不做任何提交——预填仍需人工核对补全，
// 亲手点「提交任务」才创建（ADR-0012 同款接缝），平台绝不自动重跑。
//
// 【不携带输入文件——Codex 治理审 R0 P1】任务投影的 input_file_ids 是裸 id 列表，
// 前端**无法分辨 kind**：直接提交的上传件是 kind=input，而依赖任务经 resolver 注入
// 的上游产物是 kind=output。后端 create_task 只收 kind=input（output 一律 422），
// 若把两者都当「已上传」绿标带入，kind=output 的重试稳定 422=假绿且重试失效
// （违反假绿死罪 + 信任色锁绿仅 REAL）。故一律不携带文件，只带回原始输入参数；
// 原任务若有附件，由横幅如实告知「需重新添加」，让人自己重传（重传即拿到干净的
// kind=input）。had_file_count 仅供横幅文案，不承载任何「已上传」语义。
export function buildRetryRoute(task) {
  const hadFileCount = Array.isArray(task.input_file_ids) ? task.input_file_ids.length : 0;
  sessionStorage.setItem(
    "flai_prefill",
    JSON.stringify({
      agent_id: task.agent_id,
      name: task.name ? `重跑 · ${task.name}` : null,
      inputs: task.inputs || {},
      files: [], // 见上：绝不带入无法验证 kind 的文件
      had_file_count: hadFileCount,
      conversation_id: null,
      conclude_after: false,
      retry_of: task.id,
    })
  );
  return { path: "/tasks/new", query: { agent_id: task.agent_id, from: "retry" } };
}
