<template>
  <section class="evidence-trace" :class="{ 'is-compact': compact }" :aria-label="title">
    <div class="evidence-trace-head">
      <el-icon aria-hidden="true"><Link /></el-icon>
      <div>
        <strong>{{ title }}</strong>
        <small>{{ subtitle }}</small>
      </div>
    </div>
    <ol class="evidence-trace-map">
      <li
        v-for="(step, index) in steps"
        :key="step.id"
        class="evidence-trace-step"
        :class="`tone-${step.tone}`"
      >
        <el-icon aria-hidden="true"><component :is="icons[step.id]" /></el-icon>
        <span>
          <strong>{{ step.label }}</strong>
          <small>{{ step.detail }}</small>
        </span>
        <el-icon v-if="index < steps.length - 1" class="evidence-trace-arrow" aria-hidden="true">
          <ArrowRight />
        </el-icon>
      </li>
    </ol>
  </section>
</template>

<script setup>
import { computed } from "vue";
import {
  ArrowRight,
  Collection,
  DocumentChecked,
  Link,
  Reading,
  Stamp,
} from "@element-plus/icons-vue";
import { buildEvidenceTrace, buildKnowledgeTrace } from "../utils/evidenceTrace";

const props = defineProps({
  kind: { type: String, default: "evidence" },
  findings: { type: Array, default: () => [] },
  withheld: { type: Boolean, default: false },
  requiredMissing: { type: Boolean, default: false },
  citations: { type: Array, default: () => [] },
  compact: { type: Boolean, default: false },
});

const title = computed(() => props.kind === "knowledge" ? "知识引用链" : "依据来源链");
const subtitle = computed(() =>
  props.kind === "knowledge"
    ? "检索命中与当前语料分开比对"
    : "回源状态不等于结论成立"
);
const steps = computed(() =>
  props.kind === "knowledge"
    ? buildKnowledgeTrace(props.citations)
    : buildEvidenceTrace({
      findings: props.findings,
      withheld: props.withheld,
      requiredMissing: props.requiredMissing,
    })
);
const icons = computed(() =>
  props.kind === "knowledge"
    ? { source: Reading, compare: DocumentChecked, decision: Stamp }
    : { source: Collection, resolution: Link, decision: Stamp }
);
</script>

<style scoped>
.evidence-trace {
  margin: 0 0 12px;
  padding: 11px 12px;
  border: 1px solid var(--hairline);
  border-radius: 10px;
  background: var(--paper-rail);
}
.evidence-trace-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.evidence-trace-head > .el-icon {
  flex: none;
  width: 28px;
  height: 28px;
  border: 1px solid var(--hairline);
  border-radius: 8px;
  background: var(--surface-raised);
  color: var(--ink-soft);
  font-size: 16px;
}
.evidence-trace-head > div {
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.evidence-trace-head strong {
  color: var(--ink);
  font-size: 12px;
}
.evidence-trace-head small {
  color: var(--ink-faint);
  font-size: 10px;
}
.evidence-trace-map {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.evidence-trace-step {
  position: relative;
  min-width: 0;
  min-height: 58px;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 7px 20px 7px 8px;
  border: 1px solid var(--hairline-soft);
  border-radius: 9px;
  background: var(--surface-raised);
}
.evidence-trace-step > .el-icon:first-child {
  flex: none;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: var(--paper-canvas-b, var(--paper-rail));
  color: var(--ink-soft);
  font-size: 16px;
}
.evidence-trace-step > span {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.evidence-trace-step strong {
  color: var(--ink);
  font-size: 10.5px;
}
.evidence-trace-step small {
  color: var(--ink-faint);
  font-size: 9px;
  line-height: 1.3;
  overflow-wrap: anywhere;
}
.evidence-trace-arrow {
  position: absolute;
  right: -12px;
  z-index: 1;
  color: var(--ink-faint);
  font-size: 13px;
}
.tone-pending > .el-icon:first-child,
.tone-pending small {
  color: var(--trust-pending);
}
.tone-fail > .el-icon:first-child,
.tone-fail small {
  color: var(--trust-fail);
}
.is-compact {
  padding: 8px;
}
.is-compact .evidence-trace-head small {
  display: none;
}
.is-compact .evidence-trace-step {
  min-height: 48px;
  padding-block: 5px;
}
@media (max-width: 520px) {
  .evidence-trace-map {
    grid-template-columns: 1fr;
  }
  .evidence-trace-step {
    min-height: 52px;
    padding-right: 8px;
  }
  .evidence-trace-arrow {
    right: 50%;
    bottom: -12px;
    transform: translateX(50%) rotate(90deg);
  }
}
</style>
