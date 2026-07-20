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
  assert.match(monitor, /data-agent-fact-focus-target/);
  assert.doesNotMatch(monitor, /data-agent-fact-task-id/);
  assert.doesNotMatch(monitor, /\{\{\s*(?:task|dependency)\.taskId\s*\}\}/);
  assert.match(center, /scrollIntoView\(\{ block: "nearest" \}\)/);
  assert.doesNotMatch(center, /<el-dialog[^>]*agent-monitor/i);
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
  assert.match(monitor, /agent-monitor-notice\.is-invalid\s*\{\s*color:\s*var\(--trust-pending\)/);
  assert.doesNotMatch(monitor, /agent-monitor-notice\.is-invalid\s*\{\s*color:\s*var\(--trust-fail\)/);
  assert.doesNotMatch(monitor, /runtime\.reason\s*===\s*"malformed"\)\)\s*return\s*"failure"/);
});
