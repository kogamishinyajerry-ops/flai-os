# 批A「活的工作台」Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 全站 4 条异构 HTTP 轮询链收拢为 liveFeed 多 channel 单源 + 状态迁移事件总线，其上落微反馈动效收口与首载骨架屏。

**Architecture:** 纯函数核 `liveFeedCore.js`（node --test 可测）+ Vue 响应层 `liveFeed.js`（channel 单例池/引用计数/链式轮询）；`taskFeed.js` 变 shim 保兼容；五消费方逐个换轨,每步既有 e2e 锚点复跑。动效全部挂在 liveFeed 总线的 `task-transition` 事件上。

**Tech Stack:** Vue 3 + Vite（零新依赖）；node:test 原生跑器；Playwright e2e（既有 python 驱动模式）。

## Global Constraints

- 零新 npm 依赖（轻内核纪律）；不动后端任何文件；不动 router；不动 GuidePage 对话逻辑。
- 信任色锁五槽不动；teal 仅人签（burstSigned 唯一许可点不变）；动效 token 纯时间性；带色动效只引用 `-rgb` 语义三元组。
- MOTION-SYSTEM.md 硬约束六条有效；reduced-motion 全降级。
- ADR-0013 防 stale 语义（offset 增量/整包作废/换代守卫/artifactsFingerprint）迁移后逐条保留且测试意图不减。
- 轮询纪律不变式：链式 setTimeout（上轮落地才排下轮）+ document.hidden 跳过仍续轮 + refCount 归零停链 + inflight 去重 + 失败保旧值自愈。
- 每消费方迁移=独立 commit；`git add` 只按显式路径（共享仓并发纪律）。
- 跑测：后端 `uv run --no-project --with pytest --with jsonschema --with pyyaml --with fastapi --with httpx --with python-multipart --with openpyxl --with jieba --with "pydantic>2" python -m pytest -q`；前端核 `node --test frontend/tests/`；e2e 见各任务。

---

## File Structure

```
frontend/src/stores/liveFeedCore.js   # 新·纯函数核（零 Vue 依赖）：diffTransitions/nextInterval/makeEpochGuard
frontend/src/stores/liveFeed.js       # 新·channel 池 + 总线（依赖 Vue ref + api/*）
frontend/src/stores/taskFeed.js       # 改·变 re-export shim（导出名/语义不变）
frontend/tests/livefeed_core.test.mjs # 新·node --test
frontend/src/components/SkeletonBlock.vue  # 新
frontend/e2e/batch_a_livefeed_acceptance.py # 新
scripts/verify_all.sh                 # 改·加 node --test 步 + 新 e2e
（迁移触点）StatusCenter.vue / TaskDetail.vue / WorkbenchSession.vue / GuidePage.vue / StatusDock.vue / App.vue / CompletionSeal.vue / TaskCreate.vue
（清理）src/effects/particleField.js（删）/ src/components/artwork/DraftingScene.vue（删,先 grep 归零）/ docs/design/MOTION-SYSTEM.md（修 P1 指向）
```

---

### Task 1: liveFeedCore 纯函数核（TDD）

**Files:**
- Create: `frontend/src/stores/liveFeedCore.js`
- Test: `frontend/tests/livefeed_core.test.mjs`
- Modify: `scripts/verify_all.sh`（加 `node --test frontend/tests/` 步,插在 pytest 步之后）

**Interfaces（Produces,后续任务倚赖的精确签名）:**
```js
export function diffTransitions(prevList, nextList)
// [{id,status}] × 2 → [{id, from, to, task}]；prev 中不存在的 id 视为 from:null（新任务入列也算迁移）；status 相同不产事件。
export function nextInterval(status)
// 'waiting_review'→8000；终态('completed'|'failed'|'cancelled')→null（停轮）；其余→2000。
export function makeEpochGuard()
// → {current(), bump(), wrap(epochAtStart, fn)}：wrap 返回的函数执行时若 epoch 已变则整体 no-op（整包作废语义）。
export const TERMINAL_STATUSES = ["completed", "failed", "cancelled"];
```

- [ ] **Step 1: 写失败测试**（完整文件）：

```js
// frontend/tests/livefeed_core.test.mjs — node --test，零框架依赖。
// tamper 纪律：三个核心行为各有「拆守卫必红」的断言（见各 case 注释）。
import test from "node:test";
import assert from "node:assert/strict";
import { diffTransitions, nextInterval, makeEpochGuard, TERMINAL_STATUSES } from "../src/stores/liveFeedCore.js";

test("diffTransitions: 状态翻转产事件,含 from/to/task 快照", () => {
  const prev = [{ id: "t1", status: "running" }, { id: "t2", status: "queued" }];
  const next = [{ id: "t1", status: "waiting_review" }, { id: "t2", status: "queued" }];
  const evs = diffTransitions(prev, next);
  assert.equal(evs.length, 1);
  assert.deepEqual({ id: evs[0].id, from: evs[0].from, to: evs[0].to }, { id: "t1", from: "running", to: "waiting_review" });
  assert.equal(evs[0].task.id, "t1"); // task=next 侧快照,消费方免二次查找
});

test("diffTransitions: 新入列任务 from=null 也算迁移（提交飞入动效的数据源）", () => {
  const evs = diffTransitions([], [{ id: "t9", status: "queued" }]);
  assert.equal(evs.length, 1);
  assert.equal(evs[0].from, null);
  assert.equal(evs[0].to, "queued");
});

test("diffTransitions: 状态未变零事件（tamper：把 !== 改 == 此条必红）", () => {
  const same = [{ id: "t1", status: "running" }];
  assert.equal(diffTransitions(same, same).length, 0);
});

test("nextInterval: 活跃 2s / waiting_review 8s / 终态 null（tamper：waiting_review 回 null=旧停轮缺陷复活,此条必红）", () => {
  assert.equal(nextInterval("running"), 2000);
  assert.equal(nextInterval("queued"), 2000);
  assert.equal(nextInterval("waiting_review"), 8000);
  for (const s of TERMINAL_STATUSES) assert.equal(nextInterval(s), null);
});

test("epochGuard: bump 后旧 epoch 的 wrap 整体 no-op（整包作废,ADR-0013 语义;tamper：拆比对此条必红）", () => {
  const g = makeEpochGuard();
  let applied = 0;
  const e0 = g.current();
  const apply = g.wrap(e0, () => { applied += 1; });
  g.bump();
  apply();
  assert.equal(applied, 0); // 旧世代响应作废
  const apply2 = g.wrap(g.current(), () => { applied += 1; });
  apply2();
  assert.equal(applied, 1); // 当代响应落地
});
```

- [ ] **Step 2: 跑测确认失败**：`cd frontend && node --test tests/` → Expected: FAIL（模块不存在）。
- [ ] **Step 3: 最小实现**（完整文件）：

```js
// frontend/src/stores/liveFeedCore.js —— liveFeed 的纯函数核（零 Vue/DOM 依赖,
// node --test 可测）。语义出处：spec 批A §二；ADR-0013「整包作废」推广为
// epoch 守卫；waiting_review 改降频不停轮（修跨会话放行手动刷新缺陷）。
export const TERMINAL_STATUSES = ["completed", "failed", "cancelled"];

export function diffTransitions(prevList, nextList) {
  const prevById = new Map((prevList || []).map((t) => [t.id, t.status]));
  const out = [];
  for (const task of nextList || []) {
    const from = prevById.has(task.id) ? prevById.get(task.id) : null;
    if (from !== task.status) out.push({ id: task.id, from, to: task.status, task });
  }
  return out;
}

export function nextInterval(status) {
  if (TERMINAL_STATUSES.includes(status)) return null;
  if (status === "waiting_review") return 8000;
  return 2000;
}

export function makeEpochGuard() {
  let epoch = 0;
  return {
    current: () => epoch,
    bump: () => { epoch += 1; },
    wrap: (epochAtStart, fn) => (...args) => {
      if (epochAtStart !== epoch) return undefined; // 旧世代整包作废
      return fn(...args);
    },
  };
}
```

- [ ] **Step 4: 跑测全绿**：`cd frontend && node --test tests/` → Expected: 5 pass。
- [ ] **Step 5: verify_all 接线**：`scripts/verify_all.sh` 在 pytest 步之后加：

```bash
step "①b 前端纯函数核 node --test" \
  bash -c 'cd "$ROOT/frontend" && node --test tests/'
```
（照该脚本既有 step 函数写法对齐；跑 `bash scripts/verify_all.sh` 确认新步绿。）

- [ ] **Step 6: Commit**：`git add frontend/src/stores/liveFeedCore.js frontend/tests/livefeed_core.test.mjs scripts/verify_all.sh && git commit -m "feat(ux): liveFeedCore 纯函数核（diff/interval/epoch,node --test 入 verify_all）"`

### Task 2: liveFeed channel 池 + taskFeed shim

**Files:**
- Create: `frontend/src/stores/liveFeed.js`
- Modify: `frontend/src/stores/taskFeed.js`（整文件替换为 shim）

**Interfaces（Produces）:**
```js
// liveFeed.js
export function acquireChannel(key, opts?) // → { state, release }
//   key='tasks' → state={tasks:ref([]),loaded:ref(false),error:ref("")}
//   key='task:<id>' → state={task:ref(null),events:ref([]),modelCalls:ref([]),loaded,error}
//   key='conversation:<id>' → state={conversation:ref(null),memberTasks:ref([]),loaded,error}
export function onTransition(fn)   // 订阅总线,返回 off()；fn({id,from,to,task})
export function pokeTask(id)       // 带外唤醒:若存在 task:<id> channel 立即补拉一次
```
- Consumes: Task 1 的四个导出 + `api/tasks.js` 的 listTasks/getTask/listTaskEvents/listModelCalls + `api/conversations.js` 的 getConversation/listConversationTasks。

- [ ] **Step 1: 实现 liveFeed.js**（完整文件）：

```js
// frontend/src/stores/liveFeed.js —— 全站唯一 HTTP 轮询源（spec 批A §二）。
// channel 单例池：同 key 复用,引用计数归零停链。轮询纪律五不变式承袭
// taskFeed.js（链式 setTimeout/hidden 跳过仍续轮/inflight 去重/失败保旧值/
// refCount 停链）。防 stale 统一为 epoch 守卫（liveFeedCore.makeEpochGuard,
// ADR-0013 整包作废语义推广）。tasks channel 每次落地 diffTransitions 广播
// task-transition——微反馈/翻转唤醒/后续批全吃这一个总线。
import { ref } from "vue";
import { listTasks, getTask, listTaskEvents, listModelCalls } from "../api/tasks";
import { getConversation, listConversationTasks } from "../api/conversations";
import { diffTransitions, nextInterval, makeEpochGuard, TERMINAL_STATUSES } from "./liveFeedCore";

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
  ch.fetch = async () => {
    const next = await listTasks({ limit: 100 });
    const evs = diffTransitions(ch.state.tasks.value, next);
    ch.state.tasks.value = next;
    if (evs.length) {
      emitTransitions(evs);
      // 翻转唤醒：清单先看到状态变化时,带外补拉对应详情 channel（免等其下一 tick）
      for (const ev of evs) pokeTask(ev.id);
    }
  };
}

function buildTaskChannel(ch, taskId) {
  ch.state = { task: ref(null), events: ref([]), modelCalls: ref([]), loaded: ref(false), error: ref("") };
  // 动态频率：活跃 2s / waiting_review 8s / 终态 null 停轮（liveFeedCore.nextInterval）
  ch.intervalOf = () => nextInterval(ch.state.task.value?.status || "running");
  ch.fetch = async () => {
    const offset = ch.state.events.value.length;
    const [task, tailEvents, modelCalls] = await Promise.all([
      getTask(taskId),
      listTaskEvents(taskId, { offset }),
      listModelCalls(taskId).catch(() => null), // modelCalls 失败回落旧值（StatusCenter 原语义）
    ]);
    const prev = ch.state.task.value;
    ch.state.task.value = task;
    if (tailEvents.length) ch.state.events.value = ch.state.events.value.concat(tailEvents);
    if (modelCalls !== null) ch.state.modelCalls.value = modelCalls;
    if (prev && prev.status !== task.status) emitTransitions([{ id: taskId, from: prev.status, to: task.status, task }]);
  };
}

function buildConversationChannel(ch, convId) {
  ch.state = { conversation: ref(null), memberTasks: ref([]), loaded: ref(false), error: ref("") };
  ch.intervalOf = () => 5000;
  ch.fetch = async () => {
    const [conversation, memberTasks] = await Promise.all([
      getConversation(convId), listConversationTasks(convId),
    ]);
    const evs = diffTransitions(ch.state.memberTasks.value, memberTasks);
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
  ch.inflight = (async () => {
    try {
      await ch.guard.wrap(epoch, () => ch.fetch())() ;
      // wrap 语义：epoch 已变（channel 被释放重建/参数变更）→ fetch 整体不执行
      ch.state.loaded.value = true;
      ch.state.error.value = "";
    } catch (err) {
      if (ch.state.loaded.value === false) ch.state.error.value = err.detail || err.message || "加载失败";
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

export function acquireChannel(key) {
  let ch = channels.get(key);
  if (!ch) { ch = makeChannel(key); channels.set(key, ch); }
  ch.refCount += 1;
  refresh(ch).finally(() => { if (ch.refCount > 0 && !ch.timer) schedule(ch); });
  let released = false;
  return {
    state: ch.state,
    release: () => {
      if (released) return; // release 幂等,防组件双卸载把别人的引用计数扣穿
      released = true;
      ch.refCount = Math.max(0, ch.refCount - 1);
      if (ch.refCount === 0) {
        clearTimer(ch);
        ch.guard.bump(); // in-flight 响应整包作废
        channels.delete(key); // 重新 acquire 得到干净世代（epoch 语义闭环）
      }
    },
  };
}

export function pokeTask(id) {
  const ch = channels.get(`task:${id}`);
  if (ch && ch.refCount > 0) refresh(ch);
}
```

- [ ] **Step 2: taskFeed.js 整文件替换为 shim**（完整文件）：

```js
// 兼容 shim（批A 迁移期）：导出名/语义与旧 taskFeed 完全一致,内部直连
// liveFeed 'tasks' channel。全部消费方直连 liveFeed 后本文件删除。
import { acquireChannel } from "./liveFeed";

let handle = null;
export let feedTasks, feedLoaded, feedError;

export function acquireTaskFeed() {
  handle = acquireChannel("tasks");
  feedTasks = handle.state.tasks;
  feedLoaded = handle.state.loaded;
  feedError = handle.state.error;
}
export function releaseTaskFeed() {
  if (handle) { handle.release(); handle = null; }
}
```
**注意**：旧 shim 消费方（StatusDock/TaskConsole）以 `import { feedTasks } from "../stores/taskFeed"` 顶层导入——上面写法在 acquire 前 feedTasks 为 undefined 会炸。**正确 shim**：模块加载即建 ref 别名（channel 常驻单例化）：

```js
import { acquireChannel } from "./liveFeed";
const handle = acquireChannel("tasks"); // 模块级取一次,拿稳定 ref
handle.release(); // 立刻归还引用（refCount 归零会删 channel——见下一行的对策）
```
——这个方案与「refCount 归零删 channel」冲突。**最终定案（实现者照此做,不再自行发挥）**：shim 不预取,导出**同一形状的模块级 ref**,acquire 时桥接：

```js
// frontend/src/stores/taskFeed.js —— 兼容 shim 终版
import { ref, watch } from "vue";
import { acquireChannel } from "./liveFeed";

export const feedTasks = ref([]);
export const feedLoaded = ref(false);
export const feedError = ref("");

let handle = null;
let stops = [];
export function acquireTaskFeed() {
  if (!handle) {
    handle = acquireChannel("tasks");
    stops = [
      watch(handle.state.tasks, (v) => { feedTasks.value = v; }, { immediate: true }),
      watch(handle.state.loaded, (v) => { feedLoaded.value = v; }, { immediate: true }),
      watch(handle.state.error, (v) => { feedError.value = v; }, { immediate: true }),
    ];
  }
  refCount += 1;
}
let refCount = 0;
export function releaseTaskFeed() {
  refCount = Math.max(0, refCount - 1);
  if (refCount === 0 && handle) {
    stops.forEach((s) => s());
    stops = [];
    handle.release();
    handle = null;
  }
}
```

- [ ] **Step 3: 手动冒烟**：`npm run build`（frontend/）零错误；起后端开 /tasks 页,DevTools Network 确认 listTasks 单链 5s。
- [ ] **Step 4: 既有 e2e 锚点复跑**：`m2_acceptance.py` + `m8_workbench_acceptance.py` 全绿（TaskConsole/StatusDock 是 shim 消费方）。
- [ ] **Step 5: Commit**：`git add frontend/src/stores/liveFeed.js frontend/src/stores/taskFeed.js && git commit -m "feat(ux): liveFeed 多 channel 单源 + taskFeed 兼容 shim"`

### Task 3: StatusCenter inbox 并轨（第一合并对象）

**Files:**
- Modify: `frontend/src/components/StatusCenter.vue`（inbox 部分,锚点 :220 refreshInbox 与 :458 轮询链）

**配方**：inbox 数据源从自拉 `listTasks({limit:100})` 改为 `acquireChannel('tasks')`（打开抽屉 acquire、关闭 release——保留「关闭零后台消耗」语义:抽屉关=release,channel 若无其他订阅者自停）。peek 部分本任务**不动**（Task 5）。3s 轮询链里 inbox 分支删除,peek 分支保留。验收:①开抽屉时 Network 无第二条 listTasks 链②既有 StatusCenter 相关 e2e 锚（m8_workbench）绿。Commit: `refactor(ux): StatusCenter inbox 并轨 liveFeed tasks channel`。

### Task 4: TaskDetail 换轨 + 免手动刷新验收

**Files:**
- Modify: `frontend/src/views/TaskDetail.vue`（锚点 :352 syncModelCalls/:466 loadTask/:511 schedulePoll）
- Test: `frontend/e2e/batch_a_livefeed_acceptance.py`（本任务先建骨架,断言②）

**配方**：删自建 2s 轮询链（schedulePoll/loadTask silent 路径/baseline 守卫/modelCallsSeq）,改 `acquireChannel('task:'+taskId)` 订阅（onMounted acquire/onUnmounted release;`:key` 重建天然重 acquire）。artifacts 的 fingerprint 增量逻辑**保留在组件内**（订阅 state.task 的 output_file_ids watch 触发,原语义原测试意图）。手动「刷新」按钮保留=调 `pokeTask(taskId)`。waiting_review 不再停轮（channel 8s 降频）——**跨会话放行免手动刷新**由此闭环,加 e2e 断言：

```python
# batch_a_livefeed_acceptance.py 断言②（骨架,Task 7 补全①③）：
# 开 TaskDetail 于 waiting_review 任务 → 后台直接 API approve（另一 httpx 会话模拟跨会话放行）
# → 不点刷新,12s 内页面出现终态盖章文案「已完成」。
```
验收:e2e 断言② PASS + m2_acceptance 8/8（其含 waiting_review 放行 UI 流,防回归）。Commit: `refactor(ux): TaskDetail 并轨 task channel,跨会话放行免手动刷新`。

### Task 5: StatusCenter peek 并轨

**Files:** Modify: `frontend/src/components/StatusCenter.vue`（:298 loadPeek/:458 轮询链残余）

**配方**：peek 改 `acquireChannel('task:'+taskId)`（openTaskPeek acquire、关闭/切换 release+重 acquire）;peekEpoch/artifactsFingerprint 自建守卫删除（channel epoch 承接）;产物加载沿 Task 4 同款 watch。3s 轮询链整体删除（inbox/peek 均已并轨）。验收:开抽屉 peek 与同 taskId 的 TaskDetail 同屏时 Network 仅一条该任务详情链（channel 复用实证,DevTools 截图存证）。Commit。

### Task 6: WorkbenchSession + GuidePage 会话轨并轨

**Files:** Modify: `frontend/src/views/WorkbenchSession.vue`（:225 refreshLastWords/:299 轮询）、`frontend/src/views/GuidePage.vue`（:641 maybeStartTaskPoll）

**配方**：两页各自的会话轮询改 `acquireChannel('conversation:'+id)`。WorkbenchSession 的 refreshLastWords（≤5 任务 offset:0 全量重拉）删除——成员「最后一句」改为对每个**非终态**成员任务 `acquireChannel('task:'+id)` 取 events 尾（终态成员一次性拉取后 release,不常驻）;成员数上限沿用 ≤5 常驻订阅,超出部分静态。GuidePage 方案卡 chip 改订阅 conversation channel 的 memberTasks。验收:workbench 相关 3 套 e2e 全绿;Network 实证 WorkbenchSession 不再有 offset:0 反复全量拉事件。Commit。

### Task 7: 收口 e2e ①③ + 单链断言

**Files:** Modify: `frontend/e2e/batch_a_livefeed_acceptance.py`、`scripts/verify_all.sh`

断言①:page.route 拦截计数——同屏开 TaskConsole+StatusCenter 抽屉 30s,`/api/tasks?` 清单请求 ≤8 次（单链 5s 语义,双链会 ≥12）。断言③:CompletionSeal 盖章动效 class（`seal-animate`)在「亲历迁移」时出现、历史直开不出现（Task 9 产物,若 Task 9 未落则此断言在 Task 9 里补）。入 verify_all。Commit: `test(ux): 批A liveFeed 验收 e2e 入 verify_all`。

### Task 8: --ease-lift 实机验证收口 + transition 族统一 + 孤儿清理

**Files:**
- Modify: `frontend/src/App.vue`（:301 --ease-lift 定义,:527-576 工具类区）+ 全站 ~20 处 `var(--ease-lift)` 引用（grep 定位）
- Delete: `frontend/src/effects/particleField.js`、`frontend/src/components/artwork/DraftingScene.vue`（先 `grep -rn "particleField\|DraftingScene" frontend/src` 归零才删）
- Modify: `docs/design/MOTION-SYSTEM.md`（修指向已删文件的 P1 条目）

- [ ] **Step 1 实机验证**：写 10 行 Playwright 片段读某 `.sb-new` 的 `getComputedStyle().transitionDelay`——若为 `0.18s` 确证 bug。证据（值+截图）入 commit message。
- [ ] **Step 2**：确证后全站 `transition: all 0.16s var(--ease-lift)` → `transition: all var(--motion-fast) var(--ease-out-soft)`（0.16s≈--motion-fast 0.14s,统一取 token;逐处目检 hover 意图不变）;删 --ease-lift 定义;若未确证,仅在 MOTION-SYSTEM.md 记录证据保 token。
- [ ] **Step 3**：其余零散 transition 时长归一到 --motion-* 族（grep `transition:.*[0-9]+m?s` 逐处,Element Plus 默认不覆盖的判例保留）。
- [ ] **Step 4**：孤儿删除 + MOTION-SYSTEM.md 修订;`npm run build` 零 error;全站 5 套 e2e 复跑绿（动效改动防误伤）。
- [ ] **Step 5: Commit**（含实机验证证据）。

### Task 9: CompletionSeal 盖章动效 + burstNeutral 接线

**Files:** Modify: `frontend/src/components/CompletionSeal.vue`、`frontend/src/views/TaskDetail.vue`（挂接线）

**配方**：CompletionSeal 加 prop `animate:Boolean`。animate=true 时:两根 .seal-line `transform: scaleX(0→1)`（transform-origin 分别 right/left,--motion-slow + --ease-out-soft）,.seal-text fx-ink-in 浮现;completed 且 animate 时在组件 mounted 后调 `burstNeutral(elCenterX, elCenterY)`（import 自 ../effects/burst）;failed 零迸发。reduced-motion:media query 内全部动画禁用（既有全局降级块覆盖 .seal-*）。**animate 的判定在 TaskDetail**：订阅 `onTransition`,收到本 taskId `to∈TERMINAL` 迁移置 `sealAnimate=true`（一次性,不持久）;历史直开 false。动画激活时给根节点加 class `seal-animate`（e2e 断言③锚点）。teal 纪律:completed 用中性 burstNeutral——**绝不 burstSigned**（那是人签时刻专属,已有接线不动）。验收:手动触发一次 completed 迁移录 GIF 存 docs/reviews/batch-a-shots/;e2e 断言③绿。Commit。

### Task 10: 待签发回声 + 提交飞入

**Files:** Modify: `frontend/src/components/StatusDock.vue`、`frontend/src/views/TaskCreate.vue`、`frontend/src/App.vue`（仅新增一个全局订阅挂载,若 StatusDock 内可完成则不动 App.vue）

**配方**：StatusDock（常驻订阅 tasks channel）加 `onTransition` 订阅:`to==='waiting_review'` 时①待签发角标播一轮 flai-work-pulse（复用既有 keyframes,1.8s×2 后停——不常驻闪烁）②`ElMessage({message:'「'+task.name+'」待你签发',type:'warning',onClick:跳 /tasks/:id})`（去重:同 id 30s 内不重复弹;document.hidden 时不弹积到角标）。TaskCreate 提交成功跳转前:提交按钮附近播 fx-rise 一次（列表飞入感,120ms 后正常跳转,reduced-motion 直接跳）。验收:e2e 现有 m2 创建流不破;手动截图存证。Commit。

### Task 11: SkeletonBlock + 四落点

**Files:**
- Create: `frontend/src/components/SkeletonBlock.vue`（完整代码如下）
- Modify: `TaskConsole.vue`（左栏首载）、`TaskDetail.vue`（主区首载）、`WorkbenchSession.vue`（roster 首载）、`AgentPortal.vue`（卡片栅格首载）

```vue
<template>
  <!-- 首载骨架（批A A3）：暖白 shimmer;只在「从未 loaded」时由宿主 v-if 挂载,
       轮询期间绝不回骨架（防闪烁）;失败态走宿主既有 error/EmptyState,骨架不吞错误。 -->
  <div class="skel" :style="{ height, width }" aria-hidden="true"></div>
</template>
<script setup>
defineProps({ height: { type: String, default: "16px" }, width: { type: String, default: "100%" } });
</script>
<style scoped>
.skel {
  border-radius: 6px;
  background: linear-gradient(90deg, rgba(var(--ink-rgb), 0.06) 25%, rgba(var(--ink-rgb), 0.12) 37%, rgba(var(--ink-rgb), 0.06) 63%);
  background-size: 400% 100%;
  animation: skel-shimmer 1.4s ease infinite;
}
@keyframes skel-shimmer { 0% { background-position: 100% 0; } 100% { background-position: 0 0; } }
@media (prefers-reduced-motion: reduce) { .skel { animation: none; background: rgba(var(--ink-rgb), 0.08); } }
</style>
```

落点配方（四处同型）：宿主 `v-if="!loaded && !error"` 渲染 3-6 条不同宽度 SkeletonBlock 撑出该区块的真实轮廓;`loaded` 即拆。验收:节流网络（DevTools Slow 3G）截图四处骨架形态;e2e 全绿。Commit。

### Task 12: 全批收口

- [ ] `bash scripts/verify_all.sh` 全绿（含新 node --test 步 + 新 e2e）。
- [ ] DevTools Network 30s 录制截图:全站仅 liveFeed 单源（存 docs/reviews/batch-a-shots/network_single_source.png）。
- [ ] 治理审：命中「共享核心 store+全站消费方改造」→ `codex-review-relay --base main`;grounded 复核 findings。
- [ ] ledger 收口 + spec 验收标准逐条对照打钩。

## Self-Review 记录

- Spec 覆盖：§二 liveFeed（Task 1/2/3/4/5/6/7）✓ §三动效四件（Task 8/9/10 + --ease-lift=8/盖章=9/回声=10/统一+孤儿=8）✓ §四骨架（Task 11）✓ §五测试（1/4/7/12）✓。App.vue 会话列表导航刷新缺陷=spec 明示批A不含（侦察「顺带」项,范围外）。
- 类型一致性：acquireChannel/onTransition/pokeTask/TERMINAL_STATUSES 各任务引用与 Task 1/2 定义一致。
- 无占位符。
