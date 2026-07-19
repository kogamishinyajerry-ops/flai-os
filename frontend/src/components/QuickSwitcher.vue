<template>
  <Transition name="qs-fade">
    <div v-if="quickSwitcher.open" class="qs-overlay" @click="close">
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
            role="combobox"
            aria-autocomplete="list"
            aria-controls="qs-results"
            aria-expanded="true"
            :aria-activedescendant="activeOptionId"
          />
        </div>

        <div id="qs-results" class="qs-results" ref="resultsRef" role="listbox" aria-label="搜索结果">
          <!-- 骨架语言对齐全站（W7，低优先级样式项）：面板每次打开都是新挂载/
               重拉（关闭即整体卸载），不是同页静默轮询，不需要 A3 的 everLoaded
               防闪烁——直接绑 loading 即可。骨架根是 aria-hidden，必须保留
               视觉隐藏的「加载中…」status 文本给读屏（Codex R0 P2）。 -->
          <div v-if="loading" class="qs-loading" role="status">
            <span class="qs-loading-sr">加载中…</span>
            <SkeletonBlock v-for="i in 4" :key="i" height="46px" />
          </div>
          <template v-else>
            <!-- 诚实降级条（批次五 C2）：后端搜索源失败≠没有结果——必须让用户
                 知道下面的清单可能不完整；真失败=trust-fail 红槽，role=alert 播报。 -->
            <!-- 分级口径（Codex R0 审 P2）：单源失败≠服务不可用——1-2 源失败说
                 「部分」，3/3 全失败才说「全部」；空态文案同一分级（见下）。 -->
            <div v-if="fetchDegraded" class="qs-degraded" role="alert">
              {{ fetchFailedCount === 3 ? "后端搜索请求全部失败——以下显示可能不完整" : "部分结果不可用（后端搜索请求失败）——以下显示可能不完整" }}
            </div>
            <template v-for="group in renderGroups" :key="group.key">
              <div v-if="group.items.length" class="qs-group">
                <div class="qs-group-label">{{ group.label }}</div>
                <div
                  v-for="entry in group.items"
                  :key="group.key + '-' + entry.item.id"
                  class="qs-item"
                  :class="{ 'is-selected': entry.globalIndex === selectedIndex }"
                  :id="`qs-option-${entry.globalIndex}`"
                  role="option"
                  :aria-selected="entry.globalIndex === selectedIndex"
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
            <div v-if="!flatItems.length" class="qs-empty">{{ fetchFailedCount === 3 ? "搜索服务不可用（后端请求失败）——请稍后重试" : (fetchDegraded ? "没有匹配结果（部分来源不可用，结果可能不完整）" : "没有匹配结果") }}</div>
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
import { statusLabel, taskLampColor, taskDisplayName, formatClockCompact } from "../utils/format";
import { useTodayKey } from "../composables/useTodayKey";
import { statusCenter, closeCenter } from "../stores/statusCenter";
import { quickSwitcher, openQuickSwitcher, closeQuickSwitcher } from "../stores/quickSwitcher";
import SkeletonBlock from "./SkeletonBlock.vue";

const router = useRouter();

// 响应式日界（⌘K 常驻挂载于 App 根，跨午夜后任务副行时钟同日判据需自翻页）。
const todayKey = useTodayKey();

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

// 任务标题人话化（批次四 Q1）：⌘K 面板已并行拉了 agents 三源之一，直接用它
// 建 id→name 映射喂 taskDisplayName SSOT——零新增网络调用；agents 未返回/失败
// 时映射为空，SSOT 自回退 id 切片。
const agentNameById = computed(() => {
  const m = {};
  for (const a of agents.value) {
    if (a && a.id && a.name) m[a.id] = a.name;
  }
  return m;
});

function itemTitle(type, item) {
  if (type === "conversation") return convoTitle(item);
  if (type === "task") return taskDisplayName(item, agentNameById.value);
  return item.name; // agent
}
function itemSub(type, item) {
  if (type === "conversation") return `${item.created_by || "你"} · ${item.id.slice(0, 8)}`;
  // 任务副行带紧凑时钟（3-lens 可用性镜头 P2）：同 Agent 多个缺名任务标题
  // 相同，时钟是 ⌘K 结果行的消歧锚。
  if (type === "task") {
    return [item.agent_id, formatClockCompact(item.created_at, todayKey.value)]
      .filter((p) => p && p !== "—")
      .join(" · ");
  }
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
  // 眼见即可搜（Codex R0 P2）：结果行标题已是 taskDisplayName 人话称呼，
  // 匹配域必须含同一 SSOT 产出——否则用户照着看到的注册表显示名打字反而搜不到。
  tasks.value.filter((t) => matches([taskDisplayName(t, agentNameById.value), t.agent_id, t.id.slice(0, 8)])).slice(0, 6)
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
// aria-activedescendant 只能指向当前真实挂载的 option。面板二次打开时旧结果仍在
// 内存，但 loading 分支会卸载全部 option；若只看 flatItems，读屏会收到悬空 id。
const activeOptionId = computed(() => {
  if (loading.value || selectedIndex.value < 0 || selectedIndex.value >= flatItems.value.length) {
    return undefined;
  }
  return `qs-option-${selectedIndex.value}`;
});

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

// 拉取代数守卫（Codex R0 P2，与父页「轮询整包作废」同律）：面板快开快关再开
// 会并发两轮 fetchAll，慢的旧响应后到会覆盖新数据——只认最新一代的回写。
// 诚实降级（批次五 C2）：三源任一失败必须亮「结果可能不完整」——旧实现
// .catch(()=>[]) 把后端故障伪装成「没有匹配结果」，故障与真无结果在 UI 上
// 不可区分（诚实地板violation）。失败源计数落 fetchDegraded，空态文案随之切换。
let fetchSeq = 0;
const fetchDegraded = ref(false);
const fetchFailedCount = ref(0); // 分级口径（Codex R0 审 P2）：3=全失败，1-2=部分
async function fetchAll() {
  const seq = ++fetchSeq;
  loading.value = true;
  let failed = 0;
  const grab = (p) =>
    p.catch(() => {
      failed += 1;
      return null;
    });
  try {
    const [convs, tks, ags] = await Promise.all([
      grab(listConversations()),
      grab(listTasks({ limit: 50 })),
      grab(listAgents()),
    ]);
    if (seq !== fetchSeq) return;
    conversations.value = convs || [];
    tasks.value = tks || [];
    agents.value = ags || [];
    fetchDegraded.value = failed > 0;
    fetchFailedCount.value = failed;
  } finally {
    if (seq === fetchSeq) loading.value = false;
  }
}

function open() {
  openQuickSwitcher();
}
function close() {
  closeQuickSwitcher();
  query.value = "";
}

// 打开态的副作用（重置选中/聚焦输入框/拉数据）收在这一处 watch，而不是塞进
// open()：面板可能被 open() 之外的入口唤起（如 App.vue 侧栏「搜索」按钮直
// 接调 openQuickSwitcher），watch store.open 保证不管哪条路径打开都补齐同一套
// 副作用；关状态中心抽屉的互斥逻辑同理搬进来统一生效。
// 焦点回还（批次五 C6，WCAG 焦点管理）：面板打开偷走焦点，关闭必须送回
// 触发元素——键盘用户不落回 body 从头 Tab。跨模态互斥关闭（closeCenter）
// 不参与回还：那是让位不是归位。
let focusReturnEl = null;
watch(
  () => quickSwitcher.open,
  (isOpen) => {
    if (!isOpen) {
      const el = focusReturnEl;
      focusReturnEl = null;
      if (el && typeof el.focus === "function" && document.contains(el)) {
        nextTick(() => el.focus());
      }
      return;
    }
    focusReturnEl = document.activeElement;
    // 状态中心抽屉（el-drawer z-index 2000+）开着时先关掉——否则 ⌘K 面板(200)
    // 被抽屉遮罩盖住而焦点已被偷进不可见输入框。任意时刻只留一个顶层模态。
    // suppressFocusReturn：让位不是归位——不置旗的话 SC 关闭回还的 nextTick
    // 排在本面板聚焦之后，焦点会被抢回 dock pill（⑭C6′ 实证咬合）。
    if (statusCenter.open) {
      statusCenter.suppressFocusReturn = true;
      closeCenter();
    }
    selectedIndex.value = 0;
    nextTick(() => inputRef.value?.focus());
    fetchAll();
  }
);

function activate(type, item) {
  // 导航离场不回还（3-lens 可用性 P2）：选中结果=用户去了新页面，焦点该落在
  // 新页面而不是被 close watcher 拽回侧栏搜索钮；回还只属于 Escape/点遮罩
  // 这类「放弃关闭」（⑭C6″ 实证咬合）。
  focusReturnEl = null;
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
    if (quickSwitcher.open) close();
    else open();
    return;
  }
  if (!quickSwitcher.open) return;
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
  background: var(--scrim-backdrop);
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
  box-shadow: var(--shadow-hero);
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
.qs-input:focus-visible {
  outline: 2px solid var(--focus-ring-clay);
  outline-offset: 2px;
  border-radius: var(--radius-xs);
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
  background: var(--select-tint-clay);
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
.qs-empty {
  padding: 24px 12px;
  text-align: center;
  color: var(--ink-faint);
  font-size: 13px;
}
/* 诚实降级条（批次五 C2）：真失败=trust-fail 红槽（信任色锁），安静小字不打断检索。 */
.qs-degraded {
  padding: 8px 12px 4px;
  color: var(--trust-fail);
  font-size: 12px;
}
.qs-loading {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
}
/* 读屏专用（视觉裁剪不显示，AT 可读）：repo 无全局 sr-only，本地最小实现。 */
.qs-loading-sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
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
  transition: opacity var(--motion-fast) var(--ease-out-soft);
}
.qs-fade-enter-from,
.qs-fade-leave-to {
  opacity: 0;
}
/* 入场用 --ease-spring 微弹（幅度不变，仍是 translateY(-8px) scale(0.98)→原位），
 * 退出保留原软出，避免关闭时的回弹显得拖沓。 */
.qs-fade-enter-active .qs-panel {
  transition: transform var(--motion-med) var(--ease-spring), opacity var(--motion-fast) var(--ease-out-soft);
}
.qs-fade-leave-active .qs-panel {
  transition: transform var(--motion-fast) var(--ease-out-soft), opacity var(--motion-fast) var(--ease-out-soft);
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
