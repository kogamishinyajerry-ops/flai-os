import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  createRoutePrefetcher,
  routeKeyForPath,
  scheduleIdleRoutePrefetch,
  shouldPrefetchRoutes,
} from "../src/router/routeLoaders.js";

const read = (relativePath) => readFileSync(
  new URL(relativePath, import.meta.url),
  "utf8",
);

const appSource = read("../src/App.vue");
const guideSource = read("../src/views/GuidePage.vue");
const todaySource = read("../src/views/TodayPage.vue");
const routerSource = read("../src/router/index.js");
const indexHtml = read("../index.html");
const bundleBudgetSource = read("../scripts/check-bundle-budget.mjs");
const uiLabE2eSource = read("../e2e/ui_lab_acceptance.py");

test("P1 方案依据、资产披露与 DeliveryCard 族走异步组件边界", () => {
  assert.match(guideSource, /import \{[^}]*defineAsyncComponent[^}]*\} from "vue"/);
  for (const componentName of [
    "EvidenceList",
    "AssetCandidateCallout",
    "FeatureAssetMapDisclosure",
    "AssetBuilderDrawer",
  ]) {
    assert.match(
      guideSource,
      new RegExp(`const ${componentName} = defineAsyncComponent\\(\\(\\) => import\\(`),
    );
    assert.doesNotMatch(
      guideSource,
      new RegExp(`import ${componentName} from`),
    );
  }

  assert.match(todaySource, /import \{[^}]*defineAsyncComponent[^}]*\} from "vue"/);
  assert.match(
    todaySource,
    /const DeliveryCard = defineAsyncComponent\(\(\) => import\("\.\.\/components\/DeliveryCard\.vue"\)\)/,
  );
  assert.doesNotMatch(todaySource, /import DeliveryCard from/);
});

test("P1 bundle 预算与动态路由下限保持原值，不用松门换绿", () => {
  assert.match(bundleBudgetSource, /const MAX_JS_CHUNK_BYTES = 500_000;/);
  assert.match(bundleBudgetSource, /const MAX_SYNC_JS_GZIP_BYTES = 220 \* 1024;/);
  assert.match(bundleBudgetSource, /const MAX_SYNC_CSS_GZIP_BYTES = 40 \* 1024;/);
  assert.match(bundleBudgetSource, /const MAX_ROUTE_JS_GZIP_BYTES = 220 \* 1024;/);
  assert.match(bundleBudgetSource, /const MAX_ROUTE_CSS_GZIP_BYTES = 40 \* 1024;/);
  assert.match(bundleBudgetSource, /const MIN_DYNAMIC_ENTRIES = 7;/);
  assert.match(
    bundleBudgetSource,
    /const uniqueDynamicRouteEntries = uniqueDynamicEntries\.filter/,
  );
  assert.match(bundleBudgetSource, /\(record\.src \|\| key\)\.startsWith\("src\/views\/"\)/);
  assert.match(bundleBudgetSource, /asyncComponentEntryCount/);
});

test("P1 UI Lab 冷启动会重取异步组件 frame，不把 Vite 优化重载验成失败", () => {
  assert.match(
    uiLabE2eSource,
    /def embedded_frame\(page, case_id: str, ready_selector: str = "\.guide-page"\)/,
  );
  assert.match(
    uiLabE2eSource,
    /stable_ticks_required = 8 if ready_selector != "\.guide-page" else 1/,
  );
  assert.match(uiLabE2eSource, /except PlaywrightError:/);
  assert.match(uiLabE2eSource, /ready_selector = "\.asset-builder-drawer"/);
});

test("P5 生产路由与 hover/idle prefetch 复用同一组动态 import loader", () => {
  assert.match(routerSource, /import \{ routeLoaders \} from "\.\/routeLoaders\.js"/);
  for (const loaderName of [
    "guide",
    "today",
    "me",
    "portal",
    "workbenchSession",
    "taskConsole",
    "feedback",
    "lifeDemo",
  ]) {
    assert.match(routerSource, new RegExp(`component: routeLoaders\\.${loaderName}`));
  }
  assert.doesNotMatch(routerSource, /component:\s*\(\) => import\(/);

  assert.match(appSource, /@mouseenter="warmVisibleRoute\(item\.path\)"/);
  assert.match(appSource, /@focus="warmVisibleRoute\(item\.path\)"/);
  assert.match(appSource, /@mouseenter="warmVisibleRoute\('\/me'\)"/);
  assert.match(appSource, /scheduleIdleRoutePrefetch\(\["\/today"\]/);
});

test("P5 route key 只映射现有页面；重定向保持现有目的地", () => {
  assert.equal(routeKeyForPath("/"), "guide");
  assert.equal(routeKeyForPath("/today?from=nav"), "today");
  assert.equal(routeKeyForPath("/me#summary"), "me");
  assert.equal(routeKeyForPath("/tasks/task_1"), "taskConsole");
  assert.equal(routeKeyForPath("/tasks/new"), "guide");
  assert.equal(routeKeyForPath("/workbench"), "taskConsole");
  assert.equal(routeKeyForPath("/workbench/session_1"), "workbenchSession");
  assert.equal(routeKeyForPath("/unknown"), null);
  assert.equal(routeKeyForPath(null), null);
});

test("P5 prefetch 并发/完成态去重，失败后允许真实导航重试", async () => {
  let calls = 0;
  let release;
  const pending = new Promise((resolve) => { release = resolve; });
  const prefetch = createRoutePrefetcher({
    today: async () => {
      calls += 1;
      await pending;
    },
  });

  const first = prefetch("/today");
  const second = prefetch("/today?again=1");
  await Promise.resolve();
  assert.equal(calls, 1);
  release();
  assert.deepEqual(await Promise.all([first, second]), [true, true]);
  assert.equal(await prefetch("/today"), true);
  assert.equal(calls, 1);
  assert.equal(await prefetch("/missing"), false);

  let attempts = 0;
  const retryable = createRoutePrefetcher({
    me: async () => {
      attempts += 1;
      if (attempts === 1) throw new Error("transient chunk failure");
    },
  });
  await assert.rejects(retryable("/me"), /transient chunk failure/);
  assert.equal(await retryable("/me"), true);
  assert.equal(attempts, 2);
});

test("P5 UI Lab/DEV fixture 禁止预取，普通开发产品面仍可预取", () => {
  assert.equal(shouldPrefetchRoutes({ acceptanceMode: true, isDev: true, pathname: "/" }), false);
  assert.equal(shouldPrefetchRoutes({ acceptanceMode: false, isDev: true, pathname: "/ui-lab.html" }), false);
  assert.equal(shouldPrefetchRoutes({ acceptanceMode: false, isDev: true, pathname: "/today" }), true);
  assert.equal(shouldPrefetchRoutes({ acceptanceMode: false, isDev: false, pathname: "/" }), true);

  let scheduled = false;
  const cancel = scheduleIdleRoutePrefetch(["/today"], {
    enabled: false,
    requestIdleCallback: () => { scheduled = true; return 1; },
  });
  cancel();
  assert.equal(scheduled, false);
});

test("P5 idle 调度可取消，且 speculative import 失败不形成未处理拒绝", async () => {
  let idleCallback;
  let cancelledId = null;
  let attempts = 0;
  const cancel = scheduleIdleRoutePrefetch(["/today", "/me", "/today"], {
    prefetch: async () => {
      attempts += 1;
      throw new Error("prefetch is best effort");
    },
    requestIdleCallback: (callback) => {
      idleCallback = callback;
      return 42;
    },
    cancelIdleCallback: (id) => { cancelledId = id; },
  });

  await idleCallback();
  assert.equal(attempts, 2, "同一 idle 批次应先去重路径");
  cancel();
  assert.equal(cancelledId, 42);
});

test("P4 静态首屏为零依赖品牌骨架，Vue 挂载后仍复用同一 #app", () => {
  assert.match(indexHtml, /<title>FLAi-OS 二所工程智能体运行底座<\/title>/);
  assert.match(indexHtml, /<div id="app">[\s\S]*class="flai-boot"[\s\S]*<\/div>\s*<script type="module"/);
  assert.match(indexHtml, /aria-label="FLAi-OS 正在启动"/);
  assert.match(indexHtml, /class="flai-boot__mark"[\s\S]*<svg/);
  assert.match(indexHtml, /class="flai-boot__name">FLAi-OS<\/strong>/);
  assert.match(indexHtml, /class="flai-boot__subtitle">二所工程智能体运行底座<\/span>/);

  const skeletonStart = indexHtml.indexOf('<div class="flai-boot"');
  const moduleStart = indexHtml.indexOf('<script type="module"');
  const skeleton = indexHtml.slice(skeletonStart, moduleStart);
  assert.ok(skeletonStart >= 0 && moduleStart > skeletonStart);
  assert.doesNotMatch(skeleton, /<img\b|https?:\/\//);
  assert.doesNotMatch(indexHtml, /@keyframes|animation:/);
});
