<template>
  <div class="guide-page">
    <div class="page-header">
      <h2>智能导引</h2>
      <p class="page-sub">
        说说你要做的工程活儿（可带附件），导引会帮你分析、拆解，召集合适的一个或
        多个 Agent 协作并预填草案；平台接不住时也会直说、并告诉你怎么重述才可行——
        <strong>计划由你确认后亲手提交，导引不会替你创建或签发任务。</strong>
      </p>
    </div>

    <el-alert
      v-if="pageError"
      type="error"
      :title="pageError"
      show-icon
      :closable="false"
      class="page-alert"
    />

    <div v-if="!started" class="starter">
      <el-input v-model="createdBy" placeholder="你的名字（对话需具名）" class="name-input" />
      <p class="starter-hint">先留个名字，然后在下方描述你的需求开始对话。</p>
    </div>

    <div ref="streamEl" class="chat-stream">
      <div v-for="(m, idx) in messages" :key="idx" :class="['bubble-row', m.role]">
        <div class="bubble">
          <div class="bubble-role">{{ m.role === "user" ? "你" : "导引" }}</div>
          <div class="bubble-text">{{ m.content }}</div>
          <div v-if="m.attachments && m.attachments.length" class="bubble-files">
            <el-tag v-for="a in m.attachments" :key="a.id" size="small" type="info" effect="plain">
              📎 {{ a.filename }}
            </el-tag>
          </div>

          <!-- 导引计划（M8 编排官）：refuse=显式拒绝 / orchestrate=召集协作 -->
          <div v-if="m.recommendation && m.recommendation.decision === 'refuse'" class="plan-card">
            <div class="plan-bar refuse"></div>
            <div class="plan-inner">
              <div class="plan-head">
                <span class="plan-title">这个需求，平台暂时接不住</span>
                <span class="plan-tag refuse">显式拒绝</span>
              </div>
              <p v-if="m.recommendation.reason" class="plan-reason">{{ m.recommendation.reason }}</p>
              <div v-if="m.recommendation.residual_problems && m.recommendation.residual_problems.length" class="plan-block">
                <div class="plan-block-label">你手上仍未解决的问题</div>
                <ul class="plan-list">
                  <li v-for="(p, i) in m.recommendation.residual_problems" :key="i">{{ p }}</li>
                </ul>
              </div>
              <div v-if="m.recommendation.reframe && m.recommendation.reframe.length" class="plan-block">
                <div class="plan-block-label">可以试试这样重述 / 拆解</div>
                <ul class="plan-list">
                  <li v-for="(r, i) in m.recommendation.reframe" :key="i">{{ r }}</li>
                </ul>
              </div>
            </div>
          </div>

          <div v-else-if="m.recommendation && m.recommendation.decision === 'orchestrate'" class="plan-card">
            <div class="plan-bar"></div>
            <div class="plan-inner">
              <div class="plan-head">
                <span class="plan-title">协作方案</span>
                <span class="plan-tag">{{ m.recommendation.agents.length }} 个 Agent 协作</span>
              </div>
              <p v-if="m.recommendation.goal" class="plan-goal"><strong>目标：</strong>{{ m.recommendation.goal }}</p>
              <p v-if="m.recommendation.analysis" class="plan-analysis">{{ m.recommendation.analysis }}</p>
              <div v-if="m.recommendation.workflow" class="plan-block">
                <div class="plan-block-label">分工如何衔接</div>
                <p class="plan-workflow">{{ m.recommendation.workflow }}</p>
              </div>

              <div class="agent-list">
                <div v-for="(a, ai) in m.recommendation.agents" :key="ai" class="agent-card">
                  <div class="agent-bar" :style="{ background: categoryColor(a.category) }"></div>
                  <div class="agent-inner">
                    <div class="agent-head">
                      <span class="agent-name">{{ a.agent_name }}</span>
                      <span
                        class="agent-pill"
                        :style="{ color: categoryColor(a.category), background: categoryColor(a.category) + '18' }"
                      >{{ categoryLabel(a.category) }}</span>
                      <el-tag size="small" type="info" effect="plain">{{ a.maturity }} / {{ a.status }}</el-tag>
                    </div>
                    <p v-if="a.role" class="agent-role"><strong>分工：</strong>{{ a.role }}</p>
                    <p v-if="a.rationale" class="agent-rationale">{{ a.rationale }}</p>
                    <div class="agent-block">
                      <div class="plan-block-label">预填草案（{{ inputCount(a) }} 个字段，未必完整）</div>
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
                      <el-button type="primary" size="small" @click="createOneTask(a, m.recommendation)">
                        去创建此任务
                      </el-button>
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

              <p class="plan-note">
                签发权在你——每个任务都在创建页由你补全并<strong>亲手提交</strong>。
                多 Agent 一键召集进协作工作台正在建设中（M8 P3/P4）。
              </p>
            </div>
          </div>
        </div>
      </div>

      <div v-if="sending" class="bubble-row assistant">
        <div class="bubble thinking">导引思考中…</div>
      </div>
    </div>

    <div class="composer">
      <div v-if="pendingFiles.length" class="composer-files">
        <el-tag
          v-for="f in pendingFiles"
          :key="f.uid"
          size="small"
          closable
          :type="f.status === 'error' ? 'danger' : 'info'"
          :title="f.status === 'error' ? f.error : ''"
          @close="removePendingFile(f)"
        >
          📎 {{ f.name }}{{ f.status === "error" ? "（上传失败）" : "" }}
        </el-tag>
      </div>
      <div class="composer-row">
        <el-upload :auto-upload="false" :show-file-list="false" multiple :on-change="handleFileSelect" :disabled="sending">
          <el-button :disabled="sending" title="添加附件（≤5 个/条；文本类直读、xlsx 预览，详见导引说明）">📎</el-button>
        </el-upload>
        <el-input
          v-model="draft"
          type="textarea"
          :rows="2"
          :disabled="sending"
          placeholder="描述你的工程需求，或回答导引的追问…（Enter 发送，Shift+Enter 换行；可用 📎 带附件）"
          @keydown.enter.exact.prevent="send"
        />
        <el-button type="primary" :loading="sending" :disabled="!draft.trim()" @click="send">发送</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, nextTick } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { createConversation, postMessage, concludeConversation } from "../api/conversations";
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
  await nextTick();
  if (streamEl.value) streamEl.value.scrollTop = streamEl.value.scrollHeight;
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

function createOneTask(agent, plan) {
  // 人确认接缝：把某个被召集 Agent 的预填草案交给创建任务页，由人补全后亲手
  // 提交（导引绝不代签）。走 sessionStorage 而非 URL，避免工程数据进查询串。
  // M7：会话附件随草案带走，创建页以「已上传」状态入列，人可移除。
  sessionStorage.setItem(
    "flai_prefill",
    JSON.stringify({ agent_id: agent.agent_id, inputs: agent.prefilled_inputs || {}, files: collectCarriedFiles() })
  );
  // 单 Agent 计划：确认即归档会话（保留 M6 行为，fire-and-forget，归档失败不阻断）。
  // 多 Agent 计划：可能还要为其它 Agent 逐个建任务，故本步不归档会话——会话
  // 生命周期与「一键召集进协作工作台」由 M8 P3/P4 统一接管。
  if (plan && Array.isArray(plan.agents) && plan.agents.length === 1 && conversationId.value) {
    concludeConversation(conversationId.value).catch(() => {});
  }
  router.push({ path: "/tasks/new", query: { agent_id: agent.agent_id, from: "guide" } });
}
</script>

<style scoped>
.page-header {
  margin-bottom: 16px;
}
.page-header h2 {
  margin: 0 0 4px;
}
.page-sub {
  margin: 0;
  color: var(--ink-soft);
  font-size: 13px;
  line-height: 1.6;
}
.page-alert {
  margin-bottom: 12px;
}
.starter {
  margin-bottom: 12px;
}
.name-input {
  max-width: 260px;
}
.starter-hint {
  margin: 6px 0 0;
  color: var(--ink-soft);
  font-size: 12px;
}
.chat-stream {
  min-height: 320px;
  max-height: 56vh;
  overflow-y: auto;
  padding: 8px 4px 4px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.bubble-row {
  display: flex;
}
.bubble-row.user {
  justify-content: flex-end;
}
.bubble-row.assistant {
  justify-content: flex-start;
}
.bubble {
  max-width: 78%;
  border-radius: 12px;
  padding: 10px 14px;
  border: 1px solid var(--hairline);
  background: var(--card-bg);
}
.bubble-row.user .bubble {
  background: var(--clay-soft);
  border-color: #e9d3c7;
}
.bubble-role {
  font-size: 11px;
  font-weight: 700;
  color: var(--ink-soft);
  margin-bottom: 4px;
}
.bubble-text {
  white-space: pre-wrap;
  color: var(--ink);
  font-size: 14px;
  line-height: 1.6;
}
.thinking {
  color: var(--ink-soft);
  font-size: 13px;
  font-style: italic;
}
.plan-card {
  margin-top: 12px;
  border: 1px solid var(--hairline);
  border-radius: 10px;
  overflow: hidden;
  background: #fff;
}
.plan-bar {
  height: 4px;
  width: 100%;
  background: var(--clay);
}
.plan-bar.refuse {
  background: var(--trust-pending);
}
.plan-inner {
  padding: 12px 14px;
}
.plan-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.plan-title {
  font-weight: 700;
  color: var(--ink);
  font-size: 14px;
}
.plan-tag {
  font-size: 12px;
  font-weight: 600;
  padding: 2px 9px;
  border-radius: 999px;
  color: var(--clay);
  background: var(--clay-soft);
}
.plan-tag.refuse {
  color: var(--trust-pending);
  background: #f6edd8;
}
.plan-goal {
  margin: 0 0 6px;
  color: var(--ink);
  font-size: 13.5px;
  line-height: 1.6;
}
.plan-analysis,
.plan-reason {
  margin: 0 0 10px;
  color: #606266;
  font-size: 13px;
  line-height: 1.6;
}
.plan-block {
  margin: 0 0 10px;
}
.plan-block-label {
  font-size: 12px;
  color: var(--ink-soft);
  margin-bottom: 4px;
}
.plan-workflow {
  margin: 0;
  color: #4a443d;
  font-size: 13px;
  line-height: 1.6;
}
.plan-list {
  margin: 0;
  padding-left: 20px;
  color: #4a443d;
  font-size: 13px;
  line-height: 1.7;
}
.plan-json {
  margin: 0;
  padding: 10px 12px;
  background: #faf7f2;
  border: 1px solid var(--hairline);
  border-radius: 8px;
  font-family: "SF Mono", ui-monospace, monospace;
  font-size: 12.5px;
  color: #4a443d;
  overflow-x: auto;
  white-space: pre;
}
.agent-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 10px 0;
}
.agent-card {
  border: 1px solid var(--hairline);
  border-radius: 9px;
  overflow: hidden;
  background: var(--paper-cream);
}
.agent-bar {
  height: 3px;
  width: 100%;
}
.agent-inner {
  padding: 10px 12px;
}
.agent-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.agent-name {
  font-weight: 700;
  color: var(--ink);
  font-size: 13.5px;
}
.agent-pill {
  font-size: 11.5px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
}
.agent-role {
  margin: 0 0 4px;
  color: var(--ink);
  font-size: 13px;
  line-height: 1.5;
}
.agent-rationale {
  margin: 0 0 8px;
  color: #606266;
  font-size: 12.5px;
  line-height: 1.5;
}
.agent-block {
  margin-bottom: 8px;
}
.agent-stripped {
  margin-bottom: 8px;
}
.agent-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}
.plan-alert {
  margin-top: 8px;
}
.plan-note {
  margin: 10px 0 0;
  color: var(--ink-soft);
  font-size: 12px;
  line-height: 1.6;
}
.composer {
  margin-top: 12px;
}
.composer-row {
  display: flex;
  gap: 10px;
  align-items: flex-end;
}
.composer-row .el-textarea {
  flex: 1;
}
.composer-files {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}
.bubble-files {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}
</style>
