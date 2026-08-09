import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const readSource = (path) =>
  readFileSync(new URL(path, import.meta.url), "utf8");

const cardSource = readSource("../src/components/LifeDraftCard.vue");
const demoSource = readSource("../src/views/LifeDemoPage.vue");

test("LifeDraftCard 只从持久 record 投影，不再把 payload 回传给 legacy preview", () => {
  assert.match(cardSource, /previewGeneralizationDraftRecord/);
  assert.doesNotMatch(cardSource, /previewConversationAssetDraft/);
  assert.match(cardSource, /props\.record\.payload/);
  assert.match(cardSource, /props\.record\.id/);
  assert.match(cardSource, /props\.record\.content_digest/);
});

test("卡片区分 record 摘要与后续 bundle 摘要，并诚实标注等待人工复核", () => {
  assert.match(cardSource, /草稿记录 ID/);
  assert.match(cardSource, /记录内容摘要/);
  assert.match(cardSource, /Asset Draft Bundle 摘要/);
  assert.match(cardSource, /模型草稿/);
  assert.match(cardSource, /等待人工复核/);
  assert.doesNotMatch(cardSource, /草稿没有进任何地方/);
});

test("LifeDemoPage 监听 s/c 深链：c 只 GET，创建后 replace 成 canonical URL，并阻断陈旧响应", () => {
  assert.match(demoSource, /watch\(\s*\(\) => \[route\.query\.s, route\.query\.c\]/);
  assert.match(demoSource, /resolveLifeDemoRoute/);
  assert.match(demoSource, /intent\.kind === "load"[\s\S]*?getConversation/);
  assert.match(demoSource, /intent\.kind === "create"[\s\S]*?createConversation/);
  assert.match(
    demoSource,
    /router\.replace\([\s\S]*?query:\s*\{\s*s:\s*intent\.scenarioId,\s*c:\s*created\.id\s*\}/,
  );
  assert.match(demoSource, /routeEpoch/);
  assert.match(demoSource, /epoch !== routeEpoch/);
});

test("LifeDemoPage 以 persisted message.id 为 key，只把已校验 record 交给卡片", () => {
  assert.match(demoSource, /:key="m\.id"/);
  assert.match(
    demoSource,
    /<LifeDraftCard[\s\S]*?:key="m\.draftRecord\.id"/,
  );
  assert.match(demoSource, /m\.draftRecord/);
  assert.match(demoSource, /:record="m\.draftRecord"/);
  assert.match(demoSource, /normalizeLifePostResponse/);
  assert.match(demoSource, /normalizeLifeConversationSnapshot/);
  assert.match(demoSource, /assertLifePostMatchesSnapshot/);
  assert.doesNotMatch(demoSource, /res\?\.generalization_draft/);
});

test("LifeDemoPage 对已发出但响应断开的 POST 先按 baseline 冷读对账，默认锁定而不盲重发", () => {
  assert.match(demoSource, /baselineMessages/);
  assert.match(demoSource, /pendingAmbiguousRound/);
  assert.match(demoSource, /isDefinitelyUncommittedLifePostError/);
  assert.match(demoSource, /reconcileAmbiguousLifePostSnapshot/);
  assert.match(demoSource, /reconcilePendingAmbiguousRound/);
  assert.match(
    demoSource,
    /function reloadCurrent\(\)[\s\S]*?pendingAmbiguousRound/,
  );
  assert.match(demoSource, /reconciliationRequired\.value = true/);
  assert.match(demoSource, /不要盲目重发/);
});
