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
const shellContextSource = readFileSync(
  new URL("../src/components/ShellContextPanel.vue", import.meta.url),
  "utf8",
);
const assetBuilderSource = readFileSync(
  new URL("../src/components/AssetBuilderDrawer.vue", import.meta.url),
  "utf8",
);

const REQUIRED_CASES = [
  "landing-desktop",
  "picker-desktop",
  "streaming-desktop",
  "persistence-unknown-desktop",
  "landing-mobile",
  "picker-mobile",
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
  assert.doesNotMatch(assetBuilderSource, /request\([^)]*\/register/);
  assert.doesNotMatch(assetBuilderSource, /request\([^)]*\/promote/);
});

test("Asset Builder 保留同一会话的本地草稿，并在步骤切换与生成期间守住可访问边界", () => {
  assert.match(assetBuilderSource, /#header="\{ titleId, titleClass \}"/);
  assert.match(assetBuilderSource, /:aria-describedby="drawerDescriptionId"/);
  assert.match(assetBuilderSource, /<h2 :id="titleId" :class="titleClass">/);
  assert.match(assetBuilderSource, /<el-form[^>]*:disabled="generating"/);
  assert.match(assetBuilderSource, /async function goToStep\(/);
  assert.match(assetBuilderSource, /heading\?\.focus\(\{ preventScroll: true \}\)/);
  assert.match(assetBuilderSource, /loadedConversationId\.value === props\.conversationId/);
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
      canSelectAgent: false,
    },
  );
});

test("Agent 选择器视图使用真实紧凑行所需字段", () => {
  for (const id of ["picker-desktop", "picker-mobile"]) {
    const fixture = getUiAcceptanceCase(id).guide;
    assert.equal(fixture.agentPickerOpen, true);
    assert.equal(fixture.agentShell.schema_version, "agent_shell.v1");
    assert.equal(fixture.agentShell.source.read_only, true);
    assert.ok(fixture.agentShell.agents.length >= 4);
    assert.ok(
      fixture.agentShell.agents.every(
        (agent) =>
          agent.identity.agent_id &&
          agent.identity.name &&
          agent.classification.category &&
          Array.isArray(agent.trust.limitations) &&
          agent.launch.kind === "task",
      ),
    );
  }
});

test("Agent 选择器只给待核片段 amber，不让外层引用状态吞掉中性治理语义", () => {
  assert.match(
    shellContextSource,
    /<span v-if="isPicker" class="context-agent-relation">/,
  );
  assert.doesNotMatch(
    shellContextSource,
    /<span v-if="isPicker" class="context-agent-relation" :class=/,
  );
  assert.match(
    shellContextSource,
    /:class="\{ 'context-pending-token': part\.pending \}"/,
  );
  assert.match(
    shellContextSource,
    /<span v-else class="context-agent-relation" :class="`is-\$\{agent\.referenceState\}`">/,
  );
  assert.match(
    shellContextSource,
    /\.context-agent-relation\.is-unresolved,\s*\.context-agent-relation\.is-unknown \{ color: var\(--trust-pending\); \}/,
  );
});

test("任务上下文 loading 动画服从 reduced-motion", () => {
  assert.match(
    shellContextSource,
    /@media \(prefers-reduced-motion: reduce\)[\s\S]*?\.context-loading \.is-loading \{ animation: none; \}/,
  );
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
