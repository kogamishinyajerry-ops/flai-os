<template>
  <!-- 状态中心（UI-PARADIGM.md Phase 1）：渐进披露第②③级。
       destroy-on-close：关闭即零 DOM——绝不与 TaskDetail 页的「批准放行」等
       既有 e2e 锚点产生选择器重影（红线继承§e2e）。 -->
  <el-drawer
    v-model="statusCenter.open"
    :size="drawerSize"
    :with-header="false"
    :close-on-press-escape="statusCenter.view === 'inbox'"
    destroy-on-close
    class="status-center-drawer"
    @open="onOpen"
    @closed="onClosed"
  >
    <div class="sc-shell" @keydown.esc="onEsc" tabindex="-1">
      <!-- 头部：inbox=标题；peek=←返回 + 任务名（渐进披露的返回轴） -->
      <div class="sc-head">
        <template v-if="statusCenter.view === 'peek'">
          <button class="sc-back" @click="backToInbox">←</button>
          <span class="sc-title sc-title-task">{{ peekTask?.name || statusCenter.taskId?.slice(0, 12) || "任务速览" }}</span>
        </template>
        <template v-else>
          <span class="sc-title">状态中心</span>
          <span class="sc-sub">状态来找你——这里汇总要你处理与正在发生的</span>
        </template>
        <button class="sc-close" aria-label="关闭" @click="closeCenter">✕</button>
      </div>

      <!-- ═══ 收件箱视图 ═══ -->
      <div v-if="statusCenter.view === 'inbox'" class="sc-body">
        <div v-if="inboxError" class="sc-error">{{ inboxError }}</div>

        <!-- 待你签发：amber=仅待人核；行动召唤最高优先（工程师一进来先看要我处理的） -->
        <div class="sc-group">
          <div class="sc-group-label waiting">✍ 待你签发 · {{ waitingTasks.length }}</div>
          <div v-if="waitingTasks.length" class="sc-list">
            <div v-for="t in waitingTasks" :key="t.id" class="sc-item" role="button" tabindex="0" @click="openTaskPeek(t.id)" @keydown.enter.prevent="openTaskPeek(t.id)" @keydown.space.prevent="openTaskPeek(t.id)">
              <span class="sc-lamp" :style="{ background: 'var(--trust-pending)' }"></span>
              <span class="sc-item-main">
                <span class="sc-item-name">{{ t.name || t.id.slice(0, 12) }}</span>
                <span class="sc-item-sub">{{ t.agent_id }} · {{ formatTime(t.created_at) }}</span>
              </span>
              <span class="sc-item-cta">审阅 →</span>
            </div>
          </div>
          <div v-else class="sc-zero">
            <InboxZero class="sc-zero-art" />
            <span>没有等你签发的任务</span>
          </div>
        </div>

        <!-- 进行中：clay 脉动=真实工作态 -->
        <div v-if="workingTasks.length" class="sc-group">
          <div class="sc-group-label working">运行中 · {{ workingTasks.length }}</div>
          <div class="sc-list">
            <div v-for="t in workingTasks" :key="t.id" class="sc-item" role="button" tabindex="0" @click="openTaskPeek(t.id)" @keydown.enter.prevent="openTaskPeek(t.id)" @keydown.space.prevent="openTaskPeek(t.id)">
              <span class="sc-lamp is-pulsing" :style="{ background: 'var(--clay)' }"></span>
              <span class="sc-item-main">
                <span class="sc-item-name">{{ t.name || t.id.slice(0, 12) }}</span>
                <span class="sc-item-sub">{{ t.agent_id }} · {{ statusLabel(t.status) }}</span>
              </span>
              <span class="sc-item-cta">速览 →</span>
            </div>
          </div>
        </div>

        <!-- 最近落定：completed 永远中性（信任色锁——绿仅真实实证），失败红仅真失败 -->
        <div v-if="recentDoneTasks.length" class="sc-group">
          <div class="sc-group-label">最近落定</div>
          <div class="sc-list">
            <div v-for="t in recentDoneTasks" :key="t.id" class="sc-item" role="button" tabindex="0" @click="openTaskPeek(t.id)" @keydown.enter.prevent="openTaskPeek(t.id)" @keydown.space.prevent="openTaskPeek(t.id)">
              <span class="sc-lamp" :style="{ background: taskLampColor(t.status) }"></span>
              <span class="sc-item-main">
                <span class="sc-item-name">{{ t.name || t.id.slice(0, 12) }}</span>
                <span class="sc-item-sub">{{ t.agent_id }} · {{ statusLabel(t.status) }} · {{ formatTime(t.finished_at || t.created_at) }}</span>
              </span>
            </div>
          </div>
        </div>

        <button type="button" class="sc-viewall" @click="openAllTasks">查看全部任务 →</button>
        <div class="sc-foot-note">计数与清单来自最近任务窗口（100 条）真实轮询——窗口外不虚报。</div>
      </div>

      <!-- ═══ 任务速览视图 ═══ -->
      <div v-else class="sc-body" v-loading="peekLoading">
        <div v-if="peekError" class="sc-error">{{ peekError }}</div>

        <template v-if="peekTask">
          <!-- 状态带：工作态流光（真实态绑定）+ 状态 tag -->
          <div class="peek-status">
            <div v-if="isPeekWorking" class="work-flow-strip-peek" aria-hidden="true"></div>
            <span v-if="isPeekWorking" class="work-pulse-dot"></span>
            <el-tag :type="statusTagType(peekTask.status)">{{ statusLabel(peekTask.status) }}</el-tag>
            <span class="peek-agent">{{ peekTask.agent_id }} · {{ peekTask.agent_version || "—" }}</span>
            <button class="peek-fullpage" @click="goFullPage">打开完整页 ↗</button>
          </div>

          <!-- 终态盖章：落定任务先给一行官宣（Codex「─ Worked for Xs ─」哲学） -->
          <CompletionSeal :task="peekTask" class="peek-block" />

          <div v-if="acceptedSamples.length || sampleFixResults.length" class="peek-block">
            <div v-if="acceptedSamples.length" class="sc-fix-row">
              <span>{{ acceptedSamples.length }} 条样本已认可，可固化为评测用例</span>
              <el-button
                size="small"
                class="sc-fix-sample-btn"
                :loading="sampleFixing"
                @click="fixAcceptedSamples"
              >固化</el-button>
            </div>
            <div v-if="sampleFixResults.length" class="sc-fix-result">
              <span v-for="item in sampleFixResults" :key="item.sampleId">{{ item.text }}</span>
            </div>
          </div>

          <el-alert v-if="peekTask.error_message" type="error" :title="peekTask.error_message" show-icon :closable="false" class="peek-block" />

          <!-- 产物先于动作（信任核心 P0-2：先看要签的东西，再决定放行）。
               只要任务声明了产物就必渲染此区——加载中/失败都如实可见，
               绝不出现「有产物却什么都不显示」的静默状态。 -->
          <div v-if="peekFileIds.length" class="peek-block">
            <div class="peek-label">产物<span v-if="isPeekWaiting" class="peek-review-hint">放行前请先审阅</span></div>
            <div v-if="artifactsLoading" class="peek-artifact-muted">产物预览加载中……</div>
            <template v-else>
              <div v-for="a in peekArtifacts" :key="a.fileId" class="peek-artifact">
                <!-- Artifact 容器头（Claude 哲学）：名 + 类型徽 + 尺寸 + 动作——产物是一等公民 -->
                <div class="peek-artifact-head">
                  <span class="peek-artifact-name">{{ a.filename }}</span>
                  <span v-if="a.ext" class="peek-artifact-ext">.{{ a.ext }}</span>
                  <span v-if="a.size" class="peek-artifact-size">{{ formatFileSize(a.size) }}</span>
                  <a :href="downloadUrl(a.fileId)" download class="peek-artifact-dl">下载</a>
                </div>
                <div v-if="a.error" class="peek-artifact-err">产物加载失败：{{ a.error }}</div>
                <MarkdownLite v-else-if="a.isText && (a.ext === 'md' || a.ext === 'markdown')" :text="a.text" class="peek-artifact-body" />
                <pre v-else-if="a.isText" class="peek-artifact-body peek-pre">{{ a.text }}</pre>
                <div v-else class="peek-artifact-muted">二进制文件，请下载后查看。</div>
              </div>
              <!-- 截断必披露：签发背书的是全部产物，没看全就要说清楚 -->
              <div v-if="peekFileIds.length > peekArtifacts.length" class="peek-artifact-more">
                仅预览前 {{ peekArtifacts.length }} 件，另有 {{ peekFileIds.length - peekArtifacts.length }} 件产物——请打开完整页审阅后再签发。
              </div>
            </template>
          </div>

          <!-- 内联签发卡（祈使句④）：同一 review API，人具名，fail-closed 全承袭 -->
          <div v-if="isPeekWaiting" class="peek-block peek-review-card">
            <div class="peek-label">签发</div>
            <div class="peek-review-note">批准即代表你作为工程师背书该产物——签发权在你，平台不代签。</div>
            <div class="peek-review-signer">签发人：{{ signerName }}（登录身份，不可代填）</div>
            <el-input v-model="reviewComment" type="textarea" :rows="2" placeholder="意见（可选）" class="peek-review-input" />
            <div class="peek-review-actions">
              <!-- teal=人签唯一色；成功迸发=burstSigned 唯一许可点之一。
                   产物预览未完成首次尝试前禁批准（先看后签）；驳回是安全方向不设门。 -->
              <el-button ref="peekApproveEl" class="peek-approve" :loading="reviewing" :disabled="artifactsPending" @click="doReview('approve')">批准放行</el-button>
              <el-button type="danger" plain :loading="reviewing" @click="doReview('reject')">驳回</el-button>
            </div>
          </div>

          <!-- 折叠工作日志（复用 WorkLog：默认一行，展开=叙事+聚合 chips） -->
          <div class="peek-block">
            <WorkLog :task="peekTask" :events="peekEvents" />
          </div>

          <!-- 模型消耗一行（token 凑不出=「未知」绝不记 0） -->
          <div class="peek-block peek-model-line">
            <span v-if="peekModelStats.total === 0" class="peek-muted">无模型调用</span>
            <template v-else>
              <span>模型调用 {{ peekModelStats.total }} 次</span>
              <span v-if="peekModelStats.tokenKnown > 0"> · tokens 合计 {{ peekModelStats.tokenSum.toLocaleString() }}<template v-if="peekModelStats.tokenMissing > 0">（部分未回报，为下界）</template></span>
              <span v-else class="peek-muted"> · token 用量：未知</span>
            </template>
          </div>
        </template>
      </div>
    </div>
  </el-drawer>
</template>

<script setup>
// 状态中心（收件箱+速览双视图）。轮询纪律：仅打开期间 3s 链式（上轮落地才排
// 下轮，hidden 跳过仍续轮）；速览事件走 offset 增量 + epoch 守卫（taskId 切换
// 后迟到响应整包作废）。签发链路与 TaskDetail 完全同源（reviewTask API），
// 只是把「去哪签」变成了「签发来找你」。
import { ref, computed, watch, nextTick, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { statusCenter, openTaskPeek, backToInbox, closeCenter } from "../stores/statusCenter";
import { acquireChannel } from "../stores/liveFeed";
import { getTask, listTaskEvents, reviewTask, listModelCalls } from "../api/tasks";
import { request } from "../api/client";
import { downloadUrl, fetchOutputFile } from "../api/files";
import { statusLabel, statusTagType, taskLampColor, formatTime, formatFileSize, TASK_WORK_STATES } from "../utils/format";
import { displayName } from "../stores/session";
import { markTaskSeen } from "../utils/lastSeen";
import { burstSigned } from "../effects/burst";
import WorkLog from "./WorkLog.vue";
import MarkdownLite from "./MarkdownLite.vue";
import InboxZero from "./artwork/InboxZero.vue";
import CompletionSeal from "./CompletionSeal.vue";

const router = useRouter();

// 「查看全部任务 →」：状态中心是任务总览的家（来找你）；要看更全的三栏视图 /
// 历史全量时深链到 /tasks（范式 Phase 3：任务台降级为深链，不占主导航）。
function openAllTasks() {
  router.push("/tasks");
  closeCenter();
}
const drawerSize = window.innerWidth < 640 ? "100%" : "540px";

// ── 收件箱数据（并轨 liveFeed 'tasks' channel：抽屉开 acquire、关 release——
// 「关闭零后台消耗」语义原样保留：channel 无其他订阅者时自停,有订阅者（如
// StatusDock）则由其继续养着,都正确。channel 内部 acquire 即触发一次立即
// refresh,故打开抽屉的即时性不倒退,无需本组件额外拉一次） ──
const inboxTasks = ref([]);
const inboxError = ref("");
const waitingTasks = computed(() => inboxTasks.value.filter((t) => t.status === "waiting_review"));
const workingTasks = computed(() => inboxTasks.value.filter((t) => TASK_WORK_STATES.has(t.status)));
const recentDoneTasks = computed(() =>
  inboxTasks.value.filter((t) => ["completed", "failed", "cancelled"].includes(t.status)).slice(0, 5)
);

let tasksHandle = null;
let tasksStops = [];
function acquireInboxFeed() {
  if (tasksHandle) return; // 已持有,幂等（onOpen 可能与其它触发路径重入）
  tasksHandle = acquireChannel("tasks");
  tasksStops = [
    watch(tasksHandle.state.tasks, (v) => { inboxTasks.value = v; }, { immediate: true }),
    // channel 的 error 语义与旧 refreshInbox 一致：仅首载失败才置位,已 loaded
    // 后的失败保旧值下 tick 自愈（liveFeed.js refresh()）。
    watch(tasksHandle.state.error, (v) => { inboxError.value = v; }, { immediate: true }),
  ];
}
function releaseInboxFeed() {
  tasksStops.forEach((s) => s());
  tasksStops = [];
  if (tasksHandle) {
    tasksHandle.release();
    tasksHandle = null;
  }
}

// 收件箱计数即时回落（原 refreshInbox() 二次拉,现改为复用 doReview 里已经
// 拉到的 peek 真值原地替换——不为这一下单独发网络请求）。
function patchInboxTask(task) {
  if (!task) return;
  const idx = inboxTasks.value.findIndex((t) => t.id === task.id);
  if (idx === -1) return;
  const next = inboxTasks.value.slice();
  next[idx] = { ...next[idx], ...task };
  inboxTasks.value = next;
}

// ── 速览数据 ──
const peekTask = ref(null);
const peekEvents = ref([]);
const peekArtifacts = ref([]);
const peekModelCalls = ref([]);
const peekLoading = ref(false);
const peekError = ref("");
let peekEpoch = 0; // taskId 切换守卫：迟到响应整包作废

const isPeekWorking = computed(() => peekTask.value && TASK_WORK_STATES.has(peekTask.value.status));
const isPeekWaiting = computed(() => peekTask.value?.status === "waiting_review");
const peekFileIds = computed(() => peekTask.value?.output_file_ids || []);
// 有产物声明但首次预览尝试还没完成 → 批准放行禁用（先看后签）
const artifactsPending = computed(() => peekFileIds.value.length > 0 && artifactsLoading.value);

const peekModelStats = computed(() => {
  let tokenSum = 0;
  let tokenKnown = 0;
  for (const c of peekModelCalls.value) {
    const u = c.token_usage;
    let t = null;
    if (u && typeof u === "object") {
      if (typeof u.total_tokens === "number") t = u.total_tokens;
      else if (typeof u.prompt_tokens === "number" && typeof u.completion_tokens === "number") t = u.prompt_tokens + u.completion_tokens;
    }
    if (t != null) {
      tokenSum += t;
      tokenKnown++;
    }
  }
  return {
    total: peekModelCalls.value.length,
    tokenSum,
    tokenKnown,
    tokenMissing: peekModelCalls.value.length - tokenKnown,
  };
});

// 产物加载持有独立指纹世代（taskId+file_ids），不挂靠轮询 epoch——轮询每 3s
// 换代，加载 >3s 的产物会被永久丢弃且 file_ids 未变不再重试（Codex 审出的
// 竞态）。指纹只在「任务或产物集真的变了」时换，慢加载不再被误杀。
const artifactsLoading = ref(false);
let artifactsFingerprint = null;

async function syncPeekArtifacts(taskId, ids) {
  const fp = `${taskId}::${(ids || []).join(",")}`;
  if (fp === artifactsFingerprint) return; // 同一指纹已加载/加载中，不重复拉
  artifactsFingerprint = fp;
  const targets = (ids || []).slice(0, 3); // 速览最多预览 3 件，完整页看全部
  if (!targets.length) {
    peekArtifacts.value = [];
    artifactsLoading.value = false;
    return;
  }
  artifactsLoading.value = true;
  const out = [];
  for (const fid of targets) {
    try {
      out.push(await fetchOutputFile(fid));
    } catch (err) {
      out.push({ fileId: fid, filename: fid.slice(0, 8), error: err.message, isText: false });
    }
  }
  if (fp !== artifactsFingerprint) return; // 期间换了任务/产物集，本次结果作废
  peekArtifacts.value = out;
  artifactsLoading.value = false;
}

async function loadPeek(taskId, { initial = false } = {}) {
  const epoch = ++peekEpoch;
  if (initial) {
    peekLoading.value = true;
    peekTask.value = null;
    peekEvents.value = [];
    peekArtifacts.value = [];
    peekModelCalls.value = [];
    peekError.value = "";
    artifactsFingerprint = null; // 重进同任务允许重试上次失败的产物预览
    artifactsLoading.value = false;
  }
  try {
    const offset = initial ? 0 : peekEvents.value.length;
    const [t, ev, calls] = await Promise.all([
      getTask(taskId),
      listTaskEvents(taskId, { offset }),
      listModelCalls(taskId).catch(() => peekModelCalls.value),
    ]);
    if (epoch !== peekEpoch) return;
    peekTask.value = t;
    markTaskSeen(taskId); // 速览开着=正在看：轮询期间翻终态不得回头亮未读
    peekEvents.value = initial ? ev : peekEvents.value.concat(ev);
    peekModelCalls.value = calls;
    peekError.value = "";
    syncPeekArtifacts(taskId, t.output_file_ids); // 指纹自去重，产物集没变不重拉
  } catch (err) {
    if (epoch !== peekEpoch) return;
    if (initial) peekError.value = err.detail || err.message || "加载失败";
  } finally {
    if (initial && epoch === peekEpoch) peekLoading.value = false;
  }
}

// ── 签发（宪法路径：与 TaskDetail 同一 API，人具名 fail-closed） ──
// 本组件挂根级不随身份门重挂：setup 时可能门还没过（快照为空）——每次
// 打开抽屉懒补一次（onOpen），保证「一次具名全站免问」（Codex 审 P2）。
const signerName = computed(() => displayName());
const reviewComment = ref("");
const reviewing = ref(false);
const peekApproveEl = ref(null);
const acceptedSamples = ref([]);
const sampleFixResults = ref([]);
const sampleFixing = ref(false);
let sampleFixEpoch = 0;

function resetSampleFixState() {
  sampleFixEpoch++;
  acceptedSamples.value = [];
  sampleFixResults.value = [];
  sampleFixing.value = false;
}

async function loadAcceptedSamples(taskId) {
  const epoch = ++sampleFixEpoch;
  try {
    const samples = await request(`/api/tasks/${taskId}/samples`);
    if (epoch !== sampleFixEpoch || !statusCenter.open || statusCenter.taskId !== taskId) return;
    acceptedSamples.value = samples.filter((sample) => sample.accepted_by_engineer === true);
    sampleFixResults.value = [];
  } catch {
    if (epoch !== sampleFixEpoch || statusCenter.taskId !== taskId) return;
    acceptedSamples.value = [];
    sampleFixResults.value = [];
  }
}

function sampleFixErrorText(err) {
  if (err.status === 409) return "已固化";
  if (err.status === 422) return err.detail || err.message || "前置条件未满足";
  return err.detail || err.message || "固化失败";
}

async function fixAcceptedSamples() {
  const taskId = statusCenter.taskId;
  const samples = acceptedSamples.value.slice();
  if (!taskId || !samples.length || sampleFixing.value) return;
  const epoch = sampleFixEpoch;
  sampleFixing.value = true;
  try {
    const results = await Promise.all(samples.map(async (sample) => {
      try {
        const result = await request(`/api/agents/${sample.agent_id}/eval-cases`, {
          method: "POST",
          json: { sample_id: sample.id }, // 固化人=登录会话身份（ADR-0019 D5）
        });
        return { sampleId: sample.id, text: result.case_file };
      } catch (err) {
        return { sampleId: sample.id, text: sampleFixErrorText(err) };
      }
    }));
    if (epoch === sampleFixEpoch && statusCenter.open && statusCenter.taskId === taskId) {
      sampleFixResults.value = results;
    }
  } finally {
    if (epoch === sampleFixEpoch) sampleFixing.value = false;
  }
}

async function doReview(action) {
  const taskId = statusCenter.taskId; // 调用前捕获：await 期间任务可能被切换
  if (!taskId) return;
  const label = action === "approve" ? "批准放行" : "拒绝";
  try {
    // 与 TaskDetail 同款二次确认：内联签发不降低宪法路径的操作摩擦
    await ElMessageBox.confirm(`确认${label}该任务？`, "签发确认", {
      confirmButtonText: `确认${label}`,
      cancelButtonText: "再看看",
      type: "warning",
    });
  } catch {
    return; // 用户取消
  }
  reviewing.value = true;
  try {
    await reviewTask(taskId, {
      action,
      comment: reviewComment.value || null,
    });
    markTaskSeen(taskId); // 亲手签发=已看过：其后完成不得对签发者亮未读
    reviewComment.value = ""; // 签发落定即清，绝不残留到下一个任务
    ElMessage.success(action === "approve" ? "已批准放行" : "已驳回");
    if (action === "approve") loadAcceptedSamples(taskId); // 静默旁路：失败不影响签发主流程
    // 续体绑定：await 期间抽屉可能已关/任务已切——只有还在看同一任务时才迸发+刷新
    if (statusCenter.open && statusCenter.taskId === taskId) {
      if (action === "approve") {
        burstSigned(peekApproveEl.value?.ref); // teal 迸发：人签成功唯一许可点
      }
      await loadPeek(taskId, { initial: true });
      patchInboxTask(peekTask.value); // 收件箱计数即时回落：复用刚拉到的 peek 真值,不再单独拉 inbox
    }
  } catch (err) {
    ElMessage.error(err.detail || err.message || "签发失败");
  } finally {
    reviewing.value = false;
  }
}

function goFullPage() {
  const id = statusCenter.taskId;
  // 先同步切回 inbox 让 peek 子树立即响应式卸载——不等 el-drawer 的 0.3s 关闭
  // 过渡，堵死「批准放行」与 TaskDetail 同名按钮的瞬时选择器重影窗口（红线§e2e）
  backToInbox();
  closeCenter();
  if (id) router.push(`/tasks/${id}`);
}

function onEsc(e) {
  // 渐进披露的层层退出：peek 态拦下事件回收件箱；inbox 态放行冒泡到 document，
  // 交给 el-drawer 的 close-on-press-escape 完成整体关闭（无条件 .stop 会把
  // inbox 态的 Esc 也吞掉，drawer 永远收不到——双镜头 P1）。
  if (statusCenter.view === "peek") {
    e.stopPropagation();
    backToInbox();
  }
}

// ── 打开期间 3s 链式轮询（关闭即停，零后台消耗）——inbox 分支已并轨
// liveFeed 'tasks' channel（5s 自链）,此处只剩 peek 用途,原样保留 ──
let pollTimer = null;
let disposed = false; // 卸载后 finally 不再续排（in-flight 轮询可越过 clearPoll）
function schedulePoll() {
  clearPoll();
  pollTimer = setTimeout(async () => {
    try {
      if (!document.hidden && statusCenter.open && statusCenter.view === "peek" && statusCenter.taskId) {
        await loadPeek(statusCenter.taskId);
      }
    } finally {
      if (!disposed && statusCenter.open) schedulePoll();
    }
  }, 3000);
}
function clearPoll() {
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

function onOpen() {
  acquireInboxFeed();
  ensurePeekLoaded(); // 幂等：watch 已载过同一任务则不重载
  schedulePoll();
  nextTick(() => document.querySelector(".sc-shell")?.focus());
}
function onClosed() {
  clearPoll();
  releaseInboxFeed(); // channel 无其它订阅者时自停,有则由其继续养着
  peekEpoch++; // 关闭后迟到响应全作废
  artifactsFingerprint = null;
  artifactsLoading.value = false;
  peekLoadedFor = null; // 下次打开重新初载
  reviewComment.value = ""; // 意见草稿不跨次会话残留（签发人姓名保留）
  resetSampleFixState();
}

// 初载去重：openTaskPeek 从关闭态打开时，watch（open/view/taskId 变更）与
// @open 会双触发——peekLoadedFor 保证同一任务只发一次 initial 加载。
let peekLoadedFor = null;
function ensurePeekLoaded() {
  const id = statusCenter.taskId;
  if (statusCenter.open && statusCenter.view === "peek" && id && peekLoadedFor !== id) {
    peekLoadedFor = id;
    resetSampleFixState();
    reviewComment.value = ""; // 切任务清草稿，绝不把上个任务的意见签到这个任务
    markTaskSeen(id); // 速览含产物+签发，等价「看过」，驱动任务台未读点
    loadPeek(id, { initial: true });
    loadAcceptedSamples(id); // 已批准任务重开也能看到固化入口（未认可样本被 ===true 过滤，静默无痕）
  }
}
watch(() => [statusCenter.open, statusCenter.view, statusCenter.taskId], ensurePeekLoaded);

// 焦点跟随视图：进出速览时被点击的条目/返回钮会随视图切换卸载，焦点跌落到
// body——keydown 不再冒泡经过 .sc-shell，Esc 层层退出会整体失灵（实机探针
// 咬出）。每次视图翻转都把焦点收回 shell，键盘路径才连续。
watch(
  () => [statusCenter.open, statusCenter.view],
  ([open]) => {
    if (open) nextTick(() => document.querySelector(".sc-shell")?.focus());
  }
);

onUnmounted(() => {
  disposed = true;
  clearPoll();
  releaseInboxFeed(); // 安全网：正常路径已在 onClosed 释放,release() 本身幂等
  peekEpoch++;
  artifactsFingerprint = null;
  resetSampleFixState();
});
</script>

<style scoped>
.sc-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
  outline: none;
}
.sc-head {
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 20px 12px;
  border-bottom: 1px solid var(--hairline);
}
.sc-title {
  font-family: var(--serif);
  font-size: 17px;
  font-weight: 700;
  color: var(--ink);
}
.sc-title-task {
  font-family: inherit;
  font-size: 14.5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sc-sub {
  font-size: 11.5px;
  color: var(--ink-faint);
  flex: 1 1 auto;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sc-back,
.sc-close {
  flex: none;
  border: 1px solid var(--hairline);
  background: var(--paper-rail);
  border-radius: 8px;
  width: 28px;
  height: 28px;
  cursor: pointer;
  color: var(--ink-soft);
  font-size: 13px;
  transition: color var(--motion-fast) var(--ease-out-soft), border-color var(--motion-fast) var(--ease-out-soft);
}
.sc-back:hover,
.sc-close:hover {
  color: var(--clay);
  border-color: var(--clay-softer);
}
.sc-close {
  margin-left: auto;
}
.sc-body {
  flex: 1 1 auto;
  overflow-y: auto;
  padding: 16px 20px 24px;
}
.sc-error {
  color: var(--trust-fail);
  font-size: 12.5px;
  margin-bottom: 12px;
}
.sc-group {
  margin-bottom: 22px;
}
.sc-group-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.6px;
  color: var(--ink-faint);
  margin-bottom: 8px;
}
.sc-group-label.waiting {
  color: var(--trust-pending);
}
.sc-group-label.working {
  color: var(--clay);
}
.sc-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.sc-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border: 1px solid var(--hairline-soft);
  border-radius: 10px;
  background: var(--paper-surface);
  cursor: pointer;
  transition: border-color var(--motion-fast) var(--ease-out-soft), transform var(--motion-fast) var(--ease-out-soft), box-shadow var(--motion-fast) var(--ease-out-soft);
}
.sc-item:hover {
  border-color: var(--clay-softer);
  transform: translateY(-1px);
  box-shadow: var(--shadow-card);
}
.sc-lamp {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.sc-lamp.is-pulsing {
  animation: flai-work-pulse var(--pulse-duration) ease-in-out infinite;
}
.sc-item-main {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.sc-item-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sc-item-sub {
  font-size: 11.5px;
  color: var(--ink-faint);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sc-item-cta {
  flex: none;
  font-size: 12px;
  font-weight: 600;
  color: var(--clay);
}
.sc-zero {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 18px 0 8px;
  color: var(--ink-faint);
  font-size: 12.5px;
}
.sc-zero-art {
  width: 120px;
}
.sc-viewall {
  display: inline-flex;
  align-items: center;
  align-self: flex-start;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--clay);
  background: transparent;
  border: 1px solid var(--border-clay-soft, var(--hairline));
  border-radius: 9px;
  padding: 7px 13px;
  cursor: pointer;
  transition: background 0.16s var(--ease-lift), color 0.16s var(--ease-lift);
}
.sc-viewall:hover { background: var(--clay-soft); }
.sc-foot-note {
  font-size: 11px;
  color: var(--ink-faint);
  border-top: 1px dashed var(--hairline);
  padding-top: 10px;
}

/* ── 速览 ── */
.peek-status {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 0 12px;
}
.work-flow-strip-peek {
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
.work-flow-strip-peek::after {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  width: 40%;
  background: linear-gradient(90deg, transparent, var(--clay), transparent);
  animation: sc-flow-sweep 2.4s linear infinite;
}
@keyframes sc-flow-sweep {
  from { transform: translateX(-150%); }
  to { transform: translateX(350%); }
}
.peek-agent {
  font-size: 12px;
  color: var(--ink-soft);
  flex: 1 1 auto;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.peek-fullpage {
  flex: none;
  border: none;
  background: none;
  color: var(--clay);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 6px;
}
.peek-fullpage:hover {
  background: rgba(var(--clay-rgb), 0.08);
}
.peek-block {
  margin-bottom: 16px;
}
.sc-fix-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--hairline);
  border-radius: 10px;
  background: var(--paper-rail);
  color: var(--ink-soft);
  font-size: 12.5px;
}
.sc-fix-sample-btn {
  flex: none;
}
.sc-fix-result {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 8px 12px 0;
  color: var(--ink-mid);
  font-family: var(--mono, "SF Mono", ui-monospace, monospace);
  font-size: 11.5px;
  word-break: break-word;
}
.peek-label {
  font-size: 12px;
  font-weight: 700;
  color: var(--ink-soft);
  margin-bottom: 8px;
}
.peek-review-hint {
  margin-left: 8px;
  font-weight: 500;
  font-size: 11px;
  color: var(--trust-pending);
}
.peek-artifact {
  border: 1px solid var(--hairline);
  border-radius: 10px;
  overflow: hidden;
  margin-bottom: 10px;
  background: var(--card-bg);
}
.peek-artifact-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--paper-rail);
  border-bottom: 1px solid var(--hairline-soft);
}
.peek-artifact-name {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.peek-artifact-ext {
  flex: none;
  font-family: var(--mono, "SF Mono", ui-monospace, monospace);
  font-size: 10.5px;
  font-weight: 600;
  color: var(--ink-faint);
  border: 1px solid var(--hairline);
  border-radius: 5px;
  padding: 0 5px;
}
.peek-artifact-size {
  flex: none;
  font-size: 11px;
  color: var(--ink-faint);
}
.peek-artifact-dl {
  flex: none;
  font-size: 12px;
  color: var(--clay);
  text-decoration: none;
}
.peek-artifact-body {
  padding: 10px 12px;
  max-height: 260px;
  overflow-y: auto;
  font-size: 12.5px;
}
.peek-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
}
.peek-artifact-err {
  padding: 10px 12px;
  color: var(--trust-fail);
  font-size: 12px;
}
.peek-artifact-more {
  font-size: 11.5px;
  color: var(--trust-pending);
  padding: 2px 2px 0;
}
.peek-artifact-muted,
.peek-muted {
  color: var(--ink-faint);
  font-size: 12px;
  padding: 8px 12px;
}
.peek-muted {
  padding: 0;
}
.peek-review-card {
  border: 1px solid rgba(var(--trust-signed-rgb), 0.25);
  border-radius: 12px;
  padding: 14px;
  /* .03 太淡，暗色下几乎消失；提到 .06 保住「签发卡特殊感」 */
  background: rgba(var(--trust-signed-rgb), 0.06);
}
.peek-review-signer {
  margin-bottom: 8px;
  color: var(--ink-soft);
  font-size: 12px;
}

.peek-review-note {
  font-size: 12px;
  color: var(--ink-soft);
  margin-bottom: 10px;
  line-height: 1.6;
}
.peek-review-input {
  margin-bottom: 8px;
}
.peek-review-actions {
  display: flex;
  gap: 10px;
  margin-top: 4px;
}
/* teal=人签唯一合法通道色（信任色锁） */
.peek-approve {
  background: var(--trust-signed);
  border-color: var(--trust-signed);
  color: #fff;
}
.peek-approve:hover,
.peek-approve:focus {
  background: var(--trust-signed-deep);
  border-color: var(--trust-signed-deep);
  color: #fff;
}
.peek-model-line {
  font-size: 12px;
  color: var(--ink-soft);
  border-top: 1px dashed var(--hairline);
  padding-top: 10px;
}
@media (prefers-reduced-motion: reduce) {
  .sc-lamp.is-pulsing {
    animation: none;
  }
  .work-flow-strip-peek::after {
    animation: none;
    display: none;
  }
  .sc-item,
  .sc-back,
  .sc-close {
    transition: none;
  }
  .sc-item:hover {
    transform: none;
  }
}
</style>
