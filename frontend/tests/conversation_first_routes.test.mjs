import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { buildRetryRoute } from "../src/utils/retryPrefill.js";

const readSource = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

const routerSource = readSource("../src/router/index.js");
const taskConsoleSource = readSource("../src/views/TaskConsole.vue");
const workbenchSource = readSource("../src/views/WorkbenchSession.vue");
const portalSource = readSource("../src/views/AgentPortal.vue");
const taskDetailSource = readSource("../src/views/TaskDetail.vue");
const statusCenterSource = readSource("../src/components/StatusCenter.vue");
const retrySource = readSource("../src/utils/retryPrefill.js");
const guideSource = readSource("../src/views/GuidePage.vue");
const featureAssetMapSource = readSource("../src/components/FeatureAssetMapDisclosure.vue");

test("工程师深链 /tasks/new 只回主对话，不再加载 TaskCreate", () => {
  assert.match(
    routerSource,
    /path:\s*"\/tasks\/new"[\s\S]*?redirect:\s*\(\)\s*=>\s*\(\{\s*path:\s*"\/",\s*query:\s*\{\}\s*\}\)/,
  );
  assert.doesNotMatch(routerSource, /import\("\.\.\/views\/TaskCreate\.vue"\)/);
});

test("功能与资产地图只在主会话按需披露，不新增 /map 页面", () => {
  assert.doesNotMatch(routerSource, /path:\s*["']\/map["']/);
  assert.match(guideSource, /<FeatureAssetMapDisclosure\s*\/>/);
  assert.match(featureAssetMapSource, /<details\s+@toggle="handleToggle">/);
  assert.doesNotMatch(featureAssetMapSource, /<details[^>]*\sopen(?:\s|=|>)/);
  assert.match(
    featureAssetMapSource,
    /event\.currentTarget\.open\s*&&\s*phase\.value\s*===\s*"idle"/,
  );
  assert.match(
    featureAssetMapSource,
    /inject\(\s*"flaiFeatureAssetMapLoader",\s*getFeatureAssetMap,?\s*\)/,
  );
  assert.match(featureAssetMapSource, /await featureAssetMapLoader\(\)/);
  assert.match(
    featureAssetMapSource,
    /class="map-refresh"[\s\S]*?@click="loadMap"[\s\S]*?重新读取/,
  );
  assert.doesNotMatch(featureAssetMapSource, /<input|<textarea|<select/);
});

test("任务台、协作会话与能力门户不再暴露创建表单或手工 Agent 启动", () => {
  for (const source of [taskConsoleSource, workbenchSource, portalSource, retrySource]) {
    assert.doesNotMatch(source, /\/tasks\/new/);
  }
  assert.match(taskConsoleSource, /发起新对话/);
  assert.match(workbenchSource, /回到对话补充信息/);
  assert.match(workbenchSource, /系统负责自动路由与编排/);
  assert.doesNotMatch(workbenchSource, /flai_prefill|去创建此任务/);
  assert.doesNotMatch(workbenchSource, /创建页补全|分流与预填/);
  assert.match(portalSource, /只读了解能力、边界与成熟度/);
  assert.doesNotMatch(portalSource, /<SchemaForm|创建任务|开始对话|召集此团队/);
});

test("失败任务重试回到原对话交代问题，由系统重新安排", () => {
  assert.deepEqual(
    buildRetryRoute({ id: "task_1", conversation_id: "conv_1" }),
    { path: "/", query: { c: "conv_1", retry_of: "task_1" } },
  );
  assert.deepEqual(buildRetryRoute({ id: "task_2" }), {
    path: "/",
    query: { retry_of: "task_2" },
  });
  assert.deepEqual(buildRetryRoute({}), { path: "/" });
  assert.doesNotMatch(retrySource, /sessionStorage|flai_prefill/);
  assert.match(taskDetailSource, /回到对话说明问题/);
  assert.match(statusCenterSource, /回到对话说明问题/);
  assert.doesNotMatch(taskDetailSource, /复制为新任务|带原输入进创建页/);
  assert.doesNotMatch(statusCenterSource, /复制为新任务/);
});
