// frontend/tests/branding.test.mjs — node --test，零框架依赖。
// 票 #62（map #46 批 2）品牌一致性锚：命名 SSOT 常量字面 / 散点接线 /
// 静态 title 同字面 / B6 政策句对齐 / B7 空态句号 / B9 agentDisplayName 降级。
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { PLATFORM_NAME, ASSISTANT_NAME, PLATFORM_SUBTITLE } from "../src/utils/branding.js";
import { agentDisplayName } from "../src/utils/format.js";

const read = (rel) => readFileSync(new URL(rel, import.meta.url), "utf8");
const appSource = read("../src/App.vue");
const guideSource = read("../src/views/GuidePage.vue");
const welcomeGateSource = read("../src/components/WelcomeGate.vue");
const todaySource = read("../src/views/TodayPage.vue");
const taskConsoleSource = read("../src/views/TaskConsole.vue");
const routerSource = read("../src/router/index.js");
const titleBadgeSource = read("../src/utils/titleBadge.js");
const featureMapSource = read("../src/components/FeatureAssetMapDisclosure.vue");
const indexHtml = read("../index.html");
const backendConfig = read("../../backend/app/config.py");
const backendMain = read("../../backend/app/main.py");

// ── B1：双名制常量字面锁定（owner 裁⑥⑦：FLAi-OS=平台 / FLAi=助手人格 /
//    「二所」副标保留）——改任何一个字母，本测试红。 ─────────────────────
test("B1 命名 SSOT 常量字面锁定（双名制+「二所」副标）", () => {
  assert.equal(PLATFORM_NAME, "FLAi-OS");
  assert.equal(ASSISTANT_NAME, "FLAi");
  assert.equal(PLATFORM_SUBTITLE, "二所工程智能体运行底座");
});

test("B1 命名散点全部接 SSOT，不再各写字面", () => {
  // 侧栏品牌名+副标
  assert.match(appSource, /<span class="brand-name">\{\{ PLATFORM_NAME \}\}<\/span>/);
  assert.match(appSource, /<span class="brand-sub">\{\{ PLATFORM_SUBTITLE \}\}<\/span>/);
  // 登录门标题+氛围面副标行
  assert.match(welcomeGateSource, /欢迎来到 \{\{ PLATFORM_NAME \}\}/);
  assert.match(welcomeGateSource, /\{\{ PLATFORM_SUBTITLE \}\}——任务在这里拆解、执行、留痕。/);
  // 助手气泡名/重述引导/响应口播/需求摘要来源行
  assert.match(guideSource, /<div class="ai-name">\{\{ ASSISTANT_NAME \}\}/);
  assert.match(guideSource, /告诉 \{\{ ASSISTANT_NAME \}\} 你想怎么调整/);
  assert.match(guideSource, /`\$\{ASSISTANT_NAME\} 正在响应…`/);
  assert.match(guideSource, /`\（来自 \$\{PLATFORM_NAME\} 导引对话——请平台负责人评估排期\）`/);
  // 运行时 title 合成与徽章写手同源
  assert.match(routerSource, /`\$\{to\.meta\.title\} · \$\{PLATFORM_NAME\}`/);
  assert.match(titleBadgeSource, /let base = PLATFORM_NAME/);
  // 功能与资产地图标题/aria
  assert.match(featureMapSource, /:aria-label="`\$\{PLATFORM_NAME\} 功能与资产地图`"/);
  assert.match(featureMapSource, /<strong>\{\{ PLATFORM_NAME \}\} 功能与资产地图<\/strong>/);
});

test("B1 静态 title 补「二所」且与 SSOT 同字面（无法 import，锚锁同批纪律）", () => {
  assert.match(indexHtml, /<title>FLAi-OS 二所工程智能体运行底座<\/title>/);
  assert.ok(indexHtml.includes(PLATFORM_NAME) && indexHtml.includes(PLATFORM_SUBTITLE));
});

test("B1 后端 FastAPI title 走 config.APP_NAME，与前端 SSOT 同字面", () => {
  assert.match(backendConfig, /APP_NAME = "FLAi-OS"/);
  assert.match(backendMain, /title=f"\{config\.APP_NAME\} Backend"/);
});

// ── B6（owner 裁：composer 对齐 hero 口径）——方案卡 :463 政策句逐字锁
//    （m6③ 红线锚）不在此测试复述，由 m6_guide_acceptance.py 逐字锚看管。 ──
test("B6 hero 与 composer 政策句同口径「后台安排所需能力」", () => {
  assert.match(guideSource, /输入文字或上传附件，系统会在后台安排所需能力。/);
  assert.match(guideSource, /"系统会在后台安排所需能力 · 开始与放行由你确认"/);
  assert.doesNotMatch(guideSource, /后台准备方案/);
});

// ── B7：空态句号微规则（TYPOGRAPHY-NOTES.md §4）——唯一带句号残留已收口。 ──
test("B7 空态描述不带句号（cl-zero 收口锚）", () => {
  assert.match(taskConsoleSource, /还没有任务——先在主对话里说明目标，系统会自动安排</);
  assert.doesNotMatch(taskConsoleSource, /系统会自动安排。</);
});

// ── B9（owner 裁：agentDisplayName SSOT）────────────────────────────────
test("B9 agentDisplayName：名册注册名优先，缺位诚实回落原 agent_id", () => {
  const names = { cfd_perf: "性能盘计算" };
  assert.equal(agentDisplayName("cfd_perf", names), "性能盘计算");
  // 缺位三态：查无此 agent / 名册为空 / 名册缺位——一律回原 id，不编名字。
  assert.equal(agentDisplayName("unknown_agent", names), "unknown_agent");
  assert.equal(agentDisplayName("cfd_perf", {}), "cfd_perf");
  assert.equal(agentDisplayName("cfd_perf", null), "cfd_perf");
  // 双闸（同 taskDisplayName）：原型键/非字符串注册名不捞出。
  assert.equal(agentDisplayName("constructor", names), "constructor");
  assert.equal(agentDisplayName("cfd_perf", { cfd_perf: 42 }), "cfd_perf");
  assert.equal(agentDisplayName("cfd_perf", { cfd_perf: "" }), "cfd_perf");
  // 空 id 兜底「—」（与 format 族诚实降级同律）。
  assert.equal(agentDisplayName("", names), "—");
  assert.equal(agentDisplayName(undefined, names), "—");
});

test("B9 七处副行接 agentDisplayName 且原 id 收 title 悬浮", () => {
  // 今日页 4 处：待签/进行中副行 + 晋升行 + 最活跃 chip
  assert.equal((todaySource.match(/agentDisplayName\(/g) || []).length, 4);
  assert.match(todaySource, /class="today-card-sub" :title="t\.agent_id"/);
  assert.match(todaySource, /class="today-promo-main" :title="p\.agent_id"/);
  assert.match(todaySource, /class="today-active-chip" :title="a\.agent_id"/);
  // 任务台 3 处：待签/进行中/已落定副行
  assert.equal((taskConsoleSource.match(/agentDisplayName\(/g) || []).length, 3);
  assert.equal((taskConsoleSource.match(/class="cl-sub" :title="t\.agent_id"/g) || []).length, 3);
  // 副行不再裸拼 agent_id 字面到可见文本
  assert.doesNotMatch(todaySource, /today-card-sub">\{\{ t\.agent_id \}\}/);
  assert.doesNotMatch(taskConsoleSource, /cl-sub">\{\{ t\.agent_id \}\}/);
});

// ── B11：窄屏登录门副标——<900px 补一行，≥900px 隐去（版式纪律同 Q5a）。 ──
test("B11 窄屏登录门副标在场且宽屏隐去", () => {
  assert.match(welcomeGateSource, /<p class="welcome-gate__subtitle">\{\{ PLATFORM_SUBTITLE \}\}<\/p>/);
  assert.match(
    welcomeGateSource,
    /@media \(min-width: 900px\) \{[\s\S]*\.welcome-gate__subtitle \{\s*display: none;\s*\}/,
  );
});
