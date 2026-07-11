<template>
  <div class="task-create">
    <h2>创建任务</h2>

    <el-alert
      v-if="agentsListError"
      type="error"
      :title="`Agent 列表加载失败：${agentsListError}`"
      show-icon
      :closable="false"
      class="inline-alert"
    />

    <el-form label-width="100px" class="create-form fx-rise">
      <el-form-item label="Agent" required>
        <el-select
          v-model="form.agentId"
          placeholder="请选择 Agent"
          filterable
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

      <el-card v-if="selectedAgent" class="agent-preview" shadow="never">
        <div class="agent-preview-header">
          <strong>{{ selectedAgent.name }}</strong>
          <el-tag :type="statusTagType(selectedAgent.status)" size="small">
            {{ statusLabel(selectedAgent.status) }}
          </el-tag>
        </div>
        <p class="agent-preview-summary">{{ selectedAgent.summary }}</p>
        <div v-if="selectedAgent.limitations && selectedAgent.limitations.length" class="agent-preview-limits">
          <span class="limits-label">不适用范围：</span>{{ selectedAgent.limitations.join("；") }}
        </div>
      </el-card>

      <el-form-item label="任务名称">
        <el-input v-model="form.name" placeholder="可选，便于在历史中辨认" />
      </el-form-item>

      <el-form-item label="创建人" required>
        <el-input v-model="form.createdBy" placeholder="你的名字" />
      </el-form-item>

      <el-form-item label="输入参数">
        <div class="inputs-field">
          <el-alert
            v-if="prefilledFromGuide"
            type="success"
            :closable="false"
            show-icon
            class="prefill-note"
            title="已从智能导引带入预填草案，请核对并补全后再提交——签发权在你。"
          />

          <!-- 表单模式：按 Agent input_schema 动态生成带标签+校验的字段 -->
          <template v-if="selectedAgent && schemaRenderable && !jsonMode">
            <!-- 入场动效只在「刚选中 Agent」时播（modeToggled 门控）：表单/JSON
                 来回切换是同一份数据换展示形态，不重播「刚落地」视觉（信任审 P2）。 -->
            <SchemaForm
              :schema="selectedAgent.input_schema"
              :model="formInputs"
              :disabled="submitting"
              :class="{ 'fx-stagger': !modeToggled }"
            />
            <div v-if="inputsErrors.length" class="field-error">
              <div v-for="(e, i) in inputsErrors" :key="i">{{ e }}</div>
            </div>
            <div class="field-foot">
              <el-button text size="small" class="mode-toggle" @click="toggleToJson">
                高级：直接编辑 JSON
              </el-button>
            </div>
          </template>

          <!-- JSON 模式 / schema 不可渲染时降级：入场只在刚选中 Agent 时播一次
               （modeToggled 门控同上）；不用 max-height 过渡。 -->
          <template v-else>
            <div :class="{ 'fx-rise': !modeToggled }">
              <div v-if="selectedAgent && !schemaRenderable" class="field-hint json-fallback-note">
                该 Agent 的输入结构较复杂，请按其输入契约直接填写 JSON。
              </div>
              <el-input
                v-model="form.inputsText"
                type="textarea"
                :rows="8"
                placeholder='请按该 Agent 的输入契约填写 JSON，例如：{"name": "张三"}'
              />
              <div v-if="inputsJsonError" class="field-error">{{ inputsJsonError }}</div>
              <div class="field-foot">
                <el-button
                  v-if="selectedAgent && schemaRenderable"
                  text
                  size="small"
                  class="mode-toggle"
                  @click="toggleToForm"
                >
                  ← 用表单填写
                </el-button>
                <span v-if="!selectedAgent" class="field-hint">请先在上方选择 Agent。</span>
              </div>
            </div>
          </template>
        </div>
      </el-form-item>

      <el-form-item label="附件">
        <el-upload :auto-upload="false" :show-file-list="false" multiple :on-change="handleFileSelect">
          <el-button>选择文件上传</el-button>
        </el-upload>
        <div v-if="uploadItems.length" class="upload-list">
          <div v-for="item in uploadItems" :key="item.uid" class="upload-item">
            <span class="upload-name">{{ item.name }}</span>
            <el-tag v-if="item.status === 'pending'" size="small">待上传</el-tag>
            <el-tag v-else-if="item.status === 'uploading'" type="info" size="small">上传中…</el-tag>
            <el-tag v-else-if="item.status === 'done'" type="success" size="small">已上传</el-tag>
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
        <el-button type="primary" :loading="submitting" @click="handleSubmit">
          {{ uploadingFiles ? "上传附件中…" : "提交任务" }}
        </el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup>
import { reactive, ref, computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { listAgents, getAgent } from "../api/agents";
import { createTask } from "../api/tasks";
import { concludeConversation } from "../api/conversations";
import { uploadFile as apiUploadFile } from "../api/files";
import { statusLabel, statusTagType } from "../utils/format";
import SchemaForm from "../components/SchemaForm.vue";
import { parseSchema, blankInputs, collectInputs, validateInputs } from "../utils/schemaForm";
import { getSavedName, saveName } from "../utils/identity";

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
const prefilledFromGuide = ref(false);
// M8：由导引协作会话带入的会话 id——提交任务时回填，使任务归到协作工作台的
// 同一次会话下。门户直建（无 from=guide）时保持 null。
const prefillConversationId = ref(null);
// 单 Agent 导引流程：任务创建成功后再归档本会话（异源 Codex R2-#3：会话 concluded 后
// API 真只读拒新任务，故归档必须后于创建，不能像旧流程那样先归档再跳创建页）。
const prefillConcludeAfter = ref(false);

const form = reactive({
  agentId: typeof route.query.agent_id === "string" ? route.query.agent_id : "",
  name: "",
  createdBy: getSavedName(),
  inputsText: "{}",
});

// M6 人确认接缝：从智能导引带入的预填草案（sessionStorage 传递，不走 URL）。
// 只带入 inputs，仍由人补全 + 亲手点「提交任务」——导引不代签（ADR-0012）。
// M7：会话附件随草案带入——已是 File Service 真实文件，以「已上传」状态入
// 附件列表（status:done + fileId），提交时直接进 input_file_ids；人可移除。
// 导引草案的 inputs 种子：用于在 Agent schema 加载后灌进结构化表单（仅目标 Agent 匹配时）。
let guidePrefill = null;

if (route.query.from === "guide") {
  try {
    const raw = sessionStorage.getItem("flai_prefill");
    if (raw) {
      const draft = JSON.parse(raw);
      if (draft && draft.agent_id === form.agentId && draft.inputs) {
        form.inputsText = JSON.stringify(draft.inputs, null, 2);
        guidePrefill = { agentId: draft.agent_id, inputs: draft.inputs };
        prefilledFromGuide.value = true;
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
  inputsErrors.value = [];
  inputsJsonError.value = "";
  modeToggled.value = false; // 新 Agent 的字段区=真「刚落地」，恢复入场动效
  if (!agentId) {
    selectedAgent.value = null;
    schemaRenderable.value = false;
    return;
  }
  agentLoadError.value = "";
  try {
    selectedAgent.value = await getAgent(agentId);
  } catch (err) {
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

async function uploadPendingFiles() {
  // 顺序上传全部未完成项（含上一轮失败重试项）；任一失败即中止并如实报错。
  for (const item of uploadItems.value) {
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
  if (!form.createdBy.trim()) {
    ElMessage.error("请填写创建人");
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

  submitting.value = true;
  try {
    if (uploadItems.value.some((i) => i.status !== "done")) {
      uploadingFiles.value = true;
      const failed = await uploadPendingFiles();
      uploadingFiles.value = false;
      if (failed) {
        // 持久错误提示（非瞬时 toast）：中止提交，已成的项保留 done 状态，
        // 用户可修正后重试（重试只补传未完成项）。
        submitError.value = `附件「${failed.name}」上传失败：${failed.error}，任务未创建`;
        return;
      }
    }

    const task = await createTask({
      agentId: form.agentId,
      name: form.name.trim() || null,
      inputs,
      inputFileIds: uploadItems.value.filter((i) => i.status === "done").map((i) => i.fileId),
      createdBy: form.createdBy.trim(),
      conversationId: prefillConversationId.value,
    });
    // 单 Agent 导引流程：任务已创建成功，此刻再归档本会话（fire-and-forget，归档失败
    // 不影响已建任务；多 Agent 由工作台「结束协作」显式归档）。必须后于 createTask——
    // 会话须在创建时仍 active（异源 Codex R2-#3：结束协作=真只读）。
    if (prefillConcludeAfter.value && prefillConversationId.value) {
      concludeConversation(prefillConversationId.value).catch(() => {});
    }
    saveName(form.createdBy); // 记住名字，全站免重填
    ElMessage.success("任务已创建");
    // 范式 2a 对话轴闭环：从导引来（back=chat）且会话仍活跃 → 回流对话，任务卡
    // 在流里原地亮起（Claude 式零跳页）。单 Agent conclude_after 已归档会话，
    // 回一个刚被归档的会话反而突兀——仍走详情页；工作台来的召集同样走详情页
    // （m8_collab_chain e2e 断言④=提交后落详情，该路径不带 back=chat）。
    if (route.query.back === "chat" && prefillConversationId.value && !prefillConcludeAfter.value) {
      router.push({ path: "/", query: { c: prefillConversationId.value } });
    } else {
      router.push(`/tasks/${task.id}`);
    }
  } catch (err) {
    ElMessage.error(err.detail || err.message);
  } finally {
    uploadingFiles.value = false;
    submitting.value = false;
  }
}

onMounted(loadAgents);
</script>

<style scoped>
.task-create {
  max-width: 640px;
}
.task-create > h2 {
  font-family: var(--serif);
  font-size: 25px;
  font-weight: 600;
  letter-spacing: 0.2px;
  margin: 0 0 16px;
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
.limits-label {
  font-weight: 600;
}
.prefill-note {
  margin-bottom: 8px;
}
.field-error {
  color: #f56c6c;
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
</style>
