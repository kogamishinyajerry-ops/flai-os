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

const appSource = readFileSync(
  new URL("../src/App.vue", import.meta.url),
  "utf8",
);
const guideSource = readFileSync(
  new URL("../src/views/GuidePage.vue", import.meta.url),
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
const quickSwitcherSource = readFileSync(
  new URL("../src/components/QuickSwitcher.vue", import.meta.url),
  "utf8",
);

const REQUIRED_CASES = [
  "landing-desktop",
  "routing-desktop",
  "streaming-desktop",
  "persistence-unknown-desktop",
  "landing-mobile",
  "routing-mobile",
  "asset-intake-desktop",
  "asset-review-desktop",
  "asset-review-mobile",
  "asset-blocked-mobile",
];

test("UI 验收台固定覆盖十个关键视图，未知 ID fail-closed", () => {
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
  assert.match(guideSource, /系统会在后台自动编排所需能力/);
  assert.match(guideSource, /开工与签发仍由你确认/);
  assert.equal((guideSource.match(/开工与签发仍由你确认/g) || []).length, 1);
  assert.match(guideSource, /查看路由依据与边界/);
  assert.match(guideSource, /class="route-disclosure"/);
  assert.doesNotMatch(guideSource, /class="route-summary" aria-live=/);
  assert.match(guideSource, /class="route-summary-state[^\"]*" aria-live="polite"/);
  assert.doesNotMatch(guideSource, /route-disclosure-count/);
  assert.match(guideSource, /class="section-label roster-label">执行单元 ·/);
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
