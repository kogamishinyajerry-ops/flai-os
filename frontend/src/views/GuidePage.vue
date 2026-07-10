<template>
  <div class="guide-page" :class="{ 'is-empty': !started && messages.length === 0 }">
    <!-- 起手 hero（未开始且无消息）：衬线问候 + 具名，随 composer 在视口垂直居中。 -->
    <div v-if="!started && messages.length === 0" class="guide-hero">
      <div class="hero-mark">导</div>
      <h1 class="hero-title">说说你要做的工程活儿</h1>
      <p class="hero-sub">
        导引会帮你分析、拆解，召集合适的一个或多个 Agent 协作并预填草案；平台接不住时也会直说、
        并告诉你怎么重述才可行——<strong>计划由你确认后亲手提交，导引不会替你创建或签发任务。</strong>
      </p>
      <div class="hero-starter">
        <el-input v-model="createdBy" placeholder="你的名字（对话需具名）" class="name-input" />
        <span class="starter-hint">先留个名字，在下方描述你的需求开始对话。</span>
      </div>
      <div class="hero-examples">
        <button v-for="(ex, i) in EXAMPLES" :key="i" class="ex-chip" @click="setExample(ex)">{{ ex }}</button>
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
        <div v-if="m.role === 'user'" class="user-bubble">
          <div class="user-text">{{ m.content }}</div>
          <div v-if="m.attachments && m.attachments.length" class="user-files">
            <span v-for="a in m.attachments" :key="a.id" class="file-chip">📎 {{ a.filename }}</span>
          </div>
        </div>

        <!-- 助手消息：小 mark + 流动排版，plan-card 内联渲染 -->
        <template v-else>
          <div class="ai-mark">导</div>
          <div class="ai-body">
            <div class="ai-name">智能导引</div>
            <p v-if="m.content" class="ai-lead">{{ m.content }}</p>

            <!-- 导引计划（M8 编排官）：refuse=显式拒绝 -->
            <div v-if="m.recommendation && m.recommendation.decision === 'refuse'" class="plan-card refuse">
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
                <ul class="plan-list">
                  <li v-for="(r, i) in m.recommendation.reframe" :key="i">{{ r }}</li>
                </ul>
              </div>
            </div>

            <!-- orchestrate=召集协作 -->
            <div
              v-else-if="m.recommendation && m.recommendation.decision === 'orchestrate'"
              class="plan-card"
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
                <div v-for="(a, ai) in m.recommendation.agents" :key="ai" class="agent-card">
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
                    <p v-if="a.role" class="agent-role"><span class="role-tag">分工</span>{{ a.role }}</p>
                    <p v-if="a.rationale" class="agent-rationale">{{ a.rationale }}</p>
                    <div class="agent-draft">
                      <div class="section-label">预填草案（{{ inputCount(a) }} 个字段，未必完整）</div>
                      <pre class="plan-json">{{ prettyInputs(a.prefilled_inputs) }}</pre>
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
          <span class="tdot"></span><span class="tdot"></span><span class="tdot"></span>
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
          <el-input
            v-model="draft"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 6 }"
            :disabled="sending"
            placeholder="描述你的工程需求，或回答导引的追问…"
            class="composer-input"
            @keydown.enter.exact.prevent="send"
          />
          <button class="send-btn" :disabled="sending || !draft.trim()" aria-label="发送" @click="send">
            <svg v-if="!sending" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M7 11l5-5 5 5M12 6v13"/></svg>
            <span v-else class="send-spin"></span>
          </button>
        </div>
      </div>
      <div class="composer-hint">
        <span>导引不会替你创建或签发任务</span>
        <span class="keys"><kbd>Enter</kbd> 发送<span class="sep">·</span><kbd>⇧ Enter</kbd> 换行<span class="sep">·</span>📎 可带附件</span>
      </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, nextTick, watch, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { createConversation, postMessage, getConversation } from "../api/conversations";
import { uploadFile as apiUploadFile } from "../api/files";
import { categoryColor, categoryLabel } from "../utils/format";

const router = useRouter();

const GUIDE_AGENT_ID = "guide_agent";
const MAX_FILES_PER_MESSAGE = 5; // 与后端 PostMessageRequest / 运行时同值

const createdBy = ref("");
const started = ref(false);
const conversationId = ref("");
const messages = ref([]);
const draft = ref("");
const sending = ref(false);
const pageError = ref("");
const streamEl = ref(null);
// 待发送附件（M7）：选中只入列（raw 留本地），发送时才上传——同 TaskCreate 的
// P2-A 反孤儿纪律；已上传项记 fileId，失败重试不重复上传。
const pendingFiles = ref([]);
let fileSeq = 0;

// 空状态示例提示（Claude 起手 chips）：点一下把示例填进输入框，用户再改再发。
const EXAMPLES = [
  "做双通道供电系统的控制逻辑和故障树分析",
  "给这批性能盘 case 做批量核算，出汇总",
  "查一下供电系统适航规范的相关依据",
];
function setExample(text) {
  draft.value = text;
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

async function scrollToBottom() {
  // 会话流走自然页面流（不再是内嵌定长滚动框）——把最新一条滚到视口顶部起读，
  // 让高高的协作方案卡从「目标句」开始展开，而不是被塞进 62vh 的小盒里。
  await nextTick();
  const last = streamEl.value && streamEl.value.lastElementChild;
  if (last) last.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function send() {
  const content = draft.value.trim();
  if (!content) return;
  if (!createdBy.value.trim()) {
    ElMessage.error("请先在上方填写你的名字");
    return;
  }
  pageError.value = "";

  // 乐观追加用户气泡（附件 chips 一并显示；失败整体回滚）
  const optimisticAttachments = pendingFiles.value.map((f) => ({ id: f.uid, filename: f.name }));
  messages.value.push({
    role: "user",
    content,
    attachments: optimisticAttachments.length ? optimisticAttachments : undefined,
  });
  draft.value = "";
  await scrollToBottom();

  sending.value = true;
  try {
    // 先传附件（已 done 的跳过，失败即中止——本轮消息不发送）
    const fileIds = await uploadPendingFiles();
    if (!conversationId.value) {
      const conv = await createConversation({ agentId: GUIDE_AGENT_ID, createdBy: createdBy.value.trim() });
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
    });
    await scrollToBottom();
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
  router.push({ path: "/tasks/new", query: { agent_id: agent.agent_id, from: "guide" } });
}

// ── 会话恢复（左栏历史点击 / 刷新 /?c=<id>）──
const route = useRoute();

function resetToFresh(clearError = true) {
  messages.value = [];
  started.value = false;
  conversationId.value = "";
  draft.value = "";
  pendingFiles.value = [];
  if (clearError) pageError.value = "";
}

async function loadConversation(id) {
  resetToFresh();
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
    }));
    await scrollToBottom();
  } catch (err) {
    pageError.value = err.detail || err.message || "会话加载失败";
  }
}

onMounted(() => {
  const c = route.query.c;
  if (typeof c === "string" && c) loadConversation(c);
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
  padding-bottom: 152px; /* 让会话内容避开固定悬浮 composer */
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
  animation: rise 0.5s var(--ease-lift) both;
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
  box-shadow: 0 6px 18px rgba(193, 95, 60, 0.28);
}
.hero-title {
  font-family: var(--serif);
  font-size: 30px;
  font-weight: 600;
  color: var(--ink);
  margin: 0 0 14px;
  letter-spacing: 0.3px;
}
.hero-sub {
  max-width: 560px;
  margin: 0 auto 24px;
  color: var(--ink-soft);
  font-size: 14.5px;
  line-height: 1.72;
}
.hero-sub strong {
  color: var(--ink);
  font-weight: 600;
}
.hero-starter {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.name-input {
  max-width: 280px;
}
.starter-hint {
  color: var(--ink-faint);
  font-size: 12.5px;
}
.hero-examples {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: center;
  margin-top: 26px;
}
.ex-chip {
  font-size: 13px;
  color: var(--ink-soft);
  background: var(--surface-raised);
  border: 1px solid var(--hairline);
  border-radius: 999px;
  padding: 8px 16px;
  cursor: pointer;
  box-shadow: var(--shadow-card);
  transition: transform 0.16s var(--ease-lift), box-shadow 0.16s var(--ease-lift), border-color 0.16s var(--ease-lift), color 0.16s var(--ease-lift);
}
.ex-chip:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-card-hover);
  border-color: var(--clay-softer);
  color: var(--clay);
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
  background: linear-gradient(180deg, #fbeee7, #f7e6dc);
  border: 1px solid #f0d8ca;
  color: #5b3524;
  padding: 12px 16px;
  border-radius: 18px 18px 4px 18px;
  box-shadow: 0 1px 2px rgba(140, 70, 40, 0.06);
  animation: rise 0.4s var(--ease-lift) both;
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
.ai-thinking .tdot {
  width: 6px; height: 6px; border-radius: 50%; background: var(--clay);
  opacity: 0.4; animation: blink 1.2s infinite both;
}
.ai-thinking .tdot:nth-child(2) { animation-delay: 0.2s; }
.ai-thinking .tdot:nth-child(3) { animation-delay: 0.4s; }
.ai-thinking .tlabel { margin-left: 6px; }
@keyframes blink { 0%, 80%, 100% { opacity: 0.35; } 40% { opacity: 1; } }

/* ── 协作方案 / 拒绝 卡片 ── */
.plan-card {
  background: var(--surface);
  border: 1px solid var(--hairline);
  border-radius: 18px;
  padding: 22px 24px 20px;
  box-shadow: var(--shadow-card);
  animation: rise 0.5s var(--ease-lift) both;
}
.plan-card.refuse {
  background: linear-gradient(180deg, #fdf8ef, var(--surface));
  border-color: #efdcbb;
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
  color: #4a443d;
  font-size: 13.5px;
  line-height: 1.65;
}
.plan-list {
  margin: 0;
  padding-left: 20px;
  color: #4a443d;
  font-size: 13.5px;
  line-height: 1.75;
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
  animation: rise 0.55s var(--ease-lift) both;
}
.agent-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-card-hover);
  border-color: #e4d8c8;
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
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 11px;
  font-weight: 700;
  color: var(--ink-soft);
  background: var(--paper-rail);
  border: 1px solid var(--hairline);
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
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--ink-soft);
  margin: 0 0 10px;
}
.agent-draft { margin-bottom: 10px; }
.plan-json {
  margin: 0;
  padding: 10px 12px;
  background: var(--paper-rail);
  border: 1px solid var(--hairline-soft);
  border-radius: 9px;
  font-family: "SF Mono", ui-monospace, monospace;
  font-size: 12px;
  color: #4a443d;
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
  border: 1px solid #e6c9bb;
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
  box-shadow: 0 4px 12px rgba(193, 95, 60, 0.22);
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
  box-shadow: 0 4px 12px rgba(193, 95, 60, 0.24);
  transition: transform 0.16s var(--ease-lift), box-shadow 0.16s var(--ease-lift);
}
.workbench-btn:hover { transform: translateY(-1px); box-shadow: 0 6px 16px rgba(193, 95, 60, 0.3); }
.plan-note {
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
.file-chip.error { color: var(--trust-fail); border-color: #e6bcbc; background: #faeeee; }
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
  background: linear-gradient(180deg, rgba(250, 247, 242, 0) 0%, rgba(250, 247, 242, 0.88) 42%, var(--page-bg) 74%);
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
  border-color: #dcb6a4;
  box-shadow: 0 2px 6px rgba(43, 38, 34, 0.06), 0 16px 40px rgba(72, 58, 44, 0.13), 0 0 0 4px rgba(193, 95, 60, 0.08);
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
  box-shadow: 0 4px 12px rgba(193, 95, 60, 0.28);
  transition: transform 0.16s var(--ease-lift), box-shadow 0.16s var(--ease-lift), opacity 0.16s;
}
.send-btn:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 6px 16px rgba(193, 95, 60, 0.34); }
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
.composer-hint .keys { display: flex; align-items: center; gap: 6px; }
.composer-hint .sep { color: var(--hairline); }
kbd {
  font-family: "SF Mono", ui-monospace, monospace;
  font-size: 10.5px;
  background: var(--paper-rail);
  border: 1px solid var(--hairline);
  border-radius: 5px;
  padding: 1px 5px;
  color: var(--ink-soft);
}

@keyframes rise {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: none; }
}

@media (max-width: 640px) {
  .ai-body { max-width: calc(100% - 44px); }
  .plan-goal-title { font-size: 21px; }
  .agent-maturity { display: none; }
}
</style>
