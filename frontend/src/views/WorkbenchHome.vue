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

    <!-- 协作会话（M8 P4）：导引召集成方案的会话，进入即见分工架构+进度。 -->
    <div v-if="sessions.length" class="wb-section">
      <div class="wb-section-head">
        <h3>协作会话</h3>
      </div>
      <p class="wb-note">导引召集了合适 Agent 组成协作的会话——点开看分工架构、召集进度与产物。</p>
      <div class="sess-grid">
        <div v-for="c in sessions" :key="c.id" class="sess-card" @click="goSession(c)">
          <div class="sess-card-bar"></div>
          <div class="sess-card-inner">
            <div class="sess-card-goal">{{ c.recommendation.goal || "协作会话" }}</div>
            <div class="sess-card-meta">
              <span class="sess-card-count">{{ (c.recommendation.agents || []).length }} 个 Agent</span>
              <el-tag :type="c.status === 'active' ? 'primary' : 'info'" effect="plain" size="small">
                {{ c.status === "active" ? "进行中" : "已归档" }}
              </el-tag>
            </div>
            <div class="sess-card-by">{{ c.created_by }} · {{ formatTime(c.created_at) }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 最近任务台账（旧「任务历史」页降级折入此处）。 -->
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
import { listConversations } from "../api/conversations";
import { statusLabel, formatTime, TASK_STATUS, taskLampColor } from "../utils/format";

const router = useRouter();
const tasks = ref([]);
const loading = ref(false);
const loadingMore = ref(false);
const loadError = ref("");
const PAGE_SIZE = 100;
const hasMore = ref(false);
const filters = reactive({ status: "" });

// 协作会话（M8 P4）：已形成召集方案（orchestrate）的导引会话——协作工作台的主对象。
const sessions = ref([]);
async function loadSessions() {
  try {
    const convs = await listConversations({ limit: 100 });
    sessions.value = convs.filter((c) => c.recommendation && c.recommendation.decision === "orchestrate");
  } catch {
    sessions.value = []; // 会话列表失败不阻断任务台账；诚实留空
  }
}
function goSession(c) {
  router.push(`/workbench/${c.id}`);
}

// 到席灯配色守信任色锁：抽到 utils/format.js 的 taskLampColor 单处（协作会话共用），
// 关键纪律——completed **不给绿**（跑 mock，给绿即假 REAL）。
const lampColor = taskLampColor;

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

onMounted(() => {
  load();
  loadSessions();
});
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
.sess-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}
.sess-card {
  border: 1px solid var(--hairline);
  border-radius: 12px;
  overflow: hidden;
  background: var(--card-bg);
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.sess-card:hover {
  border-color: var(--clay-softer);
  box-shadow: 0 2px 12px rgba(72, 58, 44, 0.07);
}
.sess-card-bar {
  height: 4px;
  background: var(--clay);
}
.sess-card-inner {
  padding: 14px 16px;
}
.sess-card-goal {
  font-weight: 600;
  color: var(--ink);
  line-height: 1.5;
  margin-bottom: 10px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.sess-card-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.sess-card-count {
  font-size: 12px;
  font-weight: 600;
  color: var(--clay);
}
.sess-card-by {
  font-size: 12px;
  color: var(--ink-faint);
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
