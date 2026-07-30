<template>
  <section class="governance-journey" aria-label="治理评测闭环">
    <div class="governance-journey-head">
      <el-icon aria-hidden="true"><Promotion /></el-icon>
      <div>
        <h3>治理闭环</h3>
        <p>评测通过只是证据；人工确认、服务端准入和持久化晋升记录缺一不可。</p>
      </div>
    </div>
    <div class="governance-map" role="list">
      <article
        v-for="step in steps"
        :key="step.id"
        class="governance-step"
        :class="[`step-${step.id}`, `tone-${step.tone}`]"
        role="listitem"
        :aria-label="`${step.label}：${step.detail}`"
      >
        <el-icon class="governance-icon" aria-hidden="true">
          <component :is="ICONS[step.id]" />
        </el-icon>
        <strong>{{ step.label }}</strong>
        <small>{{ step.detail }}</small>
      </article>
      <el-icon class="governance-arrow arrow-a" aria-hidden="true"><ArrowRight /></el-icon>
      <el-icon class="governance-arrow arrow-b" aria-hidden="true"><ArrowRight /></el-icon>
      <el-icon class="governance-arrow arrow-turn" aria-hidden="true"><ArrowDown /></el-icon>
      <el-icon class="governance-arrow arrow-c" aria-hidden="true"><ArrowLeft /></el-icon>
      <el-icon class="governance-arrow arrow-d" aria-hidden="true"><ArrowLeft /></el-icon>
    </div>
    <div v-if="draftCount > 0" class="governance-draft-branch">
      <el-icon aria-hidden="true"><CollectionTag /></el-icon>
      <span>该次评测发现 {{ draftCount }} 个待策展草案，不计入本次评测。</span>
    </div>
  </section>
</template>

<script setup>
import { computed } from "vue";
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  Collection,
  CollectionTag,
  DataAnalysis,
  Key,
  Promotion,
  Timer,
  UserFilled,
} from "@element-plus/icons-vue";
import { buildGovernanceJourney } from "../utils/governanceJourney";

const props = defineProps({
  maturity: { type: String, default: "" },
  curatedCasesCount: { type: Number, default: null },
  latestRun: { type: Object, default: null },
  promotionConfirmed: { type: Boolean, default: false },
  promotions: { type: Array, default: () => [] },
});

const ICONS = {
  cases: Collection,
  dispatch: Timer,
  result: DataAnalysis,
  confirmation: UserFilled,
  gate: Key,
  promotion: Promotion,
};
const steps = computed(() => buildGovernanceJourney({
  maturity: props.maturity,
  curatedCasesCount: props.curatedCasesCount,
  latestRun: props.latestRun,
  promotionConfirmed: props.promotionConfirmed,
  promotions: props.promotions,
}));
const draftCount = computed(() =>
  Array.isArray(props.latestRun?.draft_cases) ? props.latestRun.draft_cases.length : 0
);
</script>

<style scoped>
.governance-journey {
  margin: 14px 0;
  padding: 12px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: var(--paper-rail);
  container-type: inline-size;
}
.governance-journey-head {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  margin-bottom: 10px;
}
.governance-journey-head > .el-icon {
  flex: none;
  width: 30px;
  height: 30px;
  border: 1px solid var(--hairline);
  border-radius: 9px;
  background: var(--surface-raised);
  color: var(--ink-soft);
  font-size: 17px;
}
.governance-journey h3 {
  margin: 0 0 2px;
  color: var(--ink);
  font-size: 13px;
}
.governance-journey p {
  margin: 0;
  color: var(--ink-faint);
  font-size: 10.5px;
  line-height: 1.4;
}
.governance-map {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 18px minmax(0, 1fr) 18px minmax(0, 1fr);
  grid-template-areas:
    "cases arrow-a dispatch arrow-b result"
    ". . . . arrow-turn"
    "promotion arrow-d gate arrow-c confirmation";
  gap: 5px 2px;
}
.governance-step {
  min-width: 0;
  min-height: 82px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 8px 5px;
  border: 1px solid var(--hairline-soft);
  border-radius: 9px;
  background: var(--surface-raised);
  text-align: center;
}
.step-cases { grid-area: cases; }
.step-dispatch { grid-area: dispatch; }
.step-result { grid-area: result; }
.step-confirmation { grid-area: confirmation; }
.step-gate { grid-area: gate; }
.step-promotion { grid-area: promotion; }
.governance-icon {
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: var(--paper-canvas-b, var(--paper-rail));
  color: var(--ink-soft);
  font-size: 17px;
}
.governance-step strong {
  color: var(--ink);
  font-size: 10.5px;
}
.governance-step small {
  color: var(--ink-faint);
  font-size: 8.8px;
  line-height: 1.3;
  overflow-wrap: anywhere;
}
.governance-arrow {
  align-self: center;
  justify-self: center;
  color: var(--ink-faint);
  font-size: 14px;
}
.arrow-a { grid-area: arrow-a; }
.arrow-b { grid-area: arrow-b; }
.arrow-c { grid-area: arrow-c; }
.arrow-d { grid-area: arrow-d; }
.arrow-turn {
  grid-area: arrow-turn;
}
.tone-work .governance-icon {
  color: var(--clay);
  background: var(--clay-soft);
}
.tone-pending .governance-icon,
.tone-pending small {
  color: var(--trust-pending);
}
.tone-real .governance-icon,
.tone-real small {
  color: var(--trust-real);
}
.tone-signed .governance-icon,
.tone-signed small {
  color: var(--trust-signed);
}
.tone-fail .governance-icon,
.tone-fail small {
  color: var(--trust-fail);
}
.governance-draft-branch {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--hairline);
  color: var(--trust-pending);
  font-size: 10.5px;
}
@container (max-width: 430px) {
  .governance-map {
    grid-template-columns: 1fr;
    grid-template-areas:
      "cases"
      "arrow-a"
      "dispatch"
      "arrow-b"
      "result"
      "arrow-turn"
      "confirmation"
      "arrow-c"
      "gate"
      "arrow-d"
      "promotion";
  }
  .governance-step { min-height: 64px; }
  .arrow-a,
  .arrow-b {
    transform: rotate(90deg);
  }
  .arrow-turn {
    transform: none;
  }
  .arrow-c,
  .arrow-d {
    transform: rotate(-90deg);
  }
}
</style>
