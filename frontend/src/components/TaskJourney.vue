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
/* 批次 D 去盒化：整链与六节点不再各自带框带底（旧版 rail 底色盒套 6 个凸起
   盒），改 hairline 分区 + 字重/字号分层。自身即查询容器——窄宿主（任务台
   中栏/375px/速览）蛇形栅格改纵向单链，箭头让位序号与 hairline，无横向溢出。 */
.task-journey {
  margin-top: 16px;
  padding: 12px 0 0;
  border-top: 1px solid var(--hairline);
  container-type: inline-size;
}
.task-journey.is-compact {
  margin: 0 0 16px;
  padding-top: 10px;
}
.journey-head {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 10px;
}
.journey-head-icon {
  flex: none;
  margin-top: 1px;
  color: var(--ink-soft);
  font-size: 16px;
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
  grid-template-columns: minmax(0, 1fr) 16px minmax(0, 1fr) 16px minmax(0, 1fr);
  grid-template-areas:
    "input arrow-a execution arrow-b calls"
    ". . . . arrow-turn"
    "delivery arrow-d review arrow-c artifacts";
  gap: 6px 2px;
  align-items: stretch;
}
.journey-step {
  position: relative;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 8px 4px 6px;
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
  top: 4px;
  left: 6px;
  font-family: var(--mono, ui-monospace, monospace);
  font-size: 9px;
  color: var(--ink-faint);
}
.journey-icon {
  color: var(--ink-soft);
  font-size: 19px;
}
.journey-label {
  font-size: 11.5px;
  font-weight: 700;
  color: var(--ink);
}
.journey-detail {
  max-width: 100%;
  font-size: 10px;
  line-height: 1.4;
  color: var(--ink-faint);
  overflow-wrap: anywhere;
}
.journey-arrow {
  align-self: center;
  justify-self: center;
  color: var(--ink-faint);
  font-size: 14px;
}
.arrow-a { grid-area: arrow-a; }
.arrow-b { grid-area: arrow-b; }
.arrow-turn { grid-area: arrow-turn; }
.arrow-c { grid-area: arrow-c; }
.arrow-d { grid-area: arrow-d; }
.tone-work .journey-icon {
  color: var(--clay);
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
  padding-block: 6px;
}
.is-compact .journey-icon {
  font-size: 17px;
}
.is-compact .journey-detail {
  font-size: 9.5px;
}
/* 窄宿主纵向单链：DOM 序即流程序（输入→交付自上而下），蛇形箭头整体让位，
   步骤间 hairline 分区，序号回流行首。 */
@container (max-width: 620px) {
  .journey-map {
    display: flex;
    flex-direction: column;
    gap: 0;
  }
  .journey-step {
    flex-direction: row;
    align-items: flex-start;
    gap: 8px;
    padding: 8px 0;
    text-align: left;
  }
  .journey-step + .journey-step {
    border-top: 1px solid var(--hairline-soft);
  }
  .journey-index {
    position: static;
    flex: none;
    min-width: 12px;
    margin-top: 3px;
    font-size: 10px;
  }
  .journey-icon {
    flex: none;
    margin-top: 1px;
    font-size: 16px;
  }
  .journey-label {
    flex: none;
    margin-top: 1px;
  }
  .journey-detail {
    flex: 1 1 auto;
    margin-top: 2px;
  }
  .journey-arrow {
    display: none;
  }
}
</style>
