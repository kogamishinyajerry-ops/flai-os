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
                <span class="plan-count">{{ m.recommendation.agents.length }} 个 Agent 协作</span>
              </div>
              <h2 v-if="m.recommendation.goal" class="plan-goal-title">{{ m.recommendation.goal }}</h2>
              <p v-if="m.recommendation.analysis" class="plan-reason">{{ m.recommendation.analysis }}</p>
              <div v-if="m.recommendation.workflow" class="plan-section">
                <div class="section-label">分工如何衔接</div>
                <p class="plan-workflow">{{ m.recommendation.workflow }}</p>
              </div>

              <div class="section-label roster-label">召集的 Agent · {{ m.recommendation.agents.length }}</div>
              <div class="agent-list">
                <div
                  v-for="(a, ai) in m.recommendation.agents"
                  :key="ai"
                  class="agent-card"
                  :class="{ 'fx-rise': m.fresh }"
                >
                  <div class="agent-accent" :style="{ background: categoryColor(a.category) }"></div>
                  <div class="agent-main">
                    <div class="agent-top">
                      <span class="agent-step">{{ ai + 1 }}</span>
                      <span class="agent-name">{{ a.agent_name }}</span>
                      <span
                        class="agent-pill"
                        :style="{ color: categoryColor(a.category), background: categoryColor(a.category) + '18' }"
                      >{{ categoryLabel(a.category) }}</span>
                      <span class="agent-maturity">{{ a.maturity }} / {{ a.status }}</span>
                    </div>

                    <!-- B1 对话轴督战：该会话已为此 Agent 召集过任务才显示（诚实地板，
                         未召集零占位）；点击直开任务速览，不逼人跳页看进度。 -->
                    <div
                      v-if="agentTaskInfo(a)"
                      class="agent-status"
                      role="button"
                      tabindex="0"
                      @click.stop="openTaskPeek(agentTaskInfo(a).latest.id)"
                      @keydown.enter.stop.prevent="openTaskPeek(agentTaskInfo(a).latest.id)"
                      @keydown.space.stop.prevent="openTaskPeek(agentTaskInfo(a).latest.id)"
                    >
                      <span
                        class="status-lamp"
                        :class="{ 'is-pulsing': isWorkState(agentTaskInfo(a).latest.status) }"
                        :style="{ background: taskLampColor(agentTaskInfo(a).latest.status) }"
                      ></span>
                      <span class="status-word" :style="{ color: taskLampColor(agentTaskInfo(a).latest.status) }">
                        {{ statusLabel(agentTaskInfo(a).latest.status) }}
                      </span>
                      <span v-if="agentTaskInfo(a).extra > 0" class="status-extra">+{{ agentTaskInfo(a).extra }}</span>
                      <!-- 行动召唤按态分级：待签发=amber 强 CTA（签发来找人）；其余=速览 -->
                      <span v-if="agentTaskInfo(a).latest.status === 'waiting_review'" class="status-peek is-review">审阅签发 →</span>
                      <span v-else class="status-peek">速览 →</span>
                    </div>

                    <!-- 产物锚点行（Claude Artifact 卡片锚点哲学）：任务完成且真有产物
                         才长出——点击同样直开速览（产物预览+签发同面板），零跳页。 -->
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

                    <p v-if="a.rationale" class="agent-rationale">{{ a.rationale }}</p>
                    <p v-if="a.role" class="agent-role"><span class="role-tag">分工</span>{{ a.role }}</p>
                    <div class="agent-draft">
                      <button
                        type="button"
                        class="draft-toggle"
                        :class="{ open: isDraftOpen(draftKey(idx, ai)) }"
                        @click="toggleDraft(draftKey(idx, ai))"
                      >
                        预填草案 · {{ inputCount(a) }} 个字段
                        <span class="draft-chevron">›</span>
                      </button>
                      <pre v-show="isDraftOpen(draftKey(idx, ai))" class="plan-json">{{ prettyInputs(a.prefilled_inputs) }}</pre>
                    </div>
                    <el-alert
                      v-if="a.stripped_fields && a.stripped_fields.length"
                      type="warning"
                      :closable="false"
                      show-icon
                      class="agent-stripped"
                      :title="`已剔除不合法字段：${a.stripped_fields.join('、')}（未匹配该 Agent 的输入契约）`"
                    />
                    <div class="agent-actions">
                      <button class="agent-cta" @click="createOneTask(a, m.recommendation)">去创建此任务</button>
                    </div>
                  </div>
                </div>
              </div>

              <el-alert
                v-if="m.recommendation.dropped_agents && m.recommendation.dropped_agents.length"
                type="warning"
                :closable="false"
                show-icon
                class="plan-alert"
                :title="`已剔除无法召集的 Agent：${m.recommendation.dropped_agents.join('、')}（幻觉/已下线/不可召集/重复）`"
              />
              <el-alert
                v-if="m.recommendation.capped"
                type="info"
                :closable="false"
                show-icon
                class="plan-alert"
                title="召集 Agent 数已达上限（5 个），后续提议已截断。"
              />

              <div class="plan-foot">
                <button class="workbench-btn" @click="openWorkbench">进入协作工作台 →</button>
                <button type="button" class="plan-escape" @click="focusComposer">想调整方案？直接告诉导引 ↓</button>
                <span class="plan-note">
                  在工作台里看分工架构、逐个召集 Agent、追进度——签发权始终在你，
                  每个任务都由你补全并<strong>亲手提交</strong>。
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
                  <span class="ap-name">{{ a.name }}</span>
                  <span class="ap-sub">{{ a.summary }}</span>
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
          <button class="send-btn" :disabled="sending || !draft.trim()" aria-label="发送" @click="send">
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
import { createConversation, postMessage, getConversation, listConversationTasks } from "../api/conversations";
import { listAgents } from "../api/agents";
import { uploadFile as apiUploadFile } from "../api/files";
import { categoryColor, categoryLabel, categoryTip, statusLabel, taskLampColor, TASK_WORK_STATES, formatTime } from "../utils/format";
import { getSavedName, saveName } from "../utils/identity";
import { openTaskPeek } from "../stores/statusCenter";
import { resolvedTheme } from "../stores/theme";
import ThinkingInk from "../components/artwork/ThinkingInk.vue";
import IntentGlyph from "../components/artwork/IntentGlyph.vue";

const router = useRouter();

const GUIDE_AGENT_ID = "guide_agent";
const MAX_FILES_PER_MESSAGE = 5; // 与后端 PostMessageRequest / 运行时同值

const createdBy = ref(getSavedName());
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

function prettyInputs(inputs) {
  return JSON.stringify(inputs || {}, null, 2);
}
function inputCount(agent) {
  return Object.keys(agent.prefilled_inputs || {}).length;
}

// 提问卡：预填 JSON 默认展开（与既有 e2e 契约对齐——协作方案卡片一出现，
// 预填字段/值需直接在 body 文本流可见，不依赖点击）；按「消息序号_Agent序号」
// 记"用户手动收起"状态，供想要降低视觉负担的人自行折叠（纯 UI 态，不影响
// prefilled_inputs 本身/不影响创建任务的调用签名）。
const collapsedDrafts = reactive(new Set());
function draftKey(msgIdx, agentIdx) {
  return `${msgIdx}_${agentIdx}`;
}
function isDraftOpen(key) {
  return !collapsedDrafts.has(key);
}
function toggleDraft(key) {
  if (collapsedDrafts.has(key)) collapsedDrafts.delete(key);
  else collapsedDrafts.add(key);
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
  if (restoring.value) return; // 会话恢复在途不收发言——防止意外新建会话
  const content = draft.value.trim();
  if (!content) return;
  if (!createdBy.value.trim()) {
    // 身份门保证有名字；此兜底只防 localStorage 被外部清空的边角
    ElMessage.error("身份已失效，请刷新页面重新留下称呼");
    return;
  }
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
      const conv = await createConversation({ agentId: GUIDE_AGENT_ID, createdBy: createdBy.value.trim() });
      saveName(createdBy.value); // 记住名字，全站免重填
      conversationId.value = conv.id;
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
    maybeStartTaskPoll(); // 本轮若刚给出 orchestrate 方案，开始为其召集状态保鲜
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
// 方案时才拉取，5s 链式轮询保鲜（TaskDetail/WorkbenchSession 同款纪律）。
const conversationTasks = ref([]);
let taskPollTimer = null;
let taskPollDisposed = false; // 卸载后 in-flight finally 不再续排（clearTaskPoll 拦不住已入 await 的那轮）

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

async function refreshConversationTasks(convId) {
  if (!convId) return;
  try {
    const tasks = await listConversationTasks(convId);
    // 轮询在途期间会话可能已切换：陈旧响应作废，绝不倒灌覆盖新会话的状态。
    if (convId !== conversationId.value) return;
    conversationTasks.value = tasks;
  } catch {
    // 轮询失败：诚实不覆盖已展示的上一次成功结果，下一 tick 自愈（非关键展示）。
  }
}

function clearTaskPoll() {
  if (taskPollTimer) {
    clearTimeout(taskPollTimer);
    taskPollTimer = null;
  }
}

function scheduleTaskPoll() {
  clearTaskPoll();
  taskPollTimer = setTimeout(async () => {
    try {
      if (!document.hidden) await refreshConversationTasks(conversationId.value);
    } finally {
      if (!taskPollDisposed) scheduleTaskPoll();
    }
  }, 5000);
}

// 只在真出现 orchestrate 方案时启动（幂等：已有轮询在跑则不重复起）。
function maybeStartTaskPoll() {
  if (taskPollTimer || !conversationId.value || !hasOrchestratePlan()) return;
  refreshConversationTasks(conversationId.value);
  scheduleTaskPoll();
}

// ── 会话恢复（左栏历史点击 / 刷新 /?c=<id>）──
const route = useRoute();

function resetToFresh(clearError = true) {
  messages.value = [];
  started.value = false;
  conversationId.value = "";
  draft.value = "";
  pendingFiles.value = [];
  conversationTasks.value = [];
  clearTaskPoll();
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
    started.value = true;
    // 具名沿用会话发起人——恢复后继续发言仍需具名，但 hero 的名字框已隐去。
    createdBy.value = conv.created_by || createdBy.value;
    messages.value = (conv.messages || []).map((m) => ({
      role: m.role,
      content: m.content,
      recommendation: m.recommendation || null,
      attachments: m.attachments && m.attachments.length ? m.attachments : undefined,
      createdAt: m.created_at || null,
    }));
    await scrollToBottom();
    maybeStartTaskPoll(); // 恢复的历史会话若已带 orchestrate 方案，立即接上轮询
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
  taskPollDisposed = true;
  clearTaskPoll();
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
  box-shadow: 0 1px 2px rgba(var(--ink-rgb), 0.06);
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
.section-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1.1px;
  text-transform: uppercase;
  color: var(--ink-faint);
  margin-bottom: 8px;
}
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
  transition: background-color 0.16s var(--ease-out-soft), border-color 0.16s var(--ease-out-soft);
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
  transition: transform 0.22s var(--ease-lift), box-shadow 0.22s var(--ease-lift), border-color 0.22s var(--ease-lift);
  /* 入场动效交给全局 .fx-rise（m.fresh 门控，见 template）——历史会话加载
   * 路径重挂载不重播「刚发生」视觉，理由同 .plan-card/.user-bubble。 */
}
.agent-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-card-hover);
  border-color: var(--border-warm-hover);
}
.agent-accent {
  flex: 0 0 auto;
  width: 3px;
  border-radius: 3px;
}
.agent-main { flex: 1 1 auto; min-width: 0; }
.agent-top {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.agent-step {
  flex: 0 0 auto;
  width: 27px;
  height: 27px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 13px;
  font-weight: 800;
  color: var(--clay);
  background: var(--clay-soft);
  border: 1.75px solid var(--clay);
}
.agent-name {
  font-weight: 700;
  font-size: 15px;
  color: var(--ink);
}
.agent-pill {
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.4px;
  padding: 2px 9px;
  border-radius: 999px;
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
  transition: color 0.16s var(--ease-lift);
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
  transition: border-color 0.16s var(--ease-lift), color 0.16s var(--ease-lift);
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
.draft-toggle {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--ink-faint);
  background: var(--paper-rail);
  border: 1px solid var(--hairline-soft);
  border-radius: 8px;
  padding: 5px 10px;
  cursor: pointer;
  transition: color 0.16s var(--ease-lift), border-color 0.16s var(--ease-lift), background 0.16s var(--ease-lift);
}
.draft-toggle:hover { color: var(--ink-soft); border-color: var(--hairline); }
.draft-toggle.open { color: var(--ink-soft); }
.draft-chevron {
  display: inline-block;
  transition: transform 0.18s var(--ease-lift);
}
.draft-toggle.open .draft-chevron { transform: rotate(90deg); }
.plan-json {
  margin: 8px 0 0;
  padding: 10px 12px;
  background: var(--paper-rail);
  border: 1px solid var(--hairline-soft);
  border-radius: 9px;
  font-family: "SF Mono", ui-monospace, monospace;
  font-size: 12px;
  color: var(--ink-mid);
  overflow-x: auto;
  white-space: pre;
}
.agent-stripped { margin-bottom: 10px; }
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
  transition: all 0.18s var(--ease-lift);
}
.agent-cta::after {
  content: "→";
  margin-left: 7px;
  transition: transform 0.18s var(--ease-lift);
}
.agent-cta:hover {
  background: var(--clay);
  color: #fff;
  border-color: var(--clay);
  box-shadow: 0 4px 12px rgba(var(--clay-rgb), 0.22);
}
.agent-cta:hover::after { transform: translateX(2px); }

.plan-alert { margin-top: 12px; }

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
  transition: transform 0.16s var(--ease-lift), box-shadow 0.16s var(--ease-lift);
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
  transition: color 0.16s var(--ease-lift), transform 0.16s var(--ease-lift);
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
  transition: border-color 0.2s var(--ease-lift), box-shadow 0.2s var(--ease-lift);
}
.composer-shell:focus-within {
  border-color: var(--focus-ring-clay);
  box-shadow: 0 2px 6px rgba(var(--ink-rgb), 0.06), 0 16px 40px rgba(var(--ink-rgb), 0.13), 0 0 0 4px rgba(var(--clay-rgb), 0.08);
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
  transition: all 0.18s var(--ease-lift);
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
  transition: transform 0.16s var(--ease-lift), box-shadow 0.16s var(--ease-lift), opacity 0.16s;
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
}

/* 诚实地板句（Claude「can make mistakes」哲学）：常驻同一 composer 容器内，
 * 会话进行中（composer 变 fixed 悬浮）也不消失；放进容器内部避免布局跳动。 */
@media (max-width: 640px) {
}
kbd {
  font-family: "SF Mono", ui-monospace, monospace;
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
