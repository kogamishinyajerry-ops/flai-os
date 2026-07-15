// frontend/src/stores/liveFeed.js —— 全站唯一 HTTP 轮询源（spec 批A §二）。
// channel 单例池：同 key 复用,引用计数归零停链。轮询纪律五不变式承袭
// taskFeed.js（链式 setTimeout/hidden 跳过仍续轮/inflight 去重/失败保旧值/
// refCount 停链）。防 stale 统一为 epoch 守卫（liveFeedCore.makeEpochGuard,
// ADR-0013 整包作废语义推广）。tasks channel 每次落地 diffTransitions 广播
// task-transition——微反馈/翻转唤醒/后续批全吃这一个总线。
import { ref } from "vue";
import { listTasks, getTask, listTaskEvents, listModelCalls } from "../api/tasks";
import { getConversation, listConversationTasks } from "../api/conversations";
import { diffTransitions, nextInterval, makeEpochGuard, shouldRefreshOnJoin } from "./liveFeedCore";

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

// —— 三类 channel 的 fetch 策略（state 形状见各 build*） ——

function buildTasksChannel(ch) {
  ch.state = { tasks: ref([]), loaded: ref(false), error: ref("") };
  ch.intervalOf = () => 5000;
  ch.fetch = async (fresh) => {
    const next = await listTasks({ limit: 100 });
    if (!fresh()) return; // 落地前复查：响应回来时若已换代（release 重建）,整包作废
    // 水合抑制（Task 12 修复 3）：loaded 仍 false 说明这是本 channel 冷启动首拉,
    // prevById 为空会让 diffTransitions 把每个任务都判成 from:null 的「迁移」——
    // 那不是真事件,是快照的初次显影,不广播不带外补拉（上百任务的冷启动不该
    // 打一发事件雨）。首拉之后（loaded 已真）的 from:null 才是轮询窗口间新出现
    // 的任务,是真事件。
    const hydrating = ch.state.loaded.value !== true;
    const evs = hydrating ? [] : diffTransitions(ch.state.tasks.value, next);
    ch.state.tasks.value = next;
    if (evs.length) {
      emitTransitions(evs);
      // 翻转唤醒：清单先看到状态变化时,带外补拉对应详情 channel（免等其下一 tick）
      for (const ev of evs) pokeTask(ev.id);
    }
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
  };
  // 动态频率：活跃 2s / waiting_review 8s / 终态 null 停轮（liveFeedCore.nextInterval）
  ch.intervalOf = () => nextInterval(ch.state.task.value?.status || "running");
  // modelCalls 请求序号（Task 12 修复 1，恢复 main 的 modelCallsSeq 语义）：挂在 channel
  // 上而非组件内——channel 按 key 池化跨组件复用,序号必须与 channel 同寿命。
  ch.modelCallsSeq = 0;
  // detail 集合 opt-in（Codex R2-P1）：modelCalls 是详情层（速览/详情页）才消费的
  // 重集合,轻订阅者（对话轴/工作台的实时行,只要 task+events 尾巴）不该为它买单。
  // 订阅计数为 0 时 fetch 跳过 listModelCalls；首个 detail 订阅者 join 时补拉一次。
  ch.modelCallsRefs = 0;
  ch.fetch = async (fresh) => {
    const offset = ch.state.events.value.length;
    const [task, tailEvents] = await Promise.all([
      getTask(taskId),
      listTaskEvents(taskId, { offset }),
    ]);
    if (!fresh()) return; // 落地前复查：task/events 到账时若已换代,不得写入新世代 state
    const prev = ch.state.task.value;
    ch.state.task.value = task;
    if (tailEvents.length) ch.state.events.value = ch.state.events.value.concat(tailEvents);
    if (prev && prev.status !== task.status) emitTransitions([{ id: taskId, from: prev.status, to: task.status, task }]);
    // modelCalls 解耦主链（Task 12 修复 4）：task+events 已落地,不因它拖慢/拖挂主快照；
    // 并行独立发,同样受 fresh() 守卫。序号守卫（修复 1）：手动刷新可与在途轮询重叠,
    // 只让「最新一次发起」的结果落盘,迟到的旧响应（含旧错误）整包作废。错误诚实化
    // （修复 2）：main 原语义是失败时展示 modelCallsError,换轨时被静默吞掉误报「无
    // 模型调用」,此处恢复。
    if (ch.modelCallsRefs === 0) return; // 无 detail 订阅者不打重查询（Codex R2-P1）
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
  };
}

function buildConversationChannel(ch, convId) {
  ch.state = { conversation: ref(null), memberTasks: ref([]), loaded: ref(false), error: ref("") };
  ch.intervalOf = () => 5000;
  ch.fetch = async (fresh) => {
    const [conversation, memberTasks] = await Promise.all([
      getConversation(convId), listConversationTasks(convId),
    ]);
    if (!fresh()) return; // 落地前复查：响应回来时若已换代,整包作废
    // 水合抑制（Task 12 修复 3）：语义同 buildTasksChannel——冷启动首拉不广播/不带外补拉。
    const hydrating = ch.state.loaded.value !== true;
    const evs = hydrating ? [] : diffTransitions(ch.state.memberTasks.value, memberTasks);
    ch.state.conversation.value = conversation;
    ch.state.memberTasks.value = memberTasks;
    if (evs.length) { emitTransitions(evs); for (const ev of evs) pokeTask(ev.id); }
  };
}

function makeChannel(key) {
  const ch = { key, refCount: 0, timer: null, inflight: null, guard: makeEpochGuard() };
  if (key === "tasks") buildTasksChannel(ch);
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
      await ch.guard.wrap(epoch, () => ch.fetch(fresh))();
      // wrap 语义：epoch 已变（channel 被释放重建/参数变更）→ fetch 整体不执行；
      // fetch 内部另有 fresh() 落地复查,覆盖「起跑时当代但落地时已换代」的窗口。
      if (fresh()) {
        ch.state.loaded.value = true;
        ch.state.error.value = "";
        ch.lastFetchAt = Date.now(); // join 去重新鲜度锚点（shouldRefreshOnJoin）
      }
    } catch (err) {
      if (fresh() && ch.state.loaded.value === false) ch.state.error.value = err.detail || err.message || "加载失败";
      // 已 loaded 的失败保旧值,下 tick 自愈（taskFeed 原语义）
    } finally {
      ch.inflight = null;
    }
  })();
  return ch.inflight;
}

function schedule(ch) {
  clearTimer(ch);
  const ms = ch.intervalOf();
  if (ms === null) return; // 终态停轮
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
  const ensureScheduled = () => { if (ch.refCount > 0 && !ch.timer) schedule(ch); };
  // join 去重（liveFeedCore.shouldRefreshOnJoin）：channel 已 loaded 且 3s 内刚
  // 拉过时,join 不再补拉一次——链本身继续跑,排链兜底逻辑原样保留。
  if (shouldRefreshOnJoin(ch.state.loaded.value, ch.lastFetchAt, Date.now()) || needModelBackfill) {
    refresh(ch).finally(ensureScheduled);
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
// 判仍有人持有。
export function pokeTask(id) {
  const key = `task:${id}`;
  const ch = channels.get(key);
  if (!ch || ch.refCount <= 0) return Promise.resolve();
  return ch.inflight
    ? ch.inflight.then(() => (channels.get(key) === ch && ch.refCount > 0) ? refresh(ch) : undefined)
    : refresh(ch);
}

export function pokeConversation(id) {
  const key = `conversation:${id}`;
  const ch = channels.get(key);
  if (!ch || ch.refCount <= 0) return Promise.resolve();
  return ch.inflight
    ? ch.inflight.then(() => (channels.get(key) === ch && ch.refCount > 0) ? refresh(ch) : undefined)
    : refresh(ch);
}
