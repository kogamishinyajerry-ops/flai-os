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
            <!-- 人话称呼（批次四 Q1 残留收口）：选项主文本=taskDisplayName SSOT
                 （任务名→Agent 显示名→id 切片诚实回退），不再以裸 task_ id 切片
                 打头；id 切片退尾段作同名行消歧锚（与任务台左栏行 meta 同律），
                 回退态下主名已是 id 切片则尾段不重复。 -->
            <el-option
              v-for="t in tasks"
              :key="t.id"
              :label="taskOptionLabel(t)"
              :value="t.id"
            />
          </el-select>
          <div class="select-hint">仅显示最近 100 条任务，更早任务从任务历史页进入详情提交反馈</div>
        </template>
      </el-form-item>
    </el-form>

    <!-- 错误三问（批次五 C2）：本页 loadTasks 仅挂载一次、无轮询——「何为」=显式重试。 -->
    <el-alert v-if="tasksLoadError" type="error" :title="tasksLoadError" show-icon :closable="false">
      <el-button size="small" :disabled="tasksLoading" @click="loadTasks">重试</el-button>
    </el-alert>

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

      <el-alert v-if="feedbackError" type="warning" :title="feedbackError" show-icon :closable="false">
        <el-button size="small" @click="loadFeedback">重试</el-button>
      </el-alert>

      <h3 class="section-label">该任务已有反馈</h3>
      <!-- 纯数据空态=line 轻量态（W2 空态纪律）：本屏插画预算已给「先选任务」
           引导空态；「暂无反馈」一行安静文字即可。description 逐字不动（batch_d
           ⑦ 失败态互斥锚只咬文案，不咬形态）。 -->
      <EmptyState v-if="feedbackList.length === 0 && !feedbackError" variant="data" tier="line" description="暂无反馈" />
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
import { statusLabel, formatTime, taskDisplayName } from "../utils/format";
import { useAgentNames } from "../stores/agentNames";
import EmptyState from "../components/EmptyState.vue";
import SkeletonBlock from "../components/SkeletonBlock.vue";

const route = useRoute();

// Agent 人话名册（批次四 Q1）：任务选项缺名时回退注册表显示名，缺位再回退
// id 切片（taskDisplayName 内置，绝不编名字）。
const agentNames = useAgentNames();

// 选项标签：人话主名打头，id 切片退尾段消歧；SSOT 已回退 id 切片时尾段去重。
function taskOptionLabel(t) {
  const name = taskDisplayName(t, agentNames.map);
  const idSlice = t.id.slice(0, 12);
  return `${name} · ${statusLabel(t.status)}${name === idSlice ? "" : ` · ${idSlice}`}`;
}

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
/* h3 的 UA 默认 margin-top（1em）会叠在全局 .section-label 的 8px 底距之上，
   比 MePage 的 div.section-label 节奏多一块顶部空隙——归零对齐（只动 margin，
   字级/字重仍走全局 .section-label SSOT）。 */
.section-label {
  margin-top: 0;
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
/* 末行不再垂一条悬空 hairline（层级靠留白收尾，hairline 只做行间分隔）。 */
.feedback-list li:last-child {
  border-bottom: none;
}
.feedback-message {
  flex: 1;
  /* 375px 硬化：flex 项 min-width:auto 会以最长单词为最小宽，超长无断行
     字符串（如粘贴的 URL）此前会把行撑出视口——min-width:0 让位 + 断词兜底。 */
  min-width: 0;
  overflow-wrap: break-word;
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
