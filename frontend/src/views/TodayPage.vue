<template>
  <!-- 今日工作台（批B §一）：开工即看——待签发置顶、进行中一眼可见，
       版块 3/4/5（今日交付/Agent 动态/团队总量）占位待批B后续任务接入。
       全部数据来自 liveFeed 'tasks' channel（与 StatusCenter/StatusDock 同一份真值，
       全站只此一条该 channel 轮询）。 -->
  <div class="today">
    <div class="today-head">
      <span class="today-title">今日</span>
    </div>

    <!-- 首拉失败态（治理审 R1 P2 修复）：feedError 且从未 loaded 过 → 只显错误块，
         绝不在没有真数据的情况下渲染五个空版块冒充「已加载」。已 loaded 后的轮询
         错误走 v-else 分支内部的顶部小字错误条，保旧值自愈，不打断已渲染内容。 -->
    <!-- 错误三问（批次五 C2/C6）：liveFeed 5s 链持续在跑——「自动重试中」是
         机制属实的「何为」声明；role=alert 让 AT 主动播报（inline 错误规）。 -->
    <div v-if="feedError && !feedLoaded" class="today-error" role="alert">{{ feedErrorDisplay }}</div>

    <!-- 首载骨架：只在「从未 loaded 且无错误」时撑轮廓，轮询期间/带旧值刷新绝不回骨架。 -->
    <div v-else-if="!feedLoaded" class="today-skel">
      <SkeletonBlock v-for="(w, i) in ['70%', '92%', '84%', '76%', '88%', '64%']" :key="i" height="52px" :width="w" />
    </div>

    <template v-else>
      <div v-if="feedError" class="today-error" role="alert">{{ feedErrorDisplay }}</div>

      <!-- 首行安静摘要（批次八 降噪：owner「精选必要信息披露」）：原 overview
           三格与下方三个 section 头同屏重复同一组计数——section 头计数在语境里
           （batch_b ① 同源断言锚在彼侧）保留为唯一承载，此处不再复述。只留唯一
           行动召唤：有待签时一行「N 项待你签发」链接式直达签发版块；零待签整行
           不渲染（零值不显示/稀疏即尊重），进行中/今日交付不再设零值占位格。 -->
      <div v-if="waitingTasks.length" class="today-summary">
        <button type="button" class="today-summary-link" @click="scrollToSign">
          <el-icon aria-hidden="true"><Stamp /></el-icon>
          <span><span class="num-token">{{ waitingTasks.length }}</span> 项待你签发</span>
          <span class="today-summary-arrow" aria-hidden="true">↓</span>
        </button>
      </div>

      <!-- 版块 1：待你签发（amber 置顶，行动召唤最高优先）。零值不显示（批次四
           Q2，cd-bg-tasks-panel 语法全站化）：N=0 时组头不渲染「· 0」——版块
           容器恒在（batch_b ① 钉五版块），只收计数后缀。 -->
      <section ref="signSection" class="today-section">
        <div class="today-section-head waiting">
          <el-icon aria-hidden="true"><Stamp /></el-icon>
          <span>待你签发<template v-if="waitingTasks.length"> · <span class="num-token">{{ waitingTasks.length }}</span></template></span>
        </div>
        <div v-if="waitingTasks.length" class="today-list">
          <div
            v-for="t in waitingTasks"
            :key="t.id"
            class="today-card"
            role="button"
            tabindex="0"
            @click="openTask(t.id)"
            @keydown.enter.prevent="openTask(t.id)"
            @keydown.space.prevent="openTask(t.id)"
          >
            <!-- lamp 走 taskLampColor SSOT（B-T3 审 P3）。耗时：待签行不再显示
                 「运行 Xs」——taskElapsedMs 对停驻态返回 null（批次六 B6-5：
                 无 finished_at 时墙钟端锚只属于工作态，待签期间膨胀的时长=假声明）。 -->
            <span class="today-card-visual" aria-hidden="true">
              <el-icon><Stamp /></el-icon>
              <span class="today-lamp" :style="{ background: taskLampColor(t.status) }"></span>
            </span>
            <span class="today-card-main">
              <!-- 人话称呼（批次四 Q1）：缺名回退 Agent 显示名，taskDisplayName
                   三级诚实降级 SSOT；裸 id 退居详情 rail。 -->
              <span class="today-card-name">{{ taskDisplayName(t, agentNames.map) }}</span>
              <!-- meta 时钟（3-lens 可用性镜头 P2）：同 Agent 多个缺名任务主名
                   相同，时钟是行级消歧锚（契约 §十二 Q1 承诺，与状态中心行同律）。 -->
              <span class="today-card-sub">
                {{ t.agent_id }} · {{ todayClock(t.created_at) }}<template v-if="elapsedText(t)"> · 运行 {{ elapsedText(t) }}</template>
              </span>
            </span>
          </div>
        </div>
        <EmptyState v-else variant="action" description="没有等你签发的任务" />
      </section>

      <!-- 版块 2：进行中 -->
      <section class="today-section">
        <div class="today-section-head working">
          <el-icon aria-hidden="true"><Timer /></el-icon>
          <span>进行中<template v-if="workingTasks.length"> · <span class="num-token">{{ workingTasks.length }}</span></template></span>
        </div>
        <div v-if="workingTasks.length" class="today-list">
          <div
            v-for="t in workingTasks"
            :key="t.id"
            class="today-card"
            role="button"
            tabindex="0"
            @click="openTask(t.id)"
            @keydown.enter.prevent="openTask(t.id)"
            @keydown.space.prevent="openTask(t.id)"
          >
            <span class="today-card-visual" aria-hidden="true">
              <el-icon><Cpu /></el-icon>
              <span class="today-lamp" :class="{ 'is-pulsing': isWork(t.status) }" :style="{ background: taskLampColor(t.status) }"></span>
            </span>
            <span class="today-card-main">
              <span class="today-card-name">{{ taskDisplayName(t, agentNames.map) }}</span>
              <span class="today-card-sub">{{ t.agent_id }} · {{ statusLabel(t.status) }} · {{ todayClock(t.created_at) }}</span>
            </span>
          </div>
        </div>
        <EmptyState v-else variant="data" tier="line" description="当前没有进行中的任务" />
      </section>

      <!-- 版块 3：今日交付（终态叙事卡）。animate 接 sealAnimateIds（批B Task 6）
           ——本会话亲历「活跃→终态」迁移的任务才播盖章合拢仪式，历史直开静态渲染。
           渲染集合上界 12 张（B7 P1 修复：DeliveryCard 每卡自带 2-3 个只读请求，
           今日交付量大时无界渲染=无界扇出）——超出静默截断是假信息，标题栏如实
           标注「显示最近 N 条」（诚实口径，canon 纪律）。 -->
      <section class="today-section">
        <div class="today-section-head">
          <el-icon aria-hidden="true"><Files /></el-icon>
          <span>今日交付<template v-if="deliveryTasks.length"> · <span class="num-token">{{ deliveryTasks.length }}</span></template><template v-if="deliveryTasks.length > DELIVERY_DISPLAY_CAP">（显示最近 <span class="num-token">{{ DELIVERY_DISPLAY_CAP }}</span> 条）</template></span>
        </div>
        <div v-if="deliveryTasks.length" class="today-list">
          <DeliveryCard v-for="t in visibleDeliveryTasks" :key="t.id" :task="t" :animate="sealAnimateIds.has(t.id)" />
        </div>
        <EmptyState v-else variant="data" tier="line" description="今天还没有交付的任务" />
      </section>

      <!-- 版块 4：Agent 动态（4a 本周最近晋升 ≤5 条 + 4b 今日最活跃 Agent top3）。
           4a 用「本周」框定（与版块5「本周晋升」同一 since 口径），故对
           listGlobalPromotions 的结果做本地 weekStartMs 过滤而非直接取前 5——
           否则「本周暂无晋升」空态文案可能在有更早晋升时误判有数据。 -->
      <section class="today-section">
        <div class="today-section-head">
          <el-icon aria-hidden="true"><TrendCharts /></el-icon>
          <span>Agent 动态</span>
        </div>
        <!-- 晋升/统计只在挂载+零点拉取、无轮询——「自动重试中」在此是假声明，
             诚实的「何为」=行内手动重试（批次五 C2）。 -->
        <div v-if="promotionsError" class="today-error" role="alert">
          {{ promotionsError }}
          <button type="button" class="today-retry" @click="fetchPromotions">重试</button>
        </div>
        <!-- 双空态合并（批次四 Q2）：晋升可读且两侧都空 → 收敛为一行安静空态——
             两条并排的「暂无」是对新人的双倍噪音；任一侧有数据则各自照常。
             「近 100 条窗口」口径由页脚一行统一声明（Q3 同屏去重），此处不再复述。 -->
        <EmptyState
          v-else-if="!recentPromotions.length && !topActiveAgents.length"
          variant="data"
          tier="line"
          description="今天还没有 Agent 动态"
        />
        <template v-else>
          <div v-if="recentPromotions.length" class="today-list">
            <div v-for="p in recentPromotions" :key="p.id" class="today-promo-row">
              <el-icon class="today-promo-icon" aria-hidden="true"><Promotion /></el-icon>
              <span class="today-promo-copy">
                <span class="today-promo-main">
                  {{ p.agent_id }} 晋升 {{ maturityLabel(p.from_maturity) }} → {{ maturityLabel(p.to_maturity) }}
                </span>
                <span class="today-promo-sub">{{ formatRelativeTime(p.created_at) }} · 签发人 {{ p.confirmed_by }}</span>
              </span>
            </div>
          </div>
          <EmptyState v-else variant="data" tier="line" description="本周暂无晋升" />
        </template>

        <!-- 今日最活跃：数据源是本地 tasks channel，与晋升 API 无关——晋升出错
             时必须仍独立可见（3-lens 回归镜头 P2：合并空态曾把它误嵌进
             promotionsError 的 v-else 连坐隐藏）。仅「合并空态」已把两者一起
             收敛的场景（无错且双空）不再重复渲染。 -->
        <template v-if="promotionsError || recentPromotions.length || topActiveAgents.length">
          <div class="today-subhead">今日最活跃 Agent</div>
          <div v-if="topActiveAgents.length" class="today-active-row">
            <span v-for="a in topActiveAgents" :key="a.agent_id" class="today-active-chip">
              <el-icon aria-hidden="true"><User /></el-icon>
              <span>{{ a.agent_id }} · {{ a.count }}</span>
            </span>
          </div>
          <EmptyState v-else variant="data" tier="line" description="今天暂无任务" />
        </template>
      </section>

      <!-- 版块 5：团队总量条——全中性 ink 色（信任色锁：绿/teal 只留给 REAL
           结果/人签动作本身，不预支到统计数字）。零值格不渲染（批次四 Q2）：
           0 不是信息；data-stat 语义锚供 e2e 按字段对表（隐藏格由 API 真值
           证实确为 0，绝不是数据丢失）。方法论括注降 title（Q3）。 -->
      <section class="today-section">
        <div class="today-section-head">
          <el-icon aria-hidden="true"><DataAnalysis /></el-icon>
          <span>团队总量</span>
        </div>
        <div v-if="statsError" class="today-error" role="alert">
          {{ statsError }}
          <button type="button" class="today-retry" @click="fetchStats">重试</button>
        </div>
        <div v-else-if="stats && visibleStats.length" class="today-stats-bar">
          <div v-for="s in visibleStats" :key="s.key" class="today-stat-tile" :data-stat="s.key" :title="s.tip || null">
            <el-icon class="today-stat-icon" aria-hidden="true"><component :is="s.icon" /></el-icon>
            <span class="today-stat-num">{{ typeof s.value === "number" ? s.value : "—" }}</span>
            <span class="today-stat-label">{{ s.label }}</span>
          </div>
        </div>
        <EmptyState v-else-if="stats" variant="data" tier="line" description="本周还没有可统计的团队动态" />
        <SkeletonBlock v-else height="52px" width="100%" />
      </section>
    </template>

    <div class="today-foot-note">基于最近 100 条任务窗口</div>
  </div>
</template>

<script setup>
// 数据源：liveFeed 'tasks' channel（批A 单源轮询，5s 自链，与 StatusCenter/
// StatusDock/TaskConsole 同一份真值）。本页整页挂载期间持有一次 acquire，
// 卸载即 release（channel 无其它订阅者时自停）。
import { computed, onUnmounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import {
  Collection,
  Cpu,
  DataAnalysis,
  Files,
  Finished,
  Promotion,
  Stamp,
  Timer,
  TrendCharts,
  User,
} from "@element-plus/icons-vue";
import { acquireChannel, onTransition } from "../stores/liveFeed";
import { TERMINAL_STATUSES } from "../stores/liveFeedCore";
import { getStatsOverview, listGlobalPromotions } from "../api/stats";
import { statusLabel, taskLampColor, taskElapsedMs, formatDuration, formatRelativeTime, formatClockCompact, taskDisplayName, TASK_WORK_STATES, MATURITY } from "../utils/format";
import { useAgentNames } from "../stores/agentNames";
import { useTodayKey } from "../composables/useTodayKey";
import EmptyState from "../components/EmptyState.vue";
import SkeletonBlock from "../components/SkeletonBlock.vue";
import DeliveryCard from "../components/DeliveryCard.vue";

const router = useRouter();

const tasksChannel = acquireChannel("tasks");
const { tasks: feedTasks, loaded: feedLoaded, error: feedError } = tasksChannel.state;

// feed 错误展示（3-lens 可用性 P3）：超时分型文案自带「……请稍后重试」收尾，
// 与轮询链的「（自动重试中）」硬拼成「请稍后重试（自动重试中）」自相矛盾——
// 剥掉手动重试尾巴再挂自动标注（⑭C2′ 反矛盾断言咬合）。
const feedErrorDisplay = computed(() =>
  feedError.value ? feedError.value.replace(/，?请稍后重试$/, "") + "（自动重试中）" : ""
);

const maturityLabel = (m) => MATURITY[m]?.label ?? m;

const waitingTasks = computed(() => feedTasks.value.filter((t) => t.status === "waiting_review"));
const workingTasks = computed(() =>
  feedTasks.value.filter((t) => ["created", "queued", "running", "validating"].includes(t.status))
);

// 本地日切 SSOT（B7 P2 修复）：版块 3「今日交付」与版块 4b「今日最活跃」要求
// 同一「今天」定义——今天 0 点起，本地时区，非 UTC。返回本地零点 epoch ms，
// 配 Date.parse(iso) 比较，两处共享同一口径不各自重算。
function localDayStartMs() {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

// 版块 3：今日交付——终态（completed/failed/cancelled，TERMINAL_STATUSES 单一
// 映射源，与 liveFeedCore/TaskDetail 同款）且 finished_at 落在本地今日。
const deliveryTasks = computed(() => {
  const todayStartMs = localDayStartMs();
  return feedTasks.value.filter(
    (t) => TERMINAL_STATUSES.includes(t.status) && t.finished_at && Date.parse(t.finished_at) >= todayStartMs
  );
});

// 渲染上界（B7 P1 修复）：DeliveryCard 每卡自带只读请求，deliveryTasks 无界时
// =无界扇出。截断前必须按 finished_at 降序排（治理审 R1 P2 修复）——feedTasks
// 是 created_at 降序，与 finished_at 降序不等价（先创建不等于先完成），此前
// 直接对 created_at 序 slice 会把「最近交付」误判成「最近创建」。finished_at
// 缺失（理论不应发生，deliveryTasks 已过滤要求其非空）防御性排最后。
const DELIVERY_DISPLAY_CAP = 12;
function deliverySortKeyMs(t) {
  return t.finished_at ? Date.parse(t.finished_at) : -Infinity;
}
const visibleDeliveryTasks = computed(() =>
  [...deliveryTasks.value]
    .sort((a, b) => deliverySortKeyMs(b) - deliverySortKeyMs(a))
    .slice(0, DELIVERY_DISPLAY_CAP)
);

// 盖章仪式只属于亲历者（批A Task 9 同款判据，见 TaskDetail.vue ~328-341 行的
// 硬坑注释：ev.from 必须显式 != null，不能只判「不在终态列表」——否则
// StatusDock 全局常驻挂载的冷启动清单拉取会被误当成一次「亲历迁移」）。页面
// 生命周期内不清除：同一会话回看仍算亲历过。
const sealAnimateIds = reactive(new Set());

// 版块 4/5（B-T5）：「本周」=本地周一零点（周日 getDay()=0 归上周一）。治理审
// R1 P2 修复：此前算一次存常量，页面若挂机跨过周一零点或跨日（版块 4a 用
// weekStartMs 过滤晋升列表），边界永远停在挂载那一刻，标题「本周」会漂移成
// 「上周+今天」。改响应式 ref，fetchStats 每次调用前重算，另排一个「下个本地
// 零点」定时器兜底跨日翻新（跨周必然先跨若干个日，日翻新即含周翻新）。
const weekStartMs = ref(computeWeekStartMs());
function computeWeekStartMs() {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return d.getTime();
}

const stats = ref(null);
const statsError = ref("");
const promotions = ref([]);
const promotionsError = ref("");

// Agent 人话名册（批次四 Q1）：行级主文本缺名时回退注册表显示名。
const agentNames = useAgentNames();

// 行级紧凑时钟（消歧锚）：响应式日界走 useTodayKey SSOT（午夜翻页教训）。
const todayKey = useTodayKey();
const todayClock = (iso) => formatClockCompact(iso, todayKey.value);

// 团队总量可见格（批次四 Q2 零值不显示）：仅渲染 >0 的格；隐藏格的「确为 0」
// 由 e2e 按 data-stat 对照 /api/stats/overview 真值核验，不靠 DOM 残留自证。
// 字段定义与 MePage 团队行同一后端投影（tasks_completed/reviews_approved/
// curated_cases_total/promotions），此处只做展示映射不再造口径。
const STAT_DEFS = [
  { key: "tasks_completed", label: "本周完成", icon: Finished },
  { key: "reviews_approved", label: "本周人签放行", icon: Stamp },
  { key: "curated_cases_total", label: "累计固化 case", tip: "按仓内固化文件计", icon: Collection },
  { key: "promotions", label: "本周晋升", icon: TrendCharts },
];
const visibleStats = computed(() => {
  const s = stats.value;
  if (!s) return [];
  // 仅「确为 0」隐藏（3-lens 诚实镜头 P3 收紧）：字段缺失/非数字 ≠ 0——那是
  // 数据不可用，格保留并显「—」占位，绝不与真 0 混为一谈静默消失。
  return STAT_DEFS.map((d) => ({ ...d, value: s[d.key] })).filter((d) => !(typeof d.value === "number" && d.value === 0));
});

// 4a 空态文案「本周暂无晋升」要求本地按 weekStartMs 过滤（listGlobalPromotions
// 本身是全局最近 N 条，无 since 参数）——直接掐前 5 条在晋升稀疏时会把「本周
// 之前」的旧晋升误显示成「本周有」，或反过来把「本周确实有」误判成空。
// Date 对象比较而非字符串比较：created_at 是后端归一化的 '+00:00' 后缀，与
// 'Z' 后缀字符串字典序不等价（stats.py 同款坑：ASCII '.'/'Z' 与 '+' 错序），
// 必须转 Date 再比才是真时间序。weekStartMs.value 响应式——跨周/跨日翻新见上。
const recentPromotions = computed(() =>
  promotions.value.filter((p) => Date.parse(p.created_at) >= weekStartMs.value).slice(0, 5)
);

// 4b 今日最活跃 Agent：从已持有的 tasks channel（近 100 条窗口）派生，不再单独
// acquire。B7 P2 修复：此前不分日期统计整个 100 条窗口，标题写「今日」却混入
// 昨天及更早的任务——分组前先按 localDayStartMs 过滤到本地今天创建的任务。
const topActiveAgents = computed(() => {
  const todayStartMs = localDayStartMs();
  const counts = new Map();
  for (const t of feedTasks.value) {
    if (!t.agent_id) continue;
    if (!t.created_at || Date.parse(t.created_at) < todayStartMs) continue;
    counts.set(t.agent_id, (counts.get(t.agent_id) || 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([agent_id, count]) => ({ agent_id, count }));
});

// 请求序号（Codex R2-P2 verbatim）：setup 首拉/迁移补拉/零点定时三处可并发在途，
// 迟到的旧响应不得覆盖新落地（与 liveFeed fresh()/loadFeedback seq 同族守卫）。
let statsSeq = 0;
async function fetchStats() {
  weekStartMs.value = computeWeekStartMs(); // 每次拉取前重算，绝不用挂载时的陈旧边界
  const seq = ++statsSeq;
  try {
    const next = await getStatsOverview(new Date(weekStartMs.value).toISOString());
    if (seq !== statsSeq) return; // 已有更新一轮发起，本响应整包作废
    stats.value = next;
    statsError.value = "";
  } catch (err) {
    if (seq !== statsSeq) return;
    // 诚实地板：失败显式报错，绝不显示 0 冒充无数据。
    statsError.value = err.detail || err.message || "统计不可用";
  }
}

async function fetchPromotions() {
  try {
    promotions.value = await listGlobalPromotions(20);
    promotionsError.value = "";
  } catch (err) {
    promotionsError.value = err.detail || err.message || "晋升列表不可用";
  }
}

fetchStats();
fetchPromotions();

// 跨日翻新兜底（治理审 R1 P2 修复）：排一个「下个本地零点」定时器，触发时
// 重算 weekStartMs（连带纠正版块 5「本周完成」的 since）+ 补拉 stats（版块
// 4a recentPromotions 的过滤直接读 weekStartMs.value，翻新即生效不必单独拉）
// + 重排下一个零点，页面挂机跨日/跨周不再停在挂载那一刻的旧边界。
let midnightTimer = null;
function scheduleNextMidnight() {
  const now = new Date();
  const next = new Date(now);
  next.setHours(24, 0, 0, 0); // 本地下一个零点
  midnightTimer = setTimeout(() => {
    weekStartMs.value = computeWeekStartMs();
    fetchStats();
    scheduleNextMidnight();
  }, next.getTime() - now.getTime());
}
scheduleNextMidnight();

// 补拉纪律（brief §拉取纪律）：任务转 completed 或离开 waiting_review 时才可能
// 产生新的治理事件（完成数/人签数），补拉一次 stats；30s 内去重防事件雨连环拉。
// 不进 liveFeed 轮询——只在真实转移事件上触发。同一订阅内并入亲历仪式判据
// （单一 onTransition 订阅，off 只需配对一次，不造双份补拉）。
// B7 P2 修复：去重窗口内的事件此前直接丢弃——若窗口内是本轮最后一个转移事件，
// 对应的完成/人签数就永远不会补拉，图表可能长期滞后于真实状态。改为排一个
// 尾随定时器在窗口结束时刻兜底跑一次；同一窗口内只排一个（已有 pending 就不再排）。
let lastStatsRefetchAt = 0;
let pendingStatsRefetchTimer = null;
const offTransition = onTransition((ev) => {
  if (ev.to === "completed" || ev.from === "waiting_review") {
    const now = Date.now();
    const sinceLast = now - lastStatsRefetchAt;
    if (sinceLast >= 30000) {
      lastStatsRefetchAt = now;
      fetchStats();
    } else if (pendingStatsRefetchTimer === null) {
      pendingStatsRefetchTimer = setTimeout(() => {
        pendingStatsRefetchTimer = null;
        lastStatsRefetchAt = Date.now();
        fetchStats();
      }, 30000 - sinceLast);
    }
  }
  if (ev.from != null && !TERMINAL_STATUSES.includes(ev.from) && TERMINAL_STATUSES.includes(ev.to)) {
    sealAnimateIds.add(ev.id);
  }
});

function isWork(status) {
  return TASK_WORK_STATES.has(status);
}

function elapsedText(t) {
  const ms = taskElapsedMs(t, Date.now());
  if (ms === null) return "";
  const text = formatDuration(ms);
  // 零值不显示（五律）：亚秒任务「运行 0 秒」是零值噪音——段不硬凑，与
  // StatusCenter runElapsed 把「—」归空串同律；formatDuration(0)="0 秒"
  // 本身有单测锁定，此处只在行级展示层收口。
  return text === "0 秒" ? "" : text;
}

function openTask(id) {
  router.push(`/tasks/${id}`);
}

// 首行摘要「N 项待你签发 ↓」：平滑滚动直达签发版块；reduced-motion 用户瞬时
// 跳转（与本文件 807+ 行的动效削减媒体查询同律，不另造动画）。
const signSection = ref(null);
function scrollToSign() {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  signSection.value?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
}

onUnmounted(() => {
  tasksChannel.release();
  offTransition();
  if (pendingStatsRefetchTimer !== null) clearTimeout(pendingStatsRefetchTimer);
  if (midnightTimer !== null) clearTimeout(midnightTimer);
});
</script>

<style scoped>
.today {
  max-width: 760px;
  margin: 0 auto;
}
.today-head {
  margin-bottom: var(--space-4);
}
.today-title {
  font-family: var(--serif);
  font-size: var(--fs-title);
  font-weight: 600;
  letter-spacing: 0.2px;
  color: var(--ink);
}
.today-error {
  color: var(--trust-fail);
  font-size: 12.5px;
  margin-bottom: var(--space-3);
}
/* 行内重试（批次五 C2）：原生 button 语义（键盘/焦点免费），视觉=安静文字链，
   底色 ink-soft 不占 clay 预算（C3），hover 才亮 clay。 */
.today-retry {
  appearance: none;
  border: 0;
  background: transparent;
  padding: 0;
  margin-left: 6px;
  font: inherit;
  font-size: 12.5px;
  color: var(--ink-soft);
  text-decoration: underline;
  text-underline-offset: 2px;
  cursor: pointer;
}
.today-retry:hover {
  color: var(--clay);
}
.today-skel {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
/* 首行安静摘要（批次八 降噪）：一行文字链取代原三格 overview——amber 与
   签发版块组头同槽（待审语义唯一色），无卡无边，稀疏即尊重。 */
.today-summary {
  margin-bottom: var(--space-4);
}
.today-summary-link {
  appearance: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 0;
  background: transparent;
  padding: 0;
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--trust-pending);
  cursor: pointer;
}
.today-summary-link :deep(.el-icon) {
  font-size: 15px;
}
.today-summary-link:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}
.today-summary-arrow {
  font-weight: 400;
}
.today-section {
  margin-bottom: var(--space-6);
}
.today-section-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-sm);
  font-weight: 700;
  letter-spacing: 0.5px;
  color: var(--ink-faint);
  margin-bottom: var(--space-2);
}
.today-section-head :deep(.el-icon) {
  flex: none;
  font-size: 15px;
}
.today-section-head.waiting {
  color: var(--trust-pending);
}
/* clay 预算（批次五 C3）：「运行中」组头不再染 clay——逐行工作灯已携同一
   语义，组头+灯双重染色=同语义重复着色（一处一行的色彩版）；waiting 组头的
   amber 是行动召唤主 CTA 版块语义（未核槽），保留不动。 */
.today-section-head.working {
  color: var(--ink-mid);
}
.today-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.today-card {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--hairline-soft);
  border-radius: 10px;
  background: var(--card-bg);
  cursor: pointer;
  box-shadow: var(--shadow-card);
  transition: border-color var(--motion-fast) var(--ease-out-soft), transform var(--motion-fast) var(--ease-out-soft), box-shadow var(--motion-fast) var(--ease-out-soft);
}
.today-card:hover {
  border-color: var(--clay-softer);
  transform: translateY(-1px);
  box-shadow: var(--shadow-card-hover);
}
.today-lamp {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  transition: background var(--motion-med) var(--ease-out-soft);
}
.today-card-visual {
  position: relative;
  flex: none;
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border: 1px solid var(--hairline-soft);
  border-radius: 9px;
  background: var(--paper-rail);
  color: var(--ink-soft);
}
.today-card-visual :deep(.el-icon) {
  font-size: 17px;
}
.today-card-visual .today-lamp {
  position: absolute;
  right: -2px;
  bottom: -2px;
  box-shadow: 0 0 0 2px var(--card-bg);
}
.today-lamp.is-pulsing {
  animation: flai-work-pulse var(--pulse-duration) ease-in-out infinite;
}
.today-card-main {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.today-card-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.today-card-sub {
  font-size: 11.5px;
  color: var(--ink-faint);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.today-promo-row {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--hairline-soft);
  border-radius: 10px;
  background: var(--card-bg);
}
.today-promo-icon {
  flex: none;
  width: 30px;
  height: 30px;
  border: 1px solid var(--hairline-soft);
  border-radius: 9px;
  background: var(--paper-rail);
  color: var(--ink-soft);
  font-size: 17px;
}
.today-promo-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.today-promo-main {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
  /* 溢出边界（批次五 C5）：超长晋升标题截断，与同页 today-card-name 同律。 */
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.today-promo-sub {
  font-size: 11.5px;
  color: var(--ink-faint);
}
.today-subhead {
  font-size: 11px;
  font-weight: 700;
  color: var(--ink-faint);
  margin: var(--space-4) 0 var(--space-2);
}
.today-active-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
.today-active-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--ink);
  padding: var(--space-1) var(--space-2);
  border: 1px solid var(--hairline-soft);
  border-radius: 999px;
  background: var(--card-bg);
  /* 溢出边界（批次五 C5）：超长 Agent 名会把胶囊撑满整行（比换行更破版），
     参照 delivery-chip max-width 先例截断。 */
  max-width: 220px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.today-active-chip :deep(.el-icon) {
  flex: none;
  color: var(--ink-soft);
  font-size: 14px;
}
.today-active-chip > span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
.today-stats-bar {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-2);
}
@media (max-width: 520px) {
  .today-stats-bar {
    grid-template-columns: repeat(2, 1fr);
  }
}
.today-stat-tile {
  display: grid;
  grid-template-columns: auto 1fr;
  grid-template-areas:
    "icon number"
    "icon label";
  column-gap: var(--space-2);
  align-items: center;
  padding: var(--space-3) var(--space-3);
  border: 1px solid var(--hairline-soft);
  border-radius: 10px;
  background: var(--card-bg);
  box-shadow: var(--shadow-card);
}
.today-stat-icon {
  grid-area: icon;
  width: 34px;
  height: 34px;
  border: 1px solid var(--hairline-soft);
  border-radius: 10px;
  background: var(--paper-rail);
  color: var(--ink-soft);
  font-size: 19px;
}
.today-stat-num {
  grid-area: number;
  font-size: 22px;
  font-weight: 700;
  color: var(--ink);
  font-family: var(--mono);
  font-variant-numeric: tabular-nums;
}
.today-stat-label {
  grid-area: label;
  font-size: 10.5px;
  color: var(--ink-faint);
  line-height: 1.35;
}
.today-foot-note {
  font-size: 10.5px;
  color: var(--ink-faint);
  border-top: 1px dashed var(--hairline);
  margin-top: var(--space-2);
  padding-top: var(--space-2);
}
@media (prefers-reduced-motion: reduce) {
  .today-lamp.is-pulsing {
    animation: none;
  }
  .today-lamp,
  .today-card {
    transition: none;
  }
}
</style>
