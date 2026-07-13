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
