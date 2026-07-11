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
        <!-- 工作态流光带（P3，动效系统 v1）：v-if 绑真实 work-state，状态回落随之
             立即消失——诚实地板：流光=真的在跑。装饰性，不承载信息，故 aria-hidden。 -->
        <div v-if="isTaskWorking" class="work-flow-strip" aria-hidden="true"></div>
        <h2>任务详情</h2>
        <span v-if="isTaskWorking" class="work-pulse-dot"></span>
        <el-tag :type="statusTagType(task.status)">{{ statusLabel(task.status) }}</el-tag>
        <!-- 待你签发常驻徽章：与 el-tag 共存不替换（e2e 可能断言 el-tag 文案），
             复用 App.vue 全局 .pill-amber（工作台会话页同款用法）。 -->
        <span v-if="isWaitingReview" class="pill-amber">待你签发</span>
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

      <!-- 终态盖章（Codex CLI「─ Worked for Xs ─」落定仪式）：位置=标题/返回行之下、
           任务描述表之上——终态任务进页第一眼看到的官宣；组件自身对非终态渲染 null，
           零占位，不产生 a[href]/新文案与既有 e2e 断言冲突。 -->
      <CompletionSeal :task="task" />

      <!-- 首屏只留一行轻量上下文；完整元数据（ID/版本/时间）折叠为次要，让产物与决策优先。 -->
      <div class="task-context">
        <span>Agent <b>{{ task.agent_id }}</b></span>
        <span class="ctx-dot">·</span>
        <span>创建人 {{ task.created_by }}</span>
        <span class="ctx-dot">·</span>
        <span>{{ formatTime(task.created_at) }}</span>
      </div>

      <div class="task-meta-card">
        <el-collapse class="task-meta-collapse">
          <el-collapse-item title="任务信息（ID · 版本 · 时间）">
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
          </el-collapse-item>
        </el-collapse>
      </div>

      <el-alert
        v-if="task.error_message"
        type="error"
        :title="task.error_message"
        show-icon
        :closable="false"
        class="section"
      />

      <!-- 双面板：左栏=产物（签发前把要签的东西摆在眼前，放在「动作」之前——先看
           产物，再决定放行，信任核心 P0-2），右栏=来源（输入文件/参数/执行方，
           全部真实字段，无则显示"—"，诚实降级不编造）。左栏必须先于右栏出现在
           DOM 中——e2e 取 a[href*='/download'] 的 .first 仍须指向产物下载链接。 -->
      <div class="section">
        <div class="io-panel">
          <div class="section" v-if="artifacts.length">
            <h3>产物<span v-if="isWaitingReview" class="artifact-review-hint">放行前请先审阅</span></h3>
            <div v-for="a in artifacts" :key="a.fileId" class="artifact-card">
              <div class="artifact-head">
                <span class="artifact-name">{{ a.filename }}</span>
                <span v-if="a.ext" class="artifact-ext-badge">.{{ a.ext }}</span>
                <span v-if="!a.loading && a.size" class="artifact-size">
                  <span class="num-token">{{ formatSize(a.size) }}</span><template v-if="artifactLineCount(a) != null"> · <span class="num-token">{{ artifactLineCount(a) }}</span> 行</template>
                </span>
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

          <div class="source-panel">
            <h3>来源</h3>
            <div class="source-block">
              <div class="source-label">输入文件</div>
              <template v-if="task.input_file_ids && task.input_file_ids.length">
                <div v-for="(fid, idx) in task.input_file_ids" :key="fid" class="source-row">
                  <span>输入文件 {{ idx + 1 }}</span>
                  <a :href="downloadUrl(fid)" download class="source-download">下载</a>
                </div>
              </template>
              <div v-else class="muted">无输入文件</div>
            </div>
            <div class="source-block">
              <div class="source-label">输入参数</div>
              <template v-if="inputEntries.length">
                <div v-for="[k, v] in inputEntries" :key="k" class="source-row">
                  <span class="source-param-key">{{ k }}</span>
                  <span class="source-param-val">{{ v }}</span>
                </div>
              </template>
              <div v-else class="muted">无参数</div>
            </div>
            <div class="source-block">
              <div class="source-label">执行方</div>
              <div>{{ task.agent_id || "—" }} · {{ task.agent_version || "—" }}</div>
            </div>
            <!-- B1：模型调用消耗诚实披露——零调用（hello 等无 LLM Agent）显示中性
                 灰字；token 合计只对能折算出总数的行求和，凑不出来一律「未知」，
                 绝不记 0（假绿死罪）。块内无 /download 链接，不干扰 m2 e2e 的
                 a[href*='/download'] DOM 顺序取值。 -->
            <div class="source-block model-usage">
              <div class="source-label">模型调用</div>
              <div v-if="modelCallsError" class="muted">模型调用加载失败：{{ modelCallsError }}</div>
              <div v-else-if="modelCallStats.total === 0" class="muted">无模型调用</div>
              <template v-else>
                <div class="source-row model-usage-summary">
                  <span>
                    <span class="num-token">{{ modelCallStats.total }}</span> 次调用（成功 <span class="num-token">{{ modelCallStats.ok }}</span> · 失败
                    <span class="num-token" :class="modelCallStats.failed > 0 ? 'model-usage-fail-count' : ''">{{ modelCallStats.failed }}</span>）
                  </span>
                </div>
                <div class="source-row">
                  <span>模型：{{ modelCallStats.names.length ? modelCallStats.names.join("、") : "未知" }}</span>
                </div>
                <div class="source-row">
                  <span v-if="modelCallStats.tokenKnownCount > 0">tokens 合计 <span class="num-token">{{ modelCallStats.tokenSum.toLocaleString() }}</span></span>
                  <span v-else class="muted">token 用量：未知</span>
                </div>
                <div v-if="modelCallStats.tokenKnownCount > 0 && modelCallStats.tokenMissingCount > 0" class="model-usage-note">
                  部分调用上游未回报 token，合计为下界
                </div>
              </template>
            </div>
          </div>
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
              <!-- 批准=人签，用信任锁的 teal（--trust-signed），绝不用绿（绿仅表真实结果）。
                   ref 供放行成功后的 teal burst 定位元素（动效系统 v1 E2，唯一 teal 许可点）。 -->
              <el-button ref="approveBtnEl" class="approve-btn" :loading="reviewing" @click="handleReview('approve')">批准放行</el-button>
              <el-button type="danger" :loading="reviewing" @click="handleReview('reject')">拒绝</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </div>

      <div class="section">
        <h3>事件时间轴</h3>
        <WorkLog :events="events" :task="task" />
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

        <EmptyState v-if="feedbackList.length === 0" description="暂无反馈" :image-size="84" />
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
import { getTask, listTaskEvents, cancelTask, reviewTask, listModelCalls } from "../api/tasks";
import { downloadUrl, fetchOutputFile } from "../api/files";
import EmptyState from "../components/EmptyState.vue";
import { submitFeedback, listTaskFeedback, FEEDBACK_CATEGORIES } from "../api/feedback";
import { statusLabel, statusTagType, formatTime, formatFileSize, TASK_WORK_STATES } from "../utils/format";
import MarkdownLite from "../components/MarkdownLite.vue";
import WorkLog from "../components/WorkLog.vue";
import CompletionSeal from "../components/CompletionSeal.vue";
import { getSavedName, saveName } from "../utils/identity";
import { markTaskSeen } from "../utils/lastSeen";
import { burstSigned } from "../effects/burst";

const route = useRoute();
const taskId = route.params.taskId;

const task = ref(null);
const events = ref([]);
const loading = ref(true);
const loadError = ref("");

const reviewForm = reactive({ reviewer: getSavedName(), comment: "" });
const reviewing = ref(false);
// 批准按钮元素（动效系统 v1 E2）：放行成功后 burstSigned(el) 的定位来源；
// el-button 组件 ref 通过 .ref 暴露原生 DOM（element-plus expose 契约）。
const approveBtnEl = ref(null);

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

// 模型调用消耗披露（B1）：只读追溯端点，页面每次 loadTask（含 silent 轮询）都
// 整包重拉——数据量小、无 offset 语义，不存在 events 那种 stale-merge 问题。
const modelCalls = ref([]);
const modelCallsError = ref("");
// 请求序号（非响应式）：fire-and-forget 下手动刷新可与在途轮询重叠，只让「最新
// 一次发起」的结果落盘，迟到的旧响应（含旧错误）整包作废——与 loadTask 的
// baseline 守卫同一防 stale 倒灌纪律。
let modelCallsSeq = 0;

async function syncModelCalls() {
  const seq = ++modelCallsSeq;
  try {
    const calls = await listModelCalls(taskId);
    if (seq !== modelCallsSeq) return;
    modelCalls.value = calls;
    modelCallsError.value = "";
  } catch (err) {
    if (seq !== modelCallsSeq) return;
    modelCallsError.value = err.detail || err.message || "加载失败";
  }
}

// token_usage 是上游 chat/completions 原样透传的 usage 对象，形状不保证含
// total_tokens（后端测试用例里就只有 prompt_tokens+completion_tokens）——能
// 折算出总数才计入合计，折算不出来一律算「未知」，绝不当 0。
function modelCallTokenTotal(call) {
  const usage = call.token_usage;
  if (!usage || typeof usage !== "object") return null;
  if (typeof usage.total_tokens === "number") return usage.total_tokens;
  const { prompt_tokens: p, completion_tokens: c } = usage;
  if (typeof p === "number" && typeof c === "number") return p + c;
  return null;
}

const modelCallStats = computed(() => {
  const calls = modelCalls.value;
  const names = new Set();
  let ok = 0;
  let failed = 0;
  let tokenSum = 0;
  let tokenKnownCount = 0;
  for (const c of calls) {
    if (c.status === "success") ok++;
    else if (c.status === "failed") failed++;
    if (c.model_name) names.add(c.model_name);
    const t = modelCallTokenTotal(c);
    if (t != null) {
      tokenSum += t;
      tokenKnownCount++;
    }
  }
  return {
    total: calls.length,
    ok,
    failed,
    names: Array.from(names),
    tokenSum,
    tokenKnownCount,
    tokenMissingCount: calls.length - tokenKnownCount,
  };
});

// 尺寸格式化走 utils/format 的 formatFileSize SSOT（含 GB 档）——本地副本已删。
const formatSize = formatFileSize;

// 文本产物行数派生（纯前端展示，不影响下载/内容本身）：非文本或空文本一律
// null，不渲染「· N 行」，绝不显示假的 0 行。
function artifactLineCount(a) {
  return a.isText && a.text ? a.text.split("\n").length : null;
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
// 页头到席点：与 WorkLog 内部同一口径（TASK_WORK_STATES），紧邻状态 tag 左侧。
const isTaskWorking = computed(() => TASK_WORK_STATES.has(task.value?.status));

// 来源面板「输入参数」：task.inputs 的 key→值摘要（值 JSON.stringify 截 80 字符），
// 纯展示派生，不改任何签发/预填逻辑。
function summarizeInputValue(v) {
  let s;
  try {
    s = JSON.stringify(v);
  } catch {
    s = String(v);
  }
  if (s == null) return "—";
  return s.length > 80 ? `${s.slice(0, 80)}…` : s;
}
const inputEntries = computed(() => {
  const inputs = task.value?.inputs;
  if (!inputs || typeof inputs !== "object") return [];
  return Object.entries(inputs).map(([k, v]) => [k, summarizeInputValue(v)]);
});

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
    markTaskSeen(taskId); // 详情页开着=正在看：轮询期间状态翻终态不得回头亮未读
    syncArtifacts(t.output_file_ids); // fire-and-forget，增量同步产物内容
    syncModelCalls(); // fire-and-forget，全量重拉模型调用留痕（消耗诚实披露）
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

// disposed 守卫（2b 双镜头 P2）：任务台把「切任务」变成同页高频交互——
// :key 重建卸载旧实例时，若 loadTask 正 await 在途，finally 的 schedulePoll
// 会在死实例闭包上武装新 timer 且无人再清（onUnmounted 只触发一次）。
let disposed = false;
function schedulePoll() {
  clearPoll();
  if (!disposed && task.value && !isTerminal.value && !isWaitingReview.value) {
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
    markTaskSeen(taskId); // 亲手签发=已看过：其后完成不得对签发者亮未读
    saveName(reviewForm.reviewer); // 记住名字，全站免重填
    // 人签放行成功时刻（唯一 teal 许可点，动效系统硬约束）：仅 approve 分支触发；
    // 驳回/失败绝不放庆祝动效。元素取不到（ref 未挂载等）burstSigned 自兜 null。
    if (action === "approve") {
      burstSigned(approveBtnEl.value?.ref);
    }
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

onMounted(() => {
  markTaskSeen(taskId); // 打开详情即视为「已看过」，驱动任务台未读点
  loadTask();
});
onUnmounted(() => {
  disposed = true;
  clearPoll();
});
</script>

<style scoped>
.page-header {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
/* 工作态流光带（动效系统 v1 P3）：v-if 已绑真实 work-state，此处只管视觉——
   静态 clay-soft 底线常显作 reduced-motion 兜底，::after 是流动的 clay 高光扫过，
   transform-only、~2.4s linear infinite，绝不用 layout 属性。 */
.work-flow-strip {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  overflow: hidden;
  border-radius: 1px;
  background: var(--clay-soft);
  pointer-events: none;
}
.work-flow-strip::after {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  width: 40%;
  background: linear-gradient(90deg, transparent, var(--clay), transparent);
  animation: work-flow-sweep 2.4s linear infinite;
  will-change: transform;
}
@keyframes work-flow-sweep {
  from {
    transform: translateX(-150%);
  }
  to {
    transform: translateX(350%);
  }
}
@media (prefers-reduced-motion: reduce) {
  .work-flow-strip::after {
    animation: none;
    display: none;
  }
}
.page-header h2 {
  font-family: var(--serif);
  font-size: 25px;
  font-weight: 600;
  letter-spacing: 0.2px;
  margin: 0;
}
/* 状态 tag 切换过渡：与任务台 cl-lamp 动效语言统一（同一组 motion token）。 */
.page-header :deep(.el-tag) {
  transition: background-color var(--motion-med) var(--ease-out-soft);
}
.task-context {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--ink-soft);
  margin-bottom: 10px;
}
.task-context b {
  color: var(--ink);
  font-family: var(--mono, monospace);
  font-weight: 600;
}
.ctx-dot {
  color: var(--ink-faint);
}
/* 卡片化外包容器（el-collapse 本身不改，只加一层壳）：与 .artifact-card/
   .source-panel 同一套 hairline + 圆角 + paper-rail 卡片语言。 */
.task-meta-card {
  margin-bottom: 16px;
  border: 1px solid var(--hairline);
  border-radius: 10px;
  background: var(--paper-rail);
  overflow: hidden;
}
.task-meta-collapse {
  border-top: none;
}
.task-descriptions {
  margin-top: 4px;
}
.section {
  margin-top: 24px;
}
.section h3,
.source-panel h3 {
  margin: 0 0 12px;
  font-size: 15px;
  font-weight: 600;
  color: var(--ink);
}
.review-card {
  margin-top: 12px;
  max-width: 480px;
  background: var(--paper-rail);
}
/* 批准=人签，用信任锁 teal（--trust-signed）覆盖 Element Plus 按钮变量；绝不用绿。
   hover/active 深调统一走 --trust-signed-deep（App.vue color-mix 派生，暗色下自动
   变亮而非变暗），不再各自硬编码一份 teal——单一 SSOT，跨主题自动跟随。 */
.approve-btn {
  --el-button-bg-color: var(--trust-signed);
  --el-button-border-color: var(--trust-signed);
  --el-button-text-color: #fff;
  --el-button-hover-bg-color: var(--trust-signed-deep);
  --el-button-hover-border-color: var(--trust-signed-deep);
  --el-button-hover-text-color: #fff;
  --el-button-active-bg-color: var(--trust-signed-deep);
  --el-button-active-border-color: var(--trust-signed-deep);
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
.artifact-ext-badge {
  font-size: 11px;
  color: var(--ink-faint);
  background: var(--paper-canvas-b, var(--paper-rail));
  border: 1px solid var(--hairline);
  border-radius: 5px;
  padding: 1px 6px;
  font-family: var(--mono, monospace);
}
/* 双面板：左产物/右来源，宽屏两栏、窄屏单列自适应。 */
.io-panel {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}
@media (max-width: 760px) {
  .io-panel {
    grid-template-columns: 1fr;
  }
}
.source-panel {
  border: 1px solid var(--hairline);
  border-radius: 12px;
  background: var(--card-bg, var(--paper-surface));
  box-shadow: var(--shadow-card);
  padding: 16px;
}
.source-block {
  margin-bottom: 14px;
}
.source-block:last-child {
  margin-bottom: 0;
}
.source-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-soft);
  margin-bottom: 6px;
}
.source-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 13px;
  padding: 3px 0;
}
.source-download {
  margin-left: auto;
  color: var(--clay);
  font-size: 12.5px;
  text-decoration: none;
}
.source-download:hover {
  text-decoration: underline;
}
.source-param-key {
  font-family: var(--mono, monospace);
  font-weight: 600;
  color: var(--ink);
}
.source-param-val {
  color: var(--ink-soft);
  word-break: break-all;
}
/* B1：模型调用消耗披露——成功数中性色（信任色锁：completed/success 永远中性，
   绿仅表真实实证结果，不外推到「调用没报错」这种弱信号）；失败数>0 才标红。 */
.model-usage-summary {
  font-weight: 500;
}
.model-usage-fail-count {
  color: var(--trust-fail);
  font-weight: 600;
}
/* 证据数字等宽 token 化：调用次数/tokens 合计是可核验的事实证据，非行动召唤，
   故只换等宽字体（跨家族共性——Claude/Codex 行内证据同一处理），颜色/字号继承不变。 */
.num-token {
  font-family: var(--mono, "SF Mono", ui-monospace, monospace);
}
.model-usage-note {
  font-size: 11.5px;
  color: var(--ink-faint);
  margin-top: 2px;
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
