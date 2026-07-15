<template>
  <div class="feedback-page">
    <div class="page-header">
      <h2>提交反馈</h2>
    </div>

    <el-form label-width="80px" class="task-select-form fx-rise">
      <el-form-item label="任务" required>
        <!-- 首载骨架（A3 同款）：本页 loadTasks 仅 onMounted 调一次，无轮询/重刷，
             tasksLoading 天然只在首载为真。骨架根 aria-hidden，须留可读 status
             给读屏（Codex R2 P2，QuickSwitcher 同款）。 -->
        <div v-if="tasksLoading" role="status">
          <span class="skel-sr">任务列表加载中…</span>
          <SkeletonBlock height="32px" />
        </div>
        <template v-else>
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
        </template>
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
          <el-tag size="small" :type="f.rating === 'good' ? 'success' : 'danger'">
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
import SkeletonBlock from "../components/SkeletonBlock.vue";

const route = useRoute();

const tasks = ref([]);
const tasksLoadError = ref("");
const tasksLoading = ref(true);
const taskId = ref(typeof route.query.task_id === "string" ? route.query.task_id : "");

const feedbackForm = reactive({ rating: "good", category: "", message: "" });
const submitting = ref(false);
const feedbackList = ref([]);
const feedbackError = ref("");

const CATEGORY_LABEL_MAP = Object.fromEntries(FEEDBACK_CATEGORIES.map((c) => [c.value, c.label]));
const categoryLabel = (c) => CATEGORY_LABEL_MAP[c] ?? c;

async function loadTasks() {
  tasksLoading.value = true;
  try {
    tasks.value = await listTasks();
    tasksLoadError.value = "";
  } catch (err) {
    tasksLoadError.value = err.detail || err.message;
  } finally {
    tasksLoading.value = false;
  }
}

async function loadFeedback() {
  if (!taskId.value) return;
  try {
    feedbackList.value = await listTaskFeedback(taskId.value);
    feedbackError.value = "";
  } catch (err) {
    feedbackError.value = `反馈列表加载失败：${err.detail || err.message}`;
  }
}

function handleTaskChange() {
  feedbackList.value = [];
  loadFeedback();
}

async function handleSubmit() {
  if (!feedbackForm.category) {
    ElMessage.error("请选择分类");
    return;
  }
  submitting.value = true;
  try {
    await submitFeedback({
      taskId: taskId.value,
      rating: feedbackForm.rating,
      category: feedbackForm.category,
      message: feedbackForm.message || null,
    });
    ElMessage.success("反馈已提交");
    feedbackForm.message = "";
    await loadFeedback();
  } catch (err) {
    ElMessage.error(err.detail || err.message);
  } finally {
    submitting.value = false;
  }
}

onMounted(async () => {
  await loadTasks();
  if (taskId.value) {
    await loadFeedback();
  }
});
</script>

<style scoped>
.feedback-page {
  max-width: 640px;
}
.page-header { margin-bottom: var(--space-5); }
.page-header h2 {
  font-family: var(--serif);
  font-size: var(--fs-title);
  font-weight: 600;
  letter-spacing: 0.2px;
  margin: 0;
}
.task-select-form {
  margin-bottom: var(--space-2);
}
.select-hint {
  color: var(--ink-faint);
  font-size: 12px;
  line-height: 1.5;
  margin-top: var(--space-1);
}
.feedback-form {
  margin-top: var(--space-4);
}
.feedback-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.feedback-list li {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) 0;
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
/* 读屏专用（视觉裁剪，AT 可读）：repo 无全局 sr-only 的本地最小实现。 */
.skel-sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
