<template>
  <section class="agent-monitor" :aria-busy="resyncing ? 'true' : 'false'">
    <header class="agent-monitor-head">
      <span class="agent-monitor-icon" aria-hidden="true"><el-icon><DataAnalysis /></el-icon></span>
      <span class="agent-monitor-head-copy">
        <strong>运行事实</strong>
        <span v-if="summary.valid && summary.renderable">
          {{ taskScopeMeta }} · {{ subagentMeta }}
        </span>
        <span v-else>{{ connectionLabel }}</span>
      </span>
      <span v-if="summary.valid && summary.renderable" class="agent-monitor-state" :class="`tone-${headerTone}`">
        {{ summary.headline }}
      </span>
    </header>

    <p class="agent-monitor-persistence">关闭监控栏不会停止服务端任务；返回会话可继续查看。</p>

    <div v-if="!loaded && errorText" class="agent-monitor-notice is-invalid" role="alert">
      <strong>Agent 事实首次读取失败</strong>
      <span>{{ errorText }}</span>
      <button type="button" @click="emit('retry')">重试</button>
    </div>

    <div v-else-if="!loaded" class="agent-monitor-notice" role="status">
      <span>正在读取 Agent 事实</span>
    </div>

    <div v-else-if="!validation.valid" class="agent-monitor-notice is-invalid" role="alert">
      <strong>Agent 事实不可渲染</strong>
      <span>{{ validation.error }}</span>
      <button type="button" @click="emit('retry')">重新获取</button>
    </div>

    <div
      v-else-if="!groups.renderable"
      class="agent-monitor-notice"
      :class="{ 'is-pending': stale || resyncing || errorText }"
      role="status"
    >
      <strong v-if="stale || resyncing || errorText">连接尚未核实</strong>
      <span>当前保留的完整快照没有 Agent 任务事实</span>
      <button v-if="stale || resyncing || errorText" type="button" @click="emit('retry')">立即重试</button>
    </div>

    <template v-else>
      <div v-if="stale || resyncing || errorText" class="agent-monitor-sync" role="status">
        <span v-if="resyncing">正在重新同步；下列内容保持为上次完整快照。</span>
        <span v-else>连接尚未核实；下列内容来自上次完整快照。</span>
        <button type="button" @click="emit('retry')">立即重试</button>
      </div>

      <section
        v-for="group in expandedGroups"
        :key="group.key"
        class="agent-monitor-group"
        :aria-labelledby="`agent-fact-${group.key}`"
      >
        <h3 :id="`agent-fact-${group.key}`">
          {{ group.label }} <span>{{ group.count }}</span>
        </h3>

        <article
          v-for="task in group.tasks"
          :key="task.taskId"
          class="agent-monitor-task"
          :class="[{ 'is-focused': focusTaskId === task.taskId }, `tone-${taskTone(task)}`]"
        >
          <button
            type="button"
            class="agent-monitor-task-head"
            :data-agent-fact-focus-target="focusTaskId === task.taskId ? 'true' : null"
            :aria-label="`检视 ${taskLabel(task)}的运行事实`"
            @click="emit('inspect', task.taskId)"
          >
            <span class="agent-monitor-task-main">
              <strong>{{ taskLabel(task) }}</strong>
              <span>{{ phaseLabel(task.phase) }} · {{ statusLabel(task.status) }}</span>
            </span>
            <span class="agent-monitor-duration">历时 {{ durationText(task) }}</span>
          </button>

          <div class="agent-monitor-detail">
            <div v-if="task.dependencies.length" class="agent-monitor-fact-block">
              <span class="agent-monitor-label">依赖</span>
              <span v-for="dependency in task.dependencies" :key="dependency.taskId" class="agent-monitor-fact-line">
                {{ agentLabel(dependency.agentId, "上游 Agent") }} · {{ dependencyGateLabel(dependency.gate) }}
              </span>
            </div>

            <div v-if="task.wait || task.signoff.state === 'awaiting_human'" class="agent-monitor-fact-block tone-waiting">
              <span class="agent-monitor-label">等待</span>
              <strong>{{ waitView(task).label }}</strong>
              <span v-if="waitView(task).detail" class="agent-monitor-fact-line">{{ waitView(task).detail }}</span>
              <span v-if="waitView(task).continueWhen" class="agent-monitor-fact-line">继续条件：{{ waitView(task).continueWhen }}</span>
            </div>

            <div v-if="task.handoffs.length" class="agent-monitor-fact-block">
              <span class="agent-monitor-label">接力</span>
              <span
                v-for="handoff in task.handoffs"
                :key="`${handoff.fromTaskId}:${handoff.toTaskId}:${handoff.at}`"
                class="agent-monitor-fact-line"
                :title="`${handoffAgent(handoff.fromTaskId, '上游任务')} → ${handoffAgent(handoff.toTaskId, '下游任务')}`"
              >
                {{ handoffAgent(handoff.fromTaskId, "上游任务") }} → {{ handoffAgent(handoff.toTaskId, "下游任务") }} · {{ clockText(handoff.at) }}
              </span>
            </div>

            <div class="agent-monitor-signoff" :class="`tone-${signoffTone(task.signoff)}`">
              <span class="agent-monitor-label">签发</span>
              <span>{{ signoffText(task.signoff) }}</span>
            </div>

            <div
              v-if="task.runtime.reported === false && task.runtime.reason !== 'not_applicable'"
              class="agent-monitor-runtime"
              :class="`tone-${runtimeReasonTone(task.runtime.reason)}`"
            >
              运行事实：{{ runtimeReasonLabel(task.runtime.reason) }}
            </div>

            <div v-if="task.runtime.subagentCount > 0" class="agent-monitor-subagents">
              <span class="agent-monitor-label">
                子智能体 {{ task.runtime.subagentCount }}<template v-if="task.runtime.subagentsTruncated">（列表已截断）</template>
              </span>
              <span v-for="subagent in activeOrFailedSubagents(task)" :key="subagent.ordinal" class="agent-monitor-subagent">
                <span>#{{ subagent.ordinal }}</span>
                <span>{{ subagentStatusLabel(subagent.status) }}</span>
                <span v-if="subagent.retryOfOrdinal !== null">重试自 #{{ subagent.retryOfOrdinal }}</span>
              </span>
              <details v-if="settledSubagents(task).length" class="agent-monitor-subagent-history">
                <summary>已落定子智能体 · {{ settledSubagents(task).length }}</summary>
                <span v-for="subagent in settledSubagents(task)" :key="subagent.ordinal" class="agent-monitor-subagent">
                  <span>#{{ subagent.ordinal }}</span>
                  <span>{{ subagentStatusLabel(subagent.status) }}</span>
                  <span v-if="subagent.retryOfOrdinal !== null">重试自 #{{ subagent.retryOfOrdinal }}</span>
                </span>
              </details>
              <span v-if="unreturnedSubagentCount(task) > 0" class="agent-monitor-runtime">
                另有 {{ unreturnedSubagentCount(task) }} 个子智能体未包含在当前有界窗口。
              </span>
            </div>
          </div>
        </article>

        <details
          v-if="group.key === 'settled' && completedTasks.length"
          class="agent-monitor-completed"
          :open="completedTasks.some((task) => focusTaskId === task.taskId)"
        >
          <summary>完成与取消 · {{ completedTasks.length }}</summary>
          <button
            v-for="task in completedTasks"
            :key="task.taskId"
            type="button"
            class="agent-monitor-completed-row"
            :data-agent-fact-focus-target="focusTaskId === task.taskId ? 'true' : null"
            :class="{ 'is-focused': focusTaskId === task.taskId }"
            @click="emit('inspect', task.taskId)"
          >
            <span>
              <strong>{{ taskLabel(task) }}</strong>
              <small>{{ statusLabel(task.status) }}</small>
              <small :class="`tone-${signoffTone(task.signoff)}`">{{ signoffText(task.signoff) }}</small>
            </span>
            <span>历时 {{ durationText(task) }}</span>
          </button>
        </details>
      </section>

      <p v-if="snapshot.tasksTruncated" class="agent-monitor-scope">
        当前显示 {{ snapshot.tasks.length }} / {{ snapshot.taskCount }} 个最近任务；列表已截断。
      </p>
    </template>
  </section>
</template>

<script setup>
import { computed } from "vue";
import { DataAnalysis } from "@element-plus/icons-vue";

import { formatDuration } from "../utils/format.js";
import { useAgentNames } from "../stores/agentNames.js";
import {
  groupMonitorTasks,
  summarizeAgentFacts,
  validateAgentFactSnapshot,
  waitPresentation,
} from "../utils/agentFactProjection.js";

defineOptions({ inheritAttrs: false });

const props = defineProps({
  snapshot: { type: Object, default: null },
  loaded: { type: Boolean, default: false },
  connection: { type: String, default: "idle" },
  stale: { type: Boolean, default: false },
  resyncing: { type: Boolean, default: false },
  error: { type: [String, Object], default: "" },
  focusTaskId: { type: String, default: null },
});

const emit = defineEmits(["inspect", "retry"]);
const agentNames = useAgentNames();

const emptyInvalid = { valid: false, renderable: false, error: "尚无 Agent 事实快照" };
const validation = computed(() => props.snapshot
  ? validateAgentFactSnapshot(props.snapshot)
  : emptyInvalid);
const groups = computed(() => validation.value.valid
  ? groupMonitorTasks(props.snapshot)
  : validation.value);
const summary = computed(() => validation.value.valid
  ? summarizeAgentFacts(props.snapshot, null, Date.now())
  : validation.value);
const errorText = computed(() => typeof props.error === "string"
  ? props.error
  : props.error?.message || "");
const headerTone = computed(() => {
  if (!summary.value.valid) return "waiting";
  if (props.stale || props.resyncing || errorText.value) return "waiting";
  if (props.snapshot?.tasks?.some((task) => task.runtime.reason === "malformed")) return "waiting";
  if (summary.value.unavailableRuntimeCount > 0) return "waiting";
  return summary.value.state;
});
const taskScopeMeta = computed(() => summary.value.tasksTruncated
  ? `最近 ${summary.value.taskCount} / 共 ${summary.value.totalTaskCount} 个任务`
  : `${summary.value.taskCount} 个任务`);
const subagentMeta = computed(() => {
  if (!summary.value.valid) return "子智能体事实不可用";
  if (summary.value.applicableRuntimeCount === 0) return "当前任务不适用子智能体事实";
  if (summary.value.reportedRuntimeCount === 0) {
    return `${summary.value.unavailableRuntimeCount} 个运行源未报告`;
  }
  const base = `已报告 ${summary.value.subagentCount} 个子智能体`;
  return summary.value.unavailableRuntimeCount > 0
    ? `${base} · ${summary.value.unavailableRuntimeCount} 个运行源未报告`
    : base;
});
const agentByTaskId = computed(() => validation.value.valid
  ? new Map(props.snapshot.tasks.map((task) => [task.taskId, taskLabel(task)]))
  : new Map());
const taskOrdinalById = computed(() => validation.value.valid
  ? new Map(props.snapshot.tasks.map((task, index) => [task.taskId, index + 1]))
  : new Map());

const failedTasks = computed(() => groups.value.valid
  ? groups.value.settled.filter((task) => task.phase === "failed" || task.signoff.state === "rejected")
  : []);
const completedTasks = computed(() => groups.value.valid
  ? groups.value.settled.filter((task) => task.phase !== "failed" && task.signoff.state !== "rejected")
  : []);
const expandedGroups = computed(() => {
  if (!groups.value.valid) return [];
  return [
    { key: "current", label: "当前", tasks: groups.value.current, count: groups.value.current.length },
    { key: "waiting", label: "等待", tasks: groups.value.waiting, count: groups.value.waiting.length },
    { key: "settled", label: "已落定", tasks: failedTasks.value, count: groups.value.settled.length },
  ].filter((group) => group.tasks.length > 0 || (group.key === "settled" && completedTasks.value.length > 0));
});

const connectionLabel = computed(() => ({
  idle: "等待连接",
  connecting: "正在连接",
  connected: "连接正常",
  live: "连接正常",
  polling: "正在核对",
  disconnected: "连接中断",
  error: "连接失败",
})[props.connection] || "连接状态待核");

const TASK_STATUS_LABELS = {
  created: "已创建",
  queued: "排队中",
  validating: "校验中",
  running: "运行中",
  waiting_review: "等待人工审核",
  parsing: "解析中",
  analyzing: "分析中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

const PHASE_LABELS = {
  waiting_upstream: "等待接力",
  queued: "待运行",
  working: "正在工作",
  awaiting_signoff: "等待签发",
  settled: "已落定",
  failed: "运行失败",
  cancelled: "已取消",
};

const DEPENDENCY_GATE_LABELS = {
  human_signed: "已由人工签发",
  deterministic_provenance: "确定性来源已核",
  pending: "尚未满足",
  failed: "依赖失败",
  unknown: "依赖状态不可用",
};

const RUNTIME_REASON_LABELS = {
  not_applicable: "不适用",
  disabled: "运行桥已停用",
  unreachable: "运行桥不可达",
  not_found: "未找到运行记录",
  malformed: "运行事实格式非法",
  reported: "已报告",
};

const SUBAGENT_STATUS_LABELS = {
  queued: "排队中",
  running: "运行中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
  interrupted: "已中断",
};

function statusLabel(status) {
  return TASK_STATUS_LABELS[status];
}

function phaseLabel(phase) {
  return PHASE_LABELS[phase];
}

function dependencyGateLabel(gate) {
  return DEPENDENCY_GATE_LABELS[gate];
}

function runtimeReasonLabel(reason) {
  return RUNTIME_REASON_LABELS[reason];
}

function runtimeReasonTone(reason) {
  if (reason !== "not_applicable" && reason !== "reported") return "waiting";
  return "neutral";
}

function subagentStatusLabel(status) {
  return SUBAGENT_STATUS_LABELS[status];
}

function activeOrFailedSubagents(task) {
  return task.runtime.subagents.filter((subagent) => (
    subagent.status === "queued"
    || subagent.status === "running"
    || subagent.status === "failed"
    || subagent.status === "interrupted"
  ));
}

function settledSubagents(task) {
  return task.runtime.subagents.filter((subagent) => (
    subagent.status === "completed"
    || subagent.status === "cancelled"
  ));
}

function unreturnedSubagentCount(task) {
  return Math.max(0, task.runtime.subagentCount - task.runtime.subagents.length);
}

function agentLabel(agentId, fallback = "未命名 Agent") {
  return Object.hasOwn(agentNames.map, agentId) ? agentNames.map[agentId] : fallback;
}

function taskLabel(task) {
  return agentLabel(task.agentId, `Agent 任务 ${taskOrdinalById.value.get(task.taskId) || ""}`.trim());
}

function handoffAgent(taskId, fallback) {
  return agentByTaskId.value.get(taskId) || fallback;
}

function taskTone(task) {
  if (task.phase === "failed" || task.signoff.state === "rejected") return "failure";
  if (task.wait || task.phase === "awaiting_signoff") return "waiting";
  if (task.phase === "working") return "working";
  if (task.signoff.state === "approved") return "signed";
  return "neutral";
}

function waitView(task) {
  const view = waitPresentation(task.wait, task.signoff);
  if (task.wait?.kind !== "dependency") return view;
  return {
    ...view,
    detail: `等待 ${agentLabel(task.wait.subjectAgentId, "上游 Agent")}`,
    actor: agentLabel(task.wait.subjectAgentId, "上游 Agent"),
  };
}

function signoffTone(signoff) {
  if (signoff.state === "approved") return "signed";
  if (signoff.state === "rejected") return "failure";
  if (signoff.state === "awaiting_human" || signoff.state === "unknown") return "waiting";
  return "neutral";
}

function signoffText(signoff) {
  if (signoff.state === "approved") return `${signoff.reviewer} 已签 · ${clockText(signoff.decidedAt)}`;
  if (signoff.state === "rejected") return `${signoff.reviewer} 已驳回 · ${clockText(signoff.decidedAt)}`;
  if (signoff.state === "awaiting_human") return signoff.requestedFrom
    ? `等待 ${signoff.requestedFrom} 签收`
    : "等待人工签收";
  if (signoff.state === "pending_result") return "候选结果尚未产出";
  if (signoff.state === "not_required") return "本任务无需人工签发";
  return "签发事实不可用";
}

function durationText(task) {
  const started = Date.parse(task.createdAt);
  const snapshotAt = Date.parse(props.snapshot?.generatedAt);
  const terminal = task.phase === "settled" || task.phase === "failed" || task.phase === "cancelled";
  const ended = terminal ? Date.parse(task.updatedAt) : snapshotAt;
  if (!Number.isFinite(started) || !Number.isFinite(ended) || ended < started) return "不可用";
  return formatDuration(ended - started);
}

function clockText(iso) {
  if (!iso) return "时间不可用";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "时间不可用";
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}
</script>

<style scoped>
.agent-monitor {
  inline-size: 100%;
  min-inline-size: 0;
  display: grid;
  gap: var(--space-4);
  color: var(--ink);
}

.agent-monitor-head {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--space-2);
  padding-block-end: var(--space-3);
  border-bottom: 1px solid var(--hairline-soft);
}

.agent-monitor-icon {
  inline-size: 30px;
  block-size: 30px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-md);
  color: var(--clay);
  background: var(--paper-rail);
}

.agent-monitor-head-copy {
  min-inline-size: 0;
  display: grid;
  gap: 2px;
}

.agent-monitor-head-copy strong { font-size: var(--fs-sm); }
.agent-monitor-head-copy span { color: var(--ink-faint); font-size: var(--fs-xs); }

.agent-monitor-persistence {
  margin: 0;
  color: var(--ink-faint);
  font-size: var(--fs-xs);
  line-height: 1.45;
}

.agent-monitor-state {
  max-inline-size: 132px;
  overflow: hidden;
  color: var(--ink-soft);
  font-size: var(--fs-xs);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tone-working { color: var(--clay); }
.tone-waiting { color: var(--trust-pending); }
.tone-signed { color: var(--trust-signed); }
.tone-failure { color: var(--trust-fail); }
.tone-neutral { color: var(--ink-soft); }

.agent-monitor-notice,
.agent-monitor-sync {
  display: grid;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--hairline-soft);
  border-radius: var(--radius-md);
  background: var(--paper-rail);
  color: var(--ink-soft);
  font-size: var(--fs-sm);
  line-height: 1.5;
}

.agent-monitor-notice.is-invalid { color: var(--trust-pending); }
.agent-monitor-notice.is-pending,
.agent-monitor-sync { color: var(--trust-pending); }

.agent-monitor-notice button,
.agent-monitor-sync button {
  min-block-size: 44px;
  justify-self: start;
  padding-inline: var(--space-3);
  border: 1px solid var(--hairline);
  border-radius: var(--radius-sm);
  background: var(--card-bg, var(--paper-surface));
  color: var(--clay);
  cursor: pointer;
}

.agent-monitor-notice button:focus-visible,
.agent-monitor-sync button:focus-visible,
.agent-monitor-task-head:focus-visible,
.agent-monitor-completed-row:focus-visible,
.agent-monitor-completed summary:focus-visible {
  outline: 2px solid var(--focus-ring-clay, var(--clay));
  outline-offset: 2px;
}

.agent-monitor-group {
  display: grid;
  gap: var(--space-2);
}

.agent-monitor-group h3 {
  margin: 0;
  color: var(--ink-soft);
  font-size: var(--fs-xs);
  font-weight: 600;
  letter-spacing: 0.04em;
}

.agent-monitor-group h3 span {
  color: var(--ink-faint);
  font-family: var(--mono);
}

.agent-monitor-task {
  overflow: hidden;
  border: 1px solid var(--hairline-soft);
  border-inline-start: 3px solid var(--ink-faint);
  border-radius: var(--radius-md);
  background: var(--card-bg, var(--paper-surface));
  box-shadow: var(--shadow-card);
}

.agent-monitor-task.tone-working { border-inline-start-color: var(--clay); }
.agent-monitor-task.tone-waiting { border-inline-start-color: var(--trust-pending); }
.agent-monitor-task.tone-signed { border-inline-start-color: var(--trust-signed); }
.agent-monitor-task.tone-failure { border-inline-start-color: var(--trust-fail); }

.agent-monitor-task.is-focused,
.agent-monitor-completed-row.is-focused {
  box-shadow: inset 0 0 0 1px var(--clay), var(--shadow-card);
}

.agent-monitor-task-head {
  inline-size: 100%;
  min-block-size: 48px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border: 0;
  background: transparent;
  color: inherit;
  text-align: start;
  cursor: pointer;
}

.agent-monitor-task-main {
  min-inline-size: 0;
  display: grid;
  gap: 2px;
}

.agent-monitor-task-main strong {
  overflow: hidden;
  color: var(--ink);
  font-size: var(--fs-sm);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-monitor-task-main span,
.agent-monitor-duration {
  color: var(--ink-faint);
  font-size: var(--fs-xs);
}

.agent-monitor-duration { white-space: nowrap; }

.agent-monitor-detail {
  display: grid;
  gap: var(--space-2);
  padding: 0 var(--space-3) var(--space-3);
}

.agent-monitor-fact-block,
.agent-monitor-subagents {
  display: grid;
  gap: 4px;
  padding-block-start: var(--space-2);
  border-top: 1px solid var(--hairline-soft);
  color: var(--ink-soft);
  font-size: var(--fs-xs);
  line-height: 1.45;
}

.agent-monitor-label {
  color: var(--ink-faint);
  font-size: var(--fs-xs);
  font-weight: 600;
}

.agent-monitor-fact-line { overflow-wrap: anywhere; }

.agent-monitor-signoff {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  padding: var(--space-2);
  border-radius: var(--radius-sm);
  background: var(--paper-rail);
  font-size: var(--fs-xs);
}

.agent-monitor-runtime,
.agent-monitor-scope {
  color: var(--ink-faint);
  font-size: var(--fs-xs);
  line-height: 1.45;
}

.agent-monitor-runtime.tone-waiting { color: var(--trust-pending); }
.agent-monitor-runtime.tone-failure { color: var(--trust-fail); }

.agent-monitor-subagent {
  min-block-size: 28px;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--space-2);
  color: var(--ink-soft);
  font-family: var(--mono);
}

.agent-monitor-subagent-history {
  border-top: 1px solid var(--hairline-soft);
}

.agent-monitor-subagent-history summary {
  min-block-size: 44px;
  display: flex;
  align-items: center;
  color: var(--ink-faint);
  cursor: pointer;
}

.agent-monitor-subagent-history summary:focus-visible {
  outline: 2px solid var(--focus-ring-clay, var(--clay));
  outline-offset: 2px;
}

.agent-monitor-completed {
  border-top: 1px solid var(--hairline-soft);
}

.agent-monitor-completed summary {
  min-block-size: 44px;
  display: flex;
  align-items: center;
  color: var(--ink-soft);
  font-size: var(--fs-xs);
  cursor: pointer;
}

.agent-monitor-completed-row {
  inline-size: 100%;
  min-block-size: 44px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2);
  border: 0;
  border-top: 1px solid var(--hairline-soft);
  background: transparent;
  color: var(--ink-faint);
  text-align: start;
  cursor: pointer;
}

.agent-monitor-completed-row > span:first-child {
  min-inline-size: 0;
  display: grid;
  gap: 2px;
}

.agent-monitor-completed-row strong {
  overflow: hidden;
  color: var(--ink);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-monitor-completed-row small { color: var(--ink-faint); }

@media (max-width: 380px) {
  .agent-monitor-head { grid-template-columns: 28px minmax(0, 1fr); }
  .agent-monitor-state { display: none; }
  .agent-monitor-task-head { grid-template-columns: 1fr; }
  .agent-monitor-duration { justify-self: start; }
  .agent-monitor-subagent { grid-template-columns: auto 1fr; }
  .agent-monitor-subagent span:last-child { grid-column: 2; }
}

@media (prefers-reduced-motion: reduce) {
  .agent-monitor-task,
  .agent-monitor-task-head,
  .agent-monitor-completed-row { transition: none; }
}
</style>
