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
            placeholder="搜索会话、消息、任务、产物、Agent…"
            maxlength="128"
            autocomplete="off"
            spellcheck="false"
            role="combobox"
            aria-autocomplete="list"
            aria-controls="qs-results"
            aria-expanded="true"
            :aria-activedescendant="activeOptionId"
          />
        </div>

        <div
          id="qs-results"
          ref="resultsRef"
          class="qs-results"
          role="listbox"
          aria-label="搜索结果"
          :aria-busy="loading || (searchMode && !allSearchSettled)"
        >
          <!-- 骨架语言对齐全站（W7，低优先级样式项）：面板每次打开都是新挂载/
               重拉（关闭即整体卸载），不是同页静默轮询，不需要 A3 的 everLoaded
               防闪烁——直接绑 loading 即可。骨架根是 aria-hidden，必须保留
               视觉隐藏的「加载中…」status 文本给读屏（Codex R0 P2）。 -->
          <div v-if="loading && !searchMode" class="qs-loading" role="status">
            <span class="qs-loading-sr">加载中…</span>
            <SkeletonBlock v-for="i in 4" :key="i" height="46px" />
          </div>
          <template v-else>
            <!-- 诚实降级条（批次五 C2）：后端搜索源失败≠没有结果——必须让用户
                 知道下面的清单可能不完整；真失败=trust-fail 红槽，role=alert 播报。 -->
            <!-- 分级口径（Codex R0 审 P2）：单源失败≠服务不可用——1-2 源失败说
                 「部分」，3/3 全失败才说「全部」；空态文案同一分级（见下）。 -->
            <div v-if="fetchDegraded && !searchMode" class="qs-degraded" role="alert">
              {{ fetchFailedCount === 3 ? "后端搜索请求全部失败——以下显示可能不完整" : "部分结果不可用（后端搜索请求失败）——以下显示可能不完整" }}
            </div>
            <div
              v-if="searchMode && allSearchSettled && searchFailedCount > 0"
              class="qs-degraded"
              role="status"
              aria-live="polite"
            >{{ searchFailedCount }} 个检索来源暂不可用；其余来源结果仍可打开</div>
            <div v-if="shortQuery" class="qs-query-hint" role="status">至少输入 2 个字符，才会进行完整检索；当前只筛选最近项与 Agent</div>
            <template v-for="group in renderGroups" :key="group.key">
              <div v-if="group.items.length || group.showState" class="qs-group">
                <div class="qs-group-label">
                  <span>{{ group.label }}</span>
                  <span v-if="group.hasMore" class="qs-more-mark">还有更多</span>
                </div>
                <div v-if="group.pending" class="qs-scope-state" role="status">
                  <span class="qs-pending-dot" aria-hidden="true"></span>正在查找…
                </div>
                <div v-if="group.error" class="qs-scope-state is-error">
                  此来源暂不可用：{{ group.error }}
                </div>
                <div
                  v-for="entry in group.items"
                  :key="group.key + '-' + entry.item.id"
                  class="qs-item"
                  :class="{ 'is-selected': entry.globalIndex === selectedIndex }"
                  :id="`qs-option-${entry.globalIndex}`"
                  role="option"
                  :aria-selected="entry.globalIndex === selectedIndex"
                  @click="activate(group.key, entry.item)"
                  @mouseenter="selectIndex(entry.globalIndex)"
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
                  <span
                    v-if="(group.key === 'task' || group.key === 'artifact') && entry.item.content_withheld === true"
                    class="qs-item-withheld"
                    :class="{ 'is-unverified': entry.item.data_classification == null }"
                  >{{ withheldLabel(entry.item) }}</span>
                </div>
                <div
                  v-if="group.showState && !group.pending && !group.error && !group.items.length"
                  class="qs-scope-state"
                >此来源没有匹配结果</div>
                <div
                  v-if="group.hasMore"
                  class="qs-more-note"
                >还有更多结果，请继续细化关键词</div>
              </div>
            </template>
            <div v-if="!flatItems.length && !searchMode" class="qs-empty">{{ fetchFailedCount === 3 ? "搜索服务不可用（后端请求失败）——请稍后重试" : (fetchDegraded ? "没有匹配结果（部分来源不可用，结果可能不完整）" : "没有匹配结果") }}</div>
          </template>
        </div>

        <div class="qs-footer">↑↓ 选择 · ↵ 打开 · esc 关闭</div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
// ⌘K 快速切换面板：空查询保留轻量最近会话/任务/Agent；有效查询改走四轴
// 服务端寻址（会话/消息/任务/产物），Agent 仍使用本地注册表过滤。每一轴独立
// 披露 pending/error/empty，后端故障绝不伪装成“没有结果”。
import { ref, reactive, computed, watch, onMounted, onUnmounted, nextTick } from "vue";
import { useRouter } from "vue-router";
import { listConversations } from "../api/conversations";
import { listTasks } from "../api/tasks";
import { listAgents } from "../api/agents";
import { searchAddresses } from "../api/search.js";
import { statusLabel, taskLampColor, taskDisplayName, formatClockCompact } from "../utils/format";
import {
  buildSearchResultRoute,
  isSearchableQuery,
  mergeSearchItems,
  normalizeSearchQuery,
  reconcileSearchSelection,
  searchSelectionKey,
} from "../utils/searchCore.js";
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
const selectedKey = ref("");
const inputRef = ref(null);
const resultsRef = ref(null);

const conversations = ref([]);
const tasks = ref([]);
const agents = ref([]);
const agentsLoaded = ref(false);
const agentLoadError = ref("");

const SERVER_SCOPE_META = Object.freeze([
  { key: "conversation", label: "会话" },
  { key: "message", label: "消息" },
  { key: "task", label: "任务" },
  { key: "artifact", label: "产物" },
]);
const newScopeState = () => ({
  items: [],
  pending: false,
  error: "",
  hasMore: false,
  nextCursor: null,
});
const scopeStates = reactive(Object.fromEntries(
  SERVER_SCOPE_META.map(({ key }) => [key, newScopeState()]),
));
const normalizedQuery = computed(() => normalizeSearchQuery(query.value));
const searchMode = computed(() => isSearchableQuery(normalizedQuery.value));
const shortQuery = computed(() => [...normalizedQuery.value].length === 1);
const serverSearchSettled = computed(() =>
  SERVER_SCOPE_META.every(({ key }) => scopeStates[key].pending !== true)
);
const serverSearchFailedCount = computed(() =>
  SERVER_SCOPE_META.filter(({ key }) => Boolean(scopeStates[key].error)).length
);
const allSearchSettled = computed(() => serverSearchSettled.value && agentsLoaded.value);
const searchFailedCount = computed(() =>
  serverSearchFailedCount.value + (agentLoadError.value ? 1 : 0)
);

// 会话标题：与 App.vue 左栏 convoTitle 同一口径（未接住会话前缀「未接住」）。
function convoTitle(c) {
  if (c.title) return c.title;
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
  if (type === "conversation") {
    return item.kind === "conversation" ? `会话 ${item.id.slice(0, 8)}` : convoTitle(item);
  }
  if (type === "message") return item.snippet || `消息 ${item.id.slice(0, 8)}`;
  if (type === "task") return taskDisplayName(item, agentNameById.value);
  if (type === "artifact") return item.filename;
  return item.name; // agent
}
function itemSub(type, item) {
  if (type === "conversation") {
    if (item.kind === "conversation") {
      return [item.agent_id, item.status, formatClockCompact(item.created_at, todayKey.value)]
        .filter((part) => part && part !== "—")
        .join(" · ");
    }
    return `${item.created_by || "你"} · ${item.id.slice(0, 8)}`;
  }
  if (type === "message") {
    const speaker = item.role === "user" ? "你的消息" : "Agent 回复";
    return [speaker, item.conversation_agent_id, formatClockCompact(item.created_at, todayKey.value)]
      .filter((part) => part && part !== "—")
      .join(" · ");
  }
  // 任务副行带紧凑时钟（3-lens 可用性镜头 P2）：同 Agent 多个缺名任务标题
  // 相同，时钟是 ⌘K 结果行的消歧锚。
  if (type === "task") {
    return [item.agent_id, formatClockCompact(item.created_at, todayKey.value)]
      .filter((p) => p && p !== "—")
      .join(" · ");
  }
  if (type === "artifact") {
    return [item.task_name || item.task_id.slice(0, 8), formatClockCompact(item.created_at, todayKey.value)]
      .filter((part) => part && part !== "—")
      .join(" · ");
  }
  return item.id; // agent
}

function withheldLabel(item) {
  return item.data_classification == null ? "密级未核 · 内容不展开" : "内容受限";
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

// P2.4 服务端结果负责跨窗口精确寻址；最近任务仍补一条“眼见即可搜”通道：
// 用户输入当前注册表显示名时，不能因为后端只认稳定 agent_id 而丢掉已存在的
// 本地可见任务。补充项只来自同一已授权 listTasks 投影，且按稳定 task id 去重。
const localDisplayNameTaskMatches = computed(() => {
  if (!searchMode.value) return [];
  const needle = normalizedQuery.value.toLowerCase();
  return tasks.value
    .filter((task) => taskDisplayName(task, agentNameById.value).toLowerCase().includes(needle))
    .map((task) => {
      const classification = ["internal", "sensitive"].includes(task.data_classification)
        ? task.data_classification
        : null;
      return {
        ...task,
        kind: "task",
        data_classification: classification,
        content_withheld: classification !== "internal",
      };
    });
});
const taskSearchItems = computed(() => mergeSearchItems(
  scopeStates.task.items,
  localDisplayNameTaskMatches.value,
  6,
));

const groups = computed(() => {
  if (!searchMode.value) {
    return [
      { key: "conversation", label: "会话", items: filteredConversations.value, showState: false },
      { key: "task", label: "任务", items: filteredTasks.value, showState: false },
      { key: "agent", label: "Agent", items: filteredAgents.value, showState: false },
    ];
  }
  return [
    ...SERVER_SCOPE_META.map(({ key, label }) => ({
      key,
      label,
      items: key === "task" ? taskSearchItems.value : scopeStates[key].items,
      pending: scopeStates[key].pending,
      error: scopeStates[key].error,
      hasMore: scopeStates[key].hasMore,
      showState: true,
    })),
    {
      key: "agent",
      label: "Agent",
      items: filteredAgents.value,
      pending: loading.value && !agentsLoaded.value,
      error: agentLoadError.value,
      hasMore: false,
      showState: true,
    },
  ];
});

// 附上跨组连续的全局下标，供键盘 ↑↓ 在三组间无缝移动。
const renderGroups = computed(() => {
  let idx = 0;
  return groups.value.map((g) => {
    const items = g.items.map((item) => ({ item, globalIndex: idx++ }));
    return { ...g, items };
  });
});
const flatItems = computed(() => groups.value.flatMap((g) => g.items.map((item) => ({ type: g.key, item }))));
const flatSelectionKeys = computed(() =>
  flatItems.value.map((entry) => searchSelectionKey(entry.type, entry.item))
);
// aria-activedescendant 只能指向当前真实挂载的 option。面板二次打开时旧结果仍在
// 内存，但 loading 分支会卸载全部 option；若只看 flatItems，读屏会收到悬空 id。
const activeOptionId = computed(() => {
  if (loading.value || selectedIndex.value < 0 || selectedIndex.value >= flatItems.value.length) {
    const resultsAreHidden = loading.value && !searchMode.value;
    const selectionIsInvalid = selectedIndex.value < 0 || selectedIndex.value >= flatItems.value.length;
    if (resultsAreHidden || selectionIsInvalid) return undefined;
  }
  return `qs-option-${selectedIndex.value}`;
});

function selectIndex(index) {
  if (index < 0 || index >= flatItems.value.length) return;
  selectedIndex.value = index;
  selectedKey.value = flatSelectionKeys.value[index];
}

watch(
  flatSelectionKeys,
  (keys) => {
    const next = reconcileSearchSelection(keys, selectedKey.value);
    selectedIndex.value = next.index;
    selectedKey.value = next.key;
  },
  { immediate: true },
);

let searchTimer = null;
let searchSeq = 0;

function clearSearchTimer() {
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = null;
}

function resetServerSearch({ pending = false } = {}) {
  for (const { key } of SERVER_SCOPE_META) {
    Object.assign(scopeStates[key], newScopeState(), { pending });
  }
}

async function runServerSearch(searchQuery, seq) {
  const oneScope = async ({ key }) => {
    try {
      const page = await searchAddresses({ q: searchQuery, scope: key, limit: 6 });
      if (seq !== searchSeq || normalizedQuery.value !== searchQuery) return;
      Object.assign(scopeStates[key], {
        items: page.items,
        pending: false,
        error: "",
        hasMore: page.has_more,
        nextCursor: page.next_cursor,
      });
    } catch (err) {
      if (seq !== searchSeq || normalizedQuery.value !== searchQuery) return;
      Object.assign(scopeStates[key], {
        items: [],
        pending: false,
        error: err?.detail || err?.message || "请求失败",
        hasMore: false,
        nextCursor: null,
      });
    }
  };
  await Promise.all(SERVER_SCOPE_META.map(oneScope));
}

watch(query, () => {
  selectedIndex.value = 0;
  selectedKey.value = "";
  clearSearchTimer();
  const seq = ++searchSeq;
  if (!searchMode.value) {
    resetServerSearch();
    return;
  }
  const searchQuery = normalizedQuery.value;
  // Debounce 窗口也属于“正在查找”，不能先闪一帧“无结果”。
  resetServerSearch({ pending: true });
  searchTimer = setTimeout(() => {
    searchTimer = null;
    void runServerSearch(searchQuery, seq);
  }, 220);
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
  agentsLoaded.value = false;
  agentLoadError.value = "";
  let failed = 0;
  let agentFailure = "";
  const grab = (source, p) =>
    p.catch((err) => {
      failed += 1;
      if (source === "agent") {
        agentFailure = err?.detail || err?.message || "请求失败";
      }
      return null;
    });
  try {
    const [convs, tks, ags] = await Promise.all([
      grab("conversation", listConversations({ visibility: "visible" })),
      grab("task", listTasks({ limit: 50 })),
      grab("agent", listAgents()),
    ]);
    if (seq !== fetchSeq) return;
    conversations.value = convs || [];
    tasks.value = tks || [];
    agents.value = ags || [];
    agentsLoaded.value = true;
    agentLoadError.value = agentFailure;
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
  clearSearchTimer();
  searchSeq += 1;
  selectedKey.value = "";
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
    selectedKey.value = flatSelectionKeys.value[0] || "";
    nextTick(() => inputRef.value?.focus());
    fetchAll();
  }
);

function activate(type, item) {
  // 导航离场不回还（3-lens 可用性 P2）：选中结果=用户去了新页面，焦点该落在
  // 新页面而不是被 close watcher 拽回侧栏搜索钮；回还只属于 Escape/点遮罩
  // 这类「放弃关闭」（⑭C6″ 实证咬合）。
  focusReturnEl = null;
  if (["conversation", "message", "task", "artifact"].includes(type)) {
    router.push(buildSearchResultRoute(type, { ...item, kind: type }));
  }
  else if (type === "agent") router.push("/portal");
  close();
}

function moveSelection(delta) {
  const len = flatItems.value.length;
  if (!len) return;
  selectIndex((selectedIndex.value + delta + len) % len);
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
onUnmounted(() => {
  clearSearchTimer();
  searchSeq += 1;
  window.removeEventListener("keydown", onWindowKeydown);
});
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
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.8px;
  text-transform: uppercase;
  color: var(--ink-faint);
  padding: 10px 10px 4px;
}
.qs-more-mark {
  font-weight: 500;
  letter-spacing: 0;
  text-transform: none;
}
.qs-query-hint,
.qs-scope-state {
  padding: 8px 10px;
  color: var(--ink-faint);
  font-size: 12px;
}
.qs-query-hint {
  border-bottom: 1px solid var(--hairline);
}
.qs-scope-state {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.qs-scope-state.is-error {
  color: var(--trust-fail);
}
.qs-pending-dot {
  width: 6px;
  height: 6px;
  flex: none;
  border-radius: 50%;
  background: var(--clay);
  animation: qs-pending-pulse 1.2s var(--ease-out-soft) infinite;
}
@keyframes qs-pending-pulse {
  0%, 100% { opacity: 0.35; }
  50% { opacity: 1; }
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
.qs-item-withheld {
  flex: none;
  color: var(--ink-faint);
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}
.qs-item-withheld.is-unverified {
  color: var(--trust-pending);
}
.qs-empty {
  padding: 24px 12px;
  text-align: center;
  color: var(--ink-faint);
  font-size: 13px;
}
.qs-more-note {
  padding: 4px 10px 8px;
  color: var(--ink-faint);
  font-size: 12px;
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
  .qs-pending-dot {
    animation: none;
    opacity: 1;
  }
}
@media (max-width: 640px) {
  .qs-overlay {
    align-items: flex-start;
    padding: 8px;
  }
  .qs-panel {
    width: 100%;
    max-width: 100%;
    max-height: calc(100dvh - 16px);
    border-radius: 10px;
  }
  .qs-footer {
    padding-bottom: max(8px, env(safe-area-inset-bottom));
  }
}
</style>
