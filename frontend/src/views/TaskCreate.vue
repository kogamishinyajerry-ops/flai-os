<template>
  <div class="task-create">
    <div class="page-header">
      <h2>创建任务</h2>
    </div>

    <TaskCreateJourney :steps="createJourney" @navigate="navigateCreateStep" />

    <el-alert
      v-if="agentsListError"
      type="error"
      :title="`Agent 列表加载失败：${agentsListError}`"
      show-icon
      :closable="false"
      class="inline-alert"
    />

    <el-form :label-width="narrow ? '0' : '100px'" :label-position="narrow ? 'top' : 'right'" class="create-form fx-rise">
      <el-form-item ref="agentAnchor" label="Agent" required>
        <el-select
          v-model="form.agentId"
          placeholder="请选择 Agent"
          filterable
          :disabled="submitting"
          style="width: 100%"
          @change="handleAgentChange"
        >
          <el-option
            v-for="agent in selectableAgents"
            :key="agent.id"
            :label="`${agent.name}（${agent.id}）`"
            :value="agent.id"
            :disabled="agent.status === 'disabled'"
          />
        </el-select>
      </el-form-item>

      <el-alert
        v-if="agentLoadError"
        type="error"
        :title="agentLoadError"
        show-icon
        :closable="false"
        class="inline-alert"
      />

      <el-card v-if="activeAgent" ref="capabilityAnchor" class="agent-preview" shadow="never">
        <div class="agent-preview-header">
          <strong>{{ activeAgent.name }}</strong>
          <el-tag
            :type="statusTagType(activeAgent.status)"
            size="small"
            :title="agentStatusTip(activeAgent.status)"
          >
            {{ agentStatusLabel(activeAgent.status) }}
          </el-tag>
        </div>
        <p class="agent-preview-summary">{{ activeAgent.summary }}</p>
        <div v-if="activeAgent.limitations && activeAgent.limitations.length" class="agent-preview-limits">
          <span class="limits-label">不适用范围：</span>{{ activeAgent.limitations.join("；") }}
        </div>
      </el-card>

      <section v-if="activeAgent" ref="policyAnchor" class="create-policy" aria-label="本次任务策略边界">
        <div class="create-policy-item">
          <el-icon aria-hidden="true"><Lock /></el-icon>
          <span><strong>密级边界</strong><small>{{ clearancePolicyText }}</small></span>
        </div>
        <div class="create-policy-item">
          <el-icon aria-hidden="true"><DocumentChecked /></el-icon>
          <span><strong>依据要求</strong><small>{{ evidencePolicyText }}</small></span>
        </div>
        <div class="create-policy-item">
          <el-icon aria-hidden="true"><Warning /></el-icon>
          <span><strong>适用范围</strong><small>{{ limitationsPolicyText }}</small></span>
        </div>
        <p>任务由你亲手提交；提交不是签发。运行后是否进入待签发状态，以任务真实状态为准。</p>
      </section>

      <el-form-item label="任务名称">
        <!-- @input 清 nameWasPrefilled（R2 P2）：用户一旦手改任务名，即视为人工
             输入，后续预填重入不再撤它。程序化预填赋值不触发 @input，flag 不误清。 -->
        <el-input
          v-model="form.name"
          :disabled="submitting"
          placeholder="可选，便于在历史中辨认"
          @input="onNameInput"
        />
      </el-form-item>

      <el-form-item ref="inputAnchor" label="输入参数">
        <div class="inputs-field">
          <!-- 信任色锁（W7）：绿=仅真实结果，预填草案是「未核对」内容，不是已验证
               的真结果——success 绿在此处会误读成「已确认」，改 warning（amber
               未核语义）。文案逐字不动（m6 锚）。 -->
          <el-alert
            v-if="prefillOrigin"
            type="warning"
            :closable="false"
            show-icon
            class="prefill-note"
            :title="prefillBannerText"
          />

          <!-- 表单模式：按 Agent input_schema 动态生成带标签+校验的字段 -->
          <template v-if="activeAgent && schemaRenderable && !jsonMode">
            <!-- 入场动效只在「刚选中 Agent」时播（modeToggled 门控）：表单/JSON
                 来回切换是同一份数据换展示形态，不重播「刚落地」视觉（信任审 P2）。 -->
            <SchemaForm
              :schema="activeAgent.input_schema"
              :model="formInputs"
              :disabled="submitting"
              :class="{ 'fx-stagger': !modeToggled }"
            />
            <div v-if="inputsErrors.length" class="field-error">
              <div v-for="(e, i) in inputsErrors" :key="i">{{ e }}</div>
            </div>
            <div class="field-foot">
              <el-button text size="small" class="mode-toggle" :disabled="submitting" @click="toggleToJson">
                高级：直接编辑 JSON
              </el-button>
            </div>
          </template>

          <!-- JSON 模式 / schema 不可渲染时降级：入场只在刚选中 Agent 时播一次
               （modeToggled 门控同上）；不用 max-height 过渡。 -->
          <template v-else>
            <div :class="{ 'fx-rise': !modeToggled }">
              <div v-if="activeAgent && !schemaRenderable" class="field-hint json-fallback-note">
                该 Agent 的输入结构较复杂，请按其输入契约直接填写 JSON。
              </div>
              <el-input
                v-model="form.inputsText"
                type="textarea"
                :rows="8"
                :disabled="submitting"
                placeholder='请按该 Agent 的输入契约填写 JSON，例如：{"name": "张三"}'
              />
              <div v-if="inputsJsonError" class="field-error">{{ inputsJsonError }}</div>
              <div class="field-foot">
                <el-button
                  v-if="activeAgent && schemaRenderable"
                  text
                  size="small"
                  class="mode-toggle"
                  :disabled="submitting"
                  @click="toggleToForm"
                >
                  ← 用表单填写
                </el-button>
                <span v-if="!activeAgent" class="field-hint">请先在上方选择 Agent。</span>
              </div>
            </div>
          </template>
        </div>
      </el-form-item>

      <el-form-item label="附件">
        <el-upload
          :auto-upload="false"
          :show-file-list="false"
          :disabled="submitting"
          multiple
          :on-change="handleFileSelect"
        >
          <el-button :disabled="submitting">选择文件上传</el-button>
        </el-upload>
        <div v-if="uploadItems.length" class="upload-list">
          <div v-for="item in uploadItems" :key="item.uid" class="upload-item">
            <span class="upload-name">{{ item.name }}</span>
            <el-tag v-if="item.status === 'pending'" size="small">待上传</el-tag>
            <el-tag v-else-if="item.status === 'uploading'" type="info" size="small">上传中…</el-tag>
            <!-- 信任色锁：已上传=文件就位的中性事实，不是真实核验通过——不得用
                 success 绿（绿仅严格真实核验 REAL），改中性 info。文案不动（m6 锚）。 -->
            <el-tag v-else-if="item.status === 'done'" type="info" size="small">已上传</el-tag>
            <el-tag v-else type="danger" size="small">失败：{{ item.error }}</el-tag>
            <el-button size="small" text :disabled="submitting" @click="removeUploadItem(item)">移除</el-button>
          </div>
        </div>
        <div class="field-hint">文件在提交任务时才上传；提交前移除不产生任何服务端残留。</div>
      </el-form-item>

      <el-alert
        v-if="submitError"
        type="error"
        :title="submitError"
        show-icon
        :closable="false"
        class="inline-alert"
      />

      <el-form-item>
        <span ref="submitAnchor" class="submit-anchor">
          <el-button type="primary" :loading="submitting" :disabled="submitting" @click="handleSubmit">
            {{ uploadingFiles ? "上传附件中…" : "提交任务" }}
          </el-button>
        </span>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup>
import { reactive, ref, computed, watch, onMounted, onUnmounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { DocumentChecked, Lock, Warning } from "@element-plus/icons-vue";
import { listAgents, getAgent } from "../api/agents";
import { createTask } from "../api/tasks";
import { concludeConversation } from "../api/conversations";
import { uploadFile as apiUploadFile } from "../api/files";
import {
  agentStatusLabel,
  agentStatusTip,
  statusTagType,
} from "../utils/format";
import SchemaForm from "../components/SchemaForm.vue";
import TaskCreateJourney from "../components/TaskCreateJourney.vue";
import { parseSchema, blankInputs, collectInputs, validateInputs } from "../utils/schemaForm";
import {
  buildTaskCreateJourney,
  captureTaskSubmission,
} from "../utils/taskCreateVisual";

const route = useRoute();
const router = useRouter();

const agents = ref([]);
// interactive 型（导引）不作为一次性任务运行——从创建任务选择器剔除，避免用户
// 选中后只撞后端 409 死路（Codex P2 / ADR-0012）。
const selectableAgents = computed(() => agents.value.filter((a) => a.mode !== "interactive"));
const selectedAgent = ref(null);
const agentLoadError = ref("");
const agentsListError = ref("");
const inputsJsonError = ref("");
// P0-1：schema 驱动的结构化表单状态。formInputs 是交给 SchemaForm 就地读写的
// 响应式 values 对象；schemaRenderable=false 时降级回 JSON 手填（jsonMode）。
const formInputs = reactive({});
const schemaRenderable = ref(false);
const jsonMode = ref(false);
// 动效门控：刚选中 Agent=字段真「刚落地」播入场；此后表单/JSON 手动切换不重播
// （换展示形态≠新内容，诚实地板）。选中新 Agent 时复位。
const modeToggled = ref(false);
const inputsErrors = ref([]);
const submitting = ref(false);
const uploadingFiles = ref(false);
const submitError = ref("");
const uploadItems = ref([]);
let createRouteEpoch = 0;
let deferredPrefillRefresh = false;
// 预填来源（"" | guide | demo | retry）：guide=导引草案（m6 锚文案逐字不动）；
// demo=首登引导的 Hello 演示（评审 N2）；retry=失败任务「复制为新任务」
// （评审 N4a，带血缘 retry_of）。三种预填都是「机器带入待人核」内容，
// 横幅一律 warning（amber 未核语义，信任色锁）。
const prefillOrigin = ref("");
// N4a 血缘：本次创建若来自「复制为新任务」，记原任务 id，提交时随 createTask 落库。
const prefillRetryOf = ref(null);
// N4a 诚实附件提示（Codex 治理审 R0 P1）：原任务的输入文件不随重试带入（前端无法
// 分辨 kind=input/output，output 提交必 422=假绿），只记数量供横幅提示人重新添加。
const prefillHadFileCount = ref(0);
const prefillBannerText = computed(() => {
  if (prefillOrigin.value === "demo") {
    return "演示预填：Hello 示例 Agent 无业务含义——提交后可完整看到「排队 → 运行 → 产物落地」的真实生命周期。";
  }
  if (prefillOrigin.value === "retry") {
    const fileNote = prefillHadFileCount.value > 0
      ? `原任务有 ${prefillHadFileCount.value} 个输入文件未带入，请按需重新添加。`
      : "";
    return `已带入失败任务的原始输入（血缘 ${prefillRetryOf.value || "—"}）——请核对修正后重新提交，平台不会自动重跑。${fileNote}`;
  }
  return "已从智能导引带入预填草案，请核对并补全后再提交——签发权在你。";
});
// P0 手机端响应式：窄屏（<640px）标签置顶，避免固定 label-width 挤压输入区导致横向溢出。
const narrow = ref(false);
function onResize() {
  narrow.value = window.innerWidth < 640;
}
// M8：由导引协作会话带入的会话 id——提交任务时回填，使任务归到协作工作台的
// 同一次会话下。门户直建（无 from=guide）时保持 null。
const prefillConversationId = ref(null);
// 单 Agent 导引流程：任务创建成功后再归档本会话（异源 Codex R2-#3：会话 concluded 后
// API 真只读拒新任务，故归档必须后于创建，不能像旧流程那样先归档再跳创建页）。
const prefillConcludeAfter = ref(false);
// 提交飞入（批A T10）：提交成功、跳转前在提交按钮附近播一次 fx-rise（列表飞入感）。
const agentAnchor = ref(null);
const capabilityAnchor = ref(null);
const inputAnchor = ref(null);
const policyAnchor = ref(null);
const submitAnchor = ref(null);
let agentLoadSeq = 0;
const form = reactive({
  agentId: typeof route.query.agent_id === "string" ? route.query.agent_id : "",
  name: "",
  inputsText: "{}",
});
const activeAgent = computed(() =>
  selectedAgent.value?.id === form.agentId ? selectedAgent.value : null
);
const createJourney = computed(() => buildTaskCreateJourney({
  agentId: form.agentId,
  selectedAgent: activeAgent.value,
  agentsListError: agentsListError.value,
  agentLoadError: agentLoadError.value,
  prefillOrigin: prefillOrigin.value,
  schemaRenderable: schemaRenderable.value,
  jsonMode: jsonMode.value,
  inputsErrors: inputsErrors.value,
  inputsJsonError: inputsJsonError.value,
  uploadItems: uploadItems.value,
  submitting: submitting.value,
  uploadingFiles: uploadingFiles.value,
  submitError: submitError.value,
}));
const clearancePolicyText = computed(() => {
  const value = activeAgent.value?.clearance;
  if (value === "public") return "公开";
  if (value === "internal") return "内部";
  if (value === "sensitive") return "敏感";
  if (value === null || value === undefined) return "未声明，按内部数据上限保守处理";
  return "密级策略待核";
});
const evidencePolicyText = computed(() =>
  activeAgent.value?.evidence_policy_required === true
    ? "产物要求附依据"
    : activeAgent.value?.evidence_policy_required === false
      ? "未强制要求附依据"
      : "依据策略待核"
);
const limitationsPolicyText = computed(() =>
  Array.isArray(activeAgent.value?.limitations)
    ? `${activeAgent.value.limitations.length} 项不适用边界`
    : "不适用边界待核"
);
function anchorElement(anchor) {
  return anchor?.value?.$el || anchor?.value || null;
}
function navigateCreateStep(stepId) {
  const anchor = {
    agent: agentAnchor,
    capability: capabilityAnchor.value ? capabilityAnchor : agentAnchor,
    input: inputAnchor,
    policy: policyAnchor.value ? policyAnchor : agentAnchor,
    submit: submitAnchor,
  }[stepId];
  anchorElement(anchor)?.scrollIntoView({
    behavior: prefersReducedMotion() ? "auto" : "smooth",
    block: "center",
  });
}
function prefersReducedMotion() {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
function playSubmitRise() {
  return new Promise((resolve) => {
    if (prefersReducedMotion() || !submitAnchor.value) {
      resolve();
      return;
    }
    submitAnchor.value.classList.add("fx-rise");
    setTimeout(() => {
      if (submitAnchor.value) submitAnchor.value.classList.remove("fx-rise");
      resolve();
    }, 120);
  });
}

// M6 人确认接缝：从智能导引带入的预填草案（sessionStorage 传递，不走 URL）。
// 只带入 inputs，仍由人补全 + 亲手点「提交任务」——导引不代签（ADR-0012）。
// M7：会话附件随草案带入——已是 File Service 真实文件，以「已上传」状态入
// 附件列表（status:done + fileId），提交时直接进 input_file_ids；人可移除。
// 导引草案的 inputs 种子：用于在 Agent schema 加载后灌进结构化表单（仅目标 Agent 匹配时）。
let guidePrefill = null;
// 任务名是否由预填自动带入（vs 人工手输）：重入清理只撤自动带入的，不动手输。
let nameWasPrefilled = false;
// 用户手改任务名 → 转为人工输入，后续重入不再撤（R2 P2）。
function onNameInput() {
  nameWasPrefilled = false;
}

// 预填草案消费（可重入，Codex 治理审 R0 P2-5）：既在 setup 首次调用，也由下方
// watch 在「用户已在 /tasks/new、从全局 StatusCenter 再点重试只改 query 不重挂」
// 时重新调用——否则新草案永不被消费、旧表单残留。重入前先清掉上一次预填派生态
// （prefill 注入的 upload 项以 uid 前缀 guide_ 标识，只清这些不碰用户手加的）。
// 无条件重置全部预填派生态（Codex 治理审 R1 P2 → R2 P2）：抽成独立函数，供
// consumePrefillDraft 每次入口先调——**包括 from 不再是预填来源时**（retry URL
// 回到普通 /tasks/new），否则 retry_of/名称/会话关联会残留。conversation_id:null
// 靠「不覆盖」是漏的，必须显式清。
function resetPrefillState() {
  guidePrefill = null;
  prefillOrigin.value = "";
  prefillRetryOf.value = null;
  prefillHadFileCount.value = 0;
  prefillConversationId.value = null;
  prefillConcludeAfter.value = false;
  // 自动预填的任务名先撤（nameWasPrefilled 标识区分人工输入 vs 自动带入）——
  // 人工手输的名字绝不动（用户编辑后 @input 已把 flag 置 false）。
  if (nameWasPrefilled) {
    form.name = "";
    nameWasPrefilled = false;
  }
  uploadItems.value = uploadItems.value.filter((i) => !String(i.uid).startsWith("guide_"));
}

function consumePrefillDraft() {
  resetPrefillState(); // 无条件先重置——navigate away 也清干净
  if (!["guide", "demo", "retry"].includes(route.query.from)) return;
  try {
    const raw = sessionStorage.getItem("flai_prefill");
    if (raw) {
      const draft = JSON.parse(raw);
      const wantAgent =
        typeof route.query.agent_id === "string" ? route.query.agent_id : form.agentId;
      if (draft && draft.agent_id === wantAgent && draft.inputs) {
        form.agentId = draft.agent_id; // 同路由重试可能切到别的 Agent，同步表单选择
        form.inputsText = JSON.stringify(draft.inputs, null, 2);
        guidePrefill = { agentId: draft.agent_id, inputs: draft.inputs };
        prefillOrigin.value = route.query.from;
        // N4a：血缘/附件数/名称仅 retry 草案携带；名称尊重人未填时才带入（不覆盖手输）。
        if (typeof draft.retry_of === "string" && draft.retry_of) {
          prefillRetryOf.value = draft.retry_of;
        }
        if (typeof draft.had_file_count === "number") {
          prefillHadFileCount.value = draft.had_file_count;
        }
        if (typeof draft.name === "string" && draft.name && !form.name) {
          form.name = draft.name;
          nameWasPrefilled = true; // 标记为自动带入，重入时可撤（人工手输不动）
        }
        if (typeof draft.conversation_id === "string") {
          prefillConversationId.value = draft.conversation_id;
          // 单 Agent 草案带 conclude_after：提交成功后归档本会话（后于创建，见下）。
          prefillConcludeAfter.value = draft.conclude_after === true;
        }
        for (const f of Array.isArray(draft.files) ? draft.files : []) {
          if (f && f.id && f.name) {
            uploadItems.value.push(
              reactive({
                uid: `guide_${f.id}`,
                name: f.name,
                status: "done",
                raw: null,
                fileId: f.id,
                error: "",
              })
            );
          }
        }
      }
    }
  } catch {
    // 草案解析失败不阻断创建页——用户仍可手填
  } finally {
    sessionStorage.removeItem("flai_prefill");
  }
}
consumePrefillDraft();

async function loadAgents() {
  try {
    agents.value = await listAgents();
    agentsListError.value = "";
    if (form.agentId) {
      await handleAgentChange(form.agentId);
    }
  } catch (err) {
    // 持久 alert 而非瞬时 toast：toast 消失后空下拉框与「确实没有 Agent」
    // 无法区分（反方审查 P2-2，与其余页面口径一致）。
    agentsListError.value = err.detail || err.message;
  }
}

// 就地替换响应式对象的全部键（保持同一引用，使 SchemaForm 的 :model 绑定不断开）。
function replaceReactive(target, source) {
  for (const k of Object.keys(target)) delete target[k];
  Object.assign(target, source);
}

async function handleAgentChange(agentId) {
  const seq = ++agentLoadSeq;
  inputsErrors.value = [];
  inputsJsonError.value = "";
  agentLoadError.value = "";
  modeToggled.value = false; // 新 Agent 的字段区=真「刚落地」，恢复入场动效
  if (!agentId) {
    selectedAgent.value = null;
    schemaRenderable.value = false;
    return;
  }
  // 新选择到详情返回之间不继续展示旧 Agent 的能力/策略，避免视觉与 agentId
  // 短暂错配；请求世代守卫再阻止迟到响应覆盖新选择。
  selectedAgent.value = null;
  schemaRenderable.value = false;
  try {
    const detail = await getAgent(agentId);
    if (seq !== agentLoadSeq || form.agentId !== agentId) return;
    if (!detail || typeof detail !== "object" || detail.id !== agentId) {
      selectedAgent.value = null;
      schemaRenderable.value = false;
      agentLoadError.value = "Agent 信息身份不一致，请刷新后重试";
      return;
    }
    selectedAgent.value = detail;
  } catch (err) {
    if (seq !== agentLoadSeq || form.agentId !== agentId) return;
    selectedAgent.value = null;
    schemaRenderable.value = false;
    agentLoadError.value = err.detail || err.message;
    return;
  }
  const schema = selectedAgent.value ? selectedAgent.value.input_schema : null;
  schemaRenderable.value = parseSchema(schema).renderable;
  // 仅当草案目标 Agent 与当前一致时带入种子（一次性预填）。
  const seed = guidePrefill && guidePrefill.agentId === agentId ? guidePrefill.inputs : null;
  if (schemaRenderable.value) {
    replaceReactive(formInputs, blankInputs(schema, seed));
    jsonMode.value = false;
  } else {
    // schema 不可结构化 → JSON 模式；有种子则填入文本域。
    jsonMode.value = true;
    if (seed) form.inputsText = JSON.stringify(seed, null, 2);
  }
}

// 表单 → JSON：把当前结构化 values 序列化进文本域，切到高级模式。
function toggleToJson() {
  if (schemaRenderable.value && selectedAgent.value) {
    form.inputsText = JSON.stringify(collectInputs(selectedAgent.value.input_schema, formInputs), null, 2);
  }
  modeToggled.value = true; // 手动切换视图≠新内容，入场动效不再重播
  jsonMode.value = true;
}

// JSON → 表单：把文本域解析为种子回灌结构化表单；解析失败则留在 JSON 模式并报错。
function toggleToForm() {
  if (!schemaRenderable.value || !selectedAgent.value) return;
  let seed = {};
  try {
    seed = form.inputsText.trim() ? JSON.parse(form.inputsText) : {};
  } catch (err) {
    inputsJsonError.value = `JSON 解析失败：${err.message}，无法切回表单`;
    return;
  }
  inputsJsonError.value = "";
  replaceReactive(formInputs, blankInputs(selectedAgent.value.input_schema, seed));
  modeToggled.value = true;
  jsonMode.value = false;
}

// P2-A：选中文件只入列（status:"pending"，raw File 留在本地），提交时才上传——
// 杜绝「选中即上传」在移除/弃页/创建失败时留下的孤儿 blob。
let uploadSeq = 0;
function handleFileSelect(uploadFile) {
  if (submitting.value) return;
  uploadItems.value.push(
    reactive({
      uid: uploadFile.uid ?? `up_${++uploadSeq}`,
      name: uploadFile.name,
      status: "pending",
      raw: uploadFile.raw,
      fileId: null,
      error: "",
    })
  );
}

function removeUploadItem(item) {
  uploadItems.value = uploadItems.value.filter((i) => i.uid !== item.uid);
}

async function uploadPendingFiles(items) {
  // 顺序上传全部未完成项（含上一轮失败重试项）；任一失败即中止并如实报错。
  for (const item of items) {
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
      return item;
    }
  }
  return null;
}

async function handleSubmit() {
  if (!form.agentId) {
    ElMessage.error("请选择 Agent");
    return;
  }
  if (!selectedAgent.value || selectedAgent.value.id !== form.agentId) {
    ElMessage.error("Agent 信息仍在核对，请稍后再提交");
    return;
  }
  let inputs = {};
  if (schemaRenderable.value && !jsonMode.value && selectedAgent.value) {
    // 结构化表单模式：前端轻量校验兜前（真正判定仍由后端 fail-closed），再收集。
    const errs = validateInputs(selectedAgent.value.input_schema, formInputs);
    if (errs.length) {
      inputsErrors.value = errs;
      ElMessage.error(errs[0]);
      return;
    }
    inputsErrors.value = [];
    inputs = collectInputs(selectedAgent.value.input_schema, formInputs);
  } else {
    try {
      inputs = form.inputsText.trim() ? JSON.parse(form.inputsText) : {};
    } catch (err) {
      inputsJsonError.value = `inputs 不是合法 JSON：${err.message}`;
      return;
    }
    inputsJsonError.value = "";
  }
  submitError.value = "";
  const submitRouteEpoch = createRouteEpoch;
  const submissionDraft = captureTaskSubmission({
    form,
    inputs,
    uploadItems: uploadItems.value,
    conversationId: prefillConversationId.value,
    retryOf: prefillRetryOf.value,
    concludeAfter: prefillConcludeAfter.value,
    returnToChat: route.query.back === "chat",
  });

  submitting.value = true;
  try {
    if (submissionDraft.uploadItems.some((i) => i.status !== "done")) {
      uploadingFiles.value = true;
      const failed = await uploadPendingFiles(submissionDraft.uploadItems);
      uploadingFiles.value = false;
      if (failed) {
        // 持久错误提示（非瞬时 toast）：中止提交，已成的项保留 done 状态，
        // 用户可修正后重试（重试只补传未完成项）。
        submitError.value = `附件「${failed.name}」上传失败：${failed.error}，任务未创建`;
        return;
      }
    }

    const task = await createTask({
      agentId: submissionDraft.agentId,
      name: submissionDraft.name,
      inputs: submissionDraft.inputs,
      inputFileIds: submissionDraft.uploadItems
        .filter((i) => i.status === "done")
        .map((i) => i.fileId),
      conversationId: submissionDraft.conversationId,
      retryOf: submissionDraft.retryOf,
    });
    // 单 Agent 导引流程：任务已创建成功，此刻再归档本会话（fire-and-forget，归档失败
    // 不影响已建任务；多 Agent 由工作台「结束协作」显式归档）。必须后于 createTask——
    // 会话须在创建时仍 active（异源 Codex R2-#3：结束协作=真只读）。
    if (submissionDraft.concludeAfter && submissionDraft.conversationId) {
      concludeConversation(submissionDraft.conversationId).catch(() => {});
    }
    ElMessage.info("任务已创建");
    await playSubmitRise();
    // 上传/创建 await 期间若用户已打开另一份创建草案或离开本页，尊重后来的
    // 导航意图：旧任务照实创建，但不再用旧请求的自动跳转覆盖新位置。
    if (createRouteEpoch !== submitRouteEpoch || route.name !== "task-create") return;
    // 范式 2a 对话轴闭环：从导引来（back=chat）且会话仍活跃 → 回流对话，任务卡
    // 在流里原地亮起（Claude 式零跳页）。单 Agent conclude_after 已归档会话，
    // 回一个刚被归档的会话反而突兀——仍走详情页；工作台来的召集同样走详情页
    // （m8_collab_chain e2e 断言④=提交后落详情，该路径不带 back=chat）。
    if (submissionDraft.returnToChat && submissionDraft.conversationId && !submissionDraft.concludeAfter) {
      router.push({ path: "/", query: { c: submissionDraft.conversationId } });
    } else {
      router.push(`/tasks/${task.id}`);
    }
  } catch (err) {
    ElMessage.error(err.detail || err.message);
  } finally {
    uploadingFiles.value = false;
    submitting.value = false;
    // 同路由新草案在提交期间只排队、不提前消费 sessionStorage；旧请求收口后
    // 再消费当前最新 query，避免新 retry 草案被吞或污染旧任务快照。
    if (deferredPrefillRefresh) {
      deferredPrefillRefresh = false;
      if (route.name === "task-create") {
        consumePrefillDraft();
        if (["guide", "demo", "retry"].includes(route.query.from) && form.agentId) {
          handleAgentChange(form.agentId);
        }
      }
    }
  }
}

// P2-5（Codex 治理审 R0）：已在 /tasks/new 时从全局 StatusCenter 再点「复制为新
// 任务」，router.push 同路径只改 query、组件不重挂 → setup 不再跑、新草案不被消费。
// 监听预填相关 query 变化，重挂之外的同路由再入时重新消费草案并重载 Agent 表单。
// 无 immediate：首次进入由 setup 的 consumePrefillDraft() 处理，不重复消费。
watch(
  () => [route.query.from, route.query.agent_id, route.query.draft_id],
  () => {
    createRouteEpoch += 1;
    if (submitting.value) {
      deferredPrefillRefresh = true;
      return;
    }
    consumePrefillDraft();
    if (["guide", "demo", "retry"].includes(route.query.from) && form.agentId) {
      handleAgentChange(form.agentId);
    }
  }
);

onMounted(() => {
  loadAgents();
  onResize();
  window.addEventListener("resize", onResize);
});
onUnmounted(() => window.removeEventListener("resize", onResize));
</script>

<style scoped>
.task-create {
  max-width: 640px;
}
.page-header { margin-bottom: 20px; }
.page-header h2 {
  font-family: var(--serif);
  font-size: var(--fs-title);
  font-weight: 600;
  letter-spacing: 0.2px;
  margin: 0;
}
.inline-alert {
  margin-bottom: 16px;
}
.agent-preview {
  margin-bottom: 16px;
  background: var(--paper-rail);
}
.agent-preview-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.agent-preview-summary {
  margin: 0 0 6px;
  color: var(--ink-soft);
  font-size: 13px;
}
.agent-preview-limits {
  font-size: 12px;
  color: var(--ink-faint);
}
/* 策略边界区去盒化（批 B P1）：外框+三个内盒改为上下 hairline 分区 + 留白，
   图标与短文字标签成对保留；字号从 9-10.5px 提到可读的 11-12px。 */
.create-policy {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin: 0 0 18px 100px;
  padding: 12px 2px;
  border-top: 1px solid var(--hairline);
  border-bottom: 1px solid var(--hairline);
}
.create-policy-item {
  min-width: 0;
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.create-policy-item > .el-icon {
  flex: none;
  margin-top: 2px;
  color: var(--ink-soft);
  font-size: 15px;
}
.create-policy-item > span {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.create-policy-item strong {
  color: var(--ink);
  font-size: 12px;
  font-weight: 600;
}
.create-policy-item small {
  color: var(--ink-faint);
  font-size: 11px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}
.create-policy > p {
  grid-column: 1 / -1;
  margin: 0;
  padding-top: 10px;
  border-top: 1px solid var(--hairline-soft);
  color: var(--trust-pending);
  font-size: 11.5px;
  line-height: 1.5;
}
.limits-label {
  font-weight: 600;
}
.prefill-note {
  margin-bottom: 8px;
}
.field-error {
  color: var(--trust-fail);
  font-size: 12px;
  margin-top: 4px;
}
.field-hint {
  color: var(--ink-faint);
  font-size: 12px;
  margin-top: 4px;
}
.field-foot {
  margin-top: 8px;
}
.submit-anchor {
  display: inline-block;
}
.mode-toggle {
  color: var(--ink-faint);
  padding: 0;
}
.mode-toggle:hover {
  color: var(--clay);
}
.json-fallback-note {
  margin-bottom: 8px;
}
.upload-list {
  margin-top: 8px;
}
.upload-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 13px;
  /* 文件 chip hover 微反馈：transform-only，不改布局属性。 */
  transition: transform var(--motion-fast) var(--ease-out-soft);
}
.upload-item:hover {
  transform: translateX(3px);
}
.upload-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
@media (prefers-reduced-motion: reduce) {
  .upload-item:hover {
    transform: none;
  }
}
@media (max-width: 639px) {
  .create-policy {
    margin-left: 0;
    grid-template-columns: 1fr;
  }
}
</style>
