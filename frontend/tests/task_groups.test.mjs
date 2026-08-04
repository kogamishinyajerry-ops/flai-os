// frontend/tests/task_groups.test.mjs — node --test，零框架依赖。
// 任务分组谓词 SSOT（#30 今日页与任务台合并）：今日页三分组与任务台左栏
// 共用同一判据，tamper 任一谓词此处必红。
import test from "node:test";
import assert from "node:assert/strict";
import { isWaitingReview, isWorking, isDeliveredToday } from "../src/utils/taskGroups.js";

// 固定「本地零点」夹具：2026-08-04 本地零点（用本地时区构造，与调用方
// localDayStartMs 同式，避免 UTC/本地混用）。
const dayStart = new Date(2026, 7, 4, 0, 0, 0, 0);
const dayStartMs = dayStart.getTime();
const iso = (d) => d.toISOString();

test("isWaitingReview: waiting_review 命中，其余不命中", () => {
  assert.equal(isWaitingReview({ status: "waiting_review" }), true);
  for (const s of ["created", "queued", "running", "validating", "completed", "failed", "cancelled"]) {
    assert.equal(isWaitingReview({ status: s }), false, s);
  }
});

test("isWorking: 四工作态命中，待签/终态不命中", () => {
  for (const s of ["created", "queued", "running", "validating"]) {
    assert.equal(isWorking({ status: s }), true, s);
  }
  for (const s of ["waiting_review", "completed", "failed", "cancelled"]) {
    assert.equal(isWorking({ status: s }), false, s);
  }
});

test("isDeliveredToday: 终态且 finished_at ≥ 本地零点 命中", () => {
  for (const s of ["completed", "failed", "cancelled"]) {
    assert.equal(
      isDeliveredToday({ status: s, finished_at: iso(new Date(dayStartMs + 3600_000)) }, dayStartMs),
      true,
      s,
    );
  }
  // 非终态即使 finished_at 在今日也不算交付
  assert.equal(isDeliveredToday({ status: "running", finished_at: iso(new Date(dayStartMs + 1000)) }, dayStartMs), false);
});

test("isDeliveredToday: 零点边界——恰好零点算今日，昨日 23:59 不算", () => {
  assert.equal(isDeliveredToday({ status: "completed", finished_at: iso(new Date(dayStartMs)) }, dayStartMs), true);
  assert.equal(
    isDeliveredToday({ status: "completed", finished_at: iso(new Date(dayStartMs - 60_000)) }, dayStartMs),
    false,
  );
  assert.equal(isDeliveredToday({ status: "completed", finished_at: iso(new Date(dayStartMs - 1)) }, dayStartMs), false);
});

test("isDeliveredToday: finished_at 缺失不算（诚实地板，不虚报交付）", () => {
  assert.ok(!isDeliveredToday({ status: "completed" }, dayStartMs));
  assert.ok(!isDeliveredToday({ status: "completed", finished_at: null }, dayStartMs));
  assert.ok(!isDeliveredToday({ status: "completed", finished_at: "" }, dayStartMs));
});
