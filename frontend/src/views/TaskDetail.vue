<template>
  <div class="task-detail" v-loading="loading">
    <el-alert v-if="loadError" type="error" :title="loadError" show-icon :closable="false" />

    <template v-if="task">
      <!-- M8：属于某协作会话的任务，提供返回工作台会话视图的入口（分组回溯）。 -->
      <div v-if="task.conversation_id" class="sess-backlink">
        <el-button text type="primary" @click="$router.push(`/workbench/${task.conversation_id}`)">
          ← 返回协作会话
        </el-button>
      </div>
      <div class="page-header">
        <h2>任务详情</h2>
        <el-tag :type="statusTagType(task.status)">{{ statusLabel(task.status) }}</el-tag>
        <!-- 批量任务摘要（P2）：消解「全失败 case 仍显示绿色已完成」的误导——
             ok/failed 计数取自最后一条 summary_generated 折叠事件，纯前端派生。 -->
        <template v-if="batchSummary">
          <el-tag size="small" type="success">成功 {{ batchSummary.ok }}</el-tag>
          <el-tag size="small" :type="batchSummary.failed > 0 ? 'danger' : 'info'">
            失败 {{ batchSummary.failed }}
          </el-tag>
        </template>
        <!-- waiting_review 时轮询停止（避免无人值守页面永久空转），跨会话的
             人工放行结果靠本按钮手动拉取（反方审查 P2-1）。 -->
        <el-button text type="primary" class="refresh-btn" @click="loadTask()">刷新</el-button>
      </div>

      <el-descriptions :column="2" border class="task-descriptions">
        <el-descriptions-item label="ID">{{ task.id }}</el-descriptions-item>
        <el-descriptions-item label="Agent ID">{{ task.agent_id }}</el-descriptions-item>
        <el-descriptions-item label="Agent 版本">{{ task.agent_version }}</el-descriptions-item>
        <el-descriptions-item label="任务名称">{{ task.name || "—" }}</el-descriptions-item>
        <el-descriptions-item label="创建人">{{ task.created_by }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ formatTime(task.created_at) }}</el-descriptions-item>
        <el-descriptions-item label="开始时间">{{ formatTime(task.started_at) }}</el-descriptions-item>
        <el-descriptions-item label="结束时间">{{ formatTime(task.finished_at) }}</el-descriptions-item>
      </el-descriptions>

      <el-alert
        v-if="task.error_message"
        type="error"
        :title="task.error_message"
        show-icon
        :closable="false"
        class="section"
      />

      <!-- 产物：签发前把要签的东西摆在眼前（不再只给 hash 命名的下载按钮）。
           放在「动作」之前——先看产物，再决定放行（信任核心 P0-2）。 -->
      <div class="section" v-if="artifacts.length">
        <h3>产物<span v-if="isWaitingReview" class="artifact-review-hint">放行前请先审阅</span></h3>
        <div v-for="a in artifacts" :key="a.fileId" class="artifact-card">
          <div class="artifact-head">
            <span class="artifact-name">{{ a.filename }}</span>
            <span v-if="!a.loading && a.size" class="artifact-size">{{ formatSize(a.size) }}</span>
            <a :href="downloadUrl(a.fileId)" download class="artifact-download">下载</a>
          </div>
          <div v-if="a.loading" class="artifact-body muted">加载中…</div>
          <div v-else-if="a.error" class="artifact-body artifact-error">产物加载失败：{{ a.error }}</div>
          <MarkdownLite
            v-else-if="a.isText && (a.ext === 'md' || a.ext === 'markdown')"
            :text="a.text"
            class="artifact-body"
          />
          <pre v-else-if="a.isText" class="artifact-body artifact-pre">{{ a.text }}</pre>
          <div v-else class="artifact-body muted">二进制文件，请下载后查看。</div>
        </div>
      </div>

      <div class="section" v-if="canCancel || isWaitingReview">
        <h3>动作</h3>
        <el-button v-if="canCancel" type="danger" plain @click="handleCancel">取消任务</el-button>

        <el-card v-if="isWaitingReview" shadow="never" class="review-card">
          <el-form label-width="80px">
            <el-form-item label="审核人" required>
              <el-input v-model="reviewForm.reviewer" placeholder="你的名字" />
            </el-form-item>
            <el-form-item label="意见">
              <el-input v-model="reviewForm.comment" type="textarea" :rows="2" placeholder="可选" />
            </el-form-item>
            <div class="review-note">
              批准即代表你作为工程师背书该产物——签发权在你，平台不代签。
            </div>
            <el-form-item>
              <!-- 批准=人签，用信任锁的 teal（--trust-signed），绝不用绿（绿仅表真实结果）。 -->
              <el-button class="approve-btn" :loading="reviewing" @click="handleReview('approve')">批准放行</el-button>
              <el-button type="danger" :loading="reviewing" @click="handleReview('reject')">拒绝</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </div>

      <div class="section">
        <h3>事件时间轴</h3>
        <el-empty v-if="events.length === 0" description="暂无事件" />
        <el-timeline v-else>
          <el-timeline-item
            v-for="e in events"
            :key="e.event_id"
            :timestamp="formatTime(e.created_at)"
            :color="LEVEL_COLOR[e.level] || LEVEL_COLOR.info"
          >
            <div class="event-type">{{ e.event_type }}</div>
            <div class="event-message">{{ e.message }}</div>
            <el-collapse v-if="e.payload && Object.keys(e.payload).length">
              <el-collapse-item title="payload">
                <pre class="payload-json">{{ JSON.stringify(e.payload, null, 2) }}</pre>
              </el-collapse-item>
            </el-collapse>
          </el-timeline-item>
        </el-timeline>
      </div>

      <div class="section" v-if="isTerminal">
        <h3>反馈</h3>
        <el-alert v-if="feedbackError" type="warning" :title="feedbackError" show-icon :closable="false" />
        <el-form label-width="80px" class="feedback-form">
          <el-form-item label="评价">
            <el-radio-group v-model="feedbackForm.rating">
              <el-radio value="good">可用</el-radio>
              <el-radio value="bad">不可用</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="分类">
            <el-select v-model="feedbackForm.category" placeholder="请选择">
              <el-option v-for="c in FEEDBACK_CATEGORIES" :key="c.value" :label="c.label" :value="c.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="说明">
            <el-input v-model="feedbackForm.message" type="textarea" :rows="2" placeholder="可选" />
          </el-form-item>
          <el-form-item label="创建人" required>
            <el-input v-model="feedbackForm.createdBy" placeholder="你的名字" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="submittingFeedback" @click="handleSubmitFeedback">提交反馈</el-button>
          </el-form-item>
        </el-form>

        <el-empty v-if="feedbackList.length === 0" description="暂无反馈" />
        <ul v-else class="feedback-list">
          <li v-for="f in feedbackList" :key="f.id">
            <el-tag size="small" :type="f.rating === 'good' ? 'success' : 'danger'">
              {{ f.rating === "good" ? "可用" : "不可用" }}
            </el-tag>
            <span class="feedback-category">{{ categoryLabel(f.category) }}</span>
            <span class="feedback-message">{{ f.message }}</span>
            <span class="feedback-meta">{{ f.created_by }} · {{ formatTime(f.created_at) }}</span>
          </li>
        </ul>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from "vue";
import { useRoute } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { getTask, listTaskEvents, cancelTask, reviewTask } from "../api/tasks";
import { downloadUrl, fetchOutputFile } from "../api/files";
import { submitFeedback, listTaskFeedback, FEEDBACK_CATEGORIES } from "../api/feedback";
import { statusLabel, statusTagType, formatTime, LEVEL_COLOR } from "../utils/format";
import MarkdownLite from "../components/MarkdownLite.vue";
import { getSavedName, saveName } from "../utils/identity";

const route = useRoute();
const taskId = route.params.taskId;

const task = ref(null);
const events = ref([]);
const loading = ref(true);
const loadError = ref("");

const reviewForm = reactive({ reviewer: getSavedName(), comment: "" });
const reviewing = ref(false);

// 产物内联查看（P0-2）：按 task.output_file_ids 拉取文件名+内容，增量同步、集合未变不重拉。
const artifacts = ref([]);

async function syncArtifacts(ids) {
  const list = Array.isArray(ids) ? ids : [];
  const existing = new Map(artifacts.value.map((a) => [a.fileId, a]));
  const next = [];
  const toFetch = [];
  for (const id of list) {
    if (existing.has(id)) {
      next.push(existing.get(id));
    } else {
      const ph = reactive({
        fileId: id,
        filename: id.slice(0, 8),
        isText: false,
        text: null,
        ext: "",
        size: 0,
        loading: true,
        error: "",
      });
      next.push(ph);
      toFetch.push(ph);
    }
  }
  artifacts.value = next;
  for (const ph of toFetch) {
    try {
      Object.assign(ph, await fetchOutputFile(ph.fileId), { loading: false, error: "" });
    } catch (err) {
      ph.loading = false;
      ph.error = err.detail || err.message || "加载失败";
    }
  }
}

function formatSize(bytes) {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const feedbackForm = reactive({ rating: "good", category: "", message: "", createdBy: getSavedName() });
const submittingFeedback = ref(false);
const feedbackList = ref([]);
const feedbackError = ref("");

const CATEGORY_LABEL_MAP = Object.fromEntries(FEEDBACK_CATEGORIES.map((c) => [c.value, c.label]));
const categoryLabel = (c) => CATEGORY_LABEL_MAP[c] ?? c;

// 批量任务摘要：从已拉取 events 找最后一条 agent_log 且
// workflow_event_type=='summary_generated'（性能盘类批量 Agent 发出）；
// 无该事件的任务（如 hello_agent）返回 null，不显示，零影响。
const batchSummary = computed(() => {
  for (let i = events.value.length - 1; i >= 0; i--) {
    const e = events.value[i];
    if (
      e.event_type === "agent_log" &&
      e.payload?.workflow_event_type === "summary_generated" &&
      e.payload.ok_count != null &&
      e.payload.failed_count != null
    ) {
      return { ok: e.payload.ok_count, failed: e.payload.failed_count };
    }
  }
  return null;
});

const canCancel = computed(() => ["created", "queued"].includes(task.value?.status));
const isWaitingReview = computed(() => task.value?.status === "waiting_review");
const isTerminal = computed(() => ["completed", "failed", "cancelled"].includes(task.value?.status));

let pollTimer = null;

async function loadTask({ silent = false } = {}) {
  if (!silent) loading.value = true;
  // 2s 轮询（silent）只增量拉尾段事件（事件表 append-only + id ASC，见
  // api/tasks.js），避免事件越多轮询越重（Codex R1-P2）；首载/手动刷新仍
  // 全量重拉，兼作自愈路径。baseline 身份守卫：若轮询在途期间发生过全量
  // 重载（刷新/取消/放行后的 loadTask 已整体替换数组），本次轮询**整包
  // 作废**——task/events/loadError 都不动（Codex R2-P2：只弃 events 而仍写
  // task 会让 stale 快照倒灌，放行后可把状态钉回 waiting_review 且不再续
  // 轮询）；失败同理（Codex R3-P3：被淘汰快照的错误横幅不得盖住更新的
  // 状态）。finally 的 schedulePoll 依当前（更新的）状态决定是否续轮。
  const baseline = silent ? events.value : null;
  try {
    const offset = baseline ? baseline.length : 0;
    const [t, ev] = await Promise.all([getTask(taskId), listTaskEvents(taskId, { offset })]);
    if (silent && events.value !== baseline) {
      return;
    }
    task.value = t;
    syncArtifacts(t.output_file_ids); // fire-and-forget，增量同步产物内容
    if (!silent) {
      events.value = ev;
    } else if (ev.length) {
      events.value = baseline.concat(ev);
    }
    loadError.value = "";
    if (isTerminal.value) {
      await loadFeedback();
    }
  } catch (err) {
    if (silent && events.value !== baseline) {
      return;
    }
    loadError.value = err.detail || err.message;
  } finally {
    if (!silent) loading.value = false;
    schedulePoll();
  }
}

function schedulePoll() {
  clearPoll();
  if (task.value && !isTerminal.value && !isWaitingReview.value) {
    pollTimer = setTimeout(() => loadTask({ silent: true }), 2000);
  }
}
function clearPoll() {
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

async function loadFeedback() {
  try {
    feedbackList.value = await listTaskFeedback(taskId);
    feedbackError.value = "";
  } catch (err) {
    feedbackError.value = `反馈列表加载失败：${err.detail || err.message}`;
  }
}

async function handleCancel() {
  try {
    await ElMessageBox.confirm("确认取消该任务？", "取消任务", { type: "warning" });
  } catch {
    return;
  }
  try {
    await cancelTask(taskId);
    ElMessage.success("任务已取消");
    await loadTask();
  } catch (err) {
    ElMessage.error(err.detail || err.message);
  }
}

async function handleReview(action) {
  if (!reviewForm.reviewer.trim()) {
    ElMessage.error("请填写审核人");
    return;
  }
  const label = action === "approve" ? "批准放行" : "拒绝";
  try {
    await ElMessageBox.confirm(`确认${label}该任务？`, label, { type: "warning" });
  } catch {
    return;
  }
  reviewing.value = true;
  try {
    await reviewTask(taskId, { action, reviewer: reviewForm.reviewer.trim(), comment: reviewForm.comment || null });
    saveName(reviewForm.reviewer); // 记住名字，全站免重填
    ElMessage.success(`已${label}`);
    await loadTask();
  } catch (err) {
    ElMessage.error(err.detail || err.message);
  } finally {
    reviewing.value = false;
  }
}

async function handleSubmitFeedback() {
  if (!feedbackForm.createdBy.trim()) {
    ElMessage.error("请填写创建人");
    return;
  }
  if (!feedbackForm.category) {
    ElMessage.error("请选择分类");
    return;
  }
  submittingFeedback.value = true;
  try {
    await submitFeedback({
      taskId,
      rating: feedbackForm.rating,
      category: feedbackForm.category,
      message: feedbackForm.message || null,
      createdBy: feedbackForm.createdBy.trim(),
    });
    saveName(feedbackForm.createdBy); // 记住名字，全站免重填
    ElMessage.success("反馈已提交");
    feedbackForm.message = "";
    await loadFeedback();
  } catch (err) {
    ElMessage.error(err.detail || err.message);
  } finally {
    submittingFeedback.value = false;
  }
}

onMounted(() => loadTask());
onUnmounted(clearPoll);
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.page-header h2 {
  font-family: var(--serif);
  font-size: 25px;
  font-weight: 600;
  letter-spacing: 0.2px;
  margin: 0;
}
.task-descriptions {
  margin-bottom: 16px;
}
.section {
  margin-top: 24px;
}
.section h3 {
  margin: 0 0 12px;
  font-size: 15px;
}
.review-card {
  margin-top: 12px;
  max-width: 480px;
  background: var(--paper-rail);
}
.event-type {
  font-weight: 600;
  font-size: 13px;
}
.event-message {
  color: var(--ink-soft);
  font-size: 13px;
  margin: 2px 0 4px;
}
.payload-json {
  background: var(--paper-rail);
  padding: 8px;
  border-radius: 4px;
  font-size: 12px;
  overflow-x: auto;
}
/* 批准=人签，用信任锁 teal（--trust-signed）覆盖 Element Plus 按钮变量；绝不用绿。 */
.approve-btn {
  --el-button-bg-color: var(--trust-signed);
  --el-button-border-color: var(--trust-signed);
  --el-button-text-color: #fff;
  --el-button-hover-bg-color: #12707c;
  --el-button-hover-border-color: #12707c;
  --el-button-hover-text-color: #fff;
  --el-button-active-bg-color: #0f626d;
  --el-button-active-border-color: #0f626d;
}
.review-note {
  font-size: 12.5px;
  color: var(--ink-soft);
  line-height: 1.6;
  margin: 0 0 12px;
  padding-left: 80px;
}
.artifact-review-hint {
  margin-left: 10px;
  font-size: 12px;
  font-weight: 600;
  color: var(--trust-pending);
}
.artifact-card {
  border: 1px solid var(--hairline);
  border-radius: 12px;
  background: var(--card-bg, var(--paper-surface));
  box-shadow: var(--shadow-card);
  margin-bottom: 12px;
  overflow: hidden;
}
.artifact-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--hairline);
  background: var(--paper-rail);
}
.artifact-name {
  font-family: var(--mono, monospace);
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
}
.artifact-size {
  font-size: 12px;
  color: var(--ink-faint);
}
.artifact-download {
  margin-left: auto;
  font-size: 12.5px;
  color: var(--clay);
  text-decoration: none;
}
.artifact-download:hover {
  text-decoration: underline;
}
.artifact-body {
  padding: 16px;
}
.artifact-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--mono, monospace);
  font-size: 13px;
  line-height: 1.6;
  color: var(--ink);
}
.artifact-error {
  color: var(--trust-fail);
  font-size: 13px;
}
.muted {
  color: var(--ink-faint);
}
.feedback-form {
  max-width: 480px;
}
.feedback-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.feedback-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid var(--hairline);
  font-size: 13px;
}
.feedback-message {
  flex: 1;
  color: var(--ink-soft);
}
.feedback-meta {
  color: var(--ink-faint);
  font-size: 12px;
  white-space: nowrap;
}
</style>
