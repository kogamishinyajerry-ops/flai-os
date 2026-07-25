<template>
  <el-dialog
    :model-value="visible"
    :title="agent?.name || ''"
    width="560px"
    class="gov-dialog"
    @update:model-value="onDialogUpdate"
    @closed="resetGovernanceDialog"
  >
    <div v-if="agent" v-loading="governanceLoading" class="gov-panel">
      <div class="gov-maturity-tag">
        <span>成熟度</span>
        <el-tag type="info" effect="plain" size="small">{{ agentMaturity }}</el-tag>
      </div>

      <el-alert
        v-if="governanceLoadError"
        type="error"
        :title="governanceLoadError"
        show-icon
        :closable="false"
      />

      <template v-else>
        <div class="gov-ladder">
          <div class="section-label">成熟度</div>
          <div class="gov-ladder-track">
            <span
              v-for="step in maturityLadder"
              :key="step.level"
              class="gov-ladder-step"
              :class="{ reached: step.reached, current: step.current, oos: step.outOfScope }"
              :title="step.outOfScope ? 'L2/L3 范围外：当前仅 L0→L1 由机器把关晋升' : ''"
            >{{ step.level }}<em v-if="step.outOfScope" class="gov-oos-tag">范围外</em></span>
          </div>
          <div class="gov-ladder-note">仅 L0→L1 机器化把关；L2/L3 范围外</div>
        </div>

        <div v-if="evalTrend.length" class="gov-eval-trend">
          <div class="section-label">评测通过率（近 {{ evalTrend.length }} 次）</div>
          <div class="gov-trend-bars">
            <span
              v-for="run in evalTrend"
              :key="run.id"
              class="gov-trend-bar"
              :class="{ 'is-empty': run.pct === null }"
              :style="run.pct !== null ? { height: Math.max(6, run.pct) + '%' } : {}"
              :title="run.pct === null
                ? `无有效用例 · ${formatTime(run.at)}`
                : `${run.passed}/${run.total}（${run.pct}%） · ${formatTime(run.at)}`"
            ></span>
          </div>
        </div>

        <div class="gov-run-block">
          <div class="section-label">最近评测</div>
          <div class="gov-run-summary">
            <template v-if="latestGovernanceRun">
              通过 {{ latestGovernanceRun.passed }}/{{ latestGovernanceRun.total }} ·
              跳过 {{ latestGovernanceRun.skipped }} ·
              {{ formatTime(latestGovernanceRun.finished_at || latestGovernanceRun.started_at) }}
            </template>
            <template v-else>尚未跑过评测</template>
          </div>

          <ul v-if="latestGovernanceRun?.case_results?.length" class="gov-case-list">
            <li v-for="item in latestGovernanceRun.case_results" :key="item.case_file">
              <span class="gov-case-file">{{ item.case_file }}</span>
              · {{ verdictLabel(item.verdict) }}
              <span v-if="item.verdict === 'failed' && item.detail"> · {{ item.detail }}</span>
            </li>
          </ul>

          <div v-if="latestGovernanceRun?.draft_cases?.length" class="gov-drafts">
            <div class="section-label">待策展（不计入评测）</div>
            <div v-for="item in latestGovernanceRun.draft_cases" :key="item.case_file" class="gov-draft-item">
              <span class="gov-case-file">{{ item.case_file }}</span>
              <span v-if="item.detail"> · {{ item.detail }}</span>
            </div>
          </div>
        </div>

        <el-button
          type="primary"
          class="gov-run-btn"
          :loading="governanceRunLoading"
          @click="runEvaluation"
        >跑评测</el-button>

        <div v-if="curatedCasesCount !== null" class="gov-cases-count">
          已固化 <b>{{ curatedCasesCount }}</b> 个 eval case（按仓内固化文件计）
        </div>

        <div v-if="agentMaturity === 'L0'" class="gov-promote-block">
          <p class="gov-promote-note">晋升 L1 需引用一次全绿评测</p>
          <el-checkbox v-model="promotionConfirmed" class="gov-promote-confirm">
            已确认异常路径处理（记名）
          </el-checkbox>

          <div v-if="promotionErrors.length" class="gov-promote-errors">
            <el-alert
              v-for="item in promotionErrors"
              :key="item.name"
              type="error"
              :title="item.detail"
              show-icon
              :closable="false"
            />
          </div>

          <el-button
            class="gov-promote-submit"
            :loading="promotionLoading"
            :disabled="!latestGovernanceRun?.id"
            @click="promoteToL1"
          >申请晋升 L1</el-button>
        </div>

        <div v-if="governancePromotions.length" ref="promotionTimelineRef" class="gov-promotion-timeline">
          <div class="section-label">晋升史</div>
          <div
            v-for="(p, idx) in governancePromotions"
            :key="p.id"
            class="gov-promotion-card"
            :class="{ 'promote-burst': idx === 0 && witnessedPromotionBurst }"
          >
            <div class="gov-promotion-head">
              <span class="gov-promotion-jump">{{ p.from_maturity }}→{{ p.to_maturity }}</span>
              <span class="gov-promotion-meta">{{ p.confirmed_by }} · {{ formatTime(p.created_at) }}</span>
            </div>
            <el-collapse v-if="p.checks && Object.keys(p.checks).length">
              <el-collapse-item title="五门判定快照">
                <ul class="gov-checks-list">
                  <li v-for="(check, name) in p.checks" :key="name">
                    {{ name }}：{{ check && check.ok === true ? '✓' : '✗' }}
                    <span v-if="check && check.detail"> · {{ check.detail }}</span>
                  </li>
                </ul>
              </el-collapse-item>
            </el-collapse>
          </div>
        </div>
      </template>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch, nextTick } from "vue";
import { ElMessage } from "element-plus";
import { request } from "../api/client";
import { burstNeutral } from "../effects/burst.js";
import { evaluationCompletionNotice, formatTime } from "../utils/format";

const props = defineProps({
  visible: { type: Boolean, default: false },
  agent: { type: Object, default: null },
});
const emit = defineEmits(["update:visible", "changed"]);

const governanceRuns = ref([]);
const governancePromotions = ref([]);
const curatedCasesCount = ref(null);
const governanceLoading = ref(false);
const governanceLoadError = ref("");
const governanceRunLoading = ref(false);
const promotionConfirmed = ref(false);
const promotionLoading = ref(false);
const promotionErrors = ref([]);
const promotionTimelineRef = ref(null);
const localMaturity = ref(null);
// 亲历者纪律：仅本会话同步点成晋升成功回调置 true；resetGovernanceDialog/openGovernance
// 各重置点清 false——保证换 agent / 重开弹窗 / 历史直开恒静态（零残留）。
const witnessedPromotionBurst = ref(false);
let governanceEpoch = 0;

const latestGovernanceRun = computed(() => governanceRuns.value[0] || null);
const MATURITY_LADDER = ["L0", "L1", "L2", "L3"];
const agentMaturity = computed(() => localMaturity.value || props.agent?.maturity || "L0");
const maturityLadder = computed(() => {
  const current = agentMaturity.value;
  const curIdx = MATURITY_LADDER.indexOf(current);
  return MATURITY_LADDER.map((level, idx) => ({
    level,
    reached: idx <= curIdx,
    current: idx === curIdx,
    outOfScope: idx >= 2, // L2/L3 仅 L0→L1 机器化把关，诚实标范围外
  }));
});
// 最近 ≤8 次评测，旧→新（时间轴左旧右新）；pct=null 表示 total=0「无有效用例」
const evalTrend = computed(() =>
  (governanceRuns.value || [])
    .filter((r) => r.status === "completed") // 只画已完成跑批——running(total=0)/error(部分) 不作通过率证据（Codex R2）
    .slice(0, 8)
    .map((r) => ({
      id: r.id,
      passed: r.passed ?? 0,
      total: r.total ?? 0,
      pct: r.total > 0 ? Math.round((r.passed / r.total) * 100) : null,
      at: r.finished_at || r.started_at,
    }))
    .reverse()
);

function verdictLabel(verdict) {
  return { passed: "通过", failed: "失败", skipped: "跳过" }[verdict] || verdict;
}

async function loadGovernance(agentId) {
  const epoch = ++governanceEpoch;
  governanceLoading.value = true;
  governanceLoadError.value = "";
  try {
    const [runs, promotions, casesCount] = await Promise.all([
      request(`/api/agents/${agentId}/eval-runs`),
      request(`/api/agents/${agentId}/promotions`),
      request(`/api/agents/${agentId}/curated_cases_count`),
    ]);
    if (epoch !== governanceEpoch) return false;
    governanceRuns.value = runs;
    governancePromotions.value = promotions;
    curatedCasesCount.value = casesCount?.count ?? null;
    return true;
  } catch (err) {
    if (epoch !== governanceEpoch) return false;
    governanceRuns.value = [];
    governancePromotions.value = [];
    curatedCasesCount.value = null;
    governanceLoadError.value = err.detail || err.message || "治理信息加载失败";
    return false;
  } finally {
    if (epoch === governanceEpoch) governanceLoading.value = false;
  }
}

// 外层把 dialog 打开（visible:false→true）时按当前 agent 重置内部状态并加载
watch(
  () => props.visible,
  (open) => {
    if (open && props.agent) openGovernance(props.agent);
  }
);

function onDialogUpdate(val) {
  emit("update:visible", val);
}

function openGovernance(agent) {
  localMaturity.value = agent.maturity || "L0";
  governanceRuns.value = [];
  governancePromotions.value = [];
  curatedCasesCount.value = null;
  governanceLoadError.value = "";
  promotionConfirmed.value = false;
  promotionErrors.value = [];
  witnessedPromotionBurst.value = false;
  loadGovernance(agent.id).then((loaded) => {
    if (loaded) resumeInFlightRunIfAny(agent.id);
  });
}

function resetGovernanceDialog() {
  governanceEpoch++;
  localMaturity.value = null;
  governanceRuns.value = [];
  governancePromotions.value = [];
  curatedCasesCount.value = null;
  governanceLoadError.value = "";
  promotionConfirmed.value = false;
  promotionErrors.value = [];
  witnessedPromotionBurst.value = false;
}

// T1（GH #2）：评测改异步队列——POST 入队立即返回 status='queued'，真正执行由
// worker 在配额门内认领。前端入队后轮询该 run 到终态再刷新+提示，按钮全程 loading
// 如实反映「执行中」。队列等待无界 + 单工具可跑数分钟（如 cfd_solve_launch 允许 360s），
// 故不设客户端硬超时——硬超时会误报错、停轮询、重亮触发按钮诱发重复提交，而后端 run
// 仍在跑（P2，Codex R1 复审）。唯一终止=用户切走 Agent/关弹窗（不对已离开对象空转请求）；
// 弹窗常开则一路轮询到终态。请求层异常照常上抛给 runEvaluation 的 catch 收口。
async function pollEvalRunToTerminal(agentId, runId, { intervalMs = 1500 } = {}) {
  while (true) {
    if (!props.visible || props.agent?.id !== agentId) {
      return { status: "aborted" };
    }
    const run = await request(`/api/agents/${agentId}/eval-runs/${runId}`);
    if (run.status !== "queued" && run.status !== "running") return run;
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

// 重开治理面板时若最新 run 仍在队列/执行中，恢复轮询并锁住「跑评测」按钮到终态
// （P2，Codex R2 复审）：关弹窗会中止唯一的轮询，但后端仍在跑；重开只加载行不恢复
// 轮询、也不由行状态派生 loading，会把在跑的 run 显示成旧态且重亮触发按钮，诱发对同一
// agent 的重复提交。此处按最新行状态恢复轮询/锁按钮。请求层异常静默复位，用户可重试。
async function resumeInFlightRunIfAny(agentId) {
  if (!props.visible || props.agent?.id !== agentId) return;
  if (governanceRunLoading.value) return; // 已在轮询（如本会话刚发起）
  const latest = latestGovernanceRun.value;
  if (!latest || (latest.status !== "queued" && latest.status !== "running")) return;
  governanceRunLoading.value = true;
  try {
    const run = await pollEvalRunToTerminal(agentId, latest.id);
    if (run.status !== "aborted" && props.visible && props.agent?.id === agentId) {
      await loadGovernance(agentId);
    }
  } catch (err) {
    // 请求层异常：复位 loading（下方 finally）+ 提示用户，用户可重试
    ElMessage.error(err?.detail || err?.message || "评测详情加载失败");
  } finally {
    governanceRunLoading.value = false;
  }
}

async function runEvaluation() {
  const agentId = props.agent?.id;
  if (!agentId) return;
  governanceRunLoading.value = true;
  promotionErrors.value = [];
  try {
    const queued = await request(`/api/agents/${agentId}/eval-runs`, {
      method: "POST",
      json: {}, // 发起人=登录会话身份，服务端派生（ADR-0019 D5）
    });
    ElMessage.info("评测已入队，执行中…");
    const run = await pollEvalRunToTerminal(agentId, queued.id);
    if (props.visible && props.agent?.id === agentId) {
      await loadGovernance(agentId);
      if (run.status !== "aborted") {
        const notice = evaluationCompletionNotice(run);
        ElMessage[notice.type](notice.message);
      }
    }
  } catch (err) {
    ElMessage.error(err.detail || err.message || "评测失败");
  } finally {
    governanceRunLoading.value = false;
  }
}

function collectPromotionErrors(err) {
  if (err.status !== 422) return [];
  let payload = err.detail;
  if (typeof payload === "string") {
    try {
      payload = JSON.parse(payload);
    } catch {
      return [{ name: "promotion", detail: payload }];
    }
  }
  const detail = payload?.detail || payload;
  const checks = detail?.checks;
  if (!checks || typeof checks !== "object") {
    return [{ name: "promotion", detail: detail?.message || "晋升条件未满足" }];
  }
  return Object.entries(checks)
    .filter(([, check]) => check?.ok !== true)
    .map(([name, check]) => ({ name, detail: check?.detail || detail.message || name }));
}

async function promoteToL1() {
  const agentId = props.agent?.id;
  const evalRunId = latestGovernanceRun.value?.id;
  if (!agentId || !evalRunId) return;
  promotionLoading.value = true;
  promotionErrors.value = [];
  try {
    await request(`/api/agents/${agentId}/promote`, {
      method: "POST",
      json: {
        to_maturity: "L1",
        eval_run_id: evalRunId,
        confirmations: { exception_paths_handled: promotionConfirmed.value },
        // confirmed_by=登录会话身份，服务端派生（ADR-0019 D5）——记名不可代填
      },
    });
  } catch (err) {
    const errors = collectPromotionErrors(err);
    if (errors.length) promotionErrors.value = errors;
    else ElMessage.error(err.detail || err.message || "晋升失败");
    promotionLoading.value = false;
    return;
  }

  // POST 已成功就是本地可信事实：先立即翻转成熟度与按钮，再做任何可能失败的刷新。
  // 人工确认的治理动作不用绿色 REAL toast；成熟度行与晋升史承担状态见证。
  localMaturity.value = "L1";
  promotionConfirmed.value = false;
  ElMessage.info("已晋升 L1（人工确认）");
  emit("changed", { agentId, maturity: "L1" });

  try {
    // 续体绑定：await 期间弹窗可能已切到别的 agent——只有还在看同一 agent 时才回写
    if (props.visible && props.agent?.id === agentId) {
      const refreshed = await loadGovernance(agentId);
      if (!refreshed) {
        ElMessage.warning("晋升已成功，但治理信息刷新失败");
        return;
      }
      // 亲历者动效（批C，Codex R0 P2-A 修正）：必须在 post-await recheck 内触发——
      // 外层守卫在 await 前，await 期间切到别的 agent 时，recheck 外播 burst 会给
      // 无关 agent 的时间线误播「假亲历」，违反亲历者纪律。放进 recheck 内即只在
      // 「reload 完成后仍看同一 agent」时放。
      if (props.visible && props.agent?.id === agentId) {
        witnessedPromotionBurst.value = true;
        await nextTick();
        const topCard = promotionTimelineRef.value?.querySelector(".gov-promotion-card");
        if (topCard) burstNeutral(topCard);
        window.setTimeout(() => { witnessedPromotionBurst.value = false; }, 1600);
      }
    }
  } catch {
    // 后续刷新/渲染失败不能反写 POST 的既成事实，也不能污染 promotionErrors。
    ElMessage.warning("晋升已成功，但治理信息刷新失败");
  } finally {
    promotionLoading.value = false;
  }
}
</script>

<style scoped>
.gov-panel {
  color: var(--ink);
  min-height: 180px;
}
.gov-maturity-tag {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 14px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--hairline);
  color: var(--ink-soft);
  font-size: 13px;
}
.gov-run-block {
  margin-top: 2px;
}
.gov-run-summary {
  color: var(--ink);
  font-size: 13px;
  line-height: 1.6;
}
.gov-case-list {
  margin: 10px 0 0;
  padding-left: 18px;
  color: var(--ink-soft);
  font-size: 11.5px;
  line-height: 1.7;
  word-break: break-word;
}
.gov-case-file {
  color: var(--ink-mid);
  font-family: var(--mono, "SF Mono", ui-monospace, monospace);
}
.gov-drafts {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed var(--hairline);
}
.gov-draft-item {
  color: var(--ink-soft);
  font-size: 11.5px;
  line-height: 1.7;
  word-break: break-word;
}
.gov-run-btn {
  margin-top: 16px;
}
.gov-promote-block {
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--hairline);
}
.gov-promote-note {
  margin: 0 0 10px;
  color: var(--ink-soft);
  font-size: 12.5px;
}
.gov-promote-confirm {
  display: block;
  margin-bottom: 12px;
}
.gov-promote-errors {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}
.gov-promote-submit {
  margin-top: 2px;
}
.gov-ladder { margin-bottom: 16px; }
.gov-ladder-track { display: flex; gap: 6px; margin: 6px 0 4px; }
.gov-ladder-step {
  flex: 1; text-align: center; padding: 5px 0; border-radius: 6px;
  font-size: 12px; font-weight: 700; color: var(--ink-faint);
  background: var(--paper-rail); border: 1px solid var(--hairline);
}
.gov-ladder-step.reached { color: var(--ink); }
.gov-ladder-step.current { border-color: var(--clay-softer); color: var(--clay); }
.gov-ladder-step.oos { opacity: 0.6; }
.gov-oos-tag { display: block; font-size: 9px; font-style: normal; font-weight: 500; }
.gov-ladder-note { color: var(--ink-faint); font-size: 11px; }
.gov-eval-trend { margin: 14px 0; }
.gov-trend-bars {
  display: flex; align-items: flex-end; gap: 4px; height: 48px;
  padding: 4px 0; margin-top: 4px;
}
.gov-trend-bar {
  flex: 1; min-height: 6px; background: var(--ink-mid); border-radius: 2px 2px 0 0;
  opacity: 0.75;
}
.gov-trend-bar.is-empty {
  background: transparent; border: 1px dashed var(--hairline); min-height: 100%;
  opacity: 1;
}
.gov-cases-count { margin-top: 12px; color: var(--ink-soft); font-size: 12.5px; }
.gov-cases-count b { color: var(--ink); }
.gov-promotion-timeline {
  margin-top: 18px; padding-top: 12px; border-top: 1px dashed var(--hairline);
}
.gov-promotion-card {
  padding: 8px 0; border-bottom: 1px solid var(--hairline);
}
.gov-promotion-card:last-child { border-bottom: none; }
.gov-promotion-head {
  display: flex; justify-content: space-between; align-items: baseline; gap: 8px;
}
.gov-promotion-jump { color: var(--ink); font-weight: 700; font-size: 13px; }
.gov-promotion-meta { color: var(--ink-faint); font-size: 11.5px; }
.gov-checks-list {
  margin: 4px 0 0; padding-left: 16px; color: var(--ink-soft);
  font-size: 11.5px; line-height: 1.7;
}
</style>
