// frontend/tests/livefeed_core.test.mjs — node --test，零框架依赖。
// tamper 纪律：三个核心行为各有「拆守卫必红」的断言（见各 case 注释）。
import test from "node:test";
import assert from "node:assert/strict";
import { diffTransitions, nextInterval, makeEpochGuard, shouldRefreshOnJoin, TERMINAL_STATUSES } from "../src/stores/liveFeedCore.js";

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

test("shouldRefreshOnJoin: 未 loaded/超过新鲜窗必拉,3s 内刚拉过不补拉（tamper：把 >= 改 > 不咬本测试无边界 case；把整函数改恒 true 则「1s 前拉过→false」必红）", () => {
  assert.equal(shouldRefreshOnJoin(false, null, 1000), true); // 未 loaded
  assert.equal(shouldRefreshOnJoin(true, 0, 1000), false); // loaded 且 1s 前刚拉过（<3s 新鲜窗）
  assert.equal(shouldRefreshOnJoin(true, 0, 4000), true); // loaded 但 4s 前拉过（超新鲜窗）
  assert.equal(shouldRefreshOnJoin(true, undefined, 1000), true); // lastFetchAt 缺失
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

// 落地复查谓词地基（Task 12 修复 1）：liveFeed.js 的 refresh() 用
// `fresh = () => epochAtStart === guard.current()` 作为「响应落地前」的
// 复查判据（区别于 wrap 的「起跑前」预检，覆盖 await 期间换代的窗口）。
// tamper：把 refresh() 里的落地复查删掉/固定 fresh 恒 true，此条不会红
// （它测的是 makeEpochGuard 本身），但对应 build*Channel 里的 `if (!fresh())
// return;` 一旦被拆掉，批A 治理审 R0 task-report 里的落地复查回归测试会红——
// 本条只锚 epoch 语义地基，行为回归覆盖见 fetch 落地路径本身。
test("epochGuard: current() 是 fresh() 谓词的地基——bump 后 current() 变化使旧 epoch 判 stale", () => {
  const g = makeEpochGuard();
  const epochAtStart = g.current();
  const freshBefore = () => epochAtStart === g.current();
  assert.equal(freshBefore(), true); // 未 bump：仍是当代
  g.bump(); // 模拟 channel release 重建（响应在途中换代）
  const freshAfter = () => epochAtStart === g.current();
  assert.equal(freshAfter(), false); // bump 后：旧 epoch 判 stale,落地必须整包作废
});
