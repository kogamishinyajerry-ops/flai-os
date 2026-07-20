<template>
  <article v-if="eligible" class="design-comparison-panel" aria-labelledby="design-comparison-title">
    <header class="panel-header">
      <div>
        <p class="eyebrow">Open Design 窄试运行候选</p>
        <h3 id="design-comparison-title">现状与候选逐帧比较</h3>
      </div>
      <span v-if="busy || loading" class="activity-state" role="status">
        <span class="activity-pulse" aria-hidden="true"></span>
        正在同步服务端状态
      </span>
    </header>

    <section v-if="policyStopMessage" class="panel-policy-stop" role="status" aria-live="polite">
      <strong>策略停点</strong>
      <p>{{ policyStopMessage }}</p>
    </section>

    <el-alert
      v-if="errorMessage"
      class="panel-error"
      type="error"
      :title="errorMessage"
      :closable="false"
      show-icon
    >
      <template #default>
        <el-button text type="primary" :disabled="busy || loading" @click="retryComparisonLoad">
          重新加载比较
        </el-button>
      </template>
    </el-alert>

    <div v-if="loading && !comparison" class="loading-copy">正在建立一任务一候选的服务端对照…</div>

    <template v-else-if="comparison">
      <section class="comparison-summary" aria-label="候选比较摘要">
        <div class="summary-line">
          <div class="summary-line">
            <span class="candidate-status">候选资产 · 尚未发布</span>
            <span :class="phaseClass">{{ phaseLabel }}</span>
          </div>
          <span v-if="isTrialNotAttested" class="trial-provenance">LOOPBACK TRIAL · 未证明生产就绪</span>
        </div>
        <dl class="summary-grid">
          <div>
            <dt>唯一候选</dt>
            <dd><code>{{ comparison.candidate.candidate_id }}</code></dd>
          </div>
          <div>
            <dt>发布槽位</dt>
            <dd>{{ comparison.candidate.asset_slot }}</dd>
          </div>
          <div>
            <dt>目标 PNG</dt>
            <dd><code>{{ comparison.target.relative_path }}</code></dd>
          </div>
          <div>
            <dt>比较摘要</dt>
            <dd><code>{{ comparison.comparison_sha256 }}</code></dd>
          </div>
        </dl>
        <a
          class="candidate-download"
          :href="downloadUrl(comparison.candidate.asset_file_id)"
          download
        >下载原始候选 PNG</a>
      </section>

      <section class="frame-section" aria-labelledby="frame-matrix-title">
        <div class="section-heading">
          <div>
            <p class="step-kicker">对照矩阵</p>
            <h4 id="frame-matrix-title">同 viewport / state / theme 并排核对</h4>
          </div>
          <span class="frame-count">{{ comparison.frames.length }} 组服务端 PNG</span>
        </div>

        <article v-for="frame in comparison.frames" :key="frame.frame_id" class="frame-card">
          <header class="frame-meta">
            <code>{{ frame.slot_id }}</code>
            <strong>{{ frame.state }}</strong>
            <span>{{ frame.viewport.width }} × {{ frame.viewport.height }} @{{ frame.viewport.dpr }}x</span>
            <span>{{ frame.theme }}</span>
            <span>{{ frame.locale }}</span>
          </header>
          <div class="frame-pair">
            <figure>
              <figcaption>当前资产</figcaption>
              <img
                :src="frame.current.url"
                :alt="`${frame.state} ${frame.theme} 当前资产 PNG`"
                loading="lazy"
                decoding="async"
              />
              <p class="hash-line">SHA-256 <code>{{ frame.current.sha256 }}</code></p>
            </figure>
            <figure class="candidate-frame">
              <figcaption>候选资产 · 被动扫描通过</figcaption>
              <img
                :src="frame.candidate.url"
                :alt="`${frame.state} ${frame.theme} 候选资产 PNG`"
                loading="lazy"
                decoding="async"
              />
              <p class="hash-line">SHA-256 <code>{{ frame.candidate.sha256 }}</code></p>
            </figure>
          </div>
        </article>
      </section>

      <section class="gate-card candidate-gate" aria-labelledby="candidate-gate-title">
        <div class="gate-number">1</div>
        <div class="gate-body">
          <div class="section-heading">
            <div>
              <p class="step-kicker">人工候选选择</p>
              <h4 id="candidate-gate-title">候选审批（不是发布批准）</h4>
            </div>
            <span v-if="comparison.phase === 'candidate_pending'" class="candidate-status">待候选审批</span>
            <span v-else-if="comparison.phase === 'candidate_rejected'" class="rejected-state">候选已驳回</span>
            <span v-else class="approved-status">候选已批准</span>
          </div>
          <p class="gate-copy">
            这里只判断这一个候选是否值得进入发布申请。批准候选不会批准发布，也不会写入目标 PNG。
          </p>

          <div v-if="selection" class="decision-evidence" :class="selection.action === 'approve' ? 'named-human' : 'rejected-state'">
            <strong>{{ selection.action === "approve" ? "候选批准人" : "候选驳回人" }}</strong>
            {{ selection.selected_by.display_name }}（{{ selection.selected_by.username }}）
            · {{ formatTimestamp(selection.created_at) }}
            <p v-if="selection.comment">{{ selection.comment }}</p>
          </div>

          <template v-if="comparison.phase === 'candidate_pending' && !selection">
            <el-input
              v-model="candidateApproveComment"
              type="textarea"
              :rows="2"
              maxlength="2000"
              show-word-limit
              :disabled="busy"
              placeholder="候选批准说明（可选）"
            />
            <div class="gate-actions">
              <el-button class="signed-action" :loading="busyAction === 'candidate-approve'" :disabled="busy" @click="approveCandidate">
                批准这个候选
              </el-button>
              <el-button type="danger" plain :disabled="busy" @click="candidateRejectOpen = true">
                驳回这个候选
              </el-button>
            </div>
            <div v-if="candidateRejectOpen" class="reject-form">
              <el-select v-model="candidateRejectReason" :disabled="busy" placeholder="选择候选驳回原因">
                <el-option
                  v-for="option in DESIGN_REJECTION_REASON_OPTIONS"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
              <el-input
                v-model="candidateRejectComment"
                type="textarea"
                :rows="2"
                maxlength="2000"
                show-word-limit
                :disabled="busy"
                :placeholder="candidateRejectReason === 'other' ? '其他原因必须具体说明' : '候选驳回说明（可选）'"
              />
              <div class="gate-actions">
                <el-button type="danger" :loading="busyAction === 'candidate-reject'" :disabled="busy || !candidateRejectReady" @click="rejectCandidate">
                  确认驳回候选
                </el-button>
                <el-button :disabled="busy" @click="candidateRejectOpen = false">再看看</el-button>
              </div>
            </div>
          </template>

        </div>
      </section>

      <section v-if="selection?.action === 'approve'" class="gate-card" aria-labelledby="release-request-title">
        <div class="gate-number">2</div>
        <div class="gate-body">
          <div class="section-heading">
            <div>
              <p class="step-kicker">发布申请</p>
              <h4 id="release-request-title">把已批准候选提交为发布摘要</h4>
            </div>
            <span v-if="comparison.phase === 'candidate_approved'" class="candidate-status">待创建申请</span>
            <span v-else-if="comparison.phase === 'release_pending'" class="candidate-status">等待发布批准</span>
            <span v-else-if="comparison.phase === 'release_rejected'" class="rejected-state">发布申请已驳回</span>
            <span v-else class="approved-status">发布申请已锁定</span>
          </div>
          <p class="gate-copy">
            申请会锁定候选 SHA-256、比较 SHA-256 与目标前像；它不是发布批准，也不会自动发布。
          </p>
          <dl class="hash-proof">
            <div>
              <dt>候选 SHA-256</dt>
              <dd><code>{{ comparison.candidate.asset_sha256 }}</code></dd>
            </div>
            <div>
              <dt>目标前像</dt>
              <dd><code>{{ targetPreimageLabel }}</code></dd>
            </div>
          </dl>
          <el-button
            v-if="comparison.phase === 'candidate_approved' && !releaseRequest"
            :loading="busyAction === 'release-request'"
            :disabled="busy"
            @click="requestRelease"
          >创建发布申请</el-button>
          <div v-if="releaseRequest" class="request-evidence">
            申请人 {{ releaseRequest.requested_by.display_name }}（{{ releaseRequest.requested_by.username }}）
            · 摘要 <code>{{ releaseRequest.summary_sha256 }}</code>
          </div>
        </div>
      </section>

      <section v-if="releaseRequest" class="gate-card release-gate" aria-labelledby="release-decision-title">
        <div class="gate-number">3</div>
        <div class="gate-body">
          <div class="section-heading">
            <div>
              <p class="step-kicker">具名发布判断</p>
              <h4 id="release-decision-title">发布批准（不会自动发布）</h4>
            </div>
            <span v-if="!releaseDecision" class="candidate-status">待具名批准</span>
            <span v-else-if="releaseDecision.action === 'approve'" class="approved-status">发布已批准</span>
            <span v-else class="rejected-state">发布已驳回</span>
          </div>
          <p class="gate-copy">
            发布批准是独立的人类判断。它锁定发布包，但仍不会改写目标；实际写入还需要下一步显式确认。
          </p>

          <div v-if="releaseDecision" class="decision-evidence" :class="releaseDecision.action === 'approve' ? 'named-human' : 'rejected-state'">
            <strong>{{ releaseDecision.action === "approve" ? "发布批准人" : "发布驳回人" }}</strong>
            {{ releaseDecision.decided_by.display_name }}（{{ releaseDecision.decided_by.username }}）
            · {{ formatTimestamp(releaseDecision.created_at) }}
            <p v-if="releaseDecision.comment">{{ releaseDecision.comment }}</p>
          </div>

          <template v-else-if="comparison.phase === 'release_pending'">
            <el-input
              v-model="releaseApproveComment"
              type="textarea"
              :rows="2"
              maxlength="2000"
              show-word-limit
              :disabled="busy"
              placeholder="发布批准说明（可选）"
            />
            <div class="gate-actions">
              <el-button class="signed-action" :loading="busyAction === 'release-approve'" :disabled="busy" @click="approveRelease">
                批准发布摘要
              </el-button>
              <el-button type="danger" plain :disabled="busy" @click="releaseRejectOpen = true">
                驳回发布摘要
              </el-button>
            </div>
            <div v-if="releaseRejectOpen" class="reject-form">
              <el-select v-model="releaseRejectReason" :disabled="busy" placeholder="选择发布驳回原因">
                <el-option
                  v-for="option in DESIGN_REJECTION_REASON_OPTIONS"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
              <el-input
                v-model="releaseRejectComment"
                type="textarea"
                :rows="2"
                maxlength="2000"
                show-word-limit
                :disabled="busy"
                :placeholder="releaseRejectReason === 'other' ? '其他原因必须具体说明' : '发布驳回说明（可选）'"
              />
              <div class="gate-actions">
                <el-button type="danger" :loading="busyAction === 'release-reject'" :disabled="busy || !releaseRejectReady" @click="rejectRelease">
                  确认驳回发布摘要
                </el-button>
                <el-button :disabled="busy" @click="releaseRejectOpen = false">再看看</el-button>
              </div>
            </div>
          </template>
        </div>
      </section>

      <section v-if="releaseDecision?.action === 'approve'" class="gate-card publish-gate" aria-labelledby="publish-title">
        <div class="gate-number">4</div>
        <div class="gate-body">
          <div class="section-heading">
            <div>
              <p class="step-kicker">目标写入</p>
              <h4 id="publish-title">显式发布确认</h4>
            </div>
            <span v-if="comparison.phase === 'publish_ready'" class="approved-status">等待显式发布</span>
            <span v-else-if="comparison.phase === 'manual_intervention'" class="candidate-status">人工介入</span>
            <span v-else-if="comparison.phase === 'published'" class="neutral-status">已发布</span>
            <span v-else-if="comparison.phase === 'rolled_back'" class="neutral-status">已回退</span>
          </div>
          <el-alert
            v-if="comparison.phase === 'manual_intervention'"
            type="warning"
            title="需要人工介入核对发布事务"
            description="服务端已停止自动推进。请核对发布意图、目标文件与审计记录；本页不会重试发布或提供回退按钮。"
            :closable="false"
            show-icon
          />
          <p class="gate-copy">
            只有此步会按发布包写入 allowlist 中的目标 PNG。请再次核对包摘要与目标前像；勾选不是批准动作的替代。
          </p>
          <dl class="hash-proof">
            <div>
              <dt>发布包 SHA-256</dt>
              <dd><code>{{ releasePackageSha256 }}</code></dd>
            </div>
            <div>
              <dt>目标前像</dt>
              <dd><code>{{ targetPreimageLabel }}</code></dd>
            </div>
          </dl>
          <template v-if="comparison.phase === 'publish_ready' && !publishResult && !rollbackResult">
            <el-checkbox v-model="publishConfirmed" :disabled="busy">
              我确认按以上精确摘要发布到该 PNG 目标
            </el-checkbox>
            <div class="gate-actions">
              <el-button
                type="primary"
                :loading="busyAction === 'publish'"
                :disabled="busy || !publishConfirmed"
                @click="publishRelease"
              >按精确哈希发布</el-button>
            </div>
          </template>
          <div v-if="publishResult" class="publish-evidence">
            发布执行人 {{ publishResult.published_by.display_name }}（{{ publishResult.published_by.username }}）
            · 写入后 SHA-256 <code>{{ publishResult.after_sha256 }}</code>
          </div>

          <div v-if="comparison.phase === 'published' && publishResult" class="rollback-box">
            <h5>回退已发布资产</h5>
            <p>回退绑定当前已发布 SHA-256 与原发布包 SHA-256；若目标已变化，服务端会以 409 停止。</p>
            <el-checkbox v-model="rollbackConfirmed" :disabled="busy">
              我确认回退当前精确发布版本
            </el-checkbox>
            <div class="gate-actions">
              <el-button
                plain
                :loading="busyAction === 'rollback'"
                :disabled="busy || !rollbackConfirmed"
                @click="rollbackRelease"
              >按精确哈希回退</el-button>
            </div>
          </div>
          <div v-if="rollbackResult" class="publish-evidence">
            回退执行人 {{ rollbackResult.rolled_back_by.display_name }}（{{ rollbackResult.rolled_back_by.username }}）
            · 回退后 {{ rollbackResult.after_sha256 || "目标恢复为空" }}
          </div>
        </div>
      </section>
    </template>
  </article>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { ElMessageBox } from "element-plus";
import {
  createDesignComparison,
  createDesignReleaseRequest,
  decideDesignReleaseRequest,
  getDesignComparison,
  publishDesignRelease,
  rollbackDesignRelease,
  sensitiveCandidateRoleAxisMessage,
  submitDesignSelection,
} from "../api/designPromotions.js";
import { downloadUrl } from "../api/files.js";
import {
  DESIGN_REJECTION_REASON_OPTIONS,
  DesignPromotionValidationError,
  createDesignPromotionRequestId,
  isOpenDesignProductionCandidateTask,
} from "../utils/designPromotionCore.js";

const props = defineProps({
  task: { type: Object, required: true },
});

const eligible = computed(() => isOpenDesignProductionCandidateTask(props.task));
const comparison = ref(null);
const selection = ref(null);
const releaseRequest = ref(null);
const releaseDecision = ref(null);
const publishResult = ref(null);
const rollbackResult = ref(null);
const loading = ref(false);
const busyAction = ref("");
const busy = computed(() => busyAction.value !== "");
const errorMessage = ref("");
const policyStopMessage = ref("");

const candidateApproveComment = ref("");
const candidateRejectOpen = ref(false);
const candidateRejectReason = ref("");
const candidateRejectComment = ref("");
const releaseApproveComment = ref("");
const releaseRejectOpen = ref(false);
const releaseRejectReason = ref("");
const releaseRejectComment = ref("");
const publishConfirmed = ref(false);
const rollbackConfirmed = ref(false);

const candidateRejectReady = computed(() =>
  Boolean(candidateRejectReason.value) &&
  (candidateRejectReason.value !== "other" || candidateRejectComment.value.trim() !== ""),
);
const releaseRejectReady = computed(() =>
  Boolean(releaseRejectReason.value) &&
  (releaseRejectReason.value !== "other" || releaseRejectComment.value.trim() !== ""),
);
const isTrialNotAttested = computed(() =>
  comparison.value?.provenance?.mock === false &&
  comparison.value?.provenance?.production_readiness === "trial_not_attested",
);
const phaseLabel = computed(() => ({
  candidate_pending: "候选待审批",
  candidate_rejected: "候选已驳回",
  candidate_approved: "候选已批准",
  release_pending: "发布申请待审批",
  release_rejected: "发布申请已驳回",
  publish_ready: "发布已批准，待显式执行",
  published: "目标已发布",
  rolled_back: "目标已回退",
  manual_intervention: "发布事务需人工介入",
})[comparison.value?.phase] || "状态未核");
const phaseClass = computed(() => ({
  candidate_pending: "candidate-status",
  release_pending: "candidate-status",
  manual_intervention: "candidate-status",
  candidate_rejected: "rejected-state",
  release_rejected: "rejected-state",
  candidate_approved: "approved-status",
  publish_ready: "approved-status",
  published: "neutral-status",
  rolled_back: "neutral-status",
})[comparison.value?.phase] || "candidate-status");
const targetPreimageLabel = computed(() => {
  const preimage = comparison.value?.target?.preimage;
  return preimage?.kind === "present" ? preimage.sha256 : "absent（目标原先不存在）";
});
const releasePackageSha256 = computed(() =>
  releaseDecision.value?.release_package?.release_package_sha256 || "",
);

function formatTimestamp(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

function exactTargetPreimage() {
  const preimage = comparison.value.target.preimage;
  return preimage.kind === "present"
    ? { kind: "present", sha256: preimage.sha256 }
    : { kind: "absent" };
}

function requireMatch(condition, message, field) {
  if (!condition) throw new DesignPromotionValidationError(message, field);
}

function bindWorkflow(comparison) {
  const workflow = comparison.workflow;
  selection.value = workflow.selection;
  releaseRequest.value = workflow.release_request;
  releaseDecision.value = workflow.release_decision;
  publishResult.value = workflow.latest_publish?.state === "published"
    ? workflow.latest_publish
    : null;
  rollbackResult.value = workflow.latest_publish?.state === "rolled_back"
    ? workflow.latest_publish
    : null;
  publishConfirmed.value = false;
  rollbackConfirmed.value = false;
}

function bindComparison(next, previous = comparison.value) {
  requireMatch(next.task_id === props.task.id, "比较记录不属于当前任务", "task_id");
  if (previous) {
    requireMatch(next.comparison_id === previous.comparison_id, "任务出现了第二个比较记录", "comparison_id");
    requireMatch(
      next.candidate.candidate_id === previous.candidate.candidate_id,
      "任务出现了第二个候选",
      "candidate_id",
    );
    requireMatch(
      next.comparison_sha256 === previous.comparison_sha256,
      "不可变比较摘要发生漂移",
      "comparison_sha256",
    );
  }
  comparison.value = next;
  bindWorkflow(next);
}

function clearComparisonSnapshot() {
  comparison.value = null;
  selection.value = null;
  releaseRequest.value = null;
  releaseDecision.value = null;
  publishResult.value = null;
  rollbackResult.value = null;
  publishConfirmed.value = false;
  rollbackConfirmed.value = false;
}

let loadEpoch = 0;
async function initializeComparison() {
  const epoch = ++loadEpoch;
  clearComparisonSnapshot();
  errorMessage.value = "";
  policyStopMessage.value = "";
  if (!eligible.value) return;
  loading.value = true;
  try {
    const next = await createDesignComparison({
      requestId: createDesignPromotionRequestId(),
      taskId: props.task.id,
    });
    if (epoch !== loadEpoch) return;
    bindComparison(next, null);
  } catch (err) {
    if (epoch !== loadEpoch) return;
    const isolationMessage = sensitiveCandidateRoleAxisMessage(err);
    if (isolationMessage) {
      policyStopMessage.value = `候选已生成，但需角色轴/受证明隔离后才能比较。前端已停止加载帧与发布动作，不会绕过服务端隔离要求。服务端说明：${isolationMessage}`;
    } else {
      errorMessage.value = errorText(err, "无法建立候选比较");
    }
  } finally {
    if (epoch === loadEpoch) loading.value = false;
  }
}

async function reloadComparison() {
  if (!comparison.value) return false;
  const previous = comparison.value;
  const next = await getDesignComparison(previous.comparison_id);
  bindComparison(next, previous);
  return true;
}

async function handleReload() {
  if (busy.value || !comparison.value) return;
  busyAction.value = "reload";
  try {
    await reloadComparison();
    errorMessage.value = "";
    policyStopMessage.value = "";
  } catch (err) {
    const isolationMessage = sensitiveCandidateRoleAxisMessage(err);
    if (isolationMessage) {
      policyStopMessage.value = `候选已生成，但需角色轴/受证明隔离后才能比较。前端已停止加载帧与发布动作，不会绕过服务端隔离要求。服务端说明：${isolationMessage}`;
      errorMessage.value = "";
    } else {
      errorMessage.value = errorText(err, "重新加载比较失败，仍保持停止状态");
    }
    clearComparisonSnapshot();
  } finally {
    busyAction.value = "";
  }
}

async function retryComparisonLoad() {
  if (policyStopMessage.value) return;
  if (comparison.value) {
    await handleReload();
  } else {
    await initializeComparison();
  }
}

function errorText(err, prefix) {
  const detail = err?.detail || err?.message || "未知错误";
  return `${prefix}：${detail}`;
}

async function recoverAfterError(err) {
  const isolationMessage = sensitiveCandidateRoleAxisMessage(err);
  if (isolationMessage) {
    policyStopMessage.value = `候选已生成，但需角色轴/受证明隔离后才能比较。前端已停止加载帧与发布动作，不会绕过服务端隔离要求。服务端说明：${isolationMessage}`;
    errorMessage.value = "";
    clearComparisonSnapshot();
    return;
  } else if (err.status === 409) {
    errorMessage.value = "状态冲突（409）或精确哈希已过期：已停止提交，并重新加载服务端比较；请按当前状态重试。";
  } else if (err instanceof DesignPromotionValidationError) {
    errorMessage.value = `服务端返回缺字段、错字段或不安全状态，前端已 fail-closed 停止：${err.message}`;
  } else {
    errorMessage.value = errorText(err, "操作失败，未显示成功状态");
  }
  if (comparison.value) {
    try {
      await reloadComparison();
    } catch (reloadErr) {
      errorMessage.value += ` 重新加载比较也失败：${reloadErr?.detail || reloadErr?.message || "未知错误"}`;
      clearComparisonSnapshot();
    }
  }
}

async function runMutation(name, operation) {
  if (busy.value) return false;
  busyAction.value = name;
  errorMessage.value = "";
  policyStopMessage.value = "";
  try {
    await operation();
    return true;
  } catch (err) {
    await recoverAfterError(err);
    return false;
  } finally {
    busyAction.value = "";
  }
}

async function approveCandidate() {
  try {
    await ElMessageBox.confirm(
      "本动作只批准当前候选进入发布申请，不批准发布，也不会写入目标 PNG。是否继续？",
      "确认候选审批",
      { type: "warning", confirmButtonText: "批准候选", cancelButtonText: "再看看" },
    );
  } catch {
    return;
  }
  await decideCandidate("approve");
}

async function rejectCandidate() {
  await decideCandidate("reject");
}

async function decideCandidate(action) {
  await runMutation(`candidate-${action}`, async () => {
    const expected = comparison.value;
    requireMatch(expected?.phase === "candidate_pending", "候选已不在待审批状态", "phase");
    const result = await submitDesignSelection(expected.comparison_id, {
      requestId: createDesignPromotionRequestId(),
      action,
      expectedComparisonSha256: expected.comparison_sha256,
      candidateId: action === "approve" ? expected.candidate.candidate_id : null,
      reasonCode: action === "reject" ? candidateRejectReason.value : null,
      comment: action === "reject" ? candidateRejectComment.value : candidateApproveComment.value,
    });
    requireMatch(result.comparison_id === expected.comparison_id, "候选判断返回了错误比较记录", "comparison_id");
    requireMatch(result.comparison_sha256 === expected.comparison_sha256, "候选判断摘要不一致", "comparison_sha256");
    requireMatch(result.task_id === props.task.id, "候选判断返回了错误任务", "task_id");
    requireMatch(result.action === action, "候选判断动作与请求不一致", "action");
    if (action === "approve") {
      requireMatch(result.candidate_id === expected.candidate.candidate_id, "批准记录候选不一致", "candidate_id");
      requireMatch(result.candidate_sha256 === expected.candidate.asset_sha256, "批准记录候选摘要不一致", "candidate_sha256");
    }
    candidateRejectOpen.value = false;
    await reloadComparison();
    requireMatch(
      comparison.value.phase === (action === "approve" ? "candidate_approved" : "candidate_rejected"),
      "候选判断后的比较状态不完整",
      "phase",
    );
    requireMatch(
      selection.value?.selection_id === result.selection_id,
      "候选判断未进入服务端工作流投影",
      "workflow.selection",
    );
  });
}

async function requestRelease() {
  await runMutation("release-request", async () => {
    const expectedComparison = comparison.value;
    const expectedSelection = selection.value;
    requireMatch(expectedComparison?.phase === "candidate_approved", "候选尚未批准", "phase");
    requireMatch(expectedSelection?.action === "approve", "缺少候选批准记录", "selection_id");
    const result = await createDesignReleaseRequest({
      requestId: createDesignPromotionRequestId(),
      selectionId: expectedSelection.selection_id,
      expectedComparisonSha256: expectedComparison.comparison_sha256,
      expectedCandidateSha256: expectedSelection.candidate_sha256,
      expectedTarget: exactTargetPreimage(),
    });
    requireMatch(result.selection_id === expectedSelection.selection_id, "发布申请选择记录不一致", "selection_id");
    requireMatch(result.comparison_id === expectedComparison.comparison_id, "发布申请比较记录不一致", "comparison_id");
    requireMatch(
      result.summary.candidate.asset_sha256 === expectedSelection.candidate_sha256,
      "发布申请候选摘要不一致",
      "asset_sha256",
    );
    await reloadComparison();
    requireMatch(comparison.value.phase === "release_pending", "发布申请后的比较状态不完整", "phase");
    requireMatch(
      releaseRequest.value?.release_request_id === result.release_request_id,
      "发布申请未进入服务端工作流投影",
      "workflow.release_request",
    );
  });
}

async function approveRelease() {
  try {
    await ElMessageBox.confirm(
      "本动作只批准精确发布摘要并生成发布包，不会自动写入目标 PNG。是否继续？",
      "确认发布批准",
      { type: "warning", confirmButtonText: "批准发布摘要", cancelButtonText: "再看看" },
    );
  } catch {
    return;
  }
  await decideRelease("approve");
}

async function rejectRelease() {
  await decideRelease("reject");
}

async function decideRelease(action) {
  await runMutation(`release-${action}`, async () => {
    const expected = releaseRequest.value;
    requireMatch(comparison.value?.phase === "release_pending", "发布申请已不在待批准阶段", "phase");
    requireMatch(expected?.state === "awaiting_release_approval", "发布申请已不在待批准状态", "state");
    const result = await decideDesignReleaseRequest(expected.release_request_id, {
      requestId: createDesignPromotionRequestId(),
      action,
      expectedSummarySha256: expected.summary_sha256,
      reasonCode: action === "reject" ? releaseRejectReason.value : null,
      comment: action === "reject" ? releaseRejectComment.value : releaseApproveComment.value,
    });
    requireMatch(result.release_request_id === expected.release_request_id, "发布判断申请不一致", "release_request_id");
    requireMatch(result.summary_sha256 === expected.summary_sha256, "发布判断摘要不一致", "summary_sha256");
    requireMatch(result.action === action, "发布判断动作与请求不一致", "action");
    releaseRejectOpen.value = false;
    await reloadComparison();
    requireMatch(
      comparison.value.phase === (action === "approve" ? "publish_ready" : "release_rejected"),
      "发布判断后的比较状态不完整",
      "phase",
    );
    requireMatch(
      releaseDecision.value?.decision_id === result.decision_id,
      "发布判断未进入服务端工作流投影",
      "workflow.release_decision",
    );
  });
}

async function publishRelease() {
  if (publishConfirmed.value !== true) return;
  try {
    await ElMessageBox.confirm(
      "即将把已批准发布包写入 allowlist 中的目标 PNG。服务端会再次核对目标前像；是否显式发布？",
      "显式发布确认",
      { type: "warning", confirmButtonText: "按精确哈希发布", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  await runMutation("publish", async () => {
    const expectedRequest = releaseRequest.value;
    const expectedDecision = releaseDecision.value;
    requireMatch(comparison.value?.phase === "publish_ready", "当前阶段不允许发布", "phase");
    requireMatch(expectedDecision?.state === "release_approved", "发布尚未获具名批准", "state");
    const packageSha256 = expectedDecision.release_package.release_package_sha256;
    const result = await publishDesignRelease(expectedRequest.release_request_id, {
      requestId: createDesignPromotionRequestId(),
      expectedReleasePackageSha256: packageSha256,
      expectedTarget: exactTargetPreimage(),
      confirm: true,
    });
    requireMatch(result.release_request_id === expectedRequest.release_request_id, "发布结果申请不一致", "release_request_id");
    requireMatch(result.release_package_sha256 === packageSha256, "发布结果包摘要不一致", "release_package_sha256");
    requireMatch(result.target_id === comparison.value.target.target_id, "发布结果目标不一致", "target_id");
    await reloadComparison();
    requireMatch(comparison.value.phase === "published", "发布后的比较状态不完整", "phase");
    requireMatch(
      publishResult.value?.publish_event_id === result.publish_event_id,
      "发布结果未进入服务端工作流投影",
      "workflow.latest_publish",
    );
  });
}

async function rollbackRelease() {
  if (rollbackConfirmed.value !== true) return;
  try {
    await ElMessageBox.confirm(
      "回退会恢复目标 PNG 的发布前版本或移除原先不存在的目标。服务端会核对当前发布哈希；是否继续？",
      "确认精确回退",
      { type: "warning", confirmButtonText: "按精确哈希回退", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  await runMutation("rollback", async () => {
    const expectedPublish = publishResult.value;
    const packageSha256 = releasePackageSha256.value;
    requireMatch(comparison.value?.phase === "published", "当前阶段不允许回退", "phase");
    requireMatch(expectedPublish?.state === "published", "当前没有可回退的已发布结果", "state");
    const result = await rollbackDesignRelease(releaseRequest.value.release_request_id, {
      requestId: createDesignPromotionRequestId(),
      expectedReleasePackageSha256: packageSha256,
      expectedCurrentSha256: expectedPublish.after_sha256,
      confirm: true,
    });
    requireMatch(result.release_request_id === releaseRequest.value.release_request_id, "回退结果申请不一致", "release_request_id");
    requireMatch(result.release_package_sha256 === packageSha256, "回退结果包摘要不一致", "release_package_sha256");
    requireMatch(result.before_sha256 === expectedPublish.after_sha256, "回退结果当前哈希不一致", "before_sha256");
    await reloadComparison();
    requireMatch(comparison.value.phase === "rolled_back", "回退后的比较状态不完整", "phase");
    requireMatch(
      rollbackResult.value?.rollback_event_id === result.rollback_event_id,
      "回退结果未进入服务端工作流投影",
      "workflow.latest_publish",
    );
  });
}

watch(
  () => `${props.task?.id || ""}|${props.task?.metadata?.candidate_manifest_sha256 || ""}`,
  () => { void initializeComparison(); },
  { immediate: true },
);
</script>

<style scoped>
.design-comparison-panel {
  container-type: inline-size;
  border: 1px solid var(--hairline);
  border-radius: 14px;
  background: var(--card-bg, var(--paper-surface));
  box-shadow: var(--shadow-card);
  padding: var(--space-5);
  color: var(--ink);
}

.panel-header,
.section-heading,
.summary-line,
.frame-meta,
.gate-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.panel-header h3,
.section-heading h4,
.rollback-box h5 {
  margin: 0;
  color: var(--ink);
}

.panel-header h3 {
  font-family: var(--serif);
  font-size: var(--fs-title);
}

.section-heading h4 {
  font-size: 15px;
}

.eyebrow,
.step-kicker {
  margin: 0 0 var(--space-1);
  color: var(--ink-faint);
  font-size: var(--fs-xs);
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.activity-state {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--ink-soft);
  font-size: var(--fs-xs);
}

.activity-pulse {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--clay);
  animation: design-activity 1.4s ease-in-out infinite;
}

@keyframes design-activity {
  0%, 100% { opacity: 0.35; transform: scale(0.85); }
  50% { opacity: 1; transform: scale(1); }
}

.panel-policy-stop,
.panel-error,
.comparison-summary,
.frame-section,
.gate-card {
  margin-top: var(--space-5);
}

.panel-policy-stop {
  border: 1px solid color-mix(in srgb, var(--trust-pending) 45%, transparent);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--trust-pending) 8%, var(--paper-surface));
  padding: var(--space-3) var(--space-4);
  color: var(--trust-pending);
}

.panel-policy-stop p {
  margin: var(--space-1) 0 0;
  color: var(--ink-soft);
  font-size: 13px;
  line-height: 1.6;
}

.loading-copy,
.gate-copy,
.request-evidence,
.publish-evidence,
.rollback-box p {
  color: var(--ink-soft);
  font-size: 13px;
  line-height: 1.65;
}

.comparison-summary,
.gate-card {
  border: 1px solid var(--hairline);
  border-radius: 12px;
  background: var(--paper-rail);
  padding: var(--space-4);
}

.summary-grid,
.hash-proof {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
  margin: var(--space-4) 0;
}

.summary-grid div,
.hash-proof div {
  min-width: 0;
}

dt {
  margin-bottom: var(--space-1);
  color: var(--ink-faint);
  font-size: var(--fs-xs);
}

dd {
  margin: 0;
  color: var(--ink-soft);
  font-size: 13px;
}

code {
  font-family: var(--mono, monospace);
  font-size: 11.5px;
  overflow-wrap: anywhere;
}

.candidate-download {
  color: var(--ink-soft);
  font-size: 13px;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.candidate-download:hover {
  color: var(--clay);
}

.candidate-download:focus-visible {
  outline: 2px solid var(--focus-ring-clay);
  outline-offset: 3px;
}

.candidate-status,
.approved-status,
.rejected-state,
.trial-provenance,
.neutral-status {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 3px 9px;
  font-size: var(--fs-xs);
  font-weight: 700;
}

.candidate-status {
  color: var(--trust-pending);
  border: 1px solid color-mix(in srgb, var(--trust-pending) 45%, transparent);
  background: color-mix(in srgb, var(--trust-pending) 8%, transparent);
}

.approved-status,
.named-human {
  color: var(--trust-signed);
}

.approved-status {
  border: 1px solid color-mix(in srgb, var(--trust-signed) 42%, transparent);
  background: color-mix(in srgb, var(--trust-signed) 8%, transparent);
}

.rejected-state {
  color: var(--trust-fail);
}

.trial-provenance {
  color: var(--trust-pending);
  border: 1px solid color-mix(in srgb, var(--trust-pending) 45%, transparent);
  background: color-mix(in srgb, var(--trust-pending) 8%, transparent);
}

.neutral-status {
  color: var(--ink-soft);
  border: 1px solid var(--hairline);
  background: var(--paper-surface);
}

.frame-count {
  color: var(--ink-faint);
  font-size: var(--fs-xs);
}

.frame-card {
  margin-top: var(--space-4);
  border: 1px solid var(--hairline);
  border-radius: 12px;
  overflow: hidden;
  background: var(--paper-surface);
}

.frame-meta {
  justify-content: flex-start;
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--hairline);
  color: var(--ink-faint);
  font-size: var(--fs-xs);
}

.frame-meta strong {
  color: var(--ink);
}

.frame-pair {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

figure {
  min-width: 0;
  margin: 0;
  padding: var(--space-3);
}

figure + figure {
  border-left: 1px solid var(--hairline);
}

figcaption {
  margin-bottom: var(--space-2);
  color: var(--ink-soft);
  font-size: 12px;
  font-weight: 700;
}

.candidate-frame figcaption {
  color: var(--trust-pending);
}

figure img {
  display: block;
  width: 100%;
  max-height: 520px;
  object-fit: contain;
  border: 1px solid var(--hairline);
  border-radius: 8px;
  background: var(--paper-canvas-b, var(--paper-rail));
}

.hash-line {
  margin: var(--space-2) 0 0;
  color: var(--ink-faint);
  font-size: 11px;
  line-height: 1.55;
}

.gate-card {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: var(--space-3);
}

.gate-number {
  display: grid;
  place-items: center;
  align-self: start;
  width: 26px;
  height: 26px;
  border: 1px solid var(--hairline);
  border-radius: 50%;
  color: var(--ink-soft);
  background: var(--paper-surface);
  font-family: var(--mono, monospace);
  font-size: 12px;
}

.gate-body {
  min-width: 0;
}

.gate-copy {
  margin: var(--space-2) 0 var(--space-3);
}

.gate-actions {
  justify-content: flex-start;
  margin-top: var(--space-3);
}

.signed-action {
  --el-button-bg-color: var(--trust-signed);
  --el-button-border-color: var(--trust-signed);
  --el-button-text-color: var(--paper-surface);
  --el-button-hover-bg-color: var(--trust-signed-deep);
  --el-button-hover-border-color: var(--trust-signed-deep);
  --el-button-hover-text-color: var(--paper-surface);
}

.reject-form,
.rollback-box {
  display: grid;
  gap: var(--space-3);
  margin-top: var(--space-4);
  padding-top: var(--space-4);
  border-top: 1px solid var(--hairline);
}

.decision-evidence,
.request-evidence,
.publish-evidence {
  margin-top: var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--hairline);
  border-radius: 9px;
  background: var(--paper-surface);
}

.decision-evidence p {
  margin: var(--space-2) 0 0;
}

.rollback-box h5 {
  font-size: 14px;
}

@container (max-width: 680px) {
  .design-comparison-panel {
    padding: var(--space-4);
  }

  .frame-pair,
  .summary-grid,
  .hash-proof {
    grid-template-columns: minmax(0, 1fr);
  }

  figure + figure {
    border-top: 1px solid var(--hairline);
    border-left: 0;
  }

  .gate-card {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (prefers-reduced-motion: reduce) {
  .activity-pulse {
    animation: none;
  }
}
</style>
