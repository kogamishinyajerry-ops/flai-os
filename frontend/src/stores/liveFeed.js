// frontend/src/stores/liveFeed.js —— 全站唯一 HTTP 轮询源（spec 批A §二）。
// channel 单例池：同 key 复用,引用计数归零停链。轮询纪律五不变式承袭
// taskFeed.js（链式 setTimeout/hidden 跳过仍续轮/inflight 去重/失败保旧值/
// refCount 停链）。防 stale 统一为 epoch 守卫（liveFeedCore.makeEpochGuard,
// ADR-0013 整包作废语义推广）。tasks channel 每次落地 diffTransitions 广播
// task-transition——微反馈/翻转唤醒/后续批全吃这一个总线。
import { ref } from "vue";
import { listTasks, getTaskLiveSnapshot, listModelCalls } from "../api/tasks.js";
import { getConversation, listConversationTasks } from "../api/conversations.js";
import { fetchAllReviewInbox } from "../api/me.js";
import { diffTransitions, nextInterval, makeEpochGuard, shouldRefreshOnJoin } from "./liveFeedCore.js";
import {
  acknowledgeFullSnapshot,
  evaluateTaskLiveSnapshot,
  initialResyncClock,
  isSnapshotRequestCurrent,
  nextLiveConnection,
  planTaskSnapshotRequest,
  requestFullSnapshot,
} from "./liveSnapshotCore.js";

const channels = new Map(); // key → channel
const transitionSubs = new Set();

export function onTransition(fn) {
  transitionSubs.add(fn);
  return () => transitionSubs.delete(fn);
}

function emitTransitions(evs) {
  for (const ev of evs) {
    for (const fn of transitionSubs) {
      try { fn(ev); } catch { /* 订阅者异常不拖垮轮询链 */ }
    }
  }
}

function syncState() {
  return {
    connection: ref("idle"),
    lastSuccessAt: ref(null),
    stale: ref(true),
    resyncing: ref(false),
    syncError: ref(""),
  };
}

function applyConnection(state, event) {
  const next = nextLiveConnection(
    {
      connection: state.connection.value,
      lastSuccessAt: state.lastSuccessAt.value,
      stale: state.stale.value,
      resyncing: state.resyncing.value,
      error: state.syncError.value,
    },
    event,
  );
  state.connection.value = next.connection;
  state.lastSuccessAt.value = next.lastSuccessAt;
  state.stale.value = next.stale;
  state.resyncing.value = next.resyncing;
  state.syncError.value = next.error;
}

// —— 三类 channel 的 fetch 策略（state 形状见各 build*） ——

function buildTasksChannel(ch) {
  ch.state = { tasks: ref([]), loaded: ref(false), error: ref(""), ...syncState() };
  ch.intervalOf = () => 5000;
  ch.suppressTransitionsOnce = false;
  ch.onFetchFailure = () => { ch.suppressTransitionsOnce = true; };
  ch.fetch = async (fresh) => {
    const next = await listTasks({ limit: 100 });
    if (!fresh()) return; // 落地前复查：响应回来时若已换代（release 重建）,整包作废
    // 水合抑制（Task 12 修复 3）：loaded 仍 false 说明这是本 channel 冷启动首拉,
    // prevById 为空会让 diffTransitions 把每个任务都判成 from:null 的「迁移」——
    // 那不是真事件,是快照的初次显影,不广播不带外补拉（上百任务的冷启动不该
    // 打一发事件雨）。首拉之后（loaded 已真）的 from:null 才是轮询窗口间新出现
    // 的任务,是真事件。
    const hydrating = ch.state.loaded.value !== true;
    // 暖断连后的首个成功是权威快照调和，不是用户亲历的连续迁移；禁止补播
    // completion seal/toast。正常连续轮询才广播 transition。
    const reconciling = ch.suppressTransitionsOnce === true;
    const evs = (hydrating || reconciling) ? [] : diffTransitions(ch.state.tasks.value, next);
    ch.state.tasks.value = next;
    ch.suppressTransitionsOnce = false;
    if (evs.length) {
      emitTransitions(evs);
      // 翻转唤醒：清单先看到状态变化时,带外补拉对应详情 channel（免等其下一 tick）
      for (const ev of evs) pokeTask(ev.id);
    }
  };
}

function buildReviewInboxChannel(ch) {
  ch.state = { tasks: ref([]), loaded: ref(false), error: ref(""), ...syncState() };
  ch.intervalOf = () => 5000;
  ch.fetch = async (fresh) => {
    const next = await fetchAllReviewInbox();
    if (!fresh()) return;
    ch.state.tasks.value = next;
  };
}

function buildTaskChannel(ch, taskId) {
  ch.state = {
    task: ref(null),
    events: ref([]),
    modelCalls: ref([]),
    modelCallsError: ref(""),
    loaded: ref(false),
    error: ref(""),
    ...syncState(),
  };
  // 动态频率：活跃 2s / waiting_review 8s / 终态 30s 低频核对。终态不能停轮，
  // 否则页面会永久声称 connected，且完成后的反馈/审计事件永远不到达。
  ch.intervalOf = () => {
    if (ch.state.connection.value === "disconnected") return 5000;
    return nextInterval(ch.state.task.value?.status || "running") ?? 30000;
  };
  ch.cursor = { sequence: 0, eventId: null };
  ch.eventIds = new Set();
  ch.resyncClock = initialResyncClock();
  ch.onFetchFailure = () => {
    ch.resyncClock = requestFullSnapshot(ch.resyncClock);
  };
  // modelCalls 请求序号（Task 12 修复 1，恢复 main 的 modelCallsSeq 语义）：挂在 channel
  // 上而非组件内——channel 按 key 池化跨组件复用,序号必须与 channel 同寿命。
  ch.modelCallsSeq = 0;
  // detail 集合 opt-in（Codex R2-P1）：modelCalls 是详情层（速览/详情页）才消费的
  // 重集合,轻订阅者（对话轴/工作台的实时行,只要 task+events 尾巴）不该为它买单。
  // 订阅计数为 0 时 fetch 跳过 listModelCalls；首个 detail 订阅者 join 时补拉一次。
  ch.modelCallsRefs = 0;
  ch.fetch = async (fresh) => {
    let requestPlan = planTaskSnapshotRequest(ch.resyncClock, ch.cursor);
    let base = requestPlan.base;
    let payload = await getTaskLiveSnapshot(taskId, {
      afterSequence: base.sequence,
      anchorEventId: base.eventId,
    });
    if (!fresh()) return;
    let evaluated = evaluateTaskLiveSnapshot({
      ...base,
      taskId,
      eventIds: requestPlan.full ? [] : ch.eventIds,
    }, payload);
    if (evaluated.action === "resnapshot") {
      // Strict gap recovery: stop applying the suspect delta, mark the old
      // projection stale, then replace it from sequence zero.
      applyConnection(ch.state, { type: "resync", error: evaluated.reason });
      ch.resyncClock = requestFullSnapshot(ch.resyncClock);
      requestPlan = planTaskSnapshotRequest(ch.resyncClock, ch.cursor);
      base = requestPlan.base;
      payload = await getTaskLiveSnapshot(taskId, { afterSequence: 0, anchorEventId: null });
      if (!fresh()) return;
      evaluated = evaluateTaskLiveSnapshot({ ...base, taskId, eventIds: [] }, payload);
      if (evaluated.action === "resnapshot") {
        throw new Error(`完整任务快照校验失败：${evaluated.reason}`);
      }
    }
    if (!fresh()) return; // task/events 到账时若已换代,不得写入新世代 state
    // resyncClock 是 task channel 内部的内容世代。请求在途期间只要有人再次要求
    // full（断连、手动重试或 gap），旧世代响应即使 HTTP 成功也不再具有落盘资格。
    if (!isSnapshotRequestCurrent(ch.resyncClock, requestPlan.generation)) {
      return { connectionConfirmed: false };
    }
    const prev = ch.state.task.value;
    ch.state.task.value = evaluated.task;
    ch.state.events.value = evaluated.action === "replace"
      ? evaluated.events
      : ch.state.events.value.concat(evaluated.events);
    ch.cursor = evaluated.cursor;
    if (evaluated.action === "replace") {
      ch.eventIds = new Set(evaluated.events.map((event) => event.event_id));
      ch.resyncClock = acknowledgeFullSnapshot(ch.resyncClock, requestPlan.generation);
    } else {
      for (const event of evaluated.events) ch.eventIds.add(event.event_id);
    }
    // 只有经 exact cursor 验证的连续 delta 才是“本次在线亲历迁移”。sequence-0
    // replace（冷水合/断连调和）绝不补播完成动画或提醒。
    if (evaluated.action === "append" && evaluated.events.length && prev && prev.status !== evaluated.task.status) {
      emitTransitions([{ id: taskId, from: prev.status, to: evaluated.task.status, task: evaluated.task }]);
    }
    // modelCalls 解耦主链（Task 12 修复 4）：task+events 已落地,不因它拖慢/拖挂主快照；
    // 并行独立发,同样受 fresh() 守卫。序号守卫（修复 1）：手动刷新可与在途轮询重叠,
    // 只让「最新一次发起」的结果落盘,迟到的旧响应（含旧错误）整包作废。错误诚实化
    // （修复 2）：main 原语义是失败时展示 modelCallsError,换轨时被静默吞掉误报「无
    // 模型调用」,此处恢复。
    if (ch.modelCallsRefs === 0) {
      return { connectionConfirmed: ch.resyncClock.applied >= ch.resyncClock.requested };
    }
    const seq = ++ch.modelCallsSeq;
    listModelCalls(taskId)
      .then((modelCalls) => {
        if (!fresh() || seq !== ch.modelCallsSeq) return;
        ch.state.modelCalls.value = modelCalls;
        ch.state.modelCallsError.value = "";
      })
      .catch((err) => {
        if (!fresh() || seq !== ch.modelCallsSeq) return;
        ch.state.modelCallsError.value = err.detail || err.message || "加载失败";
      });
    return { connectionConfirmed: ch.resyncClock.applied >= ch.resyncClock.requested };
  };
}

function buildConversationChannel(ch, convId) {
  ch.state = {
    conversation: ref(null),
    memberTasks: ref([]),
    loaded: ref(false),
    error: ref(""),
    ...syncState(),
  };
  ch.intervalOf = () => 5000;
  ch.suppressTransitionsOnce = false;
  ch.onFetchFailure = () => { ch.suppressTransitionsOnce = true; };
  ch.fetch = async (fresh) => {
    const [conversation, memberTasks] = await Promise.all([
      getConversation(convId), listConversationTasks(convId),
    ]);
    if (!fresh()) return; // 落地前复查：响应回来时若已换代,整包作废
    // 水合抑制（Task 12 修复 3）：语义同 buildTasksChannel——冷启动首拉不广播/不带外补拉。
    const hydrating = ch.state.loaded.value !== true;
    const reconciling = ch.suppressTransitionsOnce === true;
    const evs = (hydrating || reconciling) ? [] : diffTransitions(ch.state.memberTasks.value, memberTasks);
    ch.state.conversation.value = conversation;
    ch.state.memberTasks.value = memberTasks;
    ch.suppressTransitionsOnce = false;
    if (evs.length) { emitTransitions(evs); for (const ev of evs) pokeTask(ev.id); }
  };
}

function makeChannel(key) {
  const ch = { key, refCount: 0, timer: null, inflight: null, guard: makeEpochGuard() };
  if (key === "tasks") buildTasksChannel(ch);
  else if (key.startsWith("review-inbox:")) buildReviewInboxChannel(ch);
  else if (key.startsWith("task:")) buildTaskChannel(ch, key.slice(5));
  else if (key.startsWith("conversation:")) buildConversationChannel(ch, key.slice(13));
  else throw new Error(`liveFeed: 未知 channel key ${key}`);
  return ch;
}

async function refresh(ch) {
  if (ch.inflight) return ch.inflight;
  const epoch = ch.guard.current();
  const fresh = () => epoch === ch.guard.current(); // 落地复查谓词：响应到账时世代是否仍当代
  ch.inflight = (async () => {
    try {
      const result = await ch.guard.wrap(epoch, () => ch.fetch(fresh))();
      // wrap 语义：epoch 已变（channel 被释放重建/参数变更）→ fetch 整体不执行；
      // fetch 内部另有 fresh() 落地复查,覆盖「起跑时当代但落地时已换代」的窗口。
      if (fresh() && result?.connectionConfirmed !== false) {
        ch.state.loaded.value = true;
        ch.state.error.value = "";
        const now = Date.now();
        ch.lastFetchAt = now; // join 去重新鲜度锚点（shouldRefreshOnJoin）
        applyConnection(ch.state, { type: "success", at: now });
      }
    } catch (err) {
      if (fresh()) {
        const message = err.detail || err.message || "加载失败";
        if (ch.state.loaded.value === false) ch.state.error.value = message;
        // warm failure 保留最后真实快照，但必须显式标 stale/disconnected。
        applyConnection(ch.state, { type: "failure", error: message });
        ch.onFetchFailure?.();
      }
    } finally {
      ch.inflight = null;
    }
  })();
  return ch.inflight;
}

function schedule(ch) {
  clearTimer(ch);
  const ms = ch.intervalOf();
  if (ms === null) return; // 预留无订阅轮询策略；task 终态当前明确走 30s 核对
  ch.timer = setTimeout(async () => {
    try {
      if (!document.hidden) await refresh(ch);
    } finally {
      if (ch.refCount > 0) schedule(ch);
    }
  }, ms);
}

function clearTimer(ch) {
  if (ch.timer) { clearTimeout(ch.timer); ch.timer = null; }
}

export function acquireChannel(key, opts = {}) {
  let ch = channels.get(key);
  if (!ch) { ch = makeChannel(key); channels.set(key, ch); }
  ch.refCount += 1;
  // detail 集合 opt-in（Codex R2-P1）：只有传 { modelCalls: true } 的订阅者（速览/
  // 详情页）计入 modelCallsRefs；轻订阅者共享同一条 task 链但不触发 listModelCalls。
  const wantsModelCalls = opts.modelCalls === true && typeof ch.modelCallsRefs === "number";
  let needModelBackfill = false;
  if (wantsModelCalls) {
    ch.modelCallsRefs += 1;
    // 首个 detail 订阅者加入时 channel 可能已 loaded 且 3s 内刚拉过（join 去重会
    // 跳过补拉）——此时 modelCalls 从未被拉取,必须强制补一轮,否则详情层最长要
    // 等下一 tick 才见到模型调用记录。
    needModelBackfill = ch.modelCallsRefs === 1 && ch.state.loaded.value === true;
  }
  const ensureScheduled = (replace = false) => {
    if (ch.refCount > 0 && (replace || !ch.timer)) schedule(ch);
  };
  // join 去重（liveFeedCore.shouldRefreshOnJoin）：channel 已 loaded 且 3s 内刚
  // 拉过时,join 不再补拉一次——链本身继续跑,排链兜底逻辑原样保留。
  if (shouldRefreshOnJoin(ch.state.loaded.value, ch.lastFetchAt, Date.now()) || needModelBackfill) {
    // Join/backfill 是带外核对：它可能复用一个终态 channel 已排好的 30s timer。
    // 本轮失败后 connection 已切断，必须用最新 intervalOf() 重排到 5s。
    refresh(ch).finally(() => ensureScheduled(true));
  } else {
    ensureScheduled();
  }
  let released = false;
  return {
    state: ch.state,
    release: () => {
      if (released) return; // release 幂等,防组件双卸载把别人的引用计数扣穿
      released = true;
      if (wantsModelCalls) ch.modelCallsRefs = Math.max(0, ch.modelCallsRefs - 1);
      ch.refCount = Math.max(0, ch.refCount - 1);
      if (ch.refCount === 0) {
        clearTimer(ch);
        ch.guard.bump(); // in-flight 响应整包作废
        channels.delete(key); // 重新 acquire 得到干净世代（epoch 语义闭环）
      }
    },
  };
}

// poke 排队（Task 12 修复 2/3）：调用方常在「动作后立即 await poke」以求
// 数据落地后再解锁 UI（如 TaskDetail 签发按钮）。若撞上进行中的 inflight,
// 单纯 return ch.inflight 会让调用方拿到「上一轮」的落地,可能仍是旧数据。
// 追加一次 refresh（inflight resolve 后再跑一次)才能保证「poke 之后必有一次
// 新落地」；同批多次 poke 在 inflight 之后的 .then 回调里天然收敛成一次
// （第二个 .then 执行时 ch.inflight 已被第一个占住,直接复用其 promise）,
// 不会无限链。无 channel/refCount=0 时 poke 是 no-op,返回已 resolve 的 promise
// 给调用方 await 不挂起。
// 续体所有权复查（Task 12 修复 6）：inflight 续体等待期间 channel 可能已被
// release（refCount 归零→从池中删除）或换代重建（同 key 新 ch 实例）——两种
// 情况下对旧 ch 再发一次 refresh 都是浪费请求（epoch 守卫已挡住其落地污染
// state，这里只是省网络）。channels.get(key)===ch 判同一实例，ch.refCount>0
// 判仍有人持有。带外刷新还必须重排下一 tick：终态原先可能挂着 30s timer，
// 若手动核对刚失败，不能继续等旧 timer，而要立刻切到 disconnected 的 5s 节奏。
function pokeChannel(key, ch) {
  clearTimer(ch);
  const run = ch.inflight
    ? ch.inflight.then(() => (channels.get(key) === ch && ch.refCount > 0) ? refresh(ch) : undefined)
    : refresh(ch);
  return Promise.resolve(run).finally(() => {
    if (channels.get(key) === ch && ch.refCount > 0) schedule(ch);
  });
}

export function pokeTask(id) {
  const key = `task:${id}`;
  const ch = channels.get(key);
  if (!ch || ch.refCount <= 0) return Promise.resolve();
  return pokeChannel(key, ch);
}

export function pokeConversation(id) {
  const key = `conversation:${id}`;
  const ch = channels.get(key);
  if (!ch || ch.refCount <= 0) return Promise.resolve();
  return pokeChannel(key, ch);
}

export function pokeTasks() {
  const ch = channels.get("tasks");
  if (!ch || ch.refCount <= 0) return Promise.resolve();
  return pokeChannel("tasks", ch);
}

export function pokeReviewInbox(username) {
  const key = `review-inbox:${username}`;
  const ch = channels.get(key);
  if (!ch || ch.refCount <= 0) return Promise.resolve();
  return pokeChannel(key, ch);
}

export function resnapshotTask(id) {
  const key = `task:${id}`;
  const ch = channels.get(key);
  if (!ch || ch.refCount <= 0) return Promise.resolve();
  ch.resyncClock = requestFullSnapshot(ch.resyncClock);
  applyConnection(ch.state, { type: "resync", error: "manual_resnapshot" });
  return pokeTask(id);
}
