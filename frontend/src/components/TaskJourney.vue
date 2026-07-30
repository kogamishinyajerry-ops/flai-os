<template>
  <section
    v-if="steps.length"
    class="task-journey"
    :class="{ 'is-compact': compact }"
    aria-label="任务执行链"
  >
    <div v-if="!compact" class="journey-head">
      <el-icon class="journey-head-icon" aria-hidden="true"><Connection /></el-icon>
      <div>
        <h3>执行链</h3>
        <p>从输入到交付的真实状态一眼可见；普通完成不等于已验证，只有具名人工批准才显示签发标记。</p>
      </div>
    </div>

    <div class="journey-map" role="list">
      <article
        v-for="(step, index) in steps"
        :key="step.id"
        class="journey-step"
        :class="[`step-${step.id}`, `tone-${step.tone}`]"
        role="listitem"
        :aria-label="`${step.label}：${step.detail}`"
      >
        <span class="journey-index" aria-hidden="true">{{ index + 1 }}</span>
        <el-icon class="journey-icon" aria-hidden="true">
          <component :is="icons[step.id]" />
        </el-icon>
        <span class="journey-label">{{ step.label }}</span>
        <span class="journey-detail">{{ step.detail }}</span>
      </article>
      <el-icon class="journey-arrow arrow-a" aria-hidden="true"><ArrowRight /></el-icon>
      <el-icon class="journey-arrow arrow-b" aria-hidden="true"><ArrowRight /></el-icon>
      <el-icon class="journey-arrow arrow-turn" aria-hidden="true"><ArrowDown /></el-icon>
      <el-icon class="journey-arrow arrow-c" aria-hidden="true"><ArrowLeft /></el-icon>
      <el-icon class="journey-arrow arrow-d" aria-hidden="true"><ArrowLeft /></el-icon>
    </div>
  </section>
</template>

<script setup>
import { computed } from "vue";
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  Box,
  Connection,
  Cpu,
  Files,
  Tools,
  UploadFilled,
  User,
} from "@element-plus/icons-vue";
import { buildTaskJourney } from "../utils/taskJourney";

const props = defineProps({
  task: { type: Object, default: null },
  events: { type: Array, default: () => [] },
  modelCalls: { type: Array, default: () => [] },
  modelCallsLoaded: { type: Boolean, default: false },
  modelCallsError: { type: [String, Boolean], default: "" },
  artifactCount: { type: Number, default: undefined },
  compact: { type: Boolean, default: false },
});

const icons = {
  input: UploadFilled,
  execution: Cpu,
  calls: Tools,
  artifacts: Files,
  review: User,
  delivery: Box,
};

const steps = computed(() => buildTaskJourney({
  task: props.task,
  events: props.events,
  modelCalls: props.modelCalls,
  modelCallsLoaded: props.modelCallsLoaded,
  modelCallsError: props.modelCallsError,
  artifactCount: props.artifactCount,
}));
</script>

<style scoped>
.task-journey {
  margin-top: 16px;
  padding: 14px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg, 12px);
  background: var(--paper-rail);
  container-type: inline-size;
}
.task-journey.is-compact {
  margin: 0 0 16px;
  padding: 10px;
}
.journey-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 12px;
}
.journey-head-icon {
  flex: none;
  width: 30px;
  height: 30px;
  border: 1px solid var(--hairline);
  border-radius: 9px;
  background: var(--surface-raised);
  color: var(--ink-soft);
  font-size: 17px;
}
.journey-head h3 {
  margin: 0 0 2px;
  font-size: 14px;
  font-weight: 700;
  color: var(--ink);
}
.journey-head p {
  margin: 0;
  font-size: 11.5px;
  line-height: 1.45;
  color: var(--ink-faint);
}
.journey-map {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 22px minmax(0, 1fr) 22px minmax(0, 1fr);
  grid-template-areas:
    "input arrow-a execution arrow-b calls"
    ". . . . arrow-turn"
    "delivery arrow-d review arrow-c artifacts";
  gap: 7px 2px;
  align-items: stretch;
}
.journey-step {
  position: relative;
  min-width: 0;
  min-height: 96px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 10px 6px 9px;
  border: 1px solid var(--hairline-soft);
  border-radius: 10px;
  background: var(--surface-raised);
  text-align: center;
}
.step-input { grid-area: input; }
.step-execution { grid-area: execution; }
.step-calls { grid-area: calls; }
.step-artifacts { grid-area: artifacts; }
.step-review { grid-area: review; }
.step-delivery { grid-area: delivery; }
.journey-index {
  position: absolute;
  top: 6px;
  left: 7px;
  font-family: var(--mono, ui-monospace, monospace);
  font-size: 9px;
  color: var(--ink-faint);
}
.journey-icon {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: var(--paper-canvas-b, var(--paper-rail));
  color: var(--ink-soft);
  font-size: 20px;
}
.journey-label {
  font-size: 11.5px;
  font-weight: 700;
  color: var(--ink);
  white-space: nowrap;
}
.journey-detail {
  max-width: 100%;
  font-size: 10px;
  line-height: 1.35;
  color: var(--ink-faint);
  overflow-wrap: anywhere;
}
.journey-arrow {
  align-self: center;
  justify-self: center;
  color: var(--ink-faint);
  font-size: 15px;
}
.arrow-a { grid-area: arrow-a; }
.arrow-b { grid-area: arrow-b; }
.arrow-turn { grid-area: arrow-turn; }
.arrow-c { grid-area: arrow-c; }
.arrow-d { grid-area: arrow-d; }
.tone-work .journey-icon {
  color: var(--clay);
  background: var(--clay-soft);
}
.tone-pending .journey-icon,
.tone-pending .journey-detail {
  color: var(--trust-pending);
}
.tone-signed .journey-icon,
.tone-signed .journey-detail {
  color: var(--trust-signed);
}
.tone-fail .journey-icon,
.tone-fail .journey-detail {
  color: var(--trust-fail);
}
.is-compact .journey-step {
  min-height: 82px;
  padding-block: 8px;
}
.is-compact .journey-icon {
  width: 30px;
  height: 30px;
  font-size: 18px;
}
.is-compact .journey-detail {
  font-size: 9.5px;
}
</style>
