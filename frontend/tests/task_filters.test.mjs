// frontend/tests/task_filters.test.mjs — 任务台状态筛选的纯函数契约。
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  TASK_FILTERS,
  countTasksByFilter,
  filterTasks,
  taskMatchesFilter,
} from "../src/utils/taskFilters.js";

const taskConsoleSource = readFileSync(
  new URL("../src/views/TaskConsole.vue", import.meta.url),
  "utf8",
);
const taskFiltersSource = readFileSync(
  new URL("../src/utils/taskFilters.js", import.meta.url),
  "utf8",
);

const TASKS = [
  { id: "created", status: "created" },
  { id: "queued", status: "queued" },
  { id: "running", status: "running" },
  { id: "validating", status: "validating" },
  { id: "review", status: "waiting_review" },
  { id: "completed", status: "completed" },
  { id: "failed", status: "failed" },
  { id: "cancelled", status: "cancelled" },
  { id: "unknown", status: "future_state" },
];

test("task filters expose the six required, stable groups", () => {
  assert.deepEqual(
    TASK_FILTERS.map(({ key, label }) => [key, label]),
    [
      ["all", "全部"],
      ["working", "执行中"],
      ["waiting_review", "待签发"],
      ["completed", "已完成"],
      ["failed", "失败"],
      ["cancelled", "已取消"],
    ],
  );
});

test("working matches the clay work-state SSOT; cancelled is never failed", () => {
  for (const status of ["validating", "parsing", "running", "analyzing"]) {
    assert.equal(taskMatchesFilter({ status }, "working"), true);
  }
  for (const status of ["created", "queued", "waiting_review", "completed", "failed", "cancelled"]) {
    assert.equal(taskMatchesFilter({ status }, "working"), false, `${status} must not be grouped as working`);
  }
  assert.equal(taskMatchesFilter({ status: "cancelled" }, "cancelled"), true);
  assert.equal(taskMatchesFilter({ status: "cancelled" }, "failed"), false);
  assert.match(taskFiltersSource, /import\s*\{\s*TASK_WORK_STATES\s*\}\s*from\s*["']\.\/format\.js["']/);
  assert.doesNotMatch(taskFiltersSource, /const\s+WORKING_STATUSES\s*=\s*new Set/);
});

test("counts are derived from the complete feed without hiding zero or unknown states", () => {
  assert.deepEqual(countTasksByFilter(TASKS), {
    all: 9,
    working: 2,
    waiting_review: 1,
    completed: 1,
    failed: 1,
    cancelled: 1,
  });
  assert.deepEqual(countTasksByFilter([]), {
    all: 0,
    working: 0,
    waiting_review: 0,
    completed: 0,
    failed: 0,
    cancelled: 0,
  });
});

test("filtering preserves feed order and unknown filters fail closed to an empty result", () => {
  assert.deepEqual(filterTasks(TASKS, "working").map((task) => task.id), ["running", "validating"]);
  assert.deepEqual(filterTasks(TASKS, "cancelled").map((task) => task.id), ["cancelled"]);
  assert.deepEqual(filterTasks(TASKS, "all"), TASKS);
  assert.deepEqual(filterTasks(TASKS, "not-a-filter"), []);
  assert.deepEqual(filterTasks(null, "all"), []);
});

test("TaskConsole uses a native pressed-button filter group with an explicit empty result", () => {
  assert.match(taskConsoleSource, /role="group"/);
  assert.match(taskConsoleSource, /type="button"/);
  assert.match(taskConsoleSource, /:aria-pressed=/);
  assert.doesNotMatch(taskConsoleSource, /role="tab(?:list)?"/);
  assert.match(taskConsoleSource, /该筛选下暂无任务/);
  assert.match(taskConsoleSource, /min-block-size:\s*var\(--space-6\)/);
  assert.match(
    taskConsoleSource,
    /<template\s+v-if="feedLoaded">/,
    "cold fetch failures must not render a 'recent tasks · 0' result group",
  );
});
