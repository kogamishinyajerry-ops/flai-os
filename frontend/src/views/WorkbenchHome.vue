<template>
  <div class="workbench-home">
    <div class="wb-hero">
      <div class="wb-hero-text">
        <h2>协作工作台</h2>
        <p class="wb-sub">
          把一个繁琐任务交给<strong>智能导引</strong>——它帮你分析、拆解，找到合适的
          Agent 组成协作，或者说清为什么这套系统还不该接这个任务。确认后，被召集的
          Agent 会在这里协同工作，进度、分工与产物一目了然。
        </p>
        <div class="wb-cta">
          <el-button type="primary" @click="$router.push('/')">从导引开始一个协作</el-button>
          <el-button text @click="$router.push('/portal')">浏览已上线的 Agent →</el-button>
        </div>
      </div>
    </div>

    <!-- P1 诚实占位：多 Agent「协作会话」的分组视图在 M8 P3/P4 落地；当前先把
         最近任务总览折进工作台（旧「任务历史」页降级至此）。 -->
    <div class="wb-section">
      <div class="wb-section-head">
        <h3>最近任务</h3>
        <div class="wb-filters">
          <el-select v-model="filters.status" placeholder="状态" clearable size="small" style="width: 140px" @change="load">
            <el-option v-for="(cfg, key) in TASK_STATUS" :key="key" :label="cfg.label" :value="key" />
          </el-select>
          <el-button size="small" text @click="load">刷新</el-button>
        </div>
      </div>
      <p class="wb-note">协作会话（一个任务召集多个 Agent 协同）视图正在 M8 建设中；现在这里是单个任务的台账。</p>

      <el-alert v-if="loadError" type="error" :title="loadError" show-icon :closable="false" class="wb-alert" />

      <div v-loading="loading" class="wb-list">
        <div v-for="t in tasks" :key="t.id" class="wb-row" @click="goDetail(t)">
          <span class="wb-lamp" :style="{ background: lampColor(t.status) }" :title="statusLabel(t.status)"></span>
          <span class="wb-name">{{ t.name || t.id.slice(0, 12) }}</span>
          <span class="wb-agent">{{ t.agent_id }}</span>
          <span class="wb-status" :style="{ color: lampColor(t.status) }">{{ statusLabel(t.status) }}</span>
          <span class="wb-by">{{ t.created_by }}</span>
          <span class="wb-time">{{ formatTime(t.created_at) }}</span>
        </div>
        <el-empty v-if="!loading && tasks.length === 0" description="还没有任务——从导引开始一个协作吧" />
      </div>

      <div v-if="hasMore" class="wb-more">
        <el-button :loading="loadingMore" text @click="loadMore">加载更多</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from "vue";
import { useRouter } from "vue-router";
import { listTasks } from "../api/tasks";
import { statusLabel, formatTime, TASK_STATUS } from "../utils/format";

const router = useRouter();
const tasks = ref([]);
const loading = ref(false);
const loadingMore = ref(false);
const loadError = ref("");
const PAGE_SIZE = 100;
const hasMore = ref(false);
const filters = reactive({ status: "" });

// 到席灯配色守信任色锁（App.vue :root 注释）：
// - running/validating/parsing/analyzing = clay（工作态/live）
// - waiting_review = amber（未核·待人签；teal 只留给「已签」这个动作本身，不预支）
// - failed = 红（真失败）
// - completed = 中性墨（**不给绿**——绿仅真实 REAL 结果，当前跑的是 mock，
//   给绿即假 REAL；等真实性能盘接入产出可核结果再解锁绿）
// - created/queued/cancelled = 淡墨（待命/终止）
const _WORK_STATES = new Set(["running", "validating", "parsing", "analyzing"]);
function lampColor(status) {
  if (_WORK_STATES.has(status)) return "var(--clay)";
  if (status === "waiting_review") return "var(--trust-pending)";
  if (status === "failed") return "var(--trust-fail)";
  if (status === "completed") return "var(--ink-soft)";
  return "var(--ink-faint)";
}

function _query(offset) {
  return { status: filters.status || undefined, limit: PAGE_SIZE, offset };
}

async function load() {
  loading.value = true;
  try {
    const page = await listTasks(_query(0));
    tasks.value = page;
    hasMore.value = page.length === PAGE_SIZE;
    loadError.value = "";
  } catch (err) {
    loadError.value = err.detail || err.message;
  } finally {
    loading.value = false;
  }
}

async function loadMore() {
  loadingMore.value = true;
  try {
    const page = await listTasks(_query(tasks.value.length));
    tasks.value = tasks.value.concat(page);
    hasMore.value = page.length === PAGE_SIZE;
    loadError.value = "";
  } catch (err) {
    loadError.value = err.detail || err.message;
  } finally {
    loadingMore.value = false;
  }
}

function goDetail(t) {
  router.push(`/tasks/${t.id}`);
}

onMounted(load);
</script>

<style scoped>
.wb-hero {
  background: linear-gradient(135deg, var(--paper-cream), var(--paper-surface));
  border: 1px solid var(--hairline);
  border-radius: 14px;
  padding: 28px 30px;
  margin-bottom: 24px;
}
.wb-hero h2 {
  margin: 0 0 8px;
  font-size: 22px;
}
.wb-sub {
  margin: 0 0 18px;
  max-width: 720px;
  line-height: 1.7;
  color: var(--ink-soft);
}
.wb-cta {
  display: flex;
  gap: 12px;
  align-items: center;
}
.wb-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.wb-section-head h3 {
  margin: 0;
}
.wb-filters {
  display: flex;
  gap: 8px;
  align-items: center;
}
.wb-note {
  margin: 0 0 14px;
  font-size: 12px;
  color: var(--ink-faint);
}
.wb-alert {
  margin-bottom: 12px;
}
.wb-row {
  display: grid;
  grid-template-columns: 16px 1fr 160px 96px 96px 160px;
  gap: 12px;
  align-items: center;
  padding: 12px 14px;
  border: 1px solid var(--hairline-soft);
  border-radius: 10px;
  margin-bottom: 8px;
  background: var(--card-bg);
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.wb-row:hover {
  border-color: var(--clay-softer);
  box-shadow: 0 2px 10px rgba(72, 58, 44, 0.06);
}
.wb-lamp {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}
.wb-name {
  font-weight: 600;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wb-agent {
  color: var(--ink-soft);
  font-size: 13px;
}
.wb-status {
  font-size: 13px;
  font-weight: 600;
}
.wb-by,
.wb-time {
  color: var(--ink-faint);
  font-size: 12px;
}
.wb-more {
  display: flex;
  justify-content: center;
  margin-top: 8px;
}
@media (max-width: 720px) {
  .wb-row {
    grid-template-columns: 16px 1fr auto;
  }
  .wb-agent,
  .wb-by,
  .wb-time {
    display: none;
  }
}
</style>
