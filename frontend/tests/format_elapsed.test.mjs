// 批次六 B6-5：taskElapsedMs 端锚三态契约（诚实地板）。
// 待签行此前以 now 为端锚——任务停驻待签时墙钟不是运行时长，「运行 Xs」持续
// 膨胀是假声明；无 finished_at 且非工作态 → null（不显示胜过显示膨胀谎言）。
import test from "node:test";
import assert from "node:assert/strict";
import { taskElapsedMs, TASK_WORK_STATES } from "../src/utils/format.js";

const T0 = "2026-07-16T08:00:00+00:00";
const T0_MS = Date.parse(T0);

test("taskElapsedMs: 工作态无 finished_at → now 活端锚（合法增长）", () => {
  assert.ok(TASK_WORK_STATES.has("running"), "前提：running 属工作态");
  const t = { status: "running", started_at: T0, finished_at: null };
  assert.equal(taskElapsedMs(t, T0_MS + 5000), 5000);
  assert.equal(taskElapsedMs(t, T0_MS + 9000), 9000);
});

test("taskElapsedMs: waiting_review 停驻态无 finished_at → null（绝不拿墙钟冒充运行时长）", () => {
  assert.ok(!TASK_WORK_STATES.has("waiting_review"), "前提：待签非工作态");
  const t = { status: "waiting_review", started_at: T0, finished_at: null };
  assert.equal(taskElapsedMs(t, T0_MS + 60_000), null);
});

test("taskElapsedMs: 终态 finished_at 静止端锚（不随 now 漂移）", () => {
  const t = { status: "completed", started_at: T0, finished_at: "2026-07-16T08:00:30+00:00" };
  assert.equal(taskElapsedMs(t, T0_MS + 999_000), 30_000);
});

test("taskElapsedMs: 无 started_at 诚实 null（不编造耗时）", () => {
  assert.equal(taskElapsedMs({ status: "queued", started_at: null }, T0_MS), null);
});
