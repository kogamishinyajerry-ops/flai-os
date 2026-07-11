<template>
  <div class="app-shell" :class="{ 'sidebar-open': sidebarOpen }">
    <!-- 窄屏汉堡：<860px 侧栏收起，靠它唤出抽屉（P2-7：不再让导航凭空消失）。 -->
    <button class="sb-hamburger" aria-label="打开菜单" @click="toggleSidebar">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 6h16M4 12h16M4 18h16"/></svg>
    </button>
    <div class="sb-backdrop" @click="closeSidebar"></div>

    <!-- 左侧栏（Claude 布局）：品牌 + 新对话 + 三入口导航 + 最近对话历史。 -->
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
          </a>
          <div v-if="!convos.length" class="convo-empty">还没有对话——从上方「新对话」开始</div>
        </div>
      </div>
    </aside>

    <main class="app-main">
      <!-- 路由纸张过渡（动效系统 E3）：key 用 route.path——路由/参数变化时重挂载
           并触发入场动画（副作用修正：TaskDetail/WorkbenchSession 在 setup 捕获
           params，实例复用会读到旧 id，重挂载天然修正）；query 变化不重挂载
           （GuidePage 靠自身 watch 处理 ?c 重置，保持既有行为）。 -->
      <div :key="route.path" class="page-turn">
        <router-view />
      </div>
    </main>
  </div>

  <!-- ⌘K 快速切换面板（B3）：热键监听与数据/跳转逻辑全封在组件内，这里只挂载。 -->
  <QuickSwitcher />
</template>

<script setup>
import { ref, computed, watch, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { listConversations } from "./api/conversations";
import QuickSwitcher from "./components/QuickSwitcher.vue";

const route = useRoute();
const router = useRouter();

const NAV = [
  { path: "/", label: "智能导引" },
  { path: "/portal", label: "Agent 门户" },
  { path: "/workbench", label: "协作工作台" },
];

// 任务相关页（历史/详情/创建）与协作会话子页在 M8 IA 里都归属「协作工作台」高亮。
const activeMenu = computed(() => {
  const p = route.path;
  if (p === "/tasks" || p.startsWith("/tasks/")) return "/workbench";
  if (p.startsWith("/workbench/")) return "/workbench";
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
  border: 1px solid rgba(168, 118, 26, .35);
  background: rgba(168, 118, 26, .08);
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
  box-shadow: 0 3px 10px rgba(193, 95, 60, 0.3);
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
  border: 1px solid #e6cabc;
  border-radius: 11px;
  background: var(--surface-raised);
  color: var(--clay);
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: var(--shadow-card);
  transition: all 0.16s var(--ease-lift);
}
.sb-new:hover { background: var(--clay); color: #fff; border-color: var(--clay); box-shadow: 0 4px 12px rgba(193, 95, 60, 0.22); }

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
.nav-link:hover { background: rgba(193, 95, 60, 0.07); color: var(--ink); }
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
.convo-item:hover { background: rgba(43, 38, 34, 0.05); }
.convo-item.is-active { background: rgba(193, 95, 60, 0.1); }
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
.convo-empty { font-size: 12px; color: var(--ink-faint); padding: 8px 12px; line-height: 1.5; }

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
