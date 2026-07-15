<template>
  <div class="agent-portal">
    <div class="page-header">
      <h2>Agent 门户</h2>
      <p class="page-sub">选择一个 Agent 创建任务</p>
      <p class="portal-legend">
        色条 = Agent 类型 · 状态（草案态/试运行/已发布）= 发布程度 · 成熟度 L0→L3 = 可信程度（L0 为原型，勿依赖结论）· 悬停徽章可看释义
      </p>
    </div>

    <el-alert
      v-if="loadError"
      type="error"
      :title="loadError"
      show-icon
      :closable="false"
      class="page-alert"
    />

    <!-- 首载骨架（A3）：只在「从未加载完成且无错误」时撑卡片栅格轮廓，轮询期间
         /带旧值刷新绝不回骨架（本页无轮询，loading 天然只在首载为真）；失败态
         走上面 el-alert，骨架不吞错误。 -->
    <div v-if="loading && !loadError" class="portal-skel-grid">
      <div v-for="i in 6" :key="i" class="portal-skel-card">
        <SkeletonBlock height="18px" width="60%" />
        <SkeletonBlock height="13px" width="40%" />
        <SkeletonBlock height="13px" width="90%" />
        <SkeletonBlock height="13px" width="75%" />
      </div>
    </div>

    <EmptyState v-else-if="!loadError && agents.length === 0" description="暂无可用 Agent" />

    <el-row v-else :gutter="16" class="fx-stagger">
      <el-col v-for="agent in agents" :key="agent.id" :xs="24" :sm="12" :md="8" class="agent-col">
        <el-card class="agent-card" shadow="never" :body-style="{ padding: '0' }">
          <div class="cat-bar" :style="{ background: categoryColor(agent.category) }"></div>
          <div class="card-inner">
            <div class="agent-card-header">
              <span class="agent-name">{{ agent.name }}</span>
              <el-tag
                :type="statusTagType(agent.status)"
                size="small"
                effect="light"
                :title="agentStatusTip(agent.status)"
              >{{ agentStatusLabel(agent.status) }}</el-tag>
            </div>

            <div class="agent-tags">
              <span
                class="cat-pill"
                :style="{ color: categoryColor(agent.category), background: categoryColor(agent.category) + '18' }"
                :title="categoryTip(agent.category)"
              >{{ categoryLabel(agent.category) }}</span>
              <el-tag
                v-if="agent.maturity"
                type="info"
                effect="plain"
                size="small"
                :title="maturityTip(agent.maturity)"
              >{{ agent.maturity }}</el-tag>
              <button type="button" class="gov-entry" @click="openGovernance(agent)">治理</button>
            </div>
            <div class="agent-meta">
              <span>{{ agent.id }}</span>
              <span>v{{ agent.version }}</span>
            </div>

          <p class="agent-summary">{{ agent.summary }}</p>

          <el-collapse v-if="agent.limitations && agent.limitations.length">
            <el-collapse-item title="不适用范围">
              <ul class="limitations-list">
                <li v-for="(item, idx) in agent.limitations" :key="idx">{{ item }}</li>
              </ul>
            </el-collapse-item>
          </el-collapse>

            <div class="agent-actions">
              <el-button
                v-if="agent.mode === 'interactive'"
                type="primary"
                :disabled="agent.status === 'disabled'"
                @click="startConversationFor(agent)"
              >
                开始对话
              </el-button>
              <el-button
                v-else
                type="primary"
                :disabled="agent.status === 'disabled'"
                @click="createTaskFor(agent)"
              >
                创建任务
              </el-button>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog
      v-model="governanceOpen"
      :title="governanceAgent?.name || ''"
      width="560px"
      class="gov-dialog"
      @closed="resetGovernanceDialog"
    >
      <div v-if="governanceAgent" v-loading="governanceLoading" class="gov-panel">
        <div class="gov-maturity-tag">
          <span>成熟度</span>
          <el-tag type="info" effect="plain" size="small">{{ governanceAgent.maturity }}</el-tag>
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
            <!-- 柱值数字（W7c）：与下方柱子逐一对位，无有效用例显 —，轻触不重构弹窗结构。 -->
            <div class="gov-trend-vals">
              <span v-for="run in evalTrend" :key="run.id" class="gov-trend-val num-token">{{ run.pct === null ? "—" : run.pct }}</span>
            </div>
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

          <div v-if="governanceAgent.maturity === 'L0'" class="gov-promote-block">
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
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { listAgents } from "../api/agents";
import { request } from "../api/client";
import { burstNeutral } from "../effects/burst.js";
import EmptyState from "../components/EmptyState.vue";
import SkeletonBlock from "../components/SkeletonBlock.vue";
import {
  statusTagType,
  agentStatusLabel,
  agentStatusTip,
  maturityTip,
  categoryLabel,
  categoryColor,
  categoryTip,
  formatTime,
} from "../utils/format";

const router = useRouter();
const agents = ref([]);
const loading = ref(true);
const loadError = ref("");
const governanceOpen = ref(false);
const governanceAgent = ref(null);
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
// 亲历者纪律：仅本会话同步点成晋升成功回调置 true；resetGovernanceDialog/openGovernance
// 各重置点清 false——保证换 agent / 重开弹窗 / 历史直开恒静态（零残留）。
const witnessedPromotionBurst = ref(false);
let governanceEpoch = 0;

const latestGovernanceRun = computed(() => governanceRuns.value[0] || null);
const MATURITY_LADDER = ["L0", "L1", "L2", "L3"];
const maturityLadder = computed(() => {
  const current = governanceAgent.value?.maturity || "L0";
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

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    agents.value = await listAgents();
  } catch (err) {
    loadError.value = err.detail || err.message;
  } finally {
    loading.value = false;
  }
}

function createTaskFor(agent) {
  router.push({ path: "/tasks/new", query: { agent_id: agent.id } });
}

// interactive 型（导引）不是一次性任务——引到对话入口（M6/ADR-0012）。
function startConversationFor() {
  router.push({ path: "/" });
}

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
    if (epoch !== governanceEpoch) return;
    governanceRuns.value = runs;
    governancePromotions.value = promotions;
    curatedCasesCount.value = casesCount?.count ?? null;
  } catch (err) {
    if (epoch !== governanceEpoch) return;
    governanceRuns.value = [];
    governancePromotions.value = [];
    curatedCasesCount.value = null;
    governanceLoadError.value = err.detail || err.message || "治理信息加载失败";
  } finally {
    if (epoch === governanceEpoch) governanceLoading.value = false;
  }
}

function openGovernance(agent) {
  governanceAgent.value = agent;
  governanceRuns.value = [];
  governancePromotions.value = [];
  curatedCasesCount.value = null;
  governanceLoadError.value = "";
  promotionConfirmed.value = false;
  promotionErrors.value = [];
  witnessedPromotionBurst.value = false;
  governanceOpen.value = true;
  loadGovernance(agent.id).then(() => resumeInFlightRunIfAny(agent.id));
}

function resetGovernanceDialog() {
  governanceEpoch++;
  governanceAgent.value = null;
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
    if (!governanceOpen.value || governanceAgent.value?.id !== agentId) {
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
  if (!governanceOpen.value || governanceAgent.value?.id !== agentId) return;
  if (governanceRunLoading.value) return; // 已在轮询（如本会话刚发起）
  const latest = latestGovernanceRun.value;
  if (!latest || (latest.status !== "queued" && latest.status !== "running")) return;
  governanceRunLoading.value = true;
  try {
    const run = await pollEvalRunToTerminal(agentId, latest.id);
    if (run.status !== "aborted" && governanceOpen.value && governanceAgent.value?.id === agentId) {
      await loadGovernance(agentId);
    }
  } catch {
    // 请求层异常：静默复位 loading（下方 finally），用户可重试
  } finally {
    governanceRunLoading.value = false;
  }
}

async function runEvaluation() {
  const agentId = governanceAgent.value?.id;
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
    if (governanceOpen.value && governanceAgent.value?.id === agentId) {
      await loadGovernance(agentId);
      if (run.status === "completed") ElMessage.success("评测完成");
      else if (run.status !== "aborted") ElMessage.warning(`评测收口为 ${run.status}`);
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
  const agentId = governanceAgent.value?.id;
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
    ElMessage.success("已晋升 L1");
    // 续体绑定：await 期间弹窗可能已切到别的 agent——只有还在看同一 agent 时才回写
    if (governanceOpen.value && governanceAgent.value?.id === agentId) {
      promotionConfirmed.value = false;
      governanceAgent.value = { ...governanceAgent.value, maturity: "L1" };
      await Promise.all([load(), loadGovernance(agentId)]);
      // 亲历者动效（批C，Codex R0 P2-A 修正）：必须在 post-await recheck 内触发——
      // 外层守卫在 await 前，await 期间切到别的 agent 时，recheck 外播 burst 会给
      // 无关 agent 的时间线误播「假亲历」，违反亲历者纪律。放进 recheck 内即只在
      // 「reload 完成后仍看同一 agent」时放。
      if (governanceOpen.value && governanceAgent.value?.id === agentId) {
        const refreshedAgent = agents.value.find((agent) => agent.id === agentId);
        if (refreshedAgent) governanceAgent.value = refreshedAgent;
        witnessedPromotionBurst.value = true;
        await nextTick();
        const topCard = promotionTimelineRef.value?.querySelector(".gov-promotion-card");
        if (topCard) burstNeutral(topCard);
        window.setTimeout(() => { witnessedPromotionBurst.value = false; }, 1600);
      }
    } else {
      load();
    }
  } catch (err) {
    const errors = collectPromotionErrors(err);
    if (errors.length) promotionErrors.value = errors;
    else ElMessage.error(err.detail || err.message || "晋升失败");
  } finally {
    promotionLoading.value = false;
  }
}

onMounted(load);
</script>

<style scoped>
.page-header {
  margin-bottom: var(--space-5);
}
.page-header h2 {
  font-family: var(--serif);
  font-size: var(--fs-title);
  font-weight: 600;
  letter-spacing: 0.2px;
  margin: 0 0 6px;
}
.page-sub {
  margin: 0;
  color: var(--ink-faint);
  font-size: 13px;
}
/* 图例降为一行安静小字（W7b）：此前是带底色/边框的说明块，与「色条=身份轴不是
 * 信任轴」的降重方向不一致——文意保留，只褪去卡片化装饰。 */
.portal-legend {
  margin: var(--space-1) 0 0;
  color: var(--ink-faint);
  font-size: var(--fs-xs);
  line-height: 1.5;
}
.page-alert {
  margin-bottom: var(--space-4);
}
.portal-skel-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: var(--space-4);
}
.portal-skel-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: var(--space-4) 18px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
}
.agent-col {
  margin-bottom: var(--space-4);
}
.agent-card {
  position: relative; /* W7a：左侧类型色条改绝对定位，锚点搬到卡片本身 */
  height: 100%;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-card);
  /* P4 纸感抬升：统一走动效系统 tokens（--motion-fast + --ease-out-soft），
   * 悬停终态（阴影/位移量）不变，只是过渡节奏与全站微交互对齐。 */
  transition: border-color var(--motion-fast) var(--ease-out-soft),
    box-shadow var(--motion-fast) var(--ease-out-soft),
    transform var(--motion-fast) var(--ease-out-soft);
}
.agent-card:hover {
  border-color: var(--clay-softer);
  box-shadow: var(--shadow-card-hover);
  transform: translateY(-2px);
}
@media (prefers-reduced-motion: reduce) {
  .agent-card:hover {
    transform: none;
  }
}
/* W7a：顶部饱和色条改左侧 3px 类型色条（修图例「色条」与实现「顶部通栏」的
 * 文实不符）——categoryColor 逻辑不动，只挪几何位置，饱和度不升；绝对定位不
 * 占正常流，card-inner 不必再为它预留高度。3px 为任务书钉死的具体值，无对应
 * 间距阶（最小 --space-1 已是 4px）故保留字面量。 */
.cat-bar {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
}
.card-inner {
  padding: var(--space-4) 18px 18px;
  display: flex;
  flex-direction: column;
  height: 100%;
  box-sizing: border-box;
}
.agent-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  margin-bottom: 10px;
}
.agent-name {
  font-weight: 700;
  font-size: 15.5px;
  color: var(--ink);
}
.agent-meta {
  display: flex;
  gap: var(--space-3);
  color: var(--ink-soft);
  font-size: 12px;
  font-family: var(--mono);
  margin-bottom: 10px;
}
.agent-tags {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
}
.cat-pill {
  display: inline-block;
  font-size: 12px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
}
.gov-entry {
  border: none;
  background: transparent;
  color: var(--ink-mid);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  padding: 2px var(--space-1);
}
.gov-entry:hover,
.gov-entry:focus-visible {
  color: var(--ink);
  text-decoration: underline;
}
.agent-summary {
  color: var(--ink-soft);
  font-size: 13px;
  line-height: 1.5;
  min-height: 40px;
}
.limitations-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: var(--ink-soft);
}
.agent-actions {
  margin-top: auto;
  padding-top: var(--space-3);
  text-align: right;
}
.gov-panel {
  color: var(--ink);
  min-height: 180px;
}
.gov-maturity-tag {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 14px;
  margin-bottom: var(--space-4);
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
  margin-top: var(--space-3);
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
  margin-top: var(--space-4);
}
.gov-promote-block {
  margin-top: 18px;
  padding-top: var(--space-4);
  border-top: 1px solid var(--hairline);
}
.gov-promote-note {
  margin: 0 0 10px;
  color: var(--ink-soft);
  font-size: 12.5px;
}
.gov-promote-confirm {
  display: block;
  margin-bottom: var(--space-3);
}
.gov-promote-errors {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}
.gov-promote-submit {
  margin-top: 2px;
}
.gov-ladder { margin-bottom: var(--space-4); }
.gov-ladder-track { display: flex; gap: 6px; margin: 6px 0 4px; }
.gov-ladder-step {
  flex: 1; text-align: center; padding: 5px 0; border-radius: var(--radius-sm);
  font-size: 12px; font-weight: 700; color: var(--ink-faint);
  background: var(--paper-rail); border: 1px solid var(--hairline);
}
.gov-ladder-step.reached { color: var(--ink); }
.gov-ladder-step.current { border-color: var(--clay-softer); color: var(--clay); }
.gov-ladder-step.oos { opacity: 0.6; }
.gov-oos-tag { display: block; font-size: 9px; font-style: normal; font-weight: 500; }
.gov-ladder-note { color: var(--ink-faint); font-size: 11px; }
.gov-eval-trend { margin: 14px 0; }
/* 柱值数字行（W7c）：与下方 .gov-trend-bars 逐一对位的 mono 微标数字，null 用 —。 */
.gov-trend-vals {
  display: flex;
  gap: var(--space-1);
}
.gov-trend-val {
  flex: 1;
  text-align: center;
  font-size: var(--fs-2xs);
  color: var(--ink-faint);
}
.gov-trend-bars {
  display: flex; align-items: flex-end; gap: var(--space-1); height: 48px;
  padding: var(--space-1) 0; margin-top: var(--space-1);
  border-bottom: 1px solid var(--hairline); /* W7c：hairline 基线，柱子有零轴可读 */
}
.gov-trend-bar {
  flex: 1; min-height: 6px; background: var(--ink-mid); border-radius: 2px 2px 0 0;
  opacity: 0.75;
}
.gov-trend-bar.is-empty {
  background: transparent; border: 1px dashed var(--hairline); min-height: 100%;
  opacity: 1;
}
.gov-cases-count { margin-top: var(--space-3); color: var(--ink-soft); font-size: 12.5px; }
.gov-cases-count b { color: var(--ink); }
.gov-promotion-timeline {
  margin-top: 18px; padding-top: var(--space-3); border-top: 1px dashed var(--hairline);
}
.gov-promotion-card {
  padding: var(--space-2) 0; border-bottom: 1px solid var(--hairline);
}
.gov-promotion-card:last-child { border-bottom: none; }
.gov-promotion-head {
  display: flex; justify-content: space-between; align-items: baseline; gap: var(--space-2);
}
.gov-promotion-jump { color: var(--ink); font-weight: 700; font-size: 13px; }
.gov-promotion-meta { color: var(--ink-faint); font-size: 11.5px; }
.gov-checks-list {
  margin: var(--space-1) 0 0; padding-left: var(--space-4); color: var(--ink-soft);
  font-size: 11.5px; line-height: 1.7;
}
.gov-promotion-card.promote-burst {
  animation: promote-glow 1.5s var(--ease-out-soft, ease-out);
  border-radius: var(--radius-sm);
}
@keyframes promote-glow {
  /* 直接用半透明 clay（--clay-softer 是不透明实色 hex，会闪成实块非微光）——
     亲历微光是「淡入淡出的一次性高亮」，恒用低透明度字面量。信任色锁：clay=工作
     语义非五槽信任色。 */
  0% { background: rgba(var(--clay-rgb), 0.14); }
  100% { background: transparent; }
}
@media (prefers-reduced-motion: reduce) {
  .gov-promotion-card.promote-burst { animation: none; }
}
</style>
