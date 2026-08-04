// 任务分组谓词 SSOT（#30 今日页与任务台合并）：今日页三分组与任务台左栏
// 分组共用同一份判据，搬家不改语义（实现原样出自 TodayPage.vue 批B 版本）。
// 注意：StatusCenter「运行中」是另一口径（含 waiting_upstream 接力派生态），
// 刻意不合流——那里是协作接力视角，这里是任务状态机视角。
import { TERMINAL_STATUSES } from "../stores/liveFeedCore.js";

// 待你签发：等待人工审核（amber 行动召唤语义唯一载体）。
export function isWaitingReview(t) {
  return t.status === "waiting_review";
}

// 进行中：创建后、落地前的工作态四态。
export function isWorking(t) {
  return ["created", "queued", "running", "validating"].includes(t.status);
}

// 今日交付：终态且 finished_at 落在本地今日（dayStartMs=本地零点 epoch ms，
// 由调用方用同一日界算式提供，页面内多处共享不各自重算）。
export function isDeliveredToday(t, dayStartMs) {
  return TERMINAL_STATUSES.includes(t.status) && t.finished_at && Date.parse(t.finished_at) >= dayStartMs;
}
