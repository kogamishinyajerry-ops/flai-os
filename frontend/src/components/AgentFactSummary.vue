<template>
  <button
    v-if="visible"
    type="button"
    class="agent-fact-summary"
    :class="[`tone-${tone}`, { 'is-working': animateWork, 'is-stale': stale || resyncing }]"
    :aria-label="`${factLine}，展开 Agent 监控`"
    @click="emit('open')"
  >
    <span class="agent-fact-glyph" aria-hidden="true">
      <el-icon><component :is="glyph" /></el-icon>
    </span>
    <span class="agent-fact-copy" aria-live="polite">
      <span class="agent-fact-line">{{ factLine }}</span>
      <span class="agent-fact-meta">
        <template v-if="coldError">打开监控查看原因并重试</template>
        <template v-else-if="emptyUnverified">打开监控查看保留快照并重试</template>
        <template v-else-if="projection.valid">
          <template v-if="projection.tasksTruncated">最近 {{ projection.taskCount }} / 共 {{ projection.totalTaskCount }} 个任务</template>
          <template v-else>{{ projection.taskCount }} 个任务</template> ·
          <template v-if="projection.applicableRuntimeCount === 0">当前任务不适用子智能体事实</template>
          <template v-else-if="projection.reportedRuntimeCount > 0">
            已报告 {{ projection.subagentCount }} 个子智能体<template v-if="projection.unavailableRuntimeCount > 0"> · {{ projection.unavailableRuntimeCount }} 个运行源未报告</template>
          </template>
          <template v-else>{{ projection.unavailableRuntimeCount }} 个运行源未报告</template>
        </template>
        <template v-else>事实不可渲染</template>
        <span v-if="resyncing"> · 正在重新同步</span>
        <span v-else-if="stale"> · 上次成功快照</span>
      </span>
    </span>
    <span class="agent-fact-open">展开监控</span>
  </button>
</template>

<script setup>
import { computed } from "vue";
import {
  CircleCheck,
  CircleClose,
  Clock,
  Loading,
  Minus,
  WarningFilled,
} from "@element-plus/icons-vue";

import { summarizeAgentFacts, validateAgentFactSnapshot } from "../utils/agentFactProjection.js";

const props = defineProps({
  snapshot: { type: Object, default: null },
  loaded: { type: Boolean, default: false },
  connection: { type: String, default: "idle" },
  stale: { type: Boolean, default: false },
  resyncing: { type: Boolean, default: false },
  error: { type: [String, Object], default: "" },
});

const emit = defineEmits(["open"]);

const projection = computed(() => {
  if (!props.snapshot) return { valid: false, renderable: false, error: "" };
  const validation = validateAgentFactSnapshot(props.snapshot);
  return validation.valid
    ? summarizeAgentFacts(props.snapshot, null, Date.now())
    : validation;
});

const errorText = computed(() => typeof props.error === "string"
  ? props.error
  : props.error?.message || "");
const coldError = computed(() => !props.loaded && !!errorText.value);
const emptyUnverified = computed(() => props.loaded === true
  && projection.value.valid === true
  && projection.value.renderable === false
  && (props.stale || props.resyncing || !!errorText.value || props.connection === "disconnected"));
const visible = computed(() => coldError.value || (props.loaded === true
  && props.snapshot !== null
  && (projection.value.valid === false
    || projection.value.renderable === true
    || emptyUnverified.value)));

const tone = computed(() => {
  if (coldError.value) return "unknown";
  if (!projection.value.valid) return "unknown";
  if (projection.value.state !== "failure" && projection.value.unavailableRuntimeCount > 0) {
    return "unknown";
  }
  return projection.value.state;
});
const factLine = computed(() => {
  if (coldError.value) return "Agent 事实首次读取失败";
  if (!projection.value.valid) return "Agent 事实不可渲染";
  if (emptyUnverified.value) return props.resyncing
    ? "Agent 事实正在重新同步"
    : "Agent 事实连接尚未核实";
  if (props.resyncing) return `${projection.value.headline}，正在核对快照`;
  if (props.stale || props.error || props.connection === "disconnected") {
    return `${projection.value.headline}，当前为上次成功事实`;
  }
  return projection.value.headline;
});

const glyph = computed(() => ({
  working: Loading,
  waiting: Clock,
  queued: Clock,
  signed: CircleCheck,
  failure: CircleClose,
  settled: Minus,
  unknown: WarningFilled,
}[tone.value] || WarningFilled));

const animateWork = computed(() => tone.value === "working"
  && props.stale !== true
  && props.resyncing !== true
  && !props.error
  && props.connection !== "disconnected");
</script>

<style scoped>
.agent-fact-summary {
  inline-size: 100%;
  min-block-size: 72px;
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--hairline-soft);
  border-radius: var(--radius-md);
  background: var(--card-bg, var(--paper-surface));
  color: var(--ink);
  box-shadow: var(--shadow-card);
  text-align: start;
  cursor: pointer;
  transition: border-color var(--motion-fast) var(--ease-out-soft), box-shadow var(--motion-fast) var(--ease-out-soft);
}

.agent-fact-summary:hover {
  border-color: var(--clay-softer, var(--clay));
  box-shadow: var(--shadow-card-hover);
}

.agent-fact-summary:focus-visible {
  outline: 2px solid var(--focus-ring-clay, var(--clay));
  outline-offset: 2px;
}

.agent-fact-glyph {
  inline-size: 28px;
  block-size: 28px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-pill);
  color: var(--ink-soft);
  background: var(--paper-rail);
  font-size: 14px;
}

.tone-working .agent-fact-glyph { color: var(--clay); }
.tone-waiting .agent-fact-glyph { color: var(--trust-pending); }
.tone-signed .agent-fact-glyph { color: var(--trust-signed); }
.tone-failure .agent-fact-glyph { color: var(--trust-fail); }
.tone-queued .agent-fact-glyph,
.tone-settled .agent-fact-glyph { color: var(--ink-soft); }
.tone-unknown .agent-fact-glyph { color: var(--trust-pending); }

.agent-fact-summary.is-working .agent-fact-glyph {
  animation: agent-fact-breathe 2s ease-in-out infinite;
}

.agent-fact-copy {
  min-inline-size: 0;
  display: grid;
  gap: 3px;
}

.agent-fact-line {
  overflow: hidden;
  color: var(--ink);
  font-size: var(--fs-sm);
  font-weight: 600;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-fact-meta,
.agent-fact-open {
  color: var(--ink-soft);
  font-size: var(--fs-xs);
  line-height: 1.25;
}

.agent-fact-open {
  font-weight: 600;
  text-decoration: underline;
  text-decoration-color: var(--clay);
  text-underline-offset: 2px;
  white-space: nowrap;
}

.agent-fact-summary.is-stale .agent-fact-glyph {
  color: var(--trust-pending);
}

@keyframes agent-fact-breathe {
  0%, 100% { opacity: 0.55; transform: scale(0.94); }
  50% { opacity: 1; transform: scale(1); }
}

@media (max-width: 520px) {
  .agent-fact-summary {
    grid-template-columns: 26px minmax(0, 1fr);
    padding-inline: var(--space-3);
  }

  .agent-fact-open { display: none; }
}

@media (prefers-reduced-motion: reduce) {
  .agent-fact-summary,
  .agent-fact-summary.is-working .agent-fact-glyph {
    animation: none;
    transition: none;
  }
}
</style>
