import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";

import {
  UI_ACCEPTANCE_CASES,
  getUiAcceptanceCase,
} from "../src/ui-lab/uiAcceptanceCases.js";
import { installUiAcceptanceBoundary } from "../src/ui-lab/acceptanceBoundary.js";
import { conversationInteractionPolicy } from "../src/utils/ndjsonStream.js";
import { normalizeAssetDraftPreview } from "../src/utils/assetDrafts.js";
import {
  normalizeSkillPackageReviewContent,
  normalizeSkillReuseRef,
  verifyAssetCandidateIntegrity,
} from "../src/utils/assetCandidates.js";
import { buildFeatureAssetMapView } from "../src/utils/featureAssetMap.js";

const appSource = readFileSync(
  new URL("../src/App.vue", import.meta.url),
  "utf8",
);
const guideSource = readFileSync(
  new URL("../src/views/GuidePage.vue", import.meta.url),
  "utf8",
);
const taskDetailSource = readFileSync(
  new URL("../src/views/TaskDetail.vue", import.meta.url),
  "utf8",
);
const statusCenterSource = readFileSync(
  new URL("../src/components/StatusCenter.vue", import.meta.url),
  "utf8",
);
const conversationPlansSource = readFileSync(
  new URL("../src/utils/conversationPlans.js", import.meta.url),
  "utf8",
);
const routerSource = readFileSync(
  new URL("../src/router/index.js", import.meta.url),
  "utf8",
);
const viteSource = readFileSync(
  new URL("../vite.config.js", import.meta.url),
  "utf8",
);
const labAppSource = readFileSync(
  new URL("../src/ui-lab/UiLabApp.vue", import.meta.url),
  "utf8",
);
const assetBuilderSource = readFileSync(
  new URL("../src/components/AssetBuilderDrawer.vue", import.meta.url),
  "utf8",
);
const assetCandidateSource = readFileSync(
  new URL("../src/components/AssetCandidateCallout.vue", import.meta.url),
  "utf8",
);
const quickSwitcherSource = readFileSync(
  new URL("../src/components/QuickSwitcher.vue", import.meta.url),
  "utf8",
);
const uiLabE2eSource = readFileSync(
  new URL("../e2e/ui_lab_acceptance.py", import.meta.url),
  "utf8",
);

const REQUIRED_CASES = [
  "landing-desktop",
  "routing-desktop",
  "streaming-desktop",
  "persistence-unknown-desktop",
  "landing-mobile",
  "routing-mobile",
  "feature-asset-map-closed-desktop",
  "feature-asset-map-ready-desktop",
  "feature-asset-map-error-desktop",
  "feature-asset-map-ready-mobile",
  "asset-candidate-desktop",
  "asset-candidate-accepted-desktop",
  "asset-package-approved-desktop",
  "asset-package-rejected-desktop",
  "skill-reuse-desktop",
  "skill-reuse-invalid-desktop",
  "asset-intake-desktop",
  "asset-review-desktop",
  "asset-review-mobile",
  "asset-blocked-mobile",
];

test("UI 验收台固定覆盖二十个关键视图，未知 ID fail-closed", () => {
  assert.deepEqual(
    UI_ACCEPTANCE_CASES.map((item) => item.id),
    REQUIRED_CASES,
  );
  assert.equal(
    new Set(UI_ACCEPTANCE_CASES.map((item) => item.id)).size,
    UI_ACCEPTANCE_CASES.length,
  );
  assert.equal(getUiAcceptanceCase(null).id, "landing-desktop");
  assert.throws(
    () => getUiAcceptanceCase("missing"),
    /未知 UI 验收场景：missing/,
  );
});

test("功能与资产地图固定覆盖默认收起、展开成功、503 整体停披露与 375px", () => {
  const closed = getUiAcceptanceCase("feature-asset-map-closed-desktop");
  const ready = getUiAcceptanceCase("feature-asset-map-ready-desktop");
  const unavailable = getUiAcceptanceCase("feature-asset-map-error-desktop");
  const mobile = getUiAcceptanceCase("feature-asset-map-ready-mobile");

  for (const acceptanceCase of [closed, ready, mobile]) {
    assert.equal(acceptanceCase.featureAssetMap.kind, "snapshot");
    const view = buildFeatureAssetMapView(
      acceptanceCase.featureAssetMap.snapshot,
    );
    assert.equal(view.available, true);
    assert.equal(view.summary.capabilityCount, 2);
    assert.equal(view.summary.assetCandidateCount, 1);
    assert.equal(view.summary.approvedSkillPackageCount, 1);
    const refreshed = buildFeatureAssetMapView(
      acceptanceCase.featureAssetMap.refresh_snapshot,
    );
    assert.equal(refreshed.available, true);
    assert.equal(refreshed.summary.assetCandidateCount, 2);
    assert.equal(refreshed.summary.acceptedCandidateCount, 1);
    assert.equal(refreshed.assets[1].state, "awaiting_human_review");
    assert.equal(refreshed.assets[1].packageState, null);
  }
  assert.equal(unavailable.featureAssetMap.kind, "error");
  assert.equal(unavailable.featureAssetMap.status, 503);
  assert.match(unavailable.featureAssetMap.detail, /来源完整性核验失败/);
  assert.equal(mobile.viewport.width, 375);
  assert.equal(mobile.viewport.height, 812);
});

test("completed 单任务镜头只带一份待审资产候选，不伪造 Workflow 或 Agent", async () => {
  const fixture = getUiAcceptanceCase("asset-candidate-desktop").guide;

  assert.equal(fixture.conversationTasks.length, 1);
  assert.deepEqual(
    {
      id: fixture.conversationTasks[0].id,
      status: fixture.conversationTasks[0].status,
      origin: fixture.conversationTasks[0].origin,
    },
    {
      id: "task-ui-asset-candidate",
      status: "completed",
      origin: "user",
    },
  );
  assert.equal(fixture.assetBuilderOpen, undefined);
  assert.equal(
    await verifyAssetCandidateIntegrity(fixture.assetCandidate, {
      expectedTaskId: fixture.conversationTasks[0].id,
    }),
    fixture.assetCandidate,
  );
  assert.equal(fixture.assetCandidate.state, "awaiting_human_review");
  assert.equal(fixture.assetCandidate.revision, 1);
  assert.equal(fixture.assetCandidate.supersedes_candidate_digest, null);
  assert.equal(fixture.assetCandidate.asset_map.workflow.state, "not_formed");
  assert.equal(fixture.assetCandidate.asset_map.agent.state, "not_formed");
  assert.equal(fixture.assetCandidate.effects.executes_work, false);
  assert.equal(fixture.assetCandidate.effects.registers_asset, false);
  assert.equal(fixture.assetCandidate.effects.promotes_asset, false);
});

test("接受成功态绑定 authenticated session 决定，仍不形成 Workflow 或 Agent", async () => {
  const pending = getUiAcceptanceCase("asset-candidate-desktop").guide;
  const fixture = getUiAcceptanceCase("asset-candidate-accepted-desktop").guide;
  const candidate = fixture.assetCandidate;

  assert.equal(fixture.conversationTasks.length, 1);
  assert.equal(fixture.conversationTasks[0].id, candidate.source.task_id);
  assert.equal(
    await verifyAssetCandidateIntegrity(candidate, {
      expectedTaskId: fixture.conversationTasks[0].id,
    }),
    candidate,
  );
  assert.equal(candidate.id, pending.assetCandidate.id);
  assert.equal(candidate.candidate_digest, pending.assetCandidate.candidate_digest);
  assert.equal(candidate.state, "accepted");
  assert.equal(candidate.revision, 1);
  assert.equal(candidate.supersedes_candidate_digest, null);
  assert.deepEqual(
    {
      action: candidate.decision.action,
      signer_source: candidate.decision.signer_source,
      signer_session_bound: candidate.decision.signer_session_bound,
    },
    {
      action: "accept",
      signer_source: "authenticated_session",
      signer_session_bound: true,
    },
  );
  assert.equal(candidate.decision.decided_by, "验收工程师");
  assert.equal(candidate.decision.decided_by_username, "user-ui-acceptance");
  assert.equal(candidate.asset_map.task_pattern.state, "approved_revision");
  assert.equal(candidate.asset_map.skill.state, "approved_revision");
  assert.equal(candidate.asset_map.workflow.state, "not_formed");
  assert.equal(candidate.asset_map.agent.state, "not_formed");
  assert.equal(candidate.skill_package.state, "pending_review");
  assert.equal(candidate.skill_package.isolation.zone, "candidate_quarantine");
  assert.equal(candidate.skill_package.isolation.registered, false);
  assert.equal(candidate.skill_package.isolation.executable, false);
  assert.equal(candidate.skill_package.reuse_eligible, false);
  assert.equal(
    candidate.skill_package.formation_evidence.required_independent_work_cases,
    2,
  );
  assert.equal(
    candidate.skill_package.formation_evidence.workflow_candidate.state,
    "not_formed",
  );
  assert.equal(
    candidate.skill_package.formation_evidence.agent_candidate.state,
    "not_formed",
  );
  assert.deepEqual(candidate.effects, pending.assetCandidate.effects);
  assert.match(assetCandidateSource, /这套方法已保留为资产候选/);
  assert.match(
    assetCandidateSource,
    /已接受为资产候选，尚未登记、发布或形成 Agent。/,
  );
});

test("隔离包 pending、approved、rejected 三态与真实四文件审阅内容均有可信 fixture", async () => {
  const pending = getUiAcceptanceCase("asset-candidate-accepted-desktop").guide;
  assert.equal(pending.assetCandidate.skill_package.state, "pending_review");
  assert.equal(
    await normalizeSkillPackageReviewContent(pending.skillPackageReviewContent, {
      expectedPackageId: pending.assetCandidate.skill_package.id,
      expectedPackageDigest: pending.assetCandidate.skill_package.package_digest,
      expectedFiles: pending.assetCandidate.skill_package.files,
    }),
    pending.skillPackageReviewContent,
  );
  assert.deepEqual(
    pending.skillPackageReviewContent.files.map((file) => file.path),
    [
      "SKILL.md",
      "references/provenance.json",
      "references/skill-revision.json",
      "references/task-pattern-revision.json",
    ],
  );

  for (const [id, state, action, eligible] of [
    ["asset-package-approved-desktop", "approved", "approve", true],
    ["asset-package-rejected-desktop", "rejected", "reject", false],
  ]) {
    const fixture = getUiAcceptanceCase(id).guide;
    const candidate = fixture.assetCandidate;
    assert.equal(
      await verifyAssetCandidateIntegrity(candidate, {
        expectedTaskId: fixture.conversationTasks[0].id,
      }),
      candidate,
    );
    assert.equal(candidate.skill_package.state, state);
    assert.equal(candidate.skill_package.review.action, action);
    assert.equal(candidate.skill_package.reuse_eligible, eligible);
    assert.equal(candidate.skill_package.isolation.registered, false);
    assert.equal(candidate.skill_package.isolation.executable, false);
    assert.equal(candidate.skill_package.formation_evidence.workflow_candidate.state, "not_formed");
    assert.equal(candidate.skill_package.formation_evidence.agent_candidate.state, "not_formed");
  }
});

test("自动复用与非法复用分别有主对话内联和 fail-closed 验收镜头", () => {
  const reused = getUiAcceptanceCase("skill-reuse-desktop").guide;
  const reusedPlan = reused.messages.find(
    (message) => message.recommendation?.decision === "orchestrate",
  ).recommendation;
  assert.equal(
    normalizeSkillReuseRef(reusedPlan.skill_reuse, {
      expectedAgentIds: reusedPlan.agents.map((agent) => agent.agent_id),
    }),
    reusedPlan.skill_reuse,
  );

  const invalid = getUiAcceptanceCase("skill-reuse-invalid-desktop").guide;
  const invalidPlan = invalid.messages.find(
    (message) => message.recommendation?.decision === "orchestrate",
  ).recommendation;
  assert.throws(
    () => normalizeSkillReuseRef(invalidPlan.skill_reuse, {
      expectedAgentIds: invalidPlan.agents.map((agent) => agent.agent_id),
    }),
    TypeError,
  );
});

test("Asset Builder 四镜头覆盖起步、待审与 needs_revision 阻断", () => {
  const intake = getUiAcceptanceCase("asset-intake-desktop").guide;
  assert.equal(intake.assetBuilderOpen, true);
  assert.equal(intake.assetBuilderStep, 1);
  assert.ok(intake.conversationId);
  assert.ok(intake.messages.some((message) => message.role === "user"));
  assert.equal(intake.assetDraftGeneralization.trigger, "");
  assert.deepEqual(intake.assetDraftGeneralization.inputs, []);
  assert.deepEqual(intake.assetDraftGeneralization.steps, []);

  for (const id of ["asset-review-desktop", "asset-review-mobile"]) {
    const fixture = getUiAcceptanceCase(id).guide;
    assert.equal(fixture.assetBuilderOpen, true);
    assert.equal(fixture.assetBuilderStep, 3);
    assert.equal(fixture.assetDraftPreview.schema_version, "asset_draft_bundle.v1");
    assert.equal(fixture.assetDraftPreview.status, "draft");
    assert.equal(fixture.assetDraftPreview.validation.state, "ready_for_human_review");
    assert.equal(fixture.assetDraftPreview.review.state, "awaiting_human_review");
    assert.equal(fixture.assetDraftPreview.review.decision_state, "not_recorded");
    assert.equal(normalizeAssetDraftPreview(fixture.assetDraftPreview), fixture.assetDraftPreview);
    assert.deepEqual(fixture.assetDraftPreview.effects, {
      writes_database: false,
      executes_work: false,
      registers_asset: false,
      promotes_asset: false,
    });
  }

  const blocked = getUiAcceptanceCase("asset-blocked-mobile").guide;
  assert.equal(blocked.assetBuilderOpen, true);
  assert.equal(blocked.assetBuilderStep, 3);
  assert.equal(blocked.assetDraftPreview.validation.state, "needs_revision");
  assert.equal(blocked.assetDraftPreview.validation.blocking_count, 2);
  assert.equal(blocked.assetDraftPreview.review.ready, false);
  assert.equal(blocked.assetDraftPreview.review.state, "not_ready");
  assert.equal(normalizeAssetDraftPreview(blocked.assetDraftPreview), blocked.assetDraftPreview);
});

test("Asset Builder 只提供待审 JSON 下载，不提供执行、注册、晋级或批准动作", () => {
  assert.match(assetBuilderSource, /下载不等于注册/);
  assert.match(assetBuilderSource, /下载待审 JSON/);
  assert.match(assetBuilderSource, /本页不提供批准按钮/);
  assert.match(assetBuilderSource, /:disabled="reviewReady !== true"/);
  assert.match(
    assetBuilderSource,
    /if \(!preview\.value \|\| reviewReady\.value !== true\) return;/,
  );
  assert.match(assetBuilderSource, /生成时由平台解析并校验/);
  assert.doesNotMatch(assetBuilderSource, /来源已解析/);
  assert.match(
    assetBuilderSource,
    /@media \(prefers-reduced-motion: reduce\)[\s\S]*?\.asset-builder-drawer \.is-loading \{ animation: none !important; \}/,
  );
  assert.match(
    assetBuilderSource,
    /@media \(prefers-reduced-motion: reduce\)[\s\S]*?\.el-drawer-fade-enter-active,[\s\S]*?\.asset-builder-drawer \{ transition: none !important; \}/,
  );
  assert.doesNotMatch(assetBuilderSource, /request\([^)]*\/register/);
  assert.doesNotMatch(assetBuilderSource, /request\([^)]*\/promote/);
});

test("Asset Builder 以单焦点问题流保留草稿，并在切题与生成期间守住可访问边界", () => {
  assert.match(assetBuilderSource, /#header="\{ titleId, titleClass \}"/);
  assert.match(assetBuilderSource, /:aria-describedby="drawerDescriptionId"/);
  assert.match(assetBuilderSource, /<h2 :id="titleId" :class="titleClass">/);
  assert.match(assetBuilderSource, /<el-form[^>]*:disabled="generating"/);
  assert.equal((assetBuilderSource.match(/<el-input/g) || []).length, 1);
  assert.match(assetBuilderSource, /:key="currentQuestion\.id"/);
  assert.match(assetBuilderSource, /问题 \{\{ focusState\.position \}\} \/ \{\{ focusState\.total \}\}/);
  assert.match(assetBuilderSource, /async function goToQuestion\(/);
  assert.match(assetBuilderSource, /target\?\.focus\(\{ preventScroll: true \}\)/);
  assert.match(assetBuilderSource, /assetDraftQuestionForIssue\(path\)/);
  assert.match(assetBuilderSource, /已整理 \{\{ focusState\.answeredCount \}\}/);
  assert.match(assetBuilderSource, /loadedConversationId\.value === props\.conversationId/);
  assert.match(
    assetBuilderSource,
    /preview\.value = await previewConversationAssetDraft\(props\.conversationId, form\);[\s\S]*?await showReview\(\);[\s\S]*?previewError\.value = error\?\.detail \|\| error\?\.message[\s\S]*?generating\.value = false;/,
  );
});

test("每个视图声明真实 viewport 与可逐项讨论的检查点", () => {
  for (const item of UI_ACCEPTANCE_CASES) {
    assert.ok(item.viewport.width > 0);
    assert.ok(item.viewport.height > 0);
    assert.ok(item.reviewPoints.length >= 2);
    assert.equal(item.app.displayName, "验收工程师");
  }

  assert.equal(getUiAcceptanceCase("landing-desktop").viewport.width, 1440);
  assert.equal(getUiAcceptanceCase("landing-mobile").viewport.width, 375);
});

test("流式视图只展示真实 streaming 状态，不用定时假打字", () => {
  const fixture = getUiAcceptanceCase("streaming-desktop").guide;
  assert.equal(fixture.sending, true);
  assert.ok(
    fixture.messages.some(
      (message) =>
        message.role === "assistant" &&
        message.streaming === true &&
        message.content.length > 0,
    ),
  );
});

test("保存状态待核视图显式保锁，不能伪装成失败或完成", () => {
  const fixture = getUiAcceptanceCase("persistence-unknown-desktop").guide;
  const assistant = fixture.messages.find(
    (message) => message.role === "assistant",
  );

  assert.equal(fixture.reconciliationRequired, true);
  assert.equal(fixture.sending, false);
  assert.equal(assistant.persistenceUnknown, true);
  assert.equal(assistant.streamError, true);
  assert.match(assistant.streamErrorTitle, /保存状态待核/);
  assert.deepEqual(
    conversationInteractionPolicy({
      sending: fixture.sending,
      restoring: fixture.restoring,
      reconciliationRequired: fixture.reconciliationRequired,
    }),
    {
      locked: true,
      reconciliationLocked: true,
      canSend: false,
      canAttach: false,
    },
  );
});

test("自动路由镜头只暴露方案与人工治理动作，不暴露手工选择", () => {
  for (const id of ["routing-desktop", "routing-mobile"]) {
    const fixture = getUiAcceptanceCase(id).guide;
    const recommendation = fixture.messages.find(
      (message) => message.recommendation?.decision === "orchestrate",
    )?.recommendation;
    assert.ok(recommendation);
    assert.ok(recommendation.agents.length >= 1);
    assert.ok(recommendation.agents.every((agent) => Array.isArray(agent.attachments)));
    assert.ok(Array.isArray(recommendation.ignored_attachments));
    assert.ok(fixture.agentSchemas);
    assert.equal("agentPickerOpen" in fixture, false);
    assert.equal("agentShell" in fixture, false);
  }
});

test("Agent 壳只接受文字与附件，自动路由并把内部编排按需披露", () => {
  assert.equal((guideSource.match(/<el-input/g) || []).length, 1);
  assert.equal((guideSource.match(/<el-upload/g) || []).length, 1);
  assert.match(guideSource, /系统会在后台安排所需能力/);
  assert.match(guideSource, /开始与放行由你确认/);
  assert.equal((guideSource.match(/开始与放行由你确认/g) || []).length, 1);
  assert.match(guideSource, /查看路由依据与边界/);
  assert.match(guideSource, /class="route-disclosure"/);
  assert.match(
    guideSource,
    /\.route-disclosure:not\(\[open\]\) > \.route-disclosure-body \{ display: none; \}/,
  );
  assert.doesNotMatch(guideSource, /class="route-summary" aria-live=/);
  assert.match(guideSource, /class="route-summary-state[^\"]*" aria-live="polite"/);
  assert.doesNotMatch(guideSource, /route-disclosure-count/);
  assert.match(guideSource, /class="section-label roster-label">成员 ·/);
  assert.doesNotMatch(guideSource, />召集的 Agent/);
  assert.doesNotMatch(guideSource, /Agent、模型与工具/);
  assert.doesNotMatch(guideSource, /浏览可用 Agent/);
  assert.doesNotMatch(guideSource, /<ShellContextPanel/);
  assert.doesNotMatch(guideSource, /guide-context-rail/);
  assert.doesNotMatch(guideSource, /INTENT_EXAMPLES|intent-card/);
  assert.doesNotMatch(guideSource, /stageAgentPrompt|getAgentShell/);
  assert.doesNotMatch(guideSource, /去创建此任务/);
  assert.doesNotMatch(guideSource, /router\.push\(\{ path: "\/tasks\/new"/);
  assert.match(guideSource, /plan\.agents\.length >= 1/);
  assert.match(
    guideSource,
    /plan\.agents\.every\(\(agent\) => \{[\s\S]*?return agentReady\(agent, assignedFiles\) === true;/,
  );
  assert.match(conversationPlansSource, /export function currentWorkSegmentFiles/);
  assert.match(guideSource, /currentWorkSegmentFiles\(/);
  assert.match(guideSource, /conversationTasksLoaded\.value === true/);
  assert.doesNotMatch(guideSource, /aria-label="沉淀本次工作"/);
  assert.match(guideSource, /v-if="acceptanceMode && assetBuilderOpen"/);
  assert.match(guideSource, /el\.querySelector\("\.el-upload"\)/);
  assert.doesNotMatch(guideSource, /📎/);
  assert.match(guideSource, /<div v-if="idx === latestPlanIdx" class="plan-foot">/);
  assert.doesNotMatch(guideSource, /<form\b|<select\b|contenteditable=/);
  assert.match(
    guideSource,
    /\.send-btn\.cta-clay:disabled\s*\{[\s\S]*?background:\s*var\(--paper-rail\)[\s\S]*?color:\s*var\(--ink-faint\)/,
    "空输入发送按钮必须回到中性 surface/ink，不继续占用 clay 工作色",
  );
});

test("起手 hero 示例提示条只填草稿不代发，三句示例逐字在场", () => {
  assert.equal((guideSource.match(/class="hero-example"/g) || []).length, 3);
  assert.match(guideSource, /用大白话讲讲什么是故障树/);
  assert.match(guideSource, /帮我起草一份项目周汇报/);
  assert.match(guideSource, /帮我看看这段代码有没有问题/);
  assert.match(guideSource, /function applyHeroExample\(text\)/);
  assert.match(
    guideSource,
    /function applyHeroExample\(text\) \{\n[\s\S]*?draft\.value = text;\n  focusComposer\(\);\n\}/,
    "hero 示例只能填草稿并聚焦输入框，发送仍由人亲手，绝不代发",
  );
});

test("P1-2 错误分层：三处错误面统一 details.error-disclosure 折叠技术细节", () => {
  for (const source of [guideSource, taskDetailSource, statusCenterSource]) {
    assert.match(source, /<details[^>]*class="error-disclosure"/);
    assert.match(source, /<summary>查看技术细节<\/summary>/);
    assert.match(source, /class="error-disclosure__body"/);
  }
  assert.match(
    taskDetailSource,
    /title="任务执行失败——失败原因已如实保留，展开查看技术细节。"/,
  );
  assert.match(
    statusCenterSource,
    /title="任务执行失败——失败原因已如实保留，展开查看技术细节。"/,
  );
});

test("P1-2 互审回归锚：pageError title 只收人话，原始 detail 逐字进 pageErrorDetail", () => {
  // 负向锚：任何分支都不得把原始后端 detail 直赋 el-alert title（本 finding 源头）。
  assert.doesNotMatch(guideSource, /pageError\.value = err\.detail/);
  assert.doesNotMatch(guideSource, /pageError\.value = detail;/);
  // 正向锚：三处修复后人话标题逐字在场。
  assert.match(guideSource, /pageError\.value = "发送失败——本轮未保存，原话已退回输入框"/);
  assert.match(guideSource, /pageError\.value = "会话加载失败"/);
  assert.match(guideSource, /pageError\.value = "会话核对失败"/);
  // 配对锚：原始 detail 只进折叠层。
  assert.match(guideSource, /pageErrorDetail\.value = detail;/);
  assert.match(guideSource, /pageErrorDetail\.value = err\.detail \|\| err\.message \|\| "";/);
});

test("词表双口径：默认面迁移新词，route-disclosure 内工程词保留", () => {
  assert.match(guideSource, /roster-label">成员 ·/);
  assert.match(guideSource, /未匹配该执行单元的输入契约/);
});

test("map#46 #56 方案卡依据行：披露外可见面、句式逐字、latestPlanIdx 不门控", () => {
  const evidenceTraceSource = readFileSync(
    new URL("../src/utils/evidenceTrace.js", import.meta.url),
    "utf8",
  );
  // ① 依据行在 route-disclosure 之外（可见面）：模板序必须先于披露 details，
  //    且不携带 latestPlanIdx 门控（历史方案卡也上浮）。
  const lineIdx = guideSource.indexOf('class="plan-evidence-line sa-evidence-chip"');
  const disclosureIdx = guideSource.indexOf(
    '<details v-if="idx === latestPlanIdx" class="route-disclosure">',
  );
  assert.ok(lineIdx > 0, "方案卡依据行模板不在场");
  assert.ok(disclosureIdx > 0, "route-disclosure 锚缺失");
  assert.ok(lineIdx < disclosureIdx, "依据行必须渲在 route-disclosure 披露区之外（可见面）");
  assert.match(
    guideSource,
    /<div\n\s+v-if="planEvidenceLine\(m, idx\)"\n\s+class="plan-evidence-line sa-evidence-chip"/,
    "依据行渲染条件只能是聚合非 null，不得叠加 latestPlanIdx 等门控",
  );
  // ② 三态句式与 per-member chip 逐字同句（文案沿用现行句式，owner 裁决）；
  //    计数+遮蔽共存时沿用 W7 措辞后缀。文案组装在 decidePlanEvidenceLine。
  assert.match(evidenceTraceSource, /依据 \$\{merged\.total\} 条（\$\{merged\.verified\} 已核验 · \$\{merged\.unverified\} 未核）/);
  assert.match(evidenceTraceSource, / · 置信度 \$\{merged\.level\}（模型自评）/);
  assert.match(evidenceTraceSource, /"依据结构待核·另有密级隐藏项" : "依据结构待核"/);
  assert.match(evidenceTraceSource, /text: "依据清单〔按密级隐藏〕"/);
  assert.match(evidenceTraceSource, /text \+= "·另有密级隐藏项"/);
  // ③ amber 口径同 per-member chip（has-unverified 既有类），零新色：
  //    聚合行只绑既有 chip 类，专属类仅做布局（归零缩进/静态光标）。
  assert.match(
    guideSource,
    /'has-unverified': planEvidenceLine\(m, idx\)\.hasUnverified/,
  );
  assert.match(
    guideSource,
    /'is-withheld': planEvidenceLine\(m, idx\)\.withheldOnly/,
  );
  assert.match(
    guideSource,
    /\.sa-evidence-chip\.plan-evidence-line \{\s*margin-left: 0;\s*cursor: default;\s*\}/,
  );
  // ④ 聚合信号源=确定性事实（任务存在性+产物依据+遮蔽标记），不新增分类器。
  assert.match(guideSource, /decidePlanEvidenceLine\(memberStates\)/);
  assert.match(guideSource, /taskEvidenceOf\(task\.id\)/);
  assert.match(guideSource, /taskEvidenceSummary\(task\.id\)/);
  // ⑤ 互审 F2（owner 裁：时间窗归属+fail-closed）：成员任务只计本卡时间窗
  //    [卡消息 createdAt, 其后首条带时间戳消息)内；归属不定整行不渲。
  assert.match(guideSource, /Date\.parse\(m\.createdAt\)/);
  assert.match(guideSource, /ms >= startMs && ms < endMs/);
  assert.match(guideSource, /state: "attributionFailed"/);
  assert.match(evidenceTraceSource, /s\?\.state === "attributionFailed"/);
  // ⑥ 互审 F3（owner 裁：降级「依据结构待核」）：有可读成员且仍有 pending/noTask
  //    成员时整行待核 amber，部分计数不冒充完整计数。
  assert.match(evidenceTraceSource, /s\?\.state === "pending" \|\| s\?\.state === "noTask"/);
  assert.match(evidenceTraceSource, /return \{ text: "依据结构待核", hasUnverified: true, withheldOnly: false \}/);
});

test("refuse 卡 kicker 用暂时接不住，重述引导直呼 FLAi", () => {
  assert.match(guideSource, /<div class="plan-kicker refuse">暂时接不住<\/div>/);
  assert.match(guideSource, /这个需求，平台暂时接不住/);
  assert.match(guideSource, /告诉 FLAi 你想怎么调整/);
});

test("全局快速切换只检索工程任务与会话，不把 Agent 暴露成工程师选项", () => {
  assert.match(quickSwitcherSource, /placeholder="搜索会话、任务…"/);
  assert.doesNotMatch(quickSwitcherSource, /listAgents/);
  assert.doesNotMatch(quickSwitcherSource, /filteredAgents/);
  assert.doesNotMatch(quickSwitcherSource, /key: "agent"/);
  assert.doesNotMatch(quickSwitcherSource, /type === "agent"/);
  assert.doesNotMatch(appSource, /搜索会话 \/ 任务 \/ Agent/);
  assert.match(
    quickSwitcherSource,
    /type === "conversation"\) router\.push\(\{ path: "\/", query: \{ c: item\.id \} \}\)/,
  );
  assert.doesNotMatch(quickSwitcherSource, /router\.push\(`\/workbench\/\$\{item\.id\}`\)/);
});

test("全局快速切换以可聚焦 listbox 暴露当前结果，并把焦点约束在弹窗内", () => {
  assert.match(quickSwitcherSource, /role="combobox"/);
  assert.match(quickSwitcherSource, /aria-controls="quick-switcher-results"/);
  assert.match(quickSwitcherSource, /:aria-activedescendant="activeOptionId"/);
  assert.match(quickSwitcherSource, /id="quick-switcher-results"/);
  assert.match(quickSwitcherSource, /role="listbox"/);
  assert.match(quickSwitcherSource, /role="option"/);
  assert.match(quickSwitcherSource, /:aria-selected="entry\.globalIndex === selectedIndex"/);
  assert.match(quickSwitcherSource, /:tabindex="entry\.globalIndex === selectedIndex \? 0 : -1"/);
  assert.match(quickSwitcherSource, /@focus="selectedIndex = entry\.globalIndex"/);
  assert.match(quickSwitcherSource, /@keydown\.enter\.stop\.prevent="activate\(group\.key, entry\.item\)"/);
  assert.match(quickSwitcherSource, /if \(e\.key === "Tab"\) \{[\s\S]*?trapFocus\(e\);/);
  assert.match(quickSwitcherSource, /function trapFocus\(e\)/);
  assert.match(quickSwitcherSource, /nextTick\(\(\) => el\.focus\(\)\)/);
});

test("六重旋转标记资产保持已验收的 256px RGBA 基线", () => {
  const bloomAsset = readFileSync(
    new URL("../src/assets/flai-bloom.png", import.meta.url),
  );
  assert.equal(
    createHash("sha256").update(bloomAsset).digest("hex"),
    "5e5618f6ca01243b75eb14e149510df2f27a6892383b0ef24cd319c0713cd963",
  );
});

test("验收 fixture 只在开发态生效，且不进入正式路由或生产构建入口", () => {
  assert.match(
    appSource,
    /const acceptanceFixture = import\.meta\.env\.DEV \? props\.acceptanceFixture : null/,
  );
  assert.match(
    guideSource,
    /const acceptanceFixture = import\.meta\.env\.DEV \? props\.acceptanceFixture : null/,
  );
  assert.doesNotMatch(routerSource, /ui-lab|acceptanceFixture/);
  assert.doesNotMatch(viteSource, /rollupOptions|input:\s*.*ui-lab/);
  assert.match(viteSource, /cors:\s*\{\s*origin:\s*"null"\s*\}/);
  assert.match(labAppSource, /sandbox="allow-scripts"/);
  assert.doesNotMatch(labAppSource, /allow-same-origin/);
});

test("验收入口统一阻止网络和存储副作用", () => {
  class FakeStorage {
    setItem() {}
    removeItem() {}
    clear() {}
  }

  const runtime = {
    fetch: async () => "unexpected",
    XMLHttpRequest: class {},
    WebSocket: class {},
    EventSource: class {},
    Storage: FakeStorage,
    navigator: { sendBeacon: () => true },
    indexedDB: {
      open() {},
      deleteDatabase() {},
    },
  };

  const boundary = installUiAcceptanceBoundary(runtime);
  assert.equal(boundary.mode, "read-only");
  assert.throws(() => runtime.fetch("/api/health"), /已阻止 fetch/);
  assert.throws(() => new runtime.XMLHttpRequest(), /已阻止 XMLHttpRequest/);
  assert.throws(() => new runtime.WebSocket("ws://example"), /已阻止 WebSocket/);
  assert.throws(() => new runtime.EventSource("/events"), /已阻止 EventSource/);
  assert.equal(runtime.navigator.sendBeacon("/audit", "x"), false);
  assert.throws(
    () => new runtime.Storage().setItem("flai_theme_mode", "dark"),
    /已阻止 Storage\.setItem/,
  );
  assert.throws(() => runtime.indexedDB.open("flai"), /已阻止 indexedDB\.open/);
  assert.equal(installUiAcceptanceBoundary(runtime), boundary);
});

test("组件级验收仅白名单返回草稿预览，其余 API 全部中止", () => {
  assert.match(
    uiLabE2eSource,
    /component_page\.route\(\s*f"\{BASE\}\/api\/\*\*",\s*asset_preview_route,/,
  );
  assert.match(
    uiLabE2eSource,
    /request\.method == "POST"[\s\S]*asset-draft-preview[\s\S]*route\.fulfill\([\s\S]*?return[\s\S]*?route\.abort\(\)/,
  );
});

test("UI Lab 真实执行包级批准与拒绝 POST，并在 deciding 锁住所有抽屉动作", () => {
  assert.match(uiLabE2eSource, /window\.__FLAI_PACKAGE_DECISION__/);
  assert.match(uiLabE2eSource, /apiModule\.decideSkillPackage/);
  assert.match(
    uiLabE2eSource,
    /skill_package_decision_request\.v1[\s\S]*action": "approve"[\s\S]*expected_package_digest/,
  );
  assert.match(
    uiLabE2eSource,
    /disabledFooter": 4[\s\S]*evidenceDisabled": True[\s\S]*contentDisabled": True[\s\S]*close": 0/,
  );
  assert.match(uiLabE2eSource, /candidate-state\.is-package-approved/);
  assert.match(uiLabE2eSource, /candidate-state\.is-package-rejected/);
});

test("任一已存在出口无法替换时，验收边界 fail-closed", () => {
  const escapedFetch = async () => "escaped";
  const runtime = {};
  Object.defineProperty(runtime, "fetch", {
    configurable: false,
    writable: false,
    value: escapedFetch,
  });

  assert.throws(
    () => installUiAcceptanceBoundary(runtime),
    /已阻止 无法封锁 fetch/,
  );
  assert.equal(runtime.fetch, escapedFetch);
  assert.equal(runtime.__FLAI_UI_ACCEPTANCE_BOUNDARY__, undefined);
});
