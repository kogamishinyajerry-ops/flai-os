<template>
  <div class="guide-page" :class="{ 'is-empty': !started && messages.length === 0 }">
    <div class="guide-main">
    <!-- 起手 hero（未开始且无消息）：衬线问候 + 具名，随 composer 在视口垂直居中。 -->
    <div v-if="!started && messages.length === 0 && !restoring" class="guide-hero fx-rise">
      <!-- 减重批：hero 只剩问候+一句主标题（Claude 精髓=留白克制，信任靠交互
           建立不靠说教）。价值主张/政策句收进 composer 下一行；名字由
           WelcomeGate 身份门一次收齐，此处不再询问。 -->
      <FlaiBloom class="hero-mark" :size="38" />
      <p class="hero-greeting">{{ greeting }}</p>
      <h1 class="hero-title">说说你要做的工程活儿</h1>
      <p class="hero-routing-promise">
        输入文字或上传附件，系统会在后台自动编排所需能力。
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

    <!-- 会话流 -->
    <div v-if="messages.length || sending" ref="streamEl" class="thread">
      <div v-for="(m, idx) in messages" :key="idx" :class="['bubble-row', m.role]">

        <!-- 用户消息：靠右暖气泡 -->
        <div v-if="m.role === 'user'" class="user-bubble">
          <div class="user-text">{{ m.content }}</div>
          <div v-if="m.attachments && m.attachments.length" class="user-files">
            <span v-for="a in m.attachments" :key="a.id" class="file-chip">
              <el-icon aria-hidden="true"><Paperclip /></el-icon>
              {{ a.filename }}
            </span>
          </div>
          <!-- 「保存待核」amber 小标记（B3）：与助手侧未知条同槽同语义
               （--trust-pending=仅未核/降级）——对账锁期间用户轮同样未确认，
               核对后随权威会话重渲染消失。 -->
          <span v-if="m.persistenceUnknown" class="user-unknown-chip">保存待核</span>
          <div v-if="m.createdAt" class="bubble-time">{{ formatTime(m.createdAt) }}</div>
        </div>

        <!-- 助手消息：小 mark + 流动排版，plan-card 内联渲染 -->
        <template v-else>
          <FlaiBloom
            class="ai-mark"
            :state="m.streaming ? 'generating' : 'idle'"
            :size="26"
          />
          <div class="ai-body">
            <div class="ai-name">FLAi<span v-if="m.createdAt" class="bubble-time">{{ formatTime(m.createdAt) }}</span></div>
            <!-- 助手正文走 MarkdownLite（W5）：列表/标题/引用成块渲染——桌面级
                 富文本；纯插值零 v-html，XSS 面不变。用户气泡仍纯文本忠实显示。 -->
            <MarkdownLite v-if="m.content" :text="m.content" class="ai-lead" />
            <p
              v-if="m.streamError"
              class="stream-interrupted"
              :class="{ 'is-unknown': m.persistenceUnknown, 'is-stopped': m.streamStopped }"
            >
              <strong>{{ m.streamErrorTitle || "流式中断 · 保存状态待核" }}</strong>
              <span v-if="m.streamErrorDetail"> — {{ m.streamErrorDetail }}</span>
              <span v-if="m.streamErrorAction" class="stream-interrupted-action">
                {{ m.streamErrorAction }}
              </span>
              <button
                v-if="m.persistenceUnknown"
                type="button"
                class="stream-reconcile-btn"
                :disabled="reconciling"
                @click="reconcileConversation"
              >{{ reconciling ? "核对中…" : "刷新会话核对" }}</button>
            </p>

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
              <!-- 顶行只留 kicker：成员计数由 roster-label「执行单元 · N」
                   一处承担（五律③一处一行——原 plan-count pill 与之同屏重复，降噪批撤）。 -->
              <div class="plan-topline">
                <span class="plan-kicker">协作方案</span>
              </div>
              <h2 v-if="m.recommendation.goal" class="plan-goal-title">{{ m.recommendation.goal }}</h2>
              <p v-if="m.recommendation.analysis" class="plan-reason">{{ m.recommendation.analysis }}</p>
              <div class="route-summary">
                <span>已自动编排 · {{ m.recommendation.agents.length }} 个执行单元</span>
                <span
                  v-if="planHasInvalidSkillReuse(m.recommendation)"
                  class="route-summary-state is-pending plan-alert"
                  aria-live="polite"
                >复用证据无法核验，本次禁止开工；请继续对话让系统重新编排</span>
                <span
                  v-else-if="planHasIncompleteOrchestration(m.recommendation)"
                  class="route-summary-state is-pending plan-alert"
                  aria-live="polite"
                >方案有执行单元未能纳入，请继续说明或让系统重新编排</span>
                <span v-else-if="batchCreationNeedsReconciliation" class="route-summary-state is-pending" aria-live="polite">创建状态待核，禁止重复开工</span>
                <span v-else-if="openableCount(m.recommendation) > 0" class="route-summary-state" aria-live="polite">信息已齐，等待你确认开工</span>
                <span v-else-if="planHasTasks(m.recommendation)" class="route-summary-state" aria-live="polite">执行已接入，关键状态会在这里更新</span>
                <span v-else class="route-summary-state is-pending" aria-live="polite">还需通过对话补充执行信息</span>
                <span
                  v-if="skillReuseForPlan(m.recommendation)"
                  class="skill-reuse-inline"
                >计划复用 · {{ skillReuseForPlan(m.recommendation).skill_name }}</span>
              </div>

              <details v-if="idx === latestPlanIdx" class="route-disclosure">
                <summary>
                  <span>查看路由依据与边界</span>
                </summary>
                <div class="route-disclosure-body">
              <div v-if="skillReuseForPlan(m.recommendation)" class="skill-reuse-detail">
                <span>复用方法来源</span>
                <strong>{{ skillReuseForPlan(m.recommendation).skill_name }}</strong>
                <small>
                  隔离包 {{ skillReuseForPlan(m.recommendation).package_version }} ·
                  已通过包级人工复核；系统将在开工与运行时再次核对精确摘要。
                </small>
              </div>
              <div v-if="m.recommendation.workflow" class="plan-section">
                <div class="section-label">分工如何衔接</div>
                <p class="plan-workflow">{{ m.recommendation.workflow }}</p>
              </div>
              <div class="section-label roster-label">执行单元 · {{ m.recommendation.agents.length }}</div>
              <!-- L1 编队总览行（批七 §1.4）：纯 computed 聚合成员任务快照，零动画
                   数字替换；a>0 行首 work-pulse-dot；待签发段 amber。收束态假绿
                   禁令（O7 tamper 探针）：非全终态或有待签发绝不出「完成」类总结。 -->
              <div v-if="squadSegs(m.recommendation)" class="sa-squad-line">
                <span v-if="squadHasWork(m.recommendation)" class="work-pulse-dot"></span>
                <template v-for="(seg, si) in squadSegs(m.recommendation)" :key="si">
                  <span v-if="si > 0" class="squad-sep">·</span>
                  <span class="squad-seg" :class="`tone-${seg.tone}`">{{ seg.text }}</span>
                </template>
              </div>
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
                    <!-- 六态灯（批七 T1/T4）：等待接力=空心灯（1px ink 描边，绝无
                         is-pulsing，O2 探针）；接力翻转瞬间播 2 轮 sa-relay-echo 自停。
                         灯的翻转只认 status（memberPhase 派生），事件只做旁白。 -->
                    <span
                      class="status-lamp"
                      :class="{ 'is-pulsing': agentTaskInfo(a) && isWorkState(agentTaskInfo(a).latest.status),
                                'is-hollow': memberPhaseOf(a) === 'waiting_upstream',
                                'sa-relay-echo': agentTaskInfo(a) && relayEchoIds.has(agentTaskInfo(a).latest.id) }"
                      :style="{ background: memberLampBg(a) }"
                    ></span>
                    <span class="agent-name" :title="agentTaxonomyTip(a)">{{ a.agent_name }}</span>
                    <!-- 分类学进披露（降噪批，五律④）：domain/密级/成熟度/发布状态
                         收进 agent-name 的 title 悬浮，不上成员行主视觉；唯敏感密级
                         是信任信号（amber=受控/未核槽），常驻行内不折。 -->
                    <span
                      v-if="clearanceOf(a) === 'sensitive'"
                      class="sa-clearance-pill is-sensitive"
                    >{{ clearanceLabelOf(a) }}</span>
                    <span v-if="a.role" class="agent-role"><span class="role-tag">分工</span>{{ a.role }}</span>
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
                      <span class="status-word" :style="{ color: memberStatusColor(a) }">
                        {{ memberStatusWord(a) }}
                      </span>
                      <span v-if="elapsedText(agentTaskInfo(a).latest)" class="sa-elapsed">· {{ elapsedText(agentTaskInfo(a).latest) }}</span>
                      <span v-if="agentTaskInfo(a).extra > 0" class="status-extra">+{{ agentTaskInfo(a).extra }}</span>
                      <span v-if="agentTaskInfo(a).latest.status === 'waiting_review'" class="status-peek is-review">审阅签发 →</span>
                      <span v-else class="status-peek">速览 →</span>
                    </div>
                    <!-- 右槽②未召集：只解释自动整理状态，不提供手工 Agent/参数入口。 -->
                    <div v-else-if="!summonedLocally(a)" class="agent-actions">
                      <span v-if="agentReadyForPlan(m.recommendation, a)" class="agent-readytag">输入已自动整理 · 待开工</span>
                      <span v-else class="agent-readytag is-pending">等待对话补充</span>
                    </div>
                    <span v-else class="agent-readytag">已召集 · 接入中…</span>
                  </div>

                  <div
                    v-if="planMaterialsForAgent(m.recommendation, a).length"
                    class="plan-materials"
                  >
                    <span class="plan-materials-label">使用材料</span>
                    <span
                      v-for="file in planMaterialsForAgent(m.recommendation, a)"
                      :key="file.id"
                      class="plan-material-chip"
                    >{{ file.name }}</span>
                  </div>

                  <!-- 次行：实时旁白（已召集）——运行中=事件驱动 shimmer；终态=过去式盖章 -->
                  <div
                    v-if="agentTaskInfo(a)"
                    class="sa-stageline"
                    :class="{ 'is-running': isWorkState(agentTaskInfo(a).latest.status),
                              'is-review': agentTaskInfo(a).latest.status === 'waiting_review',
                              'is-waiting-upstream': memberPhaseOf(a) === 'waiting_upstream' }"
                  >{{ stagelineFor(a) }}</div>
                  <!-- T5 依据摘要 chip（批七 §1.3）：产物 findings 忠实计数——含未核
                       整 chip amber 底纹；点击展开 EvidenceList。零 findings 零占位。 -->
                  <div
                    v-if="agentTaskInfo(a) && evidenceSummaryOf(a)"
                    class="sa-evidence-chip"
                    :class="{ 'has-unverified': evidenceSummaryOf(a).invalid || evidenceSummaryOf(a).unverified > 0 }"
                    role="button"
                    tabindex="0"
                    @click.stop="toggleEvidence(agentTaskInfo(a).latest.id)"
                    @keydown.enter.stop.prevent="toggleEvidence(agentTaskInfo(a).latest.id)"
                    @keydown.space.stop.prevent="toggleEvidence(agentTaskInfo(a).latest.id)"
                  ><template v-if="evidenceSummaryOf(a).invalid">依据结构待核</template><template v-else>依据 {{ evidenceSummaryOf(a).total }} 条（{{ evidenceSummaryOf(a).verified }} 已核验 · {{ evidenceSummaryOf(a).unverified }} 未核）<template v-if="evidenceSummaryOf(a).level"> · 置信度 {{ evidenceSummaryOf(a).level }}（模型自评）</template></template></div>
                  <!-- 批八 withheld（O6）：密级受限产物零下载零计数——静态遮蔽标记，
                       不可点击展开（无内容可展），绝不编造「依据 N 条」。 -->
                  <div
                    v-if="agentTaskInfo(a) && evidenceWithheldOf(a)"
                    class="sa-evidence-chip is-withheld"
                  >依据清单〔按密级隐藏〕</div>
                  <EvidenceList
                    v-if="agentTaskInfo(a) && expandedEvidence.has(agentTaskInfo(a).latest.id) && evidenceOfTask(agentTaskInfo(a).latest.id)"
                    :findings="evidenceOfTask(agentTaskInfo(a).latest.id).findings"
                    class="sa-evidence-expand"
                  />
                  <!-- T6 拒答拍（批七）：refusals 非空的 completed 成员——amber 非红，
                       诚实拒答是履约不是失败（O6 探针）。 -->
                  <div
                    v-if="agentTaskInfo(a) && agentTaskInfo(a).latest.status === 'completed' && refusalsOf(a).length"
                    class="sa-refusal-line"
                    role="button"
                    tabindex="0"
                    @click.stop="toggleRefusal(agentTaskInfo(a).latest.id)"
                    @keydown.enter.stop.prevent="toggleRefusal(agentTaskInfo(a).latest.id)"
                  >已如实说明：{{ refusalsOf(a).length }} 项超出能力范围 →</div>
                  <ul
                    v-if="agentTaskInfo(a) && expandedRefusals.has(agentTaskInfo(a).latest.id)"
                    class="sa-refusal-detail"
                  >
                    <li v-for="(r, ri) in refusalsOf(a)" :key="ri">
                      <span class="refusal-reason">{{ r.reason }}</span>
                      <span v-if="r.suggestion" class="refusal-suggestion">{{ r.suggestion }}</span>
                    </li>
                  </ul>
                  <!-- 次行：未召集——理由 + 预填摘要一行收纳（过程可折）。
                       Codex R1 P1：显式 !agentTaskInfo 判据——v-else 会挂到上方
                       最近的 v-if（拒答展开 ul），已召集成员未展开拒答时误渲此块。 -->
                  <template v-if="!agentTaskInfo(a)">
                    <div class="sa-subline">
                      <span v-if="a.rationale" class="agent-rationale">{{ a.rationale }}</span>
                      <span v-if="inputCount(a) > 0" class="draft-field">已从对话整理 {{ inputCount(a) }} 项执行输入</span>
                    </div>
                    <p v-if="a.stripped_fields && a.stripped_fields.length" class="agent-stripped">
                      已剔除不合法字段：{{ a.stripped_fields.join("、") }}（未匹配该执行单元的输入契约）
                    </p>
                    <div v-if="!summonedLocally(a) && agentReadyForPlan(m.recommendation, a) !== true" class="sa-subline">
                      <span class="agent-unready-hint">系统还缺少执行所需信息——继续说明目标、材料或约束即可，不需要填写字段。</span>
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
                v-if="ignoredPlanMaterials(m.recommendation).length"
                class="ignored-plan-materials"
              >
                <span>未进入本次执行：</span>
                <span
                  v-for="file in ignoredPlanMaterials(m.recommendation)"
                  :key="file.id"
                  class="plan-material-chip"
                >{{ file.name }}</span>
                <span>系统已明确忽略，不会静默带入。</span>
              </p>

                </div>
              </details>

              <div v-if="idx === latestPlanIdx" class="plan-foot">
                <button
                  v-if="planHasIncompleteOrchestration(m.recommendation)"
                  type="button"
                  class="open-plan-btn cta-clay"
                  @click="focusComposer"
                >继续说明或重新编排</button>
                <button
                  v-else-if="planHasInvalidSkillReuse(m.recommendation)"
                  type="button"
                  class="open-plan-btn is-pending"
                  @click="focusComposer"
                >复用证据待核 · 继续对话让系统重新编排</button>
                <button
                  v-else-if="batchCreationNeedsReconciliation"
                  class="open-plan-btn cta-clay"
                  :disabled="opening === conversationId"
                  @click="reconcileBatchCreation"
                >{{ opening === conversationId ? "正在核对…" : "创建状态待核 · 点击核对" }}</button>
                <button
                  v-else-if="openableCount(m.recommendation) > 0"
                  class="open-plan-btn cta-clay"
                  :disabled="opening === conversationId"
                  @click="openPlan(m.recommendation)"
                >{{ opening === conversationId ? "正在开工…" : "按方案开工" }}</button>
                <button
                  v-else-if="planHasTasks(m.recommendation)"
                  class="workbench-btn cta-clay"
                  @click="openWorkbench"
                >进入协作工作台 →</button>
                <button
                  v-else-if="conversationStatus === 'active'"
                  type="button"
                  class="open-plan-btn cta-clay"
                  @click="focusComposer"
                >继续说明缺失信息</button>
                <!-- 政策句压一行（批次四 Q3）：红线字面「亲手提交」「签发权」
                     逐字保留（m6 ③ 锚）；动词分轴（3-lens P3）——开工=提交、
                     放行=批准，不把两个动作混进一个动词；细则（参数未齐怎么办）
                     随需在导引对话里自然出现，不在每张卡常驻复述。 -->
                <span class="plan-note">
                  系统会在后台自动编排所需能力；开工由你确认，产物放行由你批准——签发权始终在你。
                </span>
              </div>
            </div>

            <!-- 垂类问答依据卡（批七 Codex R0 P1 接线）：policy_qa/standards_qa 的
                 recommendation 无 decision 键，形状 = {answer, findings, refusals}。
                 findings 走 EvidenceList（全链无绿，未核 amber）；refusals 逐条
                 如实渲染——拒答是承诺的一部分，不藏。双空不渲（schema 已拒双空）。 -->
            <div
              v-else-if="qaRecommendation(m.recommendation)"
              class="plan-card qa-evidence-card"
              :class="{ 'fx-rise': m.fresh }"
            >
              <div v-if="(m.recommendation.findings || []).length" class="plan-section">
                <div class="section-label">依据清单 · {{ m.recommendation.findings.length }}</div>
                <EvidenceList :findings="m.recommendation.findings" />
              </div>
              <div v-if="(m.recommendation.refusals || []).length" class="plan-section">
                <div class="section-label">未覆盖 · 拒答 {{ m.recommendation.refusals.length }}</div>
                <div v-for="(r, ri) in m.recommendation.refusals" :key="ri" class="qa-refusal">
                  <p class="qa-refusal-reason">{{ r.reason }}</p>
                  <p v-if="r.suggestion" class="qa-refusal-suggestion">{{ r.suggestion }}</p>
                </div>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- 完成态才长出的单一资产候选锚点。它属于主对话轴，不进入成员卡、
           不形成常驻侧栏；审核面只读且只有按钮。 -->
      <AssetCandidateCallout
        :candidate="assetCandidate"
        :phase="assetCandidatePhase"
        :error="assetCandidateError"
        :package-review-content="skillPackageReviewContent"
        :package-review-phase="skillPackageReviewPhase"
        :package-review-error="skillPackageReviewError"
        @decide="decideCurrentAssetCandidate"
        @decide-package="decideCurrentSkillPackage"
        @load-package-content="loadCurrentSkillPackageReviewContent"
        @retry="reconcileAssetCandidate"
      />

      <!-- 平台功能与当前 owner 资产只在主会话原地按需披露；默认折叠，
           首次展开才冷读，不新增 /map 页面或第二套资产工作台。 -->
      <FeatureAssetMapDisclosure />

      <div v-if="sending && !hasStreamingAssistant" class="bubble-row assistant">
        <FlaiBloom class="ai-mark" state="generating" :size="26" />
        <div class="ai-thinking">
          <div class="think-row">
            <!-- 真耗时（评审 N3）：≥3s 才显示，快回合不闪数字；tabular-nums 逐秒活跳不抖宽。 -->
            <!-- 分阶段真话（Codex R0 审 P2）：附件上传期显示「正在上传附件 X/Y」，
                 模型等待期才是「导引思考中」——300s 上传宽限下两者可能都以分钟计，
                 不许互相冒名。秒数计时随阶段重锚，只算当前阶段耗时。 -->
            <span class="tlabel">{{ uploadPhase || "FLAi 正在响应…" }}<span v-if="!uploadPhase && thinkingSeconds >= 3" class="think-elapsed num-token">{{ thinkingSeconds }}s</span></span>
          </div>
          <!-- 诚实预期管理（评审 N3）：内网大模型单轮可达一两分钟（B3 超时旋钮按内网
               p99 放宽后尤甚）——超 30s 给一行真话；绝不做假进度条（诚实地板）。 -->
          <p v-if="!uploadPhase && thinkingSeconds >= 30" class="think-slow">内网大模型推理较慢——复杂需求可能要一两分钟。请留在本页稍候：本轮若失败，你的原话会退回输入框，不会丢。</p>
        </div>
      </div>
    </div>

    <!-- 悬浮质感 composer：会话开始后固定悬浮在视口底部（Claude 布局，始终可见） -->
    <div class="composer" :class="{ 'composer-fixed': started || messages.length }">
      <div class="composer-inner">
      <!-- batch 对账是会话级状态，不属于某一张“最新方案”卡。A→B→A 恢复后
           canonical 历史消息 fresh=false、没有可操作方案下标，仍须保留唯一可达的
           同 operation_id 核对动作；composer 同时保持锁定。 -->
      <div v-if="batchCreationNeedsReconciliation" class="batch-reconcile-bar">
        <span>{{ batchCreationJournalCorrupt
          ? "本地创建记录无法安全读取 · 已锁定以避免重复任务"
          : "创建状态待核 · 本次开工已锁定，禁止换标识重复创建" }}</span>
        <button
          type="button"
          class="open-plan-btn cta-clay"
          :disabled="opening === conversationId"
          @click="reconcileBatchCreation"
        >{{ opening === conversationId
          ? "正在核对…"
          : batchCreationJournalCorrupt ? "查看处理提示" : "核对原开工请求" }}</button>
      </div>
      <div v-if="pendingFiles.length" class="composer-files">
        <!-- 附件 chip 四件：图标+名称+大小+移除。逐文件上传相位如实呈现
             （uploadPhase 同源真实状态）：uploading=clay「上传中…」（工作/进行中
             槽位）、done=中性墨「已上传」（completed 恒中性，不给绿）、error=
             只染状态词 trust-fail（W1 语法：文件名保持墨色，失败是状态不是文件）。
             「（上传失败）」字面沿用旧文案未动。 -->
        <span
          v-for="f in pendingFiles"
          :key="f.uid"
          :class="['file-chip', 'closable', { error: f.status === 'error', uploading: f.status === 'uploading' }]"
          :title="f.status === 'error' ? f.error : ''"
        >
          <svg class="chip-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21.44 11.05l-9.19 9.19a5 5 0 0 1-7.07-7.07l9.19-9.19a3.5 3.5 0 0 1 4.95 4.95l-9.2 9.19a1.5 1.5 0 0 1-2.12-2.12l8.49-8.49"/></svg>
          <span class="chip-name">{{ f.name }}</span>
          <span v-if="formatFileSize(f.size)" class="chip-size num-token">{{ formatFileSize(f.size) }}</span>
          <span v-if="f.status === 'uploading'" class="chip-phase">上传中…</span>
          <span v-else-if="f.status === 'done'" class="chip-phase is-done">已上传</span>
          <span v-else-if="f.status === 'error'" class="chip-phase is-error">（上传失败）</span>
          <button
            type="button"
            class="chip-x"
            :disabled="interactionPolicy.canAttach !== true"
            :aria-label="`移除附件 ${f.name}`"
            @click="removePendingFile(f)"
          >×</button>
        </span>
      </div>
      <div class="composer-shell">
        <div class="composer-row">
          <el-upload
            v-attach-shell-a11y
            class="composer-attach"
            :auto-upload="false"
            :show-file-list="false"
            multiple
            :on-change="handleFileSelect"
            :disabled="interactionPolicy.canAttach !== true"
          >
            <button class="icon-btn" :disabled="interactionPolicy.canAttach !== true" title="添加附件（≤5 个/条；文本类直读、xlsx 预览）" aria-label="添加附件">
              <el-icon :size="20" aria-hidden="true"><Paperclip /></el-icon>
            </button>
          </el-upload>
          <el-input
            v-model="draft"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 6 }"
            :disabled="interactionPolicy.canSend !== true"
            :placeholder="composerPlaceholder"
            class="composer-input"
            @keydown.enter.exact.prevent="send"
          />
          <!-- 流式在飞期间发送钮换形为停止钮（中性墨方块，不用红——主动停止是
               中性控制不是失败，也不另占 clay）：abort 断连 → 后端走既有
               断连零落库路径。EP 图标库无停止语义字形（仅 Stopwatch/VideoPause），
               方块字形沿用本行内联 SVG 约定。 -->
          <button
            v-if="canStopStream"
            class="send-btn stop-btn"
            aria-label="停止生成"
            title="停止生成"
            @click="stopStreaming"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2.5"/></svg>
          </button>
          <button v-else class="send-btn cta-clay" :disabled="interactionPolicy.canSend !== true || (!draft.trim() && pendingFiles.length === 0)" aria-label="发送" @click="send">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M7 11l5-5 5 5M12 6v13"/></svg>
          </button>
        </div>
      </div>
      <div class="composer-hint">
        <span class="composer-policy">{{ retryContextChecking ? "正在核对失败任务…" : batchCreationNeedsReconciliation ? "创建状态待核 · 本次开工核对前已锁定" : activeRetryOf ? "正在处理失败任务 · 审计血缘会自动保留" : "系统会在后台准备方案 · 开工与签发仍由你确认" }}</span>
        <span class="keys"><kbd>Enter</kbd> 发送<span class="sep">·</span><kbd>⇧ Enter</kbd> 换行<span class="sep">·</span>可带附件</span>
      </div>
      </div>
    </div>

    <!-- 回到底部浮钮（流式滚动跟随守卫）：用户上滚脱离贴底跟随时出现，悬浮于
         composer 上方右侧不挡主操作；脱离期间新到达的 delta 计数作为新内容
         指示。点击平滑归底并恢复跟随。 -->
    <button
      v-if="backToBottomVisible"
      type="button"
      class="back-to-bottom"
      aria-label="回到底部"
      @click="jumpToBottom"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 13l5 5 5-5M12 18V5"/></svg>
      <span>回到底部</span>
      <span v-if="newContentCount > 0" class="btb-count">{{ newContentCount > 99 ? "99+" : newContentCount }}</span>
    </button>
    </div>

    <!-- 旧资产字段式抽屉仅保留给 UI 验收台回看，不再是工程师 Guide 壳的可达入口。
         真实资产沉淀必须后续接入同一主对话：系统先自动归纳，缺口继续自然追问。 -->
    <AssetBuilderDrawer
      v-if="acceptanceMode && assetBuilderOpen"
      v-model="assetBuilderOpen"
      :conversation-id="conversationId"
      :messages="messages"
      :initial-step="assetBuilderInitialStep"
      :initial-generalization="assetBuilderInitialGeneralization"
      :initial-preview="assetBuilderInitialPreview"
    />
  </div>
</template>

<script setup>
import { reactive, ref, computed, nextTick, watch, onMounted, onUnmounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { Paperclip } from "@element-plus/icons-vue";
import { createConversation, postMessageStream, getConversation } from "../api/conversations";
import { unwrapDetail } from "../api/client";
import {
  createTaskAssetCandidate,
  decideAssetCandidate,
  decideSkillPackage,
  getSkillPackageReviewContent,
  getTaskAssetCandidate,
} from "../api/assetCandidates.js";
import {
  batchCreatePersistenceUnknown,
  createBatchOperationId,
  createTasksBatch,
  getTask,
} from "../api/tasks.js";
import { getAgent } from "../api/agents";
import { uploadFile as apiUploadFile } from "../api/files";
import {
  ensureTaskEvidence,
  taskEvidenceOf,
  taskEvidenceSummary,
  taskEvidenceWithheld,
} from "../stores/taskEvidence";
import { agentStatusLabel, MATURITY, statusLabel, taskLampColor, TASK_WORK_STATES, taskElapsedMs, formatTime, formatFileSize } from "../utils/format";
import { memberPhase, squadCounts, squadSegments } from "../utils/squad";
import { useAgentNames } from "../stores/agentNames";
import EvidenceList from "../components/EvidenceList.vue";
import AssetCandidateCallout from "../components/AssetCandidateCallout.vue";
import FeatureAssetMapDisclosure from "../components/FeatureAssetMapDisclosure.vue";
import { openTaskPeek } from "../stores/statusCenter";
import { acquireChannel, pokeConversation } from "../stores/liveFeed";
import { resolvedTheme } from "../stores/theme";
import {
  conversationInteractionPolicy,
  conversationStreamFailurePolicy,
  reconciliationLockAfterRefresh,
} from "../utils/ndjsonStream.js";
import { distanceFromBottom, shouldFollowScroll } from "../utils/scrollFollow.js";
import { recordConversationFirstUserContent } from "../utils/conversationTitles.js";
import {
  clearBatchCreationAttempt,
  persistBatchCreationAttempt,
  restoreBatchCreationAttempt,
} from "../utils/batchCreationJournal.js";
import FlaiBloom from "../components/artwork/FlaiBloom.vue";
import MarkdownLite from "../components/MarkdownLite.vue";
import AssetBuilderDrawer from "../components/AssetBuilderDrawer.vue";
import {
  agentExecutionReady,
  automaticTaskName,
  conversationSnapshotMatches,
  currentWorkSegmentFiles,
  internalConversationRouteBindingMatches,
  latestActionablePlanIndex,
  normalizeRetryLineage,
  planAttachmentRouting,
  planHasIncompleteOrchestration,
  retryLineageForPlanItem,
  verifiedFailedRetryLineage,
} from "../utils/conversationPlans.js";
import {
  assetCandidateReconcileCreateReason,
  assetCandidateRequestIsCurrent,
  eligibleAssetCandidateTask,
  normalizeSkillPackageReviewContent,
  normalizeSkillReuseRef,
  verifyAssetCandidateIntegrity,
} from "../utils/assetCandidates.js";

// UI 验收台通过独立 Vite 开发入口传入状态快照。正式应用永远忽略该 prop：
// 它只控制可视状态，不模拟网络、不写会话、不产生“假流式”。
const props = defineProps({
  acceptanceFixture: {
    type: Object,
    default: null,
  },
});
const acceptanceFixture = import.meta.env.DEV ? props.acceptanceFixture : null;
const acceptanceMode = Boolean(acceptanceFixture);

const router = useRouter();
const route = useRoute();
const requestedRetryOf = computed(() => normalizeRetryLineage(route.query.retry_of));
// URL 只表达恢复意图；必须读取服务端权威任务并确认 status 字面为 failed 后，
// 才能展示/携带 retry_of。核对期间主输入 fail-closed，避免用户在假恢复语义下发送。
const verifiedRetryOf = ref(null);
const retryContextChecking = ref(
  !acceptanceMode && requestedRetryOf.value !== null,
);
const activeRetryOf = computed(() => verifiedRetryOf.value);
// 失败回流只允许新一轮对话生成的方案开工；历史方案即便仍是最后一条 assistant
// 消息也不能复活成重跑按钮。该门只由本次 retry query 下的 canonical 回复开启。
const retryPlanArmed = ref(false);
let retryValidationSeq = 0;

async function removeRetryQuery() {
  if (!Object.hasOwn(route.query, "retry_of")) return true;
  const query = { ...route.query };
  delete query.retry_of;
  try {
    await router.replace({ path: "/", query });
    return true;
  } catch {
    return false;
  }
}

async function validateRetryContext(raw = route.query.retry_of) {
  if (acceptanceMode) return;
  const seq = ++retryValidationSeq;
  retryPlanArmed.value = false;
  verifiedRetryOf.value = null;
  const candidate = normalizeRetryLineage(raw);
  if (!candidate) {
    retryContextChecking.value = false;
    if (raw !== undefined) {
      ElMessage.info("恢复入口无效——已按普通对话打开，不会写入重跑血缘");
      await removeRetryQuery();
    }
    return;
  }

  retryContextChecking.value = true;
  try {
    const task = await getTask(candidate);
    if (seq !== retryValidationSeq) return;
    const verified = verifiedFailedRetryLineage(task, candidate);
    if (verified) {
      verifiedRetryOf.value = verified;
      return;
    }
    ElMessage.info("该任务不是失败态——已按普通对话打开，不会伪造重跑血缘");
    await removeRetryQuery();
  } catch {
    if (seq !== retryValidationSeq) return;
    ElMessage.warning("未找到可恢复的失败任务——已按普通对话打开");
    await removeRetryQuery();
  } finally {
    if (seq === retryValidationSeq) retryContextChecking.value = false;
  }
}

// 附件控件双 Tab 停靠修复（B6c）：el-upload 外壳被 EP 硬编码 tabindex=0 +
// role=button，与内层 icon-btn（aria-label「添加附件」，m6 锚不动）重复一站。
// 外壳去 Tab 序与按钮角色，键盘语义由 icon-btn 全权承担；鼠标点击外壳开文件
// 框的既有行为不受影响。updated 钩子覆盖 disabled 切换引发的外壳属性重渲染。
// 不加 aria-hidden——外壳是 icon-btn 祖先，挂上会把真控件一并对 AT 藏掉。
function neutralizeAttachShell(el) {
  const shell = el.matches(".el-upload") ? el : el.querySelector(".el-upload");
  if (!shell) return;
  shell.removeAttribute("tabindex");
  shell.removeAttribute("role");
}
const vAttachShellA11y = { mounted: neutralizeAttachShell, updated: neutralizeAttachShell };

const GUIDE_AGENT_ID = "guide_agent";
const MAX_FILES_PER_MESSAGE = 5; // 与后端 PostMessageRequest / 运行时同值

const started = ref(acceptanceFixture?.started === true);
const conversationId = ref(acceptanceFixture?.conversationId || "");
const messages = ref(
  (acceptanceFixture?.messages || []).map((message) => ({
    ...message,
    attachments: message.attachments
      ? message.attachments.map((item) => ({ ...item }))
      : undefined,
  }))
);
const hasStreamingAssistant = computed(() =>
  messages.value.some((message) => message.role === "assistant" && message.streaming === true)
);
const draft = ref(acceptanceFixture?.draft || "");
const sending = ref(acceptanceFixture?.sending === true);
const restoring = ref(acceptanceFixture?.restoring === true);
const reconciliationRequired = ref(
  acceptanceFixture?.reconciliationRequired === true
);
const reconciling = ref(false);
// POST /tasks/batch 的响应若在 COMMIT 后丢失，不能把「没收到响应」画成「零任务」。
// 按会话保留原 operation_id + 原载荷，只允许同 key 核对重放；当前会话在核对前
// 连同 composer 一起锁住，避免生成第二份方案或换 key 重建。
const batchCreationUnknownByConversation = reactive({});
const batchCreationUnknown = computed(() => (
  conversationId.value
    ? batchCreationUnknownByConversation[conversationId.value] || null
    : null
));
const batchCreationJournalCorrupt = computed(
  () => batchCreationUnknown.value?.journalCorrupt === true,
);
const batchCreationNeedsReconciliation = computed(
  () => batchCreationUnknown.value !== null,
);

function restoreBatchCreationForConversation(id) {
  if (acceptanceMode || !id) return;
  const restored = restoreBatchCreationAttempt(id);
  if (restored.state === "ready") {
    batchCreationUnknownByConversation[id] = restored.attempt;
    return;
  }
  if (restored.state === "corrupt") {
    // 不能删除或覆盖无法读取的原操作日志，否则下一次点击会换 operation_id，
    // 在旧请求已 COMMIT 时制造重复任务。保守锁住当前会话并给出处理提示。
    batchCreationUnknownByConversation[id] = {
      conversationId: id,
      operationId: null,
      journalCorrupt: true,
    };
  }
}

function clearDurableBatchCreation(attempt) {
  if (!attempt || attempt.journalCorrupt === true) return false;
  const cleared = clearBatchCreationAttempt(
    attempt.conversationId,
    attempt.operationId,
  );
  if (
    cleared === true
    && batchCreationUnknownByConversation[attempt.conversationId]?.operationId ===
      attempt.operationId
  ) {
    delete batchCreationUnknownByConversation[attempt.conversationId];
  }
  return cleared;
}
const interactionPolicy = computed(() => {
  const policy = conversationInteractionPolicy({
    sending: sending.value,
    restoring: restoring.value,
    reconciliationRequired: reconciliationRequired.value,
  });
  if (
    retryContextChecking.value !== true &&
    batchCreationNeedsReconciliation.value !== true
  ) return policy;
  return { ...policy, canSend: false, canAttach: false };
});
// 旧字段式资产整理仅供 UI 验收台回看；真实 Guide 壳没有入口，也不会挂载。
const assetBuilderOpen = ref(
  acceptanceMode && acceptanceFixture?.assetBuilderOpen === true,
);
const assetBuilderInitialStep = acceptanceFixture?.assetBuilderStep || 1;
const assetBuilderInitialGeneralization = acceptanceFixture?.assetDraftGeneralization || null;
const assetBuilderInitialPreview = acceptanceFixture?.assetDraftPreview || null;
const pageError = ref(acceptanceFixture?.pageError || "");
const streamEl = ref(null);
// 对账锁期间换成核对指引；正常态只提示工程师提供目标或补充信息，不要求
// 选择 Agent、模型、工具、工作流，也不暴露参数字段。
const composerPlaceholder = computed(() =>
  retryContextChecking.value
    ? "正在核对失败任务…"
    : batchCreationNeedsReconciliation.value
    ? "创建状态待核——请先核对本次开工"
    : reconciliationRequired.value
    ? "保存状态待核——请先刷新会话核对"
    : !started.value && messages.value.length === 0
      ? "描述工程需求…"
      : "继续说下去…"
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

function handleFileSelect(uploadFile) {
  if (interactionPolicy.value.canAttach !== true) return;
  if (pendingFiles.value.length >= MAX_FILES_PER_MESSAGE) {
    ElMessage.error(`单条消息最多 ${MAX_FILES_PER_MESSAGE} 个附件`);
    return;
  }
  pendingFiles.value.push(
    reactive({
      uid: uploadFile.uid ?? `gf_${++fileSeq}`,
      name: uploadFile.name,
      size: uploadFile.size || 0, // el-upload 给的本地真实字节数，chip 大小行忠实投影
      raw: uploadFile.raw,
      status: "pending", // pending | done | error
      fileId: null,
      error: "",
    })
  );
}

function removePendingFile(item) {
  if (interactionPolicy.value.canAttach !== true) return;
  pendingFiles.value = pendingFiles.value.filter((f) => f.uid !== item.uid);
}

async function uploadPendingFiles() {
  // 顺序上传未完成项（含上一轮失败项）；任一失败即抛出，本轮消息不发送。
  // 已知行为（反方审 P3）：某轮失败但附件已上传成功（status:done）时，附件
  // 保留在待发区——这是重试语义（重试同一句不重复上传）。若用户改发别的
  // 内容，这些附件会一并带上，但 chips 始终可见、可逐个移除，故不隐藏、
  // 不静默——是否带上由用户自己看着 chips 决定。
  // 上传阶段如实报进度（Codex R0 审 P2）：上传宽限放宽到 300s 后，把网络
  // 上传时间伪装成「导引思考中」是假声明——分阶段各说各话。
  const todo = pendingFiles.value.filter((f) => f.status !== "done").length;
  let nth = 0;
  for (const item of pendingFiles.value) {
    if (item.status === "done") continue;
    nth += 1;
    uploadPhase.value = `正在上传附件 ${nth}/${todo}（${item.name}）…`;
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
  uploadPhase.value = "";
  return pendingFiles.value.map((f) => f.fileId);
}

function inputCount(agent) {
  return Object.keys(agent.prefilled_inputs || {}).length;
}

function focusComposer() {
  // 逃生行：只聚焦并滚到既有输入框，绝不读写 draft——调整方案仍由用户在
  // composer 里亲手打字表达，导引不代写。
  const el = document.querySelector(".composer-input textarea");
  if (!el) return;
  el.focus();
  el.scrollIntoView({ behavior: "smooth", block: "center" });
}

function adoptReframe(text) {
  if (interactionPolicy.value.canSend !== true) return;
  // Codex 问题卡哲学：点一条重述建议只是把它填进草稿并聚焦输入框，人仍要
  // 自己按发送——导引绝不代人发起这条消息（红线：人是唯一发起者）。
  draft.value = text;
  focusComposer();
}

// ── 导引轮次真耗时（评审 N3）────────────────────────────────────────────
// 独立 1s 计时器（不共用实时行的 nowTick——那条由工作态任务门控启停，语义
// 不同不硬并）；sending 结束即停表清零，零常驻空转。
const sendStartedAt = ref(null);
// 上传阶段提示（Codex R0 审 P2）：非空=正在顺序传附件，thinking 区显示真话
// 「正在上传附件 X/Y…」而非「导引思考中」；空=进入模型等待阶段。
const uploadPhase = ref("");
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

// ── 流式滚动跟随守卫 + 回到底部浮钮 ─────────────────────────────────────
// 跟随判定内核在 utils/scrollFollow.js（纯函数，node 可测）；这里只接 DOM。
// atBottom=false 时新 delta 不再拉回，改累计 newContentCount 喂浮钮指示。
const atBottom = ref(true);
const newContentCount = ref(0);
const backToBottomVisible = computed(() => atBottom.value !== true && messages.value.length > 0);
// 程序性平滑滚动在飞标记：其间的 scroll 事件不改判跟随态（动画中途会经过
// 距底 >阈值 区间，照用户滚动同法判定会把跟随误杀在半路上）。
let programmaticScroll = false;
let programmaticScrollTimer = null;

function currentDistanceFromBottom() {
  return distanceFromBottom({
    scrollHeight: document.documentElement.scrollHeight,
    clientHeight: window.innerHeight,
    scrollTop: window.scrollY,
  });
}

function handleWindowScroll() {
  const distance = currentDistanceFromBottom();
  if (shouldFollowScroll(distance, { programmatic: programmaticScroll })) {
    if (programmaticScroll) return; // 程序性滚动在飞：不改判
    atBottom.value = true;
    newContentCount.value = 0;
  } else {
    atBottom.value = false;
  }
}

function endProgrammaticScroll() {
  if (programmaticScrollTimer) { clearTimeout(programmaticScrollTimer); programmaticScrollTimer = null; }
  if (!programmaticScroll) return;
  programmaticScroll = false;
  // 用真实距底重判一次：平滑滚动可能被用户 wheel 打断，此时绝不可替用户恢复跟随。
  handleWindowScroll();
}

function handleDocumentScrollEnd() {
  if (programmaticScroll) endProgrammaticScroll();
}

function markProgrammaticScroll() {
  programmaticScroll = true;
  if (programmaticScrollTimer) clearTimeout(programmaticScrollTimer);
  // 兜底：scrollend 不可达/动画被打断且无后续滚动时也能解除标记。
  programmaticScrollTimer = setTimeout(endProgrammaticScroll, 800);
}

function resetScrollFollow() {
  if (programmaticScrollTimer) { clearTimeout(programmaticScrollTimer); programmaticScrollTimer = null; }
  programmaticScroll = false;
  atBottom.value = true;
  newContentCount.value = 0;
}

function jumpToBottom() {
  atBottom.value = true;
  newContentCount.value = 0;
  markProgrammaticScroll();
  const reduceMotion = window.matchMedia
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  window.scrollTo({
    top: document.documentElement.scrollHeight,
    behavior: reduceMotion ? "auto" : "smooth",
  });
}

onMounted(() => {
  window.addEventListener("scroll", handleWindowScroll, { passive: true });
  document.addEventListener("scrollend", handleDocumentScrollEnd);
});
onUnmounted(() => {
  window.removeEventListener("scroll", handleWindowScroll);
  document.removeEventListener("scrollend", handleDocumentScrollEnd);
  if (programmaticScrollTimer) clearTimeout(programmaticScrollTimer);
});

async function scrollToBottom() {
  // 会话流走自然页面流（不再是内嵌定长滚动框）——把最新一条滚到视口顶部起读，
  // 让高高的协作方案卡从「目标句」开始展开，而不是被塞进 62vh 的小盒里。
  await nextTick();
  const last = streamEl.value && streamEl.value.lastElementChild;
  if (!last) return;
  markProgrammaticScroll();
  last.scrollIntoView({ behavior: "smooth", block: "start" });
}

// 流式跟随口：仅贴底时新 delta 才自动跟随滚底；用户上滚脱离后停止拉回，
// 新内容计数喂给「回到底部」浮钮的到达指示。
function followScrollToBottom() {
  if (atBottom.value) {
    void scrollToBottom();
  } else {
    newContentCount.value += 1;
  }
}

// ── 流式停止钮 ──────────────────────────────────────────────────────────
// streamAbort=在飞流式请求的 AbortController（停止钮的物理把手）；stopRequested
// 是「本次中断由用户主动停止发起」的本地标记——catch 里先于失败策略拦截，
// 不落入「保存状态待核」对账锁（中止是用户主动行为，后端走既有断连零落库路径）。
const STREAM_STOPPED_TITLE = "已停止 · 本轮未保存";
const streamAbort = ref(null);
const stopRequested = ref(false);
const canStopStream = computed(() => sending.value === true && streamAbort.value !== null);
function stopStreaming() {
  if (!streamAbort.value) return;
  stopRequested.value = true;
  streamAbort.value.abort();
}

async function send() {
  if (interactionPolicy.value.canSend !== true) return;
  const content = draft.value.trim();
  if (!content && pendingFiles.value.length === 0) return;
  if (acceptanceMode) {
    ElMessage.info("这是只读 UI 状态快照；真实发送请回到正式对话页面");
    return;
  }
  // 一轮发送开始就钉死恢复来源。GuidePage 在 query 变化时不重挂，模型在飞期间
  // 地址栏可能切到另一失败任务；后续整轮只能沿用这个快照，绝不读取“返回时”的 URL。
  const submittedRetryOf = activeRetryOf.value;
  const retryContextMatchesSubmitted = () => (
    activeRetryOf.value === submittedRetryOf
    && requestedRetryOf.value === submittedRetryOf
  );
  let submittedConversationId = conversationId.value;
  pageError.value = "";

  // 上一轮若在收到部分 delta 后中断，页面会保留一组明确标成「未保存」的
  // 临时消息帮助用户判断。下一次发送前清掉它，避免重试堆出重复幽灵轮次。
  messages.value = messages.value.filter((message) => message.transient !== true);

  // 乐观追加用户气泡（附件 chips 一并显示）。收到 canonical done 后才把
  // transient 清掉；流式未完成以前，这一轮在前端同样不冒充已落库。
  const optimisticAttachments = pendingFiles.value.map((f) => ({ id: f.uid, filename: f.name }));
  const optimisticUser = reactive({
    role: "user",
    content,
    attachments: optimisticAttachments.length ? optimisticAttachments : undefined,
    transient: true,
  });
  messages.value.push(optimisticUser);
  const cancelUnsentForConversationSwitch = () => {
    const optimisticIndex = messages.value.indexOf(optimisticUser);
    if (optimisticIndex >= 0) messages.value.splice(optimisticIndex, 1);
    draft.value = content;
    pageError.value = "";
    ElMessage.info("会话或失败恢复入口已切换——本轮尚未发送，原话已退回主输入");
  };
  draft.value = "";
  // 用户亲手发送=明确回到最新内容的意图：复位跟随守卫再滚底——上一轮若处于
  // 上滚脱离态，新一轮仍从贴底跟随开始。
  atBottom.value = true;
  newContentCount.value = 0;
  await scrollToBottom();

  sending.value = true;
  let provisionalAssistant = null;
  let messageRequestStarted = false;
  try {
    // 先传附件（已 done 的跳过，失败即中止——本轮消息不发送）
    const fileIds = await uploadPendingFiles();
    // 上传收尾后重锚思考计时：thinkingSeconds 只讲模型等待的真话，不把
    // 上传耗时算进「导引思考中 Ns」（Codex R0 审 P2 的分阶段诚实口径）。
    sendStartedAt.value = Date.now();
    const routeConversationBeforePost = typeof route.query.c === "string" ? route.query.c : "";
    if (retryContextMatchesSubmitted() !== true) {
      cancelUnsentForConversationSwitch();
      return;
    }
    if (submittedConversationId) {
      if (
        conversationId.value !== submittedConversationId ||
        (routeConversationBeforePost && routeConversationBeforePost !== submittedConversationId)
      ) {
        cancelUnsentForConversationSwitch();
        return;
      }
    } else {
      // 空白新会话在上传/建会等待期间若已切到历史会话，不得把原轮次偷渡过去。
      if (conversationId.value || routeConversationBeforePost) {
        cancelUnsentForConversationSwitch();
        return;
      }
      // 工程师壳始终由 guide_agent 接住自然语言或附件；所需能力由导引在会话内
      // 自动编排，不读取 URL 里的手工执行单元选择。
      const conv = await createConversation({ agentId: GUIDE_AGENT_ID });
      const routeConversationAfterCreate = typeof route.query.c === "string" ? route.query.c : "";
      if (
        conversationId.value
        || routeConversationAfterCreate
        || retryContextMatchesSubmitted() !== true
      ) {
        cancelUnsentForConversationSwitch();
        return;
      }
      conversationId.value = conv.id;
      submittedConversationId = conv.id;
      conversationStatus.value = conv.status || "active";
      started.value = true;
      // URL 反映当前会话（可刷新/分享/回退），并让左栏历史即时收录这条新会话。
      // 先挂一次性内部绑定，再触发 replace。watcher 会精确消费这一拍而不把它
      // 当成外部切会话；仅仅 await replace 不能阻止 watcher 在导航确认前重读空会话。
      const internalBinding = armInternalRouteBinding(conv.id, submittedRetryOf);
      try {
        await router.replace({
          path: "/",
          query: {
            c: conv.id,
            ...(submittedRetryOf ? { retry_of: submittedRetryOf } : {}),
          },
        });
      } catch (error) {
        clearInternalRouteBinding(internalBinding);
        throw error;
      }
    }
    const routeConversationBeforeMessage = typeof route.query.c === "string"
      ? route.query.c
      : "";
    if (
      retryContextMatchesSubmitted() !== true
      || conversationId.value !== submittedConversationId
      || (routeConversationBeforeMessage && routeConversationBeforeMessage !== submittedConversationId)
    ) {
      cancelUnsentForConversationSwitch();
      return;
    }
    messageRequestStarted = true;
    // 流式停止钮把手：请求级 AbortController 透传到 fetch 层，停止即真实断连
    // （后端 50ms 轮询 is_disconnected → 提交前 is_cancelled 检查 → 零落库）。
    streamAbort.value = new AbortController();
    stopRequested.value = false;
    const res = await postMessageStream(
      submittedConversationId,
      content,
      fileIds,
      {
        signal: streamAbort.value.signal,
        onDelta(text) {
          const routeConversationId = typeof route.query.c === "string" ? route.query.c : "";
          if (
            conversationId.value !== submittedConversationId ||
            (routeConversationId && routeConversationId !== submittedConversationId) ||
            retryContextMatchesSubmitted() !== true
          ) return;
          if (!provisionalAssistant) {
            provisionalAssistant = reactive({
              role: "assistant",
              content: "",
              recommendation: null,
              fresh: true,
              streaming: true,
              transient: true,
            });
            messages.value.push(provisionalAssistant);
          }
          provisionalAssistant.content += text;
          // 只跟随真实网络 delta；不把完整结果在前端拆字制造假流式。
          // 跟随守卫：仅贴底时滚底，用户上滚阅读中不被拉回（改喂浮钮计数）。
          followScrollToBottom();
        },
      },
    );

    const routeConversationId = typeof route.query.c === "string" ? route.query.c : "";
    if (
      conversationId.value !== submittedConversationId ||
      (routeConversationId && routeConversationId !== submittedConversationId) ||
      retryContextMatchesSubmitted() !== true
    ) {
      // 服务端已把这一轮原子保存到原会话；当前页面已切走，不能把旧回复混进新会话。
      pokeConversation(submittedConversationId);
      ElMessage.info("原会话的回复已保存——当前会话未混入旧回复，可从历史记录打开查看");
      return;
    }

    // canonical done 已抵达：这一轮才算后端原子落库成功。用权威 message
    // 整体替换临时增量（含 recommendation / created_at），消除分片差异。
    optimisticUser.transient = false;
    // post-message 的 canonical assistant 与同事务 user 共用同一保存轮次；当前接口
    // 只回 assistant 时间戳，作为工作段排序代理。缺失时保留 null，边界存在则排除。
    optimisticUser.createdAt = res.message.created_at || null;
    if (optimisticAttachments.length) {
      optimisticUser.attachments = pendingFiles.value.map((f) => ({
        id: f.fileId,
        filename: f.name,
      }));
    }
    pendingFiles.value = [];
    const canonicalAssistant = {
      role: "assistant",
      content: res.message.content,
      recommendation: res.message.recommendation || null,
      fresh: true,
      // 恢复来源绑定到产生该方案的 canonical 轮次；导航丢失 query 时，这条
      // 方案不会降级成普通开工并静默丢掉 retry_of。
      retryOf: submittedRetryOf,
      createdAt: res.message.created_at || null,
      streaming: false,
      transient: false,
    };
    const retryContextStillCurrent = (
      activeRetryOf.value === submittedRetryOf &&
      requestedRetryOf.value === submittedRetryOf
    );
    if (
      submittedRetryOf &&
      retryContextStillCurrent &&
      canonicalAssistant.recommendation?.decision === "orchestrate"
    ) {
      retryPlanArmed.value = true;
    } else if (submittedRetryOf && retryContextStillCurrent !== true) {
      ElMessage.info("恢复入口已变化——本轮回复已保存，但旧方案不会开放开工；请重新发送确认");
    }
    const provisionalIndex = provisionalAssistant
      ? messages.value.indexOf(provisionalAssistant)
      : -1;
    if (provisionalIndex >= 0) {
      messages.value.splice(provisionalIndex, 1, canonicalAssistant);
    } else {
      messages.value.push(canonicalAssistant);
    }
    if (res.conversation && res.conversation.status) {
      conversationStatus.value = res.conversation.status;
    }
    // canonical done 的滚底同样走跟随守卫：用户上滚阅读中不被收尾拉回。
    followScrollToBottom();
    ensureConversationTasksFeed(); // 本轮若刚给出 orchestrate 方案，开始为其召集状态保鲜
    ensureAgentSchemasForMessages(); // 内联召集就绪判据的契约预取（fail-closed）
  } catch (err) {
    const detail = err.detail || err.message || "流式连接中断";
    const hasPartial = Boolean(provisionalAssistant && provisionalAssistant.content);
    if (!messageRequestStarted) {
      // 附件上传或建会阶段失败：消息请求尚未发起，本地可确定该用户轮未落库。
      const optimisticIndex = messages.value.indexOf(optimisticUser);
      if (optimisticIndex >= 0) messages.value.splice(optimisticIndex, 1);
      draft.value = content;
      pageError.value = detail;
    } else if (stopRequested.value) {
      // 用户主动停止（先于失败策略拦截）：中止是用户主动行为，后端断连零落库
      // 路径在案，可如实断言本轮未保存——中性提示而非失败红，也绝不进
      // 「保存状态待核」对账锁（不触碰 reconciliationRequired）。
      if (hasPartial) {
        // 已收部分如实保留并标注未保存；气泡保持 transient，下次发送由 send()
        // 开头的 transient 清扫去掉，不堆幽灵轮次；原话还稿可直接续写重发。
        provisionalAssistant.streaming = false;
        provisionalAssistant.streamError = true;
        provisionalAssistant.streamStopped = true;
        provisionalAssistant.streamErrorTitle = STREAM_STOPPED_TITLE;
        draft.value = content;
        pageError.value = "";
        void scrollToBottom();
      } else {
        // 首 token 前停止：与零落库同语义回滚乐观气泡、原话还稿。
        const optimisticIndex = messages.value.indexOf(optimisticUser);
        if (optimisticIndex >= 0) messages.value.splice(optimisticIndex, 1);
        if (provisionalAssistant) {
          const provisionalIndex = messages.value.indexOf(provisionalAssistant);
          if (provisionalIndex >= 0) messages.value.splice(provisionalIndex, 1);
        }
        draft.value = content;
        pageError.value = "";
        ElMessage.info("已停止生成——本轮未保存，原话已退回输入框");
      }
    } else {
      const failure = conversationStreamFailurePolicy(err, { hasPartial });
      reconciliationRequired.value = failure.reconciliationRequired;
      if (failure.canRetry) {
        if (!failure.discardOptimisticUser) {
          // 只有服务端 error 事件明确 persisted:false 才可断言零落库、自动还稿，
          // 并把本组标为 transient 供安全重试时清理。
          provisionalAssistant.streaming = false;
          provisionalAssistant.streamError = true;
          provisionalAssistant.streamErrorTitle = failure.title;
          provisionalAssistant.streamErrorDetail = detail;
          draft.value = content;
          pageError.value = "";
          void scrollToBottom();
        } else {
          const optimisticIndex = messages.value.indexOf(optimisticUser);
          if (optimisticIndex >= 0) messages.value.splice(optimisticIndex, 1);
          draft.value = content;
          pageError.value = `${failure.title} — ${detail}`;
        }
      } else if (failure.retainUnconfirmedTurn) {
        // 超时、读流断开、提前 EOF、畸形 done 都可能发生在服务端 COMMIT 之后。
        // 保留本地未确认轮次且不自动还稿，明确要求刷新会话核对后再继续。
        if (!provisionalAssistant) {
          provisionalAssistant = reactive({
            role: "assistant",
            content: "",
            recommendation: null,
            fresh: false,
            streaming: false,
            transient: false,
          });
          messages.value.push(provisionalAssistant);
        }
        optimisticUser.transient = false;
        optimisticUser.persistenceUnknown = true;
        provisionalAssistant.streaming = false;
        provisionalAssistant.transient = false;
        provisionalAssistant.persistenceUnknown = true;
        provisionalAssistant.streamError = true;
        provisionalAssistant.streamErrorTitle = failure.title;
        provisionalAssistant.streamErrorDetail = detail;
        provisionalAssistant.streamErrorAction = detail.includes("刷新会话")
          ? ""
          : "请刷新会话核对后再继续。";
        pageError.value = "";
        void scrollToBottom();
      }
    }
  } finally {
    sending.value = false;
    uploadPhase.value = ""; // 上传中途失败的清扫口（成功路径在 uploadPendingFiles 尾清）
    streamAbort.value = null;
    stopRequested.value = false;
    // 流结束复位跟随守卫（不动程序性滚动标记——收尾平滑滚动可能仍在飞，
    // 其间的 scroll 事件仍需按程序性对待，否则会把跟随误杀在半路上）。
    atBottom.value = true;
    newContentCount.value = 0;
  }
}

// batch 成功到 live feed 刷新的数秒窗口，由本地权威响应先划出工作段；feed
// 一旦到位会以全部真实任务 created_at 继续对账。新会话/切会话时归零。
const attachmentSegmentBoundaryMs = ref(0);

function collectCarriedFiles() {
  return currentWorkSegmentFiles(
    messages.value,
    conversationTasks.value,
    attachmentSegmentBoundaryMs.value,
  );
}

function openWorkbench() {
  // 进入本次会话的协作工作台（分工架构 + 逐个召集 + 进度）。不归档会话——
  // 工作台里还要继续从蓝图召集 Agent；会话作协作锚点保持存续。
  if (conversationId.value) {
    router.push(`/workbench/${conversationId.value}`);
  }
}

// ── 原地召集（对话轴内联确认，范式 2a 单入口）─────────────────────────
// 宪法边界：导引绝不代召集——自动路由只生成可解释方案，真正开工仍由人点击。
// 单/多 Agent 统一走原子的 POST /api/tasks/batch（服务端 fail-closed）。只在
// ①整份方案就绪 ②附件可被唯一、安全地路由时提供；信息不全回到同一 composer
// 补充，绝不要求工程师填写参数表或手工挑选执行者。
const opening = ref(null); // 「照此方案开工」进行中的会话 id（按会话作用域，CRS R1-P2：
// 全局布尔会在切会话后把新会话的开工按钮一并禁死；API client 无超时，卡住的旧请求
// 可无限期封锁新会话的唯一开工入口）
// 本地已召集账（CRS R0-P2）：批量创建成功后 conversationTasks 轮询最长滞后 5s，
// 期间 openableCount 若仍计入已成功成员，按钮复活可被二次点击造重复任务。
// key=`${会话id}:${agent_id}`，跨会话天然隔离；feed 数据到位后与 agentTaskInfo 双保险。
const locallySummoned = reactive({});
// 会话可写态（Codex R0-P2）：getConversation/createConversation 如实带出，concluded
// 只读会话不提供内联召集（否则创建必 409）。未知（null）= fail-closed 不提供。
const conversationStatus = ref(acceptanceFixture?.conversationStatus || null);
// Agent 输入契约缓存（Codex R0-P1）：POST /api/tasks 不做即时 schema 校验（校验在
// worker 运行期），故「自动整理就绪」必须由前端按 input_schema.required 或附件
// 后缀契约逐项判定后才提供开工按钮——契约拉不到 / 未知一律 fail-closed，并留在
// 当前对话继续追问，绝不回退到字段表。
const agentSchemaCache = reactive({
  ...(acceptanceFixture?.agentSchemas || {}),
}); // agent_id -> { loaded: true, version, packageDigest, schema, inputMode, allowedExtensions }
const agentSchemaLoadSeq = new Map();

async function refreshAgentSchema(agentId, { force = false } = {}) {
  if (!force && agentId in agentSchemaCache) return agentSchemaCache[agentId];
  const seq = (agentSchemaLoadSeq.get(agentId) || 0) + 1;
  agentSchemaLoadSeq.set(agentId, seq);
  agentSchemaCache[agentId] = {
    loaded: false,
    version: null,
    packageDigest: null,
    schema: null,
    inputMode: null,
    allowedExtensions: null,
  };
  try {
    const detail = await getAgent(agentId);
    // 旧预取响应不得覆盖一次更晚的人点击强制刷新；否则 cache 又会退回旧 schema。
    if (agentSchemaLoadSeq.get(agentId) !== seq) return agentSchemaCache[agentId] || null;
    agentSchemaCache[agentId] = {
      loaded: true,
      version: typeof detail?.version === "string" ? detail.version : null,
      packageDigest: typeof detail?.package_snapshot_digest === "string"
        ? detail.package_snapshot_digest
        : null,
      schema: (detail && detail.input_schema) || null,
      inputMode: (detail && detail.input_mode) || null,
      allowedExtensions: Array.isArray(detail?.input_allowed_extensions)
        ? detail.input_allowed_extensions
        : null,
    };
  } catch {
    if (agentSchemaLoadSeq.get(agentId) !== seq) return agentSchemaCache[agentId] || null;
    agentSchemaCache[agentId] = {
      loaded: true,
      version: null,
      packageDigest: null,
      schema: null,
      inputMode: null,
      allowedExtensions: null,
    };
  }
  return agentSchemaCache[agentId];
}

function ensureAgentSchemasForMessages() {
  // 方案卡出现（新回复或历史恢复）即预取成员 Agent 的输入契约；失败记 null=不就绪。
  // cache 条目携版本；真正开工仍强制刷新，绝不让 agent_id 永久绑定旧 schema。
  for (const m of messages.value) {
    const plan = m && m.recommendation;
    if (!plan || plan.decision !== "orchestrate" || !Array.isArray(plan.agents)) continue;
    for (const a of plan.agents) {
      const id = a.agent_id;
      if (!id || id in agentSchemaCache) continue;
      void refreshAgentSchema(id);
    }
  }
}

async function refreshAgentSchemasForPlan(plan) {
  const ids = [...new Set(
    (Array.isArray(plan?.agents) ? plan.agents : [])
      .map((agent) => agent?.agent_id)
      .filter(Boolean),
  )];
  const entries = await Promise.all(
    ids.map((agentId) => refreshAgentSchema(agentId, { force: true })),
  );
  const pinnedVersions = {};
  const pinnedPackageDigests = {};
  for (let index = 0; index < ids.length; index += 1) {
    const entry = entries[index];
    if (
      entry?.loaded !== true ||
      typeof entry.version !== "string" ||
      !entry.version ||
      typeof entry.packageDigest !== "string" ||
      !/^[a-f0-9]{64}$/.test(entry.packageDigest)
    ) {
      return null;
    }
    pinnedVersions[ids[index]] = entry.version;
    pinnedPackageDigests[ids[index]] = entry.packageDigest;
  }
  return ids.length > 0 ? { pinnedVersions, pinnedPackageDigests } : null;
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
// Codex R1 P2：validation_started 是开工 bootstrap——它总在 charter_intro 之后
// 立刻出现，若同权处理，T2 承诺的 charter 开场句会在入场瞬间被「校验输入
// 契约…」顶掉、永不上屏。故 bootstrap 仅作兜底：charter 或任何实质过程旁白
// （工具/阶段/业务 agent_log）在场时优先；无 charter 的任务行为不变。
function latestProcessNote(events) {
  let bootstrap = "";
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const ev = events[i];
    if (STATE_EVENT_TYPES.has(ev.event_type)) continue;
    const note = describeEvent(ev);
    if (!note) continue;
    if (ev.event_type === "validation_started") {
      if (!bootstrap) bootstrap = note;
      continue;
    }
    return note;
  }
  return bootstrap;
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
          // 批七 O3 事件通道：channel 首见 dependency_resolved → 接力回波
          // （playedRelay 抑制重复投递；状态沿通道先到也只播一次）。放在工作态
          // 早退之前——事件史扫描不依赖当前快照状态。
          if ((events || []).some(
            (ev) => ev.payload && ev.payload.workflow_event_type === "dependency_resolved"
          )) {
            playRelayEcho(id);
          }
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

// 成员级就绪（fail-closed）：按 Agent 声明的输入模式确定性判定。
// params 校验当前 schema；file_upload 校验真实已保存附件与后缀契约；none 只接受
// 空输入。未知模式或契约漂移一律留在对话追问，不生成字段表。
function agentReady(agent, files = collectCarriedFiles()) {
  const contract = agentSchemaCache[agent.agent_id];
  if (
    contract?.loaded !== true ||
    typeof contract.version !== "string" ||
    !contract.version ||
    typeof contract.packageDigest !== "string" ||
    !/^[a-f0-9]{64}$/.test(contract.packageDigest)
  ) return false;
  return agentExecutionReady(
    contract,
    agent.prefilled_inputs || {},
    files,
  );
}

function attachmentRoutingForPlan(plan) {
  return planAttachmentRouting(plan, agentSchemaCache, collectCarriedFiles());
}

function agentReadyForPlan(plan, agent) {
  const routing = attachmentRoutingForPlan(plan);
  if (routing.ready !== true) return false;
  const assignedIds = new Set(routing.inputFileIdsByAgent[agent.agent_id] || []);
  const assignedFiles = collectCarriedFiles().filter((file) => assignedIds.has(file.id));
  return agentReady(agent, assignedFiles);
}

function planMaterialsForAgent(plan, agent) {
  const routing = attachmentRoutingForPlan(plan);
  if (routing.ready !== true || routing.canonical !== true) return [];
  return routing.attachmentsByAgent[agent.agent_id] || [];
}

function ignoredPlanMaterials(plan) {
  const routing = attachmentRoutingForPlan(plan);
  if (routing.ready !== true || routing.canonical !== true) return [];
  return routing.ignoredAttachments;
}

// 方案级可开工门：会话可写、至少一个 Agent、整份方案的结构化输入全部就绪。
// 附件由系统路由：单 Agent 方案可安全地把本轮附件交给唯一执行者；多 Agent
// 方案若仍有附件归属歧义则 fail-closed，回到同一个 composer 继续对话澄清，
// 绝不把工程师送去字段表或要求其手工分配 Agent。
function planOpenable(plan) {
  if (planHasInvalidSkillReuse(plan) === true) return false;
  if (planHasIncompleteOrchestration(plan) === true) return false;
  const carriedFiles = collectCarriedFiles();
  const attachmentRouting = planAttachmentRouting(
    plan,
    agentSchemaCache,
    carriedFiles,
  );
  return (
    !!conversationId.value &&
    conversationStatus.value === "active" &&
    batchCreationNeedsReconciliation.value !== true &&
    // 先拿到本会话任务快照再判断附件工作段，避免历史任务尚未加载时短暂误开放。
    (acceptanceMode || conversationTasksLoaded.value === true) &&
    sending.value !== true &&
    plan && Array.isArray(plan.agents) && plan.agents.length >= 1 &&
    plan.agents.every((agent) => {
      const assignedIds = new Set(attachmentRouting.inputFileIdsByAgent[agent.agent_id] || []);
      const assignedFiles = carriedFiles.filter((file) => assignedIds.has(file.id));
      return agentReady(agent, assignedFiles) === true;
    }) &&
    pendingFiles.value.length === 0 &&
    attachmentRouting.ready === true
  );
}

function summonedLocally(agent) {
  return locallySummoned[`${conversationId.value}:${agent.agent_id}`] === true;
}

function retryAlreadyStarted() {
  if (!activeRetryOf.value) return false;
  return conversationTasks.value.some(
    (task) => task.retry_of === activeRetryOf.value,
  );
}

function openableCount(plan) {
  if (planOpenable(plan) !== true) return 0;
  const untouched = activeRetryOf.value
    ? retryPlanArmed.value === true &&
      retryAlreadyStarted() !== true &&
      plan.agents.every((agent) => !summonedLocally(agent))
    : plan.agents.every((agent) => !agentTaskInfo(agent) && !summonedLocally(agent));
  return untouched ? plan.agents.length : 0;
}

function planHasTasks(plan) {
  if (activeRetryOf.value && retryPlanArmed.value === true) {
    return retryAlreadyStarted() || plan.agents.some((agent) => summonedLocally(agent));
  }
  return Array.isArray(plan?.agents) && plan.agents.some(
    (agent) => !!agentTaskInfo(agent) || summonedLocally(agent)
  );
}

function skillReuseStateForPlan(plan) {
  if (!plan || typeof plan !== "object" || !Object.hasOwn(plan, "skill_reuse")) {
    return { state: "absent", reference: null };
  }
  if (!Array.isArray(plan.agents)) return { state: "invalid", reference: null };
  try {
    return {
      state: "valid",
      reference: normalizeSkillReuseRef(plan.skill_reuse, {
        expectedAgentIds: plan.agents.map((agent) => agent?.agent_id),
      }),
    };
  } catch {
    return { state: "invalid", reference: null };
  }
}

function skillReuseForPlan(plan) {
  const result = skillReuseStateForPlan(plan);
  return result.state === "valid" ? result.reference : null;
}

function planHasInvalidSkillReuse(plan) {
  return skillReuseStateForPlan(plan).state === "invalid";
}

// 「照此方案开工」（批七 §3-B6 切 batch，owner 裁决本批切换）：一键把全部就绪
// 且未召集的成员按方案顺序**原子召集**——单次 POST /api/tasks/batch，全有全无
// （任一项非法整批 422 零写入，逐项错误清单如实透出，绝不半建）。这一键由人
// 亲手点下=人召集；导引从未获得任何自动路径。方案 after（方案下标依赖）随行
// 重映射为批内下标 → 服务端映射真 depends_on。
async function openPlan(plan) {
  if (opening.value === conversationId.value && opening.value !== null) return;
  if (planHasInvalidSkillReuse(plan)) {
    ElMessage.warning("Skill 复用证据无法核验，本次未创建任务；请继续对话让系统重新编排。");
    focusComposer();
    return;
  }
  if (planHasIncompleteOrchestration(plan)) {
    ElMessage.warning("方案有执行单元未能纳入，请继续说明或让系统重新编排");
    focusComposer();
    return;
  }
  if (planOpenable(plan) !== true) {
    ElMessage.error("方案信息尚未全部就绪——请在下方继续说明或发送待处理附件。");
    return;
  }
  // 会话 id 提前钉死（CRS R0-P1 语义保留）：原子端点下不存在「中途切会话」的
  // 半建窗口，但请求发出前仍须复核未切换，绝不把旧方案的任务写进别的会话。
  const approvedConvId = conversationId.value;
  const approvedRetryOf = activeRetryOf.value;
  const submittedPlanSnapshot = {
    conversationId: approvedConvId,
    retryOf: approvedRetryOf,
  };
  // 整份方案一次原子创建；绝不只启动 ready 子集，也不静默剥离依赖。
  const targets = plan.agents.map((agent) => ({ a: agent }));
  if (
    approvedRetryOf === null &&
    targets.some(({ a }) => agentTaskInfo(a) || summonedLocally(a))
  ) return;
  opening.value = approvedConvId;
  let batchAttempt = null;
  try {
    const refreshedPins = await refreshAgentSchemasForPlan(plan);
    if (!conversationSnapshotMatches(submittedPlanSnapshot, {
      conversationId: conversationId.value,
      routeConversationId: typeof route.query.c === "string" ? route.query.c : "",
      retryOf: activeRetryOf.value,
      requestedRetryOf: requestedRetryOf.value,
    })) return;
    if (refreshedPins === null || planOpenable(plan) !== true) {
      ElMessage.error("执行单元输入契约已更新或暂时无法核对——本次未创建任务，请继续补充信息。");
      return;
    }
    const { pinnedVersions, pinnedPackageDigests } = refreshedPins;
    const reusedSkill = skillReuseForPlan(plan);
    const carriedFiles = collectCarriedFiles();
    const attachmentRouting = planAttachmentRouting(
      plan,
      agentSchemaCache,
      carriedFiles,
    );
    if (attachmentRouting.ready !== true) {
      ElMessage.error("附件归属尚不能唯一确定——请在下方继续说明由哪个环节使用。");
      return;
    }
    const items = targets.map(({ a }, index) => {
      const after = Array.isArray(a.after) ? a.after : [];
      return {
        agentId: a.agent_id,
        name: automaticTaskName(plan, a, index),
        inputs: a.prefilled_inputs || {},
        inputFileIds: attachmentRouting.inputFileIdsByAgent[a.agent_id] || [],
        retryOf: retryLineageForPlanItem(approvedRetryOf, after),
        after,
        skillPackageRef:
          reusedSkill?.matched_agent_id === a.agent_id
            ? reusedSkill
            : undefined,
      };
    });
    const candidateAttempt = {
      schemaVersion: 1,
      conversationId: approvedConvId,
      retryOf: approvedRetryOf,
      items,
      pinnedVersions,
      pinnedPackageDigests,
      operationId: createBatchOperationId(),
      submittedPlanSnapshot,
    };
    let durableAttempt;
    try {
      // 必须在 POST 前把同一 operation_id 与精确请求快照写入会话级日志。
      // 写入失败即不发请求；绝不能先请求、等网络异常后才尝试记 key。
      durableAttempt = persistBatchCreationAttempt(candidateAttempt);
    } catch (journalError) {
      ElMessage.error(
        `无法安全保存本次开工标识，本次未发起任务：${journalError.message || "本地操作日志不可用"}`,
      );
      return;
    }
    batchAttempt = { ...durableAttempt, targets };
    batchCreationUnknownByConversation[approvedConvId] = batchAttempt;
    const createdBatch = await createTasksBatch({
      conversationId: batchAttempt.conversationId,
      items: batchAttempt.items,
      pinnedVersions: batchAttempt.pinnedVersions,
      pinnedPackageDigests: batchAttempt.pinnedPackageDigests,
      operationId: batchAttempt.operationId,
    });
    const creationJournalCleared = clearDurableBatchCreation(batchAttempt);
    if (!conversationSnapshotMatches(submittedPlanSnapshot, {
      conversationId: conversationId.value,
      routeConversationId: typeof route.query.c === "string" ? route.query.c : "",
      retryOf: activeRetryOf.value,
      requestedRetryOf: requestedRetryOf.value,
    })) {
      // A 的任务已经由服务端原子创建，但用户已切到 B；只提醒 A 的订阅刷新，
      // 绝不把附件边界、retry 动作门或成功提示写进当前 B 会话。
      pokeConversation(approvedConvId);
      return;
    }
    const createdTimes = (createdBatch?.tasks || [])
      .map((task) => Date.parse(task?.created_at))
      .filter((value) => Number.isFinite(value));
    attachmentSegmentBoundaryMs.value = createdTimes.length > 0
      ? Math.max(...createdTimes)
      : Date.now();
    for (const { a } of targets) locallySummoned[`${approvedConvId}:${a.agent_id}`] = true;
    // retry_of 是一次性系统上下文。服务端整批成功后才消费；失败时保留 query，
    // 工程师可以在同一对话继续说明后重试，不会丢审计血缘。
    const consumedRetryOf = approvedRetryOf;
    let retryUrlCleaned = true;
    if (consumedRetryOf) {
      // POST 已提交后立即关闭本地动作门，再单独清地址栏。即使导航失败，也绝不
      // 进入下面的“零任务落库”错误分支或让同一方案二次开工。
      retryPlanArmed.value = false;
      if (activeRetryOf.value === consumedRetryOf) verifiedRetryOf.value = null;
      if (requestedRetryOf.value === consumedRetryOf) {
        retryUrlCleaned = await removeRetryQuery();
      }
    }
    ensureConversationTasksFeed(); // 督战 chip 保鲜：召集即接上会话任务订阅
    ElMessage.success(`已按方案召集 ${targets.length} 名成员——进度与签发都会来这里找你`);
    if (creationJournalCleared !== true) {
      ElMessage.warning("任务已创建，但本地开工记录尚未安全清除；本会话继续锁定以避免重复创建");
    }
    if (retryUrlCleaned !== true) {
      ElMessage.warning("任务已创建，但地址栏恢复标记未清理；本页已关闭重复开工入口");
    }
  } catch (err) {
    if (batchAttempt && batchCreatePersistenceUnknown(err) === true) {
      if (conversationSnapshotMatches(submittedPlanSnapshot, {
        conversationId: conversationId.value,
        routeConversationId: typeof route.query.c === "string" ? route.query.c : "",
        retryOf: activeRetryOf.value,
        requestedRetryOf: requestedRetryOf.value,
      })) {
        ElMessage.warning(
          "创建状态待核——无法确认任务是否已写入；本方案已锁定，请用同一操作标识核对，禁止重复开工。",
        );
      }
      return;
    }
    const structuredDetail = unwrapDetail(err?.detail);
    // 走到这里的 4xx/422 已由 batchCreatePersistenceUnknown 判定为权威零写入。
    // 必须按提交时钉死的会话与 operation_id 先清日志，再看用户是否仍停留在
    // 原会话；否则 A 请求期间切到 B 会被下面的视图守卫提前 return，永久锁住 A。
    clearDurableBatchCreation(batchAttempt);
    if (!conversationSnapshotMatches(submittedPlanSnapshot, {
      conversationId: conversationId.value,
      routeConversationId: typeof route.query.c === "string" ? route.query.c : "",
      retryOf: activeRetryOf.value,
      requestedRetryOf: requestedRetryOf.value,
    })) return;
    if (structuredDetail?.code === "conversation_not_active") {
      conversationStatus.value = structuredDetail.conversation_status || "concluded";
      ElMessage.error(
        "该协作会话已结束，本次确定未创建任务——请返回历史查看，或新建对话重新发起。",
      );
      return;
    }
    if (structuredDetail?.code === "skill_package_reuse_invalid") {
      ElMessage.warning(
        "Skill 复用证据在开工前未通过复核，本次确定未创建任务；请继续对话让系统重新编排。",
      );
      return;
    }
    // 全有全无：整批 422 零写入。逐项错误清单必须清晰可读（R5 走查）——
    // 玫红仅真失败；client 对非字符串 detail 会 JSON.stringify，这里解回结构。
    let batchErrors = null;
    if (typeof err.detail === "string" && err.detail.startsWith("{")) {
      try {
        const parsed = JSON.parse(err.detail);
        batchErrors = parsed?.detail?.batch_errors || parsed?.batch_errors || null;
      } catch {
        /* 保底走原文 */
      }
    }
    if (Array.isArray(batchErrors) && batchErrors.length > 0) {
      const lines = batchErrors.map((e) => {
        const t = targets[e.index];
        const who = t ? t.a.agent_name : `第 ${(e.index ?? 0) + 1} 项`;
        return `${who}：${(e.errors || []).join("；")}`;
      });
      ElMessage.error(`召集未执行（全有全无，未创建任何任务）——${lines.join("；")}`);
    } else {
      ElMessage.error(`召集失败（未创建任何任务）：${err.detail || err.message || "请稍后重试"}`);
    }
  } finally {
    if (opening.value === approvedConvId) opening.value = null; // 只清本会话的忙态
  }
}

async function reconcileBatchCreation() {
  const attempt = batchCreationUnknown.value;
  if (!attempt || opening.value === attempt.conversationId) return;
  if (attempt.journalCorrupt === true) {
    ElMessage.error(
      "本地开工记录无法安全读取。为避免重复任务，本会话保持锁定；请先从任务列表核对并联系管理员处理。",
    );
    return;
  }
  opening.value = attempt.conversationId;
  try {
    const createdBatch = await createTasksBatch({
      conversationId: attempt.conversationId,
      items: attempt.items,
      pinnedVersions: attempt.pinnedVersions,
      pinnedPackageDigests: attempt.pinnedPackageDigests,
      operationId: attempt.operationId,
    });
    const creationJournalCleared = clearDurableBatchCreation(attempt);
    if (!conversationSnapshotMatches(attempt.submittedPlanSnapshot, {
      conversationId: conversationId.value,
      routeConversationId: typeof route.query.c === "string" ? route.query.c : "",
      retryOf: activeRetryOf.value,
      requestedRetryOf: requestedRetryOf.value,
    })) {
      pokeConversation(attempt.conversationId);
      return;
    }
    const createdTimes = (createdBatch?.tasks || [])
      .map((task) => Date.parse(task?.created_at))
      .filter((value) => Number.isFinite(value));
    attachmentSegmentBoundaryMs.value = createdTimes.length > 0
      ? Math.max(...createdTimes)
      : Date.now();
    for (const item of attempt.items) {
      locallySummoned[`${attempt.conversationId}:${item.agentId}`] = true;
    }
    let retryUrlCleaned = true;
    if (attempt.retryOf) {
      retryPlanArmed.value = false;
      if (activeRetryOf.value === attempt.retryOf) verifiedRetryOf.value = null;
      if (requestedRetryOf.value === attempt.retryOf) retryUrlCleaned = await removeRetryQuery();
    }
    ensureConversationTasksFeed();
    ElMessage.success(
      `已核对：原开工请求已创建 ${attempt.items.length} 个任务，没有重复创建`,
    );
    if (creationJournalCleared !== true) {
      ElMessage.warning("任务已核对成功，但本地开工记录尚未安全清除；本会话继续锁定");
    }
    if (retryUrlCleaned !== true) {
      ElMessage.warning("任务已创建，但地址栏恢复标记未清理；本页已关闭重复开工入口");
    }
  } catch (err) {
    const structuredDetail = unwrapDetail(err?.detail);
    const stillViewingAttempt = conversationSnapshotMatches(attempt.submittedPlanSnapshot, {
      conversationId: conversationId.value,
      routeConversationId: typeof route.query.c === "string" ? route.query.c : "",
      retryOf: activeRetryOf.value,
      requestedRetryOf: requestedRetryOf.value,
    });
    if (
      batchCreatePersistenceUnknown(err) === true ||
      [401, 403].includes(err?.status)
    ) {
      if (stillViewingAttempt) {
        ElMessage.warning("创建状态仍待核——原操作标识已保留，禁止换 key 重复开工。");
      }
      return;
    }
    clearDurableBatchCreation(attempt);
    if (!stillViewingAttempt) return;
    if (structuredDetail?.code === "conversation_not_active") {
      conversationStatus.value = structuredDetail.conversation_status || "concluded";
      ElMessage.error(
        "已核对：会话已结束，原开工请求确定未创建任务——请返回历史查看，或新建对话重新发起。",
      );
      return;
    }
    ElMessage.error(`核对确认本次未创建任务：${err.detail || err.message || "请重新生成方案"}`);
  } finally {
    if (opening.value === attempt.conversationId) opening.value = null;
  }
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
const conversationTasks = ref(acceptanceFixture?.conversationTasks || []);
const conversationTasksLoaded = ref(acceptanceMode);

// ADR-0034：单个 completed 用户任务自动形成一张候选；多任务会话留给未来
// Workflow Revision，不在成员墙上批量长卡。acceptance fixture 只提供只读快照。
const acceptanceAssetCandidate = acceptanceFixture?.assetCandidate || null;
const assetCandidate = ref(null);
const assetCandidatePhase = ref(acceptanceAssetCandidate ? "loading" : "idle");
const assetCandidateError = ref("");
const assetCandidateTaskId = ref(acceptanceAssetCandidate?.source?.task_id || null);
let assetCandidateRequestSeq = 0;
const acceptanceSkillPackageReviewContent =
  acceptanceFixture?.skillPackageReviewContent || null;
const skillPackageReviewContent = ref(null);
const skillPackageReviewPhase = ref("idle");
const skillPackageReviewError = ref("");
let skillPackageReviewRequestSeq = 0;

watch(
  () => [
    assetCandidate.value?.skill_package?.id || "",
    assetCandidate.value?.skill_package?.package_digest || "",
  ],
  ([packageId, packageDigest], [previousId, previousDigest] = []) => {
    if (packageId === previousId && packageDigest === previousDigest) return;
    skillPackageReviewRequestSeq += 1;
    skillPackageReviewContent.value = null;
    skillPackageReviewPhase.value = "idle";
    skillPackageReviewError.value = "";
  },
);

async function verifyAcceptanceAssetCandidate() {
  if (!acceptanceMode || !acceptanceAssetCandidate) return;
  const task = eligibleAssetCandidateTask(conversationTasks.value);
  try {
    const verified = await verifyAssetCandidateIntegrity(
      acceptanceAssetCandidate,
      { expectedTaskId: task?.id },
    );
    if (
      task?.id !== verified.source.task_id
      || verified.source.conversation_id !== conversationId.value
    ) {
      throw new TypeError("验收候选没有绑定当前任务与会话");
    }
    assetCandidate.value = verified;
    assetCandidatePhase.value = "ready";
  } catch (error) {
    assetCandidate.value = null;
    assetCandidatePhase.value = "unavailable";
    assetCandidateError.value = candidateErrorMessage(error);
  }
}

onMounted(() => {
  void verifyAcceptanceAssetCandidate();
});

function candidateErrorMessage(error) {
  const detail = unwrapDetail(error?.detail);
  if (detail && typeof detail === "object" && typeof detail.message === "string") {
    return detail.message;
  }
  if (typeof detail === "string" && detail.trim()) return detail;
  return error?.message || "资产候选状态暂时无法核对";
}

async function loadCurrentSkillPackageReviewContent() {
  const current = assetCandidate.value;
  const packageRevision = current?.skill_package;
  if (
    !current
    || current.state !== "accepted"
    || !packageRevision
    || assetCandidatePhase.value !== "ready"
    || skillPackageReviewPhase.value === "loading"
  ) return;
  const requestContext = {
    seq: ++skillPackageReviewRequestSeq,
    packageId: packageRevision.id,
    packageDigest: packageRevision.package_digest,
  };
  const reviewIsCurrent = () => (
    requestContext.seq === skillPackageReviewRequestSeq
    && assetCandidate.value?.skill_package?.id === requestContext.packageId
    && assetCandidate.value?.skill_package?.package_digest === requestContext.packageDigest
  );
  skillPackageReviewContent.value = null;
  skillPackageReviewPhase.value = "loading";
  skillPackageReviewError.value = "";
  try {
    const content = acceptanceMode
      ? await normalizeSkillPackageReviewContent(acceptanceSkillPackageReviewContent, {
          expectedPackageId: packageRevision.id,
          expectedPackageDigest: packageRevision.package_digest,
          expectedFiles: packageRevision.files,
        })
      : await getSkillPackageReviewContent(packageRevision);
    if (!reviewIsCurrent()) return;
    skillPackageReviewContent.value = content;
    skillPackageReviewPhase.value = "ready";
  } catch (error) {
    if (!reviewIsCurrent()) return;
    skillPackageReviewContent.value = null;
    skillPackageReviewPhase.value = "error";
    skillPackageReviewError.value = candidateErrorMessage(error);
  }
}

async function ensureAssetCandidateForTasks(tasks, { force = false } = {}) {
  const task = eligibleAssetCandidateTask(tasks);
  if (!task) {
    assetCandidateRequestSeq += 1;
    assetCandidate.value = null;
    assetCandidatePhase.value = "idle";
    assetCandidateError.value = "";
    assetCandidateTaskId.value = null;
    return;
  }
  if (acceptanceMode) return;
  if (
    force !== true
    && assetCandidateTaskId.value === task.id
    && assetCandidatePhase.value !== "idle"
  ) return;

  const seq = ++assetCandidateRequestSeq;
  assetCandidateTaskId.value = task.id;
  assetCandidate.value = null;
  assetCandidatePhase.value = "loading";
  assetCandidateError.value = "";
  try {
    const formed = await createTaskAssetCandidate(task.id);
    if (
      seq !== assetCandidateRequestSeq
      || eligibleAssetCandidateTask(conversationTasks.value)?.id !== task.id
    ) return;
    assetCandidate.value = formed;
    assetCandidatePhase.value = "ready";
  } catch (error) {
    if (seq !== assetCandidateRequestSeq) return;
    assetCandidatePhase.value = "unavailable";
    assetCandidateError.value = candidateErrorMessage(error);
  }
}

async function reconcileAssetCandidate() {
  const task = eligibleAssetCandidateTask(conversationTasks.value);
  if (!task || !conversationId.value || acceptanceMode) return;
  const reconcileContext = {
    seq: ++assetCandidateRequestSeq,
    taskId: task.id,
    conversationId: conversationId.value,
  };
  const reconcileIsCurrent = () => assetCandidateRequestIsCurrent(
    reconcileContext,
    {
      seq: assetCandidateRequestSeq,
      taskId: eligibleAssetCandidateTask(conversationTasks.value)?.id || "",
      conversationId: conversationId.value,
    },
  );
  assetCandidateTaskId.value = task.id;
  assetCandidatePhase.value = "loading";
  assetCandidateError.value = "";
  try {
    const current = await getTaskAssetCandidate(task.id);
    if (!reconcileIsCurrent()) return;
    assetCandidate.value = current;
    assetCandidatePhase.value = "ready";
  } catch (error) {
    if (!reconcileIsCurrent()) return;
    const createReason = assetCandidateReconcileCreateReason(
      error?.status,
      unwrapDetail(error?.detail),
    );
    if (createReason !== null) {
      try {
        const revised = await createTaskAssetCandidate(task.id);
        if (!reconcileIsCurrent()) return;
        assetCandidate.value = revised;
        assetCandidatePhase.value = "ready";
      } catch (createError) {
        if (!reconcileIsCurrent()) return;
        assetCandidatePhase.value = "reconcile_required";
        assetCandidateError.value = candidateErrorMessage(createError);
      }
      return;
    }
    assetCandidatePhase.value = "reconcile_required";
    assetCandidateError.value = candidateErrorMessage(error);
  }
}

async function decideCurrentAssetCandidate(action) {
  const current = assetCandidate.value;
  const currentTask = eligibleAssetCandidateTask(conversationTasks.value);
  if (
    !current
    || current.state !== "awaiting_human_review"
    || assetCandidatePhase.value !== "ready"
    || currentTask?.id !== current.source.task_id
    || assetCandidateTaskId.value !== current.source.task_id
    || current.source.conversation_id !== conversationId.value
    || acceptanceMode
  ) return;
  const decisionContext = {
    seq: ++assetCandidateRequestSeq,
    taskId: current.source.task_id,
    conversationId: conversationId.value,
  };
  assetCandidatePhase.value = "deciding";
  assetCandidateError.value = "";
  try {
    const decided = await decideAssetCandidate(current, action);
    if (!assetCandidateRequestIsCurrent(decisionContext, {
      seq: assetCandidateRequestSeq,
      taskId: eligibleAssetCandidateTask(conversationTasks.value)?.id || "",
      conversationId: conversationId.value,
    })) return;
    assetCandidate.value = decided;
    assetCandidatePhase.value = "ready";
    ElMessage.info(
      action === "accept"
        ? "已接受为资产候选；尚未登记或发布"
        : "已记录本次不保留；原任务证据不受影响",
    );
  } catch (error) {
    if (!assetCandidateRequestIsCurrent(decisionContext, {
      seq: assetCandidateRequestSeq,
      taskId: eligibleAssetCandidateTask(conversationTasks.value)?.id || "",
      conversationId: conversationId.value,
    })) return;
    // 409、断网或 5xx 都可能处于“服务端已提交、客户端未收到”窗口；不换摘要
    // 重放决定，锁到显式 GET 对账。
    assetCandidatePhase.value = "reconcile_required";
    assetCandidateError.value = candidateErrorMessage(error);
  }
}

async function decideCurrentSkillPackage(action) {
  const current = assetCandidate.value;
  const packageRevision = current?.skill_package;
  const currentTask = eligibleAssetCandidateTask(conversationTasks.value);
  if (
    !current
    || current.state !== "accepted"
    || packageRevision?.state !== "pending_review"
    || assetCandidatePhase.value !== "ready"
    || currentTask?.id !== current.source.task_id
    || assetCandidateTaskId.value !== current.source.task_id
    || current.source.conversation_id !== conversationId.value
    || acceptanceMode
  ) return;
  if (
    action === "approve"
    && (
      skillPackageReviewPhase.value !== "ready"
      || skillPackageReviewContent.value?.package_id !== packageRevision.id
      || skillPackageReviewContent.value?.package_digest !== packageRevision.package_digest
    )
  ) {
    skillPackageReviewPhase.value = "error";
    skillPackageReviewError.value = "必须先核验并审阅当前隔离包的真实字节，才能批准复用。";
    ElMessage.warning("真实包内容尚未核验，本次未提交批准决定。");
    return;
  }
  const packageDecisionContext = {
    seq: ++assetCandidateRequestSeq,
    taskId: current.source.task_id,
    conversationId: conversationId.value,
  };
  assetCandidatePhase.value = "deciding";
  assetCandidateError.value = "";
  try {
    const decidedPackage = await decideSkillPackage(packageRevision, action);
    if (!assetCandidateRequestIsCurrent(packageDecisionContext, {
      seq: assetCandidateRequestSeq,
      taskId: eligibleAssetCandidateTask(conversationTasks.value)?.id || "",
      conversationId: conversationId.value,
    })) return;
    assetCandidate.value = { ...current, skill_package: decidedPackage };
    assetCandidatePhase.value = "ready";
    ElMessage.info(
      action === "approve"
        ? "工程师已批准该精确隔离包；相似新任务可由系统自动匹配"
        : "已记录本次不批准复用；Candidate 与原任务证据不受影响",
    );
  } catch (error) {
    if (!assetCandidateRequestIsCurrent(packageDecisionContext, {
      seq: assetCandidateRequestSeq,
      taskId: eligibleAssetCandidateTask(conversationTasks.value)?.id || "",
      conversationId: conversationId.value,
    })) return;
    assetCandidatePhase.value = "reconcile_required";
    assetCandidateError.value = candidateErrorMessage(error);
  }
}

// ── 批七编队投影状态（§1.3/§1.4）────────────────────────────────────────────
const agentNames = useAgentNames(); // 名册+meta（domain/clearance/charter）懒加载单例
const relayEchoIds = ref(new Set()); // 正在播接力回波的 task_id（2 轮自停）
const playedRelay = new Set(); // 组件内重播抑制（O3）：同 task 只播一次
let prevPhaseById = new Map(); // 上一帧 memberPhase 快照（接力翻转沿检测）
const expandedEvidence = ref(new Set());
const expandedRefusals = ref(new Set());

function playRelayEcho(id) {
  if (playedRelay.has(id)) return;
  playedRelay.add(id);
  const next = new Set(relayEchoIds.value);
  next.add(id);
  relayEchoIds.value = next;
  setTimeout(() => {
    const s = new Set(relayEchoIds.value);
    s.delete(id);
    relayEchoIds.value = s;
  }, 3600); // flai-work-pulse 1.8s × 2 播完即停（StatusDock 同参）
}

// 接力翻转检测（T4/O3 双通道，同一 playedRelay 抑制）：①状态沿——上一帧
// waiting_upstream、本帧已入活跃态（灯翻转本体，事件缺席时的兜底）；②事件
// 通道——task channel 首见 dependency_resolved（快照窗跳过 waiting_upstream
// 帧时状态沿永不触发，靠事件补位）。重复投递/两通道先后到达都只播一次。
function detectRelayFlips(tasks) {
  const nextMap = new Map();
  for (const t of tasks) {
    const phase = memberPhase(t);
    nextMap.set(t.id, phase);
    const was = prevPhaseById.get(t.id);
    if (
      was === "waiting_upstream" &&
      phase !== "waiting_upstream" &&
      phase !== "failed" &&
      phase !== "cancelled"
    ) {
      playRelayEcho(t.id);
    }
  }
  prevPhaseById = nextMap;
}

function memberPhaseOf(a) {
  const info = agentTaskInfo(a);
  return info ? memberPhase(info.latest) : null;
}

function memberLampBg(a) {
  const info = agentTaskInfo(a);
  if (!info) return "var(--hairline)";
  if (memberPhase(info.latest) === "waiting_upstream") return "transparent"; // 空心灯
  return taskLampColor(info.latest.status);
}

function memberStatusWord(a) {
  const info = agentTaskInfo(a);
  if (!info) return "";
  return memberPhase(info.latest) === "waiting_upstream" ? "等待接力" : statusLabel(info.latest.status);
}

function memberStatusColor(a) {
  const info = agentTaskInfo(a);
  if (!info) return "var(--ink-soft)";
  return memberPhase(info.latest) === "waiting_upstream"
    ? "var(--ink-soft)"
    : taskLampColor(info.latest.status);
}

// 等待接力旁白（T1/T4 文案表）：上游名经 agentNames 解析人话名；上游真失败
// → 中性灰兜底句（非红——下游没失败，只是接不上力）。
function upstreamNarration(t) {
  const byId = new Map(conversationTasks.value.map((x) => [x.id, x]));
  const ups = (t.depends_on || []).map((d) => byId.get(d)).filter(Boolean);
  const anyFailed = ups.some((u) => u.status === "failed" || u.status === "cancelled");
  if (anyFailed) return "前序失败，接力已暂停 · 详情→";
  const names = ups.map((u) => agentNames.map[u.agent_id] || u.agent_id.slice(0, 12));
  const label = names.length ? names.join("、") : "上游成员";
  return `等待〈${label}〉的产物 · 就绪后自动接力`;
}

// T2 首行口播：charter 开场句已由后端在创建期落成持久化事件（agent_log +
// charter_intro，Codex R0 P2）——经常规事件通道进 stageNotes，与其余旁白同源。
// 不再回退读当前注册表元数据：包升级会让在途旧任务「被念出」新 charter
//（时点漂移伪史），审计事件流里却无此句。
function stagelineFor(a) {
  const info = agentTaskInfo(a);
  if (!info) return "";
  const t = info.latest;
  if (memberPhase(t) === "waiting_upstream") return upstreamNarration(t);
  if (t.status === "cancelled" && (t.depends_on || []).length > 0) return "已取消（上游未交付）";
  return stagelineText(t);
}

// domain/密级 pill（注册表投影；domain 徽走中性描边不占彩色预算——信任色五槽
// 已锁满，domain 不再引入新色轴）。
const DOMAIN_LABEL = {
  policy_qa: "制度",
  standards_qa: "标准",
  fault_history: "故障史",
  sys_calc: "系统计算",
  cfd_sim: "CFD 仿真",
  test_data: "试验数据",
  design_opt: "设计优化",
  generic: "通用",
};
const CLEARANCE_LABEL = { public: "公开", internal: "内部", sensitive: "敏感" };

function domainLabelOf(a) {
  const d = agentNames.meta[a.agent_id]?.domain;
  return d ? DOMAIN_LABEL[d] || d : "";
}

function clearanceOf(a) {
  return agentNames.meta[a.agent_id]?.clearance || "";
}

function clearanceLabelOf(a) {
  const c = clearanceOf(a);
  return c ? CLEARANCE_LABEL[c] || c : "";
}

// 成熟度人话标签走 format.js SSOT（与 TodayPage maturityLabel 同口径），
// 未声明成熟度的存量包诚实回落原值，不编造。
const maturityLabel = (m) => MATURITY[m]?.label ?? m;

// 成员行分类学披露（降噪批，五律④行话进披露）：domain/密级/成熟度/发布状态
// 拼一行收进 agent-name 的 title 悬浮——全部走既有 SSOT 人话标签
// （L0→「L0 · 原型」、draft→「草案态」），忠实投影，缺项不占位不编造。
function agentTaxonomyTip(a) {
  const parts = [];
  const d = domainLabelOf(a);
  if (d) parts.push(`领域 ${d}`);
  const c = clearanceLabelOf(a);
  if (c) parts.push(`密级 ${c}`);
  if (a.maturity) parts.push(`成熟度 ${maturityLabel(a.maturity)}`);
  if (a.status) parts.push(agentStatusLabel(a.status));
  return parts.length ? parts.join(" · ") : null;
}

function evidenceOfTask(taskId) {
  return taskEvidenceOf(taskId);
}

// 最新可执行方案卡下标：后端每个 assistant 轮都会整体替换 recommendation
// 快照（含替换成空）。最后一轮不是 orchestrate 时，历史方案动作全部退役，
// 不能从过期计划启动任务；资产沉淀只发生在 completed 后的候选卡。
const latestPlanIdx = computed(() => latestActionablePlanIndex(messages.value, {
  activeRetryOf: activeRetryOf.value,
  retryPlanArmed: retryPlanArmed.value,
}));

function evidenceWithheldOf(a) {
  const info = agentTaskInfo(a);
  return info !== null && taskEvidenceWithheld(info.latest.id) === true;
}

function evidenceSummaryOf(a) {
  const info = agentTaskInfo(a);
  if (!info) return null;
  return taskEvidenceSummary(info.latest.id);
}

function refusalsOf(a) {
  const info = agentTaskInfo(a);
  if (!info) return [];
  const ev = taskEvidenceOf(info.latest.id);
  return ev ? ev.refusals : [];
}

function toggleEvidence(taskId) {
  const s = new Set(expandedEvidence.value);
  if (s.has(taskId)) s.delete(taskId);
  else s.add(taskId);
  expandedEvidence.value = s;
}

function toggleRefusal(taskId) {
  const s = new Set(expandedRefusals.value);
  if (s.has(taskId)) s.delete(taskId);
  else s.add(taskId);
  expandedRefusals.value = s;
}

// L1 编队总览（§1.4）：成员任务快照聚合；无任何已召集任务时零占位不渲行。
// Codex R0 P1：聚合方案成员的**全部**会话任务，不再各取最新一条——同 Agent
// 多任务时，最新条已终态会让旧任务还在跑/待签的编队被谎报「协作已收束」。
function squadTasksOf(plan) {
  const ids = new Set(plan.agents.map((a) => a.agent_id));
  return conversationTasks.value.filter((t) => ids.has(t.agent_id));
}

function squadSegs(plan) {
  const tasks = squadTasksOf(plan);
  if (tasks.length === 0) return null;
  return squadSegments(squadCounts(tasks), tasks, nowTick.value);
}

function squadHasWork(plan) {
  const tasks = squadTasksOf(plan);
  return tasks.some((t) => TASK_WORK_STATES.has(t.status));
}

// 会话任务快照每次落地 → 对账 task channel 持有集；有任一工作态成员任务 →
// 秒表开，全部终态 → 秒表停（不空转）。必须声明在 conversationTasks 之后：
// watch source 创建时即求值，TDZ 抛错会被 Vue callWithErrorHandling 吞成
// console.error，watcher 静默死亡（Codex R0-P0，实拍佐证：秒表恒 0s、旁白恒
// 兜底句——引擎看似在场实则从未运转）。
watch(
  conversationTasks,
  (tasks) => {
    syncLiveChannels();
    detectRelayFlips(tasks); // 批七 T4：waiting_upstream→活跃 状态沿 → 接力回波
    for (const t of tasks) ensureTaskEvidence(t); // 批七 T5/T6：终审面成员拉依据摘要
    void ensureAssetCandidateForTasks(tasks);
    const anyWork = tasks.some((t) => TASK_WORK_STATES.has(t.status));
    // 等待接力行虽无秒表，但编队行/等待旁白仍要随快照活现——工作态判定不变
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
let convTasksLoadedStop = null;
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
  if (convTasksLoadedStop) {
    convTasksLoadedStop();
    convTasksLoadedStop = null;
  }
  if (convTasksHandle) {
    convTasksHandle.release();
    convTasksHandle = null;
  }
  convTasksHandleFor = null;
  conversationTasks.value = [];
  conversationTasksLoaded.value = acceptanceMode;
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
  convTasksLoadedStop = watch(
    convTasksHandle.state.loaded,
    (loaded) => {
      if (convTasksHandleFor === id) conversationTasksLoaded.value = loaded === true;
    },
    { immediate: true },
  );
}

// ── 会话恢复（左栏历史点击 / 刷新 /?c=<id>）──

function resetToFresh(clearError = true) {
  messages.value = [];
  started.value = false;
  conversationId.value = "";
  conversationStatus.value = null;
  reconciliationRequired.value = false;
  assetBuilderOpen.value = false;
  assetCandidateRequestSeq += 1;
  assetCandidate.value = null;
  assetCandidatePhase.value = "idle";
  assetCandidateError.value = "";
  assetCandidateTaskId.value = null;
  attachmentSegmentBoundaryMs.value = 0;
  draft.value = "";
  pendingFiles.value = [];
  releaseConversationTasksFeed();
  resetScrollFollow(); // 新会话/切换会话：滚动跟随守卫一并复位
  if (clearError) pageError.value = "";
}

// 垂类问答 recommendation 判据：无 decision 键（refuse/orchestrate 是导引专属）
// 且真带 findings/refusals 数组、至少一边非空——双空已被包 schema 拒收。
function qaRecommendation(rec) {
  if (!rec || rec.decision) return false;
  const f = Array.isArray(rec.findings) ? rec.findings : null;
  const r = Array.isArray(rec.refusals) ? rec.refusals : null;
  if (f === null && r === null) return false;
  return (f || []).length > 0 || (r || []).length > 0;
}

// 恢复在途标记：?c 深链（含 2a 回流）落地时 getConversation 在途的窗口里，
// 不渲染可交互的空态 hero（「假起手」）、send 早退——否则此刻发消息会因
// conversationId 尚空而意外新建会话（双镜头 P2 实审咬出的竞态）。
async function loadConversation(id, { preserveOnFailure = false, isCurrent = () => true } = {}) {
  if (!preserveOnFailure) resetToFresh();
  restoring.value = true;
  try {
    const conv = await getConversation(id);
    if (isCurrent() !== true) return false;
    // 失败恢复若来自已归档会话，不能让工程师落到一个后端必定 409 的旧输入框。
    // 自动换成新对话，同时保留 retry_of；工程师仍只需输入文字或上传附件。
    if (activeRetryOf.value && conv.status !== "active") {
      const retryOf = activeRetryOf.value;
      resetToFresh();
      await router.replace({ path: "/", query: { retry_of: retryOf } });
      ElMessage.info("原对话已归档——已为这次失败恢复打开新对话，审计血缘仍会保留");
      return true;
    }
    // 对账模式在请求成功前保留「保存状态待核」轮次和核对按钮；只有拿到
    // 服务端权威会话后才清掉本地快照与 reconciliationRequired 锁。
    if (preserveOnFailure) resetToFresh();
    conversationId.value = conv.id;
    restoreBatchCreationForConversation(conv.id);
    recordConversationFirstUserContent(conv.id, conv.messages); // E-4 侧栏标题数据面：拉过全量的会话才供得起首条用户消息
    conversationStatus.value = conv.status || null; // 只读会话如实带出（Codex R0-P2）
    started.value = true;
    messages.value = (conv.messages || []).map((m) => ({
      role: m.role,
      content: m.content,
      recommendation: m.recommendation || null,
      attachments: m.attachments && m.attachments.length ? m.attachments : undefined,
      createdAt: m.created_at || null,
      // 历史方案只读展示。要开工，工程师在同一主输入补一句即可获得基于当前
      // Registry/schema 的 fresh 方案，避免旧计划或丢失 retry 血缘被复活。
      fresh: false,
      retryOf: null,
    }));
    await scrollToBottom();
    if (isCurrent() !== true) return false;
    ensureConversationTasksFeed(); // 恢复的历史会话若已带 orchestrate 方案，立即接上订阅
    ensureAgentSchemasForMessages(); // 历史方案卡同样预取输入契约（内联就绪判据）
    return true;
  } catch (err) {
    if (isCurrent() !== true) return false;
    if (activeRetryOf.value) {
      const retryOf = activeRetryOf.value;
      resetToFresh();
      await router.replace({ path: "/", query: { retry_of: retryOf } });
      ElMessage.warning("原对话不可用——已打开新对话，失败任务血缘仍会保留");
      return true;
    }
    pageError.value = err.detail || err.message || "会话加载失败";
    return false;
  } finally {
    if (isCurrent() === true) restoring.value = false;
  }
}

async function reconcileConversation() {
  if (reconciliationRequired.value !== true || reconciling.value === true) return;
  if (acceptanceMode) {
    ElMessage.info("这是保存待核状态快照；真实核对请回到正式对话页面");
    return;
  }
  const id = conversationId.value;
  if (!id) {
    pageError.value = "无法核对：当前会话标识缺失，请从左侧历史重新打开会话";
    return;
  }

  reconciling.value = true;
  pageError.value = "";
  const requiredBeforeRefresh = reconciliationRequired.value;
  // 对账前快照滞留的未确认用户原文（B2）：核对成功后若服务端权威会话确认
  // 该轮未落库，把原文还回输入草稿（现状原文随本地快照被清、草稿为空）。
  // fail-closed：只有权威会话确认无此轮才还稿；确认已落库则清本地快照不还稿。
  const unconfirmedTurn = messages.value.find(
    (m) => m.role === "user" && m.persistenceUnknown === true,
  );
  const unconfirmedContent = unconfirmedTurn ? unconfirmedTurn.content : "";
  try {
    const reconciled = await loadConversation(id, { preserveOnFailure: true });
    reconciliationRequired.value = reconciliationLockAfterRefresh({
      required: requiredBeforeRefresh,
      succeeded: reconciled,
    });
    if (reconciled === true && unconfirmedContent) {
      // loadConversation 成功后 messages 已是服务端权威清单：查得到同文用户
      // 轮=已落库（不还稿）；查不到=确认未落库，原文还稿供用户续写重发。
      const persisted = messages.value.some(
        (m) => m.role === "user" && m.content === unconfirmedContent,
      );
      if (!persisted) {
        draft.value = unconfirmedContent;
        ElMessage.info("服务端确认该轮未保存——原话已退回输入框");
      }
    }
  } catch (err) {
    // loadConversation 当前会把读取错误转成 false；此 catch 仍为未来改动保底：
    // 任意未预期异常都不能误解锁，也不能吞掉对账失败原因。
    reconciliationRequired.value = true;
    pageError.value = err.detail || err.message || "会话核对失败";
  } finally {
    reconciling.value = false;
  }
}

// c 与 retry_of 是同一份导航意图：先核对失败任务权威状态，再决定能否加载/使用
// 指向的会话。一个 watcher + 单调序号消除原先两个 watcher 同拍竞跑；迟到的 A
// 读取也由 isCurrent 门挡在写入 B 的 messages/status 之前。
let routeNavigationSeq = 0;
let internalRouteBindingEpoch = 0;
let internalRouteBinding = null;

function armInternalRouteBinding(conversationIdToBind, retryOfToBind) {
  internalRouteBinding = {
    conversationId: conversationIdToBind,
    retryOf: retryOfToBind,
    epoch: ++internalRouteBindingEpoch,
  };
  return internalRouteBinding;
}

function clearInternalRouteBinding(binding) {
  if (internalRouteBinding?.epoch === binding?.epoch) internalRouteBinding = null;
}

function consumeInternalRouteBinding(rawConversationId, rawRetryOf) {
  const binding = internalRouteBinding;
  if (!binding) return false;
  // 任一下一拍路由都消费 token：精确匹配代表内部镜像；不匹配代表真实外部导航，
  // token 立即作废，不能留到以后误吞一次同地址回访。
  internalRouteBinding = null;
  return internalConversationRouteBindingMatches(binding, rawConversationId, rawRetryOf);
}

async function syncRouteContext(rawConversationId, rawRetryOf) {
  if (acceptanceMode) return;
  if (consumeInternalRouteBinding(rawConversationId, rawRetryOf)) {
    // 内部 URL 镜像仍是一笔新的路由权威。它不重读刚创建的空会话，但必须
    // 作废此前外部 B 导航已经发出的 getTask/loadConversation；否则 B 的迟到
    // 响应会覆盖本次已钉死的 A 恢复语义。binding 只可能由已验证快照 arm。
    routeNavigationSeq += 1;
    retryValidationSeq += 1;
    retryPlanArmed.value = false;
    verifiedRetryOf.value = normalizeRetryLineage(rawRetryOf);
    retryContextChecking.value = false;
    return;
  }
  const navigationSeq = ++routeNavigationSeq;
  await validateRetryContext(rawRetryOf);
  if (navigationSeq !== routeNavigationSeq) return;

  const conversationRouteId = typeof rawConversationId === "string"
    ? rawConversationId.trim()
    : "";
  if (conversationRouteId) {
    // retry 新增/切换时即便 c 未变也必须重读：只有先确认 retry authority 后，
    // loadConversation 才能把 concluded 会话安全地换成新的可写对话。
    if (conversationRouteId !== conversationId.value || activeRetryOf.value !== null) {
      await loadConversation(conversationRouteId, {
        isCurrent: () => navigationSeq === routeNavigationSeq,
      });
    }
    return;
  }
  if (started.value || messages.value.length) resetToFresh();
  // 取消一个在途的历史会话读取时，它的 finally 会因 epoch 失效而不清标记；
  // 当前无 c 的导航事务负责把恢复锁归零。
  restoring.value = false;
}

onMounted(() => {
  void syncRouteContext(route.query.c, route.query.retry_of);
});
onUnmounted(() => {
  routeNavigationSeq += 1;
  internalRouteBinding = null;
  feedDisposed = true; // 先封门再释放：卸载后任何 await 续体不得再 acquire
  releaseConversationTasksFeed();
});

// 左栏切会话、失败回流与 query 清理都作为同一个路由快照串行处理。
watch(
  () => [route.query.c, route.query.retry_of],
  ([c, retryOf]) => {
    void syncRouteContext(c, retryOf);
  },
);
</script>

<style scoped>
.guide-page {
  max-width: 784px;
  margin: 0 auto;
  padding-bottom: 132px; /* 让会话内容避开紧凑后的固定 composer（含诚实地板句） */
}
.guide-main { min-width: 0; }
/* 空状态：hero + composer 作为一组在可用视口内居中。 */
.guide-page.is-empty {
  padding-bottom: 0;
  min-height: calc(100vh - 56px);
}
.guide-page.is-empty .guide-main {
  min-height: calc(100vh - 56px);
  display: flex;
  flex-direction: column;
  justify-content: center;
}
/* ── 起手 hero ── */
.guide-hero {
  text-align: center;
  padding: 12px 12px 14px;
  /* 入场动效走全局 .fx-rise（模板上加类）：起手 hero 只在「零消息」落地态渲染
   * 一次=真「刚落地」无需门控；用全局类天然继承 App.vue 的 reduced-motion
   * 降级（双镜头审合流 finding——本地 animation 没有降级覆盖，已迁移根治）。 */
}
/* 品牌徽记使用严格六重旋转对称的真实图形资产；idle 静止。 */
.hero-mark {
  margin: 0 auto 11px;
}
/* 时段感问候：抒情场合走衬线，字号克制小于主标题，颜色降一级不抢戏。 */
.hero-greeting {
  font-family: var(--serif);
  font-size: 13.5px;
  font-weight: 500;
  color: var(--ink-soft);
  margin: 0 0 3px;
}
.hero-title {
  font-family: var(--serif);
  font-size: 26px;
  font-weight: 600;
  color: var(--ink);
  margin: 0;
  letter-spacing: 0.2px;
}
.hero-routing-promise {
  max-width: 520px;
  margin: var(--space-3) auto 0;
  color: var(--ink-soft);
  font-size: var(--fs-sm);
  line-height: 1.7;
}

.page-alert {
  margin-bottom: 14px;
}

/* ── 会话流 ── */
.thread {
  display: flex;
  flex-direction: column;
  gap: 22px;
  padding: 14px 2px 6px;
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
  padding: 9px 13px;
  border-radius: 16px 16px 4px 16px;
  box-shadow: var(--shadow-card);
}
.user-text {
  white-space: pre-wrap;
  font-size: 14px;
  line-height: 1.55;
}
.user-files {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
/* 悬浮时间戳：静止态隐去，hover 或行内焦点（focus-within，触屏/键盘可达）整行
 * 气泡才渐显（历史消息/新回合皆可能无 createdAt——user 乐观推送不带时间戳，
 * v-if 已兜底不渲染空占位）。 */
.bubble-time {
  opacity: 0;
  font-size: 11px;
  color: var(--ink-faint);
  transition: opacity var(--motion-fast) var(--ease-out-soft);
}
.bubble-row:hover .bubble-time,
.bubble-row:focus-within .bubble-time { opacity: 1; }
.user-bubble .bubble-time {
  display: block;
  margin-top: 6px;
  text-align: right;
}
/* 「保存待核」amber 小标记（B3）：与助手侧 .stream-interrupted.is-unknown
 * 同槽同语义（--trust-pending=仅未核/降级），几何沿用 stream-reconcile-btn
 * 同款描边/圆角/字号档。 */
.user-unknown-chip {
  display: inline-block;
  margin-top: 7px;
  padding: 1px 8px;
  border: 1px solid rgba(var(--trust-pending-rgb), 0.45);
  border-radius: 7px;
  background: rgba(var(--trust-pending-rgb), 0.08);
  color: var(--trust-pending);
  font-size: 11.5px;
  font-weight: 700;
  line-height: 1.6;
}
@media (prefers-reduced-motion: reduce) {
  .bubble-time { transition: none; }
}

/* 助手：小 mark + 流动排版 */
.bubble-row.assistant { gap: 10px; }
.ai-mark {
  flex: 0 0 auto;
  margin-top: 2px;
}
.ai-body {
  flex: 1 1 auto;
  min-width: 0;
  max-width: calc(100% - 36px);
}
.ai-name {
  font-size: 12px;
  color: var(--ink-faint);
  font-weight: 600;
  letter-spacing: 0.3px;
  margin-bottom: 5px;
}
.ai-name .bubble-time {
  margin-left: 8px;
  font-weight: 500;
  letter-spacing: normal;
}
/* ai-lead 现为 MarkdownLite 容器（W5）：块结构由组件内 md-* 承担，容器只定
 * 基础字号/行高/下距；pre-wrap 移除（段落切分已由块级渲染接管）。 */
.ai-lead {
  font-size: 14.25px;
  line-height: 1.62;
  color: var(--ink);
  margin: 0 0 12px;
}
.ai-lead :deep(.md-p:first-child),
.ai-lead :deep(.md-h:first-child) {
  margin-top: 0;
}

/* 思考指示（N3 双行容器：旋转对称品牌标+状态词+秒表，次行=慢等待诚实提示） */
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
.ai-thinking .tlabel { margin-left: 0; }
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
.stream-interrupted {
  margin: 8px 0 0;
  padding: 7px 10px;
  border-left: 2px solid var(--trust-fail);
  background: var(--error-chip-bg);
  color: var(--ink-soft);
  font-size: 12px;
  line-height: 1.55;
}
.stream-interrupted strong {
  color: var(--trust-fail);
  font-weight: 700;
}
.stream-interrupted.is-unknown {
  border-left-color: var(--trust-pending);
  background: rgba(var(--trust-pending-rgb), 0.08);
}
.stream-interrupted.is-unknown strong {
  color: var(--trust-pending);
}
/* 用户主动停止（流式停止钮）：中性墨——主动控制不是失败，与 persisted=false
 * 的红边失败、保存待核的 amber 严格区分；不占 clay 以外新色槽。 */
.stream-interrupted.is-stopped {
  border-left-color: var(--hairline);
  background: var(--surface-raised);
}
.stream-interrupted.is-stopped strong {
  color: var(--ink-soft);
}
.stream-interrupted-action {
  display: block;
  margin-top: 3px;
  color: var(--ink-soft);
}
.stream-reconcile-btn {
  display: inline-flex;
  align-items: center;
  margin-top: 7px;
  padding: 4px 9px;
  border: 1px solid rgba(var(--trust-pending-rgb), 0.45);
  border-radius: 7px;
  background: transparent;
  color: var(--trust-pending);
  font: inherit;
  font-size: 11.5px;
  font-weight: 700;
  cursor: pointer;
}
.stream-reconcile-btn:hover:not(:disabled) {
  background: rgba(var(--trust-pending-rgb), 0.08);
}
.stream-reconcile-btn:disabled {
  opacity: 0.55;
  cursor: wait;
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
  /* clay 预算（批次五 C3）：eyebrow 降灰，与 WorkbenchSession .sess-goal-kicker 同语法。 */
  color: var(--ink-faint);
}
.plan-kicker.refuse { color: var(--trust-pending); margin-bottom: 10px; display: inline-block; }
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
.route-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin: 0 0 var(--space-3);
  padding: 10px 12px;
  border: 1px solid var(--hairline-soft);
  border-radius: var(--radius-md);
  background: var(--paper-rail);
  color: var(--ink);
  font-size: var(--fs-xs);
  font-weight: 700;
}
.route-summary-state {
  color: var(--ink-soft);
  font-weight: 500;
  text-align: right;
}
.route-summary-state.is-pending { color: var(--trust-pending); }
.skill-reuse-inline {
  flex: 1 0 100%;
  color: var(--clay);
  font-weight: 700;
}
.route-disclosure {
  margin: 0;
  border-top: 1px solid var(--hairline-soft);
  border-bottom: 1px solid var(--hairline-soft);
}
.route-disclosure > summary {
  min-height: 44px;
  display: list-item;
  padding: 12px 2px;
  color: var(--ink-soft);
  font-size: var(--fs-xs);
  font-weight: 700;
  cursor: pointer;
}
.route-disclosure > summary:focus-visible {
  outline: 2px solid var(--focus-ring-clay);
  outline-offset: 2px;
  border-radius: var(--radius-sm);
}
.route-disclosure:not([open]) > .route-disclosure-body { display: none; }
.route-disclosure-body { padding: var(--space-3) 0 var(--space-4); }
.skill-reuse-detail {
  display: grid;
  gap: 3px;
  margin: 0 0 var(--space-4);
  padding: 10px 12px;
  border-left: 2px solid var(--clay-softer);
  color: var(--ink-soft);
  font-size: var(--fs-xs);
}
.skill-reuse-detail strong { color: var(--ink); }
.skill-reuse-detail small { color: var(--ink-faint); line-height: 1.55; }
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
  /* clay 预算（批次五 C3）：重述建议序号圈逐条重复，降中性——序号是结构
     不是强调。 */
  color: var(--ink-soft);
  background: transparent;
  border: 1.5px solid var(--ink-faint);
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
   注意特异性：.agent-card 基类是 flex 且声明在后，必须用双类压制。
   去盒化（批次五 C3）：降盒为 hairline 分隔的扁平行——去同色底+描边，
   行间发丝线分隔；hover 只留 --hover-tint 底，不抬不影。 */
.agent-card.sa-row {
  display: block;
  padding: 10px 14px;
  gap: 0;
  background: transparent;
  border: none;
  border-radius: 0;
  border-bottom: 1px solid var(--hairline-soft);
}
.agent-card.sa-row:hover {
  transform: none;
  box-shadow: none;
  background: var(--hover-tint);
}
.plan-materials,
.ignored-plan-materials {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  color: var(--ink-faint);
  font-size: var(--fs-xs);
  line-height: 1.5;
}
.plan-materials { margin: 7px 0 0 17px; }
.ignored-plan-materials {
  margin: 10px 14px 2px;
  padding-top: 9px;
  border-top: 1px dashed var(--hairline-soft);
}
.plan-materials-label { font-weight: 600; color: var(--ink-soft); }
.plan-material-chip {
  display: inline-flex;
  min-width: 0;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 2px 7px;
  border: 1px solid var(--hairline);
  border-radius: 999px;
  background: var(--paper-rail);
  color: var(--ink-soft);
}
.sa-head {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
}
.sa-head .agent-name { flex: 0 1 auto; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sa-head .agent-role { margin: 0; flex: 0 1 auto; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sa-spacer { flex: 1 1 auto; min-width: 8px; }
.sa-head .agent-status { margin: 0; flex: 0 0 auto; }
.sa-head .agent-actions { margin: 0; flex: 0 0 auto; }
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

/* ── 批七编队投影（§1.3/§1.4）───────────────────────────────────────────── */
/* L1 编队总览行：纯文本聚合，数字 tabular-nums 零动画替换 */
.sa-squad-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin: 2px 0 8px;
  font-size: 12.5px;
  color: var(--ink-soft);
  font-variant-numeric: tabular-nums;
}
.sa-squad-line .squad-sep { color: var(--ink-faint); }
.squad-seg.tone-clay { color: var(--clay); font-weight: 600; }
.squad-seg.tone-amber { color: var(--trust-pending); font-weight: 600; }
.squad-seg.tone-rose { color: var(--trust-fail); font-weight: 600; }

/* 等待接力=空心灯（T1）：1px ink 描边圆，绝无 is-pulsing（O2 探针断言互斥） */
.status-lamp.is-hollow {
  background: transparent;
  box-shadow: inset 0 0 0 1px var(--ink-soft);
}
/* 接力回波（T4）：复制 StatusDock dock-pulse-echo 参数（不提升作用域），
   2 轮播完自停；触发一次性（组件内 Set 抑制重播） */
.status-lamp.sa-relay-echo {
  animation: flai-work-pulse var(--pulse-duration) ease-in-out 2;
}
.sa-stageline.is-waiting-upstream { color: var(--ink-soft); }

/* 敏感密级 pill（降噪批后唯一常驻的分类学标记）：amber=受控/未核语义槽，
   是信任信号不是行话——domain/非敏感密级/成熟度/发布状态已收进 agent-name
   title（五律④），不再上成员行主视觉。 */
.sa-clearance-pill {
  flex: none;
  font-size: 11px;
  line-height: 1;
  padding: 3px 7px;
  border-radius: 6px;
  border: 1px solid var(--hairline);
  color: var(--ink-soft);
  white-space: nowrap;
}
.sa-clearance-pill.is-sensitive {
  border-color: color-mix(in srgb, var(--trust-pending) 55%, transparent);
  color: var(--trust-pending);
}

/* T5 依据摘要 chip：含未核整 chip amber 底纹；点击展开 EvidenceList */
.sa-evidence-chip {
  display: inline-flex;
  align-items: center;
  margin: 6px 0 0 17px;
  padding: 4px 10px;
  border: 1px solid var(--hairline);
  border-radius: 8px;
  font-size: 12px;
  color: var(--ink-soft);
  cursor: pointer;
  font-variant-numeric: tabular-nums;
  transition: border-color var(--motion-fast) var(--ease-out-soft);
}
/* 批八 withheld：静态遮蔽标记——不可点（无内容可展），虚线弱化非警示 */
.sa-evidence-chip.is-withheld {
  cursor: default;
  border-style: dashed;
  color: var(--ink-faint);
}
.sa-evidence-chip:hover { border-color: var(--clay-softer); }
.sa-evidence-chip.has-unverified {
  border-color: color-mix(in srgb, var(--trust-pending) 45%, transparent);
  background: color-mix(in srgb, var(--trust-pending) 8%, transparent);
  color: var(--trust-pending);
}
/* 去盒化（批次五 C3）：去底色+描边，只留顶部发丝线与上方 chip 分隔。 */
.sa-evidence-expand {
  margin: 8px 0 0 17px;
  padding: 10px 12px;
  border-top: 1px solid var(--hairline-soft);
}

/* T6 拒答行：amber 非红——诚实拒答是履约不是失败（O6 探针） */
.sa-refusal-line {
  margin: 6px 0 0 17px;
  font-size: 12.5px;
  color: var(--trust-pending);
  cursor: pointer;
}
.sa-refusal-detail {
  margin: 4px 0 0 17px;
  padding: 0 0 0 16px;
  font-size: 12.5px;
  color: var(--ink-soft);
}
.sa-refusal-detail li { margin: 3px 0; }
.sa-refusal-detail .refusal-suggestion { color: var(--ink-faint); margin-left: 6px; }

@media (prefers-reduced-motion: reduce) {
  .status-lamp.sa-relay-echo { animation: none; }
}
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
 * sa-row 改版后无 DOM 承载——删规则；.agent-card 基类保留（class token 本身是
 * m9 e2e 的 nth 钩子，模板中的 "agent-card" 字符串绝不可摘）；批次五 C3 去盒化
 * 后，其背景/描边/hover 影由 .agent-card.sa-row 覆盖为 hairline 扁平行。 */
.agent-name {
  font-weight: 700;
  font-size: 15px;
  color: var(--ink);
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
  /* clay 预算（批次五 C3）：逐行「速览→」常驻降灰，hover 回 clay 保操作暗示。 */
  color: var(--ink-soft);
  margin-left: 2px;
  transition: color var(--motion-fast) var(--ease-out-soft);
}
.status-peek:hover {
  color: var(--clay);
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
  /* clay 预算（批次五 C3）：与 .status-peek 同语法——常驻 ink-soft，行 hover 回 clay。 */
  color: var(--ink-soft);
  font-size: 11.5px;
  transition: color var(--motion-fast) var(--ease-out-soft);
}
.status-artifact:hover .artifact-open {
  color: var(--clay);
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
/* clay 预算（批次五 C3）：分工徽章逐成员行重复出现，降灰承担信息不占强调
   预算——方案卡的 clay 只留给工作态灯与主 CTA（开工/工作台钮）。 */
.role-tag {
  display: inline-block;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.4px;
  color: var(--ink-soft);
  background: var(--hover-tint);
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
/* 自动整理摘要只报告已抽取项数；字段和值不作为工程师的常驻输入面板。 */
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
.agent-stripped {
  margin: 2px 0 10px;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--ink-soft);
}
.agent-actions { display: flex; }
/* 决策收敛后的成员行（disclosure grammar：正常态不说话，异常态才有标签） */
.agent-actions { gap: 10px; align-items: center; flex-wrap: wrap; }
.agent-readytag {
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-soft);
}
.agent-readytag.is-pending { color: var(--trust-pending); }
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
.open-plan-btn.is-pending {
  border: 1px solid rgba(var(--trust-pending-rgb), 0.45);
  background: rgba(var(--trust-pending-rgb), 0.08);
  color: var(--trust-pending);
  cursor: pointer;
}
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
.route-summary-state.plan-alert {
  margin-top: 0;
  font-size: inherit;
  line-height: inherit;
  color: var(--trust-pending);
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

/* 文件 chip（composer 待发区与 user 气泡共用）：几何走 token，四件（图标/名称/
   大小/相位）baseline 对齐；名称超宽截断，大小等宽防抖。 */
.file-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-sm);
  color: var(--ink-soft);
  background: var(--paper-rail);
  border: 1px solid var(--hairline);
  border-radius: var(--radius-md);
  padding: var(--space-1) 10px;
  max-width: 100%;
}
.chip-icon { flex: 0 0 auto; display: inline-flex; color: var(--ink-faint); }
.chip-name {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.chip-size { flex: 0 0 auto; font-size: var(--fs-xs); color: var(--ink-faint); }
.chip-phase { flex: 0 0 auto; font-size: var(--fs-xs); }
/* 上传中=工作/进行中槽位（真实相位，非装饰进度）；已上传=中性墨（completed
   恒中性，不给绿）。 */
.file-chip.uploading .chip-phase { color: var(--clay); }
.chip-phase.is-done { color: var(--ink-faint); }
/* 失败只染状态词（W1 语法），文件名/大小保持墨色——失败是状态不是文件。 */
.file-chip.error { border-color: var(--error-chip-border); background: var(--error-chip-bg); }
.chip-phase.is-error { color: var(--trust-fail); font-weight: 600; }
/* 移除钮=原生 button（键盘可达，:focus-visible 走全局 clay 环）；视觉 18px
   静谧点，hover 才给底色 affordance。 */
.chip-x {
  flex: 0 0 auto;
  display: inline-grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border: none;
  border-radius: var(--radius-xs);
  background: transparent;
  cursor: pointer;
  color: var(--ink-faint);
  font-size: var(--fs-sm);
  font-weight: 700;
  line-height: 1;
  padding: 0;
  transition: background var(--motion-fast) var(--ease-out-soft), color var(--motion-fast) var(--ease-out-soft);
}
.chip-x:hover { background: var(--hover-tint); color: var(--ink); }
.chip-x:disabled { opacity: 0.4; cursor: not-allowed; background: transparent; }

/* ── composer ── */
/* 空态时与 hero 同组垂直居中：本 margin 即 hero↔composer 的唯一直接间距（token 归位）。 */
.composer { margin-top: 12px; }
/* 会话开始后：固定悬浮在视口底部，上缘渐隐让消息从下方穿过（Claude 布局）。 */
.composer.composer-fixed {
  position: fixed;
  left: var(--sidebar-w);
  right: 0;
  bottom: 0;
  z-index: 15;
  margin-top: 0;
  /* 底部悬浮条减重（W5）：多轮对话时视觉更轻，渐隐遮罩起点不变 */
  padding: 8px var(--space-6) 10px;
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
.batch-reconcile-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
  padding: 9px 10px 9px 14px;
  border: 1px solid rgba(var(--trust-pending-rgb), 0.45);
  border-radius: 14px;
  background: rgba(var(--trust-pending-rgb), 0.08);
  color: var(--trust-pending);
  font-size: 12px;
  font-weight: 600;
}
.batch-reconcile-bar .open-plan-btn {
  min-height: 36px;
  padding: 8px 14px;
  white-space: nowrap;
}
.composer-files {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
  padding: 0 var(--space-1);
}
.composer-shell {
  background: var(--surface-raised);
  border: 1px solid var(--hairline);
  border-radius: 18px;
  box-shadow: var(--shadow-composer);
  padding: 4px;
  /* focus-within 抬升：位移走 --motion-med（比描边慢半拍的落地感），描边/投影
     保持 fast 即时反馈；reduced-motion 全静化见下方媒体块。 */
  transition: border-color var(--motion-fast) var(--ease-out-soft),
    box-shadow var(--motion-fast) var(--ease-out-soft),
    transform var(--motion-med) var(--ease-out-soft);
}
.composer-shell:focus-within {
  border-color: var(--focus-ring-clay);
  box-shadow: var(--shadow-composer), 0 0 0 4px rgba(var(--clay-rgb), 0.08);
  transform: translateY(-1px);
}
.composer-row {
  display: flex;
  align-items: flex-end;
  gap: 6px;
}
.composer-attach { flex: 0 0 auto; }
.icon-btn {
  width: 36px;
  height: 36px;
  border-radius: 11px;
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
  padding: 7px 4px;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.5;
  color: var(--ink);
}
.composer-input :deep(.el-textarea__inner::placeholder) { color: var(--ink-faint); }
/* 渐变/投影/hover/过渡走全局 .cta-clay（W0 真归位，模板已接线）——本类只留结构。 */
.send-btn {
  flex: 0 0 auto;
  width: 36px;
  height: 36px;
  border-radius: 11px;
  display: grid;
  place-items: center;
}
.send-btn.cta-clay:disabled {
  opacity: 1;
  background: var(--paper-rail);
  border: 1px solid var(--hairline);
  color: var(--ink-faint);
  box-shadow: none;
  cursor: not-allowed;
}
/* 停止钮（流式在飞时替换发送钮）：中性墨实心方块——主动停止是中性控制，
 * 不用红、不占 clay；结构尺寸与 .send-btn 一致，换形不抖动。 */
.stop-btn {
  background: var(--surface-raised);
  border: 1px solid var(--hairline);
  color: var(--ink-soft);
  cursor: pointer;
  transition: all var(--motion-fast) var(--ease-out-soft);
}
.stop-btn:hover { color: var(--ink); border-color: var(--ink-faint); }
@media (prefers-reduced-motion: reduce) {
  .stop-btn { transition: none; }
}
/* 诚实地板句（Claude「can make mistakes」哲学）：常驻同一 composer 容器内，
 * 会话进行中（composer 变 fixed 悬浮）也不消失；放进容器内部避免布局跳动。 */
.composer-hint {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 3px 10px 0;
  font-size: 10.5px;
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
  /* focus-within 抬升/描边过渡与 chip 交互态在 reduce 下瞬时呈现（状态本身
     由描边/环色承担，无需动画传达）。 */
  .composer-shell { transition: none; }
  .composer-shell:focus-within { transform: none; }
  .chip-x { transition: none; }
}

kbd {
  font-family: var(--mono);
  font-size: 10.5px;
  background: var(--paper-rail);
  border: 1px solid var(--hairline);
  border-radius: var(--radius-xs);
  padding: 1px 5px;
  color: var(--ink-soft);
}

/* 回到底部浮钮：悬浮于 composer 上方右侧（fixed，垂直向避开发送钮主操作），
 * 样式全走 token——surface-raised 底 + hairline 描边 + ink-soft 字，clay 不占用。 */
.back-to-bottom {
  position: fixed;
  right: 28px;
  bottom: 128px;
  z-index: 16;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 13px;
  border-radius: 17px;
  background: var(--surface-raised);
  border: 1px solid var(--hairline);
  box-shadow: var(--shadow-card);
  color: var(--ink-soft);
  font-size: 12px;
  cursor: pointer;
  transition: color var(--motion-fast) var(--ease-out-soft),
    border-color var(--motion-fast) var(--ease-out-soft);
}
.back-to-bottom:hover { color: var(--ink); border-color: var(--ink-faint); }
.btb-count {
  min-width: 17px;
  height: 17px;
  padding: 0 4px;
  border-radius: 9px;
  background: var(--paper-rail);
  border: 1px solid var(--hairline-soft);
  color: var(--ink-soft);
  font-size: 10.5px;
  line-height: 15px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}
@media (prefers-reduced-motion: reduce) {
  .back-to-bottom { transition: none; }
}
@media (max-width: 640px) {
  /* 375px：右缩进收紧，底部抬升量与移动端 composer 实高对齐，不遮发送钮。 */
  .back-to-bottom { right: 16px; bottom: 118px; }
}

@media (max-width: 640px) {
  .ai-body { max-width: calc(100% - 36px); }
  .plan-goal-title { font-size: 21px; }
  .route-summary { align-items: flex-start; flex-direction: column; }
  .route-summary-state { text-align: left; }
  .open-plan-btn,
  .workbench-btn { min-height: 44px; }
  .composer.composer-fixed { padding: 7px 12px 9px; }
  .batch-reconcile-bar { align-items: stretch; flex-direction: column; }
  .composer-hint .keys { display: none; }
  .icon-btn,
  .send-btn {
    width: 44px;
    height: 44px;
  }
}
</style>

<style>
/* 垂类问答依据卡（Codex R0 P1 接线）：中性纸面，依据行交给 EvidenceList
   （全链无绿）；拒答块灰字如实，不作警示红——拒答是承诺兑现非故障。 */
.qa-evidence-card { display: flex; flex-direction: column; gap: 14px; }
.qa-refusal { display: flex; flex-direction: column; gap: 2px; margin: 0 0 8px; }
.qa-refusal:last-child { margin-bottom: 0; }
.qa-refusal-reason { margin: 0; font-size: 13px; line-height: 1.55; color: var(--ink); }
.qa-refusal-suggestion { margin: 0; font-size: 12.5px; line-height: 1.5; color: var(--ink-soft); }

</style>
