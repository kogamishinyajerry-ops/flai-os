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
          <span class="sc-title sc-title-task">{{ peekTask ? taskDisplayName(peekTask, agentNames.map) : statusCenter.taskId?.slice(0, 12) || "任务速览" }}</span>
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
          <!-- 零值不显示（批次四 Q2）：N=0 时组头不渲染「· 0」——0 不是信息。 -->
          <div class="sc-group-label waiting">✍ 待你签发<template v-if="waitingTasks.length"> · <span class="num-token">{{ waitingTasks.length }}</span></template></div>
          <div v-if="waitingTasks.length" class="sc-list">
            <div v-for="t in waitingTasks" :key="t.id" class="sc-item" role="button" tabindex="0" @click="openTaskPeek(t.id)" @keydown.enter.prevent="openTaskPeek(t.id)" @keydown.space.prevent="openTaskPeek(t.id)">
              <span class="sc-lamp" :style="{ background: 'var(--trust-pending)' }"></span>
              <span class="sc-item-main">
                <!-- 人话称呼（批次四 Q1）：缺名任务回退 Agent 显示名而非裸 id——
                     taskDisplayName 三级诚实降级 SSOT，名册缺位仍显 id 切片。 -->
                <span class="sc-item-name">{{ taskDisplayName(t, agentNames.map) }}</span>
                <!-- 行级紧凑时钟（批次三 G4）：全量 locale 串收敛为同日 HH:MM/跨日 MM-DD HH:MM。 -->
                <span class="sc-item-sub">{{ t.agent_id }} · {{ rowClock(t.created_at) }}</span>
              </span>
              <span class="sc-item-cta is-review">审阅 →</span>
            </div>
          </div>
          <div v-else class="sc-zero">
            <InboxZero class="sc-zero-art" />
            <span>没有等你签发的任务</span>
          </div>
        </div>

        <!-- 进行中：clay 脉动=真实工作态 -->
        <div v-if="workingTasks.length" class="sc-group">
          <div class="sc-group-label working">运行中 · <span class="num-token">{{ workingTasks.length }}</span></div>
          <div class="sc-list">
            <div v-for="t in workingTasks" :key="t.id" class="sc-item" role="button" tabindex="0" @click="openTaskPeek(t.id)" @keydown.enter.prevent="openTaskPeek(t.id)" @keydown.space.prevent="openTaskPeek(t.id)">
              <!-- Codex R0 P2：等待接力行灯=空心不脉动（clay 脉动=真在干活唯一
                   语义；阻塞 created 冒充活跃工作=灯语假绿）。 -->
              <span
                class="sc-lamp"
                :class="memberPhase(t) === 'waiting_upstream' ? 'is-hollow' : 'is-pulsing'"
                :style="memberPhase(t) === 'waiting_upstream' ? {} : { background: 'var(--clay)' }"
              ></span>
              <span class="sc-item-main">
                <span class="sc-item-name">{{ taskDisplayName(t, agentNames.map) }}</span>
                <!-- 活跳时长（批次三 G3，cd-bg-tasks-panel Running 卡「时长实时」）：
                     started_at 缺失（queued/validating 早期）=段不出现，不硬凑。 -->
                <span class="sc-item-sub">{{ t.agent_id }} · {{ statusLabel(t.status) }}<template v-if="memberPhase(t) === 'waiting_upstream'"> <span class="sc-relay-note">(等待接力)</span></template><template v-if="runElapsed(t)"> · 已 {{ runElapsed(t) }}</template></span>
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
                <span class="sc-item-name">{{ taskDisplayName(t, agentNames.map) }}</span>
                <span class="sc-item-sub">{{ t.agent_id }} · {{ statusLabel(t.status) }} · {{ rowClock(t.finished_at || t.created_at) }}</span>
              </span>
            </div>
          </div>
        </div>

        <button type="button" class="sc-viewall" @click="openAllTasks">查看全部任务 →</button>
        <!-- 诚实口径压缩（批次四 Q3；3-lens 诚实镜头 P2 补回「计数与清单」双重
             范围声明——组头数字与列表内容都被窗口限定，压缩不丢范围界定）。
             全句叙述形态只留任务台一处（m8 锚在彼侧）。 -->
        <div class="sc-foot-note">口径：计数与清单均来自最近 100 条任务窗口，窗口外不虚报。</div>
      </div>

      <!-- ═══ 任务速览视图 ═══ -->
      <div v-else class="sc-body" :class="{ 'sc-sensitive': peekTask?.data_classification === 'sensitive' }" v-loading="peekLoading">
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

          <!-- N9 敏感声明（ADR-0025）：形状+字重，零新色；框在 .sc-sensitive 整窗双线。 -->
          <div v-if="peekTask.data_classification === 'sensitive'" class="peek-sensitive-decl">
            <span aria-hidden="true">◆</span>
            <span>敏感数据任务——产物按部门数据口径流转，不外发。</span>
          </div>

          <TaskJourney
            :task="peekTask"
            :events="peekEvents"
            :model-calls="peekModelCalls"
            :model-calls-loaded="peekModelCallsLoaded"
            :model-calls-error="peekModelCallsError"
            compact
          />

          <!-- 终态盖章：落定任务先给一行官宣（Codex「─ Worked for Xs ─」哲学） -->
          <CompletionSeal :task="peekTask" class="peek-block" />

          <div v-if="acceptedSamples.length || sampleFixResults.length" class="peek-block">
            <div v-if="acceptedSamples.length" class="sc-fix-row">
              <span><span class="num-token">{{ acceptedSamples.length }}</span> 条样本已认可，可固化为评测用例</span>
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

          <!-- N4a 速览里的失败任务同样给下一步：与 TaskDetail 同源 util，
               预填需人工核对亲手提交，绝不自动重跑。 -->
          <div v-if="peekTask.status === 'failed'" class="peek-block peek-retry">
            <button type="button" class="peek-retry-btn" @click="retryFromPeek">复制为新任务</button>
            <span class="peek-retry-hint">带原输入进创建页，核对后重新提交。</span>
          </div>

          <!-- 产物先于动作（信任核心 P0-2：先看要签的东西，再决定放行）。
               只要任务声明了产物就必渲染此区——加载中/失败都如实可见，
               绝不出现「有产物却什么都不显示」的静默状态。 -->
          <div v-if="peekFileIds.length" class="peek-block">
            <div class="peek-label">产物<span v-if="isPeekWaiting" class="peek-review-hint">放行前请先审阅</span></div>
            <div v-if="artifactsLoading" class="peek-artifact-muted">产物预览加载中……</div>
            <template v-else>
              <div v-for="a in peekArtifacts" :key="a.fileId" class="peek-artifact">
                <!-- Artifact 容器头（Claude 哲学）：名 + 类型徽 + 尺寸 + 动作——产物是一等公民 -->
                <div class="peek-artifact-head" :class="{ 'is-collapsed': a.collapsed }">
                  <button
                    type="button"
                    class="peek-artifact-toggle"
                    :aria-expanded="!a.collapsed"
                    @click="togglePeekArtifact(a)"
                  >
                    <el-icon class="peek-artifact-chevron" aria-hidden="true">
                      <ArrowRight v-if="a.collapsed" />
                      <ArrowDown v-else />
                    </el-icon>
                    <span class="peek-artifact-name">{{ a.filename }}</span>
                    <!-- 类型标签（F6 同款，SSOT=utils/format artifactTypeLabel）：与 TaskDetail 产物卡同语法。 -->
                    <span v-if="a.ext" class="peek-artifact-ext">{{ artifactTypeLabel(a.ext) }}</span>
                    <span v-if="a.size" class="peek-artifact-size">{{ formatFileSize(a.size) }}</span>
                  </button>
                  <a :href="downloadUrl(a.fileId)" download class="peek-artifact-dl">下载</a>
                </div>
                <div v-show="!a.collapsed">
                  <div v-if="a.error" class="peek-artifact-err">产物加载失败：{{ a.error }}</div>
                  <MarkdownLite v-else-if="a.isText && (a.ext === 'md' || a.ext === 'markdown')" :text="a.text" class="peek-artifact-body" />
                  <pre v-else-if="a.isText" class="peek-artifact-body peek-pre">{{ a.text }}</pre>
                  <div v-else class="peek-artifact-muted">二进制文件，请下载后查看。</div>
                </div>
              </div>
              <!-- 截断必披露：签发背书的是全部产物，没看全就要说清楚 -->
              <div v-if="peekFileIds.length > peekArtifacts.length" class="peek-artifact-more">
                仅预览前 <span class="num-token">{{ peekArtifacts.length }}</span> 件，另有 <span class="num-token">{{ peekFileIds.length - peekArtifacts.length }}</span> 件产物——请打开完整页审阅后再签发。
              </div>
            </template>
          </div>

          <!-- 内联签发卡（祈使句④）：同一 review API，人具名，fail-closed 全承袭 -->
          <div v-if="isPeekWaiting" class="peek-block peek-review-card">
            <div class="peek-label">签发</div>
            <div class="peek-review-note">批准即代表你作为工程师背书该产物——签发权在你，平台不代签。</div>
            <div class="peek-review-signer">签发人：{{ signerName }}（登录身份，不可代填）</div>
            <!-- N8 授权链一行（与 TaskDetail 同口径）：字段全真，无自动放行=宪法事实。 -->
            <div class="peek-review-chain">授权链：{{ peekTask.created_by }} 于 {{ formatTime(peekTask.created_at) }} 创建本任务；除你此刻的批准外，平台没有任何自动放行路径。</div>
            <!-- 填空默认收纳（disclosure grammar：决策时刻只露决策本身）；要留意见的人自己展开 -->
            <button v-if="!commentOpen" type="button" class="peek-comment-toggle" @click="commentOpen = true">附意见 ›</button>
            <el-input v-else v-model="reviewComment" type="textarea" :rows="2" placeholder="意见（可选）" class="peek-review-input" />
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
              <!-- token 千位压缩（F1，disclosure-grammar §三）：与 TaskDetail rail/DeliveryCard 同 SSOT。 -->
              <span v-if="peekModelStats.tokenKnown > 0"> · tokens 合计 {{ formatTokens(peekModelStats.tokenSum) }}<template v-if="peekModelStats.tokenMissing > 0">（部分未回报，为下界）</template></span>
              <span v-else class="peek-muted"> · token 用量：未知</span>
            </template>
          </div>
        </template>
      </div>
    </div>
  </el-drawer>
</template>

<script setup>
// 状态中心（收件箱+速览双视图）。轮询纪律：收件箱并轨 liveFeed 'tasks'
// channel（5s 自链），速览并轨 'task:<id>' channel（批A Task 5：与 TaskDetail
// 共用同一条链——同 taskId 同屏时全站只此一条该任务详情轮询）。本组件不再
// 自建任何 setTimeout 轮询/epoch 守卫，全部由 channel 统一承接。签发链路与
// TaskDetail 完全同源（reviewTask API），只是把「去哪签」变成了「签发来找你」。
import { ref, computed, watch, nextTick, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { ArrowDown, ArrowRight } from "@element-plus/icons-vue";
import { statusCenter, openTaskPeek, backToInbox, closeCenter } from "../stores/statusCenter";
import { acquireChannel, pokeTask } from "../stores/liveFeed";
import { reviewTask, listOutputFiles } from "../api/tasks";
import { request } from "../api/client";
import { downloadUrl, fetchOutputFile } from "../api/files";
import {
  orderArtifactsForReview,
  shouldCollapseArtifactForReview,
} from "../utils/artifactReview";
// formatTime 保留给授权链行（N8）——签发决策面的检视级全量时间戳；行级扫读
// 面（待签/落定行）走 formatClockCompact 紧凑时钟（批次三 G4 边界：检视面
// 全量精度，扫读面紧凑）。
import { statusLabel, statusTagType, taskLampColor, formatTime, formatClockCompact, formatDuration, taskElapsedMs, formatFileSize, formatTokens, artifactTypeLabel, taskDisplayName, TASK_WORK_STATES } from "../utils/format";
import { memberPhase } from "../utils/squad";
import { displayName } from "../stores/session";
import { useAgentNames } from "../stores/agentNames";
import { markTaskSeen } from "../utils/lastSeen";
import { buildRetryRoute } from "../utils/retryPrefill";
import { burstSigned } from "../effects/burst";
import WorkLog from "./WorkLog.vue";
import MarkdownLite from "./MarkdownLite.vue";
import InboxZero from "./artwork/InboxZero.vue";
import CompletionSeal from "./CompletionSeal.vue";
import TaskJourney from "./TaskJourney.vue";

const router = useRouter();

// Agent 人话名册（批次四 Q1）：行级主文本缺名时回退注册表显示名。
const agentNames = useAgentNames();

// 「查看全部任务 →」：状态中心是任务总览的家（来找你）；要看更全的三栏视图 /
// 历史全量时深链到 /tasks（范式 Phase 3：任务台降级为深链，不占主导航）。
function openAllTasks() {
  closeForNavigation();
  router.push("/tasks");
}
// 抽屉宽度两档（<640px 全屏 / 否则 540px）：原为 setup 一次性求值，窗口跨档
// 拖放不更新——改 ref + matchMedia change 监听（max-width:639px ≡ innerWidth<640
// 的整数像素等价），挂载期持续跟随，卸载即清；两档取值不变。
const drawerSize = ref(window.innerWidth < 640 ? "100%" : "540px");
const drawerMedia = window.matchMedia("(max-width: 639px)");
const onDrawerMediaChange = (e) => {
  drawerSize.value = e.matches ? "100%" : "540px";
};
drawerMedia.addEventListener("change", onDrawerMediaChange);
onUnmounted(() => drawerMedia.removeEventListener("change", onDrawerMediaChange));

// ── 收件箱行级活面（批次三 G3/G4）：1s ticker 仅抽屉打开期间存活、关闭即清
// ——驱动「运行中」行活跳时长（cd-bg-tasks-panel Running 卡字段序「时长实时」）
// 与 todayKey 响应式日界（formatClockCompact 同日判据——承袭 CompletionSeal
// 午夜翻页教训 R1-P3，绝不裸读 new Date() 后永不重算）。纯离散文本替换零动画
// （与 WorkLog F2 同语法，reduced-motion 无涉）。 ──
const nowTick = ref(Date.now());
let tickTimer = null;
// 焦点回还（批次五 C6，与 ⌘K 同律）：抽屉关闭把焦点送回触发元素（StatusDock
// pill），键盘用户不落回 body。immediate 首评 open=false 时 focusReturnEl 为
// null，静默跳过。
let focusReturnEl = null;
watch(() => statusCenter.open, (open) => {
  if (open) {
    focusReturnEl = document.activeElement;
  } else {
    const el = focusReturnEl;
    focusReturnEl = null;
    if (statusCenter.suppressFocusReturn) {
      // 跨模态让位（⌘K 互斥关闭本抽屉）：让位不是归位——跳过这一次回还，
      // 否则本 nextTick 排在 ⌘K 聚焦之后会把焦点抢回 dock（3-lens 回归 P1）。
      statusCenter.suppressFocusReturn = false;
    } else if (el && typeof el.focus === "function" && document.contains(el)) {
      nextTick(() => el.focus());
    }
  }
  if (open && tickTimer === null) {
    nowTick.value = Date.now();
    tickTimer = setInterval(() => { nowTick.value = Date.now(); }, 1000);
  } else if (!open && tickTimer !== null) {
    clearInterval(tickTimer);
    tickTimer = null;
  }
}, { immediate: true });

const todayKey = computed(() => new Date(nowTick.value).toDateString());
// 行级紧凑时钟（G4）：同日 HH:MM、跨日 MM-DD HH:MM，SSOT=utils/format。
function rowClock(iso) {
  return formatClockCompact(iso, todayKey.value);
}
// 运行中行活跳时长（G3）：started_at 缺失/解析失败=空串（v-if 段不出现），
// 诚实降级不硬凑「已 —」。
function runElapsed(t) {
  const ms = taskElapsedMs(t, nowTick.value);
  if (ms == null) return "";
  const text = formatDuration(ms);
  return text === "—" ? "" : text;
}

// ── 收件箱数据（并轨 liveFeed 'tasks' channel：抽屉开 acquire、关 release——
// 「关闭零后台消耗」语义原样保留：channel 无其他订阅者时自停,有订阅者（如
// StatusDock）则由其继续养着,都正确。channel 内部 acquire 即触发一次立即
// refresh,故打开抽屉的即时性不倒退,无需本组件额外拉一次） ──
const inboxTasks = ref([]);
const inboxError = ref("");
const waitingTasks = computed(() => inboxTasks.value.filter((t) => t.status === "waiting_review"));
// 批七 §3-15：等待接力任务（created+depends_on 派生态）并入运行中组可见——
// 行尾灰注标注，不脉动不计时（memberPhase 同口径，任务 status 是唯一真值）。
const workingTasks = computed(() =>
  inboxTasks.value.filter(
    (t) => TASK_WORK_STATES.has(t.status) || memberPhase(t) === "waiting_upstream"
  )
);
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

// ── 速览数据（并轨 liveFeed 'task:<id>' channel——与 TaskDetail 同 taskId
// 同屏时全站只有一条该任务详情链。acquire 时机=速览打开某任务；release 时机
// =切任务/退出速览/抽屉关闭。epoch 守卫、动态轮询频率、失败保旧值全由
// channel 统一承接，本组件不再自建 epoch/setTimeout 轮询） ──
const peekTask = ref(null);
const peekEvents = ref([]);
const peekArtifacts = ref([]);
const peekModelCalls = ref([]);
const peekModelCallsLoaded = ref(false);
const peekModelCallsError = ref("");
const peekLoading = ref(false);
const peekError = ref("");

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

// 产物加载持有独立指纹（taskId+file_ids）：同一指纹已加载/加载中不重拉；
// 指纹只在「任务或产物集真的变了」时换，慢加载不再被误杀（Codex 审出的
// 竞态，Task 4 同款姿势沿用）。
const artifactsLoading = ref(false);
let artifactsFingerprint = null;

async function syncPeekArtifacts(taskId, ids) {
  const fp = `${taskId}::${(ids || []).join(",")}`;
  if (fp === artifactsFingerprint) return; // 同一指纹已加载/加载中，不重复拉
  artifactsFingerprint = fp;
  const uniqueIds = [...new Set(ids || [])];
  if (!uniqueIds.length) {
    peekArtifacts.value = [];
    artifactsLoading.value = false;
    return;
  }
  let targets = uniqueIds.slice(0, 3);
  // 先拉轻量元数据决定审阅顺序，再只下载前三件内容。元数据失败则诚实退回
  // output_file_ids 原顺序；无论哪条路径，内容预览仍严格有界为 3 件。
  try {
    const files = await listOutputFiles(taskId);
    const byId = new Map(files.map((file) => [file.id, file]));
    const candidates = uniqueIds.map((id) => byId.get(id) || { id, filename: id.slice(0, 8) });
    targets = orderArtifactsForReview(candidates).slice(0, 3).map((file) => file.id);
  } catch {
    // 元数据不可用不阻断产物审阅；下面按任务声明顺序继续拉取。
  }
  if (fp !== artifactsFingerprint) return;
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
  const ordered = orderArtifactsForReview(out);
  for (const artifact of ordered) {
    artifact.collapsed = shouldCollapseArtifactForReview(artifact, ordered);
    artifact.collapseTouched = false;
  }
  peekArtifacts.value = ordered;
  artifactsLoading.value = false;
}

function togglePeekArtifact(artifact) {
  artifact.collapseTouched = true;
  artifact.collapsed = !artifact.collapsed;
}

// 产物集变化即触发（Task 4 / TaskDetail 同款姿势）：channel 每轮询整包重拉
// task，output_file_ids 每次都是新数组引用，但 fingerprint 对未变集合零重拉。
watch(() => peekTask.value?.output_file_ids, (ids) => {
  const tid = peekTask.value?.id;
  if (!tid) return;
  syncPeekArtifacts(tid, ids || []);
});

let peekHandle = null;
let peekStops = [];
function acquirePeekFeed(taskId) {
  if (peekHandle) return; // 已持有,幂等（ensurePeekLoaded 已按 id 去重,双保险）
  peekHandle = acquireChannel(`task:${taskId}`, { modelCalls: true }); // 速览消费模型调用记录（detail opt-in）
  peekStops = [
    watch(peekHandle.state.task, (v) => {
      peekTask.value = v;
      if (v) {
        markTaskSeen(taskId); // 速览开着=正在看：轮询期间翻终态不得回头亮未读
        patchInboxTask(v); // 收件箱条目跟随速览真值即时回落，不必单独拉 inbox
      }
    }, { immediate: true }),
    watch(peekHandle.state.events, (v) => { peekEvents.value = v; }, { immediate: true }),
    watch(peekHandle.state.modelCalls, (v) => { peekModelCalls.value = v; }, { immediate: true }),
    watch(peekHandle.state.modelCallsLoaded, (v) => { peekModelCallsLoaded.value = v; }, { immediate: true }),
    watch(peekHandle.state.modelCallsError, (v) => { peekModelCallsError.value = v; }, { immediate: true }),
    // loading 双源联动（Task 12 修复 5）：单独 watch loaded 时,已 loaded 的
    // channel 若之后拉取失败,loaded 不回落 false,peekLoading 会卡在 false
    // 却无内容可看——error 分支需同样能把 loading 状态收口,而不是只镜像展示。
    watch(
      [peekHandle.state.loaded, peekHandle.state.error],
      ([l, e]) => { peekLoading.value = !l && !e; },
      { immediate: true },
    ),
    watch(peekHandle.state.error, (v) => { peekError.value = v; }, { immediate: true }),
  ];
}
function releasePeekFeed() {
  peekStops.forEach((s) => s());
  peekStops = [];
  if (peekHandle) {
    peekHandle.release();
    peekHandle = null;
  }
  // 换代/关闭即清显示态：channel 释放后不再更新，残留旧任务数据会在下次
  // acquire 前的空档里闪烁（组件在 destroy-on-close 之外的场景下持续挂载）。
  peekTask.value = null;
  peekEvents.value = [];
  peekModelCalls.value = [];
  peekModelCallsLoaded.value = false;
  peekModelCallsError.value = "";
  peekLoading.value = false;
  peekError.value = "";
}

// ── 签发（宪法路径：与 TaskDetail 同一 API，人具名 fail-closed） ──
// 本组件挂根级不随身份门重挂：setup 时可能门还没过（快照为空）——每次
// 打开抽屉懒补一次（onOpen），保证「一次具名全站免问」（Codex 审 P2）。
const signerName = computed(() => displayName());
const reviewComment = ref("");
const commentOpen = ref(false); // 意见框默认收纳，签发决策面零填空
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
  // 措辞统一（W7）：按钮/弹窗同用「驳回」——同一动作一种中文（与 TaskDetail 对齐）。
  const label = action === "approve" ? "批准放行" : "驳回";
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
    reviewComment.value = ""; commentOpen.value = false; // 签发落定即清、意见框收回，绝不残留到下一个任务
    ElMessage.success(action === "approve" ? "已批准放行" : "已驳回");
    if (action === "approve") loadAcceptedSamples(taskId); // 静默旁路：失败不影响签发主流程
    // 续体绑定：await 期间抽屉可能已关/任务已切——只有还在看同一任务时才迸发+刷新
    if (statusCenter.open && statusCenter.taskId === taskId) {
      if (action === "approve") {
        burstSigned(peekApproveEl.value?.ref); // teal 迸发：人签成功唯一许可点
      }
      // 带外补拉（Task 4 同款）：不等下一轮询，channel 落地后 task watch
      // 自动回填 peekTask 并 patchInboxTask，不再本地二次拉取。await（Task 12
      // 修复 4）：reviewing 须在数据真落地后才解锁，否则用户可能在旧数据仍
      // 显示 waiting_review 时二次点击提交，触发后端 409。
      await pokeTask(taskId);
    }
  } catch (err) {
    ElMessage.error(err.detail || err.message || "签发失败");
  } finally {
    reviewing.value = false;
  }
}

// 导航退场统一出口（Codex R0 审 P2：goFullPage/retryFromPeek 之外还有
// openAllTasks 第四条导航路径漏置空）：导航离场不回还——焦点归新页面，
// 回还只属于 Escape/点遮罩这类「放弃关闭」。所有导航出口一律走这里。
function closeForNavigation() {
  focusReturnEl = null;
  backToInbox();
  closeCenter();
}

function goFullPage() {
  const id = statusCenter.taskId;
  // 先同步切回 inbox 让 peek 子树立即响应式卸载——不等 el-drawer 的 0.3s 关闭
  // 过渡，堵死「批准放行」与 TaskDetail 同名按钮的瞬时选择器重影窗口（红线§e2e）
  closeForNavigation();
  if (id) router.push(`/tasks/${id}`);
}

// N4a：失败任务速览 → 复制为新任务（buildRetryRoute 写 flai_prefill 草案）。
// 与 goFullPage 同款退场纪律：先同步卸 peek 子树再导航，堵选择器重影窗口。
function retryFromPeek() {
  const t = peekTask.value;
  if (!t) return;
  const target = buildRetryRoute(t);
  closeForNavigation();
  router.push(target);
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

function onOpen() {
  acquireInboxFeed();
  ensurePeekLoaded(); // 幂等：目标未变则不重新 acquire
  nextTick(() => document.querySelector(".sc-shell")?.focus());
}
function onClosed() {
  releaseInboxFeed(); // channel 无其它订阅者时自停,有则由其继续养着
  releasePeekFeed();
  peekLoadedFor = null; // 下次打开重新初载
  artifactsFingerprint = null;
  artifactsLoading.value = false;
  reviewComment.value = ""; // 意见草稿不跨次会话残留（签发人姓名保留）
  commentOpen.value = false; // 意见框收回：下次签发面回到零填空默认（CRS R0-P2）
  resetSampleFixState();
}

// 初载/换代去重：openTaskPeek 从关闭态打开时，watch（open/view/taskId 变更）
// 与 @open 会双触发——peekLoadedFor 保证同一目标只 acquire 一次；目标（含
// 「离开速览」的 null）变化时先 release 旧的再 acquire 新的，防止同屏挂两条
// task channel。
let peekLoadedFor = null;
function ensurePeekLoaded() {
  const id = (statusCenter.open && statusCenter.view === "peek") ? statusCenter.taskId : null;
  if (id === peekLoadedFor) return;
  if (peekLoadedFor) releasePeekFeed(); // 换代前先释放旧任务的 channel 订阅
  peekLoadedFor = id;
  if (!id) return;
  resetSampleFixState();
  reviewComment.value = ""; // 切任务清草稿，绝不把上个任务的意见签到这个任务
  commentOpen.value = false; // 切任务意见框同步收回（CRS R0-P2）
  peekArtifacts.value = []; // 换任务先清旧任务的产物预览，避免换代间隙闪烁旧内容
  artifactsFingerprint = null; // 重进同任务（含重开同任务）允许重试上次失败的产物预览
  artifactsLoading.value = false;
  markTaskSeen(id); // 速览含产物+签发，等价「看过」，驱动任务台未读点（打开即标，不等首次拉取落地）
  acquirePeekFeed(id);
  loadAcceptedSamples(id); // 已批准任务重开也能看到固化入口（未认可样本被 ===true 过滤，静默无痕）
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
  releaseInboxFeed(); // 安全网：正常路径已在 onClosed 释放,release() 本身幂等
  releasePeekFeed();
  artifactsFingerprint = null;
  resetSampleFixState();
  if (tickTimer !== null) {
    clearInterval(tickTimer); // ticker 安全网：抽屉开着被整组件卸载时不留游离计时器
    tickTimer = null;
  }
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
  /* ring-elevation 试点（批次五 C5，claude 复刻包「shadow 假装成 border」）：
     transparent 边框占位保布局零位移，1px 暖环走 box-shadow——视觉比实边框
     更轻；hover 换环色+叠卡影，厚度不变。 */
  border: 1px solid transparent;
  border-radius: 10px;
  background: var(--paper-surface);
  box-shadow: 0 0 0 1px var(--hairline-soft);
  cursor: pointer;
  transition: transform var(--motion-fast) var(--ease-out-soft), box-shadow var(--motion-fast) var(--ease-out-soft);
}
.sc-item:hover {
  transform: translateY(-1px);
  box-shadow: 0 0 0 1px var(--clay-softer), var(--shadow-card);
}
.sc-lamp {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
/* 等待接力=空心静灯（与 WorkbenchSession .rg-lamp-hollow 同语法）：
   未开工不是异常也不是工作，绝不脉动。 */
.sc-lamp.is-hollow {
  background: transparent;
  box-shadow: inset 0 0 0 1px var(--ink-soft);
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
/* 批七 §3-15：等待接力灰注（中性——未开工不是异常） */
.sc-relay-note { color: var(--ink-faint); }
.sc-item-cta {
  flex: none;
  font-size: 12px;
  font-weight: 600;
  color: var(--clay);
}
/* amber=待人签强 CTA（信任色锁：amber 仅待审语义）——与 GuidePage
   .status-peek.is-review 同槽同语义，签发来找人。 */
.sc-item-cta.is-review {
  color: var(--trust-pending);
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
  transition: background var(--motion-fast) var(--ease-out-soft), color var(--motion-fast) var(--ease-out-soft);
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
.peek-artifact-head.is-collapsed {
  border-bottom-color: transparent;
}
.peek-artifact-toggle {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}
.peek-artifact-chevron {
  flex: none;
  width: 10px;
  height: 10px;
  color: var(--ink-faint);
  font-size: 10px;
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
/* 下载链接（批次五 C3 裁决，DeliveryCard .delivery-chip 同语法）：常驻非状态
   语义的链接降 ink-soft+下划线，hover 回 clay。 */
.peek-artifact-dl {
  flex: none;
  font-size: 12px;
  color: var(--ink-soft);
  text-decoration: underline;
  text-underline-offset: 2px;
}
.peek-artifact-dl:hover {
  color: var(--clay);
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
.peek-review-chain {
  font-size: 11.5px;
  color: var(--ink-faint);
  margin-bottom: 10px;
  line-height: 1.6;
}
.peek-comment-toggle {
  align-self: flex-start;
  background: transparent;
  border: none;
  padding: 2px 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-soft);
  cursor: pointer;
}
.peek-comment-toggle:hover { color: var(--ink); }
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

/* N9 敏感整窗框（peek）：双线 ink 边框+声明行，形状/字重承载，零新色。 */
.sc-body.sc-sensitive {
  border: 3px double var(--ink);
  border-radius: 14px;
}
.peek-sensitive-decl {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ink);
  line-height: 1.6;
  border-bottom: 1px solid var(--hairline);
  padding-bottom: 6px;
  margin-bottom: 10px;
}
.peek-sensitive-decl > span[aria-hidden] {
  flex: none;
  font-size: 9px;
}
/* N4a 速览失败重试行 */
.peek-retry {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.peek-retry-btn {
  background: transparent;
  border: 1px solid var(--hairline);
  border-radius: 8px;
  padding: 4px 12px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--clay);
  cursor: pointer;
}
.peek-retry-hint {
  font-size: 12px;
  color: var(--ink-faint);
}
</style>
