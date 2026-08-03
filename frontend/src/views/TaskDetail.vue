<template>
  <div class="task-detail">
    <el-alert v-if="loadError" type="error" :title="loadError" show-icon :closable="false" />

    <!-- 首载骨架（A3）：只在「从未 loaded 且无错误」时撑主区轮廓，轮询期间/
         带旧值刷新绝不回骨架；失败态走上面 el-alert，骨架不吞错误。 -->
    <div v-if="!loaded && !loadError" class="td-skel">
      <SkeletonBlock height="26px" width="200px" />
      <SkeletonBlock height="14px" width="340px" />
      <SkeletonBlock height="76px" width="100%" />
      <SkeletonBlock height="220px" width="100%" />
      <SkeletonBlock height="120px" width="100%" />
    </div>

    <template v-if="task">
      <!-- M8：属于某协作会话的任务，提供返回工作台会话视图的入口（分组回溯）。 -->
      <div v-if="task.conversation_id" class="sess-backlink">
        <el-button text type="primary" @click="$router.push(`/workbench/${task.conversation_id}`)">
          ← 返回协作会话
        </el-button>
      </div>
      <!-- 桌面工艺批 W3：页级「主叙事 | 环境 rail」（Codex 环境仪表盘范式）。
           容器查询驱动——组件自身宽 ≥780px 双栏（260px rail；≥1120px 提 300px），更窄宿主自动单列；
           DOM 序=主列（含产物）先、rail（含来源）后，m2 的
           a[href*='/download'] .first 指向产物下载的契约保持。 -->
      <div class="td-grid" :class="{ 'td-sensitive': isSensitive }">
      <div class="td-main">
      <!-- N9 敏感整窗声明（ADR-0025 执行期落库分级）：形状+字重承载，零新色
           （Phase-2c 未读判例同款纪律）；框在 .td-sensitive 整窗双线。 -->
      <div v-if="isSensitive" class="sensitive-decl">
        <span class="sensitive-decl-mark" aria-hidden="true">◆</span>
        <span>敏感数据任务——执行期接触了受限文件、语料或工具产出，产物及其内容请按部门数据口径流转，不外发。</span>
      </div>
      <div class="page-header">
        <!-- 工作态流光带（P3，动效系统 v1）：v-if 绑真实 work-state，状态回落随之
             立即消失——诚实地板：流光=真的在跑。装饰性，不承载信息，故 aria-hidden。 -->
        <div v-if="isTaskWorking" class="work-flow-strip" aria-hidden="true"></div>
        <h2>任务详情</h2>
        <span v-if="isTaskWorking" class="work-pulse-dot"></span>
        <el-tag :type="statusTagType(task.status)">{{ statusLabel(task.status) }}</el-tag>
        <!-- 待你签发常驻徽章：与 el-tag 共存不替换（e2e 可能断言 el-tag 文案），
             复用 App.vue 全局 .pill-amber（工作台会话页同款用法）。 -->
        <span v-if="isWaitingReview" class="pill-amber">待你签发</span>
        <!-- 批量任务摘要（P2）：消解「全失败 case 仍显示绿色已完成」的误导——
             ok/failed 计数取自最后一条 summary_generated 折叠事件，纯前端派生。
             成功计数用中性 info 不给绿（3-lens trust P2 收口）：绿=仅真实 REAL
             结果，mock 前提下 case 计数给绿即假 REAL——与下方核验段中性口径
             同锁，同一数字同屏一种信任信号。 -->
        <template v-if="batchSummary">
          <el-tag size="small" type="info">成功 {{ batchSummary.ok }}</el-tag>
          <el-tag size="small" :type="batchSummary.failed > 0 ? 'danger' : 'info'">
            失败 {{ batchSummary.failed }}
          </el-tag>
        </template>
        <!-- waiting_review 不再停轮（channel 8s 降频承接，见 liveFeedCore.
             nextInterval）——跨会话人工放行结果免手动刷新即会到账；本按钮保留
             作带外补拉（poke），满足「现在就要」的即时性诉求。 -->
        <el-button text type="primary" class="refresh-btn" @click="pokeTask(taskId)">刷新</el-button>
        <!-- 仿真监控深链（PM 路线图 Next-1，S 级）：仅在浮窗已配置（同 localStorage
             开关，默认关零渲染）时出现。任务已关联仿真 run（metadata.sim_run_ref）时
             深链直达该 run 视图，否则回退 hub 首页。 -->
        <a v-if="simHubUrl" class="sim-link" :href="simHubUrl" target="_blank" rel="noopener" :title="simRunTitle">
          查看仿真监控<span v-if="simRunRef" class="sim-link-ref">（{{ simRunRef }}）</span> ↗
        </a>
      </div>

      <!-- 终态盖章（Codex CLI「─ Worked for Xs ─」落定仪式）：位置=标题/返回行之下、
           任务描述表之上——终态任务进页第一眼看到的官宣；组件自身对非终态渲染 null，
           零占位，不产生 a[href]/新文案与既有 e2e 断言冲突。animate=sealAnimate：
           仪式只属于亲历者，见下方 onTransition 订阅注释。 -->
      <CompletionSeal :task="task" :animate="sealAnimate" />

      <!-- 首屏只留一行轻量上下文；完整元数据（ID/版本/时间）折叠为次要，让产物与决策优先。 -->
      <div class="task-context">
        <span>Agent <b>{{ task.agent_id }}</b></span>
        <span class="ctx-dot">·</span>
        <span>创建人 {{ task.created_by }}</span>
        <span class="ctx-dot">·</span>
        <span>{{ formatTime(task.created_at) }}</span>
        <!-- N4a 血缘注记（迁移#12）：本任务由失败任务复制而来，深链回原任务。 -->
        <template v-if="task.retry_of">
          <span class="ctx-dot">·</span>
          <router-link class="ctx-retry-link" :to="`/tasks/${task.retry_of}`">
            重跑自 <span class="num-token">{{ task.retry_of }}</span>
          </router-link>
        </template>
        <!-- 批七 §1.6 接力血缘行：depends_on 忠实投影（上游名经任务/名册解析，
             解析失败回退 id 切片诚实不编）；与 retry_of 同区同语法。 -->
        <template v-if="relayLineage.length">
          <span class="ctx-dot">·</span>
          <span class="ctx-relay">接力自：<router-link
            v-for="(l, li) in relayLineage"
            :key="l.id"
            class="ctx-retry-link"
            :to="`/tasks/${l.id}`"
          >〈{{ l.name }}〉<template v-if="li < relayLineage.length - 1">、</template></router-link> →</span>
        </template>
      </div>

      <TaskJourney
        :task="task"
        :events="events"
        :model-calls="modelCalls"
        :model-calls-loaded="modelCallsLoaded"
        :model-calls-error="modelCallsError"
      />

      <el-alert
        v-if="task.error_message"
        type="error"
        :title="task.error_message"
        show-icon
        :closable="false"
        class="section"
      />

      <!-- 失败不是死胡同，但也不把工程师送进参数表。回到原对话，用文字或附件
           说明失败现象，由系统重新编排；绝不自动重跑。 -->
      <div v-if="task.status === 'failed'" class="retry-row">
        <el-button plain @click="retryAsNew">回到对话说明问题</el-button>
        <span class="retry-hint">直接补充文字或附件，系统结合原会话重新编排——平台不会自动重跑。</span>
      </div>

      <!-- 产物在主叙事列（签发前把要签的东西摆在眼前，放在「动作」之前——先看
           产物，再决定放行，信任核心 P0-2）；来源/元数据迁至环境 rail（下方
           aside，DOM 序在主列之后）——e2e 取 a[href*='/download'] 的 .first
           仍指向产物下载链接。 -->
      <div class="section" v-if="artifacts.length">
        <h3>产物<span v-if="isWaitingReview" class="artifact-review-hint">放行前请先审阅</span></h3>
        <div v-for="a in visibleArtifacts" :key="a.fileId" class="artifact-card">
          <!-- 逐卡收起 affordance（W3）：默认全展开不变；多产物任务可手动收纳
               已读卡。披露触发器=真 <button>（原生 Enter/Space，免 tabindex/
               keydown 手写），下载 <a> 是其兄弟——嵌套可交互控件是非法 ARIA
               结构，SR 会拍扁 button 后代（Codex R0 P2 + 3-lens P2 同修）。 -->
          <div class="artifact-head">
            <button
              type="button"
              class="artifact-toggle"
              :aria-expanded="!a.collapsed"
              @click="toggleArtifact(a)"
            >
              <el-icon class="artifact-chevron" aria-hidden="true">
                <ArrowRight v-if="a.collapsed" />
                <ArrowDown v-else />
              </el-icon>
              <span class="artifact-name">{{ a.filename }}</span>
              <!-- 类型标签（F6，Codex R6「文档 · MD」语法）：类型词+格式，不再裸后缀。 -->
            <span v-if="a.ext" class="artifact-ext-badge">{{ artifactTypeLabel(a.ext) }}</span>
              <span v-if="!a.loading && a.size" class="artifact-size">
                <span class="num-token">{{ formatSize(a.size) }}</span><template v-if="artifactLineCount(a) != null"> · <span class="num-token">{{ artifactLineCount(a) }}</span> 行</template>
              </span>
            </button>
            <a :href="downloadUrl(a.fileId)" download class="artifact-download">下载</a>
          </div>
          <div v-show="!a.collapsed">
            <div v-if="a.loading" class="artifact-body muted">加载中…</div>
            <div v-else-if="a.error" class="artifact-body artifact-error">产物加载失败：{{ a.error }}</div>
            <MarkdownLite
              v-else-if="a.isText && (a.ext === 'md' || a.ext === 'markdown')"
              :text="a.text"
              class="artifact-body"
            />
            <pre v-else-if="a.isText" class="artifact-body artifact-pre">{{ a.text }}</pre>
            <div v-else class="artifact-body muted">二进制文件，请下载后查看。</div>
          </div>
        </div>
        <!-- 产物尾部折叠（F5，Codex R6「显示另外 1 个 ⌄」/ Claude「Show 3 more」）：
             >3 件默认渲染前 3，真 button 单向展开（展开后本次浏览不再收回——
             与两家实拍一致）；前 3 恒渲染，m2 e2e 首下载锚不受扰。 -->
        <button
          v-if="hiddenArtifactCount > 0"
          type="button"
          class="artifact-more"
          :aria-expanded="false"
          @click="artifactsExpanded = true"
        >
          <span>显示另外 {{ hiddenArtifactCount }} 个</span>
          <el-icon class="artifact-more-icon" aria-hidden="true"><ArrowDown /></el-icon>
        </button>
        <!-- 渐进披露说明行（批次 D P1）：默认先给可读报告，数据/日志类产物由
             shouldCollapseArtifactForReview 自动收纳——把「为什么有的产物折着」
             讲成一句人话，下钻路径显式可见。计数来自真实折叠态，不估。 -->
        <p v-if="collapsedArtifactCount > 0" class="artifact-collapsed-hint">
          数据与日志类产物已默认收纳 <span class="num-token">{{ collapsedArtifactCount }}</span> 件——先读报告，展开即可逐项核对原始数据。
        </p>
      </div>

      <!-- 核验自证段（F3，kit11「校验方式」语法）：产物之后、动作之前——签发前
           最后一眼看到「这活儿怎么核验」；完成态则作为成果报告的自证层。
           class="section" 融入既有节奏（组件根 v-if 不渲染时 class 随之消失，
           无幽灵 margin）。 -->
      <VerificationCard class="section" :task="task" :events="events" :batch-summary="batchSummary" />

      <!-- 批七 §1.6 依据段（签发卡上方强制挂载）：findings 忠实投影；
           evidence_policy.required 但零依据 → amber 警示行（**不阻塞人签**——
           人是唯一签发者，警示只是把「没依据」摆在眼前）。拒答条 amber 非红。 -->
      <div v-if="evidenceFindings.length || evidenceRefusals.length || evidenceRequiredMissing || evidenceWithheld" class="section evidence-section">
        <h3>依据</h3>
        <div v-if="evidenceRequiredMissing" class="evidence-missing">
          本次输出未提供依据，请谨慎签发
        </div>
        <!-- 批八 withheld（O6，与 GuidePage/Workbench 同 store 口径）：密级受限
             产物零下载零计数——静态遮蔽行，签发前经授权渠道核对。 -->
        <div v-if="evidenceWithheld" class="evidence-withheld">
          依据清单〔按密级隐藏〕——原文未拉取，签发前请经授权渠道核对
        </div>
        <EvidenceTrace
          v-if="!evidenceFindings.length"
          :findings="[]"
          :withheld="evidenceWithheld"
          :required-missing="evidenceRequiredMissing"
        />
        <EvidenceList
          v-if="evidenceFindings.length"
          :findings="evidenceFindings"
        />
        <ul v-if="evidenceRefusals.length" class="evidence-refusals">
          <li v-for="(r, ri) in evidenceRefusals" :key="ri">
            已如实说明超出范围：{{ r.reason }}<span v-if="r.suggestion" class="refusal-suggestion">{{ r.suggestion }}</span>
          </li>
        </ul>
      </div>

      <div class="section" v-if="canCancel || isWaitingReview">
        <h3>动作</h3>
        <el-button v-if="canCancel" type="danger" plain @click="handleCancel">取消任务</el-button>

        <el-card v-if="isWaitingReview" shadow="never" class="review-card">
          <el-form label-width="80px">
            <el-form-item label="审核人">
              <span class="review-signer">{{ signerName }}（登录身份，签发记名不可代填）</span>
            </el-form-item>
            <el-form-item label="意见">
              <el-input v-model="reviewForm.comment" type="textarea" :rows="2" placeholder="可选" />
            </el-form-item>
            <div class="review-note">
              批准即代表你作为工程师背书该产物——签发权在你，平台不代签。
            </div>
            <!-- N8 授权链一行：把「为什么此刻停在你手里」讲成一句人话——
                 全部字段真实（创建人/时刻来自任务行），无自动放行路径是
                 宪法事实（人是唯一签发者），不是营销话术。 -->
            <div class="review-chain">
              授权链：{{ task.created_by }} 于 {{ formatTime(task.created_at) }} 创建本任务；除你此刻的批准外，平台没有任何自动放行路径。
            </div>
            <el-form-item class="review-actions">
              <!-- 批准=人签，用信任锁的 teal（--trust-signed），绝不用绿（绿仅表真实结果）。
                   ref 供放行成功后的 teal burst 定位元素（动效系统 v1 E2，唯一 teal 许可点）。 -->
              <el-button ref="approveBtnEl" class="approve-btn review-action-btn" :loading="reviewing" @click="handleReview('approve')">批准放行</el-button>
              <!-- 措辞统一（W7）：与 StatusCenter 速览同用「驳回」——同一动作一种中文。 -->
              <el-button class="review-action-btn" type="danger" :loading="reviewing" @click="handleReview('reject')">驳回</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </div>

      <div class="section">
        <h3>事件时间轴</h3>
        <WorkLog :events="events" :task="task" />
      </div>

      <div class="section" v-if="isTerminal">
        <!-- 细削（Phase 3）：反馈折叠为渐进披露（默认收起，标题带计数）——任务详情
             已是深链检视页，留反馈是次要动作，不再 always 占屏（诚实地板不变：内容
             一件不删，展开即完整表单+历史）。 -->
        <el-collapse class="feedback-collapse">
        <el-collapse-item name="fb" :title="feedbackList.length ? `反馈（${feedbackList.length}）` : '反馈'">
        <el-alert v-if="feedbackError" type="warning" :title="feedbackError" show-icon :closable="false" />
        <el-form label-width="80px" class="feedback-form">
          <el-form-item label="评价">
            <el-radio-group v-model="feedbackForm.rating">
              <el-radio value="good">可用</el-radio>
              <el-radio value="bad">不可用</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="分类">
            <el-select v-model="feedbackForm.category" placeholder="请选择">
              <el-option v-for="c in FEEDBACK_CATEGORIES" :key="c.value" :label="c.label" :value="c.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="说明">
            <el-input v-model="feedbackForm.message" type="textarea" :rows="2" placeholder="可选" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="submittingFeedback" @click="handleSubmitFeedback">提交反馈</el-button>
          </el-form-item>
        </el-form>

        <!-- 纯数据空态=line 轻量态（W2 空态纪律，与 FeedbackPage 孪生面同律）：
             「暂无反馈」不庆祝也不引导行动，一行安静文字；文案逐字不动。 -->
        <EmptyState v-if="feedbackList.length === 0 && !feedbackError" tier="line" description="暂无反馈" />
        <ul v-else class="feedback-list">
          <li v-for="f in feedbackList" :key="f.id">
            <el-tag size="small" :type="f.rating === 'good' ? 'success' : 'danger'">
              {{ f.rating === "good" ? "可用" : "不可用" }}
            </el-tag>
            <span class="feedback-category">{{ categoryLabel(f.category) }}</span>
            <span class="feedback-message">{{ f.message }}</span>
            <span class="feedback-meta">{{ f.created_by }} · {{ formatTime(f.created_at) }}</span>
          </li>
        </ul>
        </el-collapse-item>
        </el-collapse>
      </div>
      </div><!-- /td-main -->

      <!-- 环境 rail（W3，Codex 环境仪表盘范式）：任务元数据/来源/模型消耗从主叙事
           流里抽出，成为常驻可参照的「执行环境对象」——宽宿主 sticky 随读随查，
           窄宿主自动落主列之下。全部真实字段，无则「—」/「无 X」，诚实降级不编造。 -->
      <aside class="td-rail">
        <div class="task-meta-card">
          <el-collapse class="task-meta-collapse">
            <el-collapse-item title="任务信息（ID · 版本 · 时间）">
              <el-descriptions :column="1" border class="task-descriptions">
                <el-descriptions-item label="ID">{{ task.id }}</el-descriptions-item>
                <el-descriptions-item label="Agent ID">{{ task.agent_id }}</el-descriptions-item>
                <el-descriptions-item label="Agent 版本">{{ task.agent_version }}</el-descriptions-item>
                <el-descriptions-item label="任务名称">{{ task.name || "—" }}</el-descriptions-item>
                <el-descriptions-item label="创建人">{{ task.created_by }}</el-descriptions-item>
                <el-descriptions-item label="创建时间">{{ formatTime(task.created_at) }}</el-descriptions-item>
                <el-descriptions-item label="开始时间">{{ formatTime(task.started_at) }}</el-descriptions-item>
                <el-descriptions-item label="结束时间">{{ formatTime(task.finished_at) }}</el-descriptions-item>
              </el-descriptions>
            </el-collapse-item>
          </el-collapse>
        </div>

        <div class="source-panel">
          <h3>来源</h3>
          <div class="source-block">
            <div class="source-label">输入文件</div>
            <template v-if="task.input_file_ids && task.input_file_ids.length">
              <div v-for="(fid, idx) in task.input_file_ids" :key="fid" class="source-row">
                <span>输入文件 {{ idx + 1 }}</span>
                <a :href="downloadUrl(fid)" download class="source-download">下载</a>
              </div>
            </template>
            <div v-else class="muted">无输入文件</div>
          </div>
          <div class="source-block">
            <div class="source-label">输入参数</div>
            <template v-if="inputEntries.length">
              <div v-for="[k, v] in inputEntries" :key="k" class="source-row">
                <span class="source-param-key">{{ k }}</span>
                <span class="source-param-val">{{ v }}</span>
              </div>
            </template>
            <div v-else class="muted">无参数</div>
          </div>
          <div class="source-block">
            <div class="source-label">执行方</div>
            <div>{{ task.agent_id || "—" }} · {{ task.agent_version || "—" }}</div>
          </div>
          <!-- B1：模型调用消耗诚实披露——零调用（hello 等无 LLM Agent）显示中性
               灰字；token 合计只对能折算出总数的行求和，凑不出来一律「未知」，
               绝不记 0（假绿死罪）。块内无 /download 链接，且整个 rail 在 DOM 中
               位于主列（产物）之后，不干扰 m2 e2e 的 a[href*='/download'] 顺序。 -->
          <div class="source-block model-usage">
            <div class="source-label">模型调用</div>
            <div v-if="modelCallsError" class="muted">模型调用加载失败：{{ modelCallsError }}</div>
            <div v-else-if="modelCallStats.total === 0" class="muted">无模型调用</div>
            <template v-else>
              <div class="source-row model-usage-summary">
                <span>
                  <span class="num-token">{{ modelCallStats.total }}</span> 次调用（成功 <span class="num-token">{{ modelCallStats.ok }}</span> · 失败
                  <span class="num-token" :class="modelCallStats.failed > 0 ? 'model-usage-fail-count' : ''">{{ modelCallStats.failed }}</span>）
                </span>
              </div>
              <div class="source-row">
                <span>模型：{{ modelCallStats.names.length ? modelCallStats.names.join("、") : "未知" }}</span>
              </div>
              <div class="source-row">
                <!-- token 千位压缩（F1，disclosure-grammar §三）：消耗量属「量级感受」轴，
                     12.3k 而非 12,345；精确轴（次数/行数/diff）不压缩。 -->
                <span v-if="modelCallStats.tokenKnownCount > 0">tokens 合计 <span class="num-token">{{ formatTokens(modelCallStats.tokenSum) }}</span></span>
                <span v-else class="muted">token 用量：未知</span>
              </div>
              <div v-if="modelCallStats.tokenKnownCount > 0 && modelCallStats.tokenMissingCount > 0" class="model-usage-note">
                部分调用上游未回报 token，合计为下界
              </div>
            </template>
          </div>
          <!-- N7/ADR-0029 知识引用回源：执行期 knowledge_search 命中的语料块，
               签发人一步核对原文。无检索的任务整块零渲染（不摆空态）；披露
               触发器=真 <button>（W3 同款纪律）；块内无 /download 链接，不扰
               m2 e2e 的产物链接 DOM 序锚点。 -->
          <div class="source-block knowledge-citations" v-if="knowledgeCitations.length">
            <div class="source-label">知识引用</div>
            <EvidenceTrace
              kind="knowledge"
              :citations="knowledgeTraceCitations"
              compact
            />
            <div class="citation-hint">执行期知识检索命中的语料块——签发前可回源核对原文。</div>
            <div v-for="c in knowledgeCitations" :key="c.key" class="citation-item">
              <button
                type="button"
                class="citation-toggle"
                :aria-expanded="citState(c.key).open ? 'true' : 'false'"
                @click="toggleCitation(c)"
              >
                <el-icon class="citation-chevron" aria-hidden="true">
                  <ArrowDown v-if="citState(c.key).open" />
                  <ArrowRight v-else />
                </el-icon>
                <span class="citation-id">{{ c.chunkId }}</span>
                <span class="citation-scope">{{ c.scopeId }}</span>
                <span class="citation-action">{{ citState(c.key).open ? "收起" : "查看原文" }}</span>
              </button>
              <div v-if="citState(c.key).open" class="citation-body">
                <div v-if="citState(c.key).loading" class="muted">原文加载中…</div>
                <div v-else-if="citState(c.key).error" class="citation-note citation-error">{{ citState(c.key).error }}</div>
                <template v-else-if="citState(c.key).chunk">
                  <p class="citation-text">{{ citState(c.key).chunk.text }}</p>
                  <div class="citation-meta">{{ citState(c.key).chunk.source }} · 指纹 <span class="num-token">{{ citState(c.key).chunk.fingerprint }}</span></div>
                  <!-- 漂移实证（R1 P2）：检索时指纹与回源现值不一致 → 如实警示，
                       不假装「原文即检索所见」。amber 未核语义（形状+字重承载）。 -->
                  <div v-if="citState(c.key).drifted" class="citation-note citation-drift">
                    <el-icon aria-hidden="true"><Warning /></el-icon>
                    语料在检索后已变动：检索时指纹 <span class="num-token">{{ c.searchFingerprint }}</span>，与当前不一致——请以当前原文为准重新核对。
                  </div>
                  <div v-else class="citation-note">显示的是当前语料——检索之后语料若被更新，内容可能与执行当时不同。</div>
                </template>
              </div>
            </div>
          </div>
        </div>
      </aside>
      </div><!-- /td-grid -->
    </template>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { ArrowDown, ArrowRight, Warning } from "@element-plus/icons-vue";
import { cancelTask, reviewTask, getTask } from "../api/tasks";
import { downloadUrl, fetchOutputFile } from "../api/files";
import { readChunk } from "../api/knowledge";
import { buildRetryRoute } from "../utils/retryPrefill";
import {
  orderArtifactsForReview,
  shouldCollapseArtifactForReview,
} from "../utils/artifactReview";
import { acquireChannel, pokeTask, onTransition } from "../stores/liveFeed";
import { TERMINAL_STATUSES } from "../stores/liveFeedCore";
import EmptyState from "../components/EmptyState.vue";
import SkeletonBlock from "../components/SkeletonBlock.vue";
import { submitFeedback, listTaskFeedback, FEEDBACK_CATEGORIES } from "../api/feedback";
import { statusLabel, statusTagType, formatTime, formatFileSize, formatTokens, artifactTypeLabel, TASK_WORK_STATES } from "../utils/format";
import MarkdownLite from "../components/MarkdownLite.vue";
import WorkLog from "../components/WorkLog.vue";
import CompletionSeal from "../components/CompletionSeal.vue";
import TaskJourney from "../components/TaskJourney.vue";
import VerificationCard from "../components/VerificationCard.vue";
import EvidenceList from "../components/EvidenceList.vue";
import EvidenceTrace from "../components/EvidenceTrace.vue";
import { ensureTaskEvidence, taskEvidenceWithheld } from "../stores/taskEvidence";
import { useAgentNames } from "../stores/agentNames";
import { displayName } from "../stores/session";
import { markTaskSeen } from "../utils/lastSeen";
import { burstSigned } from "../effects/burst";

const route = useRoute();
const router = useRouter();
const taskId = route.params.taskId;

// 仿真监控深链：读浮窗同款配置（未配置=null=按钮零渲染，e2e 不受扰）。
const simHubBase = (() => {
  try {
    const configured = window.localStorage.getItem("flai.simMonitorHub");
    if (!configured) return null;
    const u = new URL(configured);
    // 只认 http(s)：存储值可能被 ?simhub= 链接投毒，scheme 白名单与浮窗同判据
    // （javascript:/data: 的 origin 序列化为 "null"，深链 href 不给任何出口）
    return (u.protocol === "http:" || u.protocol === "https:") ? u.origin + "/" : null;
  } catch (e) {
    return null;
  }
})();
// 本任务若已关联仿真 run（metadata.sim_run_ref，后端 setter 写入），深链直达该 run
// 的监控视图 #/<mod>@<run_id>（hub 侧路由已支持+对账提示）；未关联则回退 hub 首页。
// module/run_id 后端已按安全字符白名单钳死，此处直接拼 hash 无注入面。
const simHubUrl = computed(() => {
  if (!simHubBase) return null;
  const r = task.value && task.value.metadata && task.value.metadata.sim_run_ref;
  if (r && r.module && r.run_id) return `${simHubBase}#/${r.module}@${r.run_id}`;
  return simHubBase;
});
// run 引用可长达 module(64)+run_id(128) 字符——只把这一段单独渲染并用 CSS
// 截断（Codex 治理审 P2），前缀「查看仿真监控」与「↗」恒可见不外溢挤走 header
// 控件；完整值进 title 悬停可读。
const simRunRef = computed(() => {
  const r = task.value && task.value.metadata && task.value.metadata.sim_run_ref;
  return r && r.module && r.run_id ? `${r.module}@${r.run_id}` : "";
});
const simRunTitle = computed(() =>
  simRunRef.value ? `查看仿真监控（${simRunRef.value}）` : "查看仿真监控",
);

// 换轨（批A Task 4）：task/events/modelCalls/loaded/error 全部来自 liveFeed 的
// task:<id> channel（onMounted 隐含 acquire——acquireChannel 调用即 join，
// onUnmounted release；:key=taskId 令组件随任务切换整体重挂，天然重 acquire，
// 无需额外 watch taskId）。旧的自建 2s 轮询/baseline 守卫/modelCallsSeq 全部
// 删除——防 stale 语义已由 channel 的 epoch guard 统一承接（liveFeedCore.
// makeEpochGuard，release 时 bump epoch，在途响应整包作废）。
const taskChannel = acquireChannel(`task:${taskId}`, { modelCalls: true }); // 详情页消费模型调用记录（detail opt-in）
const {
  task,
  events,
  modelCalls,
  modelCallsLoaded,
  modelCallsError,
  loaded,
  error: loadError,
} = taskChannel.state;

const reviewForm = reactive({ comment: "" });
const signerName = computed(() => displayName());
const reviewing = ref(false);
// 批准按钮元素（动效系统 v1 E2）：放行成功后 burstSigned(el) 的定位来源；
// el-button 组件 ref 通过 .ref 暴露原生 DOM（element-plus expose 契约）。
const approveBtnEl = ref(null);

// 盖章动效仪式只属于亲历者（批A Task 9）：本次会话内亲眼观察到「活跃→终态」
// 迁移才播；历史页面直开（首载即终态）sealAnimate 恒 false——一次性置真不
// 复位，不随后续轮询/轮转翻回。onTransition 是全站总线（所有 channel 共用），
// 用 ev.id===taskId 过滤只认本任务。
//
// 硬坑（实测抓到，勿删）：ev.from 必须显式判 != null，不能只判「不在终态
// 列表」——StatusDock 全局常驻挂载，onMounted 无条件 acquireTaskFeed()（独立
// 于本页 task:<id> channel 的另一条 'tasks' 清单链），其首次冷启动 fetch 对
// diffTransitions 而言 prevById 为空，会给列表里每个任务都产出 from:null 的
// 事件（liveFeedCore.diffTransitions 语义，供别处「新入列飞入动效」使用，
// 本身正确）。若只判「!TERMINAL_STATUSES.includes(ev.from)」，from:null 会被
// 当成「非终态」放行，导致历史直开一个已终态任务时，StatusDock 的冷启动
// 清单拉取被误当成「亲历了一次迁移」，盖章动效假阳性播放。from 必须是本会话
// 真观察到的非终态字符串，null（未知前态）不算亲历。
const sealAnimate = ref(false);
let offTransition = null;

// ── 批七 §1.6：依据段 + 接力血缘 ─────────────────────────────────────────
const agentNamesStore = useAgentNames();

// findings/refusals 从已拉取的 JSON 产物解析（§2.2 输出契约惯例）；无匹配
// 产物/解析失败/密级遮蔽拒读 → null，段落零渲染（诚实缺位不编空态）。
const evidenceData = computed(() => {
  for (const a of artifacts.value) {
    if (a.isText && /\.json$/i.test(a.filename || "") && a.text) {
      try {
        const d = JSON.parse(a.text);
        if (Array.isArray(d.findings) || Array.isArray(d.refusals)) {
          return {
            findings: Array.isArray(d.findings) ? d.findings : [],
            refusals: Array.isArray(d.refusals) ? d.refusals : [],
          };
        }
      } catch {
        /* 非依据结构的 JSON 产物：跳过 */
      }
    }
  }
  return null;
});
const evidenceFindings = computed(() => evidenceData.value?.findings || []);
const evidenceRefusals = computed(() => evidenceData.value?.refusals || []);
// 批八 withheld：与 GuidePage/Workbench 共用 taskEvidence store（listOutputFiles
// 元数据判定，零下载）；task 快照到位即水合。
const evidenceWithheld = computed(
  () => task.value !== null && taskEvidenceWithheld(task.value.id) === true
);
watch(
  task,
  (t) => {
    if (t) ensureTaskEvidence(t);
  },
  { immediate: true }
);
// 警示行判据：包声明 evidence_policy.required 且任务已到签发/完成面但零 findings。
// withheld 时不报「未提供依据」——依据可能存在只是被遮蔽，误报会教用户错怪 agent。
const evidenceRequiredMissing = computed(() => {
  const t = task.value;
  if (!t) return false;
  if (t.status !== "waiting_review" && t.status !== "completed") return false;
  if (evidenceWithheld.value === true) return false;
  const meta = agentNamesStore.meta[t.agent_id];
  if (!meta || meta.evidenceRequired !== true) return false;
  return evidenceFindings.value.length === 0;
});

// 接力血缘（depends_on 已在 GET 投影）：上游任务名逐个轻量解析（≤32，常态
// 1-2 个）；拉取失败回退 id 切片（绝不编名字）。
const relayLineage = ref([]);
watch(
  () => task.value?.depends_on,
  async (deps) => {
    const list = Array.isArray(deps) ? deps : [];
    if (list.length === 0) {
      relayLineage.value = [];
      return;
    }
    if (relayLineage.value.length === list.length) return; // 已解析（depends_on 不可变）
    const out = [];
    for (const id of list) {
      try {
        const ut = await getTask(id);
        out.push({ id, name: agentNamesStore.map[ut.agent_id] || ut.name || id.slice(0, 8) });
      } catch {
        out.push({ id, name: id.slice(0, 8) });
      }
    }
    relayLineage.value = out;
  },
  { immediate: true }
);

// 产物内联查看（P0-2）：按 task.output_file_ids 拉取文件名+内容，增量同步、集合未变不重拉。
const artifacts = ref([]);

async function syncArtifacts(ids) {
  const list = Array.isArray(ids) ? ids : [];
  const existing = new Map(artifacts.value.map((a) => [a.fileId, a]));
  const next = [];
  const toFetch = [];
  for (const id of list) {
    if (existing.has(id)) {
      next.push(existing.get(id));
    } else {
      const ph = reactive({
        fileId: id,
        filename: id.slice(0, 8),
        isText: false,
        text: null,
        ext: "",
        size: 0,
        loading: true,
        error: "",
        collapsed: false,
        collapseTouched: false,
      });
      next.push(ph);
      toFetch.push(ph);
    }
  }
  artifacts.value = orderArtifactsForReview(next);
  for (const ph of toFetch) {
    try {
      Object.assign(ph, await fetchOutputFile(ph.fileId), { loading: false, error: "" });
    } catch (err) {
      ph.loading = false;
      ph.error = err.detail || err.message || "加载失败";
    }
  }
  const ordered = orderArtifactsForReview(artifacts.value);
  for (const artifact of ordered) {
    if (artifact.collapseTouched !== true) {
      artifact.collapsed = shouldCollapseArtifactForReview(artifact, ordered);
    }
  }
  artifacts.value = ordered;
}

function toggleArtifact(artifact) {
  artifact.collapseTouched = true;
  artifact.collapsed = !artifact.collapsed;
}

// 模型调用消耗披露（B1）：modelCalls 现由 task:<id> channel 每轮询整包重拉
// 承接（liveFeed.js buildTaskChannel）；请求序号守卫与失败态展示（main 原
// modelCallsSeq/modelCallsError 语义，Task 12 修复 1/2）已下沉到 channel 层，
// 本组件只读 modelCallsError，不再自己维护。

// token_usage 是上游 chat/completions 原样透传的 usage 对象，形状不保证含
// total_tokens（后端测试用例里就只有 prompt_tokens+completion_tokens）——能
// 折算出总数才计入合计，折算不出来一律算「未知」，绝不当 0。
function modelCallTokenTotal(call) {
  const usage = call.token_usage;
  if (!usage || typeof usage !== "object") return null;
  if (typeof usage.total_tokens === "number") return usage.total_tokens;
  const { prompt_tokens: p, completion_tokens: c } = usage;
  if (typeof p === "number" && typeof c === "number") return p + c;
  return null;
}

const modelCallStats = computed(() => {
  const calls = modelCalls.value;
  const names = new Set();
  let ok = 0;
  let failed = 0;
  let tokenSum = 0;
  let tokenKnownCount = 0;
  for (const c of calls) {
    if (c.status === "success") ok++;
    else if (c.status === "failed") failed++;
    if (c.model_name) names.add(c.model_name);
    const t = modelCallTokenTotal(c);
    if (t != null) {
      tokenSum += t;
      tokenKnownCount++;
    }
  }
  return {
    total: calls.length,
    ok,
    failed,
    names: Array.from(names),
    tokenSum,
    tokenKnownCount,
    tokenMissingCount: calls.length - tokenKnownCount,
  };
});

// 尺寸格式化走 utils/format 的 formatFileSize SSOT（含 GB 档）——本地副本已删。
const formatSize = formatFileSize;

// ── 产物尾部折叠（F5）：>3 件默认渲染前 3；单向展开（本地视图态，轮询整包
// 更新不影响——syncArtifacts 只动 artifacts 数组，展开位独立）。 ──
const ARTIFACT_PREVIEW_COUNT = 3;
const artifactsExpanded = ref(false);
const visibleArtifacts = computed(() =>
  artifactsExpanded.value ? artifacts.value : artifacts.value.slice(0, ARTIFACT_PREVIEW_COUNT),
);
const hiddenArtifactCount = computed(() => artifacts.value.length - visibleArtifacts.value.length);
// 默认收纳计数（批次 D P1）：含自动收纳与手动收起，纯真实视图态投影。
const collapsedArtifactCount = computed(() =>
  artifacts.value.filter((a) => a.collapsed).length,
);

// 产物类型标签（F6）走 utils/format 的 artifactTypeLabel SSOT——StatusCenter
// 速览同款徽章共用一份词表（3-lens 抓过孪生点漂移），本地副本已删。

// 文本产物行数派生（纯前端展示，不影响下载/内容本身）：非文本或空文本一律
// null，不渲染「· N 行」，绝不显示假的 0 行。
function artifactLineCount(a) {
  return a.isText && a.text ? a.text.split("\n").length : null;
}

const feedbackForm = reactive({ rating: "good", category: "", message: "" });
const submittingFeedback = ref(false);
const feedbackList = ref([]);
const feedbackError = ref("");

const CATEGORY_LABEL_MAP = Object.fromEntries(FEEDBACK_CATEGORIES.map((c) => [c.value, c.label]));
const categoryLabel = (c) => CATEGORY_LABEL_MAP[c] ?? c;

// 批量任务摘要：从已拉取 events 找最后一条 agent_log 且
// workflow_event_type=='summary_generated'（性能盘类批量 Agent 发出）；
// 无该事件的任务（如 hello_agent）返回 null，不显示，零影响。
const batchSummary = computed(() => {
  for (let i = events.value.length - 1; i >= 0; i--) {
    const e = events.value[i];
    if (
      e.event_type === "agent_log" &&
      e.payload?.workflow_event_type === "summary_generated" &&
      e.payload.ok_count != null &&
      e.payload.failed_count != null
    ) {
      return { ok: e.payload.ok_count, failed: e.payload.failed_count };
    }
  }
  return null;
});

const canCancel = computed(() => ["created", "queued"].includes(task.value?.status));
const isWaitingReview = computed(() => task.value?.status === "waiting_review");
const isTerminal = computed(() => ["completed", "failed", "cancelled"].includes(task.value?.status));
// 页头到席点：与 WorkLog 内部同一口径（TASK_WORK_STATES），紧邻状态 tag 左侧。
const isTaskWorking = computed(() => TASK_WORK_STATES.has(task.value?.status));
// N9 敏感整窗框：执行期落库的不可变分级（ADR-0025），sensitive 才亮框——
// internal/null 零渲染，绝不把「未分级」冒充「已判非敏感」。
const isSensitive = computed(() => task.value?.data_classification === "sensitive");
// 失败任务回到原对话补充信息；cancelled=人为中止，不提供重试动作。
function retryAsNew() {
  if (task.value) router.push(buildRetryRoute(task.value));
}

// 来源面板「输入参数」：task.inputs 的 key→值摘要（值 JSON.stringify 截 80 字符），
// 纯展示派生，不改任何签发/预填逻辑。
function summarizeInputValue(v) {
  let s;
  try {
    s = JSON.stringify(v);
  } catch {
    s = String(v);
  }
  if (s == null) return "—";
  return s.length > 80 ? `${s.slice(0, 80)}…` : s;
}
const inputEntries = computed(() => {
  const inputs = task.value?.inputs;
  if (!inputs || typeof inputs !== "object") return [];
  return Object.entries(inputs).map(([k, v]) => [k, summarizeInputValue(v)]);
});

// N7/ADR-0029 知识引用：knowledge_search info 事件 → 去重引用行。优先用
// payload.hit_citations（四钥：chunk_id/source/fingerprint，Codex 治理审 R1 P2
// 起内核逐命中携出处）——带 source 可对同 stem 碰撞一键消歧、带检索时 fingerprint
// 可与回源现值比对漂移。旧事件只有 hit_chunk_ids 时降级为两钥（回源碰撞项停 409，
// 诚实降级不假绿）。键含 source 使碰撞的两源各成一行、各自可回源。
const knowledgeCitations = computed(() => {
  const seen = new Set();
  const rows = [];
  for (const e of events.value || []) {
    if (e.event_type !== "knowledge_search") continue;
    const p = e.payload || {};
    if (!p.scope_id) continue;
    if (Array.isArray(p.hit_citations) && p.hit_citations.length) {
      for (const cit of p.hit_citations) {
        if (!cit || !cit.chunk_id) continue;
        // 键含 fingerprint（Codex 治理审 R2 P2）：同 scope/chunk/source 但不同
        // 指纹＝任务内语料版本已变，各成一行，漂移提示不因去重被吞成假阴性。
        const key = `${p.scope_id}::${cit.chunk_id}::${cit.source || ""}::${cit.fingerprint || ""}`;
        if (seen.has(key)) continue;
        seen.add(key);
        rows.push({
          key, scopeId: p.scope_id, chunkId: cit.chunk_id,
          source: cit.source || null, searchFingerprint: cit.fingerprint || null,
        });
      }
    } else if (Array.isArray(p.hit_chunk_ids)) {
      for (const chunkId of p.hit_chunk_ids) {
        const key = `${p.scope_id}::${chunkId}::`;
        if (seen.has(key)) continue;
        seen.add(key);
        rows.push({ key, scopeId: p.scope_id, chunkId, source: null, searchFingerprint: null });
      }
    }
  }
  return rows;
});

// 引用行视图态与 computed 行列表分离持有：events 轮询重算不清空已拉取的原文。
const citationStates = reactive({});
const EMPTY_CITATION = Object.freeze({ open: false, loading: false, error: "", chunk: null, drifted: false });
function citState(key) {
  return citationStates[key] || EMPTY_CITATION;
}
const knowledgeTraceCitations = computed(() =>
  knowledgeCitations.value.map((citation) => {
    const state = citState(citation.key);
    return {
      searchFingerprint: citation.searchFingerprint,
      currentFingerprint: state.chunk?.fingerprint ?? null,
    };
  })
);

// 错误文案按后果说话：403/404/409 的后端 detail 本就是给人看的中文如实口径
//（受限拒绝/当前语料无此块/同名歧义），直接透出不二次翻译；403 追加一句
// 防止被误读成「引用是编的」——拒的是原文外发，不是引用真实性。
function citationErrorText(err) {
  const detail = err?.detail || err?.message || "原文加载失败";
  if (err?.status === 403) {
    return `${detail}——引用本身真实存在，只是原文按密级不放行。`;
  }
  return detail;
}

async function toggleCitation(c) {
  let st = citationStates[c.key];
  if (!st) {
    st = citationStates[c.key] = reactive({ open: false, loading: false, error: "", chunk: null, drifted: false });
  }
  st.open = !st.open;
  if (st.open !== true) return; // 收起
  if (st.chunk || st.loading) return; // 已有内容/在途不重拉；上次失败(chunk仍null)重开即重试
  st.loading = true;
  st.error = "";
  try {
    // 带 source 消歧（有则传，同 stem 碰撞不再永远停 409）；回源后与检索时
    // fingerprint 比对，漂移则如实标注（回源读的是当前语料）。
    st.chunk = await readChunk({ scopeId: c.scopeId, chunkId: c.chunkId, source: c.source });
    st.drifted =
      c.searchFingerprint != null &&
      st.chunk?.fingerprint != null &&
      st.chunk.fingerprint !== c.searchFingerprint;
  } catch (err) {
    st.error = citationErrorText(err);
  } finally {
    st.loading = false;
  }
}

// artifacts fingerprint 增量逻辑保留在组件内：syncArtifacts 自身按 fileId
// 做 Map 合并去重（已有的不重拉），output_file_ids 每次轮询都是全新数组
// 引用（后端 JSON 每次现拼），watch 因而每轮询都会触发一次，但对已知产物
// 零重复请求，语义与原 loadTask 内联调用完全等价。immediate（Task 12 修复
// 6，warm-join）：channel join 时若已有 loaded 缓存（同 key 复用），首帧
// output_file_ids 已非空却错过这次 watch——immediate 补首帧，syncArtifacts
// 自带 fileId 去重，不产生重复请求。
watch(() => task.value?.output_file_ids, (ids) => {
  syncArtifacts(ids || []);
}, { immediate: true });

// 详情页开着=正在看：task 每次更新（含跨会话人工放行到账）都重新标记已看
// 过，轮询期间状态翻终态不得回头亮未读；到终态时补拉一次反馈列表——channel
// 到终态即停轮（liveFeedCore.nextInterval 返回 null），故本 watch 只会在
// 「刚好翻终态」的那一次触发 loadFeedback，效果与原 loadTask 内联调用一致，
// 不会在终态后空转重复拉。immediate（Task 12 修复 6，warm-join）：channel
// 复用时首帧 task 可能已是终态却错过这次 watch——immediate 补首帧标记已看
// /补拉反馈；markTaskSeen/loadFeedback 均幂等，不产生副作用重复。
// 请求序号（Task 12 修复 5）：终态 watch 补拉与「提交反馈后重载」都会调用本
// 函数，慢的首拉响应若晚于后一次调用落地，会用旧列表覆盖掉刚提交的反馈——
// 只让「最新一次发起」的结果落盘，迟到的旧响应整包作废。声明必须先于下方
// immediate watch（Codex R2-P2 verbatim）：warm-join 终态首帧会同步触发
// loadFeedback，`let` 在 TDZ 内即 ReferenceError。
let feedbackSeq = 0;

watch(task, (t) => {
  if (!t) return;
  markTaskSeen(taskId);
  if (isTerminal.value) loadFeedback();
}, { immediate: true });
async function loadFeedback() {
  const seq = ++feedbackSeq;
  try {
    const list = await listTaskFeedback(taskId);
    if (seq !== feedbackSeq) return;
    feedbackList.value = list;
    feedbackError.value = "";
  } catch (err) {
    if (seq !== feedbackSeq) return;
    feedbackError.value = `反馈列表加载失败：${err.detail || err.message}`;
  }
}

async function handleCancel() {
  try {
    await ElMessageBox.confirm("确认取消该任务？", "取消任务", { type: "warning" });
  } catch {
    return;
  }
  try {
    await cancelTask(taskId);
    ElMessage.info("任务已取消");
    await pokeTask(taskId); // 带外补拉：不等下一 tick，动作结果立即回显
  } catch (err) {
    ElMessage.error(err.detail || err.message);
  }
}

async function handleReview(action) {
  const label = action === "approve" ? "批准放行" : "驳回";
  try {
    await ElMessageBox.confirm(`确认${label}该任务？`, label, {
      type: "warning",
      // B6a：确认签发（approve）属人签槽，确认钮 teal（.sign-confirm-btn，
      // 全局定义见 App.vue）；驳回不占人签槽，维持既有形态。
      ...(action === "approve" ? { confirmButtonClass: "sign-confirm-btn" } : {}),
    });
  } catch {
    return;
  }
  reviewing.value = true;
  try {
    await reviewTask(taskId, { action, comment: reviewForm.comment || null });
    markTaskSeen(taskId); // 亲手签发=已看过：其后完成不得对签发者亮未读
    // 人签放行成功时刻（唯一 teal 许可点，动效系统硬约束）：仅 approve 分支触发；
    // 驳回/失败绝不放庆祝动效。元素取不到（ref 未挂载等）burstSigned 自兜 null。
    if (action === "approve") {
      burstSigned(approveBtnEl.value?.ref);
    }
    if (action === "approve") {
      ElMessage({
        message: `已${label}`,
        type: "info",
        customClass: "flai-message-signed",
      });
    } else {
      ElMessage.error(`已${label}`);
    }
    await pokeTask(taskId); // 带外补拉：不等下一 tick，动作结果立即回显
  } catch (err) {
    ElMessage.error(err.detail || err.message);
  } finally {
    reviewing.value = false;
  }
}

async function handleSubmitFeedback() {
  if (!feedbackForm.category) {
    ElMessage.error("请选择分类");
    return;
  }
  submittingFeedback.value = true;
  try {
    await submitFeedback({
      taskId,
      rating: feedbackForm.rating,
      category: feedbackForm.category,
      message: feedbackForm.message || null,
    });
    ElMessage.info("反馈已提交");
    feedbackForm.message = "";
    await loadFeedback();
  } catch (err) {
    ElMessage.error(err.detail || err.message);
  } finally {
    submittingFeedback.value = false;
  }
}

onMounted(() => {
  markTaskSeen(taskId); // 打开详情即视为「已看过」，驱动任务台未读点——数据到达前先标
  offTransition = onTransition((ev) => {
    if (
      ev.id === taskId &&
      TERMINAL_STATUSES.includes(ev.to) &&
      ev.from != null &&
      !TERMINAL_STATUSES.includes(ev.from)
    ) {
      sealAnimate.value = true; // 一次性，不复位
    }
  });
});
onUnmounted(() => {
  taskChannel.release(); // refCount 归零则停链（其它订阅者仍持有时继续养着，都正确）
  if (offTransition) offTransition();
});
</script>

<style scoped>
/* W3 容器查询：rail 布局由组件自身宽度决定——全页深链宿主（~1100px）双栏，
 * 任务台中栏窄宿主（~850px）自动单列，不靠视口媒查猜宿主。 */
.task-detail {
  container-type: inline-size;
}
.td-skel {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
/* 主叙事 | 环境 rail：默认单列（窄宿主/移动端）。断点按真实宿主几何定——
   /tasks/:id 走任务台三栏，1440 视口下中栏≈820px（app-main 1112 − 列表栏 264 −
   gap 24），故 ≥780 即双栏（260px rail，主列 ≥536——比旧 io-panel 对半分给产物
   的 ~390 更宽）；≥1120（超宽屏/全宽宿主）rail 提到 300px。 */
.td-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-6);
  align-items: start;
}
.td-main {
  min-width: 0;
}
.td-rail {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
@container (min-width: 780px) {
  .td-grid {
    grid-template-columns: minmax(0, 1fr) 260px;
  }
  .td-rail {
    position: sticky;
    /* 让位固定态状态坞（StatusDock fixed top16+高32：占用视口 y≈16-48）——
     * 初始位与 sticky 位都要清空该区，否则坞叠压元信息卡（Codex R0 P2）。
     * 64/48 是坞几何推导值非间距阶，故 sticky top 用字面量。 */
    top: 64px;
    margin-top: var(--space-12);
  }
}
@container (min-width: 1120px) {
  .td-grid {
    grid-template-columns: minmax(0, 1fr) 300px;
  }
}
.page-header {
  position: relative;
  display: flex;
  flex-wrap: wrap; /* 页头最多 7 元素并发（tag/pill/批量摘要/深链），既有不换行溢出 bug 修复 */
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
/* 工作态流光带（动效系统 v1 P3）：v-if 已绑真实 work-state，此处只管视觉——
   静态 clay-soft 底线常显作 reduced-motion 兜底，::after 是流动的 clay 高光扫过，
   transform-only、~2.4s linear infinite，绝不用 layout 属性。 */
.work-flow-strip {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  overflow: hidden;
  border-radius: 1px;
  background: var(--clay-soft);
  pointer-events: none;
}
.work-flow-strip::after {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  width: 40%;
  background: linear-gradient(90deg, transparent, var(--clay), transparent);
  animation: work-flow-sweep 2.4s linear infinite;
  will-change: transform;
}
@keyframes work-flow-sweep {
  from {
    transform: translateX(-150%);
  }
  to {
    transform: translateX(350%);
  }
}
@media (prefers-reduced-motion: reduce) {
  .work-flow-strip::after {
    animation: none;
    display: none;
  }
}
.page-header h2 {
  font-family: var(--serif);
  font-size: var(--fs-title);
  font-weight: 600;
  letter-spacing: 0.2px;
  margin: 0;
}
/* 状态 tag 切换过渡：与任务台 cl-lamp 动效语言统一（同一组 motion token）。 */
.page-header :deep(.el-tag) {
  transition: background-color var(--motion-med) var(--ease-out-soft);
}
.task-context {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--ink-soft);
  margin-bottom: 10px;
}
.task-context b {
  color: var(--ink);
  font-family: var(--mono, monospace);
  font-weight: 600;
}
.ctx-dot {
  color: var(--ink-faint);
}
/* 卡片化外包容器（el-collapse 本身不改，只加一层壳）：与 .artifact-card/
   .source-panel 同一套 hairline + 圆角 + paper-rail 卡片语言。 */
.task-meta-card {
  margin-bottom: 16px;
  border: 1px solid var(--hairline);
  border-radius: 10px;
  background: var(--paper-rail);
  overflow: hidden;
}
.task-meta-collapse {
  border-top: none;
}
.task-descriptions {
  margin-top: 4px;
}
.section {
  margin-top: 24px;
}
.section h3,
.source-panel h3 {
  margin: 0 0 12px;
  font-size: 15px;
  font-weight: 600;
  color: var(--ink);
}
.review-signer {
  color: var(--ink-soft);
  font-size: 13px;
}

.review-card {
  margin-top: 12px;
  max-width: 480px;
  background: var(--paper-rail);
}
/* 批准=人签，用信任锁 teal（--trust-signed）覆盖 Element Plus 按钮变量；绝不用绿。
   hover/active 深调统一走 --trust-signed-deep（App.vue color-mix 派生，暗色下自动
   变亮而非变暗），不再各自硬编码一份 teal——单一 SSOT，跨主题自动跟随。 */
.approve-btn {
  --el-button-bg-color: var(--trust-signed);
  --el-button-border-color: var(--trust-signed);
  --el-button-text-color: #fff;
  --el-button-hover-bg-color: var(--trust-signed-deep);
  --el-button-hover-border-color: var(--trust-signed-deep);
  --el-button-hover-text-color: #fff;
  --el-button-active-bg-color: var(--trust-signed-deep);
  --el-button-active-border-color: var(--trust-signed-deep);
}
.review-actions :deep(.el-form-item__content) {
  gap: 12px;
}
.review-action-btn {
  min-height: 44px;
}
.review-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}
.review-note {
  font-size: 12.5px;
  color: var(--ink-soft);
  line-height: 1.6;
  margin: 0 0 12px;
  padding-left: 80px;
}
.review-chain {
  font-size: 12px;
  color: var(--ink-faint);
  line-height: 1.6;
  margin: 0 0 12px;
  padding-left: 80px;
}
.artifact-review-hint {
  margin-left: 10px;
  font-size: 12px;
  font-weight: 600;
  color: var(--trust-pending);
}
.artifact-card {
  border: 1px solid var(--hairline);
  border-radius: 12px;
  background: var(--card-bg, var(--paper-surface));
  box-shadow: var(--shadow-card);
  margin-bottom: 12px;
  overflow: hidden;
}
.artifact-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--hairline);
  background: var(--paper-rail);
  transition: background var(--motion-fast) var(--ease-out-soft);
}
.artifact-head:hover {
  background: var(--hover-tint);
}
/* 披露触发器（真 button）：chrome 归零继承行样式，占满剩余宽度——命中区
 * 覆盖整行除下载链接外的部分；焦点环走全局 focus-visible 语法。 */
.artifact-toggle {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1 1 auto;
  min-width: 0;
  margin: 0;
  padding: 0;
  border: none;
  background: none;
  font: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;
}
.artifact-chevron {
  flex: none;
  width: 12px;
  height: 12px;
  font-size: 12px;
  color: var(--ink-faint);
}
.artifact-name {
  font-family: var(--mono, monospace);
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
}
.artifact-size {
  font-size: 12px;
  color: var(--ink-faint);
}
/* clay 预算（批次五 C3）：产物/来源/引用/仿真的次要动作链接逐行重复，常驻
   降 ink-soft+下划线（链接语义由下划线承担），hover 回 clay——本页 clay 只留
   给工作态灯/扫光与主动作。 */
.artifact-download {
  margin-left: auto;
  font-size: 12.5px;
  color: var(--ink-soft);
  text-decoration: underline;
  text-underline-offset: 2px;
}
.artifact-download:hover {
  color: var(--clay);
}
.artifact-ext-badge {
  font-size: 11px;
  color: var(--ink-faint);
  background: var(--paper-canvas-b, var(--paper-rail));
  border: 1px solid var(--hairline);
  border-radius: 5px;
  padding: 1px 6px;
  font-family: var(--mono, monospace);
}
/* 产物尾部折叠链接（F5）：Codex 折叠行同款安静灰文字（非按钮面），hover 走
   clay 工作色；button-reset 保真语义（Enter/Space 原生）。 */
.artifact-more {
  display: flex;
  align-items: center;
  gap: 4px;
  margin: 2px 0 0;
  padding: 4px 2px;
  border: none;
  background: none;
  font: inherit;
  font-size: 12.5px;
  color: var(--ink-soft);
  cursor: pointer;
}
.artifact-more:hover {
  color: var(--clay);
}
.artifact-more-icon {
  width: 13px;
  height: 13px;
  font-size: 13px;
}
/* 渐进披露说明行（批次 D P1）：安静一行灰字，零盒零底色（空态 line 态纪律）。 */
.artifact-collapsed-hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--ink-faint);
}
.source-panel {
  border: 1px solid var(--hairline);
  border-radius: 12px;
  background: var(--card-bg, var(--paper-surface));
  box-shadow: var(--shadow-card);
  padding: 16px;
}
.source-block {
  margin-bottom: 14px;
}
.source-block:last-child {
  margin-bottom: 0;
}
.source-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-soft);
  margin-bottom: 6px;
}
.source-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 13px;
  padding: 3px 0;
}
.source-download {
  margin-left: auto;
  color: var(--ink-soft);
  font-size: 12.5px;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.source-download:hover {
  color: var(--clay);
}
.source-param-key {
  font-family: var(--mono, monospace);
  font-weight: 600;
  color: var(--ink);
}
.source-param-val {
  color: var(--ink-soft);
  word-break: break-all;
}
/* B1：模型调用消耗披露——成功数中性色（信任色锁：completed/success 永远中性，
   绿仅表真实实证结果，不外推到「调用没报错」这种弱信号）；失败数>0 才标红。 */
.model-usage-summary {
  font-weight: 500;
}
.model-usage-fail-count {
  color: var(--trust-fail);
  font-weight: 600;
}
/* 证据数字等宽 token 化：调用次数/tokens 合计是可核验的事实证据，非行动召唤，
   故只换等宽字体（跨家族共性——Claude/Codex 行内证据同一处理），颜色/字号继承不变。 */
.num-token {
  font-family: var(--mono, "SF Mono", ui-monospace, monospace);
}
.model-usage-note {
  font-size: 11.5px;
  color: var(--ink-faint);
  margin-top: 2px;
}
.artifact-body {
  padding: 16px;
}
.artifact-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--mono, monospace);
  font-size: 13px;
  line-height: 1.6;
  color: var(--ink);
}
.artifact-error {
  color: var(--trust-fail);
  font-size: 13px;
}
/* N9 敏感整窗框：双线 ink 边框 = 形状承载的分级信号（零新色，信任色五槽
   不动）；声明行字重+菱形记号同一纪律。 */
.td-grid.td-sensitive {
  border: 3px double var(--ink);
  border-radius: 16px;
  padding: 16px;
}
.sensitive-decl {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ink);
  line-height: 1.6;
  border-bottom: 1px solid var(--hairline);
  padding-bottom: 8px;
}
.sensitive-decl-mark {
  flex: none;
  font-size: 10px;
}
/* 失败告警下的下一步行——回到原对话补充信息，不进入字段表单。 */
.retry-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 20px;
}
.retry-hint {
  font-size: 12.5px;
  color: var(--ink-faint);
}
.ctx-retry-link {
  color: var(--ink-soft);
  text-decoration: underline;
  text-underline-offset: 2px;
}
.ctx-retry-link:hover {
  color: var(--clay);
}
/* 批七 §1.6：接力血缘 + 依据段 */
.ctx-relay { color: var(--ink-faint); }
/* 批八 withheld：中性虚线弱化（遮蔽是策略非异常，不占 amber/红） */
.evidence-withheld {
  display: inline-block;
  margin: 0 0 10px;
  padding: 6px 12px;
  border: 1px dashed var(--hairline);
  border-radius: 8px;
  color: var(--ink-faint);
  font-size: 13px;
}
.evidence-missing {
  display: inline-block;
  margin: 0 0 10px;
  padding: 6px 12px;
  border: 1px solid color-mix(in srgb, var(--trust-pending) 45%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, var(--trust-pending) 8%, transparent);
  color: var(--trust-pending);
  font-size: 13px;
}
.evidence-refusals {
  margin: 10px 0 0;
  padding: 0 0 0 18px;
  font-size: 13px;
  color: var(--trust-pending);
}
.evidence-refusals .refusal-suggestion { color: var(--ink-soft); margin-left: 6px; }

/* N7 知识引用：rail 内静默披露行——mono 引用号 + 幽灵按钮，原文收在 hairline
   内衬里。错误态用 ink-soft 不用红：403/404/409 是口径说明不是系统故障，
   红只留给真失败（信任色锁）。 */
.citation-hint {
  font-size: 12px;
  color: var(--ink-faint);
  margin-bottom: 6px;
}
.citation-item {
  border-top: 1px solid var(--hairline);
  padding: 6px 0;
}
.citation-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 44px;
  margin: 0;
  padding: 0;
  border: none;
  background: none;
  font: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;
}
.citation-chevron {
  flex: none;
  font-size: 10px;
  color: var(--ink-faint);
}
.citation-id {
  font-family: var(--mono, monospace);
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ink);
  word-break: break-all;
}
.citation-scope {
  font-size: 12px;
  color: var(--ink-faint);
}
.citation-action {
  margin-left: auto;
  flex: none;
  font-size: 12px;
  color: var(--ink-soft);
}
.citation-action:hover {
  color: var(--clay);
}
.citation-body {
  margin: 6px 0 2px 18px;
}
.citation-text {
  margin: 0 0 6px;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--ink-soft);
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--paper-canvas-b, var(--paper-rail));
  border: 1px solid var(--hairline);
  border-radius: 8px;
  padding: 8px 10px;
  max-height: 240px;
  overflow-y: auto;
}
.citation-meta {
  font-size: 11.5px;
  color: var(--ink-faint);
  font-family: var(--mono, monospace);
  word-break: break-all;
  margin-bottom: 4px;
}
.citation-note {
  font-size: 11.5px;
  color: var(--ink-faint);
  line-height: 1.6;
}
.citation-error {
  color: var(--ink-soft);
}
/* 漂移警示：官方矢量图标+字重承载，用 amber 未核语义色。 */
.citation-drift {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  color: var(--trust-pending, var(--ink-soft));
  font-weight: 600;
}
.citation-drift > .el-icon {
  flex: none;
  margin-top: 2px;
}
.muted {
  color: var(--ink-faint);
}
.feedback-form {
  max-width: 480px;
}
.feedback-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.feedback-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid var(--hairline);
  font-size: 13px;
}
.feedback-message {
  flex: 1;
  color: var(--ink-soft);
}
.feedback-meta {
  color: var(--ink-faint);
  font-size: 12px;
  white-space: nowrap;
}
.sim-link {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-soft);
  text-decoration: underline;
  text-underline-offset: 2px;
  white-space: nowrap;
  max-width: 100%;
}
.sim-link:hover { color: var(--clay); }
/* 只截 run 引用这一段（module@run_id 可长达 192 字符）：前缀与箭头恒可见，
   窄屏/移动端不外溢挤走控件（Codex 治理审 P2）；全值在 title。 */
.sim-link-ref {
  display: inline-block;
  max-width: 22ch;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
}
</style>
