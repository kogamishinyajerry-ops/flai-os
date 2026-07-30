<template>
  <nav class="create-journey" aria-label="创建任务步骤">
    <div class="create-journey-head">
      <el-icon aria-hidden="true"><Connection /></el-icon>
      <div>
        <h3>一页完成</h3>
        <p>按图核对能力、输入和边界；最后一次点击才真正创建任务。</p>
      </div>
    </div>
    <div class="create-journey-map">
      <button
        v-for="step in steps"
        :key="step.id"
        type="button"
        class="create-step"
        :class="[`step-${step.id}`, `tone-${step.tone}`]"
        :aria-label="`${step.label}：${step.detail}`"
        @click="$emit('navigate', step.id)"
      >
        <el-icon class="create-step-icon" aria-hidden="true">
          <component :is="ICONS[step.id]" />
        </el-icon>
        <span class="create-step-copy">
          <strong>{{ step.label }}</strong>
          <small>{{ step.detail }}</small>
        </span>
      </button>
      <el-icon class="create-arrow arrow-a" aria-hidden="true"><ArrowRight /></el-icon>
      <el-icon class="create-arrow arrow-b" aria-hidden="true"><ArrowRight /></el-icon>
      <el-icon class="create-arrow arrow-turn" aria-hidden="true"><ArrowDown /></el-icon>
      <el-icon class="create-arrow arrow-c" aria-hidden="true"><ArrowLeft /></el-icon>
    </div>
  </nav>
</template>

<script setup>
import {
  Aim,
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  Connection,
  Cpu,
  EditPen,
  Lock,
  User,
} from "@element-plus/icons-vue";

defineProps({
  steps: { type: Array, default: () => [] },
});
defineEmits(["navigate"]);

const ICONS = {
  agent: Cpu,
  capability: Aim,
  input: EditPen,
  policy: Lock,
  submit: User,
};
</script>

<style scoped>
.create-journey {
  margin-bottom: 18px;
  padding: 14px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: var(--paper-rail);
  container-type: inline-size;
}
.create-journey-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 12px;
}
.create-journey-head > .el-icon {
  flex: none;
  width: 32px;
  height: 32px;
  border: 1px solid var(--hairline);
  border-radius: 9px;
  background: var(--surface-raised);
  color: var(--ink-soft);
  font-size: 18px;
}
.create-journey h3 {
  margin: 0 0 2px;
  color: var(--ink);
  font-size: 14px;
}
.create-journey p {
  margin: 0;
  color: var(--ink-faint);
  font-size: 11.5px;
  line-height: 1.45;
}
.create-journey-map {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 20px minmax(0, 1fr) 20px minmax(0, 1fr);
  grid-template-areas:
    "agent arrow-a capability arrow-b input"
    ". . . . arrow-turn"
    ". . submit arrow-c policy";
  gap: 6px 2px;
}
.create-step {
  min-width: 0;
  min-height: 76px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border: 1px solid var(--hairline-soft);
  border-radius: 10px;
  background: var(--surface-raised);
  color: inherit;
  text-align: left;
  cursor: pointer;
}
.create-step:hover,
.create-step:focus-visible {
  border-color: var(--clay-softer);
  outline: none;
  box-shadow: 0 0 0 3px rgba(var(--clay-rgb), 0.08);
}
.step-agent { grid-area: agent; }
.step-capability { grid-area: capability; }
.step-input { grid-area: input; }
.step-policy { grid-area: policy; }
.step-submit { grid-area: submit; }
.create-step-icon {
  flex: none;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: var(--paper-canvas-b, var(--paper-rail));
  color: var(--ink-soft);
  font-size: 19px;
}
.create-step-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.create-step strong {
  color: var(--ink);
  font-size: 11.5px;
  line-height: 1.25;
}
.create-step small {
  color: var(--ink-faint);
  font-size: 9.5px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}
.create-arrow {
  align-self: center;
  justify-self: center;
  color: var(--ink-faint);
}
.arrow-a { grid-area: arrow-a; }
.arrow-b { grid-area: arrow-b; }
.arrow-c { grid-area: arrow-c; }
.arrow-turn {
  grid-area: arrow-turn;
}
.tone-work .create-step-icon {
  color: var(--clay);
  background: var(--clay-soft);
}
.tone-pending .create-step-icon,
.tone-pending small {
  color: var(--trust-pending);
}
.tone-fail .create-step-icon,
.tone-fail small {
  color: var(--trust-fail);
}
@container (max-width: 500px) {
  .create-journey-map {
    grid-template-columns: 1fr;
    grid-template-areas:
      "agent"
      "arrow-a"
      "capability"
      "arrow-b"
      "input"
      "arrow-turn"
      "policy"
      "arrow-c"
      "submit";
    gap: 4px;
  }
  .create-step { min-height: 62px; }
  .arrow-a,
  .arrow-b {
    justify-self: center;
    transform: rotate(90deg);
  }
  .arrow-turn {
    justify-self: center;
    transform: none;
  }
  .arrow-c {
    justify-self: center;
    transform: rotate(-90deg);
  }
}
</style>
