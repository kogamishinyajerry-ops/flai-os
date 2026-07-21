import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

test("conversation live snapshot carries one canonical Agent fact projection", () => {
  const api = read("../src/api/conversations.js");
  const feed = read("../src/stores/liveFeed.js");

  assert.match(api, /\/agent-facts/);
  assert.match(feed, /agentFacts:\s*ref\(null\)/);
  assert.match(feed, /getConversationAgentFacts\(convId\)/);
  assert.match(feed, /ch\.state\.agentFacts\.value\s*=\s*agentFacts/);
  assert.match(feed, /agentFactRuntimeFloors\s*=\s*new Map\(\)/);
  assert.match(feed, /evaluateAgentFactContinuity\([^)]*ch\.agentFactRuntimeFloors/s);
  assert.match(feed, /advanceAgentFactRuntimeFloors\(ch\.agentFactRuntimeFloors, agentFacts\)/);
  assert.match(feed, /applyConnection\(ch\.state, \{ type: "resync", error: continuity\.reason \}\)/);
  assert.match(feed, /完整 Agent 事实快照校验失败/);
});

test("the existing right drawer owns the on-demand monitor workspace", () => {
  const store = read("../src/stores/statusCenter.js");
  const center = read("../src/components/StatusCenter.vue");
  const monitor = read("../src/components/AgentMonitorView.vue");

  assert.match(store, /view:\s*"inbox"[^]*'monitor'/);
  assert.match(store, /export function openAgentMonitor\(conversationId, focusTaskId = null\)/);
  assert.match(store, /export function backFromTaskPeek\(\)/);
  assert.match(store, /peekReturnConversationId/);
  assert.match(store, /peekReturnTaskId/);
  assert.match(center, /AgentMonitorView/);
  assert.match(center, /statusCenter\.view === ["']monitor["']/);
  assert.match(center, /openTaskPeek/);
  assert.match(center, /acquireChannel\(`conversation:\$\{conversationId\}`\)/);
  assert.match(center, /statusCenter\.view === "monitor" \? "360px" : "540px"/);
  assert.match(center, /@media\s*\(max-width:\s*640px\)[^]*\.sc-back,[^]*\.sc-close\s*\{[^}]*width:\s*44px;[^}]*height:\s*44px;/);
  assert.match(center, /\.sc-back:focus-visible,[^]*\.sc-close:focus-visible/);
  assert.match(center, /返回 Agent 运行监控/);
  assert.match(center, /const peekTitle = computed/);
  assert.doesNotMatch(center, /sc-title-task[^\n]*taskId\?\.slice/);
  assert.doesNotMatch(center, /\{\{\s*t\.agent_id\s*\}\}/);
  assert.doesNotMatch(center, /\{\{\s*peekTask\.agent_id\s*\}\}/);
  assert.match(monitor, /data-agent-fact-focus-target/);
  assert.doesNotMatch(monitor, /data-agent-fact-task-id/);
  assert.doesNotMatch(monitor, /\{\{\s*(?:task|dependency)\.taskId\s*\}\}/);
  assert.match(center, /scrollIntoView\(\{ block: "nearest" \}\)/);
  assert.doesNotMatch(center, /<el-dialog[^>]*agent-monitor/i);
  assert.match(center, /employeeTaskLabel\(t\)/);
  assert.doesNotMatch(center, /taskDisplayName\(t, agentNames\.map\)/);
});

test("ordinary task surfaces hide runtime brands and internal handles", () => {
  const center = read("../src/components/StatusCenter.vue");
  const detail = read("../src/views/TaskDetail.vue");

  assert.match(center, /const employeeTaskLabel = \(task\) =>/);
  assert.match(detail, /const taskAgentLabel = computed/);
  assert.match(detail, /const taskTitle = computed/);
  assert.doesNotMatch(detail, /\{\{\s*task\.agent_id\s*\}\}/);
  assert.doesNotMatch(detail, /\{\{\s*task\.retry_of\s*\}\}/);
  assert.doesNotMatch(detail, /out\.push\(\{\s*id,\s*name:\s*id\.slice\(/);
  assert.match(detail, /重跑自 上次失败任务/);
  assert.doesNotMatch(detail, /<el-descriptions-item label="Agent ID">/);
  assert.doesNotMatch(detail, /<el-descriptions-item label="ID">\{\{\s*task\.id/);
});

test("the guide keeps one compact fact card and opens the same monitor", () => {
  const guide = read("../src/views/GuidePage.vue");

  assert.match(guide, /<AgentFactSummary/);
  assert.match(guide, /:snapshot="conversationAgentFacts"/);
  assert.match(guide, /@open="openConversationAgentMonitor"/);
  assert.match(guide, /openAgentMonitor\(conversationId\.value\)/);
  assert.doesNotMatch(guide, /sa-shimmer|work-pulse-dot|is-pulsing/);
});

test("monitor motion and trust colors stay inside the existing semantic slots", () => {
  const summary = read("../src/components/AgentFactSummary.vue");
  const monitor = read("../src/components/AgentMonitorView.vue");
  const combined = `${summary}\n${monitor}`;

  assert.match(combined, /prefers-reduced-motion:\s*reduce/);
  assert.match(combined, /var\(--clay\)/);
  assert.match(combined, /var\(--trust-pending\)/);
  assert.match(combined, /var\(--trust-signed\)/);
  assert.match(combined, /var\(--trust-fail\)/);
  assert.doesNotMatch(combined, /#[0-9a-fA-F]{3,8}\b/);
  assert.doesNotMatch(combined, /success|var\(--trust-real\)/i);
  assert.match(summary, /settled:\s*Minus/);
  assert.match(monitor, /关闭监控栏不会停止服务端任务/);
  assert.match(monitor, /v-if="!loaded && errorText"/);
  assert.match(monitor, /agent-monitor-subagent-history/);
  assert.match(summary, /Agent 事实首次读取失败/);
  assert.match(summary, /!props\.loaded\s*&&\s*!!errorText\.value/);
  assert.match(summary, /const emptyUnverified = computed/);
  assert.match(summary, /projection\.value\.unavailableRuntimeCount > 0/);
  assert.match(summary, /if \(coldError\.value\) return "unknown"/);
  assert.match(monitor, /agent-monitor-notice\.is-invalid[^}]*color:\s*var\(--ink-soft\)[^}]*border-inline-start-color:\s*var\(--trust-pending\)/s);
  assert.doesNotMatch(monitor, /agent-monitor-notice\.is-invalid\s*\{\s*color:\s*var\(--trust-fail\)/);
  assert.doesNotMatch(monitor, /runtime\.reason\s*===\s*"malformed"\)\)\s*return\s*"failure"/);
});

test("monitor has a named dialog and progressively discloses dense task facts", () => {
  const center = read("../src/components/StatusCenter.vue");
  const monitor = read("../src/components/AgentMonitorView.vue");
  const summary = read("../src/components/AgentFactSummary.vue");

  assert.match(center, /aria-labelledby="status-center-drawer-title"/);
  assert.match(center, /id="status-center-drawer-title"/);
  assert.match(center, /class="sc-head"\s*:class="\{ 'is-monitor': statusCenter\.view === 'monitor' \}"/);
  assert.match(center, /\.sc-head\.is-monitor[^}]*grid-template-columns:\s*minmax\(0, 1fr\) auto/s);
  assert.match(monitor, /class="agent-monitor-facts"/);
  assert.match(monitor, /:open="shouldExpandTask\(task\)"/);
  assert.match(monitor, /taskDisclosureLabel\(task\)/);
  assert.match(monitor, /focusTaskId === task\.taskId[^]*task\.phase === "failed"[^]*task\.signoff\.state === "awaiting_human"/);
  assert.match(monitor, /agent-monitor-completed-row[^]*`tone-\$\{taskTone\(task\)\}`/);
  assert.match(monitor, /\.agent-monitor-completed-row\.tone-signed[^}]*border-inline-start-color:\s*var\(--trust-signed\)/s);

  // Semantic slots stay on icons, rails and borders; ordinary small copy uses
  // the readable ink tier instead of sub-AA decorative color tokens.
  assert.match(summary, /\.agent-fact-meta,[^}]*color:\s*var\(--ink-soft\)/s);
  assert.match(monitor, /\.agent-monitor-runtime\.tone-waiting[^}]*color:\s*var\(--ink-soft\)/s);
  assert.match(monitor, /\.agent-monitor-signoff\.tone-signed[^}]*border-inline-start-color:\s*var\(--trust-signed\)/s);
});
