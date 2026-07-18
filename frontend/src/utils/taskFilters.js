/**
 * 任务台状态筛选 SSOT。
 *
 * 这些分组是视图切面，不改变后端状态机：未知/新增状态仍计入「全部」，但不会
 * 被猜进某个既有语义组。特别地，cancelled 是中性终止，绝不并入 failed。
 */

import { TASK_WORK_STATES } from "./format.js";

export const TASK_FILTERS = Object.freeze([
  Object.freeze({ key: "all", label: "全部" }),
  Object.freeze({ key: "working", label: "执行中" }),
  Object.freeze({ key: "waiting_review", label: "待签发" }),
  Object.freeze({ key: "completed", label: "已完成" }),
  Object.freeze({ key: "failed", label: "失败" }),
  Object.freeze({ key: "cancelled", label: "已取消" }),
]);

const FILTER_KEYS = new Set(TASK_FILTERS.map(({ key }) => key));
export function taskMatchesFilter(task, filterKey) {
  if (!FILTER_KEYS.has(filterKey)) return false;
  if (filterKey === "all") return true;
  if (filterKey === "working") return TASK_WORK_STATES.has(task?.status);
  return task?.status === filterKey;
}

export function filterTasks(tasks, filterKey) {
  if (!Array.isArray(tasks)) return [];
  return tasks.filter((task) => taskMatchesFilter(task, filterKey));
}

export function countTasksByFilter(tasks) {
  const source = Array.isArray(tasks) ? tasks : [];
  const counts = {
    all: source.length,
    working: 0,
    waiting_review: 0,
    completed: 0,
    failed: 0,
    cancelled: 0,
  };

  for (const task of source) {
    for (const filter of TASK_FILTERS.slice(1)) {
      if (taskMatchesFilter(task, filter.key)) counts[filter.key] += 1;
    }
  }
  return counts;
}
