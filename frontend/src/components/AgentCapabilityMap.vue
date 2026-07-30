<template>
  <section v-if="overview.available" class="capability-overview" aria-labelledby="capability-map-title">
    <div class="capability-overview-head">
      <el-icon aria-hidden="true"><Grid /></el-icon>
      <div>
        <h3 id="capability-map-title">能力地图</h3>
        <p>先看它擅长哪类工作，再进入卡片核对能力边界。</p>
      </div>
    </div>
    <div class="capability-grid" role="list">
      <article
        v-for="item in overview.items"
        :key="item.id"
        class="capability-node"
        role="listitem"
      >
        <span
          class="capability-glyph"
          :style="{ color: categoryColor(item.id), background: categoryColor(item.id) + '14' }"
          aria-hidden="true"
        >
          <el-icon><component :is="CATEGORY_VISUALS[item.id].icon" /></el-icon>
        </span>
        <span class="capability-copy">
          <strong>{{ categoryLabel(item.id) }}</strong>
          <small>{{ CATEGORY_VISUALS[item.id].description }}</small>
        </span>
        <span class="capability-count num-token">{{ item.count }}</span>
      </article>
      <article v-if="overview.unknownCount > 0" class="capability-node is-unknown" role="listitem">
        <span class="capability-glyph" aria-hidden="true">
          <el-icon><QuestionFilled /></el-icon>
        </span>
        <span class="capability-copy">
          <strong>分类待核</strong>
          <small>未归入现有四类</small>
        </span>
        <span class="capability-count num-token">{{ overview.unknownCount }}</span>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed } from "vue";
import {
  Aim,
  Document,
  Grid,
  QuestionFilled,
  Reading,
  Tools,
} from "@element-plus/icons-vue";
import { categoryColor, categoryLabel } from "../utils/format";
import { buildPortalCategoryOverview } from "../utils/portalVisual";

const props = defineProps({
  agents: { type: Array, default: () => [] },
});

const CATEGORY_VISUALS = {
  tool_automation: { icon: Tools, description: "执行明确的工具步骤" },
  knowledge_qa: { icon: Reading, description: "检索并组织依据" },
  structured_gen: { icon: Document, description: "整理为标准化产物" },
  reasoning_assist: { icon: Aim, description: "提供候选与分析路径" },
};

const overview = computed(() => buildPortalCategoryOverview(props.agents));
</script>

<style scoped>
.capability-overview {
  margin: 0 0 var(--space-5);
  padding: 14px 16px 16px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: var(--paper-rail);
}
.capability-overview-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 12px;
}
.capability-overview-head > .el-icon {
  flex: none;
  width: 32px;
  height: 32px;
  border: 1px solid var(--hairline);
  border-radius: 9px;
  background: var(--surface-raised);
  color: var(--ink-soft);
  font-size: 18px;
}
.capability-overview h3 {
  margin: 0 0 2px;
  font-size: 14px;
  color: var(--ink);
}
.capability-overview p {
  margin: 0;
  color: var(--ink-faint);
  font-size: 11.5px;
  line-height: 1.45;
}
.capability-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}
.capability-node {
  min-width: 0;
  min-height: 64px;
  display: grid;
  grid-template-columns: 40px minmax(0, 1fr) auto;
  align-items: center;
  gap: 9px;
  padding: 9px 10px;
  border: 1px solid var(--hairline-soft);
  border-radius: 10px;
  background: var(--surface-raised);
}
.capability-glyph {
  width: 40px;
  height: 40px;
  display: inline-grid;
  place-items: center;
  border-radius: 11px;
  color: var(--ink-soft);
  background: var(--paper-canvas-b, var(--paper-rail));
  font-size: 22px;
}
.capability-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.capability-copy strong {
  color: var(--ink);
  font-size: 12px;
  line-height: 1.3;
}
.capability-copy small {
  color: var(--ink-faint);
  font-size: 10px;
  line-height: 1.35;
}
.capability-count {
  align-self: start;
  color: var(--ink-mid);
  font-size: 13px;
}
.capability-node.is-unknown .capability-glyph,
.capability-node.is-unknown .capability-count {
  color: var(--trust-pending);
}
@media (max-width: 980px) {
  .capability-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 520px) {
  .capability-overview { padding-inline: 12px; }
  .capability-grid { grid-template-columns: 1fr; }
}
</style>
