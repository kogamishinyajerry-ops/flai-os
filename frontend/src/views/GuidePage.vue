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
      <!-- 首登三步引导（评审 N2）：只在起手空态出现；「去跑演示」只预填创建页、
           「开始说」只聚焦输入框——全程零代发零代建（人是唯一发起者）。 -->
      <OnboardingCard @demo="startDemoTask" @say="focusComposer" />
    </div>

    <el-alert
      v-if="pageError"
      type="error"
      :title="pageError"
      show-icon
      :closable="false"
      class="page-alert"
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
            <!-- 助手正文走 MarkdownLite（W5）：列表/标题/引用成块渲染——桌面级
                 富文本；纯插值零 v-html，XSS 面不变。用户气泡仍纯文本忠实显示。 -->
            <MarkdownLite v-if="m.content" :text="m.content" class="ai-lead" />

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
              <!-- 需求登记引导（评审 N6）：拒接 ≠ 需求消失。反馈通道是任务级的、挂不上
                   无任务的需求，先给「复制摘要 → 找平台负责人登记」最短闭环；接件评估
                   Agent（feat/requirement-intake-agent）合入后升级为一键登记进待办队列。 -->
              <div class="refuse-keep">
                <button type="button" class="refuse-copy" @click="copyRefusedNeed(idx)">复制需求摘要</button>
                <span class="refuse-keep-note">接不住 ≠ 不重要——复制摘要发给平台负责人登记，平台会按家底口径统一评估排期。</span>
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
                <span class="plan-count">{{ m.recommendation.agents.length }} 个 Agent 协作</span>
              </div>
              <h2 v-if="m.recommendation.goal" class="plan-goal-title">{{ m.recommendation.goal }}</h2>
              <p v-if="m.recommendation.analysis" class="plan-reason">{{ m.recommendation.analysis }}</p>
              <div v-if="m.recommendation.workflow" class="plan-section">
                <div class="section-label">分工如何衔接</div>
                <p class="plan-workflow">{{ m.recommendation.workflow }}</p>
              </div>

              <div class="section-label roster-label">召集的 Agent · {{ m.recommendation.agents.length }}</div>
              <!-- codex 式子 agent 行（owner 定向：紧凑+实时感，不要大静卡）：
                   一行一名成员——状态灯 + 名字 + 分工 + 右槽实时状态词/耗时秒表；
                   次行=实时进度旁白（运行中 shimmer 扫光，事件驱动）或未召集时的
                   预填摘要。过程可折，变更与决策必露。 -->
              <div class="agent-list">
                <div
                  v-for="(a, ai) in m.recommendation.agents"
                  :key="ai"
                  class="agent-card sa-row"
                  :class="{ 'fx-rise': m.fresh, 'is-live': !!agentTaskInfo(a) }"
                >
                  <div class="sa-head">
                    <span
                      class="status-lamp"
                      :class="{ 'is-pulsing': agentTaskInfo(a) && isWorkState(agentTaskInfo(a).latest.status) }"
                      :style="{ background: agentTaskInfo(a) ? taskLampColor(agentTaskInfo(a).latest.status) : 'var(--hairline)' }"
                    ></span>
                    <span class="agent-name">{{ a.agent_name }}</span>
                    <span v-if="a.role" class="agent-role"><span class="role-tag">分工</span>{{ a.role }}</span>
                    <span class="agent-maturity">{{ a.maturity }} / {{ a.status }}</span>
                    <span class="sa-spacer"></span>

                    <!-- 右槽①已召集：实时状态词+秒表，点击直开速览（B1 对话轴督战原语义） -->
                    <div
                      v-if="agentTaskInfo(a)"
                      class="agent-status"
                      role="button"
                      tabindex="0"
                      @click.stop="openTaskPeek(agentTaskInfo(a).latest.id)"
                      @keydown.enter.stop.prevent="openTaskPeek(agentTaskInfo(a).latest.id)"
                      @keydown.space.stop.prevent="openTaskPeek(agentTaskInfo(a).latest.id)"
                    >
                      <span class="status-word" :style="{ color: taskLampColor(agentTaskInfo(a).latest.status) }">
                        {{ statusLabel(agentTaskInfo(a).latest.status) }}
                      </span>
                      <span v-if="elapsedText(agentTaskInfo(a).latest)" class="sa-elapsed">· {{ elapsedText(agentTaskInfo(a).latest) }}</span>
                      <span v-if="agentTaskInfo(a).extra > 0" class="status-extra">+{{ agentTaskInfo(a).extra }}</span>
                      <span v-if="agentTaskInfo(a).latest.status === 'waiting_review'" class="status-peek is-review">审阅签发 →</span>
                      <span v-else class="status-peek">速览 →</span>
                    </div>
                    <!-- 右槽②未召集：就绪徽 / 创建页 escape -->
                    <div v-else-if="!summonedLocally(a)" class="agent-actions">
                      <span v-if="agentBatchable(a, m.recommendation)" class="agent-readytag">✓ 参数已齐 · 待开工</span>
                      <button v-else class="agent-cta" @click="createOneTask(a, m.recommendation)">去创建此任务</button>
                    </div>
                    <span v-else class="agent-readytag">已召集 · 接入中…</span>
                  </div>

                  <!-- 次行：实时旁白（已召集）——运行中=事件驱动 shimmer；终态=过去式盖章 -->
                  <div
                    v-if="agentTaskInfo(a)"
                    class="sa-stageline"
                    :class="{ 'is-running': isWorkState(agentTaskInfo(a).latest.status),
                              'is-review': agentTaskInfo(a).latest.status === 'waiting_review' }"
                  >{{ stagelineText(agentTaskInfo(a).latest) }}</div>
                  <!-- 次行：未召集——理由 + 预填摘要一行收纳（过程可折） -->
                  <template v-else>
                    <div class="sa-subline">
                      <span v-if="a.rationale" class="agent-rationale">{{ a.rationale }}</span>
                      <span v-for="(v, k) in a.prefilled_inputs" :key="k" class="draft-field">
                        <span class="df-key">{{ k }}</span>
                        <span class="df-val">{{ formatDraftVal(v) }}</span>
                      </span>
                    </div>
                    <p v-if="a.stripped_fields && a.stripped_fields.length" class="agent-stripped">
                      已剔除不合法字段：{{ a.stripped_fields.join("、") }}（未匹配该 Agent 的输入契约）
                    </p>
                    <!-- 提示按成员就绪分轴（CRS R0-P3）：参数齐但方案级不可开工（归档/附件）
                         不能误导用户去修本已齐的参数 -->
                    <div v-if="!summonedLocally(a) && !agentBatchable(a, m.recommendation)" class="sa-subline">
                      <span v-if="agentReady(a) === true" class="agent-unready-hint">参数已齐——本方案暂不可一键开工（会话已归档或有附件），可去创建页亲手提交。</span>
                      <span v-else class="agent-unready-hint">参数未齐——直接回复导引补全，或去创建页填好后亲手提交。</span>
                    </div>
                  </template>

                  <!-- 产物锚点行（Claude Artifact 卡片锚点哲学）：完成且真有产物才长出 -->
                  <div
                    v-if="agentTaskInfo(a) && agentTaskInfo(a).latest.status === 'completed' && (agentTaskInfo(a).latest.output_file_ids || []).length"
                    class="status-artifact"
                    role="button"
                    tabindex="0"
                    @click.stop="openTaskPeek(agentTaskInfo(a).latest.id)"
                    @keydown.enter.stop.prevent="openTaskPeek(agentTaskInfo(a).latest.id)"
                    @keydown.space.stop.prevent="openTaskPeek(agentTaskInfo(a).latest.id)"
                  >
                    <svg class="artifact-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/></svg>
                    <span class="artifact-count">{{ (agentTaskInfo(a).latest.output_file_ids || []).length }} 件产物</span>
                    <span class="artifact-open">查看 ↗</span>
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
                <button
                  v-if="openableCount(m.recommendation) > 0"
                  class="open-plan-btn cta-clay"
                  :disabled="opening === conversationId"
                  @click="openPlan(m.recommendation)"
                >{{ opening === conversationId ? "召集中…" : `照此方案开工 · 召集 ${openableCount(m.recommendation)} 名就绪成员` }}</button>
                <!-- 层级结构化（W5）：开工在场时工作台入口降次级——由数据显式绑定，
                     不再依赖 :has() 条件级联（一屏一主动作的结构性落点）。主/次
                     互斥换装：主态接全局 .cta-clay（SSOT），次态走 .is-secondary。 -->
                <button class="workbench-btn" :class="openableCount(m.recommendation) > 0 ? 'is-secondary' : 'cta-clay'" @click="openWorkbench">进入协作工作台 →</button>
                <button type="button" class="plan-escape" @click="focusComposer">想调整方案？直接告诉导引 ↓</button>
                <!-- 政策句压一行（批次四 Q3）：红线字面「亲手提交」「签发权」
                     逐字保留（m6 ③ 锚）；动词分轴（3-lens P3）——开工=提交、
                     放行=批准，不把两个动作混进一个动词；细则（参数未齐怎么办）
                     随需在导引对话里自然出现，不在每张卡常驻复述。 -->
                <span class="plan-note">
                  开工由你<strong>亲手提交</strong>，产物放行由你批准——签发权始终在你，导引不代召集、不代签。
                </span>
              </div>
            </div>
          </div>
        </template>
      </div>

      <div v-if="sending" class="bubble-row assistant">
        <div class="ai-mark">导</div>
        <div class="ai-thinking">
          <div class="think-row">
            <ThinkingInk />
            <!-- 真耗时（评审 N3）：≥3s 才显示，快回合不闪数字；tabular-nums 逐秒活跳不抖宽。 -->
            <span class="tlabel">导引思考中…<span v-if="thinkingSeconds >= 3" class="think-elapsed num-token">{{ thinkingSeconds }}s</span></span>
          </div>
          <!-- 诚实预期管理（评审 N3）：内网大模型单轮可达一两分钟（B3 超时旋钮按内网
               p99 放宽后尤甚）——超 30s 给一行真话；绝不做假进度条（诚实地板）。 -->
          <p v-if="thinkingSeconds >= 30" class="think-slow">内网大模型推理较慢——复杂需求可能要一两分钟。请留在本页稍候：本轮若失败，你的原话会退回输入框，不会丢。</p>
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
          <span class="chip-x" @click="removePendingFile(f)">×</span>
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
            :disabled="sending"
          >
            <button class="icon-btn" :disabled="sending" title="添加附件（≤5 个/条；文本类直读、xlsx 预览）" aria-label="添加附件">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a5 5 0 0 1-7.07-7.07l9.19-9.19a3.5 3.5 0 0 1 4.95 4.95l-9.2 9.19a1.5 1.5 0 0 1-2.12-2.12l8.49-8.49"/></svg>
            </button>
          </el-upload>
          <!-- Agent 选择器（范式 2b：门户降级为 composer 内浏览）：点选只把
               Agent 名填进草稿并聚焦——问导引怎么用它，绝不代发（人是唯一发起者）。 -->
          <el-popover placement="top-start" :width="320" trigger="click" popper-class="agent-pick-pop">
            <template #reference>
              <button class="icon-btn" :disabled="sending" title="浏览可用 Agent" aria-label="浏览可用 Agent">
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
                  <span class="ap-sub" :title="a.summary">{{ a.summary }}</span>
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
            :disabled="sending"
            :placeholder="composerPlaceholder"
            class="composer-input"
            @keydown.enter.exact.prevent="send"
          />
          <button class="send-btn cta-clay" :disabled="sending || !draft.trim()" aria-label="发送" @click="send">
            <svg v-if="!sending" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M7 11l5-5 5 5M12 6v13"/></svg>
            <span v-else class="send-spin"></span>
          </button>
        </div>
      </div>
      <!-- 减重批：政策句+诚实地板合一行（「导引不会替你创建」是 m6 e2e 锚，
           字面保留）；快捷键仍 hover/聚焦才显。 -->
      <div class="composer-hint">
        <span>导引不会替你创建或签发任务——产出是草案，判定权在你。</span>
        <span class="keys"><kbd>Enter</kbd> 发送<span class="sep">·</span><kbd>⇧ Enter</kbd> 换行<span class="sep">·</span>📎 可带附件</span>
      </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, computed, nextTick, watch, onMounted, onUnmounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { createConversation, postMessage, getConversation } from "../api/conversations";
import { createTask } from "../api/tasks";
import { listAgents, getAgent } from "../api/agents";
import { uploadFile as apiUploadFile } from "../api/files";
import { categoryColor, categoryLabel, categoryTip, maturityTip, statusLabel, taskLampColor, TASK_WORK_STATES, taskElapsedMs, formatTime } from "../utils/format";
import { openTaskPeek } from "../stores/statusCenter";
import { acquireChannel, pokeConversation } from "../stores/liveFeed";
import { resolvedTheme } from "../stores/theme";
import ThinkingInk from "../components/artwork/ThinkingInk.vue";
import IntentGlyph from "../components/artwork/IntentGlyph.vue";
import MarkdownLite from "../components/MarkdownLite.vue";
import OnboardingCard from "../components/OnboardingCard.vue";
import { displayName } from "../stores/session";

const router = useRouter();

const GUIDE_AGENT_ID = "guide_agent";
const MAX_FILES_PER_MESSAGE = 5; // 与后端 PostMessageRequest / 运行时同值

const started = ref(false);
const conversationId = ref("");
const messages = ref([]);
const draft = ref("");
const sending = ref(false);
const pageError = ref("");
const streamEl = ref(null);
// composer placeholder 语境分化：未起手空会话引导点意图卡；会话中改为「继续说下去」，
// 不再重复「回答导引的追问」（此刻输入框已在真实对话流里，无需再解释这是什么）。
const composerPlaceholder = computed(() =>
  !started.value && messages.value.length === 0
    ? "描述你的工程需求，或点一张下方的意图卡…"
    : "回复导引，继续说下去…"
);
// 待发送附件（M7）：选中只入列（raw 留本地），发送时才上传——同 TaskCreate 的
// P2-A 反孤儿纪律；已上传项记 fileId，失败重试不重复上传。
const pendingFiles = ref([]);
let fileSeq = 0;

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
  pendingFiles.value = pendingFiles.value.filter((f) => f.uid !== item.uid);
}

async function uploadPendingFiles() {
  // 顺序上传未完成项（含上一轮失败项）；任一失败即抛出，本轮消息不发送。
  // 已知行为（反方审 P3）：某轮失败但附件已上传成功（status:done）时，附件
  // 保留在待发区——这是重试语义（重试同一句不重复上传）。若用户改发别的
  // 内容，这些附件会一并带上，但 chips 始终可见、可逐个移除，故不隐藏、
  // 不静默——是否带上由用户自己看着 chips 决定。
  for (const item of pendingFiles.value) {
    if (item.status === "done") continue;
    item.status = "uploading";
    item.error = "";
    try {
      const res = await apiUploadFile(item.raw);
      item.status = "done";
      item.fileId = res.id;
    } catch (err) {
      item.status = "error";
      item.error = err.detail || err.message;
      throw new Error(`附件「${item.name}」上传失败：${item.error}`);
    }
  }
  return pendingFiles.value.map((f) => f.fileId);
}

function inputCount(agent) {
  return Object.keys(agent.prefilled_inputs || {}).length;
}

// 预填值紧凑渲染：标量直显（值恒在可见 DOM 文本流——诚实地板 + m6 e2e 锚
// top_event/供电完全丧失 不依赖点击）；对象/数组回退单行 JSON。
function formatDraftVal(v) {
  return v !== null && typeof v === "object" ? JSON.stringify(v) : String(v);
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

// ── 导引轮次真耗时（评审 N3）────────────────────────────────────────────
// 独立 1s 计时器（不共用实时行的 nowTick——那条由工作态任务门控启停，语义
// 不同不硬并）；sending 结束即停表清零，零常驻空转。
const sendStartedAt = ref(null);
const sendNow = ref(0);
let sendTimer = null;
watch(sending, (s) => {
  if (s === true) {
    sendStartedAt.value = Date.now();
    sendNow.value = Date.now();
    sendTimer = setInterval(() => { sendNow.value = Date.now(); }, 1000);
  } else {
    if (sendTimer) { clearInterval(sendTimer); sendTimer = null; }
    sendStartedAt.value = null;
  }
});
onUnmounted(() => { if (sendTimer) clearInterval(sendTimer); });
const thinkingSeconds = computed(() =>
  sendStartedAt.value ? Math.max(0, Math.round((sendNow.value - sendStartedAt.value) / 1000)) : 0
);

// ── 演示任务预填（评审 N2）──────────────────────────────────────────────
// 与导引草案同一 sessionStorage 契约（TaskCreate 按 from=demo 读取并给演示
// 语境横幅）；inputs 示例值=登录显示名——是用户自己的名字不是编造工程数据，
// 且创建页人可改可核后亲手提交（预填 ≠ 代建）。
function startDemoTask() {
  sessionStorage.setItem(
    "flai_prefill",
    JSON.stringify({
      agent_id: "hello_agent",
      inputs: { name: displayName() || "同事" },
      files: [],
      conversation_id: null,
      conclude_after: false,
    })
  );
  router.push({ path: "/tasks/new", query: { agent_id: "hello_agent", from: "demo" } });
}

// ── 复制需求摘要（评审 N6）──────────────────────────────────────────────
// 内网 http 非 secure context，navigator.clipboard 大概率不可用——必须带
// execCommand 兜底；两路都失败如实报错，绝不假报「已复制」。
async function copyText(text) {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* 落入 execCommand 兜底 */
  }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok === true;
  } catch {
    return false;
  }
}

function precedingUserContent(idx) {
  for (let i = idx - 1; i >= 0; i -= 1) {
    if (messages.value[i].role === "user") return messages.value[i].content;
  }
  return "";
}

async function copyRefusedNeed(idx) {
  const m = messages.value[idx];
  const rec = (m && m.recommendation) || {};
  const lines = ["【需求登记草稿】"];
  const need = precedingUserContent(idx);
  if (need) lines.push(`需求原文：${need}`);
  if (rec.reason) lines.push(`平台初判：暂时接不住——${rec.reason}`);
  if (Array.isArray(rec.residual_problems) && rec.residual_problems.length) {
    lines.push("仍未解决的问题：");
    for (const p of rec.residual_problems) lines.push(`- ${p}`);
  }
  if (Array.isArray(rec.reframe) && rec.reframe.length) {
    lines.push("导引建议的重述方向：");
    for (const r of rec.reframe) lines.push(`- ${r}`);
  }
  lines.push("（来自 FLAi-OS 导引对话——请平台负责人按家底口径评估排期）");
  const ok = await copyText(lines.join("\n"));
  if (ok === true) ElMessage.success("需求摘要已复制——发给平台负责人登记，别让它溜走");
  else ElMessage.error("复制失败——请手动选取文字复制");
}

async function scrollToBottom() {
  // 会话流走自然页面流（不再是内嵌定长滚动框）——把最新一条滚到视口顶部起读，
  // 让高高的协作方案卡从「目标句」开始展开，而不是被塞进 62vh 的小盒里。
  await nextTick();
  const last = streamEl.value && streamEl.value.lastElementChild;
  if (last) last.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function send() {
  if (restoring.value) return; // 会话恢复在途不收发言——防止意外新建会话
  const content = draft.value.trim();
  if (!content) return;
  pageError.value = "";

  // 乐观追加用户气泡（附件 chips 一并显示；失败整体回滚）
  const optimisticAttachments = pendingFiles.value.map((f) => ({ id: f.uid, filename: f.name }));
  messages.value.push({
    role: "user",
    content,
    attachments: optimisticAttachments.length ? optimisticAttachments : undefined,
    // fresh：仅本次会话中「刚落地」的气泡播墨迹入场；历史加载不带此标记——
    // 诚实地板：不让三天前的旧对话表演"刚发生"（信任镜头 P2）。
    fresh: true,
  });
  draft.value = "";
  await scrollToBottom();

  sending.value = true;
  try {
    // 先传附件（已 done 的跳过，失败即中止——本轮消息不发送）
    const fileIds = await uploadPendingFiles();
    if (!conversationId.value) {
      const conv = await createConversation({ agentId: GUIDE_AGENT_ID });
      conversationId.value = conv.id;
      conversationStatus.value = conv.status || "active";
      started.value = true;
      // URL 反映当前会话（可刷新/分享/回退），并让左栏历史即时收录这条新会话。
      router.replace({ path: "/", query: { c: conv.id } });
    }
    const res = await postMessage(conversationId.value, content, fileIds);
    // 成功：附件已随消息落库，清空待发区；气泡 chips 换用真实文件 id
    const sent = messages.value[messages.value.length - 1];
    if (sent && sent.role === "user" && optimisticAttachments.length) {
      sent.attachments = pendingFiles.value.map((f) => ({ id: f.fileId, filename: f.name }));
    }
    pendingFiles.value = [];
    messages.value.push({
      role: "assistant",
      content: res.message.content,
      recommendation: res.message.recommendation || null,
      fresh: true,
      createdAt: res.message.created_at || null,
    });
    await scrollToBottom();
    ensureConversationTasksFeed(); // 本轮若刚给出 orchestrate 方案，开始为其召集状态保鲜
    ensureAgentSchemasForMessages(); // 内联召集就绪判据的契约预取（fail-closed）
  } catch (err) {
    // 本轮失败：后端契约是「失败零落库」（幂等重试，ADR-0013），本地同样回滚
    // 乐观气泡并把原文还原到输入框——不在界面上留一条服务端不存在的幽灵消息，
    // 重试也不会堆出重复 user 气泡（Codex R1-P2）。附件 chips 留在待发区
    // （已上传项带 fileId，重试不重复上传）。不伪造 assistant 回复。
    const last = messages.value[messages.value.length - 1];
    if (last && last.role === "user" && last.content === content) {
      messages.value.pop();
    }
    draft.value = content;
    pageError.value = err.detail || err.message;
  } finally {
    sending.value = false;
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

// ── 原地召集（对话轴内联确认，范式 2a 单入口）─────────────────────────
// 宪法边界：导引绝不代召集——「原地召集」「确认召集」两次点击都由人亲手完成，
// 走与创建页完全相同的 POST /api/tasks（服务端 jsonschema 校验 fail-closed）。
// 只在①多 Agent 方案（单 Agent 保留创建页 conclude_after 归档语义）②预填非空
// ③会话无携带附件（附件必须经创建页人工过目）时提供；参数不全由 422 如实
// 透出，引导走「去创建此任务」补全，绝不客户端猜校验。
const opening = ref(null); // 「照此方案开工」进行中的会话 id（按会话作用域，CRS R1-P2：
// 全局布尔会在切会话后把新会话的开工按钮一并禁死；API client 无超时，卡住的旧请求
// 可无限期封锁新会话的唯一开工入口）
// 本地已召集账（CRS R0-P2）：批量创建成功后 conversationTasks 轮询最长滞后 5s，
// 期间 openableCount 若仍计入已成功成员，按钮复活可被二次点击造重复任务。
// key=`${会话id}:${agent_id}`，跨会话天然隔离；feed 数据到位后与 agentTaskInfo 双保险。
const locallySummoned = reactive({});
// 会话可写态（Codex R0-P2）：getConversation/createConversation 如实带出，concluded
// 只读会话不提供内联召集（否则创建必 409）。未知（null）= fail-closed 不提供。
const conversationStatus = ref(null);
// Agent 输入契约缓存（Codex R0-P1）：POST /api/tasks 不做即时 schema 校验（校验在
// worker 运行期），故「预填就绪」必须由前端按 input_schema.required 逐键判定后才
// 提供内联路径——schema 拉不到 / 未知一律 fail-closed 回创建页路径。
const agentSchemaCache = reactive({}); // agent_id -> { loaded: true, schema: object|null }


function fieldMatchesSchema(propSchema, v) {
  // 轻量原语校验（string/number/integer/boolean/enum）：导引出案时已按当时 schema
  // 逐字段校验，这里补的是「会话恢复后 Agent 契约已升级」的漂移窗（Codex R1-P2）。
  // 只做原语级判定，object/array 等复杂类型放行交服务端/worker 权威校验。
  if (!propSchema || typeof propSchema !== "object") return false; // 键已不在当前契约里
  if (Array.isArray(propSchema.enum)) return propSchema.enum.includes(v);
  const t = propSchema.type;
  if (t === "string") return typeof v === "string";
  if (t === "number") return typeof v === "number" && Number.isFinite(v);
  if (t === "integer") return typeof v === "number" && Number.isInteger(v);
  if (t === "boolean") return typeof v === "boolean";
  return true;
}

function prefillSatisfiesSchema(schema, prefilled) {
  // 就绪判据（纯函数，fail-closed）：schema 存在、required 明确、每个必填键在预填里
  // 非空白、且每个预填键都通过当前契约的原语校验。这只是「提供内联入口」的门槛，
  // 不替代服务端/worker 的权威校验。
  if (!schema || typeof schema !== "object") return false;
  const required = Array.isArray(schema.required) ? schema.required : null;
  if (required === null) return false;
  const props = schema.properties && typeof schema.properties === "object" ? schema.properties : {};
  const filled = prefilled || {};
  const requiredOk = required.every((k) => {
    const v = filled[k];
    return v !== undefined && v !== null && String(v).trim() !== "";
  });
  const typesOk = Object.keys(filled).every((k) => fieldMatchesSchema(props[k], filled[k]));
  return requiredOk === true && typesOk === true;
}

function ensureAgentSchemasForMessages() {
  // 方案卡出现（新回复或历史恢复）即预取成员 Agent 的输入契约；失败记 null=不就绪。
  for (const m of messages.value) {
    const plan = m && m.recommendation;
    if (!plan || plan.decision !== "orchestrate" || !Array.isArray(plan.agents)) continue;
    for (const a of plan.agents) {
      const id = a.agent_id;
      if (!id || id in agentSchemaCache) continue;
      agentSchemaCache[id] = { loaded: false, schema: null };
      getAgent(id)
        .then((detail) => {
          agentSchemaCache[id] = {
            loaded: true,
            schema: (detail && detail.input_schema) || null,
            // 输入模式：只有纯参数型（params）可走内联；file_upload 的 required
            // 可为空数组，若不看模式会空洞通过后必失败「无输入文件」（Codex R1-P1）。
            inputMode: (detail && detail.input_mode) || null,
          };
        })
        .catch(() => {
          agentSchemaCache[id] = { loaded: true, schema: null, inputMode: null };
        });
    }
  }
}

// ── 实时子 agent 行引擎（owner 定向「像 codex 子 agent」）────────────────────
// 秒表：1s 离散文本替换（codex 灰阶纪律：活着的信号=文本活跳，零 spinner 通胀）；
// 旁白：每个工作态最新任务 acquire 共享 liveFeed 'task:<id>' channel（Codex R1-P2：
// 不自开第二条轮询链——in-flight 去重/hidden 跳过/引用计数/与速览共链全部继承，
// task+events 同拍落地不产生「状态还在跑、旁白已收官」的错拍窗口），取最新过程
// 事件译成一行人话（disclosure grammar「过程压成摘要行」）。只在有工作态任务时运转。
const nowTick = ref(Date.now());
const stageNotes = reactive({}); // taskId -> 最新过程旁白（状态措辞一律由 status 出，见下）
let liveTimer = null;

// 状态迁移类事件不进旁白（Codex R1-P2）：终态/审核措辞统一由任务快照 status 经
// stagelineText 给出，避免事件先到、快照未追平时「clay 脉动灯 + 任务完成」同屏矛盾。
const STATE_EVENT_TYPES = new Set([
  "task_created",
  "validation_failed",
  "review_requested",
  "review_approved",
  "review_rejected",
  "task_completed",
  "task_failed",
]);

const EVENT_VERB = {
  validation_started: "校验输入契约…",
  tool_started: "调用工具…",
  tool_finished: "工具已返回",
  agent_log: "运行中…",
};

// workflow 折叠事件译文（runtime._WorkflowEventLogger 把业务事件折成 agent_log，
// 原始类型在 payload.workflow_event_type）：只译仓内已知类型，未知回退通用工作语。
const WORKFLOW_EVENT_VERB = {
  dependency_resolved: "前序产物已就绪，接力开始",
  summary_generated: "汇总已生成",
};

function describeEvent(ev) {
  if (!ev) return "";
  const payload = ev.payload || {};
  if (typeof payload.stage === "string" && payload.stage) {
    let txt = payload.stage;
    if (payload.residual) txt += ` · 残差 ${payload.residual}`;
    if (payload.iterations) txt += ` · 累计 ${payload.iterations} 次迭代`;
    if (payload.result) txt += ` · ${payload.result}`;
    return txt;
  }
  // 折叠事件的 message 形如「workflow 上报事件：case_started」——直显会把内部
  // snake_case 标识符泄进旁白（Codex R1-P2），必须先于 message 分支拦截翻译。
  if (typeof payload.workflow_event_type === "string" && payload.workflow_event_type) {
    return WORKFLOW_EVENT_VERB[payload.workflow_event_type] || EVENT_VERB.agent_log;
  }
  if (typeof ev.message === "string" && ev.message.trim()) return ev.message.trim();
  return EVENT_VERB[ev.event_type] || ""; // 未知类型不裸显 snake_case，留旧旁白
}

// 从事件尾巴取最新「过程」旁白（状态迁移类跳过，见 STATE_EVENT_TYPES）。
function latestProcessNote(events) {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const ev = events[i];
    if (STATE_EVENT_TYPES.has(ev.event_type)) continue;
    const note = describeEvent(ev);
    if (note) return note;
  }
  return "";
}

// taskId -> { handle, stops }：每个工作态最新任务持一条共享 task channel。
const liveChannels = new Map();

function syncLiveChannels() {
  // 目标集=每个 agent 的**最新可见任务**（与 agentTaskInfo 同口径：列表 created_at
  // 降序取首个），旧的重复任务不占名额（Codex R0-P2）；覆盖全部工作态
  // （validating/parsing/analyzing 同样产事件），queued 无事件不拉。
  const latestByAgent = new Map();
  for (const t of conversationTasks.value) {
    if (!latestByAgent.has(t.agent_id)) latestByAgent.set(t.agent_id, t);
  }
  const wanted = new Set(
    [...latestByAgent.values()]
      .filter((t) => TASK_WORK_STATES.has(t.status))
      .map((t) => t.id)
  );
  for (const [id, entry] of [...liveChannels]) {
    if (!wanted.has(id)) {
      entry.stops.forEach((stop) => stop());
      entry.handle.release();
      liveChannels.delete(id);
    }
  }
  for (const id of wanted) {
    if (liveChannels.has(id)) continue;
    const handle = acquireChannel(`task:${id}`);
    const stops = [
      watch(
        handle.state.events,
        (events) => {
          // 只在 channel 自身快照仍是工作态时收旁白（Codex R2-P2）：失败路径上
          // 终态事件前常跟着失败缘由消息（如 validation_failed→task_failed），
          // 若照收，会话快照追平前会出现「clay 脉动灯 + 失败措辞」同屏矛盾。
          // task 与 events 同一次 fetch 落地，此判定与事件尾巴同拍不追旧。
          const snap = handle.state.task.value;
          if (snap && !TASK_WORK_STATES.has(snap.status)) return;
          const note = latestProcessNote(events || []);
          if (note) stageNotes[id] = note;
        },
        { immediate: true }
      ),
      // channel（2s）先于会话快照（5s）看到离开工作态 → poke 会话链让成员行
      // 状态秒级追平，收窄「灯还脉动、任务已收官」的错拍窗（Codex R1-P2）。
      watch(
        () => handle.state.task.value && handle.state.task.value.status,
        (s) => {
          if (s && !TASK_WORK_STATES.has(s) && conversationId.value) {
            pokeConversation(conversationId.value);
          }
        }
      ),
    ];
    liveChannels.set(id, { handle, stops });
  }
}

function releaseLiveChannels() {
  for (const [, entry] of liveChannels) {
    entry.stops.forEach((stop) => stop());
    entry.handle.release();
  }
  liveChannels.clear();
}

function ensureLiveTicker() {
  if (liveTimer) return;
  liveTimer = setInterval(() => {
    nowTick.value = Date.now(); // 秒表 1s 活跳（纯本地渲染，零请求）
  }, 1000);
}

function stopLiveTicker() {
  if (liveTimer) {
    clearInterval(liveTimer);
    liveTimer = null;
  }
}

// 秒表锚点=started_at（taskElapsedMs 的诚实契约：未开工返回 null 不编造）——锚
// created_at 会把排队等待计成工时，且 started_at 落库后时钟倒跳（Codex R1-P2）。
// 数字格式走 canon §三（<60s 纯秒 / ≥60s Nm 0Ss 秒补零），不复用 formatDuration
// 的「X 分 X 秒」长格式——codex 式紧凑行寸土寸金。
function elapsedText(t) {
  if (!TASK_WORK_STATES.has(t.status) && !t.finished_at) return ""; // 非工作态无收尾戳不给活秒表
  const ms = taskElapsedMs(t, nowTick.value);
  if (ms === null) return "";
  const sec = Math.max(0, Math.round(ms / 1000));
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m ${String(sec % 60).padStart(2, "0")}s`;
}

function stagelineText(t) {
  if (t.status === "queued") return "排队中——等待执行器领取";
  if (TASK_WORK_STATES.has(t.status)) return stageNotes[t.id] || `${statusLabel(t.status)}…`;
  if (t.status === "waiting_review") return "产物已就绪——等待你审阅放行";
  if (t.status === "completed") {
    const dur = elapsedText(t);
    return dur ? `任务完成 · 用时 ${dur}` : "任务完成"; // 时态即状态：过去式盖章
  }
  if (t.status === "failed") return "运行失败——点右侧速览看详情（如实透出，不静默）";
  if (t.status === "cancelled") return "已取消";
  return "";
}

// 成员级就绪（fail-closed）：params 型 + 预填非空 + 过当前契约（required 齐 + 原语校验）。
// Codex R0-R2 三轮收敛的全部门保留：file_upload/none/未知模式、空预填、契约漂移都不就绪。
function agentReady(agent) {
  const cached = agentSchemaCache[agent.agent_id];
  return (
    !!cached && cached.loaded === true &&
    cached.inputMode === "params" &&
    Object.keys(agent.prefilled_inputs || {}).length > 0 &&
    prefillSatisfiesSchema(cached.schema, agent.prefilled_inputs || {})
  );
}

// 方案级可开工门：会话可写 + 多 Agent 方案 + 无携带/未发送附件（附件必经创建页过目）。
function planOpenable(plan) {
  return (
    !!conversationId.value &&
    conversationStatus.value === "active" &&
    plan && Array.isArray(plan.agents) && plan.agents.length > 1 &&
    collectCarriedFiles().length === 0 &&
    pendingFiles.value.length === 0
  );
}

function agentBatchable(agent, plan) {
  return planOpenable(plan) === true && agentReady(agent) === true;
}

function summonedLocally(agent) {
  return locallySummoned[`${conversationId.value}:${agent.agent_id}`] === true;
}

function openableCount(plan) {
  if (planOpenable(plan) !== true) return 0;
  return plan.agents.filter(
    (a) => agentReady(a) === true && !agentTaskInfo(a) && !summonedLocally(a)
  ).length;
}

// 「照此方案开工」：一键把全部就绪且未召集的成员按方案顺序召集（每个都是同一
// POST /api/tasks，服务端校验 fail-closed）。这一键由人亲手点下=人召集；导引
// 从未获得任何自动路径。逐个失败如实收集透出，绝不静默。
async function openPlan(plan) {
  if (opening.value === conversationId.value && opening.value !== null) return;
  if (planOpenable(plan) !== true) {
    ElMessage.error("条件已变化（会话归档 / 新增附件），请刷新方案或走「去创建此任务」。");
    return;
  }
  // 会话 id 在进入循环前钉死（CRS R0-P1）：批量创建期间用户切换历史会话/新对话会
  // 改写 conversationId，后续任务会错账到新会话。全程只用这枚不可变值；一旦检测到
  // 会话已切换，剩余目标立即中止并如实上报（绝不把旧方案的任务写进别的会话）。
  const approvedConvId = conversationId.value;
  const targets = plan.agents.filter(
    (a) => agentReady(a) === true && !agentTaskInfo(a) && !summonedLocally(a)
  );
  if (targets.length === 0) return;
  opening.value = approvedConvId;
  const failed = [];
  let aborted = 0;
  for (let i = 0; i < targets.length; i += 1) {
    const a = targets[i];
    if (conversationId.value !== approvedConvId) {
      aborted = targets.length - i; // 会话已切换：剩余不再创建
      break;
    }
    try {
      await createTask({
        agentId: a.agent_id,
        name: null,
        inputs: a.prefilled_inputs || {},
        inputFileIds: [],
        conversationId: approvedConvId,
      });
      locallySummoned[`${approvedConvId}:${a.agent_id}`] = true;
    } catch (err) {
      failed.push(`${a.agent_name}：${err.detail || err.message || "创建失败"}`);
    }
  }
  ensureConversationTasksFeed(); // 督战 chip 保鲜：召集即接上会话任务订阅
  if (failed.length === 0 && aborted === 0) {
    ElMessage.success(`已按方案召集 ${targets.length} 名成员——进度与签发都会来这里找你`);
  } else {
    // fail-closed 如实透出（409 已归档 / 校验拒绝 / 中途切会话），不静默、不假报全成
    const parts = [];
    if (failed.length > 0) parts.push(`失败：${failed.join("；")}`);
    if (aborted > 0) parts.push(`会话已切换，剩余 ${aborted} 名未召集`);
    ElMessage.error(`召集未全部完成——${parts.join("；")}`);
  }
  if (opening.value === approvedConvId) opening.value = null; // 只清本会话的忙态
}

function createOneTask(agent, plan) {
  // 人确认接缝：把某个被召集 Agent 的预填草案交给创建任务页，由人补全后亲手
  // 提交（导引绝不代签）。走 sessionStorage 而非 URL，避免工程数据进查询串。
  // M7：会话附件随草案带走，创建页以「已上传」状态入列，人可移除。
  // 单 Agent 计划：确认后应归档会话（保留 M6「一次会话=一个任务」语义）。但归档必须
  // **后于任务创建成功**——异源 Codex R2-#3：会话 concluded 后 API 真只读拒新任务，若
  // 沿用旧的「先 fire-and-forget 归档、再跳创建页」，创建时会话已 concluded → 创建被 409
  // 打回。故这里不再先归档，只在草案里带 conclude_after 标记，由创建页在提交成功后归档。
  const isSingleAgent =
    plan && Array.isArray(plan.agents) && plan.agents.length === 1 && !!conversationId.value;
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

// 会话任务快照每次落地 → 对账 task channel 持有集；有任一工作态成员任务 →
// 秒表开，全部终态 → 秒表停（不空转）。必须声明在 conversationTasks 之后：
// watch source 创建时即求值，TDZ 抛错会被 Vue callWithErrorHandling 吞成
// console.error，watcher 静默死亡（Codex R0-P0，实拍佐证：秒表恒 0s、旁白恒
// 兜底句——引擎看似在场实则从未运转）。
watch(
  conversationTasks,
  (tasks) => {
    syncLiveChannels();
    const anyWork = tasks.some((t) => TASK_WORK_STATES.has(t.status));
    if (anyWork === true) ensureLiveTicker();
    else stopLiveTicker();
  },
  { immediate: true }
);
onUnmounted(() => {
  stopLiveTicker();
  releaseLiveChannels();
});
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

// agent_id 匹配：后端按 created_at DESC, id DESC 返回，同一 agent 多任务时
// 第一条即最新一次召集；其余只计数，不逐条铺开（roster 卡片寸土寸金）。
function agentTaskInfo(agent) {
  const list = conversationTasks.value.filter((t) => t.agent_id === agent.agent_id);
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
const route = useRoute();

function resetToFresh(clearError = true) {
  messages.value = [];
  started.value = false;
  conversationId.value = "";
  conversationStatus.value = null;
  draft.value = "";
  pendingFiles.value = [];
  releaseConversationTasksFeed();
  if (clearError) pageError.value = "";
}

// 恢复在途标记：?c 深链（含 2a 回流）落地时 getConversation 在途的窗口里，
// 不渲染可交互的空态 hero（「假起手」）、send 早退——否则此刻发消息会因
// conversationId 尚空而意外新建会话（双镜头 P2 实审咬出的竞态）。
const restoring = ref(false);

async function loadConversation(id) {
  resetToFresh();
  restoring.value = true;
  try {
    const conv = await getConversation(id);
    conversationId.value = conv.id;
    conversationStatus.value = conv.status || null; // 只读会话如实带出（Codex R0-P2）
    started.value = true;
    messages.value = (conv.messages || []).map((m) => ({
      role: m.role,
      content: m.content,
      recommendation: m.recommendation || null,
      attachments: m.attachments && m.attachments.length ? m.attachments : undefined,
      createdAt: m.created_at || null,
    }));
    await scrollToBottom();
    ensureConversationTasksFeed(); // 恢复的历史会话若已带 orchestrate 方案，立即接上订阅
    ensureAgentSchemasForMessages(); // 历史方案卡同样预取输入契约（内联就绪判据）
  } catch (err) {
    pageError.value = err.detail || err.message || "会话加载失败";
  } finally {
    restoring.value = false;
  }
}

onMounted(() => {
  const c = route.query.c;
  if (typeof c === "string" && c) loadConversation(c);
});
onUnmounted(() => {
  feedDisposed = true; // 先封门再释放：卸载后任何 await 续体不得再 acquire
  releaseConversationTasksFeed();
});

// 左栏切换会话 / 点「新对话」→ 据 ?c 变化恢复或重置（跳过刚创建的本会话，避免回灌）。
watch(
  () => route.query.c,
  (c) => {
    if (typeof c === "string" && c) {
      if (c !== conversationId.value) loadConversation(c);
    } else if (started.value || messages.value.length) {
      resetToFresh();
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
  background: linear-gradient(160deg, var(--clay), var(--clay-deep));
  box-shadow: 0 6px 18px rgba(var(--clay-rgb), 0.26);
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
  font-size: var(--fs-display-lg);
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
/* ai-lead 现为 MarkdownLite 容器（W5）：块结构由组件内 md-* 承担，容器只定
 * 基础字号/行高/下距；pre-wrap 移除（段落切分已由块级渲染接管）。 */
.ai-lead {
  font-size: 15px;
  line-height: 1.72;
  color: var(--ink);
  margin: 0 0 16px;
}
.ai-lead :deep(.md-p:first-child),
.ai-lead :deep(.md-h:first-child) {
  margin-top: 0;
}

/* 思考指示（N3 改双行容器：首行=墨滴+状态词+秒表，次行=慢等待诚实提示） */
.ai-thinking {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  color: var(--ink-faint);
  font-size: 13.5px;
}
.think-row {
  display: flex;
  align-items: center;
  gap: 5px;
}
.ai-thinking .tlabel { margin-left: 6px; }
.think-elapsed {
  margin-left: 7px;
  font-size: 12px;
  color: var(--ink-soft);
}
.think-slow {
  margin: 0 0 0 2px;
  max-width: 460px;
  font-size: 12px;
  line-height: 1.65;
  color: var(--ink-faint);
}

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
.plan-goal-title {
  font-family: var(--serif);
  font-size: var(--fs-display);
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

/* 需求登记引导（N6）：refuse 卡尾的安静动作行——按钮走 hairline 中性描边
 * （登记是保底动作不是主 CTA，不占 clay）。 */
.refuse-keep {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed var(--hairline);
}
.refuse-copy {
  flex: none;
  border: 1px solid var(--hairline);
  background: var(--surface-raised);
  color: var(--ink-soft);
  font-size: 12px;
  font-weight: 600;
  border-radius: 8px;
  padding: 5px 11px;
  cursor: pointer;
  transition: color var(--motion-fast) var(--ease-out-soft), border-color var(--motion-fast) var(--ease-out-soft);
}
.refuse-copy:hover {
  color: var(--ink);
  border-color: var(--ink-faint);
}
.refuse-keep-note {
  flex: 1 1 240px;
  min-width: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--ink-faint);
}
@media (prefers-reduced-motion: reduce) {
  .refuse-copy { transition: none; }
}

/* Agent roster 卡 */
.agent-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 6px;
}

/* codex 式子 agent 行：紧凑、实时、灰阶纪律（彩色只给状态灯与信任色语义）。
   注意特异性：.agent-card 基类是 flex 且声明在后，必须用双类压制。 */
.agent-card.sa-row {
  display: block;
  padding: 10px 14px;
  gap: 0;
}
.agent-card.sa-row:hover { transform: none; }
.sa-head {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
}
.sa-head .agent-name { flex: 0 1 auto; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sa-head .agent-role { margin: 0; flex: 0 1 auto; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sa-head .agent-maturity { margin-left: 0; }
.sa-spacer { flex: 1 1 auto; min-width: 8px; }
.sa-head .agent-status { margin: 0; flex: 0 0 auto; }
.sa-head .agent-actions { margin: 0; flex: 0 0 auto; }
.sa-head .agent-cta { padding: 5px 11px; font-size: 12.5px; }
/* 窄屏（嵌套 padding 后仅剩 ~170-220px）：状态槽整体落到第二行（Codex R2-P2），
   身份行（灯+名+分工）保住可读性——不换行时名字会被压成空省略号或控件溢出卡外。 */
@media (max-width: 640px) {
  .sa-head { flex-wrap: wrap; row-gap: 4px; }
  .sa-head .agent-status,
  .sa-head .agent-actions { flex: 0 0 100%; justify-content: flex-start; }
}
.sa-elapsed {
  font-size: 12px;
  color: var(--ink-soft);
  font-variant-numeric: tabular-nums; /* 秒表逐秒活跳不抖宽 */
}

/* 实时旁白行：事件驱动一行人话；运行中=灰阶 shimmer 扫光（活着的信号） */
.sa-stageline {
  margin: 6px 0 0 17px;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--ink-soft);
}
.sa-stageline.is-running {
  background: linear-gradient(100deg, var(--ink-soft) 30%, var(--clay) 50%, var(--ink-soft) 70%);
  background-size: 220% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  animation: sa-shimmer 2.4s linear infinite;
}
.sa-stageline.is-review { color: var(--trust-pending); }
@keyframes sa-shimmer {
  from { background-position: 200% 0; }
  to { background-position: -20% 0; }
}
@media (prefers-reduced-motion: reduce) {
  .sa-stageline.is-running {
    animation: none;
    background: none;
    color: var(--ink-soft);
  }
}

/* 未召集次行：理由 + 预填 chips 单行收纳 */
.sa-subline {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin: 6px 0 0 17px;
}
.sa-subline .agent-rationale { margin: 0; font-size: 12.5px; font-weight: 500; color: var(--ink-soft); }
.sa-row .status-artifact { margin: 7px 0 0 17px; }
.sa-row .agent-stripped { margin: 6px 0 0 17px; }
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
/* 死 CSS 清理（W5，grep 实证模板零消费）：.agent-main/.agent-top 属旧大卡布局，
 * sa-row 改版后无 DOM 承载——删规则；.agent-card 基类是 sa-row 的承重底座
 * （背景/描边/圆角/hover 阴影），保留；class token 本身是 m9 e2e 的 nth 钩子，
 * 模板中的 "agent-card" 字符串绝不可摘。 */
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
/* 预填草案：紧凑「键 值」chip 取代 monospace JSON 大块——值恒完整可见
   （诚实地板：不截断，让人看清按此会创建什么），视觉重量大幅下降。
   （.agent-draft/.draft-label/.draft-fields 旧容器类已删——模板零消费，W5） */
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

/* 决策收敛后的成员行（disclosure grammar：正常态不说话，异常态才有标签） */
.agent-actions { gap: 10px; align-items: center; flex-wrap: wrap; }
.agent-readytag {
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-soft);
}
.agent-unready-hint {
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--ink-soft);
}

/* 照此方案开工：整卡唯一主决策（clay 满底=工作态启动） */
/* 渐变/投影/hover/过渡走全局 .cta-clay（W0 真归位，模板已接线）——本类只留结构。 */
.open-plan-btn {
  flex: 0 0 auto;
  font-size: 13.5px;
  font-weight: 700;
  border-radius: 10px;
  padding: 10px 18px;
}
.open-plan-btn:disabled { opacity: 0.6; cursor: default; }
/* 开工在场时工作台入口降次级：数据驱动 .is-secondary（模板显式绑定），
 * 替换原 :has() 条件级联——主次由状态决定而非 DOM 巧合。 */
.workbench-btn.is-secondary {
  background: transparent;
  color: var(--clay);
  border: 1px solid var(--border-clay-soft);
  box-shadow: none;
  transition: background var(--motion-fast) var(--ease-out-soft);
}
.workbench-btn.is-secondary:hover {
  background: var(--select-tint-clay);
  box-shadow: none;
}

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
/* 主态渐变/投影/hover 走全局 .cta-clay（模板按主/次互斥换装）——本类只留结构。 */
.workbench-btn {
  flex: 0 0 auto;
  font-size: 13.5px;
  font-weight: 600;
  border-radius: 10px;
  padding: 9px 16px;
  cursor: pointer;
}
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
  /* 底部悬浮条减重（W5）：多轮对话时视觉更轻，渐隐遮罩起点不变 */
  padding: var(--space-4) var(--space-6) var(--space-5);
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
/* 渐变/投影/hover/过渡走全局 .cta-clay（W0 真归位，模板已接线）——本类只留结构。 */
.send-btn {
  flex: 0 0 auto;
  width: 40px;
  height: 40px;
  border-radius: 12px;
  display: grid;
  place-items: center;
}
.send-btn:disabled { opacity: 0.4; box-shadow: none; }
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
