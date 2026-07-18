// 编队聚合纯函数（批七 §1.4）：GuidePage `.sa-squad-line` 与 WorkbenchSession
// hero 句共用一份口径。一切计数都是任务快照的忠实投影——不虚构进度、不预测。
//
// waiting_upstream 是**纯前端派生态**（§1.1）：status=created 且 depends_on 非空
// =「等待接力」。任务 status 是唯一真值；事件（dependency_resolved）只做旁白，
// 灯与分组的翻转只认 status。
import { TASK_WORK_STATES, taskElapsedMs } from "./format";

const TERMINAL = new Set(["completed", "failed", "cancelled"]);

export function memberPhase(t) {
  if (!t) return null;
  if (t.status === "created" && (t.depends_on || []).length > 0) return "waiting_upstream";
  return t.status;
}

export function squadCounts(tasks) {
  const c = {
    total: tasks.length,
    // 「N 位专家」计人不计任务（Codex R0 P1 配套）：同 Agent 多任务时任务数
    // 会虚增专家数；无 agent_id 的降级快照按任务数如实回退。
    experts: tasks.every((t) => t.agent_id)
      ? new Set(tasks.map((t) => t.agent_id)).size
      : tasks.length,
    running: 0, // 真工作态（running/validating/parsing/analyzing）
    queued: 0,
    waitingUpstream: 0,
    waitingReview: 0,
    completed: 0,
    failed: 0,
    cancelled: 0,
  };
  for (const t of tasks) {
    const phase = memberPhase(t);
    if (TASK_WORK_STATES.has(phase)) c.running += 1;
    else if (phase === "queued" || phase === "created") c.queued += 1;
    else if (phase === "waiting_upstream") c.waitingUpstream += 1;
    else if (phase === "waiting_review") c.waitingReview += 1;
    else if (phase === "completed") c.completed += 1;
    else if (phase === "failed") c.failed += 1;
    else if (phase === "cancelled") c.cancelled += 1;
  }
  c.settled = tasks.length > 0 && tasks.every((t) => TERMINAL.has(t.status));
  return c;
}

// 收束态假绿禁令（§1.4，O7 tamper 探针在场）：只要有待签发或非终态成员，
// 绝不出现「完成」类总结措辞；全终态且零待签才「协作已收束」。
// segments 带 tone（neutral/clay/amber/rose）：待你签发段必须 amber 上屏
// （信任色锁：amber=待人签唯一语义），失败段玫红（真失败才红）。
export function squadSegments(counts, tasks, now) {
  if (counts.settled === true && counts.waitingReview === 0) {
    let maxMs = 0;
    for (const t of tasks) {
      const ms = taskElapsedMs(t, now);
      if (ms !== null && ms > maxMs) maxMs = ms;
    }
    const dur = formatDur(maxMs);
    const segs = [{ text: dur ? `协作已收束 · 用时 ${dur}` : "协作已收束", tone: "neutral" }];
    if (counts.failed > 0) segs.push({ text: `${counts.failed} 失败`, tone: "rose" });
    return segs;
  }
  const segs = [{ text: `${counts.experts ?? counts.total} 位专家协作`, tone: "neutral" }];
  if (counts.running > 0) segs.push({ text: `${counts.running} 运行中`, tone: "clay" });
  if (counts.queued > 0) segs.push({ text: `${counts.queued} 已入队`, tone: "neutral" });
  if (counts.waitingUpstream > 0) segs.push({ text: `${counts.waitingUpstream} 等待接力`, tone: "neutral" });
  if (counts.waitingReview > 0) segs.push({ text: `${counts.waitingReview} 待你签发`, tone: "amber" });
  if (counts.completed > 0) segs.push({ text: `${counts.completed} 已完成`, tone: "neutral" });
  if (counts.failed > 0) segs.push({ text: `${counts.failed} 失败`, tone: "rose" });
  if (counts.cancelled > 0) segs.push({ text: `${counts.cancelled} 已取消`, tone: "neutral" });
  return segs;
}

export function squadLineText(counts, tasks, now) {
  return squadSegments(counts, tasks, now).map((s) => s.text).join(" · ");
}

function formatDur(ms) {
  const sec = Math.max(0, Math.round(ms / 1000));
  if (sec <= 0) return "";
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m ${String(sec % 60).padStart(2, "0")}s`;
}

// 接力顺序一句话（§1.5）：depends_on 拓扑序（Kahn），同层保持任务原序；
// 环理论上不存在（batch 按构造 DAG），防御性兜底：残余项按原序附尾，绝不死循环。
export function relayOrderText(tasks, nameOf) {
  const withDeps = tasks.filter((t) => (t.depends_on || []).length > 0);
  if (withDeps.length === 0) return "";
  const ids = new Set(tasks.map((t) => t.id));
  const indeg = new Map(tasks.map((t) => [t.id, (t.depends_on || []).filter((d) => ids.has(d)).length]));
  const order = [];
  let frontier = tasks.filter((t) => indeg.get(t.id) === 0);
  const done = new Set();
  while (frontier.length > 0) {
    for (const t of frontier) {
      order.push(t);
      done.add(t.id);
    }
    frontier = tasks.filter(
      (t) => !done.has(t.id) && (t.depends_on || []).every((d) => !ids.has(d) || done.has(d))
    );
  }
  for (const t of tasks) if (!done.has(t.id)) order.push(t);
  return order.map((t) => nameOf(t)).join(" → ");
}
