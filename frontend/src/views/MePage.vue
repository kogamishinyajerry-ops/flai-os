<template>
  <div class="me-page">
    <div class="page-header">
      <h2>我的贡献</h2>
      <p class="page-sub">仅你本人可见 · 只统计可精确归因的贡献</p>
    </div>

    <el-alert v-if="loadError" type="error" :title="loadError" show-icon :closable="false" class="page-alert" />

    <!-- 版块1：贡献概览（精确）。零值不显示（批次四 Q2）：已加载后 0 值格不渲染
         ——0 不是信息；data-stat 语义锚供 e2e 按字段对表（不再用 :last-child 位置
         定位）。未加载（contrib 为 null）保持四格「—」占位，不冒充有数据。 -->
    <div v-if="!contrib || visibleMeStats.length" class="me-overview">
      <template v-if="contrib">
        <div v-for="s in visibleMeStats" :key="s.key" class="me-stat" :data-stat="s.key">
          <span class="me-stat-num">{{ typeof s.value === "number" ? s.value : "—" }}</span><span class="me-stat-label">{{ s.label }}</span>
        </div>
      </template>
      <template v-else>
        <div v-for="s in ME_STAT_DEFS" :key="s.key" class="me-stat" :data-stat="s.key">
          <span class="me-stat-num">—</span><span class="me-stat-label">{{ s.label }}</span>
        </div>
      </template>
    </div>
    <EmptyState v-else variant="data" tier="line" description="还没有可统计的贡献——从对话发起第一个任务吧" />

    <!-- 版块2：我发起的任务（精确） -->
    <div class="me-section">
      <div class="section-label">最近发起的任务</div>
      <!-- 首载骨架（A3 同款）：everLoaded 只在首次成功后置 true 且恒 true——跨
           跨日定时刷新/换号刷新不回骨架，只有真·首次加载空窗期显示骨架。 -->
      <div v-if="!everLoaded && !loadError" class="me-task-skel" role="status">
        <span class="skel-sr">任务列表加载中…</span>
        <SkeletonBlock v-for="i in 3" :key="i" height="38px" />
      </div>
      <EmptyState v-else-if="!loading && !loadError && !myTasks.length" description="你还没有发起任务" />
      <div v-else class="me-task-list">
        <router-link v-for="t in myTasks" :key="t.id" class="me-task-item" :to="`/tasks/${t.id}`">
          <!-- 人话称呼（批次四 Q1）：缺名回退 Agent 显示名（原为裸 agent_id）。 -->
          <span class="me-task-name">{{ taskDisplayName(t, agentNames.map) }}</span>
          <span class="me-task-status">{{ statusLabel(t.status) }}</span>
          <!-- 行级紧凑时钟（批次三 G4 孪生面）：与 StatusCenter 行/CompletionSeal
               同 formatClockCompact SSOT——同屏扫读面绝不再现 locale 全量串。 -->
          <span class="me-task-time">{{ formatClockCompact(t.created_at, todayKey) }}</span>
        </router-link>
      </div>
      <div v-if="contrib && contrib.total_created > myTasks.length" class="me-feedback-note">
        仅显示最近 {{ myTasks.length }} 条，共发起 {{ contrib.total_created }} 条
      </div>
    </div>

    <!-- 版块3：我的反馈（近似，显式标注）。零值收敛（批次四 Q2）：0 条时整段
         收一行安静空态——计数与近似口径注只在真有数据时出现（诚实口径注是
         「已显示数字」的限定语，没有数字就没有被限定对象）。 -->
    <div class="me-section">
      <div class="section-label">我的反馈</div>
      <template v-if="feedbackCount === null">
        <div class="me-feedback-count">—</div>
      </template>
      <EmptyState v-else-if="feedbackCount === 0" variant="data" tier="line" description="还没有反馈记录" />
      <template v-else>
        <div class="me-feedback-count">{{ feedbackCount }} 条</div>
        <div class="me-feedback-note" title="反馈无唯一身份列，按显示名匹配，可能与同名者混计">按显示名近似统计，可能与同名者混计</div>
      </template>
    </div>

    <!-- 版块4：团队总量（复用批B口径，无人际排名）。零值项不渲染（Q2，与今日页
         团队总量同律）；全 0 收一行。 -->
    <div class="me-section">
      <div class="section-label">团队总量</div>
      <div v-if="!team || visibleTeamStats.length" class="me-team-bar">
        <template v-if="team">
          <span v-for="s in visibleTeamStats" :key="s.key" :data-stat="s.key">{{ s.label }} {{ typeof s.value === "number" ? s.value : "—" }}</span>
        </template>
        <template v-else>
          <span v-for="s in TEAM_STAT_DEFS" :key="s.key">{{ s.label }} —</span>
        </template>
      </div>
      <EmptyState v-else variant="data" tier="line" description="本周还没有可统计的团队动态" />
      <div class="me-team-note">团队总量仅作氛围对照，不含任何人际排名</div>
    </div>

    <!-- 版块5：诚实缺口条（显式上屏，非装饰；批次四 Q3 压缩为一行——红线语义
         「人是唯一签发者」与缺口事实保留，细节措辞收短）。 -->
    <div class="me-honest-gap">
      此页只统计可精确归因的发起贡献；签发/样本认可的归因待后续（人是唯一签发者，签发身份现仅留审计轨）。
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from "vue";
import { fetchMyContributions, fetchMyTasks } from "../api/me";
import { request } from "../api/client";
import EmptyState from "../components/EmptyState.vue";
import SkeletonBlock from "../components/SkeletonBlock.vue";
import { formatClockCompact, statusLabel, taskDisplayName } from "../utils/format";
import { useTodayKey } from "../composables/useTodayKey";
import { useAgentNames } from "../stores/agentNames";
import { currentUser } from "../stores/session";

// 响应式日界（G4）：本页是静态拉取面（无轮询），跨午夜后紧凑时钟的同日判据
// 必须能自行翻页——useTodayKey 卸载即清（与 CompletionSeal 同 SSOT）。
const todayKey = useTodayKey();

const contrib = ref(null);
const myTasks = ref([]);
const team = ref(null);
const loading = ref(true);
const loadError = ref("");

// Agent 人话名册（批次四 Q1）：任务行缺名时回退注册表显示名。
const agentNames = useAgentNames();

// 零值不显示（批次四 Q2）：>0 才渲染；隐藏格的「确为 0」由 e2e 按 data-stat
// 对照 /api/me/contributions 与 /api/stats/overview 真值核验。字段=后端投影，
// 此处只做展示映射。
const ME_STAT_DEFS = [
  { key: "since_created", label: "本周发起" },
  { key: "since_completed", label: "本周完成" },
  { key: "waiting_review", label: "待我跟进" },
  { key: "total_created", label: "累计发起" },
];
const visibleMeStats = computed(() => {
  const c = contrib.value;
  if (!c) return [];
  // 仅「确为 0」隐藏；字段缺失/非数字=数据不可用，保格显「—」（与今日页同律）。
  return ME_STAT_DEFS.map((d) => ({ ...d, value: c[d.key] })).filter((d) => !(typeof d.value === "number" && d.value === 0));
});

const TEAM_STAT_DEFS = [
  { key: "tasks_completed", label: "本周完成" },
  { key: "reviews_approved", label: "本周签发" },
  { key: "curated_cases_total", label: "累计固化" },
  { key: "promotions", label: "本周晋升" },
];
const visibleTeamStats = computed(() => {
  const t = team.value;
  if (!t) return [];
  return TEAM_STAT_DEFS.map((d) => ({ ...d, value: t[d.key] })).filter((d) => !(typeof d.value === "number" && d.value === 0));
});

// 反馈计数三态：null=未加载（显「—」）/ 0=收敛空态 / >0 显示计数+近似口径注。
const feedbackCount = computed(() => {
  const v = contrib.value?.feedback_count_approx;
  return typeof v === "number" ? v : null;
});
// 首载完成标记（A3 同款，与 loading 解耦）：loading 在跨日定时刷新/换号刷新时
// 每次都会重置 true，若骨架直接绑 loading 会在这些静默刷新时闪回骨架——只在
// 从未成功过时为 false，成功一次后恒 true。
const everLoaded = ref(false);

// 批B TodayPage 同款：本地周一零点（避免与后端窗口口径漂移）
function weekStartIso() {
  const now = new Date();
  const day = (now.getDay() + 6) % 7; // 周一=0
  const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - day, 0, 0, 0, 0);
  return monday.toISOString();
}

let loadSeq = 0;
async function load() {
  const seq = ++loadSeq;
  loading.value = true;
  loadError.value = "";
  const since = weekStartIso();
  try {
    const [c, t, s] = await Promise.all([
      fetchMyContributions(since),
      fetchMyTasks(20),
      request(`/api/stats/overview?since=${encodeURIComponent(since)}`),
    ]);
    if (seq !== loadSeq) return; // 陈旧响应丢弃（换号期间 in-flight 不落地）
    contrib.value = c;
    myTasks.value = t;
    team.value = s;
    everLoaded.value = true;
  } catch (err) {
    if (seq !== loadSeq) return;
    loadError.value = err.detail || err.message || "加载失败";
  } finally {
    if (seq === loadSeq) loading.value = false;
  }
}

// 跨日/跨周零点翻新（Codex R2，同 TodayPage）：页面挂机跨过本地零点时 since 会停在
// 挂载那天的旧边界，本周 tiles 漂移。排「下个本地零点」定时器：触发即重拉（load 内
// 每次重算 weekStartIso）并重排；跨日必先跨周则连带纠正。
let midnightTimer = null;
function scheduleMidnightRefresh() {
  const next = new Date();
  next.setHours(24, 0, 0, 0); // 下一个本地零点
  midnightTimer = window.setTimeout(() => {
    load();
    scheduleMidnightRefresh();
  }, next.getTime() - Date.now());
}

onMounted(() => {
  load();
  scheduleMidnightRefresh();
});
onUnmounted(() => {
  if (midnightTimer) window.clearTimeout(midnightTimer);
});

// 换号纠偏（Codex R1 P1）：另一标签页登出换号→本标签 focus 纠正 currentUser 但页面
// 不重挂（identityReady/route 不变），/me 是私有页会残留旧用户私有数据。监听 username
// 变化：立即清空旧数据（不留残影）+ 重新拉取（seq 丢弃 in-flight 旧响应）。
watch(() => currentUser.value?.username, (next, prev) => {
  if (next === prev) return;
  contrib.value = null;
  myTasks.value = [];
  team.value = null;
  load();
});
</script>

<style scoped>
.page-header { margin-bottom: var(--space-5); }
.page-header h2 { font-family: var(--serif); font-size: var(--fs-title); font-weight: 600; letter-spacing: 0.2px; margin: 0 0 6px; }
.page-sub { margin: 0; color: var(--ink-faint); font-size: 13px; }
.page-alert { margin-bottom: var(--space-4); }
.me-overview { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--space-3); margin-bottom: var(--space-6); }
.me-stat {
  display: flex; flex-direction: column; gap: var(--space-1); padding: var(--space-4) 18px;
  border: 1px solid var(--hairline); border-radius: var(--radius-lg); background: var(--paper-rail);
}
.me-stat-num { font-size: 26px; font-weight: 700; color: var(--ink); font-family: var(--serif); }
.me-stat-label { font-size: 12px; color: var(--ink-soft); }
.me-section { margin-bottom: 22px; }
.me-task-skel { display: flex; flex-direction: column; gap: var(--space-2); }
/* 读屏专用（视觉裁剪，AT 可读；Codex R2 P2）。 */
.skel-sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
.me-task-list { display: flex; flex-direction: column; gap: 6px; }
.me-task-item {
  display: flex; align-items: center; gap: var(--space-3); padding: 10px 14px; cursor: pointer;
  border: 1px solid var(--hairline); border-radius: var(--radius-md);
}
.me-task-item:hover { border-color: var(--clay-softer); }
.me-task-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--ink); font-size: 13.5px; }
.me-task-status { color: var(--ink-soft); font-size: 12px; }
.me-task-time { color: var(--ink-faint); font-size: 11.5px; }
.me-feedback-count { font-size: 18px; font-weight: 700; color: var(--ink); }
.me-feedback-note { color: var(--ink-faint); font-size: 11.5px; margin-top: var(--space-1); }
.me-team-bar { display: flex; gap: 18px; color: var(--ink-soft); font-size: 13px; }
.me-team-note { color: var(--ink-faint); font-size: 11px; margin-top: 6px; }
.me-honest-gap {
  margin-top: var(--space-6); padding: var(--space-3) 14px; border: 1px dashed var(--hairline);
  border-radius: var(--radius-md); background: var(--paper-rail);
  color: var(--ink-faint); font-size: 12px; line-height: 1.6;
}

@media (max-width: 640px) {
  .me-overview { grid-template-columns: repeat(2, 1fr); }
  .me-team-bar { flex-wrap: wrap; gap: 10px 18px; }
}
</style>
