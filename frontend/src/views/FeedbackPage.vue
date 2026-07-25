<template>
  <div class="feedback-page">
    <div class="page-header">
      <BackLink label="任务台" fallback="/tasks" />
      <h2>提交反馈</h2>
    </div>

    <el-form label-width="80px" class="task-select-form fx-rise">
      <el-form-item label="任务" required>
        <el-select
          v-model="taskId"
          placeholder="请选择任务"
          filterable
          style="width: 100%"
          @change="handleTaskChange"
        >
          <el-option
            v-for="t in tasks"
            :key="t.id"
            :label="`${t.id.slice(0, 12)} · ${t.name || '(未命名)'} · ${statusLabel(t.status)}`"
            :value="t.id"
          />
        </el-select>
        <div class="select-hint">仅显示最近 100 条任务，更早任务从任务历史页进入详情提交反馈</div>
      </el-form-item>
    </el-form>

    <el-alert v-if="tasksLoadError" type="error" :title="tasksLoadError" show-icon :closable="false" />

    <!-- 反馈区块整体只在 taskId 首次从空变为有值时挂载一次（用户刚选定任务，
         内容确属「本次刚落地」）；切换到另一个任务时该 div 不重挂载（v-if 恒真、
         只是内部数据换了），fx-stagger 不重播——不对 .feedback-list 逐行加动效，
         避免任务切换时列表重刷被误当「新事件」重播入场（诚实地板④）。 -->
    <div v-if="taskId" class="fx-stagger">
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
          <el-input v-model="feedbackForm.message" type="textarea" :rows="3" placeholder="可选" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="handleSubmit">提交反馈</el-button>
        </el-form-item>
      </el-form>

      <el-alert v-if="feedbackError" type="warning" :title="feedbackError" show-icon :closable="false" />

      <h3 class="section-label">该任务已有反馈</h3>
      <EmptyState v-if="feedbackList.length === 0 && !feedbackError" description="暂无反馈" />
      <ul v-else class="feedback-list">
        <li v-for="f in feedbackList" :key="f.id">
          <el-tag size="small" :type="f.rating === 'good' ? 'info' : 'danger'">
            {{ f.rating === "good" ? "可用" : "不可用" }}
          </el-tag>
          <span class="feedback-category">{{ categoryLabel(f.category) }}</span>
          <span class="feedback-message">{{ f.message }}</span>
          <span class="feedback-meta">{{ f.created_by }} · {{ formatTime(f.created_at) }}</span>
        </li>
      </ul>
    </div>

    <EmptyState v-else variant="action" description="先在上方选择一个任务，再填写反馈" :image-size="96" />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from "vue";
import { useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import { listTasks } from "../api/tasks";
import { submitFeedback, listTaskFeedback, FEEDBACK_CATEGORIES } from "../api/feedback";
import { statusLabel, formatTime } from "../utils/format";
import EmptyState from "../components/EmptyState.vue";
import BackLink from "../components/BackLink.vue";

const route = useRoute();

const tasks = ref([]);
const tasksLoadError = ref("");
const taskId = ref(typeof route.query.task_id === "string" ? route.query.task_id : "");

const feedbackForm = reactive({ rating: "", category: "", message: "" });
const submitting = ref(false);
const feedbackList = ref([]);
const feedbackError = ref("");
let feedbackEpoch = 0;

const CATEGORY_LABEL_MAP = Object.fromEntries(FEEDBACK_CATEGORIES.map((c) => [c.value, c.label]));
const categoryLabel = (c) => CATEGORY_LABEL_MAP[c] ?? c;

async function loadTasks() {
  try {
    tasks.value = await listTasks();
    tasksLoadError.value = "";
  } catch (err) {
    tasksLoadError.value = err.detail || err.message;
  }
}

async function loadFeedback(requestedTaskId = taskId.value) {
  const epoch = ++feedbackEpoch;
  if (!requestedTaskId) {
    feedbackList.value = [];
    feedbackError.value = "";
    return;
  }
  try {
    const list = await listTaskFeedback(requestedTaskId);
    if (epoch !== feedbackEpoch || taskId.value !== requestedTaskId) return;
    feedbackList.value = list;
    feedbackError.value = "";
  } catch (err) {
    if (epoch !== feedbackEpoch || taskId.value !== requestedTaskId) return;
    feedbackError.value = `反馈列表加载失败：${err.detail || err.message}`;
  }
}

function handleTaskChange() {
  feedbackForm.rating = "";
  feedbackForm.category = "";
  feedbackForm.message = "";
  feedbackList.value = [];
  feedbackError.value = "";
  loadFeedback(taskId.value);
}

async function handleSubmit() {
  if (!feedbackForm.rating) {
    ElMessage.error("请选择评价（可用/不可用）");
    return;
  }
  if (!feedbackForm.category) {
    ElMessage.error("请选择分类");
    return;
  }
  submitting.value = true;
  const submittedTaskId = taskId.value;
  try {
    await submitFeedback({
      taskId: submittedTaskId,
      rating: feedbackForm.rating,
      category: feedbackForm.category,
      message: feedbackForm.message || null,
    });
    ElMessage.info("反馈已提交");
    if (taskId.value === submittedTaskId) {
      feedbackForm.message = "";
      await loadFeedback(submittedTaskId);
    }
  } catch (err) {
    ElMessage.error(err.detail || err.message);
  } finally {
    submitting.value = false;
  }
}

onMounted(async () => {
  await loadTasks();
  if (taskId.value) {
    await loadFeedback(taskId.value);
  }
});
</script>

<style scoped>
.feedback-page {
  max-width: 640px;
}
.page-header { margin-bottom: 20px; }
.page-header h2 {
  font-family: var(--serif);
  font-size: var(--fs-title);
  font-weight: 600;
  letter-spacing: 0.2px;
  margin: 0;
}
.task-select-form {
  margin-bottom: 8px;
}
.select-hint {
  color: var(--ink-faint);
  font-size: 12px;
  line-height: 1.5;
  margin-top: 4px;
}
.feedback-form {
  margin-top: 16px;
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
