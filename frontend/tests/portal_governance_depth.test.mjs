/**
 * 批次 A+C（门户能力发现 + 治理/评测/晋升）深度打磨的回归网。
 *
 * 只补 core_visuals.test.mjs 未覆盖的新语义：
 * - 能力地图关系派生（可用 Agent / 适用边界 / 发起方式）的 fail-closed 分支；
 * - 评测通过率趋势点（buildEvalTrend）的严格 REAL / 诚实降级；
 * - 治理闭环步骤的阅读顺序契约。
 * 既有 fail-closed 断言（core_visuals.test.mjs）不重复、不削弱。
 */
import test from "node:test";
import assert from "node:assert/strict";

import { buildPortalCategoryOverview } from "../src/utils/portalVisual.js";
import {
  buildEvalTrend,
  buildGovernanceJourney,
} from "../src/utils/governanceJourney.js";

test("能力地图：非数组输入仍是形状未知，关系字段不编造", () => {
  const overview = buildPortalCategoryOverview("not-an-array");
  assert.equal(overview.available, false);
  assert.equal(overview.unknownCount, null);
  assert.deepEqual(overview.items, []);
});

test("能力地图：边界计数真实派生——limitations 非数组记待核，绝不压成 0", () => {
  const overview = buildPortalCategoryOverview([
    { id: "a1", name: "甲", category: "tool_automation", mode: "task", limitations: ["x", "y"] },
    { id: "a2", name: "乙", category: "tool_automation", mode: "task", limitations: "broken" },
    { id: "a3", name: "丙", category: "knowledge_qa", mode: "task" }, // limitations 缺失
    { id: "a4", name: "丁", category: "structured_gen", mode: "task", limitations: [] },
  ]);
  const byId = Object.fromEntries(overview.items.map((item) => [item.id, item]));

  // 同类内任一 agent 边界字段畸形 → 整个分类边界待核（fail-closed）
  assert.equal(byId.tool_automation.boundaryCount, null);
  // limitations 缺失同样不得当成「已声明零边界」
  assert.equal(byId.knowledge_qa.boundaryCount, null);
  // 空数组是如实声明「无不适用边界」，与待核严格区分
  assert.equal(byId.structured_gen.boundaryCount, 0);
  // 完全无成员的分类不计数、不标待核
  assert.equal(byId.reasoning_assist.boundaryCount, null);
  assert.equal(byId.reasoning_assist.count, 0);
});

test("能力地图：发起方式只认服务端明确投影，未知 mode 记待核不回退", () => {
  const overview = buildPortalCategoryOverview([
    { id: "a1", name: "甲", category: "tool_automation", mode: "interactive", limitations: [] },
    { id: "a2", name: "乙", category: "tool_automation", mode: "task", limitations: [] },
    { id: "a3", name: "丙", category: "knowledge_qa", limitations: [] }, // mode 缺失
    { id: "a4", name: "丁", category: "structured_gen", mode: 42, limitations: [] }, // 畸形 mode
  ]);
  const byId = Object.fromEntries(overview.items.map((item) => [item.id, item]));

  assert.deepEqual(byId.tool_automation.launch, { chat: 1, task: 1, unknown: 0 });
  assert.deepEqual(byId.knowledge_qa.launch, { chat: 0, task: 0, unknown: 1 });
  assert.deepEqual(byId.structured_gen.launch, { chat: 0, task: 0, unknown: 1 });
});

test("能力地图：可用 Agent 名单 name 优先 id 兜底，双缺不崩溃；未知分类不混入已知类", () => {
  const overview = buildPortalCategoryOverview([
    { id: "a1", name: "甲", category: "tool_automation", mode: "task", limitations: [] },
    { id: "a2", category: "tool_automation", mode: "task", limitations: [] }, // name 缺失
    { category: "tool_automation", mode: "task", limitations: [] }, // name/id 双缺
    { id: "x1", name: "未分类", category: "brand_new", mode: "task", limitations: [] },
    null, // 畸形条目
  ]);
  const tool = overview.items.find((item) => item.id === "tool_automation");
  assert.equal(tool.count, 3);
  assert.deepEqual(tool.members, ["甲", "a2", "未具名"]);
  // 未知分类与畸形条目只进 unknownCount，绝不塞进任何已知分类
  assert.equal(overview.unknownCount, 2);
});

test("评测趋势：畸形 run 被剔除，未知计数绝不压成 0 或假绿", () => {
  const runs = [
    { id: "bad-1", status: "completed", total: 3, passed: 3, failed: 0, skipped: 0, case_results: [] }, // 明细未对上
    { id: "bad-2", status: "completed", total: "3", passed: 3, failed: 0, skipped: 0, case_results: [] }, // 字段待核
    { id: "run-err", status: "error" },
    { id: "run-run", status: "running" },
    { id: "ok-pass", status: "completed", total: 2, passed: 2, failed: 0, skipped: 0, case_results: [{ verdict: "passed" }, { verdict: "passed" }], finished_at: "2026-07-30T10:00:00Z" },
    { id: "ok-empty", status: "completed", total: 0, passed: 0, failed: 0, skipped: 0, case_results: [], finished_at: "2026-07-29T10:00:00Z" },
  ];
  const trend = buildEvalTrend(runs);
  // 只有字段与明细严格对上的已完成跑批入图
  assert.deepEqual(trend.map((point) => point.id), ["ok-empty", "ok-pass"]); // 旧→新
  const empty = trend.find((point) => point.id === "ok-empty");
  assert.equal(empty.pct, null); // 无有效用例不画 0%
  assert.equal(empty.tone, "neutral");
  const pass = trend.find((point) => point.id === "ok-pass");
  assert.equal(pass.pct, 100);
  assert.equal(pass.tone, "real"); // 严格全通过才可给绿
});

test("评测趋势：含失败标红、含跳过标 amber，非数组输入安全降级为空", () => {
  const trend = buildEvalTrend([
    { id: "r-fail", status: "completed", total: 2, passed: 1, failed: 1, skipped: 0, case_results: [{ verdict: "passed" }, { verdict: "failed" }] },
    { id: "r-skip", status: "completed", total: 2, passed: 1, failed: 0, skipped: 1, case_results: [{ verdict: "passed" }, { verdict: "skipped" }] },
  ]);
  assert.equal(trend.find((point) => point.id === "r-fail").tone, "fail");
  assert.equal(trend.find((point) => point.id === "r-skip").tone, "pending");
  assert.deepEqual(buildEvalTrend(null), []);
  assert.deepEqual(buildEvalTrend("junk"), []);
});

test("评测趋势：窗口上限生效且保留最新（先切头部再反转）", () => {
  const mk = (i) => ({
    id: `run-${i}`,
    status: "completed",
    total: 1,
    passed: 1,
    failed: 0,
    skipped: 0,
    case_results: [{ verdict: "passed" }],
  });
  const runs = Array.from({ length: 10 }, (_, i) => mk(i)); // runs[0] 最新
  const trend = buildEvalTrend(runs);
  assert.equal(trend.length, 8);
  assert.deepEqual(trend[0].id, "run-7"); // 最旧在左
  assert.deepEqual(trend[trend.length - 1].id, "run-0"); // 最新在右
});

test("治理闭环：六步阅读顺序契约（用例→调度→结果→确认→准入→晋升）", () => {
  const steps = buildGovernanceJourney({ maturity: "L0" });
  assert.deepEqual(
    steps.map((step) => step.id),
    ["cases", "dispatch", "result", "confirmation", "gate", "promotion"],
  );
});
