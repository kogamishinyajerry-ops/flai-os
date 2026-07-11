<template>
  <div class="app-shell" :class="{ 'sidebar-open': sidebarOpen }">
    <!-- 窄屏汉堡：<860px 侧栏收起，靠它唤出抽屉（P2-7：不再让导航凭空消失）。 -->
    <button class="sb-hamburger" aria-label="打开菜单" @click="toggleSidebar">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 6h16M4 12h16M4 18h16"/></svg>
    </button>
    <div class="sb-backdrop" @click="closeSidebar"></div>

    <!-- 左侧栏（Claude 布局）：品牌 + 新对话 + 双入口导航（双 Surface）+ 最近对话历史。 -->
    <aside class="sidebar" :class="{ 'is-open': sidebarOpen }">
      <div class="sb-brand" @click="newConversation">
        <span class="brand-mark">F</span>
        <span class="brand-text">
          <span class="brand-name">FLAi-OS</span>
          <span class="brand-sub">二所工程智能体运行底座</span>
        </span>
      </div>

      <button class="sb-new" @click="newConversation">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
        新对话
      </button>

      <nav class="sidebar-nav">
        <a
          v-for="item in NAV"
          :key="item.path"
          class="nav-link"
          :class="{ 'is-active': activeMenu === item.path }"
          @click="$router.push(item.path)"
        >{{ item.label }}</a>
      </nav>

      <div class="sb-history">
        <div class="sb-section-label">最近对话</div>
        <div class="sb-convos">
          <a
            v-for="c in convos"
            :key="c.id"
            class="convo-item"
            :class="{ 'is-active': activeConvoId === c.id }"
            :title="convoTitle(c)"
            @click="openConvo(c)"
          >
            <span class="convo-dot" :class="c.recommendation && c.recommendation.decision === 'refuse' ? 'refuse' : (c.recommendation ? 'plan' : 'talk')"></span>
            <span class="convo-title">{{ convoTitle(c) }}</span>
            <span v-if="c.updated_at || c.created_at" class="convo-time">{{ formatTime(c.updated_at || c.created_at) }}</span>
          </a>
          <div v-if="!convos.length" class="convo-empty">还没有对话——从上方「新对话」开始</div>
        </div>
      </div>

      <!-- 侧栏脚部（美化批）：⌘K 可见入口（可点性+快捷键教学）+ 主题三段切换。 -->
      <div class="sb-foot">
        <button class="sb-foot-btn" title="搜索任务 / 会话 / Agent（⌘K）" @click="openQuickSwitcher">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
          搜索
          <kbd class="sb-kbd">⌘K</kbd>
        </button>
        <button class="sb-foot-btn sb-theme" :title="`主题：${themeLabel}（点击切换）`" @click="cycleTheme">
          <svg v-if="resolvedTheme === 'dark'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>
          <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
          {{ themeLabel }}
        </button>
      </div>
    </aside>

    <main class="app-main">
      <!-- 路由纸张过渡（动效系统 E3）：key 用 route.path——路由/参数变化时重挂载
           并触发入场动画（副作用修正：TaskDetail/WorkbenchSession 在 setup 捕获
           params，实例复用会读到旧 id，重挂载天然修正）；query 变化不重挂载
           （GuidePage 靠自身 watch 处理 ?c 重置，保持既有行为）。 -->
      <!-- key 优先 meta.pageKey：任务台 /tasks ↔ /tasks/:id 选中切换不整页
           重挂（中栏 TaskDetail 靠 :key=taskId 自行重建，保留参数修正语义）。 -->
      <div :key="route.meta.pageKey || route.path" class="page-turn">
        <router-view />
      </div>
    </main>
  </div>

  <!-- ⌘K 快速切换面板（B3）：热键监听与数据/跳转逻辑全封在组件内，这里只挂载。 -->
  <QuickSwitcher />

  <!-- 状态坞 + 状态中心（UI-PARADIGM Phase 1「状态来找人」）：轮询/数据/签发
       逻辑全封在组件与 stores/statusCenter 单例内，这里只挂载。 -->
  <StatusDock />
  <StatusCenter />
</template>

<script setup>
import { ref, computed, watch, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { listConversations } from "./api/conversations";
import { formatTime } from "./utils/format";
import { themeMode, resolvedTheme, setThemeMode } from "./stores/theme";
import { openQuickSwitcher } from "./stores/quickSwitcher";
import QuickSwitcher from "./components/QuickSwitcher.vue";
import StatusDock from "./components/StatusDock.vue";
import StatusCenter from "./components/StatusCenter.vue";

// 主题三段循环（跟随系统→浅色→深色）：显示当前模式而非解析结果，用户能看懂
// 「跟随系统」这个第三态；图标随 resolvedTheme（实际生效的亮暗）走。
const THEME_ORDER = ["system", "light", "dark"];
const THEME_LABELS = { system: "跟随系统", light: "浅色", dark: "深色" };
const themeLabel = computed(() => THEME_LABELS[themeMode.value]);
function cycleTheme() {
  const next = THEME_ORDER[(THEME_ORDER.indexOf(themeMode.value) + 1) % THEME_ORDER.length];
  setThemeMode(next);
}

const route = useRoute();
const router = useRouter();

// 范式 2b 双 Surface：应用只剩两个一级入口——对话（发起与跟进一切的家）
// 与任务台（Codex 三栏：列表|叙事流|面板坞）。Agent 门户降级为 composer 内
// 选择器 + /portal 深链（owner 拍板）；协作会话视图从对话/任务流深链进入。
const NAV = [
  { path: "/", label: "对话" },
  { path: "/tasks", label: "任务台" },
];

// 任务相关页（详情/创建）与协作会话子页归「任务台」高亮；门户归「对话」
// （Agent 是对话的弹药库）。
const activeMenu = computed(() => {
  const p = route.path;
  if (p === "/tasks" || p.startsWith("/tasks/")) return "/tasks";
  if (p.startsWith("/workbench")) return "/tasks";
  if (p === "/portal") return "/";
  return p;
});

// 当前恢复中的会话 id（导引页 /?c=<id>），用于左栏高亮。
const activeConvoId = computed(() => (typeof route.query.c === "string" ? route.query.c : ""));

// 窄屏抽屉开合（P2-7）；宽屏 CSS 让侧栏常驻，此状态不生效。
const sidebarOpen = ref(false);
function toggleSidebar() { sidebarOpen.value = !sidebarOpen.value; }
function closeSidebar() { sidebarOpen.value = false; }

const convos = ref([]);
async function loadConvos() {
  try {
    const list = await listConversations({ limit: 30 });
    convos.value = list;
  } catch {
    convos.value = []; // 左栏历史失败不阻断主区
  }
}
function convoTitle(c) {
  const r = c.recommendation;
  if (r && r.decision === "orchestrate" && r.goal) return r.goal;
  if (r && r.decision === "refuse" && r.reason) return "（未接住）" + r.reason;
  return `与 ${c.created_by || "你"} 的对话`;
}
function openConvo(c) {
  router.push({ path: "/", query: { c: c.id } });
}
function newConversation() {
  // 清掉 ?c 回到全新导引；若已在 /?c=x，query 变化会触发导引页重置。
  if (route.path === "/" && !route.query.c) return;
  router.push({ path: "/" });
}

// 路由变化后刷新左栏历史（导引创建新会话会把 URL 改成 /?c=<id>，据此让新会话即时入列），
// 并收起窄屏抽屉（点导航/会话跳转后自动关闭）。
watch(() => route.fullPath, () => {
  loadConvos();
  closeSidebar();
});
onMounted(loadConvos);
</script>

<style>
/* 全局设计变量：clay 暖橙作品牌与强调锚点，暖白背景，收敛的语义色。
 *
 * 信任色锁（M8，收编自 COMACAgentPlatform 协作面，焊死纪律）：语义色只表状态、
 * 绝不被装饰借用——clay=工作/进行/选中（唯一彩色语法）· 绿=仅真实(REAL)数据/结果
 * · teal=仅人签(改变工程状态的唯一合法通道) · 红=仅真失败/驳回 · amber=仅未核/降级。
 * 装饰要用色一律走中性暖阶（--paper-* / --sand-*），不碰上面五个语义槽。
 */
:root {
  --clay: #c15f3c;
  --clay-softer: #cc785c;
  --clay-soft: #f3e5de;
  --ink: #2b2622;
  --ink-soft: #6b6259;
  --ink-faint: #a39d90;
  --page-bg: #faf7f2;
  --card-bg: #ffffff;
  --hairline: #ece5db;
  --hairline-soft: #f0ece2;
  /* 暖纸阶（协作工作台底色，收编自 team.css）*/
  --paper-canvas-a: #fcfbf7;
  --paper-canvas-b: #f1eee6;
  --paper-surface: #fdfcf9;
  --paper-rail: #f7f4ec;
  --paper-cream: #fbf9f3;
  /* 信任语义锁（只表状态，绝不装饰借用）*/
  --trust-real: #2e8f50;   /* 绿：仅真实数据/结果 */
  --trust-signed: #167d8b; /* teal：仅人签 */
  --trust-fail: #be3a3a;   /* 红：仅真失败/驳回 */
  --trust-pending: #a8761a;/* amber：仅未核/降级 */
  --pulse-duration: 1.8s;
  /* elevation：暖调柔阴影（纯工艺层，中性 ink 色不碰语义槽）——静止态极轻、hover 抬升。
   * 卡片从"只有边框的扁平"升为"有纸感的浮起"，是本轮 UI 抬升的主手段。*/
  --shadow-card: 0 1px 2px rgba(43, 38, 34, 0.035), 0 4px 14px rgba(72, 58, 44, 0.05);
  --shadow-card-hover: 0 2px 6px rgba(43, 38, 34, 0.06), 0 12px 30px rgba(72, 58, 44, 0.10);
  --shadow-hero: 0 1px 3px rgba(43, 38, 34, 0.04), 0 10px 34px rgba(72, 58, 44, 0.06);
  --shadow-composer: 0 1px 3px rgba(43, 38, 34, 0.05), 0 12px 32px rgba(72, 58, 44, 0.09);
  --ease-lift: 0.18s cubic-bezier(0.22, 0.61, 0.36, 1);
  /* 动效系统 v1 tokens（SSOT=docs/design/MOTION-SYSTEM.md）：纸张/墨迹材质隐喻，
   * 只用 transform/opacity；--ease-spring 仅限小位移元素（防溢出裁切）。 */
  --motion-fast: 0.14s;
  --motion-med: 0.22s;
  --motion-slow: 0.6s;
  --ease-out-soft: cubic-bezier(0.25, 0.8, 0.35, 1);
  --ease-spring: cubic-bezier(0.34, 1.4, 0.64, 1);
  /* 衬线 display 字体（Claude 暖编辑语言）：只用于「大时刻」标题——目标句、hero 问候。
   * CJK 走 Songti/宋体，Latin 走 Iowan/Palatino，营造克制的编辑质感，与无衬线 body 对位。*/
  --serif: "Iowan Old Style", "Palatino Linotype", Palatino, "Songti SC", "STSong", "Times New Roman", serif;
  --clay-deep: #a54e2f;
  --surface-raised: #ffffff;
  --sidebar-w: 264px;
  --el-color-primary: #c15f3c;
  --el-color-primary-light-3: #d08663;
  --el-color-primary-light-5: #dba489;
  --el-color-primary-light-7: #e8c6b4;
  --el-color-primary-light-8: #f0d9cc;
  --el-color-primary-light-9: #f6e7de;
  --el-color-primary-dark-2: #a54e2f;
  /* Element Plus 框架中性层暖化：EP 默认冷灰边框/填充（#dcdfe6/#ebeef5/#f5f7fa）与
   * 暖白基调撞色，统一映到暖 hairline/paper 阶（明度对齐 EP 原值，纯中性、绝不碰
   * 语义槽）。一处覆盖，全站 el-table/el-descriptions/el-input/el-timeline/el-collapse
   * 的冷灰线与填充随之转暖。*/
  --el-border-color: #e4ddd2;
  --el-border-color-light: #ece5db;
  --el-border-color-lighter: #f0ece2;
  --el-border-color-extra-light: #f5f1ea;
  --el-fill-color: #f2eee6;
  --el-fill-color-light: #faf7f2;
  --el-fill-color-lighter: #fbf9f3;
  --el-fill-color-blank: #ffffff;
  /* ── RGB 三元组（美化批）：供 rgba(var(--x-rgb), a) 派生透明色——此前各处
   * 把 token 的 RGB 抄成字面量（rgba(193,95,60,.08) 等），主题一换就失联；
   * 暗色块里三元组随主题重定义，派生色自动跟随。 ── */
  --clay-rgb: 193, 95, 60;
  --ink-rgb: 43, 38, 34;
  --page-bg-rgb: 250, 247, 242;
  --trust-pending-rgb: 168, 118, 26;
  --trust-signed-rgb: 22, 125, 139;
  /* ── 表面/边框语义 token（美化批）：散落在组件里的浅色字面量收口于此，
   * 暗色主题只需在下方 dark 块翻转这一层。 ── */
  --ink-mid: #4a443d; /* 介于 ink 与 ink-soft 的次级正文（plan 正文/JSON/蓝图行）*/
  --bubble-user-bg: linear-gradient(180deg, #fbeee7, #f7e6dc);
  --bubble-user-border: #f0d8ca;
  --bubble-user-ink: #5b3524;
  --refuse-card-bg: linear-gradient(180deg, #fdf8ef, var(--surface-raised));
  --refuse-card-border: #efdcbb;
  --border-warm-hover: #e4d8c8;
  --border-clay-soft: #e6c9bb;
  --error-chip-border: #e6bcbc;
  --error-chip-bg: #faeeee;
  --focus-ring-clay: #dcb6a4;
  --review-chip-bg: #f9f2e2;
  /* hover/选中叠色：亮色=深色小叠加，暗色=亮色小叠加——方向相反，必须走 token */
  --hover-tint: rgba(43, 38, 34, 0.05);
  --select-tint-clay: rgba(193, 95, 60, 0.08);
  --trust-signed-deep: color-mix(in srgb, var(--trust-signed) 82%, black);
  color-scheme: light; /* 原生控件（滚动条/复选框）跟随主题 */
}

/* ═══ 暗色主题「夜航图纸」（美化批，Claude Desktop 证据：暖炭非纯黑、clay
 * 唯一强调保持、问候随主题变）。铁律：信任色锁五槽只做明度适配保 AA 对比，
 * 语义与色相一个不动；e2e 默认亮色跑（harness 已 pin light），此块不进断言。═══ */
:root[data-theme="dark"] {
  color-scheme: dark;
  /* 画布与纸阶：暖炭系（棕黑，不是冷灰黑）*/
  --page-bg: #211d19;
  --card-bg: #2a2521;
  --surface-raised: #2e2823;
  --paper-canvas-a: #262019;
  --paper-canvas-b: #1e1a15;
  --paper-surface: #2b2620;
  --paper-rail: #272220;
  --paper-cream: #292420;
  --hairline: #3a332c;
  --hairline-soft: #332d26;
  /* 墨阶反相为暖白系 */
  --ink: #ece5db;
  --ink-soft: #b0a698;
  --ink-faint: #8a8174; /* 诚实地板句层级：4.5:1 AA-text on #211d19（审查实测 #7a7164 只 3.49）*/
  --ink-mid: #cfc6b8;
  /* clay 锚：微提亮保对比，色相不动（唯一强调地位不变）*/
  --clay: #d4714a;
  --clay-softer: #d98a68;
  --clay-deep: #de8257;
  --clay-soft: rgba(212, 113, 74, 0.16);
  /* 信任五槽：明度适配（语义/色相锁死）*/
  --trust-real: #4aa96c;
  --trust-signed: #3b9eae;
  --trust-fail: #d4645a;
  --trust-pending: #c99a3f;
  /* 阴影：浅底投深影公式在暗底失效，改黑基调重算 */
  --shadow-card: 0 1px 2px rgba(0, 0, 0, 0.35), 0 4px 14px rgba(0, 0, 0, 0.4);
  --shadow-card-hover: 0 2px 6px rgba(0, 0, 0, 0.4), 0 12px 30px rgba(0, 0, 0, 0.5);
  --shadow-hero: 0 1px 3px rgba(0, 0, 0, 0.35), 0 10px 34px rgba(0, 0, 0, 0.45);
  --shadow-composer: 0 1px 3px rgba(0, 0, 0, 0.4), 0 12px 32px rgba(0, 0, 0, 0.5);
  /* RGB 三元组随主题重定义（派生透明色自动跟随）*/
  --clay-rgb: 212, 113, 74;
  --ink-rgb: 236, 229, 219;
  --page-bg-rgb: 33, 29, 25;
  --trust-pending-rgb: 201, 154, 63;
  --trust-signed-rgb: 59, 158, 174;
  /* 表面/边框语义 token 暗色值 */
  --bubble-user-bg: linear-gradient(180deg, #3a2d24, #332821);
  --bubble-user-border: #4a3a2e;
  --bubble-user-ink: #ecd9c9;
  --refuse-card-bg: linear-gradient(180deg, #322b1f, var(--surface-raised));
  --refuse-card-border: #4d4128;
  --border-warm-hover: #4a4238;
  --border-clay-soft: #55402f;
  --error-chip-border: #5a3535;
  --error-chip-bg: #362323;
  --focus-ring-clay: #8a5a42;
  --review-chip-bg: rgba(201, 154, 63, 0.12);
  --hover-tint: rgba(255, 255, 255, 0.055);
  --select-tint-clay: rgba(212, 113, 74, 0.16);
  --trust-signed-deep: color-mix(in srgb, var(--trust-signed) 78%, white); /* 暗底 hover 变亮非变暗 */
  /* Element Plus 暗色覆盖（main.js 未接 EP 官方 dark css-vars——那套按 html.dark
   * 生效与本仓 data-theme 约定不合；沿用「手动暖化 EP」既有模式补暗色一套）*/
  --el-bg-color: #2a2521;
  --el-bg-color-page: #211d19;
  --el-bg-color-overlay: #2e2823;
  --el-mask-color: rgba(0, 0, 0, 0.55);
  --el-mask-color-extra-light: rgba(0, 0, 0, 0.35);
  --el-text-color-primary: #ece5db;
  --el-text-color-regular: #cfc6b8;
  --el-text-color-secondary: #b0a698;
  --el-text-color-placeholder: #7a7164;
  --el-text-color-disabled: #5f574c;
  --el-border-color: #3f382f;
  --el-border-color-light: #3a332c;
  --el-border-color-lighter: #332d26;
  --el-border-color-extra-light: #2f2924;
  --el-fill-color: #332d26;
  --el-fill-color-light: #2b2620;
  --el-fill-color-lighter: #292420;
  --el-fill-color-blank: #2e2823;
  --el-color-primary: #d4714a;
  /* primary 色阶暗色反向：light-N 朝暗底混（EP 拿它们做 hover/浅底，暗色下
   * 照搬亮色的近白值会成奶油亮斑）*/
  --el-color-primary-light-3: #b0603f;
  --el-color-primary-light-5: #8f5136;
  --el-color-primary-light-7: #6a4029;
  --el-color-primary-light-8: #573729;
  --el-color-primary-light-9: #453026;
  --el-color-primary-dark-2: #de8257;
  --el-box-shadow: 0 12px 32px 4px rgba(0, 0, 0, 0.36), 0 8px 20px rgba(0, 0, 0, 0.72);
  --el-box-shadow-light: 0 0 12px rgba(0, 0, 0, 0.72);
  --el-box-shadow-lighter: 0 0 6px rgba(0, 0, 0, 0.72);
  --el-box-shadow-dark: 0 16px 48px 16px rgba(0, 0, 0, 0.72), 0 12px 32px #000, 0 8px 16px -8px #000;
  --el-disabled-bg-color: #2b2620;
  --el-disabled-text-color: #5f574c;
  --el-disabled-border-color: #3a332c;
  /* EP 语境四族：全梯度朝暗底混（light-N = 主色向 --page-bg 混 N 成，与 EP
   * dark 梯度同构）——只补 8/9 会让 danger 按钮 hover/plain tag 边框（light-3/5）
   * 继承亮色奶油值（Codex 异源审 P2）。 */
  --el-color-success: #67c23a;
  --el-color-success-light-3: color-mix(in srgb, #67c23a 70%, #211d19);
  --el-color-success-light-5: color-mix(in srgb, #67c23a 50%, #211d19);
  --el-color-success-light-7: color-mix(in srgb, #67c23a 30%, #211d19);
  --el-color-success-light-8: #2a3a24;
  --el-color-success-light-9: #253321;
  --el-color-success-dark-2: color-mix(in srgb, #67c23a 80%, white);
  --el-color-warning: #e6a23c;
  --el-color-warning-light-3: color-mix(in srgb, #e6a23c 70%, #211d19);
  --el-color-warning-light-5: color-mix(in srgb, #e6a23c 50%, #211d19);
  --el-color-warning-light-7: color-mix(in srgb, #e6a23c 30%, #211d19);
  --el-color-warning-light-8: #3e3423;
  --el-color-warning-light-9: #362e20;
  --el-color-warning-dark-2: color-mix(in srgb, #e6a23c 80%, white);
  --el-color-danger: #f56c6c;
  --el-color-danger-light-3: color-mix(in srgb, #f56c6c 70%, #211d19);
  --el-color-danger-light-5: color-mix(in srgb, #f56c6c 50%, #211d19);
  --el-color-danger-light-7: color-mix(in srgb, #f56c6c 30%, #211d19);
  --el-color-danger-light-8: #422a2a;
  --el-color-danger-light-9: #392525;
  --el-color-danger-dark-2: color-mix(in srgb, #f56c6c 80%, white);
  --el-color-error: #f56c6c;
  --el-color-error-light-3: color-mix(in srgb, #f56c6c 70%, #211d19);
  --el-color-error-light-5: color-mix(in srgb, #f56c6c 50%, #211d19);
  --el-color-error-light-7: color-mix(in srgb, #f56c6c 30%, #211d19);
  --el-color-error-light-8: #422a2a;
  --el-color-error-light-9: #392525;
  --el-color-error-dark-2: color-mix(in srgb, #f56c6c 80%, white);
  --el-color-info: #909399;
  --el-color-info-light-3: color-mix(in srgb, #909399 70%, #211d19);
  --el-color-info-light-5: color-mix(in srgb, #909399 50%, #211d19);
  --el-color-info-light-7: color-mix(in srgb, #909399 30%, #211d19);
  --el-color-info-light-8: #33322f;
  --el-color-info-light-9: #2d2c2a;
  --el-color-info-dark-2: color-mix(in srgb, #909399 80%, white);
}
/* ── 工作态氛围（全局复用）── */
@keyframes flai-work-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: .45; transform: scale(.82); }
}
.work-pulse-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--clay);
  animation: flai-work-pulse var(--pulse-duration) ease-in-out infinite;
  flex: none;
}
.pill-amber {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 10px;
  border-radius: 999px;
  font-size: 12px;
  color: var(--trust-pending);
  border: 1px solid rgba(var(--trust-pending-rgb), 0.35);
  background: rgba(var(--trust-pending-rgb), 0.08);
  white-space: nowrap;
}
/* ── 动效系统 v1 全局层（E3）：纸张过渡 + 入场工具类 + 按压微交互 ──
 * 全部 transform/opacity（零 layout），reduced-motion 一律静态降级。 */
/* 路由过渡刻意只用 opacity：动画期间容器带 transform 会成为后代
 * position:fixed 的 containing block（GuidePage 悬浮 composer 会被劫持
 * 220ms，回归镜头 P2 实证）——「升起」观感由各页内部 .fx-stagger/.fx-rise
 * 承担（它们不包裹 fixed 后代）。 */
@keyframes fx-page-turn {
  from { opacity: 0; }
  to { opacity: 1; }
}
.page-turn {
  animation: fx-page-turn var(--motion-med) var(--ease-out-soft) backwards;
}
/* 入场工具类：单元素 .fx-rise；容器 .fx-stagger 让直接子元素错峰升起
 * （前 8 个逐级延迟，其后同步——长列表不做无限延迟）。 */
@keyframes fx-rise {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
.fx-rise { animation: fx-rise var(--motion-med) var(--ease-out-soft) backwards; }
.fx-stagger > * { animation: fx-rise var(--motion-med) var(--ease-out-soft) backwards; }
.fx-stagger > *:nth-child(1) { animation-delay: 0.03s; }
.fx-stagger > *:nth-child(2) { animation-delay: 0.07s; }
.fx-stagger > *:nth-child(3) { animation-delay: 0.11s; }
.fx-stagger > *:nth-child(4) { animation-delay: 0.15s; }
.fx-stagger > *:nth-child(5) { animation-delay: 0.19s; }
.fx-stagger > *:nth-child(6) { animation-delay: 0.23s; }
.fx-stagger > *:nth-child(7) { animation-delay: 0.27s; }
.fx-stagger > *:nth-child(8) { animation-delay: 0.31s; }
/* 墨迹晕开：新事件/新气泡入场（P2/P3 用）——轻微模糊聚焦，如墨点落纸。 */
/* 墨迹晕开：只用 transform/opacity（硬约束⑤字面合规，不用 filter）——
 * 「晕开」感由 scale 起点压小 + 时长放到 --motion-slow 营造。 */
@keyframes fx-ink-in {
  from { opacity: 0; transform: translateY(5px) scale(0.97); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
.fx-ink-in { animation: fx-ink-in var(--motion-slow) var(--ease-out-soft) backwards; }
/* 按压微交互：全站按钮统一「按得下去」的实感（transform-only）。
 * 刻意不覆盖 .el-button 的 transition——Element Plus 自带 `transition: all .1s`
 * 已含 transform；单独覆盖会吃掉 hover/loading 的颜色过渡（回归镜头 P2）。 */
.el-button:not(.is-disabled):active,
.sb-new:active,
.nav-link:active {
  transform: scale(0.97);
}

@media (prefers-reduced-motion: reduce) {
  .work-pulse-dot { animation: none; }
  .page-turn,
  .fx-rise,
  .fx-stagger > *,
  .fx-ink-in { animation: none; }
  .el-button:not(.is-disabled):active,
  .sb-new:active,
  .nav-link:active { transform: none; }
}

body {
  margin: 0;
  background: var(--page-bg);
  color: var(--ink);
  font-family: "PingFang SC", "Microsoft YaHei", system-ui, -apple-system, sans-serif;
}
.app-shell {
  min-height: 100vh;
}

/* ── 左侧栏 ── */
.sidebar {
  position: fixed;
  left: 0;
  top: 0;
  bottom: 0;
  width: var(--sidebar-w);
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 16px 12px;
  background: linear-gradient(180deg, var(--paper-cream), var(--paper-rail));
  border-right: 1px solid var(--hairline);
  z-index: 30;
}
.sb-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px 10px;
  cursor: pointer;
}
.brand-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: linear-gradient(150deg, var(--clay), var(--clay-deep));
  color: #fff;
  font-weight: 800;
  font-size: 16px;
  box-shadow: 0 3px 10px rgba(var(--clay-rgb), 0.3);
}
.brand-text { display: flex; flex-direction: column; line-height: 1.2; }
.brand-name { font-size: 16px; font-weight: 700; color: var(--ink); letter-spacing: 0.2px; }
.brand-sub { font-size: 10.5px; color: var(--ink-faint); margin-top: 1px; }

.sb-new {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 2px 0 8px;
  padding: 9px 12px;
  border: 1px solid var(--border-clay-soft);
  border-radius: 11px;
  background: var(--surface-raised);
  color: var(--clay);
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: var(--shadow-card);
  transition: all 0.16s var(--ease-lift);
}
.sb-new:hover { background: var(--clay); color: #fff; border-color: var(--clay); box-shadow: 0 4px 12px rgba(var(--clay-rgb), 0.22); }

.sidebar-nav { display: flex; flex-direction: column; gap: 2px; }
.nav-link {
  display: block;
  padding: 8px 12px;
  border-radius: 9px;
  font-size: 13.5px;
  font-weight: 500;
  color: var(--ink-soft);
  cursor: pointer;
  transition: background 0.14s var(--ease-lift), color 0.14s var(--ease-lift);
}
.nav-link:hover { background: rgba(var(--clay-rgb), 0.07); color: var(--ink); }
.nav-link.is-active { background: var(--clay-soft); color: var(--clay); font-weight: 600; }

.sb-history {
  margin-top: 10px;
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.sb-section-label {
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.8px;
  text-transform: uppercase;
  color: var(--ink-faint);
  padding: 4px 12px 6px;
}
.sb-convos { overflow-y: auto; display: flex; flex-direction: column; gap: 1px; }
.sb-convos::-webkit-scrollbar { width: 6px; }
.sb-convos::-webkit-scrollbar-thumb { background: var(--hairline); border-radius: 6px; }
.convo-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.14s var(--ease-lift);
}
.convo-item:hover { background: var(--hover-tint); }
.convo-item.is-active { background: var(--select-tint-clay); }
.convo-dot { flex: 0 0 auto; width: 6px; height: 6px; border-radius: 50%; background: var(--ink-faint); }
.convo-dot.plan { background: var(--clay); }
.convo-dot.refuse { background: var(--trust-pending); }
.convo-title {
  font-size: 12.5px;
  color: var(--ink-soft);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.convo-item.is-active .convo-title { color: var(--ink); font-weight: 600; }
/* hover 出时间戳（Claude Desktop 语言）：静止零噪音，悬停渐显 */
.convo-time {
  flex: none;
  margin-left: auto;
  font-size: 10.5px;
  color: var(--ink-faint);
  opacity: 0;
  transition: opacity var(--motion-fast) var(--ease-out-soft);
}
.convo-item:hover .convo-time { opacity: 1; }
.convo-empty { font-size: 12px; color: var(--ink-faint); padding: 8px 12px; line-height: 1.5; }

/* ── 侧栏脚部：搜索（⌘K 教学）+ 主题切换 ── */
.sb-foot {
  display: flex;
  gap: 6px;
  padding-top: 8px;
  margin-top: 6px;
  border-top: 1px solid var(--hairline-soft);
}
.sb-foot-btn {
  flex: 1 1 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 7px 8px;
  border: 1px solid transparent;
  border-radius: 9px;
  background: none;
  font-size: 12px;
  color: var(--ink-faint);
  cursor: pointer;
  transition: background var(--motion-fast) var(--ease-out-soft), color var(--motion-fast) var(--ease-out-soft);
}
.sb-foot-btn:hover {
  background: var(--hover-tint);
  color: var(--ink-soft);
}
.sb-kbd {
  font-size: 10px;
  font-family: ui-monospace, monospace;
  padding: 0 4px;
  border: 1px solid var(--hairline);
  border-radius: 4px;
  color: var(--ink-faint);
}
@media (prefers-reduced-motion: reduce) {
  .convo-time,
  .sb-foot-btn {
    transition: none;
  }
}

/* ── 主区 ── */
.app-main {
  margin-left: var(--sidebar-w);
  width: calc(100% - var(--sidebar-w));
  box-sizing: border-box;
  padding: 28px 32px 48px;
  min-height: 100vh;
}

/* ── 窄屏汉堡 + 抽屉背板（宽屏隐藏；侧栏常驻） ── */
.sb-hamburger { display: none; }
.sb-backdrop { display: none; }

@media (max-width: 860px) {
  .sidebar {
    transform: translateX(-100%);
    transition: transform 0.22s var(--ease-lift);
    box-shadow: none;
  }
  .sidebar.is-open {
    transform: translateX(0);
    box-shadow: 0 0 0 1px var(--hairline), 12px 0 36px rgba(43, 38, 34, 0.16);
  }
  .app-main { margin-left: 0; width: 100%; padding: 60px 16px 40px; }

  .sb-hamburger {
    position: fixed;
    top: 12px;
    left: 12px;
    z-index: 40;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    border: 1px solid var(--hairline);
    border-radius: 10px;
    background: var(--surface-raised);
    color: var(--ink-soft);
    cursor: pointer;
    box-shadow: var(--shadow-card);
  }
  .sb-hamburger:hover { color: var(--clay); border-color: var(--clay-softer); }

  .sidebar-open .sb-backdrop {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 25;
    background: rgba(43, 38, 34, 0.32);
  }
}
</style>
