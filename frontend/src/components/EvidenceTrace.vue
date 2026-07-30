<template>
  <!-- 依据链三节点（批次 D 去盒化重排）：hairline 分区取代「卡中卡中卡」——
       节点不再各自带框带底，宽容器横向流（箭头右指），窄容器（含 260px 环境
       rail）经容器查询改纵向流（箭头下指），长说明自由换行绝不裁切——旧版定高
       盒 + 绝对定位箭头在 1440px 下把「人工判断」说明拦腰裁掉（P0）。
       tone 仍只有 neutral/pending/fail 三槽：resolved=true 恒中性，绿不外借；
       状态词随文字同行，不靠颜色单独表达。 -->
  <section class="evidence-trace" :class="{ 'is-compact': compact }" :aria-label="title">
    <div class="evidence-trace-head">
      <el-icon aria-hidden="true"><Link /></el-icon>
      <strong>{{ title }}</strong>
      <small>{{ subtitle }}</small>
    </div>
    <ol class="evidence-trace-map">
      <template v-for="(step, index) in steps" :key="step.id">
        <li class="evidence-trace-step" :class="`tone-${step.tone}`">
          <el-icon aria-hidden="true"><component :is="icons[step.id]" /></el-icon>
          <span class="evidence-trace-text">
            <strong>{{ step.label }}</strong>
            <small>{{ step.detail }}</small>
          </span>
        </li>
        <li v-if="index < steps.length - 1" class="evidence-trace-arrow" aria-hidden="true">
          <el-icon><ArrowRight /></el-icon>
        </li>
      </template>
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
/* 自身即查询容器（W3 同款纪律）：按真实宿主几何切换横/纵——详情页主列宽宿主
   横向三节点，260px 环境 rail / 窄屏自动纵向，不靠视口媒查猜宿主。 */
.evidence-trace {
  container-type: inline-size;
  margin: 0 0 12px;
  padding: 10px 0 0;
  border-top: 1px solid var(--hairline-soft);
}
.evidence-trace-head {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 6px;
}
.evidence-trace-head > .el-icon {
  align-self: center;
  color: var(--ink-soft);
  font-size: 14px;
}
.evidence-trace-head strong {
  color: var(--ink);
  font-size: 12.5px;
  font-weight: 600;
}
.evidence-trace-head small {
  color: var(--ink-faint);
  font-size: 11px;
}
.evidence-trace-map {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin: 8px 0 0;
  padding: 0;
  list-style: none;
}
.evidence-trace-step {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  align-items: flex-start;
  gap: 7px;
}
.evidence-trace-step > .el-icon {
  flex: none;
  margin-top: 1px;
  color: var(--ink-soft);
  font-size: 15px;
}
.evidence-trace-text {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.evidence-trace-text strong {
  color: var(--ink);
  font-size: 11.5px;
  font-weight: 600;
}
/* 说明文字自由换行是 P0 裁切修复的本体：无定高、无裁切、无给箭头预留的
   右 padding——信息完整优先于节点等高。 */
.evidence-trace-text small {
  color: var(--ink-faint);
  font-size: 10.5px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}
.evidence-trace-arrow {
  flex: none;
  display: flex;
  margin-top: 1px;
  color: var(--ink-faint);
  font-size: 13px;
}
.tone-pending > .el-icon,
.tone-pending small {
  color: var(--trust-pending);
}
.tone-fail > .el-icon,
.tone-fail small {
  color: var(--trust-fail);
}
.is-compact {
  padding-top: 8px;
}
.is-compact .evidence-trace-head small {
  display: none;
}
/* 窄宿主纵向流：箭头转向下（静态旋转变换，非动效，reduced-motion 无涉），
   步骤间用 hairline 分区。 */
@container (max-width: 540px) {
  .evidence-trace-map {
    flex-direction: column;
    gap: 0;
  }
  .evidence-trace-step {
    padding: 7px 0;
  }
  .evidence-trace-step + .evidence-trace-arrow + .evidence-trace-step {
    border-top: 1px solid var(--hairline-soft);
  }
  .evidence-trace-arrow {
    margin: 0 0 0 1px;
  }
  .evidence-trace-arrow .el-icon {
    transform: rotate(90deg);
  }
}
</style>
