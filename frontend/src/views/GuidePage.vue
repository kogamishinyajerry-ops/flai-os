<template>
  <div class="guide-page" :class="{ 'is-empty': !started && messages.length === 0 }">
    <!-- 起手 hero（未开始且无消息）：衬线问候 + 具名，随 composer 在视口垂直居中。 -->
    <div v-if="!started && messages.length === 0 && !restoring" class="guide-hero fx-rise">
      <!-- 减重批：hero 只剩问候+一句主标题（Claude 精髓=留白克制，信任靠交互
           建立不靠说教）。价值主张/政策句收进 composer 下一行；名字由
           WelcomeGate 身份门一次收齐，此处不再询问。 -->
      <div class="hero-mark">导</div>
      <p class="hero-greeting">{{ greeting }}</p>
      <h1 class="hero-title">说说你要做的工程活儿</h1>
      <!-- 四意图卡（原 hero-examples/ex-chip 原地升级）：数据=四分类 AGENT_CATEGORY
           一一配对，点击只填 draft + focusComposer，绝不代发（同 setExample 语义）。 -->
      <div class="hero-intents">
        <div
          v-for="item in INTENT_EXAMPLES"
          :key="item.category"
          class="intent-card"
          role="button"
          tabindex="0"
          @click="setExample(item.example)"
          @keydown.enter.prevent="setExample(item.example)"
          @keydown.space.prevent="setExample(item.example)"
        >
          <span class="intent-accent" :style="{ background: categoryColor(item.category) }"></span>
          <!-- 减重批：tip 收进 title 悬浮，卡面只留标题+例句两行 -->
          <div class="intent-body" :title="categoryTip(item.category)">
            <div class="intent-title"><IntentGlyph :name="item.glyph" :size="21" />{{ categoryLabel(item.category) }}</div>
            <p class="intent-example">{{ item.example }}</p>
          </div>
        </div>
      </div>
    </div>

    <el-alert
      v-if="pageError"
      type="error"
      :title="pageError"
      show-icon
      :closable="false"
      class="page-alert"
    />

    <el-alert
      v-if="conversationReadOnly && !pageError"
      type="info"
      :title="conversationReadOnlyNotice"
      show-icon
      :closable="false"
      class="page-alert conversation-readonly"
    />

    <!-- 会话流 -->
    <div v-if="messages.length || sending" ref="streamEl" class="thread">
      <div v-for="(m, idx) in messages" :key="idx" :class="['bubble-row', m.role]">

        <!-- 用户消息：靠右暖气泡 -->
        <div v-if="m.role === 'user'" class="user-bubble" :class="{ 'fx-ink-in': m.fresh }">
          <div class="user-text">{{ m.content }}</div>
          <div v-if="m.attachments && m.attachments.length" class="user-files">
            <span v-for="a in m.attachments" :key="a.id" class="file-chip">📎 {{ a.filename }}</span>
          </div>
          <div v-if="m.createdAt" class="bubble-time">{{ formatTime(m.createdAt) }}</div>
        </div>

        <!-- 助手消息：小 mark + 流动排版，plan-card 内联渲染 -->
        <template v-else>
          <div class="ai-mark">导</div>
          <div class="ai-body" :class="{ 'fx-ink-in': m.fresh }">
            <div class="ai-name">智能导引<span v-if="m.createdAt" class="bubble-time">{{ formatTime(m.createdAt) }}</span></div>
            <p v-if="m.content" class="ai-lead">{{ m.content }}</p>
            <div
              v-if="m.recommendation?.decision === 'awaiting_plan'"
              class="execution-strip blocked"
            >
              <span class="execution-dot"></span>
              <span class="execution-title">导引仍在澄清，尚未创建任务</span>
              <span v-if="m.recommendation.execution?.issues?.length" class="execution-detail">
                {{ m.recommendation.execution.issues[0].message }}
              </span>
            </div>

            <!-- 导引计划（M8 编排官）：refuse=显式拒绝 -->
            <div v-if="m.recommendation && m.recommendation.decision === 'refuse'" class="plan-card refuse" :class="{ 'fx-rise': m.fresh }">
              <div class="plan-kicker refuse">显式拒绝</div>
              <h3 class="plan-goal-title small">这个需求，平台暂时接不住</h3>
              <p v-if="m.recommendation.reason" class="plan-reason">{{ m.recommendation.reason }}</p>
              <div
                v-if="m.recommendation.residual_problems && m.recommendation.residual_problems.length"
                class="plan-section"
              >
                <div class="section-label">你手上仍未解决的问题</div>
                <ul class="plan-list">
                  <li v-for="(p, i) in m.recommendation.residual_problems" :key="i">{{ p }}</li>
                </ul>
              </div>
              <div v-if="m.recommendation.reframe && m.recommendation.reframe.length" class="plan-section">
                <div class="section-label">可以试试这样重述 / 拆解</div>
                <div class="reframe-list">
                  <div
                    v-for="(r, i) in m.recommendation.reframe"
                    :key="i"
                    class="reframe-item"
                    role="button"
                    tabindex="0"
                    @click="adoptReframe(r)"
                    @keydown.enter.prevent="adoptReframe(r)"
                    @keydown.space.prevent="adoptReframe(r)"
                  >
                    <span class="reframe-num">{{ i + 1 }}</span>
                    <span class="reframe-text">{{ r }}</span>
                    <span class="reframe-adopt">采纳 →</span>
                  </div>
                </div>
                <p class="reframe-escape">或者直接在下方输入框，告诉导引你想怎么调整。</p>
              </div>
            </div>

            <!-- orchestrate=召集协作 -->
            <div
              v-else-if="m.recommendation && m.recommendation.decision === 'orchestrate'"
              class="plan-card"
              :class="{ 'fx-rise': m.fresh }"
            >
              <div class="plan-topline">
                <span class="plan-kicker">协作方案</span>
                <span class="plan-count">{{ planAgents(m.recommendation).length }} 个 Agent 协作</span>
              </div>
              <div
                v-if="m.recommendation.execution"
                class="execution-strip"
                :class="{
                  blocked:
                    m.recommendation.execution.status !== 'dispatched' ||
                    !!planTaskMappingIssue(m.recommendation),
                }"
              >
                <span class="execution-dot"></span>
                <span class="execution-title">
                  {{
                    planTaskMappingIssue(m.recommendation)
                      ? "版本化计划任务映射不可验证，已停止关联"
                      : executionStatusText(m.recommendation.execution)
                  }}
                </span>
                <span
                  v-if="
                    planTaskMappingIssue(m.recommendation) ||
                    (m.recommendation.execution.issues && m.recommendation.execution.issues.length)
                  "
                  class="execution-detail"
                >{{
                  planTaskMappingIssue(m.recommendation) ||
                  m.recommendation.execution.issues[0].message
                }}</span>
              </div>
              <div
                v-else-if="m.recommendation.contract === 'guide_dag.v1'"
                class="execution-strip blocked"
              >
                <span class="execution-dot"></span>
                <span class="execution-title">版本化 DAG 缺少权威执行回执</span>
                <span class="execution-detail">已禁止逐节点创建；请用 safe_auto 重新提交。</span>
              </div>
              <h2 v-if="m.recommendation.goal" class="plan-goal-title">{{ m.recommendation.goal }}</h2>
              <p v-if="m.recommendation.analysis" class="plan-reason">{{ m.recommendation.analysis }}</p>
              <div v-if="m.recommendation.workflow" class="plan-section">
                <div class="section-label">分工如何衔接</div>
                <p class="plan-workflow">{{ m.recommendation.workflow }}</p>
              </div>

              <div class="section-label roster-label">召集的 Agent · {{ planAgents(m.recommendation).length }}</div>
              <div class="agent-list">
                <div
                  v-for="(a, ai) in planAgents(m.recommendation)"
                  :key="a.node_id || `${a.agent_id || 'agent'}:${ai}`"
                  class="agent-card"
                  :class="{ 'fx-rise': m.fresh }"
                >
                  <div class="agent-main">
                    <div class="agent-top">
                      <span class="agent-name">{{ a.agent_name }}</span>
                      <span v-if="a.maturity || a.status" class="agent-maturity">
                        {{ [a.maturity, a.status].filter(Boolean).join(" / ") }}
                      </span>
                    </div>

                    <!-- B1 对话轴督战：该会话已为此 Agent 召集过任务才显示（诚实地板，
                         未召集零占位）；点击直开任务速览，不逼人跳页看进度。 -->
                    <div
                      v-if="agentTaskInfo(a, m.recommendation)"
                      class="agent-status"
                      role="button"
                      tabindex="0"
                      @click.stop="openTaskPeek(agentTaskInfo(a, m.recommendation).latest.id)"
                      @keydown.enter.stop.prevent="openTaskPeek(agentTaskInfo(a, m.recommendation).latest.id)"
                      @keydown.space.stop.prevent="openTaskPeek(agentTaskInfo(a, m.recommendation).latest.id)"
                    >
                      <span
                        class="status-lamp"
                        :class="{ 'is-pulsing': isWorkState(agentTaskInfo(a, m.recommendation).latest.status) }"
                        :style="{ background: taskLampColor(agentTaskInfo(a, m.recommendation).latest.status) }"
                      ></span>
                      <span class="status-word" :style="{ color: taskLampColor(agentTaskInfo(a, m.recommendation).latest.status) }">
                        {{ statusLabel(agentTaskInfo(a, m.recommendation).latest.status) }}
                      </span>
                      <span v-if="agentTaskInfo(a, m.recommendation).extra > 0" class="status-extra">+{{ agentTaskInfo(a, m.recommendation).extra }}</span>
                      <!-- 行动召唤按态分级：待签发=amber 强 CTA（签发来找人）；其余=速览 -->
                      <span v-if="agentTaskInfo(a, m.recommendation).latest.status === 'waiting_review'" class="status-peek is-review">审阅签发 →</span>
                      <span v-else class="status-peek">速览 →</span>
                    </div>

                    <!-- 产物锚点行（Claude Artifact 卡片锚点哲学）：任务完成且真有产物
                         才长出——点击同样直开速览（产物预览+签发同面板），零跳页。 -->
                    <div
                      v-if="agentTaskInfo(a, m.recommendation) && agentTaskInfo(a, m.recommendation).latest.status === 'completed' && (agentTaskInfo(a, m.recommendation).latest.output_file_ids || []).length"
                      class="status-artifact"
                      role="button"
                      tabindex="0"
                      @click.stop="openTaskPeek(agentTaskInfo(a, m.recommendation).latest.id)"
                      @keydown.enter.stop.prevent="openTaskPeek(agentTaskInfo(a, m.recommendation).latest.id)"
                      @keydown.space.stop.prevent="openTaskPeek(agentTaskInfo(a, m.recommendation).latest.id)"
                    >
                      <svg class="artifact-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/></svg>
                      <span class="artifact-count">{{ (agentTaskInfo(a, m.recommendation).latest.output_file_ids || []).length }} 件产物</span>
                      <span class="artifact-open">查看 ↗</span>
                    </div>

                    <p v-if="a.rationale" class="agent-rationale">{{ a.rationale }}</p>
                    <p v-if="a.role" class="agent-role"><span class="role-tag">分工</span>{{ a.role }}</p>
                    <p v-if="a.depends_on && a.depends_on.length" class="agent-role">
                      <span class="role-tag">前置</span>{{ a.depends_on.join("、") }}
                    </p>
                    <div v-if="inputCount(a)" class="agent-draft">
                      <div class="draft-label">预填草案 · {{ inputCount(a) }} 个字段</div>
                      <div class="draft-fields">
                        <span v-for="(v, k) in a.prefilled_inputs" :key="k" class="draft-field">
                          <span class="df-key">{{ k }}</span>
                          <span class="df-val">{{ formatDraftVal(v) }}</span>
                        </span>
                      </div>
                    </div>
                    <p v-if="a.stripped_fields && a.stripped_fields.length" class="agent-stripped">
                      已剔除不合法字段：{{ a.stripped_fields.join("、") }}（未匹配该 Agent 的输入契约）
                    </p>
                    <!-- 历史 plan_only 会话保留兼容入口；新 safe_auto 计划由后端执行，
                         页面不再自动点按钮，也不要求用户搬运参数。 -->
                    <div
                      v-if="
                        conversationStatus === 'active' &&
                        !m.recommendation.execution &&
                        guidePlanAllowsManualCreate(m.recommendation)
                      "
                      class="agent-actions"
                    >
                      <button class="agent-cta" @click="createOneTask(a, m.recommendation)">去创建此任务</button>
                    </div>
                  </div>
                </div>
              </div>

              <p
                v-if="m.recommendation.dropped_agents && m.recommendation.dropped_agents.length"
                class="plan-alert"
              >
                已剔除无法召集的 Agent：{{ m.recommendation.dropped_agents.join("、") }}（幻觉/已下线/不可召集/重复）
              </p>
              <p v-if="m.recommendation.capped" class="plan-alert">
                召集 Agent 数已达上限（5 个），后续提议已截断。
              </p>

              <div class="plan-foot">
                <button class="workbench-btn" @click="openWorkbench">进入协作工作台 →</button>
                <button type="button" class="plan-escape" @click="focusComposer">想调整方案？直接告诉导引 ↓</button>
                <span v-if="planTaskMappingIssue(m.recommendation)" class="plan-note">
                  版本化计划任务映射不可验证，页面已停止关联任务；请重新获取权威执行回执。
                </span>
                <span
                  v-else-if="
                    m.recommendation.contract === 'guide_dag.v1' &&
                    m.recommendation.execution?.status === 'dispatched'
                  "
                  class="plan-note"
                >
                  任务图已原子创建，根节点已入队，下游等待依赖推进，叶节点仍需真人签发。
                </span>
                <span v-else-if="m.recommendation.execution?.status === 'dispatched'" class="plan-note">
                  安全任务已由平台自动创建并入队；若任务进入 waiting_review，最终工程签发仍由你完成。
                </span>
                <span v-else-if="m.recommendation.execution" class="plan-note">
                  当前方案未自动执行，也没有创建任务；请按上方原因直接在会话中补充或调整。
                </span>
                <span
                  v-else-if="conversationStatus === 'active' && guidePlanAllowsManualCreate(m.recommendation)"
                  class="plan-note"
                >
                  在工作台里看分工架构、逐个召集 Agent、追进度——签发权始终在你，
                  每个任务都由你补全并<strong>亲手提交</strong>。
                </span>
                <span v-else class="plan-note">
                  版本化方案缺少权威执行回执，已禁止回退为逐节点手动创建。
                </span>
              </div>
            </div>
          </div>
        </template>
      </div>

      <div v-if="sending" class="bubble-row assistant">
        <div class="ai-mark">导</div>
        <div class="ai-thinking">
          <ThinkingInk />
          <span class="tlabel">导引思考中…</span>
        </div>
      </div>
    </div>

    <!-- 悬浮质感 composer：会话开始后固定悬浮在视口底部（Claude 布局，始终可见） -->
    <div class="composer" :class="{ 'composer-fixed': started || messages.length }">
      <div class="composer-inner">
      <div v-if="pendingFiles.length" class="composer-files">
        <span
          v-for="f in pendingFiles"
          :key="f.uid"
          :class="['file-chip', 'closable', { error: f.status === 'error' }]"
          :title="f.status === 'error' ? f.error : ''"
        >
          📎 {{ f.name }}{{ f.status === "error" ? "（上传失败）" : "" }}
          <span v-if="!f.locked && !sending" class="chip-x" @click="removePendingFile(f)">×</span>
        </span>
      </div>
      <div class="composer-shell">
        <div class="composer-row">
          <el-upload
            class="composer-attach"
            :auto-upload="false"
            :show-file-list="false"
            multiple
            :on-change="handleFileSelect"
            :disabled="sending || conversationReadOnly"
          >
            <button class="icon-btn" :disabled="sending || conversationReadOnly" title="添加附件（≤5 个/条；文本类直读、xlsx 预览）" aria-label="添加附件">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a5 5 0 0 1-7.07-7.07l9.19-9.19a3.5 3.5 0 0 1 4.95 4.95l-9.2 9.19a1.5 1.5 0 0 1-2.12-2.12l8.49-8.49"/></svg>
            </button>
          </el-upload>
          <!-- Agent 选择器（范式 2b：门户降级为 composer 内浏览）：点选只把
               Agent 名填进草稿并聚焦——问导引怎么用它，绝不代发（人是唯一发起者）。 -->
          <el-popover placement="top-start" :width="320" trigger="click" popper-class="agent-pick-pop">
            <template #reference>
              <button class="icon-btn" :disabled="sending || conversationReadOnly" title="浏览可用 Agent" aria-label="浏览可用 Agent">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-3.92 7.94"/></svg>
              </button>
            </template>
            <div class="agent-pick">
              <!-- 错误态只显示错误行（「· 0」会被误读成平台真没有 Agent——
                   AgentPortal 同款语义区分）；真零态如实显示空态文案。 -->
              <div v-if="pickAgentsError" class="ap-error">{{ pickAgentsError }}</div>
              <template v-else>
                <div class="ap-title">可用 Agent · {{ pickAgents.length }}</div>
                <div v-if="!pickAgents.length" class="ap-zero">暂无可用 Agent</div>
              </template>
              <div
                v-for="a in pickAgents"
                :key="a.id"
                class="ap-item"
                role="button"
                tabindex="0"
                @click="pickAgent(a)"
                @keydown.enter.prevent="pickAgent(a)"
              >
                <span class="ap-dot" :style="{ background: categoryColor(a.category) }"></span>
                <span class="ap-main">
                  <span class="ap-name">{{ a.name }}
                    <span v-if="a.maturity" class="ap-maturity" :title="maturityTip(a.maturity)">{{ a.maturity }}</span>
                  </span>
                  <span class="ap-sub">{{ a.summary }}</span>
                  <!-- 诚实前置（宪法五条）：信任边界随第一次点选同屏可见，
                       不许「L0/模拟」藏在两跳深的 /portal 里 -->
                  <span v-if="a.limitations && a.limitations.length" class="ap-limit">{{ a.limitations[0] }}</span>
                </span>
              </div>
              <a class="ap-portal-link" @click="$router.push('/portal')">浏览完整门户 →</a>
            </div>
          </el-popover>
          <el-input
            v-model="draft"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 6 }"
            :disabled="sending || conversationReadOnly"
            :placeholder="composerPlaceholder"
            class="composer-input"
            @keydown.enter.exact.prevent="send"
          />
          <button class="send-btn" :disabled="conversationReadOnly || sending || !draft.trim()" aria-label="发送" @click="send">
            <svg v-if="!sending" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M7 11l5-5 5 5M12 6v13"/></svg>
            <span v-else class="send-spin"></span>
          </button>
        </div>
      </div>
      <!-- safe_auto 默认执行安全计划；“自动执行”与“工程签发”严格分层。 -->
      <div class="composer-hint">
        <span>满足安全门的方案会自动执行；缺信息或风险例外会在这里说明，最终工程签发仍由你完成。</span>
        <span class="keys"><kbd>Enter</kbd> 发送<span class="sep">·</span><kbd>⇧ Enter</kbd> 换行<span class="sep">·</span>📎 可带附件</span>
      </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, computed, nextTick, watch, onMounted, onUnmounted } from "vue";
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { createConversation, postMessage, getConversation } from "../api/conversations";
import { listAgents } from "../api/agents";
import { uploadFile as apiUploadFile } from "../api/files";
import { authenticatedPrincipal, fetchMe } from "../stores/session";
import {
  createGuideSafeAutoOutbox,
  dispatchGuideSafeAutoIntent,
  filesFromGuideSafeAutoRecord,
  recoverGuideSafeAutoOutbox,
} from "../utils/guideSafeAutoOutbox";
import { categoryColor, categoryLabel, categoryTip, maturityTip, statusLabel, taskLampColor, TASK_WORK_STATES, formatTime } from "../utils/format";
import {
  guidePlanAgents,
  guidePlanAllowsManualCreate,
  guidePlanTaskMappingIssue,
  indexGuidePlanTasks,
  tasksForGuidePlanAgent,
} from "../utils/guidePlan";
import { openTaskPeek } from "../stores/statusCenter";
import { acquireChannel } from "../stores/liveFeed";
import { resolvedTheme } from "../stores/theme";
import ThinkingInk from "../components/artwork/ThinkingInk.vue";
import IntentGlyph from "../components/artwork/IntentGlyph.vue";

const router = useRouter();
const route = useRoute();

const GUIDE_AGENT_ID = "guide_agent";
const MAX_FILES_PER_MESSAGE = 5; // 与后端 PostMessageRequest / 运行时同值

const started = ref(false);
const conversationId = ref("");
const conversationStatus = ref("");
const messages = ref([]);
const draft = ref("");
const sending = ref(false);
const pageError = ref("");
const streamEl = ref(null);
const outboxRecoveryBlocked = ref(false);
const outboxRecoveryActive = ref(false);
const guideSafeAutoOutbox = createGuideSafeAutoOutbox();
// 已恢复会话只有后端明确 active 时才允许继续发言；缺失/未知状态同样
// fail-closed 为只读。全新会话 started=false，不受该守卫影响。
const routeConversationId = computed(() =>
  typeof route.query.c === "string" && route.query.c ? route.query.c : ""
);
const conversationTargetMismatch = computed(() =>
  !!routeConversationId.value && conversationId.value !== routeConversationId.value
);
const conversationReadOnly = computed(() =>
  outboxRecoveryBlocked.value ||
  conversationTargetMismatch.value ||
  (started.value && conversationStatus.value !== "active")
);
const conversationReadOnlyNotice = computed(() =>
  outboxRecoveryBlocked.value
    ? "有一轮自动执行仍待服务端权威确认，已锁定输入；刷新后会用原 request_id 自动恢复"
    : conversationTargetMismatch.value
    ? "会话尚未可靠加载，已禁止发送；请重新打开该会话"
    : started.value && !conversationStatus.value
    ? "会话加载失败，已禁止发送；请重新打开该会话"
    : "会话已归档，只读展示——可查看历史消息与任务，不能继续发送"
);
// composer placeholder 语境分化：未起手空会话引导点意图卡；会话中改为「继续说下去」，
// 不再重复「回答导引的追问」（此刻输入框已在真实对话流里，无需再解释这是什么）。
const composerPlaceholder = computed(() =>
  conversationReadOnly.value
    ? "会话已归档，仅可查看"
    : !started.value && messages.value.length === 0
    ? "描述你的工程需求，或点一张下方的意图卡…"
    : "回复导引，继续说下去…"
);
// 待发送附件（M7）：选中只入列（raw 留本地），发送时才上传——同 TaskCreate 的
// P2-A 反孤儿纪律；已上传项记 fileId，失败重试不重复上传。
const pendingFiles = ref([]);
let fileSeq = 0;
// 网络丢响应时以同一 request_id 重试；只有正文/附件意图真变化才换 key。
// 后端回执是最终去重权威，本地只负责让用户无感复用同一轮授权。
let retryTurn = null;

let sendUiEpoch = 0;
const inFlightSends = new Map();
const failedSends = new Map();
let freshInFlightSend = null;
let failedFreshSend = null;
let internalConversationNavigation = null;

function invalidateSendUi() {
  sendUiEpoch++;
  sending.value = false;
}

function isCurrentSendUi(token, loadEpoch, targetConversationId) {
  return (
    token === sendUiEpoch &&
    loadEpoch === conversationLoadEpoch &&
    conversationId.value === targetConversationId
  );
}

function bindInFlightSend(operation, targetConversationId) {
  const previousTarget = operation.targetConversationId;
  if (previousTarget && inFlightSends.get(previousTarget) === operation) {
    inFlightSends.delete(previousTarget);
  }
  operation.targetConversationId = targetConversationId;
  if (targetConversationId) inFlightSends.set(targetConversationId, operation);
}

function releaseInFlightSend(operation) {
  const targetConversationId = operation.targetConversationId;
  if (targetConversationId && inFlightSends.get(targetConversationId) === operation) {
    inFlightSends.delete(targetConversationId);
  }
  if (freshInFlightSend === operation) freshInFlightSend = null;
}

function isViewingConversation(targetConversationId) {
  return typeof route.query.c === "string" && route.query.c === targetConversationId;
}

function rememberFailedSend(operation, err) {
  const targetConversationId = operation.targetConversationId;
  const failure = {
    content: operation.content,
    files: operation.files,
    requestId: operation.requestId,
    fingerprint: operation.fingerprint,
    error: err.detail || err.message || "发送失败",
  };
  if (targetConversationId) failedSends.set(targetConversationId, failure);
  else if (operation.originatedFresh) failedFreshSend = failure;
}

function restoreConversationSendState(targetConversationId) {
  if (conversationId.value !== targetConversationId) return;
  const inFlight = inFlightSends.get(targetConversationId);
  if (inFlight) {
    sending.value = true;
    return;
  }
  sending.value = false;
  const failed = failedSends.get(targetConversationId);
  if (!failed) return;
  draft.value = failed.content;
  pendingFiles.value = [...failed.files];
  retryTurn = failed.requestId
    ? { fingerprint: failed.fingerprint, requestId: failed.requestId }
    : null;
  pageError.value = failed.error;
}

function restoreFreshSendState() {
  if (routeConversationId.value || conversationId.value) return;
  if (freshInFlightSend) {
    sending.value = true;
    return;
  }
  sending.value = false;
  const failed = failedFreshSend;
  if (!failed) return;
  draft.value = failed.content;
  pendingFiles.value = [...failed.files];
  retryTurn = failed.requestId
    ? { fingerprint: failed.fingerprint, requestId: failed.requestId }
    : null;
  pageError.value = failed.error;
}

function clearFailedSendIfCommitted(targetConversationId, history) {
  const failed = failedSends.get(targetConversationId);
  if (!failed?.requestId) return;
  const alreadyCommitted = history.some(
    (message) => message?.recommendation?.execution?.request_id === failed.requestId
  );
  if (alreadyCommitted) failedSends.delete(targetConversationId);
}

function hasActiveGuideSend() {
  return (
    sending.value ||
    outboxRecoveryActive.value ||
    outboxRecoveryBlocked.value ||
    !!retryTurn ||
    !!freshInFlightSend ||
    inFlightSends.size > 0 ||
    hasPendingGuideOutbox()
  );
}

function canNavigateDuringGuideSend(to = null) {
  if (
    to &&
    internalConversationNavigation &&
    typeof to.query?.c === "string" &&
    to.query.c === internalConversationNavigation
  ) {
    return true;
  }
  return !hasActiveGuideSend();
}

onBeforeRouteLeave(() => canNavigateDuringGuideSend());
onBeforeRouteUpdate((to) => canNavigateDuringGuideSend(to));

function newTurnRequestId() {
  return globalThis.crypto?.randomUUID
    ? globalThis.crypto.randomUUID()
    : `turn_${Date.now()}_${Math.random().toString(36).slice(2)}`;
}

function attachmentIntentForFiles(files) {
  return files.map((file, index) => {
    const raw = file.raw;
    const sizeBytes = Number.isSafeInteger(raw?.size) && raw.size >= 0 ? raw.size : null;
    const lastModified = Number.isSafeInteger(raw?.lastModified) && raw.lastModified >= 0
      ? raw.lastModified
      : null;
    const mimeType = typeof raw?.type === "string" ? raw.type : "";
    const seed = JSON.stringify([String(file.uid), file.name, sizeBytes, mimeType, lastModified]);
    let hash = 2166136261;
    for (let i = 0; i < seed.length; i += 1) {
      hash ^= seed.charCodeAt(i);
      hash = Math.imul(hash, 16777619);
    }
    return {
      token: `attachment_${index}_${(hash >>> 0).toString(16).padStart(8, "0")}`,
      name: file.name,
      sizeBytes,
      mimeType,
      lastModified,
    };
  });
}

function turnRequestId(content, attachmentIntent) {
  const fingerprint = JSON.stringify([content, attachmentIntent]);
  if (retryTurn && retryTurn.fingerprint === fingerprint) return retryTurn.requestId;
  const requestId = newTurnRequestId();
  retryTurn = { fingerprint, requestId };
  return requestId;
}

function hasPendingGuideOutbox() {
  try {
    return guideSafeAutoOutbox.read() !== null;
  } catch {
    // 畸形/未知版本/存储不可读均不能当作“没有待办”继续 POST。
    return true;
  }
}

function failedSendMatchesCurrentOutbox(operation) {
  if (!operation.requestId) return true;
  const principal = authenticatedPrincipal();
  if (!principal) return false;

  // A failed turn is directly retryable only on the exact page target that owns the durable
  // intent. A forced route switch must not let another conversation consume the one-tab outbox.
  const routeTarget = routeConversationId.value || null;
  if ((operation.targetConversationId || null) !== routeTarget) return false;

  try {
    const record = guideSafeAutoOutbox.loadForPrincipal(principal);
    if (record?.phase === "preparing_uploads") {
      return guideSafeAutoOutbox.matchesUploadIntent(principal, {
        requestId: operation.requestId,
        agentId: GUIDE_AGENT_ID,
        conversationId: operation.targetConversationId || null,
        content: operation.content,
        attachmentIntent: operation.attachmentIntent,
      });
    }
    return guideSafeAutoOutbox.matchesIntent(principal, {
      requestId: operation.requestId,
      agentId: GUIDE_AGENT_ID,
      conversationId: operation.targetConversationId || null,
      content: operation.content,
      fileIds: operation.files.map((file) => file.fileId),
      files: operation.files.map((file) => ({ id: file.fileId, name: file.name })),
      attachmentIntent: operation.attachmentIntent,
    });
  } catch {
    // unreadable/malformed/version-mismatched/principal-drifted records stay fail-closed.
    return false;
  }
}

function preflightDurableRetry(principal, operation) {
  let record;
  try {
    record = guideSafeAutoOutbox.loadForPrincipal(principal);
  } catch (error) {
    operation.outboxPreflightFailed = true;
    throw error;
  }

  if (!record) {
    if (retryTurn?.requestId) {
      operation.requestId = retryTurn.requestId;
      operation.outboxPreflightFailed = true;
      throw new Error("OUTBOX_RECORD_MISSING: 待确认 safe_auto 意图已丢失，禁止生成新 request_id");
    }
    return null;
  }

  operation.requestId = record.request_id;
  const routeTarget = routeConversationId.value || null;
  const operationTarget = operation.targetConversationId || null;
  const fileIds = operation.files.map((file) => file.fileId);
  const filesReady = fileIds.every((fileId) => typeof fileId === "string" && fileId.length > 0);
  operation.fingerprint = JSON.stringify([operation.content, operation.attachmentIntent]);
  if (record.phase === "preparing_uploads") {
    if (
      routeTarget !== operationTarget ||
      !guideSafeAutoOutbox.matchesUploadIntent(principal, {
        requestId: record.request_id,
        agentId: GUIDE_AGENT_ID,
        conversationId: operationTarget,
        content: operation.content,
        attachmentIntent: operation.attachmentIntent,
      })
    ) {
      operation.outboxPreflightFailed = true;
      throw new Error(
        "OUTBOX_INTENT_MISMATCH: 待上传附件意图与当前主体、会话或正文不一致，禁止上传或换新 ID",
      );
    }
    retryTurn = { fingerprint: operation.fingerprint, requestId: record.request_id };
    return record;
  }
  if (
    routeTarget !== operationTarget ||
    !filesReady ||
    !guideSafeAutoOutbox.matchesIntent(principal, {
      requestId: record.request_id,
      agentId: GUIDE_AGENT_ID,
      conversationId: operationTarget,
      content: operation.content,
      fileIds,
      files: operation.files.map((file) => ({ id: file.fileId, name: file.name })),
      attachmentIntent: operation.attachmentIntent,
    })
  ) {
    operation.outboxPreflightFailed = true;
    throw new Error(
      "OUTBOX_INTENT_MISMATCH: 待确认意图与当前主体、会话、正文或附件不一致，禁止上传或换新 ID",
    );
  }
  retryTurn = { fingerprint: operation.fingerprint, requestId: record.request_id };
  return record;
}

// 时段感问候（Claude「Up late?」人格温度）：起手 hero 只挂载一次渲染，但改用
// computed 让「随主题」变体能在主题切换时即时反映（不需要跟随时间跳动刷新，
// 理由同旧注释——只是克制的抒情点缀，不值得为纯时间流逝另起 timer）。
// 暗色主题下深夜变体换「夜航」风格文案（仅深夜这一档，其余时段克制不铺开臆造文案）。
const greeting = computed(() => {
  const h = new Date().getHours();
  if (h >= 5 && h < 11) return "早。";
  if (h >= 11 && h < 14) return "午安。";
  if (h >= 14 && h < 18) return "下午好。";
  if (h >= 18 && h < 23) return "晚上好。";
  return resolvedTheme.value === "dark" ? "夜航中？" : "夜深了，辛苦。"; // 23:00–次日 5:00
});

// 空状态四意图卡（Claude 起手 chips 升级版）：与 AGENT_CATEGORY 四分类一一配对，
// 点一下把示例填进输入框并聚焦，用户再改再发（绝不代发）。
// glyph=IntentGlyph 墨线图标（Codex 绘）：disk=性能包线/knowledge=书+放大镜/
// logic=状态机/fta=故障树——各配四分类的旗舰意象。
const INTENT_EXAMPLES = [
  { category: "tool_automation", glyph: "disk", example: "给这批性能盘 case 做批量核算，出汇总" },
  { category: "knowledge_qa", glyph: "knowledge", example: "查一下供电系统适航规范的相关依据" },
  { category: "structured_gen", glyph: "logic", example: "做双通道供电系统的控制逻辑和故障树分析" },
  { category: "reasoning_assist", glyph: "fta", example: "帮我起草一份 XX 系统失效的 FTA 顶事件分析" },
];
function setExample(text) {
  draft.value = text;
  focusComposer();
}

function handleFileSelect(uploadFile) {
  if (pendingFiles.value.length >= MAX_FILES_PER_MESSAGE) {
    ElMessage.error(`单条消息最多 ${MAX_FILES_PER_MESSAGE} 个附件`);
    return;
  }
  pendingFiles.value.push(
    reactive({
      uid: uploadFile.uid ?? `gf_${++fileSeq}`,
      name: uploadFile.name,
      raw: uploadFile.raw,
      status: "pending", // pending | done | error
      fileId: null,
      error: "",
    })
  );
}

function removePendingFile(item) {
  if (item.locked || sending.value || outboxRecoveryActive.value || outboxRecoveryBlocked.value) {
    return;
  }
  pendingFiles.value = pendingFiles.value.filter((f) => f.uid !== item.uid);
}

async function uploadPendingFiles(files = pendingFiles.value, expectedPrincipal = null) {
  // 顺序上传未完成项（含上一轮失败项）；任一失败即抛出，本轮消息不发送。
  // 已知行为（反方审 P3）：某轮失败但附件已上传成功（status:done）时，附件
  // 保留在待发区——这是重试语义（重试同一句不重复上传）。若用户改发别的
  // 内容，这些附件会一并带上，但 chips 始终可见、可逐个移除，故不隐藏、
  // 不静默——是否带上由用户自己看着 chips 决定。
  for (const item of files) {
    if (item.status === "done") continue;
    item.status = "uploading";
    item.error = "";
    try {
      if (!item.raw) throw new Error("原始附件已丢失，禁止自动重传");
      const res = await apiUploadFile(item.raw, null, expectedPrincipal);
      item.status = "done";
      item.fileId = res.id;
    } catch (err) {
      item.status = "error";
      item.error = err.detail || err.message;
      throw new Error(`附件「${item.name}」上传失败：${item.error}`);
    }
  }
  return files.map((f) => f.fileId);
}

function inputCount(agent) {
  return Object.keys(agent.prefilled_inputs || {}).length;
}

// 预填值紧凑渲染：标量直显（值恒在可见 DOM 文本流——诚实地板 + m6 e2e 锚
// top_event/供电完全丧失 不依赖点击）；对象/数组回退单行 JSON。
function formatDraftVal(v) {
  return v !== null && typeof v === "object" ? JSON.stringify(v) : String(v);
}

function executionStatusText(execution) {
  if (execution?.status === "dispatched") return "已自动发起，无需手动创建";
  if (execution?.status === "blocked_input") return "还缺输入，暂未执行";
  if (execution?.status === "blocked_source") return "来源边界未满足，暂未执行";
  if (execution?.status === "blocked_policy") return "超出自动执行范围，暂未执行";
  if (execution?.status === "blocked_conflict") return "计划存在冲突，暂未执行";
  return "暂未自动执行";
}

function planAgents(plan) {
  return guidePlanAgents(plan);
}

function focusComposer() {
  // 逃生行：只聚焦并滚到既有输入框，绝不读写 draft——调整方案仍由用户在
  // composer 里亲手打字表达，导引不代写。
  const el = document.querySelector(".composer-input textarea");
  if (!el) return;
  el.focus();
  el.scrollIntoView({ behavior: "smooth", block: "center" });
}

// ── Agent 选择器（范式 2b：门户降级为 composer 内浏览）──
// 只列可被召集的执行型 Agent（过滤 disabled 与 interactive——导引自己不列
// 自己）；点选只填草稿+聚焦，人自己描述需求再发送。
const pickAgents = ref([]);
const pickAgentsError = ref("");
onMounted(async () => {
  try {
    const list = await listAgents();
    pickAgents.value = (list || []).filter((a) => a.status !== "disabled" && a.mode !== "interactive");
  } catch (err) {
    pickAgentsError.value = err.detail || err.message || "Agent 列表加载失败";
  }
});
function pickAgent(a) {
  draft.value = `我想用「${a.name}」做：`;
  focusComposer();
}

function adoptReframe(text) {
  // Codex 问题卡哲学：点一条重述建议只是把它填进草稿并聚焦输入框，人仍要
  // 自己按发送——导引绝不代人发起这条消息（红线：人是唯一发起者）。
  draft.value = text;
  focusComposer();
}

async function scrollToBottom() {
  // 会话流走自然页面流（不再是内嵌定长滚动框）——把最新一条滚到视口顶部起读，
  // 让高高的协作方案卡从「目标句」开始展开，而不是被塞进 62vh 的小盒里。
  await nextTick();
  const last = streamEl.value && streamEl.value.lastElementChild;
  if (last) last.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function send() {
  // 会话恢复在途不收发言；concluded/未知状态硬守卫零 POST。
  // 即使 disabled 控件被 DOM 篡改或程序触发，也不得穿透到 API。
  if (sending.value || restoring.value || conversationReadOnly.value) return;
  const content = draft.value.trim();
  if (!content) return;

  // 一轮发送必须锁定它开始时的页面代际、目标会话与附件集合。GuidePage 会在
  // ?c 切换时复用组件实例；任何 await 之后都不能再从响应式全局状态“现取”目标，
  // 否则旧会话的附件/消息/计划可能串进新会话。
  const sendLoadEpoch = conversationLoadEpoch;
  const initialConversationId = conversationId.value;
  const sendFiles = [...pendingFiles.value];
  const attachmentIntent = attachmentIntentForFiles(sendFiles);
  const sendUiToken = ++sendUiEpoch;
  let targetConversationId = initialConversationId;
  const sendOperation = {
    originatedFresh: !targetConversationId,
    targetConversationId,
    content,
    files: sendFiles,
    attachmentIntent,
    requestId: retryTurn?.requestId || null,
    fingerprint: null,
    outboxPreflightFailed: false,
  };
  if (targetConversationId) {
    failedSends.delete(targetConversationId);
    bindInFlightSend(sendOperation, targetConversationId);
  } else {
    failedFreshSend = null;
    freshInFlightSend = sendOperation;
  }
  let sendSettled = false;
  pageError.value = "";

  // 乐观追加用户气泡（附件 chips 一并显示；失败整体回滚）
  const optimisticAttachments = sendFiles.map((f) => ({ id: f.uid, filename: f.name }));
  const optimisticMessage = {
    role: "user",
    content,
    attachments: optimisticAttachments.length ? optimisticAttachments : undefined,
    // fresh：仅本次会话中「刚落地」的气泡播墨迹入场；历史加载不带此标记——
    // 诚实地板：不让三天前的旧对话表演"刚发生"（信任镜头 P2）。
    fresh: true,
  };
  messages.value.push(optimisticMessage);
  draft.value = "";
  sending.value = true;
  try {
    await scrollToBottom();
    // safe_auto 前紧贴请求重读服务端身份，避免另一标签页换 cookie 后本页仍拿旧
    // currentUser 生成 outbox principal。身份 GET 失败/漂移时附件与会话 POST 均为零。
    if ((await fetchMe()) !== true) {
      throw new Error("无法确认当前认证身份，已禁止自动执行");
    }
    const principal = authenticatedPrincipal();
    if (!principal) throw new Error("认证身份缺少 username/role，已禁止自动执行");
    // 未知结果重试必须先验证 durable outbox；记录缺失/坏版本/主体、路由、正文或
    // 附件漂移时，在上传和任一会话 POST 之前 fail-closed，绝不旋转 request_id。
    const durableRetry = preflightDurableRetry(principal, sendOperation);
    const requestId = durableRetry
      ? durableRetry.request_id
      : isCurrentSendUi(sendUiToken, sendLoadEpoch, targetConversationId)
      ? turnRequestId(content, attachmentIntent)
      : newTurnRequestId();
    sendOperation.requestId = requestId;
    sendOperation.fingerprint = JSON.stringify([content, attachmentIntent]);
    if (!durableRetry) {
      // 真正的版本化发送意图必须先写入正式 outbox key 并回读，再允许附件 POST。
      // 此时只持久化不可变附件描述；服务端 file_id 在上传完成后一次绑定。
      try {
        guideSafeAutoOutbox.prepareUploads(principal, {
          requestId,
          agentId: GUIDE_AGENT_ID,
          conversationId: targetConversationId || null,
          content,
          attachmentIntent,
        });
      } catch (error) {
        sendOperation.outboxPreflightFailed = true;
        throw error;
      }
    }
    // 已 done 的附件跳过；其余上传都带持久化主体快照，任一失败即中止消息。
    const fileIds = await uploadPendingFiles(sendFiles, principal);
    guideSafeAutoOutbox.completeUploads(principal, requestId, {
      fileIds,
      files: sendFiles.map((file) => ({ id: file.fileId, name: file.name })),
    });
    const dispatched = await dispatchGuideSafeAutoIntent({
      outbox: guideSafeAutoOutbox,
      principal,
      intent: {
        requestId,
        agentId: GUIDE_AGENT_ID,
        conversationId: targetConversationId || null,
        content,
        fileIds,
        // 只持久化服务端 file id 与显示名；raw File 永不进入 sessionStorage。
        files: sendFiles.map((file) => ({ id: file.fileId, name: file.name })),
        attachmentIntent,
      },
      createConversation: ({ agentId, requestId: createRequestId, expectedPrincipal }) =>
        createConversation({ agentId, requestId: createRequestId, expectedPrincipal }),
      postMessage: ({ conversationId: id, content: body, fileIds: ids, requestId: idempotencyKey, expectedPrincipal }) =>
        postMessage(id, body, ids, {
          executionMode: "safe_auto",
          requestId: idempotencyKey,
          expectedPrincipal,
        }),
      getConversation,
      onConversationBound: async (boundConversationId) => {
        if (targetConversationId) return;
        targetConversationId = boundConversationId;
        bindInFlightSend(sendOperation, targetConversationId);
        // 全新会话在 create await 期间若已切走，仍完成已持久化意图，但绝不夺回
        // 当前 URL/UI；仍停留原页面时才接管为当前会话。
        if (isCurrentSendUi(sendUiToken, sendLoadEpoch, initialConversationId)) {
          conversationId.value = targetConversationId;
          conversationStatus.value = "active";
          started.value = true;
          internalConversationNavigation = targetConversationId;
          const clearInternalNavigation = () => {
            if (internalConversationNavigation === targetConversationId) {
              internalConversationNavigation = null;
            }
          };
          try {
            await router.replace({ path: "/", query: { c: targetConversationId } });
          } finally {
            clearInternalNavigation();
          }
          if (routeConversationId.value !== targetConversationId) {
            throw new Error("新会话 URL 绑定失败，已保留 outbox 且未发送消息");
          }
        }
      },
    });
    const res = dispatched.response;
    outboxRecoveryBlocked.value = false;
    releaseInFlightSend(sendOperation);
    sendSettled = true;
    failedSends.delete(targetConversationId);
    const replayed =
      res.execution?.replayed === true ||
      res.message?.recommendation?.execution?.replayed === true;
    if (replayed) {
      // 幂等回放说明权威消息已经在服务端历史中；本地乐观气泡若再 append 会重影。
      // 当前仍看目标会话时整包重读，离开目标时等下一次正常恢复即可。
      if (isViewingConversation(targetConversationId)) await loadConversation(targetConversationId);
      return;
    }
    if (!isCurrentSendUi(sendUiToken, sendLoadEpoch, targetConversationId)) {
      // A→B→A：若旧 POST 结算时 URL 又回到 A，必须在 POST 之后重新读取服务端
      // 权威历史。这样即使先前的 A GET 早于 POST，也不会展示“尚未发送”诱导重复执行。
      if (isViewingConversation(targetConversationId)) await loadConversation(targetConversationId);
      return;
    }

    // 成功：附件已随消息落库，清空待发区；气泡 chips 换用真实文件 id
    if (optimisticAttachments.length) {
      optimisticMessage.attachments = sendFiles.map((f) => ({ id: f.fileId, filename: f.name }));
    }
    const sentFiles = new Set(sendFiles);
    pendingFiles.value = pendingFiles.value.filter((f) => !sentFiles.has(f));
    if (retryTurn?.requestId === requestId) retryTurn = null;
    messages.value.push({
      role: "assistant",
      content: res.message.content,
      recommendation: res.message.recommendation || null,
      fresh: true,
      createdAt: res.message.created_at || null,
    });
    await scrollToBottom();
    if (isCurrentSendUi(sendUiToken, sendLoadEpoch, targetConversationId)) {
      ensureConversationTasksFeed(); // 本轮若刚给出 orchestrate 方案，开始为其召集状态保鲜
    }
  } catch (err) {
    // 本轮失败：后端契约是「失败零落库」（幂等重试，ADR-0013），本地同样回滚
    // 乐观气泡并把原文还原到输入框——不在界面上留一条服务端不存在的幽灵消息，
    // 重试也不会堆出重复 user 气泡（Codex R1-P2）。附件 chips 留在待发区
    // （已上传项带 fileId，重试不重复上传）。不伪造 assistant 回复。
    releaseInFlightSend(sendOperation);
    sendSettled = true;
    // Persisted + exact + same-route failures are safe to retry in place with the same
    // request_id. Only unreadable/missing/mismatched durable state locks the composer.
    outboxRecoveryBlocked.value =
      sendOperation.outboxPreflightFailed || !failedSendMatchesCurrentOutbox(sendOperation);
    rememberFailedSend(sendOperation, err);
    if (!isCurrentSendUi(sendUiToken, sendLoadEpoch, targetConversationId)) {
      // 若用户已回到目标会话，恢复原草稿/附件与稳定 request_id；若该会话仍在
      // GET 恢复途中，loadConversation 落地后会从 failedSends 做同一恢复。
      if (isViewingConversation(targetConversationId)) {
        restoreConversationSendState(targetConversationId);
      }
      return;
    }
    const optimisticIndex = messages.value.indexOf(optimisticMessage);
    if (optimisticIndex >= 0) messages.value.splice(optimisticIndex, 1);
    draft.value = content;
    pageError.value = err.detail || err.message;
  } finally {
    if (!sendSettled) releaseInFlightSend(sendOperation);
    if (isCurrentSendUi(sendUiToken, sendLoadEpoch, targetConversationId)) {
      sending.value = false;
    } else if (isViewingConversation(targetConversationId) && !inFlightSends.has(targetConversationId)) {
      sending.value = false;
    } else if (!routeConversationId.value && !freshInFlightSend) {
      sending.value = false;
    }
  }
}

function collectCarriedFiles() {
  // 会话里发送成功的附件（真实 fileId）去重收集——随草案带入创建页。
  // 成功气泡按构造只含真实 fileId（失败气泡已回滚、成功时 chips 已换真 id）。
  const carried = [];
  const seen = new Set();
  for (const m of messages.value) {
    if (m.role !== "user" || !m.attachments) continue;
    for (const a of m.attachments) {
      if (a.id && !seen.has(a.id)) {
        seen.add(a.id);
        carried.push({ id: a.id, name: a.filename });
      }
    }
  }
  return carried;
}

function openWorkbench() {
  // 进入本次会话的协作工作台（分工架构 + 逐个召集 + 进度）。不归档会话——
  // 工作台里还要继续从蓝图召集 Agent；会话作协作锚点保持存续。
  if (conversationId.value) {
    router.push(`/workbench/${conversationId.value}`);
  }
}

function createOneTask(agent, plan) {
  if (conversationStatus.value !== "active") {
    pageError.value = "会话已归档或状态未知，只读历史禁止继续创建任务";
    return;
  }
  // 人确认接缝：把某个被召集 Agent 的预填草案交给创建任务页，由人补全后亲手
  // 提交（导引绝不代签）。走 sessionStorage 而非 URL，避免工程数据进查询串。
  // M7：会话附件随草案带走，创建页以「已上传」状态入列，人可移除。
  // 单 Agent 计划：确认后应归档会话（保留 M6「一次会话=一个任务」语义）。但归档必须
  // **后于任务创建成功**——异源 Codex R2-#3：会话 concluded 后 API 真只读拒新任务，若
  // 沿用旧的「先 fire-and-forget 归档、再跳创建页」，创建时会话已 concluded → 创建被 409
  // 打回。故这里不再先归档，只在草案里带 conclude_after 标记，由创建页在提交成功后归档。
  const isSingleAgent = planAgents(plan).length === 1 && !!conversationId.value;
  sessionStorage.setItem(
    "flai_prefill",
    JSON.stringify({
      agent_id: agent.agent_id,
      inputs: agent.prefilled_inputs || {},
      files: collectCarriedFiles(),
      // M8：带上会话 id——创建的任务归到本次导引协作会话下（协作工作台按会话聚合）。
      conversation_id: conversationId.value || null,
      // 单 Agent：创建页提交成功后再归档本会话（多 Agent 由工作台「结束协作」显式归档）。
      conclude_after: isSingleAgent,
    })
  );
  // back=chat（范式 2a 对话轴闭环）：从导引来的创建，提交成功后回流本会话——
  // 任务卡在对话流里原地亮起，不再把人甩到详情页（跳页=范式失败标志）。
  // WorkbenchSession 的召集不带此参数，保持跳详情（m8_collab_chain e2e 契约不动）。
  router.push({ path: "/tasks/new", query: { agent_id: agent.agent_id, from: "guide", back: "chat" } });
}

// ── B1 对话轴督战（UI-PARADIGM.md 祈使句①）──────────────────────────────
// orchestrate 方案卡的每个 agent-card 内联该会话真实任务状态：只在本会话已为
// 该 agent_id 召集过任务时渲染 chip（诚实地板，未召集零占位）；点「速览 →」
// 直开任务速览（openTaskPeek），渐进披露不逼人跳页。只在会话真出现 orchestrate
// 方案时才订阅，改并轨 liveFeed 'conversation:<id>' channel（批A Task 6）——
// GuidePage 组件实例跨会话复用（App.vue router-view :key 对 query 变化不重挂
// 载，见该文件注释），故不能像 WorkbenchSession 那样在 setup 顶层一次性
// acquire，需按当前目标（有无 orchestrate 方案 × 当前 conversationId）
// watch-diff acquire/release，同 StatusCenter.vue 的 ensurePeekLoaded 姿势。
const conversationTasks = ref([]);
let convTasksHandle = null;
let convTasksStop = null;
let convTasksHandleFor = null; // 当前持有订阅所属的 conversationId（null=未订阅）
let feedDisposed = false; // 组件已卸载：拒绝 await 续体的迟到 acquire（Codex R2-P1）

function hasOrchestratePlan() {
  return messages.value.some(
    (m) => m.role === "assistant" && m.recommendation && m.recommendation.decision === "orchestrate"
  );
}

function isWorkState(status) {
  return TASK_WORK_STATES.has(status);
}

// DAG 只能依赖 execution.node_tasks 的 node_id → task_id 权威映射；legacy 才允许
// agent_id 分组。任一映射不完整时整张图不关联任务，避免把同 Agent 的其它任务
// 冒充成本轮节点。后端按 created_at DESC, id DESC 返回，legacy 多任务沿用该顺序。
function planTaskIndex(plan) {
  return indexGuidePlanTasks(plan, conversationTasks.value);
}

function planTaskMappingIssue(plan) {
  return guidePlanTaskMappingIssue(plan, conversationTasks.value);
}

function agentTaskInfo(agent, plan) {
  const index = indexGuidePlanTasks(plan, conversationTasks.value);
  const list = tasksForGuidePlanAgent(index, agent);
  if (!list.length) return null;
  return { latest: list[0], extra: list.length - 1 };
}

function releaseConversationTasksFeed() {
  if (convTasksStop) {
    convTasksStop();
    convTasksStop = null;
  }
  if (convTasksHandle) {
    convTasksHandle.release();
    convTasksHandle = null;
  }
  convTasksHandleFor = null;
  conversationTasks.value = [];
}

// 只在真出现 orchestrate 方案时订阅（幂等：目标未变则不重新 acquire；目标
// 变化——含「离开该会话」的 null——先 release 旧的再 acquire 新的，防止同屏
// 挂两条 conversation channel）。channel 落地的 memberTasks 直接镜射到本地
// conversationTasks，陈旧响应作废由 channel 自身的 epoch guard 承接，不需要
// 本组件再比对 convId。
function ensureConversationTasksFeed() {
  // 卸载后拒绝迟到订阅（Codex R2-P1 verbatim）：postMessage/getConversation 的
  // await 续体可能在组件卸载后才走到这里——那时唯一的 onUnmounted release 已
  // 执行过，再 acquire 的 channel 将无人释放，泄漏成 tab 级 5s 常驻轮询。
  if (feedDisposed) return;
  const id = hasOrchestratePlan() ? conversationId.value : null;
  if (id === convTasksHandleFor) return;
  if (convTasksHandleFor) releaseConversationTasksFeed();
  if (!id) return;
  convTasksHandleFor = id;
  convTasksHandle = acquireChannel(`conversation:${id}`);
  convTasksStop = watch(
    convTasksHandle.state.memberTasks,
    (v) => {
      if (convTasksHandleFor === id) conversationTasks.value = v;
    },
    { immediate: true }
  );
}

// ── 会话恢复（左栏历史点击 / 刷新 /?c=<id>）──
function resetToFresh(clearError = true) {
  invalidateSendUi();
  messages.value = [];
  started.value = false;
  conversationId.value = "";
  conversationStatus.value = "";
  draft.value = "";
  pendingFiles.value = [];
  retryTurn = null;
  releaseConversationTasksFeed();
  if (clearError) pageError.value = "";
}

// 恢复在途标记：?c 深链（含 2a 回流）落地时 getConversation 在途的窗口里，
// 不渲染可交互的空态 hero（「假起手」）、send 早退——否则此刻发消息会因
// conversationId 尚空而意外新建会话（双镜头 P2 实审咬出的竞态）。
const restoring = ref(false);
let conversationLoadEpoch = 0;

function isCurrentConversationLoad(epoch, targetId) {
  return (
    epoch === conversationLoadEpoch &&
    typeof route.query.c === "string" &&
    route.query.c === targetId
  );
}

async function loadConversation(id) {
  // GuidePage 实例会跨 ?c 复用；每次恢复都领取新 epoch，只允许
  // 「最后一次请求 + URL 当前目标」写入状态。过期响应连 restoring
  // 也不得清除，否则会提前打开新目标会话的 composer。
  const targetId = id;
  const epoch = ++conversationLoadEpoch;
  const fallbackMessages = conversationId.value === targetId ? [...messages.value] : [];
  resetToFresh();
  restoring.value = true;
  try {
    const conv = await getConversation(targetId);
    if (!isCurrentConversationLoad(epoch, targetId)) return;
    if (!conv || conv.id !== targetId) {
      pageError.value = "会话响应与当前目标不一致";
      return;
    }
    conversationId.value = conv.id;
    conversationStatus.value = conv.status || "";
    started.value = true;
    messages.value = (conv.messages || []).map((m) => ({
      role: m.role,
      content: m.content,
      recommendation: m.recommendation || null,
      attachments: m.attachments && m.attachments.length ? m.attachments : undefined,
      createdAt: m.created_at || null,
    }));
    clearFailedSendIfCommitted(targetId, messages.value);
    restoreConversationSendState(targetId);
    await scrollToBottom();
    if (!isCurrentConversationLoad(epoch, targetId)) return;
    ensureConversationTasksFeed(); // 恢复的历史会话若已带 orchestrate 方案，立即接上订阅
  } catch (err) {
    if (!isCurrentConversationLoad(epoch, targetId)) return;
    // URL 已明确指向 targetId 时，失败态也保留其身份并标记 status unknown。
    // 这样 composer 继续 fail-closed，而不会把目标会话误当成可新建的 fresh 页面。
    conversationId.value = targetId;
    conversationStatus.value = "";
    started.value = true;
    messages.value = fallbackMessages;
    pageError.value = err.detail || err.message || "会话加载失败";
  } finally {
    if (isCurrentConversationLoad(epoch, targetId)) restoring.value = false;
  }
}

async function keepOutboxBlockedAndLoadRoute(errorText) {
  restoring.value = false;
  outboxRecoveryActive.value = false;
  const targetId = routeConversationId.value;
  if (targetId) await loadConversation(targetId);
  pageError.value = pageError.value ? `${errorText}；${pageError.value}` : errorText;
  return true;
}

async function resumePersistedGuideTurn() {
  const hasRecord = hasPendingGuideOutbox();
  if (!hasRecord) return false;

  // App 身份门只会在 /me 完成后挂载页面；这里仍做防御纵深，username/role 任一
  // 缺失都不读取意图、更不发网络请求。
  outboxRecoveryBlocked.value = true;
  outboxRecoveryActive.value = true;
  restoring.value = true;
  if ((await fetchMe()) !== true) {
    pageError.value = "无法向服务端确认当前身份，待恢复自动执行已被锁定";
    restoring.value = false;
    outboxRecoveryActive.value = false;
    return true;
  }
  const principal = authenticatedPrincipal();
  if (!principal) {
    pageError.value = "认证身份缺少 username/role，待恢复自动执行已被锁定";
    restoring.value = false;
    outboxRecoveryActive.value = false;
    return true;
  }

  let visibleRecord = null;
  try {
    visibleRecord = guideSafeAutoOutbox.loadForPrincipal(principal);
    if (visibleRecord) {
      const routeId = routeConversationId.value;
      if (
        routeId &&
        (visibleRecord.conversation_id === null || visibleRecord.conversation_id !== routeId)
      ) {
        return keepOutboxBlockedAndLoadRoute(
          "当前 URL 会话与待恢复 safe_auto 意图不一致，已锁定且未发起任何恢复 POST",
        );
      }
      draft.value = visibleRecord.payload.content;
      pendingFiles.value = filesFromGuideSafeAutoRecord(visibleRecord).map((file) => reactive(file));
      retryTurn = {
        fingerprint: JSON.stringify([
          visibleRecord.payload.content,
          visibleRecord.attachment_intent.map((entry) => ({
            token: entry.token,
            name: entry.name,
            sizeBytes: entry.size_bytes,
            mimeType: entry.mime_type,
            lastModified: entry.last_modified,
          })),
        ]),
        requestId: visibleRecord.request_id,
      };
    }
  } catch (err) {
    // sessionStorage 不可读、坏版本、主体漂移都禁止恢复 POST，但不应连安全的
    // 权威 GET 也一并吞掉：深链会话仍可只读展示，composer 继续由 outbox 锁封闭。
    return keepOutboxBlockedAndLoadRoute(err.message || "待恢复自动执行记录非法");
  }

  const result = await recoverGuideSafeAutoOutbox({
    outbox: guideSafeAutoOutbox,
    principal,
    createConversation: ({ agentId, requestId, expectedPrincipal }) =>
      createConversation({ agentId, requestId, expectedPrincipal }),
    postMessage: ({ conversationId: id, content, fileIds, executionMode, requestId, expectedPrincipal }) =>
      postMessage(id, content, fileIds, { executionMode, requestId, expectedPrincipal }),
    getConversation,
    onConversationBound: async (boundConversationId, record) => {
      visibleRecord = record;
      const routeId = routeConversationId.value;
      if (routeId && routeId !== boundConversationId) {
        throw new Error("当前 URL 会话与待恢复 safe_auto 会话不一致，已禁止后台重放");
      }
      if (!routeId) {
        internalConversationNavigation = boundConversationId;
        const clearInternalNavigation = () => {
          if (internalConversationNavigation === boundConversationId) {
            internalConversationNavigation = null;
          }
        };
        try {
          await router.replace({ path: "/", query: { c: boundConversationId } });
        } finally {
          clearInternalNavigation();
        }
        if (routeConversationId.value !== boundConversationId) {
          throw new Error("待恢复会话 URL 绑定失败，已禁止消息重放");
        }
      }
    },
  });

  outboxRecoveryActive.value = false;
  restoring.value = false;
  if (result.status === "confirmed") {
    outboxRecoveryBlocked.value = false;
    pendingFiles.value = [];
    retryTurn = null;
    pageError.value = "";
    const targetId = result.record?.conversation_id || visibleRecord?.conversation_id;
    const currentRouteId = routeConversationId.value;
    if (targetId && currentRouteId === targetId) {
      await loadConversation(targetId);
    } else if (currentRouteId) {
      await loadConversation(currentRouteId);
    } else {
      resetToFresh();
    }
    return true;
  }

  // 权威 GET 失败、409、主体/版本异常都保留 outbox 并锁 composer。若会话已
  // CAS 绑定，URL/页面也锚定该会话；绝不退回“新对话”诱导用户换 request_id。
  const retained = result.record || visibleRecord;
  if (retained?.conversation_id) {
    conversationId.value = retained.conversation_id;
    conversationStatus.value = "";
    started.value = true;
  }
  pageError.value =
    result.error?.detail ||
    result.error?.message ||
    "待恢复自动执行尚未获得服务端权威确认，记录已保留";
  return true;
}

onMounted(async () => {
  if (await resumePersistedGuideTurn()) return;
  const c = route.query.c;
  if (typeof c === "string" && c) loadConversation(c);
  else restoreFreshSendState();
});
onUnmounted(() => {
  conversationLoadEpoch++; // 作废所有 await 中的恢复续体
  feedDisposed = true; // 先封门再释放：卸载后任何 await 续体不得再 acquire
  releaseConversationTasksFeed();
});

// 左栏切换会话 / 点「新对话」→ 据 ?c 变化恢复或重置（跳过刚创建的本会话，避免回灌）。
watch(
  () => route.query.c,
  (c) => {
    if (outboxRecoveryActive.value) return;
    if (typeof c === "string" && c) {
      if (c !== conversationId.value) loadConversation(c);
    } else {
      // 「新对话」或移除 ?c 同样是新目标：即使旧请求尚在途也要立即作废。
      conversationLoadEpoch++;
      restoring.value = false;
      if (started.value || messages.value.length || sending.value) resetToFresh();
      restoreFreshSendState();
    }
  }
);
</script>

<style scoped>
.guide-page {
  max-width: 784px;
  margin: 0 auto;
  padding-bottom: 178px; /* 让会话内容避开固定悬浮 composer（含常驻诚实地板句一行） */
}
/* 空状态：hero + composer 作为一组在视口垂直居中（Claude 起手布局）。*/
.guide-page.is-empty {
  padding-bottom: 0;
  min-height: 72vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

/* ── 起手 hero ── */
.guide-hero {
  text-align: center;
  padding: 40px 12px 30px;
  /* 入场动效走全局 .fx-rise（模板上加类）：起手 hero 只在「零消息」落地态渲染
   * 一次=真「刚落地」无需门控；用全局类天然继承 App.vue 的 reduced-motion
   * 降级（双镜头审合流 finding——本地 animation 没有降级覆盖，已迁移根治）。 */
}
.hero-mark {
  width: 46px;
  height: 46px;
  border-radius: 14px;
  margin: 0 auto 20px;
  display: grid;
  place-items: center;
  color: #fff;
  font-weight: 800;
  font-size: 21px;
  background: linear-gradient(150deg, var(--clay), var(--clay-deep));
  box-shadow: 0 6px 18px rgba(var(--clay-rgb), 0.28);
}
/* 时段感问候：抒情场合走衬线，字号克制小于主标题，颜色降一级不抢戏。 */
.hero-greeting {
  font-family: var(--serif);
  font-size: 15px;
  font-weight: 500;
  color: var(--ink-soft);
  margin: 0 0 8px;
}
.hero-title {
  font-family: var(--serif);
  font-size: 30px;
  font-weight: 600;
  color: var(--ink);
  margin: 0 0 14px;
  letter-spacing: 0.3px;
}
/* 四意图卡：≥520px 宽 2×2，窄屏 1 列（原 hero-examples/ex-chip 原地升级）。 */
.hero-intents {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
  margin-top: 26px;
  text-align: left;
}
@media (min-width: 520px) {
  .hero-intents {
    grid-template-columns: 1fr 1fr;
  }
}
.intent-card {
  display: flex;
  gap: 12px;
  background: var(--surface-raised);
  border: 1px solid var(--hairline);
  border-radius: 14px;
  padding: 14px 16px;
  cursor: pointer;
  box-shadow: var(--shadow-card);
  transition: transform var(--motion-fast) var(--ease-out-soft), box-shadow var(--motion-fast) var(--ease-out-soft);
}
.intent-card:hover,
.intent-card:focus-visible {
  transform: translateY(-1px);
  box-shadow: var(--shadow-card-hover);
}
.intent-card:focus-visible {
  outline: 2px solid var(--clay-softer);
  outline-offset: 1px;
}
.intent-accent {
  flex: 0 0 auto;
  width: 3px;
  border-radius: 3px;
}
.intent-body { flex: 1 1 auto; min-width: 0; }
.intent-title {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 13.5px;
  font-weight: 700;
  color: var(--ink);
  margin-bottom: 4px;
}
.intent-example {
  font-size: 12.5px;
  color: var(--ink-soft);
  margin: 0;
  line-height: 1.5;
}
@media (prefers-reduced-motion: reduce) {
  .intent-card { transition: none; }
}

.page-alert {
  margin-bottom: 14px;
}

/* ── 会话流 ── */
.thread {
  display: flex;
  flex-direction: column;
  gap: 30px;
  padding: 20px 2px 8px;
}

.bubble-row { display: flex; scroll-margin-top: 84px; }
.bubble-row.user { justify-content: flex-end; }
.bubble-row.assistant { justify-content: flex-start; }

/* 用户气泡：靠右，暖 clay 淡底 */
.user-bubble {
  max-width: 76%;
  background: var(--bubble-user-bg);
  border: 1px solid var(--bubble-user-border);
  color: var(--bubble-user-ink);
  padding: 12px 16px;
  border-radius: 18px 18px 4px 18px;
  box-shadow: var(--shadow-card);
  /* 入场动效交给全局 .fx-ink-in（墨迹晕开，见 App.vue）——本地 rise 动画让位，
   * 避免 scoped 选择器特异度盖过全局工具类导致新类无效播放。 */
}
.user-text {
  white-space: pre-wrap;
  font-size: 15px;
  line-height: 1.55;
}
.user-files {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
/* 悬浮时间戳：静止态隐去，hover 整行气泡才渐显（历史消息/新回合皆可能无
 * createdAt——user 乐观推送不带时间戳，v-if 已兜底不渲染空占位）。 */
.bubble-time {
  opacity: 0;
  font-size: 11px;
  color: var(--ink-faint);
  transition: opacity var(--motion-fast) var(--ease-out-soft);
}
.bubble-row:hover .bubble-time { opacity: 1; }
.user-bubble .bubble-time {
  display: block;
  margin-top: 6px;
  text-align: right;
}
@media (prefers-reduced-motion: reduce) {
  .bubble-time { transition: none; }
}

/* 助手：小 mark + 流动排版 */
.bubble-row.assistant { gap: 14px; }
.ai-mark {
  flex: 0 0 auto;
  width: 30px;
  height: 30px;
  border-radius: 9px;
  margin-top: 2px;
  display: grid;
  place-items: center;
  color: var(--clay);
  font-weight: 800;
  font-size: 14px;
  background: var(--surface-raised);
  border: 1px solid var(--hairline);
  box-shadow: var(--shadow-card);
}
.ai-body {
  flex: 1 1 auto;
  min-width: 0;
  max-width: calc(100% - 44px);
}
.ai-name {
  font-size: 12.5px;
  color: var(--ink-faint);
  font-weight: 600;
  letter-spacing: 0.3px;
  margin-bottom: 7px;
}
.ai-name .bubble-time {
  margin-left: 8px;
  font-weight: 500;
  letter-spacing: normal;
}
.ai-lead {
  font-size: 15px;
  line-height: 1.72;
  color: var(--ink);
  margin: 0 0 16px;
  white-space: pre-wrap;
}

/* 思考指示 */
.ai-thinking {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--ink-faint);
  font-size: 13.5px;
}
.ai-thinking .tlabel { margin-left: 6px; }

/* ── 协作方案 / 拒绝 卡片 ── */
.plan-card {
  background: var(--surface-raised);
  border: 1px solid var(--hairline);
  border-radius: 18px;
  padding: 22px 24px 20px;
  box-shadow: var(--shadow-card);
  /* 入场动效交给全局 .fx-rise（见 App.vue）——本地 rise 动画让位，理由同 .user-bubble。 */
}
.plan-card.refuse {
  background: var(--refuse-card-bg);
  border-color: var(--refuse-card-border);
}
.plan-topline {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.plan-kicker {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1.4px;
  text-transform: uppercase;
  color: var(--clay);
}
.plan-kicker.refuse { color: var(--trust-pending); margin-bottom: 10px; display: inline-block; }
.plan-count {
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-soft);
  background: var(--paper-rail);
  border: 1px solid var(--hairline);
  border-radius: 999px;
  padding: 2px 10px;
}
.execution-strip {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: -2px 0 16px;
  padding: 9px 11px;
  border: 1px solid var(--border-clay-soft);
  border-radius: 10px;
  background: var(--clay-soft);
  color: var(--clay-deep);
  font-size: 12px;
  line-height: 1.45;
}
.execution-strip.blocked {
  border-color: rgba(var(--trust-pending-rgb), 0.35);
  background: rgba(var(--trust-pending-rgb), 0.08);
  color: var(--trust-pending);
}
.execution-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--clay);
  flex: none;
}
.execution-strip.blocked .execution-dot { background: var(--trust-pending); }
.execution-title { font-weight: 750; }
.execution-detail { color: var(--ink-soft); }
.plan-goal-title {
  font-family: var(--serif);
  font-size: 24px;
  line-height: 1.36;
  color: var(--ink);
  font-weight: 600;
  margin: 0 0 16px;
  letter-spacing: 0.2px;
}
.plan-goal-title.small { font-size: 20px; margin-bottom: 12px; }
.plan-reason {
  font-size: 14px;
  line-height: 1.7;
  color: var(--ink-soft);
  margin: 0 0 16px;
}
.plan-section { margin: 0 0 16px; }
.roster-label { margin-top: 4px; }
.plan-workflow {
  margin: 0;
  color: var(--ink-mid);
  font-size: 13.5px;
  line-height: 1.65;
}
.plan-list {
  margin: 0;
  padding-left: 20px;
  color: var(--ink-mid);
  font-size: 13.5px;
  line-height: 1.75;
}

/* 重述建议 → 可点编号选项（Codex 问题卡哲学）：点一条只填草稿+聚焦输入框，
 * 绝不代人发送。序号圈用 clay（行动召唤语义，信任色锁合规）。 */
.reframe-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.reframe-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 11px;
  border-radius: 10px;
  border: 1px solid transparent;
  cursor: pointer;
  transition: background-color var(--motion-fast) var(--ease-out-soft), border-color var(--motion-fast) var(--ease-out-soft);
}
.reframe-item:hover,
.reframe-item:focus-visible {
  background: var(--paper-rail);
  border-color: var(--hairline-soft);
}
.reframe-item:focus-visible {
  outline: 2px solid var(--clay-softer);
  outline-offset: 1px;
}
.reframe-num {
  flex: 0 0 auto;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 11px;
  font-weight: 800;
  color: var(--clay);
  background: var(--clay-soft);
  border: 1.5px solid var(--clay);
}
.reframe-text {
  flex: 1 1 auto;
  color: var(--ink-mid);
  font-size: 13.5px;
  line-height: 1.6;
}
.reframe-adopt {
  flex: 0 0 auto;
  font-size: 12px;
  font-weight: 700;
  color: var(--clay);
  opacity: 0;
  transform: translateX(4px);
  transition: opacity var(--motion-fast) var(--ease-out-soft), transform var(--motion-fast) var(--ease-out-soft);
}
.reframe-item:hover .reframe-adopt,
.reframe-item:focus-visible .reframe-adopt {
  opacity: 1;
  transform: translateX(0);
}
@media (prefers-reduced-motion: reduce) {
  .reframe-adopt { transition: none; transform: none; }
}
.reframe-escape {
  margin: 8px 0 0;
  color: var(--ink-faint);
  font-size: 12px;
  line-height: 1.6;
}

/* Agent roster 卡 */
.agent-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 6px;
}
.agent-card {
  display: flex;
  gap: 14px;
  align-items: stretch;
  background: var(--surface-raised);
  border: 1px solid var(--hairline-soft);
  border-radius: 14px;
  padding: 15px 16px;
  transition: transform var(--motion-fast) var(--ease-out-soft), box-shadow var(--motion-fast) var(--ease-out-soft), border-color var(--motion-fast) var(--ease-out-soft);
  /* 入场动效交给全局 .fx-rise（m.fresh 门控，见 template）——历史会话加载
   * 路径重挂载不重播「刚发生」视觉，理由同 .plan-card/.user-bubble。 */
}
.agent-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-card-hover);
  border-color: var(--border-warm-hover);
}
.agent-main { flex: 1 1 auto; min-width: 0; }
.agent-top {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.agent-name {
  font-weight: 700;
  font-size: 15px;
  color: var(--ink);
}
.agent-maturity {
  margin-left: auto;
  font-size: 11.5px;
  font-family: var(--mono, "SF Mono", ui-monospace, monospace);
  color: var(--ink-faint);
}
/* B1 对话轴督战：该会话已召集时的内联状态 chip（只在有真任务时渲染）。 */
.agent-status {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 8px;
  cursor: pointer;
}
.status-lamp {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: none;
}
.status-lamp.is-pulsing {
  animation: flai-work-pulse var(--pulse-duration) ease-in-out infinite;
}
.status-word {
  font-size: 12px;
  font-weight: 600;
}
.status-extra {
  font-size: 11px;
  font-weight: 600;
  color: var(--ink-faint);
}
.status-peek {
  font-size: 12px;
  font-weight: 700;
  color: var(--clay);
  margin-left: 2px;
  transition: color var(--motion-fast) var(--ease-out-soft);
}
.agent-status:hover .status-peek {
  color: var(--clay-deep);
}
/* amber=待人签强 CTA（信任色锁：amber 仅待审语义）——签发来找人 */
.status-peek.is-review {
  color: var(--trust-pending);
}
/* 产物锚点行：完成任务的产物直达（Claude Artifact 卡片锚点） */
.status-artifact {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 8px;
  padding: 4px 10px;
  border: 1px solid var(--hairline);
  border-radius: 8px;
  background: var(--paper-rail, var(--card-bg));
  cursor: pointer;
  color: var(--ink-soft);
  font-size: 12px;
  transition: border-color var(--motion-fast) var(--ease-out-soft), color var(--motion-fast) var(--ease-out-soft);
}
.status-artifact:hover {
  border-color: var(--clay-softer);
  color: var(--clay);
}
.artifact-icon {
  flex: none;
}
.artifact-count {
  font-weight: 600;
}
.artifact-open {
  font-weight: 700;
  color: var(--clay);
  font-size: 11.5px;
}
@media (prefers-reduced-motion: reduce) {
  .status-lamp.is-pulsing { animation: none; }
}
.agent-role {
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--ink);
  margin: 0 0 6px;
}
.role-tag {
  display: inline-block;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.4px;
  color: var(--clay);
  background: var(--clay-soft);
  border-radius: 5px;
  padding: 1px 7px;
  margin-right: 8px;
  vertical-align: 1px;
}
.agent-rationale {
  font-size: 13.5px;
  font-weight: 600;
  line-height: 1.5;
  color: var(--ink);
  margin: 0 0 6px;
}
.agent-draft { margin-bottom: 10px; }
/* 预填草案：紧凑「键 值」chip 取代 monospace JSON 大块——值恒完整可见
   （诚实地板：不截断，让人看清按此会创建什么），视觉重量大幅下降。 */
.draft-label {
  font-size: 11px;
  color: var(--ink-faint);
  margin-bottom: 5px;
}
.draft-fields {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.draft-field {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  padding: 3px 9px;
  background: var(--paper-rail);
  border: 1px solid var(--hairline-soft);
  border-radius: 7px;
  font-size: 12px;
  min-width: 0;
}
.df-key {
  flex: 0 0 auto;
  color: var(--ink-faint);
  font-weight: 600;
}
.df-val {
  color: var(--ink);
  word-break: break-word;
}
.agent-stripped {
  margin: 2px 0 10px;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--ink-soft);
}
.agent-actions { display: flex; }
.agent-cta {
  display: inline-flex;
  align-items: center;
  font-size: 13px;
  font-weight: 600;
  color: var(--clay);
  background: transparent;
  border: 1px solid var(--border-clay-soft);
  border-radius: 10px;
  padding: 8px 14px;
  cursor: pointer;
  transition: all var(--motion-fast) var(--ease-out-soft);
}
.agent-cta::after {
  content: "→";
  margin-left: 7px;
  transition: transform var(--motion-fast) var(--ease-out-soft);
}
.agent-cta:hover {
  background: var(--clay);
  color: #fff;
  border-color: var(--clay);
  box-shadow: 0 4px 12px rgba(var(--clay-rgb), 0.22);
}
.agent-cta:hover::after { transform: translateX(2px); }

.plan-alert {
  margin-top: 10px;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--ink-soft);
}

.plan-foot {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--hairline-soft);
}
.workbench-btn {
  flex: 0 0 auto;
  font-size: 13.5px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(160deg, var(--clay), var(--clay-deep));
  border: none;
  border-radius: 10px;
  padding: 9px 16px;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(var(--clay-rgb), 0.24);
  transition: transform var(--motion-fast) var(--ease-out-soft), box-shadow var(--motion-fast) var(--ease-out-soft);
}
.workbench-btn:hover { transform: translateY(-1px); box-shadow: 0 6px 16px rgba(var(--clay-rgb), 0.3); }
.plan-escape {
  flex: 0 0 100%;
  order: 1;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  text-align: left;
  background: transparent;
  border: none;
  padding: 0;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--clay);
  cursor: pointer;
  transition: color var(--motion-fast) var(--ease-out-soft), transform var(--motion-fast) var(--ease-out-soft);
}
.plan-escape:hover { color: var(--clay-deep); transform: translateX(2px); }
.plan-note {
  order: 2;
  flex: 1;
  min-width: 220px;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--ink-faint);
}
.plan-note strong { color: var(--ink-soft); font-weight: 600; }

/* 文件 chip */
.file-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--ink-soft);
  background: var(--paper-rail);
  border: 1px solid var(--hairline);
  border-radius: 8px;
  padding: 3px 9px;
}
.file-chip.error { color: var(--trust-fail); border-color: var(--error-chip-border); background: var(--error-chip-bg); }
.chip-x {
  cursor: pointer;
  color: var(--ink-faint);
  font-weight: 700;
  line-height: 1;
  padding: 0 2px;
}
.chip-x:hover { color: var(--ink); }

/* ── composer ── */
.composer { margin-top: 18px; }
/* 会话开始后：固定悬浮在视口底部，上缘渐隐让消息从下方穿过（Claude 布局）。 */
.composer.composer-fixed {
  position: fixed;
  left: var(--sidebar-w);
  right: 0;
  bottom: 0;
  z-index: 15;
  margin-top: 0;
  padding: 22px 24px 24px;
  background: linear-gradient(180deg, rgba(var(--page-bg-rgb), 0) 0%, rgba(var(--page-bg-rgb), 0.88) 42%, var(--page-bg) 74%);
  pointer-events: none;
}
@media (max-width: 860px) {
  .composer.composer-fixed { left: 0; }
}
.composer-inner {
  max-width: 784px;
  margin: 0 auto;
}
.composer.composer-fixed .composer-inner { pointer-events: auto; }
.composer-files {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
  padding: 0 4px;
}
.composer-shell {
  background: var(--surface-raised);
  border: 1px solid var(--hairline);
  border-radius: 22px;
  box-shadow: var(--shadow-composer);
  padding: 6px;
  transition: border-color var(--motion-fast) var(--ease-out-soft), box-shadow var(--motion-fast) var(--ease-out-soft);
}
.composer-shell:focus-within {
  border-color: var(--focus-ring-clay);
  box-shadow: var(--shadow-composer), 0 0 0 4px rgba(var(--clay-rgb), 0.08);
}
.composer-row {
  display: flex;
  align-items: flex-end;
  gap: 6px;
}
.composer-attach { flex: 0 0 auto; }
.icon-btn {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  border: none;
  background: transparent;
  color: var(--ink-faint);
  cursor: pointer;
  display: grid;
  place-items: center;
  transition: all var(--motion-fast) var(--ease-out-soft);
}
.icon-btn:hover:not(:disabled) { background: var(--paper-rail); color: var(--ink-soft); }
.icon-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.composer-input { flex: 1 1 auto; }
.composer-input :deep(.el-textarea__inner) {
  border: none;
  box-shadow: none;
  background: transparent;
  resize: none;
  padding: 10px 4px;
  font-family: inherit;
  font-size: 15px;
  line-height: 1.6;
  color: var(--ink);
}
.composer-input :deep(.el-textarea__inner::placeholder) { color: var(--ink-faint); }
.send-btn {
  flex: 0 0 auto;
  width: 40px;
  height: 40px;
  border-radius: 12px;
  border: none;
  cursor: pointer;
  background: linear-gradient(160deg, var(--clay), var(--clay-deep));
  color: #fff;
  display: grid;
  place-items: center;
  box-shadow: 0 4px 12px rgba(var(--clay-rgb), 0.28);
  transition: transform var(--motion-fast) var(--ease-out-soft), box-shadow var(--motion-fast) var(--ease-out-soft), opacity var(--motion-fast) var(--ease-out-soft);
}
.send-btn:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 6px 16px rgba(var(--clay-rgb), 0.34); }
.send-btn:disabled { opacity: 0.4; cursor: not-allowed; box-shadow: none; }
.send-spin {
  width: 15px; height: 15px; border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.4);
  border-top-color: #fff;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.composer-hint {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 14px 0;
  font-size: 11.5px;
  color: var(--ink-faint);
}
/* 按键提示段静止态隐去，composer 区域 hover / focus-within 时渐显——
 * 「导引不会替你创建或签发任务」政策句留在旁边常驻，不受此规则影响。 */
.composer-hint .keys {
  display: flex;
  align-items: center;
  gap: 6px;
  opacity: 0;
  transition: opacity var(--motion-fast) var(--ease-out-soft);
}
.composer-inner:hover .composer-hint .keys,
.composer-inner:focus-within .composer-hint .keys {
  opacity: 1;
}
.composer-hint .sep { color: var(--hairline); }
@media (prefers-reduced-motion: reduce) {
  .composer-hint .keys { transition: none; }
  .send-spin { animation: none; }
}

/* 诚实地板句（Claude「can make mistakes」哲学）：常驻同一 composer 容器内，
 * 会话进行中（composer 变 fixed 悬浮）也不消失；放进容器内部避免布局跳动。 */
@media (max-width: 640px) {
}
kbd {
  font-family: var(--mono);
  font-size: 10.5px;
  background: var(--paper-rail);
  border: 1px solid var(--hairline);
  border-radius: 5px;
  padding: 1px 5px;
  color: var(--ink-soft);
}

@media (max-width: 640px) {
  .ai-body { max-width: calc(100% - 44px); }
  .plan-goal-title { font-size: 21px; }
  .agent-maturity { display: none; }
}
</style>

<style>
/* Agent 选择器 popover（EP popper 渲染在 body，需全局作用域）。 */
.agent-pick-pop { padding: 10px 0 !important; }
.agent-pick .ap-title {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.5px;
  color: var(--ink-faint);
  padding: 2px 14px 8px;
}
.agent-pick .ap-error { color: var(--trust-fail); font-size: 12px; padding: 4px 14px; }
.agent-pick .ap-maturity {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--ink-mid);
  border: 1px solid var(--border-soft, var(--hairline));
  border-radius: 4px;
  padding: 0 4px;
  margin-left: 6px;
  vertical-align: 1px;
}
.agent-pick .ap-limit {
  display: block;
  font-size: 11px;
  color: var(--ink-faint);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 268px;
}
.agent-pick .ap-item {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 7px 14px;
  cursor: pointer;
}
.agent-pick .ap-item:hover { background: var(--paper-rail); }
.agent-pick .ap-dot { flex: none; width: 8px; height: 8px; border-radius: 50%; }
.agent-pick .ap-main { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.agent-pick .ap-name { font-size: 13px; font-weight: 600; color: var(--ink); }
.agent-pick .ap-sub {
  font-size: 11px;
  color: var(--ink-faint);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.agent-pick .ap-portal-link {
  display: block;
  padding: 8px 14px 2px;
  margin-top: 4px;
  border-top: 1px solid var(--hairline-soft);
  font-size: 12px;
  font-weight: 600;
  color: var(--clay);
  cursor: pointer;
}
</style>
<style>
.agent-pick .ap-zero { font-size: 12px; color: var(--ink-faint); padding: 4px 14px 8px; }
</style>
