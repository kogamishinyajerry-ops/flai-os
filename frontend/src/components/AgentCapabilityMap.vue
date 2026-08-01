<template>
  <section v-if="overview.available" class="capability-overview" aria-labelledby="capability-map-title">
    <div class="capability-overview-head">
      <el-icon aria-hidden="true"><Grid /></el-icon>
      <div>
        <h3 id="capability-map-title">能力本体</h3>
        <p>工作类型、专业域与发起方式统一来自只读 Registry 快照。</p>
      </div>
      <div class="capability-summary" aria-label="本体摘要">
        <span>专业域 <strong class="num-token">{{ overview.domainCount }}</strong></span>
        <span :class="{ 'is-unknown': overview.unresolvedReferenceCount > 0 }">
          引用待核 <strong class="num-token">{{ overview.unresolvedReferenceCount }}</strong>
        </span>
        <span :class="{ 'is-unknown': overview.defaultedClearanceCount > 0 }">
          密级默认 <strong class="num-token">{{ overview.defaultedClearanceCount }}</strong>
        </span>
        <span :class="{ 'is-unknown': overview.mockToolReferenceCount > 0 }">
          MOCK 工具 <strong class="num-token">{{ overview.mockToolReferenceCount }}</strong>
        </span>
        <span :class="{ 'is-unknown': overview.unknownMockToolReferenceCount > 0 }">
          工具真伪待核 <strong class="num-token">{{ overview.unknownMockToolReferenceCount }}</strong>
        </span>
      </div>
    </div>
    <div class="capability-grid" role="list">
      <article
        v-for="item in overview.items"
        :key="item.id"
        class="capability-node"
        role="listitem"
      >
        <div class="capability-node-head">
          <span
            class="capability-glyph"
            :style="{ color: categoryColor(item.id), background: categoryColor(item.id) + '14' }"
            aria-hidden="true"
          >
            <el-icon><component :is="visualOf(item.id).icon" /></el-icon>
          </span>
          <span class="capability-copy">
            <strong>{{ categoryLabel(item.id) }}</strong>
            <small>{{ visualOf(item.id).description }}</small>
          </span>
          <span
            class="capability-count num-token"
            :class="{ 'is-empty': item.total === 0 }"
            :title="item.total === 0 ? '该分类暂无已注册 Agent' : undefined"
          >{{ item.total }}</span>
        </div>
        <div v-if="item.total > 0" class="capability-relations">
          <span class="cap-relation">
            <el-icon aria-hidden="true"><User /></el-icon>
            已注册 {{ item.total }} 个 Agent
          </span>
          <span
            class="cap-relation"
            :class="{ 'is-unknown': item.unknown > 0 }"
          >
            <el-icon aria-hidden="true"><Promotion /></el-icon>
            {{ launchText(item) }}
          </span>
        </div>
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
  Promotion,
  QuestionFilled,
  Reading,
  Tools,
  User,
} from "@element-plus/icons-vue";
import { categoryColor, categoryLabel } from "../utils/format";
import { buildAgentShellOverview } from "../utils/agentShell.js";

const props = defineProps({
  snapshot: { type: Object, default: null },
});

const CATEGORY_VISUALS = {
  tool_automation: { icon: Tools, description: "执行明确的工具步骤" },
  knowledge_qa: { icon: Reading, description: "检索并组织依据" },
  structured_gen: { icon: Document, description: "整理为标准化产物" },
  reasoning_assist: { icon: Aim, description: "提供候选与分析路径" },
};

const overview = computed(() => buildAgentShellOverview(props.snapshot));
function visualOf(category) {
  return CATEGORY_VISUALS[category] || {
    icon: QuestionFilled,
    description: "分类语义待核",
  };
}

function launchText(item) {
  if (item.unknown > 0) return `${item.unknown} 项发起方式待核`;
  if (item.conversation > 0 && item.task > 0) {
    return `任务 ${item.task} · 对话 ${item.conversation}`;
  }
  if (item.conversation > 0) return `对话发起 ${item.conversation}`;
  return `任务发起 ${item.task}`;
}
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
  gap: var(--space-2);
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
.capability-summary {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--ink-faint);
  font-size: var(--fs-2xs);
  white-space: nowrap;
}
.capability-summary strong { color: var(--ink-soft); font-weight: 650; }
.capability-summary .is-unknown,
.capability-summary .is-unknown strong { color: var(--trust-pending); }
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
  padding: 9px 10px;
  border: 1px solid var(--hairline-soft);
  border-radius: 10px;
  background: var(--surface-raised);
}
.capability-node-head {
  display: grid;
  grid-template-columns: 40px minmax(0, 1fr) auto;
  align-items: center;
  gap: 9px;
  min-height: 46px;
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
/* 零计数降噪：分类卡兼图例职责保留显示，但 0 不抢视觉权重（非零样式不变）。 */
.capability-count.is-empty {
  color: var(--ink-faint);
}
.capability-node.is-unknown .capability-glyph,
.capability-node.is-unknown .capability-count {
  color: var(--trust-pending);
}
/* 关系行：纯文字+hairline，不再叠盒子（盒子套盒子红线） */
.capability-relations {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-top: 7px;
  padding-top: 7px;
  border-top: 1px solid var(--hairline-soft);
}
.cap-relation {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  max-width: 100%;
  overflow-wrap: anywhere;
  color: var(--ink-soft);
  font-size: 10.5px;
  line-height: 1.4;
}
.cap-relation .el-icon {
  flex: none;
  font-size: 12px;
  color: var(--ink-faint);
}
.cap-relation.is-unknown,
.cap-relation.is-unknown .el-icon {
  color: var(--trust-pending);
}
@media (max-width: 980px) {
  .capability-overview-head { flex-wrap: wrap; }
  .capability-summary {
    width: 100%;
    margin-left: calc(var(--space-8) + var(--space-2));
    flex-wrap: wrap;
    white-space: normal;
  }
  .capability-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 520px) {
  .capability-overview { padding-inline: 12px; }
  .capability-summary { margin-left: 0; }
  .capability-grid { grid-template-columns: 1fr; }
}
</style>
