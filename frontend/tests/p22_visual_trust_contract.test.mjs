// P2.2 visual-trust debt: source contracts keep theme, trust-color, focus,
// reduced-motion, and narrow-layout fixes from drifting behind Element Plus.
import test from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";

const srcRoot = fileURLToPath(new URL("../src/", import.meta.url));
const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const app = read("../src/App.vue");
const format = read("../src/utils/format.js");
const guide = read("../src/views/GuidePage.vue");
const portal = read("../src/views/AgentPortal.vue");
const feedbackPage = read("../src/views/FeedbackPage.vue");
const taskDetail = read("../src/views/TaskDetail.vue");
const onboarding = read("../src/components/OnboardingCard.vue");
const statusCenter = read("../src/components/StatusCenter.vue");
const today = read("../src/views/TodayPage.vue");
const workbench = read("../src/views/WorkbenchSession.vue");
const delivery = read("../src/components/DeliveryCard.vue");
const workLog = read("../src/components/WorkLog.vue");
const simFloat = read("../src/components/SimMonitorFloat.vue");
const statusDock = read("../src/components/StatusDock.vue");
const quickSwitcher = read("../src/components/QuickSwitcher.vue");

function vueSources(dirPath = srcRoot) {
  const out = [];
  for (const entry of readdirSync(dirPath, { withFileTypes: true })) {
    const path = join(dirPath, entry.name);
    if (entry.isDirectory()) out.push(vueSources(path));
    else if (extname(entry.name) === ".vue") out.push(readFileSync(path, "utf8"));
  }
  return out.join("\n");
}

function hexRgb(hex) {
  const n = Number.parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function luminance(hex) {
  const channels = hexRgb(hex).map((v) => {
    const s = v / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

function tokenHex(block, token) {
  const value = block.match(new RegExp(`--${token}:\\s*(#[0-9a-fA-F]{6})`))?.[1];
  assert.ok(value, `missing literal color token --${token}`);
  return value;
}

function mediaBodies(source, condition) {
  const bodies = [];
  let cursor = 0;
  while (cursor < source.length) {
    const start = source.indexOf(`@media (${condition})`, cursor);
    if (start < 0) break;
    const open = source.indexOf("{", start);
    assert.ok(open >= 0, `missing media body for ${condition}`);
    let depth = 0;
    let end = open;
    for (; end < source.length; end += 1) {
      if (source[end] === "{") depth += 1;
      else if (source[end] === "}") {
        depth -= 1;
        if (depth === 0) break;
      }
    }
    assert.equal(depth, 0, `unbalanced media body for ${condition}`);
    bodies.push(source.slice(open + 1, end));
    cursor = end + 1;
  }
  return bodies;
}

function assertReducedRule(source, pattern, message) {
  assert.ok(
    mediaBodies(source, "prefers-reduced-motion: reduce").some((body) => pattern.test(body)),
    message,
  );
}

test("Element Plus semantic colors are a bridge to the five locked trust slots", () => {
  for (const [ep, token] of [
    ["success", "trust-real"],
    ["warning", "trust-pending"],
    ["danger", "trust-fail"],
    ["error", "trust-fail"],
    ["info", "ink-soft"],
  ]) {
    const matches = app.match(new RegExp(`--el-color-${ep}:\\s*var\\(--${token}\\)`, "g")) || [];
    assert.equal(matches.length, 1, `${ep} base color must have one trust-token SSOT`);
    for (const step of ["light-3", "light-5", "light-7", "light-8", "light-9", "dark-2"]) {
      const derived = app.match(new RegExp(`--el-color-${ep}-${step}:\\s*color-mix\\(in srgb, var\\(--${token}\\)`, "g")) || [];
      assert.equal(derived.length, 2, `${ep}-${step} must derive from the trust token in both theme blocks`);
    }
  }
  assert.doesNotMatch(app, /--el-color-(?:success|warning|danger|error|info):\s*#[0-9a-f]{6}/i);
});

test("ordinary confirmations and neutral completion never enter Element Plus success green", () => {
  const vue = vueSources();
  assert.doesNotMatch(vue, /ElMessage\.success\s*\(/);
  assert.doesNotMatch(vue, /(?:^|\s)type\s*=\s*["']success["']/);
  assert.doesNotMatch(vue, /\?\s*["']success["']\s*:\s*["']danger["']/);
  assert.match(statusCenter, /customClass:\s*["']trust-message-signed["']/);
  assert.match(app, /\.trust-message-signed\s*\{[\s\S]*?--el-message-text-color:\s*var\(--trust-signed\)/);
  assert.match(feedbackPage, /<el-alert v-if="feedbackError" type="error"/);
  assert.match(taskDetail, /<el-alert v-if="feedbackError" type="error"/);
  assert.match(portal, /if \(run\.status === "completed"\)[^\n]*[\s\S]*?else if \(run\.status !== "aborted"\) ElMessage\.error\(`/);
  assert.doesNotMatch(portal, /run\.status[^\n]*ElMessage\.warning/);
});

test("category identity colors are theme tokens with AA text contrast", () => {
  const light = app.match(/:root\s*\{([\s\S]*?)\n\}/)?.[1] || "";
  const dark = app.match(/:root\[data-theme=["']dark["']\]\s*\{([\s\S]*?)\n\}/)?.[1] || "";
  const categories = [
    "category-tool-automation",
    "category-knowledge-qa",
    "category-structured-gen",
    "category-reasoning-assist",
    "category-unknown",
  ];
  for (const token of categories) {
    assert.ok(contrast(tokenHex(light, token), "#ffffff") >= 4.5, `${token} light contrast`);
    assert.ok(contrast(tokenHex(dark, token), "#2e2823") >= 4.5, `${token} dark contrast`);
  }
  for (const token of categories) assert.match(format, new RegExp(`var\\(--${token}\\)`));
  assert.doesNotMatch(format, /color:\s*#[0-9a-f]{6}/i);
  assert.doesNotMatch(portal + workbench, /categoryColor\([^)]*\)\s*\+\s*["']18["']/);
});

test("timeline levels stay inside the neutral/pending/fail token contract", () => {
  assert.match(format, /LEVEL_COLOR\s*=\s*\{[\s\S]*?info:\s*["']var\(--ink-soft\)["']/);
  assert.match(format, /LEVEL_COLOR\s*=\s*\{[\s\S]*?warning:\s*["']var\(--trust-pending\)["']/);
  assert.match(format, /LEVEL_COLOR\s*=\s*\{[\s\S]*?error:\s*["']var\(--trust-fail\)["']/);
  assert.doesNotMatch(format, /LEVEL_COLOR\s*=\s*\{[^}]*#[0-9a-f]{6}/i);
});

test("focus rings use the global 2px token grammar", () => {
  for (const selector of ["intent-card", "reframe-item"]) {
    assert.match(
      guide,
      new RegExp(`\\.${selector}:focus-visible\\s*\\{[\\s\\S]*?outline:\\s*2px solid var\\(--focus-ring-clay\\);[\\s\\S]*?outline-offset:\\s*2px;[\\s\\S]*?\\}`),
    );
  }
});

test("every audited hover lift is static under reduced motion", () => {
  const cases = [
    [today, "today-card:hover"],
    [delivery, "delivery-card:hover"],
    [workbench, "member:hover"],
    [simFloat, "sim-pill:hover"],
    [statusDock, "dock-monitor:hover"],
  ];
  for (const [source, selector] of cases) {
    assertReducedRule(
      source,
      new RegExp(`\\.${selector.replace(/[.*+?^${}()|[\\]\\]/g, "\\$&")}\\s*\\{\\s*transform:\\s*none;`),
      `${selector} must clear transform in reduced motion`,
    );
  }
  for (const selector of ["intent-card:hover", "intent-card:focus-visible", "agent-cta:hover::after", "plan-escape:hover"]) {
    assertReducedRule(
      guide,
      new RegExp(`\\.${selector.replace(/[.*+?^${}()|[\\]\\]/g, "\\$&")}[^\\{]*\\{[^}]*transform:\\s*none;`),
      `${selector} must clear transform in reduced motion`,
    );
  }
  assertReducedRule(workLog, /\.worklog-arrow\s*\{\s*transition:\s*none;/, "worklog arrow must stop transitioning");
});

test("custom interactive rows expose Space and combobox semantics", () => {
  assert.match(guide, /class="sa-refusal-line"[\s\S]*?@keydown\.enter[^\n]*[\s\S]*?@keydown\.space/);
  assert.match(guide, /class="ap-item"[\s\S]*?@keydown\.enter[^\n]*[\s\S]*?@keydown\.space/);
  assert.match(guide, /<button type="button" class="chip-x"/);
  assert.match(guide, /<button type="button" class="ap-portal-link"/);
  assert.match(workbench, /class="rg-line rg-done"[\s\S]*?@keydown\.enter[^\n]*[\s\S]*?@keydown\.space/);
  assert.match(workbench, /<button type="button" class="task-chip-main" @click="goTask\(t\)">/);
  assert.doesNotMatch(workbench, /class="task-chip[^>]*role="button"/);
  assert.match(workbench, /<button[\s\S]*?v-for="t in otherTasks"[\s\S]*?type="button"[\s\S]*?:class="\['task-chip'/);
  assert.match(quickSwitcher, /role="combobox"[\s\S]*?:aria-activedescendant="activeOptionId"/);
  assert.match(quickSwitcher, /const activeOptionId\s*=\s*computed\(\(\)\s*=>\s*\{[\s\S]*?if\s*\(loading\.value\s*\|\|[\s\S]*?selectedIndex\.value\s*>=\s*flatItems\.value\.length\)/);
  assert.match(quickSwitcher, /class="qs-results"[^>]*role="listbox"/);
  assert.match(quickSwitcher, /class="qs-item"[\s\S]*?role="option"[\s\S]*?:aria-selected=/);
});

test("narrow surfaces wrap and the status drawer tracks live viewport width", () => {
  assert.match(portal, /minmax\(min\(280px,\s*100%\),\s*1fr\)/);
  assert.match(portal, /@media\s*\(max-width:\s*640px\)[\s\S]*?\.teams-header[^{]*\{[^}]*flex-wrap:\s*wrap;/);
  assert.match(portal, /@media\s*\(max-width:\s*640px\)[\s\S]*?\.seat-upload-item[^{]*\{[^}]*flex-wrap:\s*wrap;/);
  assert.match(onboarding, /\.ob-mobile-summary\s*\{\s*display:\s*none;/);
  assert.match(onboarding, /@media\s*\(max-width:\s*640px\)[\s\S]*?\.ob-mobile-summary\s*\{[^}]*display:\s*flex;/);
  assert.match(workbench, /@media\s*\(max-width:\s*640px\)[\s\S]*?\.rg-line[^{]*\{[^}]*flex-wrap:\s*wrap;/);
  assert.match(workbench, /@keydown\.space\.prevent="goTask\(latestTaskFor\(a\)\)"/);
  assert.match(statusCenter, /const viewportWidth\s*=\s*ref\(window\.innerWidth\)/);
  assert.match(statusCenter, /const drawerSize\s*=\s*computed\(\(\)\s*=>\s*viewportWidth\.value\s*<\s*640\s*\?\s*["']100%["']\s*:\s*["']540px["']\)/);
  assert.match(statusCenter, /window\.addEventListener\(["']resize["'],\s*syncViewportWidth\)/);
  assert.match(statusCenter, /window\.removeEventListener\(["']resize["'],\s*syncViewportWidth\)/);
});
