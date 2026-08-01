<template>
  <section
    ref="panelEl"
    :class="['shell-context', { 'agent-pick': isPicker, 'is-picker': isPicker }]"
    :role="isPicker ? 'dialog' : undefined"
    :aria-label="isPicker ? '选择 Agent' : '任务上下文'"
    :tabindex="isPicker ? -1 : undefined"
  >
    <header class="context-head">
      <div class="context-head-copy">
        <span class="context-kicker">{{ isPicker ? "AGENT ONTOLOGY" : "AGENT SHELL · CONTEXT" }}</span>
        <div class="context-title-row">
          <h2>{{ isPicker ? "按工作选择 Agent" : "任务上下文" }}</h2>
          <span v-if="!isPicker" class="context-contract">只读本体 · v1</span>
        </div>
        <p v-if="!isPicker">对象、关系与边界来自当前 Registry 快照。</p>
      </div>
    </header>

    <div v-if="!isPicker" class="context-object" aria-label="当前工程对象">
      <span class="context-object-icon" aria-hidden="true"><el-icon><Connection /></el-icon></span>
      <span class="context-object-copy">
        <small>当前工程对象</small>
        <strong>尚未绑定</strong>
        <span>先描述目标；没有依据的对象关系不会被补写。</span>
      </span>
    </div>

    <div v-if="loading" class="context-loading" role="status">
      <el-icon class="is-loading" aria-hidden="true"><Loading /></el-icon>
      <span>正在同步 Agent Registry 快照…</span>
    </div>
    <div v-else-if="error" class="context-unavailable is-error" role="status">
      <el-icon aria-hidden="true"><Warning /></el-icon>
      <span>{{ error }}</span>
    </div>
    <div v-else-if="navigator.available !== true" class="context-unavailable" role="status">
      <el-icon aria-hidden="true"><Warning /></el-icon>
      <span>Agent 本体投影不可用；没有把未知状态压成“0 个”。</span>
    </div>

    <template v-else>
      <div class="context-controls">
        <div class="context-section-label">
          <span>工作类型</span>
          <span class="context-count num-token">{{ navigator.totalCount }} 个候选</span>
        </div>
        <div class="context-facets" aria-label="按工作类型筛选">
          <button
            type="button"
            :class="['context-facet', { 'is-active': workType === 'all' }]"
            :aria-pressed="workType === 'all'"
            :disabled="disabled"
            @click="workType = 'all'"
          >全部 <span class="num-token">{{ navigator.totalCount }}</span></button>
          <button
            v-for="item in navigator.workTypes"
            :key="item.id"
            type="button"
            :class="['context-facet', { 'is-active': workType === item.id }]"
            :aria-pressed="workType === item.id"
            :disabled="disabled"
            :title="categoryLabel(item.id)"
            @click="workType = item.id"
          >
            <span class="facet-dot" :style="{ background: categoryColor(item.id) }"></span>
            {{ contextCategoryLabel(item.id) }}
            <span class="num-token">{{ item.count }}</span>
          </button>
        </div>
        <label class="context-search-wrap">
          <el-icon aria-hidden="true"><Search /></el-icon>
          <input
            ref="searchEl"
            v-model="query"
            type="search"
            class="ap-search context-search"
            :disabled="disabled"
            placeholder="搜索工作、Agent 或边界"
            aria-label="搜索可用 Agent"
          />
        </label>
      </div>

      <div class="context-list-head">
        <span>候选 Agent</span>
        <span class="num-token">{{ navigator.visibleCount }} / {{ navigator.totalCount }}</span>
      </div>
      <div class="ap-scroll context-agent-list">
        <button
          v-for="agent in navigator.items"
          :key="agent.id"
          type="button"
          class="ap-item context-agent"
          :disabled="disabled"
          :aria-label="agentAriaLabel(agent)"
          @click="stage(agent)"
        >
          <span class="ap-dot" :style="{ background: categoryColor(agent.category) }"></span>
          <span class="ap-main context-agent-main">
            <span class="ap-name-row">
              <span class="ap-name" :title="agent.name">{{ agent.name }}</span>
              <span v-if="agent.maturity" class="ap-maturity" :title="maturityTip(agent.maturity)">{{ agent.maturity }}</span>
            </span>
            <span class="ap-detail" :title="agent.detail">{{ agent.detail }}</span>
            <span v-if="isPicker" class="context-agent-relation">
              <template v-for="(part, index) in pickerGateParts(agent)" :key="`${part.text}-${index}`">
                <span :class="{ 'context-pending-token': part.pending }">{{ part.text }}</span>
                <span v-if="index < pickerGateParts(agent).length - 1" aria-hidden="true"> · </span>
              </template>
            </span>
            <span v-else class="context-agent-relation" :class="`is-${agent.referenceState}`">
              <template v-if="agent.referenceState === 'resolved'">
                工具 {{ agent.toolCount }} · 知识范围 {{ agent.scopeCount }} ·
                {{ clearanceState(agent.clearance, agent.clearanceSource).label }}<span
                  v-if="clearanceState(agent.clearance, agent.clearanceSource).suffix"
                  class="context-pending-token"
                >{{ clearanceState(agent.clearance, agent.clearanceSource).suffix }}</span>
              </template>
              <template v-else-if="agent.referenceState === 'unresolved'">
                引用待核 · {{ agent.unresolvedReferenceCount }} 项未解析
              </template>
              <template v-else>工具与知识引用待核</template>
            </span>
            <span
              v-if="!isPicker && (agent.reviewRequired !== false || agent.evidenceRequired !== false || agent.mockToolCount > 0 || agent.unknownMockToolCount > 0)"
              class="context-trust-row"
            >
              <span v-if="agent.reviewRequired === true" class="context-trust-pill"><el-icon><User /></el-icon>需人工复核</span>
              <span v-else-if="agent.reviewRequired === null" class="context-trust-pill is-pending"><el-icon><Warning /></el-icon>复核要求待核</span>
              <span v-if="agent.evidenceRequired === true" class="context-trust-pill"><el-icon><DocumentChecked /></el-icon>需可核依据</span>
              <span v-else-if="agent.evidenceRequired === null" class="context-trust-pill is-pending"><el-icon><Warning /></el-icon>依据要求待核</span>
              <span v-if="agent.mockToolCount > 0" class="context-trust-pill is-pending"><el-icon><Warning /></el-icon>MOCK 工具 {{ agent.mockToolCount }}</span>
              <span v-if="agent.unknownMockToolCount > 0" class="context-trust-pill is-pending"><el-icon><Warning /></el-icon>工具真伪待核 {{ agent.unknownMockToolCount }}</span>
            </span>
          </span>
          <el-icon v-if="!isPicker" class="context-stage-icon" aria-hidden="true"><Plus /></el-icon>
        </button>
        <div v-if="navigator.items.length === 0" class="ap-zero context-zero">
          {{ query.trim() || workType !== "all" ? "没有匹配的候选 Agent" : "暂无可暂存的 Agent" }}
        </div>
      </div>
    </template>

    <footer class="context-footer">
      <p><el-icon aria-hidden="true"><Lock /></el-icon>选择只加入输入草稿，不会发送、建任务或签发。</p>
      <button type="button" class="ap-portal-link context-portal" :disabled="disabled" @click="$emit('open-portal')">
        查看完整治理与能力边界 <el-icon aria-hidden="true"><ArrowRight /></el-icon>
      </button>
    </footer>
  </section>
</template>

<script setup>
import { computed, ref } from "vue";
import {
  ArrowRight,
  Connection,
  DocumentChecked,
  Lock,
  Loading,
  Plus,
  Search,
  User,
  Warning,
} from "@element-plus/icons-vue";
import { buildAgentShellNavigator } from "../utils/agentShell.js";
import {
  categoryColor,
  categoryLabel,
  maturityTip,
} from "../utils/format";

const props = defineProps({
  snapshot: { type: Object, default: null },
  error: { type: String, default: "" },
  disabled: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  variant: { type: String, default: "rail" },
});
const emit = defineEmits(["stage", "open-portal"]);

const query = ref("");
const workType = ref("all");
const searchEl = ref(null);
const panelEl = ref(null);
const isPicker = computed(() => props.variant === "picker");
const navigator = computed(() =>
  buildAgentShellNavigator(props.snapshot, {
    query: query.value,
    workType: workType.value,
  }),
);

const CLEARANCE_LABELS = {
  public: "公开级",
  internal: "内部级",
  sensitive: "敏感级",
};
function clearanceState(value, source) {
  const label = CLEARANCE_LABELS[value] || "密级待核";
  if (!CLEARANCE_LABELS[value]) return { label, suffix: "", pending: true };
  if (source === "defaulted") return { label, suffix: "（默认）", pending: true };
  if (source === "invalid_defaulted") {
    return { label, suffix: "（非法值回退）", pending: true };
  }
  return { label, suffix: "", pending: false };
}
const CONTEXT_CATEGORY_LABELS = {
  tool_automation: "工具执行",
  knowledge_qa: "知识问答",
  structured_gen: "结构生成",
  reasoning_assist: "推理辅助",
};
function contextCategoryLabel(value) {
  return CONTEXT_CATEGORY_LABELS[value] || categoryLabel(value);
}
function stage(agent) {
  if (props.disabled) return;
  emit("stage", agent);
}
function pickerGateParts(agent) {
  const parts = [];
  if (agent.referenceState === "unresolved") {
    parts.push({ text: `${agent.unresolvedReferenceCount} 项引用待核`, pending: true });
  } else if (agent.referenceState === "resolved") {
    parts.push({ text: `工具 ${agent.toolCount} · 知识 ${agent.scopeCount}`, pending: false });
  } else {
    parts.push({ text: "引用状态待核", pending: true });
  }
  const clearance = clearanceState(agent.clearance, agent.clearanceSource);
  parts.push({
    text: `${clearance.label}${clearance.suffix}`,
    pending: clearance.pending,
  });
  if (agent.reviewRequired === true) parts.push({ text: "需人工复核", pending: false });
  if (agent.reviewRequired === null) parts.push({ text: "复核待核", pending: true });
  if (agent.evidenceRequired === true) parts.push({ text: "需可核依据", pending: false });
  if (agent.evidenceRequired === null) parts.push({ text: "依据待核", pending: true });
  if (agent.mockToolCount > 0) {
    parts.push({ text: `MOCK 工具 ${agent.mockToolCount}`, pending: true });
  }
  if (agent.unknownMockToolCount > 0) {
    parts.push({ text: `工具真伪待核 ${agent.unknownMockToolCount}`, pending: true });
  }
  return parts;
}
function pickerGateText(agent) {
  return pickerGateParts(agent).map((part) => part.text).join(" · ");
}
function agentAriaLabel(agent) {
  return `选择 ${agent.name}，${categoryLabel(agent.category)}，${agent.detail}，${pickerGateText(agent)}`;
}
function focusInitial() {
  (searchEl.value || panelEl.value)?.focus();
}
function reset() {
  query.value = "";
  workType.value = "all";
}
defineExpose({ focusInitial, reset });
</script>

<style scoped>
.shell-context {
  min-width: 0;
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 88px);
  overflow: hidden;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: var(--paper-rail);
  box-shadow: var(--shadow-card);
  color: var(--ink);
}
.context-head {
  flex: none;
  padding: var(--space-3);
  border-bottom: 1px solid var(--hairline-soft);
}
.context-kicker {
  display: block;
  margin-bottom: var(--space-1);
  color: var(--ink-faint);
  font-family: var(--mono);
  font-size: var(--fs-2xs);
  letter-spacing: 0.08em;
}
.context-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}
.context-head h2 {
  margin: 0;
  font-family: var(--serif);
  font-size: var(--fs-h3);
  font-weight: 600;
}
.context-head p {
  margin: var(--space-1) 0 0;
  color: var(--ink-faint);
  font-size: var(--fs-xs);
  line-height: 1.45;
}
.context-contract {
  flex: none;
  padding: var(--space-1) var(--space-2);
  border: 1px solid var(--hairline);
  border-radius: var(--radius-pill);
  color: var(--ink-soft);
  background: var(--surface-raised);
  font-size: var(--fs-2xs);
}
.context-object {
  flex: none;
  display: flex;
  gap: var(--space-2);
  margin: var(--space-3) var(--space-3) 0;
  padding: var(--space-2);
  border: 1px solid var(--hairline-soft);
  border-radius: var(--radius-md);
  background: var(--surface-raised);
}
.context-object-icon {
  flex: none;
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-md);
  background: var(--paper-canvas-b, var(--paper-rail));
  color: var(--ink-soft);
}
.context-object-copy { min-width: 0; display: flex; flex-direction: column; gap: var(--space-1); }
.context-object-copy small { color: var(--ink-faint); font-size: var(--fs-2xs); }
.context-object-copy strong { font-size: var(--fs-sm); font-weight: 650; }
.context-object-copy > span { color: var(--ink-faint); font-size: var(--fs-2xs); line-height: 1.35; }
.context-controls { flex: none; padding: var(--space-3) var(--space-3) var(--space-2); }
.context-section-label,
.context-list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  color: var(--ink-faint);
  font-size: var(--fs-2xs);
  font-weight: 650;
  letter-spacing: 0.02em;
}
.context-count { font-weight: 500; }
.context-facets {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-2);
  margin: var(--space-2) 0;
}
.context-facet {
  width: 100%;
  min-width: 0;
  min-height: 28px;
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: 0 var(--space-2);
  border: 1px solid var(--hairline);
  border-radius: var(--radius-pill);
  background: var(--surface-raised);
  color: var(--ink-soft);
  font: inherit;
  font-size: var(--fs-xs);
  cursor: pointer;
}
.context-facet:first-child { grid-column: 1 / -1; justify-content: center; }
.context-facet.is-active {
  border-color: var(--focus-ring-clay);
  background: var(--select-tint-clay);
  color: var(--ink);
}
.context-facet:disabled { opacity: 0.45; cursor: not-allowed; }
.facet-dot { width: 6px; height: 6px; border-radius: 50%; }
.context-search-wrap {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 34px;
  box-sizing: border-box;
  padding: 0 var(--space-2);
  border: 1px solid var(--hairline);
  border-radius: var(--radius-md);
  background: var(--surface-raised);
  color: var(--ink-faint);
}
.context-search-wrap:focus-within {
  border-color: var(--focus-ring-clay);
  box-shadow: 0 0 0 2px rgba(var(--clay-rgb), 0.1);
}
.shell-context .context-search {
  min-width: 0;
  width: 100%;
  padding: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--ink);
  font: inherit;
  font-size: var(--fs-sm);
}
.shell-context .context-search::placeholder { color: var(--ink-faint); }
.context-list-head {
  flex: none;
  padding: 0 var(--space-3) var(--space-2);
  border-bottom: 1px solid var(--hairline-soft);
}
.context-agent-list {
  flex: 1 1 auto;
  min-height: 96px;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: var(--space-1) 0;
}
.context-agent {
  width: 100%;
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border: 0;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: background var(--motion-fast) var(--ease-out-soft);
}
.context-agent:hover,
.context-agent:focus-visible { background: var(--hover-tint); }
.context-agent:active { background: var(--select-tint-clay); }
.context-agent:disabled { opacity: 0.45; cursor: not-allowed; }
.ap-dot { flex: none; width: 8px; height: 8px; margin-top: var(--space-1); border-radius: 50%; }
.context-agent-main { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: var(--space-1); }
.ap-name-row { min-width: 0; display: flex; align-items: center; gap: var(--space-1); }
.ap-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--ink);
  font-size: var(--fs-sm);
  font-weight: 650;
}
.ap-maturity {
  flex: none;
  padding: 0 var(--space-1);
  border: 1px solid var(--hairline);
  border-radius: var(--radius-xs);
  color: var(--ink-mid);
  font-family: var(--mono);
  font-size: var(--fs-2xs);
}
.ap-detail {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--ink-faint);
  font-size: var(--fs-xs);
  line-height: 1.35;
}
.context-agent-relation {
  color: var(--ink-soft);
  font-size: var(--fs-2xs);
  line-height: 1.35;
}
.context-agent-relation.is-unresolved,
.context-agent-relation.is-unknown { color: var(--trust-pending); }
.context-pending-token { color: var(--trust-pending); }
.context-trust-row { display: flex; flex-wrap: wrap; gap: var(--space-1); margin-top: var(--space-1); }
.context-trust-pill {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  color: var(--ink-soft);
  font-size: var(--fs-2xs);
}
.context-trust-pill.is-pending { color: var(--trust-pending); }
.context-stage-icon { flex: none; margin-top: var(--space-1); color: var(--ink-faint); font-size: var(--fs-body); }
.context-zero { padding: var(--space-2) var(--space-3); color: var(--ink-faint); font-size: var(--fs-xs); }
.context-footer {
  flex: none;
  border-top: 1px solid var(--hairline-soft);
  background: var(--surface-raised);
}
.context-footer p {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  margin: 0;
  padding: var(--space-2) var(--space-3);
  color: var(--ink-faint);
  font-size: var(--fs-2xs);
  line-height: 1.4;
}
.context-footer p .el-icon { flex: none; margin-top: var(--space-1); }
.shell-context .context-portal {
  width: 100%;
  min-height: 34px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--space-3);
  border: 0;
  border-top: 1px solid var(--hairline-soft);
  background: transparent;
  color: var(--clay);
  font: inherit;
  font-size: var(--fs-xs);
  font-weight: 650;
  cursor: pointer;
}
.context-unavailable,
.context-loading {
  display: flex;
  gap: var(--space-2);
  margin: var(--space-3);
  padding: var(--space-2);
  border-radius: var(--radius-md);
  font-size: var(--fs-xs);
  line-height: 1.45;
}
.context-unavailable {
  align-items: flex-start;
  border: 1px solid color-mix(in srgb, var(--trust-pending) 32%, var(--hairline));
  color: var(--trust-pending);
}
.context-loading {
  align-items: center;
  border: 1px solid var(--hairline-soft);
  background: var(--select-tint-clay);
  color: var(--ink-soft);
}
.context-unavailable.is-error { color: var(--trust-fail); border-color: color-mix(in srgb, var(--trust-fail) 30%, var(--hairline)); }
.is-picker {
  max-height: min(390px, calc(100vh - var(--space-6)));
  border: 0;
  border-radius: 0;
  box-shadow: none;
  background: var(--surface-raised);
}
.is-picker .context-head { padding: var(--space-2) var(--space-2) var(--space-1); border-bottom: 0; }
.is-picker .context-kicker { margin-bottom: var(--space-1); font-size: var(--fs-2xs); }
.is-picker .context-head h2 { font-family: inherit; font-size: var(--fs-sm); font-weight: 700; }
.is-picker .context-controls { padding: var(--space-1) var(--space-2) var(--space-2); border-bottom: 1px solid var(--hairline-soft); }
.is-picker .context-section-label,
.is-picker .context-list-head { display: none; }
.is-picker .context-facets {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin: var(--space-1) 0 var(--space-2);
}
.is-picker .context-facet:first-child { grid-column: auto; }
.is-picker .context-facet { min-height: 26px; padding-inline: var(--space-2); font-size: var(--fs-2xs); }
.is-picker .context-search-wrap { min-height: 34px; }
.is-picker .context-agent-list { min-height: 0; }
.is-picker .context-agent { align-items: center; padding: var(--space-2); }
.is-picker .ap-dot { margin-top: 0; }
.is-picker .ap-name { font-size: var(--fs-body); }
.is-picker .ap-detail { font-size: var(--fs-xs); line-height: 1.25; }
.is-picker .context-agent-relation {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--fs-2xs);
}
.is-picker .context-footer p { display: none; }
.is-picker .context-portal { min-height: 36px; font-size: var(--fs-sm); }
@media (max-width: 520px) {
  .is-picker .context-facet,
  .is-picker .context-search-wrap,
  .is-picker .context-agent,
  .is-picker .context-portal { min-height: 44px; }
}
@media (prefers-reduced-motion: reduce) {
  .context-agent,
  .context-facet { transition: none; }
  .context-loading .is-loading { animation: none; }
}
</style>
