<template>
  <Transition name="qs-fade">
    <div v-if="isOpen" class="qs-overlay" @click="close">
      <div class="qs-panel" role="dialog" aria-modal="true" aria-label="快速切换" @click.stop>
        <div class="qs-search">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/></svg>
          <input
            ref="inputRef"
            v-model="query"
            class="qs-input"
            type="text"
            placeholder="搜索会话、任务、Agent…"
            autocomplete="off"
            spellcheck="false"
          />
        </div>

        <div class="qs-results" ref="resultsRef">
          <div v-if="loading" class="qs-loading">加载中…</div>
          <template v-else>
            <template v-for="group in renderGroups" :key="group.key">
              <div v-if="group.items.length" class="qs-group">
                <div class="qs-group-label">{{ group.label }}</div>
                <div
                  v-for="entry in group.items"
                  :key="group.key + '-' + entry.item.id"
                  class="qs-item"
                  :class="{ 'is-selected': entry.globalIndex === selectedIndex }"
                  @click="activate(group.key, entry.item)"
                  @mouseenter="selectedIndex = entry.globalIndex"
                >
                  <span class="qs-item-main">
                    <span class="qs-item-title">{{ itemTitle(group.key, entry.item) }}</span>
                    <span class="qs-item-sub">{{ itemSub(group.key, entry.item) }}</span>
                  </span>
                  <span
                    v-if="group.key === 'task'"
                    class="qs-item-status"
                    :style="{ color: taskLampColor(entry.item.status) }"
                  >{{ statusLabel(entry.item.status) }}</span>
                </div>
              </div>
            </template>
            <div v-if="!flatItems.length" class="qs-empty">没有匹配结果</div>
          </template>
        </div>

        <div class="qs-footer">↑↓ 选择 · ↵ 打开 · esc 关闭</div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
// ⌘K 快速切换面板（Claude Desktop 检索态移植）：全局热键唤出，并行拉会话/任务/Agent
// 三源做客户端 substring 过滤，键盘上下+回车直达。App.vue 只挂载本组件，热键监听
// 与数据/跳转逻辑全封在这里，不外溢到 App.vue。
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from "vue";
import { useRouter } from "vue-router";
import { listConversations } from "../api/conversations";
import { listTasks } from "../api/tasks";
import { listAgents } from "../api/agents";
import { statusLabel, taskLampColor } from "../utils/format";
import { statusCenter, closeCenter } from "../stores/statusCenter";

const router = useRouter();

const isOpen = ref(false);
const query = ref("");
const loading = ref(false);
const selectedIndex = ref(0);
const inputRef = ref(null);
const resultsRef = ref(null);

const conversations = ref([]);
const tasks = ref([]);
const agents = ref([]);

// 会话标题：与 App.vue 左栏 convoTitle 同一口径（未接住会话前缀「未接住」）。
function convoTitle(c) {
  const r = c.recommendation;
  if (r && r.decision === "orchestrate" && r.goal) return r.goal;
  if (r && r.decision === "refuse" && r.reason) return "（未接住）" + r.reason;
  return `与 ${c.created_by || "你"} 的对话`;
}

function itemTitle(type, item) {
  if (type === "conversation") return convoTitle(item);
  if (type === "task") return item.name || item.id.slice(0, 12);
  return item.name; // agent
}
function itemSub(type, item) {
  if (type === "conversation") return `${item.created_by || "你"} · ${item.id.slice(0, 8)}`;
  if (type === "task") return item.agent_id || "";
  return item.id; // agent
}

// 客户端 substring 过滤：名称/goal/agent_id/id 前 8 位，任一命中即算匹配。
function matches(fields) {
  const q = query.value.trim().toLowerCase();
  if (!q) return true;
  return fields.some((f) => f && String(f).toLowerCase().includes(q));
}

const filteredConversations = computed(() =>
  conversations.value.filter((c) => matches([convoTitle(c), c.created_by, c.id.slice(0, 8)])).slice(0, 6)
);
const filteredTasks = computed(() =>
  tasks.value.filter((t) => matches([t.name, t.agent_id, t.id.slice(0, 8)])).slice(0, 6)
);
const filteredAgents = computed(() =>
  agents.value.filter((a) => matches([a.name, a.id, a.id.slice(0, 8)])).slice(0, 6)
);

const groups = computed(() => [
  { key: "conversation", label: "会话", items: filteredConversations.value },
  { key: "task", label: "任务", items: filteredTasks.value },
  { key: "agent", label: "Agent", items: filteredAgents.value },
]);

// 附上跨组连续的全局下标，供键盘 ↑↓ 在三组间无缝移动。
const renderGroups = computed(() => {
  let idx = 0;
  return groups.value.map((g) => {
    const items = g.items.map((item) => ({ item, globalIndex: idx++ }));
    return { ...g, items };
  });
});
const flatItems = computed(() => groups.value.flatMap((g) => g.items.map((item) => ({ type: g.key, item }))));

watch(query, () => {
  selectedIndex.value = 0;
});

// 键盘 ↑↓ 跨组连续移动时，把选中项滚入可视区（长列表/末组不被面板裁切）；
// nextTick 等 is-selected 类先落到新 DOM 节点上再查询。
watch(selectedIndex, () => {
  nextTick(() => {
    resultsRef.value?.querySelector(".qs-item.is-selected")?.scrollIntoView({ block: "nearest" });
  });
});

async function fetchAll() {
  loading.value = true;
  try {
    const [convs, tks, ags] = await Promise.all([
      listConversations().catch(() => []),
      listTasks({ limit: 50 }).catch(() => []),
      listAgents().catch(() => []),
    ]);
    conversations.value = convs;
    tasks.value = tks;
    agents.value = ags;
  } finally {
    loading.value = false;
  }
}

async function open() {
  // 状态中心抽屉（el-drawer z-index 2000+）开着时先关掉——否则 ⌘K 面板(200)
  // 被抽屉遮罩盖住而焦点已被偷进不可见输入框。任意时刻只留一个顶层模态。
  if (statusCenter.open) closeCenter();
  isOpen.value = true;
  selectedIndex.value = 0;
  await nextTick();
  inputRef.value?.focus();
  fetchAll();
}
function close() {
  isOpen.value = false;
  query.value = "";
}

function activate(type, item) {
  if (type === "conversation") router.push(`/workbench/${item.id}`);
  else if (type === "task") router.push(`/tasks/${item.id}`);
  else if (type === "agent") router.push("/portal");
  close();
}

function moveSelection(delta) {
  const len = flatItems.value.length;
  if (!len) return;
  selectedIndex.value = (selectedIndex.value + delta + len) % len;
}

// 全局热键：(⌘/Ctrl)+K 开关面板；面板打开时 Esc 关闭、↑↓ 选中、Enter 跳转。
function onWindowKeydown(e) {
  // IME 组合输入中（中文拼音等）：Enter/方向键是候选词操作，不是面板指令。
  if (e.isComposing) return;
  const key = e.key.toLowerCase();
  if ((e.metaKey || e.ctrlKey) && key === "k") {
    e.preventDefault();
    if (isOpen.value) close();
    else open();
    return;
  }
  if (!isOpen.value) return;
  if (e.key === "Escape") {
    e.preventDefault();
    close();
  } else if (e.key === "ArrowDown") {
    e.preventDefault();
    moveSelection(1);
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    moveSelection(-1);
  } else if (e.key === "Enter") {
    e.preventDefault();
    const entry = flatItems.value[selectedIndex.value];
    if (entry) activate(entry.type, entry.item);
  }
}

onMounted(() => window.addEventListener("keydown", onWindowKeydown));
onUnmounted(() => window.removeEventListener("keydown", onWindowKeydown));
</script>

<style scoped>
.qs-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  justify-content: center;
  padding-top: 12vh;
  background: rgba(43, 38, 34, 0.32);
}
.qs-panel {
  width: 560px;
  max-width: calc(100vw - 32px);
  max-height: 70vh;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  background: var(--paper-surface);
  border: 1px solid var(--hairline);
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(43, 38, 34, 0.12), 0 24px 64px rgba(43, 38, 34, 0.18);
  overflow: hidden;
}
.qs-search {
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--hairline);
  color: var(--ink-faint);
}
.qs-input {
  flex: 1 1 auto;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  font-family: inherit;
  font-size: 14.5px;
  color: var(--ink);
}
.qs-input::placeholder {
  color: var(--ink-faint);
}
.qs-results {
  flex: 1 1 auto;
  overflow-y: auto;
  padding: 6px 8px;
}
.qs-results::-webkit-scrollbar {
  width: 6px;
}
.qs-results::-webkit-scrollbar-thumb {
  background: var(--hairline);
  border-radius: 6px;
}
.qs-group-label {
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.8px;
  text-transform: uppercase;
  color: var(--ink-faint);
  padding: 10px 10px 4px;
}
.qs-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  border-left: 3px solid transparent;
  cursor: pointer;
  transition: background var(--motion-fast) var(--ease-out-soft), border-color var(--motion-fast) var(--ease-out-soft);
}
.qs-item.is-selected {
  background: rgba(193, 95, 60, 0.08);
  border-left-color: var(--clay);
}
.qs-item-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 1px;
}
.qs-item-title {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.qs-item-sub {
  font-size: 11.5px;
  color: var(--ink-faint);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.qs-item-status {
  flex: none;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}
.qs-empty,
.qs-loading {
  padding: 24px 12px;
  text-align: center;
  color: var(--ink-faint);
  font-size: 13px;
}
.qs-footer {
  flex: none;
  padding: 8px 16px;
  border-top: 1px solid var(--hairline);
  font-size: 11px;
  color: var(--ink-faint);
  background: var(--paper-rail);
}

.qs-fade-enter-active,
.qs-fade-leave-active {
  transition: opacity 0.14s var(--ease-lift);
}
.qs-fade-enter-from,
.qs-fade-leave-to {
  opacity: 0;
}
/* 入场用 --ease-spring 微弹（幅度不变，仍是 translateY(-8px) scale(0.98)→原位），
 * 退出保留原软出，避免关闭时的回弹显得拖沓。 */
.qs-fade-enter-active .qs-panel {
  transition: transform var(--motion-med) var(--ease-spring), opacity 0.16s var(--ease-lift);
}
.qs-fade-leave-active .qs-panel {
  transition: transform 0.16s var(--ease-lift), opacity 0.16s var(--ease-lift);
}
.qs-fade-enter-from .qs-panel,
.qs-fade-leave-to .qs-panel {
  transform: translateY(-8px) scale(0.98);
  opacity: 0;
}
@media (prefers-reduced-motion: reduce) {
  .qs-fade-enter-active,
  .qs-fade-leave-active,
  .qs-fade-enter-active .qs-panel,
  .qs-fade-leave-active .qs-panel {
    transition: none;
  }
  .qs-item {
    transition: none;
  }
}
</style>
