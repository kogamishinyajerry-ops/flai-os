<template>
  <div class="agent-portal">
    <!-- 图例句撤下（批次四 Q4，「行话进披露」）：类型/状态/成熟度的释义全部
         已挂在对应徽章的 :title（categoryTip/agentStatusTip/maturityTip，含
         L0「勿依赖其结论」诚实提示）——页头不再预讲一遍分类学。 -->
    <div class="page-header">
      <h2>Agent 门户</h2>
      <p class="page-sub">选择一个 Agent 创建任务</p>
    </div>

    <el-alert
      v-if="loadError"
      type="error"
      :title="loadError"
      show-icon
      :closable="false"
      class="page-alert"
    />
    <el-alert
      v-else-if="agentShellError"
      type="warning"
      :title="agentShellError"
      description="Agent 目录仍可浏览，但能力关系与引用状态不作展示。"
      show-icon
      :closable="false"
      class="page-alert"
    />

    <AgentCapabilityMap
      v-if="!loading && !loadError && agents.length && agentShellSnapshot"
      :snapshot="agentShellSnapshot"
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
          <div class="card-inner">
            <div class="agent-card-header">
              <span class="agent-identity">
                <span
                  class="agent-type-glyph"
                  :style="{ color: categoryColor(agent.category), background: categoryColor(agent.category) + '14' }"
                  aria-hidden="true"
                >
                  <el-icon><component :is="categoryIcon(agent.category)" /></el-icon>
                </span>
                <span class="agent-name">{{ agent.name }}</span>
              </span>
              <el-tag
                :type="statusTagType(agent.status)"
                size="small"
                effect="light"
                :title="agentStatusTip(agent.status)"
              >{{ agentStatusLabel(agent.status) }}</el-tag>
            </div>

            <!-- N8 能力语言前置：先一句人话「它替你干什么」，治理徽章/元数据
                 退居其后——新手选 Agent 靠的是能力描述，不是标签体系。 -->
            <p class="agent-summary">{{ agent.summary }}</p>
            <!-- 批七 §3-14：expertise.specialty 副文 + domain/密级/L1-L3 pill
                 （注册表投影，存量包无声明零占位；治理弹窗不动）。 -->
            <p v-if="agent.expertise && agent.expertise.specialty" class="agent-specialty">{{ agent.expertise.specialty }}</p>
            <div v-if="agent.expertise || agent.clearance" class="agent-expert-pills">
              <span v-if="agent.expertise && agent.expertise.domain" class="expert-pill">{{ domainLabel(agent.expertise.domain) }}</span>
              <span v-if="agent.expertise && agent.expertise.usefulness_level" class="expert-pill" :title="usefulnessTip(agent.expertise.usefulness_level)">{{ agent.expertise.usefulness_level }} · {{ usefulnessLabel(agent.expertise.usefulness_level) }}</span>
              <span v-if="agent.clearance" class="expert-pill" :class="{ 'is-sensitive': agent.clearance === 'sensitive' }">密级上限 · {{ clearanceLabel(agent.clearance) }}</span>
            </div>

            <!-- 次级 meta 一行（批次四 Q4）：类型/成熟度/id·版本合并为一行
                 安静小字——释义走 :title；id 字面保持可见 DOM（m10 has_text
                 锚 + m2 body 断言），只降视觉权重不降可见性。
                 批次 A+C：「N 项不适用边界」chip 撤下——与下方「不适用范围 · N」
                 折叠标题纯重复（P1 文字墙）；治理入口移至动作行与主 CTA 同列。 -->
            <div class="agent-tags">
              <span
                class="cat-pill"
                :style="{ color: categoryColor(agent.category), background: categoryColor(agent.category) + '18' }"
                :title="categoryTip(agent.category)"
              >
                <el-icon aria-hidden="true"><component :is="categoryIcon(agent.category)" /></el-icon>
                {{ categoryLabel(agent.category) }}
              </span>
              <el-tag
                v-if="agent.maturity"
                type="info"
                effect="plain"
                size="small"
                :title="maturityTip(agent.maturity)"
              >
                <el-icon aria-hidden="true"><TrendCharts /></el-icon>
                成熟度 · {{ agent.maturity }}
              </el-tag>
              <span class="agent-meta-token">{{ agent.id }} · v{{ agent.version }}</span>
            </div>

          <el-collapse v-if="agent.limitations && agent.limitations.length">
            <el-collapse-item>
              <template #title>
                <span class="limitations-title">
                  <el-icon aria-hidden="true"><Warning /></el-icon>
                  不适用范围 · {{ agent.limitations.length }}
                </span>
              </template>
              <ul class="limitations-list">
                <li v-for="(item, idx) in agent.limitations" :key="idx">{{ item }}</li>
              </ul>
            </el-collapse-item>
          </el-collapse>

            <div class="agent-actions">
              <button type="button" class="gov-entry" @click="openGovernance(agent)">治理</button>
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

    <!-- 批八：专家团队区块（保存自导引方案的可复用蓝本）。零团队零占位；
         成员缺位/下线由服务端投影 present/disabled 预先置灰（权威判定仍在
         summon 对账 gate，422 清单如实渲染）。 -->
    <div v-if="teams.length" class="teams-section">
      <div class="teams-header">
        <h3>专家团队</h3>
        <span class="teams-sub">保存自导引方案——召集前自动对账成员在岗与版本</span>
      </div>
      <div class="team-cards fx-stagger">
        <div v-for="t in teams" :key="t.id" class="team-card">
          <div class="team-head">
            <span class="team-name">{{ t.name }}</span>
            <span class="team-clearance" :title="'团队密级=成员上限最小值（仅展示口径；召集时仍按每位成员各自判定）'">密级 · {{ clearanceLabel(t.clearance_display) }}</span>
          </div>
          <p v-if="t.goal_template" class="team-goal">{{ t.goal_template }}</p>
          <div class="team-chain">{{ teamChainText(t) }}</div>
          <p v-if="teamUnready(t)" class="team-unready">{{ teamUnready(t) }}</p>
          <div class="team-actions">
            <el-button
              type="primary"
              size="small"
              :disabled="!!teamUnready(t)"
              @click="openSummon(t)"
            >召集此团队</el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- summon 填参面板（Codex R0 P2×2 重构）：逐席位复用 SchemaForm/validateInputs
         （枚举/整数/数组约束由控件与校验兜住，不再手搓字段）；file_upload 席位复用
         TaskCreate 上传流（提交时才上传，提交前移除零服务端残留）；契约拉取失败或
         结构过复杂 fail-closed 禁提交；对账失败清单中性渲染（策略拒绝非报警红）。 -->
    <!-- 召集中封死全部关闭路径（Codex R1 P1）：上传 await 期间关掉对话框只是
         隐藏，submitSummon 恢复后仍会发起召集——「取消了却背地里建了任务」。 -->
    <el-dialog
      v-model="summonOpen"
      :title="summonTarget ? `召集 · ${summonTarget.name}` : ''"
      width="min(640px, 92vw)"
      class="summon-dialog"
      :close-on-click-modal="!summoning"
      :close-on-press-escape="!summoning"
      :show-close="!summoning"
    >
      <div v-for="s in summonSeats" :key="s.seq" class="seat-block">
        <div class="seat-head">
          席位 {{ s.seq }} · {{ agentNameOf(s.agent_id) }}
          <span v-if="s.role" class="seat-role">{{ s.role }}</span>
          <span v-if="s.after.length" class="seat-after">等待席位 {{ s.after.join("、") }} 的产物</span>
        </div>
        <template v-if="s.schemaLoaded">
          <p v-if="!seatSupported(s)" class="seat-note is-blocked">
            该成员的输入契约本面板无法承接（拉取失败或结构过复杂）——请从导引方案逐个创建。
          </p>
          <template v-else>
            <SchemaForm v-if="s.schema" :schema="s.schema" :model="s.values" :disabled="summoning" />
            <div v-if="s.inputMode === 'file_upload'" class="seat-upload">
              <el-upload :auto-upload="false" :show-file-list="false" multiple :on-change="(f) => seatFileSelect(s, f)">
                <el-button size="small">选择材料文件</el-button>
              </el-upload>
              <div v-for="item in s.uploadItems" :key="item.uid" class="seat-upload-item">
                <span class="seat-upload-name">{{ item.name }}</span>
                <el-tag v-if="item.status === 'pending'" size="small">待上传</el-tag>
                <el-tag v-else-if="item.status === 'uploading'" type="info" size="small">上传中…</el-tag>
                <el-tag v-else-if="item.status === 'done'" type="success" size="small">已上传</el-tag>
                <el-tag v-else type="danger" size="small">失败：{{ item.error }}</el-tag>
                <el-button size="small" text :disabled="summoning" @click="removeSeatFile(s, item)">移除</el-button>
              </div>
              <p class="seat-note">材料在提交召集时才上传，提交前移除零服务端残留；该席位至少需要一份材料文件。</p>
            </div>
            <p v-if="s.inputMode !== 'file_upload' && !s.fieldCount" class="seat-note">该席位无需参数。</p>
          </template>
        </template>
        <p v-else class="seat-note">正在读取输入契约…</p>
      </div>
      <div v-if="summonErrors.length" class="summon-errors">
        <p class="summon-errors-title">召集未发起（整单拒发，未创建任何任务）：</p>
        <p v-for="(e, i) in summonErrors" :key="i" class="summon-error-line">{{ e }}</p>
      </div>
      <template #footer>
        <el-button :disabled="summoning" @click="summonOpen = false">取消</el-button>
        <el-button
          type="primary"
          :disabled="summonReady !== true || summoning"
          @click="submitSummon"
        >{{ summoning ? "召集中…" : "亲手提交召集" }}</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="governanceOpen"
      :title="governanceAgent?.name || ''"
      width="min(680px, 94vw)"
      class="gov-dialog"
      @closed="resetGovernanceDialog"
    >
      <div v-if="governanceAgent" v-loading="governanceLoading" class="gov-panel">
        <el-alert
          v-if="governanceLoadError"
          type="error"
          :title="governanceLoadError"
          show-icon
          :closable="false"
        />

        <template v-else>
          <div class="gov-ladder">
            <!-- 「成熟度」全弹窗只出现这一次（P0 修订）：顶部曾另有一行
                 成熟度+pill 与阶梯重复、信息层级自相矛盾，已撤——当前档位的
                 pill 并入阶梯标题行，阶梯本身是唯一的成熟度呈现。 -->
            <div class="gov-ladder-head">
              <span class="section-label">成熟度</span>
              <el-tag
                type="info"
                effect="plain"
                size="small"
                :title="maturityTip(governanceAgent.maturity)"
              >{{ governanceAgent.maturity }}</el-tag>
            </div>
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
            <div v-if="!maturityState.known" class="gov-maturity-unknown">
              成熟度字段待核，未默认回退为 L0
            </div>
          </div>

          <GovernanceJourney
            :maturity="governanceAgent.maturity"
            :curated-cases-count="curatedCasesCount"
            :latest-run="latestGovernanceRun"
            :promotion-confirmed="promotionConfirmed"
            :promotions="governancePromotions"
          />

          <div v-if="evalTrend.length" class="gov-eval-trend">
            <div class="section-label">评测通过率（近 {{ evalTrend.length }} 次）</div>
            <!-- 语义化趋势（P0 修订）：每柱=mono 数字+状态图标+信任色 tone
                 （严格全通过才绿/真实失败红/含跳过 amber/无有效用例中性 —），
                 hairline 基线为唯一零轴；柱列固定宽度左对齐，单次评测不再拉成
                 一根撑满全宽的无语义灰条。颜色永不单独表达状态（图标+数字同在）。 -->
            <div class="gov-trend-vals">
              <span
                v-for="run in evalTrend"
                :key="run.id"
                class="gov-trend-val num-token"
                :class="`tone-${run.tone}`"
              >
                <el-icon aria-hidden="true">
                  <CircleCheckFilled v-if="run.tone === 'real'" />
                  <CircleCloseFilled v-else-if="run.tone === 'fail'" />
                  <QuestionFilled v-else-if="run.tone === 'pending'" />
                  <Minus v-else />
                </el-icon>
                {{ run.pct === null ? "—" : run.pct }}
              </span>
            </div>
            <div class="gov-trend-bars">
              <span
                v-for="run in evalTrend"
                :key="run.id"
                class="gov-trend-bar"
                :class="[`tone-${run.tone}`, { 'is-empty': run.pct === null }]"
                :style="run.pct !== null ? { height: Math.max(6, run.pct) + '%' } : {}"
                :title="run.pct === null
                  ? `无有效用例 · ${formatTime(run.at)}`
                  : `${run.passed}/${run.total}（${run.pct}%） · ${formatTime(run.at)}`"
              ></span>
            </div>
          </div>

          <div class="gov-run-block">
            <div class="section-label">最近评测</div>
            <div v-if="governanceResumeError" class="gov-resume-error" role="alert">
              {{ governanceResumeError }}
              <button type="button" class="gov-resume-retry" :disabled="governanceRunLoading" @click="retryResume">重试</button>
            </div>
            <div class="gov-run-summary">
              <template v-if="latestGovernanceRun">
                <span :class="`tone-${latestRunVisual.tone}`">{{ latestRunVisual.detail }}</span> ·
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
            :disabled="latestRunInFlight"
            :title="latestRunInFlight && !governanceRunLoading ? '上一跑仍在进行或状态待确认——用行内「重试」刷新状态，不重复入队' : undefined"
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
                <span class="gov-promotion-meta">{{ p.confirmed_by || "记名人待核" }} · {{ formatTime(p.created_at) }}</span>
              </div>
              <div
                class="gov-promotion-identity"
                :class="`tone-${promotionIdentityOf(p).tone}`"
              >
                <el-icon aria-hidden="true">
                  <UserFilled v-if="promotionIdentityOf(p).tone === 'signed'" />
                  <Key v-else-if="promotionIdentityOf(p).tone === 'neutral'" />
                  <QuestionFilled v-else />
                </el-icon>
                {{ promotionIdentityOf(p).detail }}
              </div>
              <el-collapse v-if="p.checks && Object.keys(p.checks).length">
                <el-collapse-item title="准入判定快照">
                  <ul class="gov-checks-list">
                    <li v-for="(check, name) in p.checks" :key="name">
                      {{ promotionCheckLabel(name) }}：
                      <span :class="`tone-${checkVisual(check).tone}`">
                        <el-icon aria-hidden="true">
                          <CircleCheckFilled v-if="checkVisual(check).tone === 'real'" />
                          <CircleCloseFilled v-else-if="checkVisual(check).tone === 'fail'" />
                          <QuestionFilled v-else />
                        </el-icon>
                        {{ checkVisual(check).label }}
                      </span>
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
import { ref, computed, onMounted, onUnmounted, nextTick } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import {
  Aim,
  CircleCheckFilled,
  CircleCloseFilled,
  Document,
  Key,
  Minus,
  QuestionFilled,
  Reading,
  Tools,
  TrendCharts,
  UserFilled,
  Warning,
} from "@element-plus/icons-vue";
import { listAgents, getAgent, getAgentShell } from "../api/agents";
import { listTeams, summonTeam as summonTeamApi } from "../api/teams";
import { request, unwrapDetail } from "../api/client";
import { burstNeutral } from "../effects/burst.js";
import { buildAgentShellOverview } from "../utils/agentShell.js";
import EmptyState from "../components/EmptyState.vue";
import SkeletonBlock from "../components/SkeletonBlock.vue";
import AgentCapabilityMap from "../components/AgentCapabilityMap.vue";
import GovernanceJourney from "../components/GovernanceJourney.vue";
import SchemaForm from "../components/SchemaForm.vue";
import { parseSchema, blankInputs, collectInputs, validateInputs } from "../utils/schemaForm";
import { uploadFile as apiUploadFile } from "../api/files";
import {
  buildEvalTrend,
  buildMaturityLadder,
  PROMOTION_CHECK_LABELS,
  promotionIdentity,
  summarizeEvalRun,
} from "../utils/governanceJourney";
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

// 批七 §3-14：expertise/clearance 投影的人话映射（与 GuidePage pill 同词表）。
const DOMAIN_LABEL_MAP = {
  policy_qa: "制度",
  standards_qa: "标准",
  fault_history: "故障史",
  sys_calc: "系统计算",
  cfd_sim: "CFD 仿真",
  test_data: "试验数据",
  design_opt: "设计优化",
  generic: "通用",
};
const domainLabel = (d) => DOMAIN_LABEL_MAP[d] || d;
const USEFULNESS_LABEL = { L1: "帮我省事", L2: "比我聪明", L3: "带我做" };
const usefulnessLabel = (l) => USEFULNESS_LABEL[l] || l;
const usefulnessTip = (l) =>
  ({
    L1: "L1 帮我省事：机械劳动代劳，人全程可核对",
    L2: "L2 比我聪明：给出人想不到的候选，采纳权在人",
    L3: "L3 带我做：牵引式协作，产物必经人签发",
  })[l] || "";
const CLEARANCE_LABEL_MAP = { public: "公开", internal: "内部", sensitive: "敏感" };
const clearanceLabel = (c) => CLEARANCE_LABEL_MAP[c] || c;
const CATEGORY_ICONS = {
  tool_automation: Tools,
  knowledge_qa: Reading,
  structured_gen: Document,
  reasoning_assist: Aim,
};
const categoryIcon = (category) => CATEGORY_ICONS[category] || QuestionFilled;

const router = useRouter();
const agents = ref([]);
const agentShellSnapshot = ref(null);
const agentShellError = ref("");
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
// 恢复轮询失败的诚实呈现（批次五 C2）：绝不静默——面板 run 数据可能过期。
const governanceResumeError = ref("");
const promotionConfirmed = ref(false);
const promotionLoading = ref(false);
const promotionErrors = ref([]);
const promotionTimelineRef = ref(null);
// 亲历者纪律：仅本会话同步点成晋升成功回调置 true；resetGovernanceDialog/openGovernance
// 各重置点清 false——保证换 agent / 重开弹窗 / 历史直开恒静态（零残留）。
const witnessedPromotionBurst = ref(false);
let governanceEpoch = 0;

const latestGovernanceRun = computed(() => governanceRuns.value[0] || null);
// 「已知在跑」与「本会话轮询中」分离（Codex R0 审 P2）：恢复轮询失败会解除
// loading，但最新 run 本地仍是 queued/running——后端允许并发触发（governance
// API 无互斥），此时放开「跑评测」等于诱导对同一 agent 重复入队。旧 run 未
// 确认终态前持续压住新评测入口；行内「重试」只重查状态，是唯一恢复动作。
const latestRunInFlight = computed(() => {
  const s = latestGovernanceRun.value?.status;
  return s === "queued" || s === "running";
});
const maturityState = computed(() => buildMaturityLadder(governanceAgent.value?.maturity));
const maturityLadder = computed(() => maturityState.value.items);
const latestRunVisual = computed(() => summarizeEvalRun(latestGovernanceRun.value));
const promotionIdentityOf = (promotion) => promotionIdentity(promotion);
const promotionCheckLabel = (name) => PROMOTION_CHECK_LABELS[name] || name;
const checkVisual = (check) => {
  if (check?.ok === true) return { tone: "real", label: "通过" };
  if (check?.ok === false) return { tone: "fail", label: "未通过" };
  return { tone: "pending", label: "待核" };
};
// 最近 ≤8 次评测，旧→新（时间轴左旧右新），逐点带信任色 tone（P0 趋势语义化）；
// 只画 summarizeEvalRun 严格对账通过的跑批——未知计数不压成 0，pct=null=无有效用例。
const evalTrend = computed(() => buildEvalTrend(governanceRuns.value));

async function load() {
  loading.value = true;
  loadError.value = "";
  agentShellError.value = "";
  agentShellSnapshot.value = null;
  const [agentsResult, shellResult] = await Promise.allSettled([
    listAgents(),
    getAgentShell(),
  ]);
  if (agentsResult.status === "fulfilled") {
    agents.value = agentsResult.value;
  } else {
    const err = agentsResult.reason || {};
    loadError.value = err.detail || err.message || "Agent 目录加载失败";
  }
  if (shellResult.status === "fulfilled") {
    if (buildAgentShellOverview(shellResult.value).available === true) {
      agentShellSnapshot.value = shellResult.value;
    } else {
      agentShellError.value = "Agent 本体投影契约不兼容";
    }
  } else {
    const err = shellResult.reason || {};
    agentShellError.value = err.detail || err.message || "Agent 本体投影加载失败";
  }
  loading.value = false;
  // 批八：团队列表并行拉取——失败不污染 Agent 门户主面（区块诚实缺席）。
  try {
    teams.value = await listTeams();
  } catch {
    teams.value = [];
  }
}

// ── 批八：专家团队区块 + summon 填参面板 ─────────────────────────────────

const teams = ref([]);
const summonOpen = ref(false);
const summonTarget = ref(null);
const summonSeats = ref([]);
const summonErrors = ref([]);
const summoning = ref(false);

function agentNameOf(agentId) {
  const a = agents.value.find((x) => x.id === agentId);
  return (a && a.name) || agentId;
}

// 摘要行拓扑诚实（Codex R2 P2）：箭头只在**真线性链**（每位成员恰好接力上一位）
// 时使用；含依赖但非线性（多根/分叉/汇聚）用 · 并列——绝不虚构不存在的依赖边，
// 真实边在召集面板逐席位「等待席位 N 的产物」如实展示。
function teamChainText(t) {
  const parts = t.members.map((m) => agentNameOf(m.agent_id));
  const linear =
    t.members.length > 1 &&
    t.members.every((m, i) => {
      const after = m.after || [];
      if (i === 0) return after.length === 0;
      return after.length === 1 && after[0] === t.members[i - 1].seq;
    });
  return parts.join(linear ? " → " : " · ");
}

// 预览级不可召集提示（服务端投影 present/disabled；权威判定在 summon gate）。
function teamUnready(t) {
  const gone = t.members.filter((m) => m.present !== true).map((m) => m.agent_id);
  if (gone.length) return `成员已不在场：${gone.join("、")}——请从最新导引方案另存新团队`;
  const off = t.members.filter((m) => m.disabled === true).map((m) => m.agent_id);
  if (off.length) return `成员已下线：${off.join("、")}`;
  return "";
}

function openSummon(t) {
  summonTarget.value = t;
  summonErrors.value = [];
  summonOpen.value = true;
  summonSeats.value = t.members.map((m) => ({
    seq: m.seq,
    agent_id: m.agent_id,
    role: m.role,
    after: m.after || [],
    schemaLoaded: false,
    inputMode: null,
    schema: null,
    renderable: false,
    fieldCount: 0,
    values: {},
    uploadItems: [],
  }));
  for (const seat of summonSeats.value) {
    getAgent(seat.agent_id)
      .then((detail) => {
        // input_mode 缺失（agent 无 input 段）按 none=无输入席位。
        seat.inputMode = (detail && detail.input_mode) || "none";
        seat.schema = (detail && detail.input_schema) || null;
        const parsed = parseSchema(seat.schema);
        seat.renderable = parsed.renderable;
        seat.fieldCount = parsed.fields.length;
        seat.values = blankInputs(seat.schema, null);
        seat.schemaLoaded = true;
      })
      .catch(() => {
        // 契约拉不到 fail-closed：席位标记「不可承接」，禁提交。
        seat.inputMode = "unknown";
        seat.schemaLoaded = true;
      });
  }
}

// 席位可承接判据：params/file_upload/none 三型均可（Codex R0 P2：file 席位此前
// 一刀切禁提交，含文件成员的合法团队永远召不动=死入口）；契约拉取失败（unknown）
// 或 schema 结构超出 SchemaForm 覆盖面（renderable=false）→ fail-closed 不可承接。
function seatSupported(s) {
  if (!["params", "file_upload", "none"].includes(s.inputMode)) return false;
  // params/file_upload 席位必须有可读 schema（Codex R2 P2）：全部 agent 包都
  // 随包携带 input_schema.json，null=后端读取失败/损坏——放行会召出注定
  // runtime 失败的任务，fail-closed 禁提交。
  if ((s.inputMode === "params" || s.inputMode === "file_upload") && !s.schema) return false;
  if (s.schema && s.renderable !== true) return false;
  return true;
}

// 就绪判据（fail-closed）：全部席位契约已载且可承接、schema 约束校验全过
// （validateInputs：必填/数字界/枚举控件化——Codex R0 P2）、file 席位至少一份材料。
const summonReady = computed(() => {
  const seats = summonSeats.value;
  if (!seats.length) return false;
  for (const s of seats) {
    if (s.schemaLoaded !== true) return false;
    if (!seatSupported(s)) return false;
    if (s.schema && validateInputs(s.schema, s.values).length > 0) return false;
    if (s.inputMode === "file_upload" && s.uploadItems.length === 0) return false;
  }
  return true;
});

let seatUploadSeq = 0;
function seatFileSelect(seat, uploadItem) {
  seat.uploadItems.push({
    uid: uploadItem.uid ?? `su_${++seatUploadSeq}`,
    name: uploadItem.name,
    status: "pending",
    raw: uploadItem.raw,
    error: "",
    id: null,
  });
}

function removeSeatFile(seat, item) {
  seat.uploadItems = seat.uploadItems.filter((i) => i.uid !== item.uid);
}

// 路由离开=取消语义（Codex R2 P1 verbatim：from onUnmounted invalidate）：上传
// await 期间用浏览器返回离开门户，捕获引用不变、守卫恒过——卸载时显式收起
// 对话框，使 await 后守卫如实中止，不在用户离开后背地里建任务再拽回 /tasks。
onUnmounted(() => {
  summonOpen.value = false;
});

async function submitSummon() {
  if (summonReady.value !== true || summoning.value) return;
  summonErrors.value = [];
  summoning.value = true;
  // 快照捕获（Codex R1 P1 纵深）：上传 await 期间用户若仍设法关闭/切换团队，
  // 恢复后绝不以新 reactive 状态背地里发起——目标或席位引用变了即中止。
  const target = summonTarget.value;
  const seats = summonSeats.value;
  try {
    // 文件席位材料：提交时才上传（同 TaskCreate uploadPendingFiles 语义），任一
    // 失败即中止整单——绝不带残缺材料发起召集。
    for (const s of seats) {
      for (const item of s.uploadItems) {
        if (item.status === "done" && item.id) continue;
        item.status = "uploading";
        item.error = "";
        try {
          const rec = await apiUploadFile(item.raw);
          item.id = rec.id;
          item.status = "done";
        } catch (e) {
          item.status = "error";
          item.error = (e && (e.detail || e.message)) || "上传失败";
          throw new Error(`席位 ${s.seq} 材料「${item.name}」上传失败——未发起召集`);
        }
      }
    }
    if (summonOpen.value !== true || summonTarget.value !== target || summonSeats.value !== seats) {
      return; // 上传期间被取消/切换——如实中止，不发起召集
    }
    const items = seats.map((s) => {
      const it = { seq: s.seq, inputs: s.schema ? collectInputs(s.schema, s.values) : {} };
      if (s.uploadItems.length) it.input_file_ids = s.uploadItems.map((i) => i.id);
      return it;
    });
    const res = await summonTeamApi({ teamId: target.id, items });
    for (const w of res.warnings || []) ElMessage.warning(w);
    ElMessage.success(`已召集「${target.name}」全体 ${items.length} 名成员——进度在任务台跟进`);
    summonOpen.value = false;
    router.push({ path: "/tasks" });
  } catch (err) {
    // Codex R0 P2：api client 对 object 型 FastAPI detail 统一 JSON.stringify——
    // 解回结构再取 summon_errors/batch_errors，否则对账清单永远渲成生 JSON。
    const detail = unwrapDetail(err.detail);
    const list =
      (detail &&
        typeof detail === "object" &&
        (detail.summon_errors || (detail.batch_errors || []).flatMap((b) => b.errors))) ||
      [];
    summonErrors.value = list.length
      ? list
      : [
          (typeof detail === "string" && detail) ||
            (detail && detail.message) ||
            err.message ||
            "召集失败",
        ];
  } finally {
    summoning.value = false;
  }
}

function createTaskFor(agent) {
  router.push({ path: "/tasks/new", query: { agent_id: agent.id } });
}

// interactive 型（导引）不是一次性任务——引到对话入口（M6/ADR-0012）。
function startConversationFor(agent) {
  // Codex R0 P1：携带所选交互 Agent id——否则 GuidePage 恒建 guide_agent，
  // 新增垂类问答包（policy_qa/standards_qa）从可见入口永远够不着。
  router.push({ path: "/", query: { agent: agent.id } });
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
    // 合并保留本地乐观 in-flight 行（Codex R2 审 P2，verbatim）：POST pending
    // 期间关窗重开，旧列表快照晚于入队 unshift 提交会把 queued 行抹掉→按钮
    // 重开=重复入队窗口。服务端响应缺失的本地 queued/running 行保留表头，
    // 同 id 以服务端字段为准；下一次真实刷新（重试/终态 load）自然收敛。
    const localInFlight = governanceRuns.value.filter(
      (r) => (r.status === "queued" || r.status === "running") && !runs.some((s) => s.id === r.id),
    );
    governanceRuns.value = [...localInFlight, ...runs];
    governancePromotions.value = promotions;
    curatedCasesCount.value = casesCount?.count ?? null;
  } catch (err) {
    if (epoch !== governanceEpoch) return;
    // 对称保留（同上）：load 失败也不许抹掉在飞行的 queued/running 行。
    governanceRuns.value = governanceRuns.value.filter(
      (r) => r.status === "queued" || r.status === "running",
    );
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
  governanceResumeError.value = "";
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
  governanceResumeError.value = "";
  try {
    const run = await pollEvalRunToTerminal(agentId, latest.id);
    if (run.status !== "aborted" && governanceOpen.value && governanceAgent.value?.id === agentId) {
      await loadGovernance(agentId);
    }
  } catch (err) {
    // 诚实降级（批次五 C2）：旧实现空 catch 静默复位——用户不知道恢复轮询已
    // 失败、面板显示的 run 可能是旧态。报错如实，恢复动作明说。
    if (governanceOpen.value && governanceAgent.value?.id === agentId) {
      // 尾巴不再指路「再次跑评测」（3-lens 可用性 P2）：那个按钮语义是起新
      // 评测，照着点会对同一 agent 多起一跑——恢复动作由行内「重试」钮承载。
      governanceResumeError.value = `评测状态刷新失败（${err.detail || err.message}）——所示结果可能已过期`;
    }
  } finally {
    governanceRunLoading.value = false;
  }
}

// 行内重试=只重查刚才那次 run 的状态（resumeInFlightRunIfAny 幂等：失败后
// latestGovernanceRun 仍是 queued/running 旧态，复调即恢复轮询）。
function retryResume() {
  if (governanceAgent.value) resumeInFlightRunIfAny(governanceAgent.value.id);
}

async function runEvaluation() {
  const agentId = governanceAgent.value?.id;
  if (!agentId) return;
  governanceRunLoading.value = true;
  promotionErrors.value = [];
  let enqueuedRun = null; // POST 成功即非 null——catch 据此区分「入队前/后」失败
  try {
    const queued = await request(`/api/agents/${agentId}/eval-runs`, {
      method: "POST",
      json: {}, // 发起人=登录会话身份，服务端派生（ADR-0019 D5）
    });
    // 入队即本地落行（Codex R1 复审 P2）：POST 成功后若首轮询失败，
    // latestGovernanceRun 必须已经是这条 queued——否则 finally 解锁 loading
    // 后按钮重开=重复入队窗口。默认 status 兜底在前，服务端字段为准；
    // loadGovernance 到达后整表被服务端行覆盖。
    enqueuedRun = { status: "queued", ...queued };
    if (governanceAgent.value?.id === agentId) {
      governanceRuns.value = [enqueuedRun, ...governanceRuns.value.filter((r) => r.id !== enqueuedRun.id)];
    }
    ElMessage.info("评测已入队，执行中…");
    const run = await pollEvalRunToTerminal(agentId, queued.id);
    if (governanceOpen.value && governanceAgent.value?.id === agentId) {
      await loadGovernance(agentId);
      if (run.status === "completed") ElMessage.success("评测完成");
      else if (run.status !== "aborted") ElMessage.warning(`评测收口为 ${run.status}`);
    }
  } catch (err) {
    // 已入队后的失败（轮询/收口层）收敛到 resume 恢复链（与重开面板同一
    // 车道）：错误行+行内「重试」上屏，按钮由 latestRunInFlight 压住——
    // 绝不静默解锁诱导重复 POST。
    if (enqueuedRun && governanceOpen.value && governanceAgent.value?.id === agentId) {
      governanceResumeError.value = `评测状态刷新失败（${err.detail || err.message}）——所示结果可能已过期`;
    }
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
.card-inner {
  padding: var(--space-4) 18px 18px;
  display: flex;
  flex-direction: column;
  height: 100%;
  box-sizing: border-box;
}
.agent-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-2);
  margin-bottom: 10px;
}
.agent-identity {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
}
.agent-type-glyph {
  flex: none;
  width: 46px;
  height: 46px;
  display: inline-grid;
  place-items: center;
  border-radius: 12px;
  font-size: 24px;
}
.agent-name {
  min-width: 0;
  font-weight: 700;
  font-size: 15.5px;
  color: var(--ink);
  overflow-wrap: anywhere;
}
.agent-tags {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
/* 释义可发现性（3-lens 诚实镜头 P2）：图例句撤下后，徽章 title 是 L0「勿依赖
   其结论」等诚实提示的唯一入口——cursor:help + 虚线下划线给出「可悬停」
   affordance，不再靠图例句口头宣布「悬停徽章可看释义」。 */
.agent-tags .el-tag,
.agent-tags .cat-pill {
  cursor: help;
  text-decoration: underline dotted;
  text-underline-offset: 3px;
}
/* id·版本 token（Q4 合并进 meta 行）：mono 弱字，可见但不喧宾。 */
.agent-meta-token {
  color: var(--ink-faint);
  font-size: 11.5px;
  font-family: var(--mono);
}
.cat-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
}
.agent-tags .el-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.limitations-title {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--ink-soft);
  font-size: 11.5px;
}
.limitations-title {
  min-height: 24px;
  font-size: 13px;
}
.gov-entry {
  border: none;
  background: transparent;
  color: var(--ink-mid);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  padding: 2px var(--space-1);
  border-radius: var(--radius-sm);
}
.gov-entry:hover {
  color: var(--ink);
  text-decoration: underline;
}
.gov-entry:focus-visible {
  outline: 2px solid var(--focus-ring-clay);
  outline-offset: 2px;
  color: var(--ink);
}
.agent-summary {
  color: var(--ink-soft);
  font-size: 13px;
  line-height: 1.5;
  min-height: 40px;
}
/* 批七 §3-14：specialty 副文 + 专家 pill（中性描边；敏感=amber 描边） */
.agent-specialty {
  color: var(--ink-faint);
  font-size: 12px;
  line-height: 1.5;
  margin: -2px 0 6px;
}
.agent-expert-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0 0 8px;
}
.expert-pill {
  font-size: 11px;
  line-height: 1;
  padding: 3px 7px;
  border-radius: 6px;
  border: 1px solid var(--hairline);
  color: var(--ink-soft);
  white-space: nowrap;
}
.expert-pill.is-sensitive {
  border-color: color-mix(in srgb, var(--trust-pending) 55%, transparent);
  color: var(--trust-pending);
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
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}
.gov-panel {
  color: var(--ink);
  min-height: 180px;
}
.gov-ladder-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}
.gov-run-block {
  margin-top: 2px;
}
.gov-resume-error {
  color: var(--trust-pending);
  font-size: 12px;
  margin-bottom: 6px;
}
.gov-resume-retry {
  margin-left: 8px;
  background: none;
  border: none;
  padding: 0;
  font-size: 12px;
  color: var(--ink-soft);
  text-decoration: underline;
  text-underline-offset: 2px;
  cursor: pointer;
}
.gov-resume-retry:hover { color: var(--clay); }
.gov-resume-retry:disabled { opacity: 0.5; cursor: default; }
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
.gov-maturity-unknown {
  margin-top: 5px;
  color: var(--trust-pending);
  font-size: 11px;
}
.gov-eval-trend { margin: 14px 0; }
/* 趋势列（P0 语义化）：固定宽度左对齐——1 次评测也是一根窄柱而非撑满全宽；
   数字行与柱行同宽逐一对位，hairline 基线为唯一零轴。 */
.gov-trend-vals {
  display: flex;
  gap: 10px;
}
.gov-trend-val {
  flex: none;
  width: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 2px;
  font-size: var(--fs-2xs);
  color: var(--ink-faint);
}
.gov-trend-val .el-icon { font-size: 10px; }
.gov-trend-bars {
  display: flex; align-items: flex-end; gap: 10px; height: 48px;
  padding: var(--space-1) 0; margin-top: var(--space-1);
  border-bottom: 1px solid var(--hairline); /* W7c：hairline 基线，柱子有零轴可读 */
}
.gov-trend-bar {
  flex: none; width: 34px; min-height: 6px; background: var(--ink-mid); border-radius: 2px 2px 0 0;
  opacity: 0.75;
}
.gov-trend-bar.is-empty {
  background: transparent; border: 1px dashed var(--hairline); min-height: 100%;
  opacity: 1;
}
/* 柱 tone 承袭 summarizeEvalRun 严格判定：绿仅严格全通过，红仅真实失败，
   amber=含跳过待核，中性=无有效用例（completed 恒中性）。 */
.gov-trend-bar.tone-real { background: var(--trust-real); }
.gov-trend-bar.tone-fail { background: var(--trust-fail); }
.gov-trend-bar.tone-pending { background: var(--trust-pending); }
.gov-trend-val.tone-real { color: var(--trust-real); }
.gov-trend-val.tone-fail { color: var(--trust-fail); }
.gov-trend-val.tone-pending { color: var(--trust-pending); }
/* 窄屏（375px 弹窗内容 ~300px）：柱列收窄保 8 柱无横向溢出，数字/柱仍逐一对位。 */
@media (max-width: 480px) {
  .gov-trend-vals,
  .gov-trend-bars { gap: 6px; }
  .gov-trend-val,
  .gov-trend-bar { width: 26px; }
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
.gov-promotion-identity {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 5px;
  color: var(--ink-faint);
  font-size: 11.5px;
}
.gov-promotion-identity.tone-signed { color: var(--trust-signed); }
.gov-promotion-identity.tone-pending { color: var(--trust-pending); }
.gov-run-summary .tone-real,
.gov-checks-list .tone-real { color: var(--trust-real); }
.gov-run-summary .tone-pending,
.gov-checks-list .tone-pending { color: var(--trust-pending); }
.gov-run-summary .tone-work { color: var(--clay); }
.gov-run-summary .tone-fail,
.gov-checks-list .tone-fail { color: var(--trust-fail); }
.gov-checks-list li > span {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}
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

/* ── 批八：专家团队区块 + summon 面板（信任色零新增；对账失败=中性） ── */
.teams-section { margin-top: 28px; }
.teams-header { display: flex; align-items: baseline; gap: 10px; margin-bottom: 12px; }
.teams-header h3 { margin: 0; font-size: 16px; }
.teams-sub { font-size: 12px; color: var(--ink-faint); }
.team-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
.team-card {
  border: 1px solid var(--hairline);
  border-radius: 10px;
  padding: 14px 16px;
  background: var(--surface);
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.team-head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.team-name { font-weight: 600; font-size: 14px; color: var(--ink); }
.team-clearance { font-size: 11px; color: var(--ink-faint); white-space: nowrap; }
.team-goal { margin: 0; font-size: 12.5px; color: var(--ink-soft); line-height: 1.5; }
.team-chain { font-size: 12px; color: var(--ink-soft); }
.team-unready { margin: 0; font-size: 12px; color: var(--ink-faint); }
.team-actions { margin-top: 2px; }
.seat-block { padding: 10px 0; border-bottom: 1px solid var(--hairline-soft); }
.seat-block:last-of-type { border-bottom: none; }
.seat-head { font-size: 13px; font-weight: 600; color: var(--ink); display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
.seat-role { font-weight: 400; font-size: 12px; color: var(--ink-soft); }
.seat-after { font-weight: 400; font-size: 11.5px; color: var(--ink-faint); }
.seat-note { margin: 6px 0 0; font-size: 12px; color: var(--ink-faint); }
.seat-note.is-blocked { color: var(--trust-pending); }
.seat-upload { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }
.seat-upload-item { display: flex; align-items: center; gap: 8px; font-size: 12.5px; }
.seat-upload-name { color: var(--ink-soft); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 260px; }
.summon-errors { margin-top: 12px; padding: 10px 12px; border: 1px solid var(--hairline); border-radius: 8px; }
.summon-errors-title { margin: 0 0 4px; font-size: 12.5px; font-weight: 600; color: var(--ink); }
.summon-error-line { margin: 2px 0 0; font-size: 12.5px; color: var(--ink-soft); }
</style>
