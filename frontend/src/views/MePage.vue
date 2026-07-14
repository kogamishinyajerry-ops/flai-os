<template>
  <div class="me-page">
    <div class="page-header">
      <h2>我的贡献</h2>
      <p class="page-sub">仅你本人可见 · 只统计可精确归因的贡献</p>
    </div>

    <el-alert v-if="loadError" type="error" :title="loadError" show-icon :closable="false" class="page-alert" />

    <!-- 版块1：贡献概览（精确） -->
    <div class="me-overview">
      <div class="me-stat"><span class="me-stat-num">{{ contrib?.since_created ?? "—" }}</span><span class="me-stat-label">本周发起</span></div>
      <div class="me-stat"><span class="me-stat-num">{{ contrib?.since_completed ?? "—" }}</span><span class="me-stat-label">本周完成</span></div>
      <div class="me-stat"><span class="me-stat-num">{{ contrib?.waiting_review ?? "—" }}</span><span class="me-stat-label">待我跟进</span></div>
      <div class="me-stat"><span class="me-stat-num">{{ contrib?.total_created ?? "—" }}</span><span class="me-stat-label">累计发起</span></div>
    </div>

    <!-- 版块2：我发起的任务（精确） -->
    <div class="me-section">
      <div class="me-section-label">最近发起的任务</div>
      <EmptyState v-if="!loading && !loadError && !myTasks.length" description="你还没有发起任务" />
      <div v-else class="me-task-list">
        <a v-for="t in myTasks" :key="t.id" class="me-task-item" @click="openTask(t)">
          <span class="me-task-name">{{ t.name || t.agent_id }}</span>
          <span class="me-task-status">{{ statusLabel(t.status) }}</span>
          <span class="me-task-time">{{ formatTime(t.created_at) }}</span>
        </a>
      </div>
      <div v-if="contrib && contrib.total_created > myTasks.length" class="me-feedback-note">
        仅显示最近 {{ myTasks.length }} 条，共发起 {{ contrib.total_created }} 条
      </div>
    </div>

    <!-- 版块3：我的反馈（近似，显式标注） -->
    <div class="me-section">
      <div class="me-section-label">我的反馈</div>
      <div class="me-feedback-count">{{ contrib?.feedback_count_approx ?? "—" }} 条</div>
      <div class="me-feedback-note">按显示名近似统计（可能与同名者混计）——反馈无唯一身份列</div>
    </div>

    <!-- 版块4：团队总量（复用批B，无人际排名） -->
    <div class="me-section">
      <div class="me-section-label">团队总量</div>
      <div class="me-team-bar">
        <span>本周完成 {{ team?.tasks_completed ?? "—" }}</span>
        <span>本周签发 {{ team?.reviews_approved ?? "—" }}</span>
        <span>累计固化 {{ team?.curated_cases_total ?? "—" }}</span>
        <span>本周晋升 {{ team?.promotions ?? "—" }}</span>
      </div>
      <div class="me-team-note">团队总量仅作氛围对照，不含任何人际排名</div>
    </div>

    <!-- 版块5：诚实缺口条（显式上屏，非装饰） -->
    <div class="me-honest-gap">
      签发 / 样本认可的个人归因待后续——签发唯一身份当前仅在审计轨留痕（人是唯一签发者），暂无应用数据读路径。此页只统计可精确归因的发起贡献。
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from "vue";
import { useRouter } from "vue-router";
import { fetchMyContributions, fetchMyTasks } from "../api/me";
import { request } from "../api/client";
import EmptyState from "../components/EmptyState.vue";
import { formatTime, statusLabel } from "../utils/format";
import { currentUser } from "../stores/session";

const router = useRouter();
const contrib = ref(null);
const myTasks = ref([]);
const team = ref(null);
const loading = ref(true);
const loadError = ref("");

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
  } catch (err) {
    if (seq !== loadSeq) return;
    loadError.value = err.detail || err.message || "加载失败";
  } finally {
    if (seq === loadSeq) loading.value = false;
  }
}

function openTask(t) {
  router.push({ path: `/tasks/${t.id}` });
}

onMounted(load);

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
.page-header { margin-bottom: 20px; }
.page-header h2 { font-family: var(--serif); font-size: 27px; font-weight: 600; margin: 0 0 6px; }
.page-sub { margin: 0; color: var(--ink-faint); font-size: 13px; }
.page-alert { margin-bottom: 16px; }
.me-overview { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }
.me-stat {
  display: flex; flex-direction: column; gap: 4px; padding: 16px 18px;
  border: 1px solid var(--hairline); border-radius: 12px; background: var(--paper-rail);
}
.me-stat-num { font-size: 26px; font-weight: 700; color: var(--ink); font-family: var(--serif); }
.me-stat-label { font-size: 12px; color: var(--ink-soft); }
.me-section { margin-bottom: 22px; }
.me-section-label { font-size: 11.5px; font-weight: 700; color: var(--ink-faint); margin-bottom: 8px; }
.me-task-list { display: flex; flex-direction: column; gap: 6px; }
.me-task-item {
  display: flex; align-items: center; gap: 12px; padding: 10px 14px; cursor: pointer;
  border: 1px solid var(--hairline); border-radius: 8px;
}
.me-task-item:hover { border-color: var(--clay-softer); }
.me-task-name { flex: 1; color: var(--ink); font-size: 13.5px; }
.me-task-status { color: var(--ink-soft); font-size: 12px; }
.me-task-time { color: var(--ink-faint); font-size: 11.5px; }
.me-feedback-count { font-size: 18px; font-weight: 700; color: var(--ink); }
.me-feedback-note { color: var(--ink-faint); font-size: 11.5px; margin-top: 4px; }
.me-team-bar { display: flex; gap: 18px; color: var(--ink-soft); font-size: 13px; }
.me-team-note { color: var(--ink-faint); font-size: 11px; margin-top: 6px; }
.me-honest-gap {
  margin-top: 24px; padding: 12px 14px; border: 1px dashed var(--hairline);
  border-radius: 8px; background: var(--paper-rail);
  color: var(--ink-faint); font-size: 12px; line-height: 1.6;
}

@media (max-width: 640px) {
  .me-overview { grid-template-columns: repeat(2, 1fr); }
  .me-team-bar { flex-wrap: wrap; gap: 10px 18px; }
}
</style>
