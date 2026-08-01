import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  clearBatchCreationAttempt,
  persistBatchCreationAttempt,
  restoreBatchCreationAttempt,
  validBatchCreationAttempt,
} from "../src/utils/batchCreationJournal.js";

class MemoryStorage {
  constructor() {
    this.values = new Map();
  }

  getItem(key) {
    return this.values.has(key) ? this.values.get(key) : null;
  }

  setItem(key, value) {
    this.values.set(key, value);
  }

  removeItem(key) {
    this.values.delete(key);
  }
}

const validAttempt = () => ({
  schemaVersion: 1,
  conversationId: "conv_journal_1",
  retryOf: null,
  operationId: "guide_batch_fixed_001",
  items: [{
    agentId: "hello_agent",
    name: "自动生成的任务名",
    inputs: { name: "测试" },
    inputFileIds: [],
    retryOf: null,
    after: [],
  }],
  pinnedVersions: { hello_agent: "1.0.0" },
  pinnedPackageDigests: { hello_agent: "a".repeat(64) },
  submittedPlanSnapshot: { conversationId: "conv_journal_1", retryOf: null },
});

test("batch 开工在 POST 前可持久恢复同一 operation_id 与精确请求快照", () => {
  const storage = new MemoryStorage();
  const persisted = persistBatchCreationAttempt(validAttempt(), storage);
  assert.equal(validBatchCreationAttempt(persisted), true);
  assert.deepEqual(restoreBatchCreationAttempt("conv_journal_1", storage), {
    state: "ready",
    attempt: persisted,
  });

  assert.equal(
    clearBatchCreationAttempt("conv_journal_1", "guide_batch_wrong_001", storage),
    false,
  );
  assert.equal(restoreBatchCreationAttempt("conv_journal_1", storage).state, "ready");
  assert.equal(
    clearBatchCreationAttempt("conv_journal_1", persisted.operationId, storage),
    true,
  );
  assert.equal(restoreBatchCreationAttempt("conv_journal_1", storage).state, "empty");
});

test("同一会话已有待核请求时禁止用新 operation_id 覆盖", () => {
  const storage = new MemoryStorage();
  const first = persistBatchCreationAttempt(validAttempt(), storage);
  assert.deepEqual(persistBatchCreationAttempt(validAttempt(), storage), first);

  const second = validAttempt();
  second.operationId = "guide_batch_fixed_002";
  assert.throws(
    () => persistBatchCreationAttempt(second, storage),
    /已有待核的开工请求/,
  );
  assert.equal(
    restoreBatchCreationAttempt("conv_journal_1", storage).attempt.operationId,
    first.operationId,
  );
});

test("版本/摘要覆盖不完整或本地日志被篡改时 fail-closed 且不静默清锁", () => {
  const storage = new MemoryStorage();
  const missingDigest = validAttempt();
  missingDigest.pinnedPackageDigests = {};
  assert.throws(
    () => persistBatchCreationAttempt(missingDigest, storage),
    /缺少可恢复的版本、摘要或任务快照/,
  );

  persistBatchCreationAttempt(validAttempt(), storage);
  const [key] = storage.values.keys();
  storage.setItem(key, "{broken");
  assert.deepEqual(restoreBatchCreationAttempt("conv_journal_1", storage), {
    state: "corrupt",
    attempt: null,
  });
  assert.equal(
    clearBatchCreationAttempt("conv_journal_1", "guide_batch_fixed_001", storage),
    false,
  );
  assert.equal(storage.getItem(key), "{broken");
});

test("操作日志不可用时不伪造待核记录，但后续持久化会在 POST 前阻断", () => {
  const unavailable = {};
  assert.deepEqual(restoreBatchCreationAttempt("conv_journal_1", unavailable), {
    state: "unavailable",
    attempt: null,
  });
  assert.throws(
    () => persistBatchCreationAttempt(validAttempt(), unavailable),
    /创建操作日志不可用/,
  );
});

test("Guide durable arm、reload restore 与 retry epoch 失效都发生在网络副作用之前", () => {
  const source = readFileSync(
    new URL("../src/views/GuidePage.vue", import.meta.url),
    "utf8",
  );
  assert.match(
    source,
    /persistBatchCreationAttempt\(candidateAttempt\)[\s\S]*?batchCreationUnknownByConversation\[approvedConvId\][\s\S]*?await createTasksBatch/,
  );
  assert.match(source, /conversationId\.value = conv\.id;\s*restoreBatchCreationForConversation\(conv\.id\)/);
  assert.match(
    source,
    /if \(consumeInternalRouteBinding\(rawConversationId, rawRetryOf\)\) \{[\s\S]*?routeNavigationSeq \+= 1;[\s\S]*?retryValidationSeq \+= 1;[\s\S]*?return;/,
  );
  assert.match(
    source,
    /const retryContextMatchesSubmitted = \(\) =>[\s\S]*?requestedRetryOf\.value === submittedRetryOf/,
  );
  assert.ok(
    (source.match(/retryContextMatchesSubmitted\(\) !== true/g) || []).length >= 5,
    "上传、建会、路由镜像、流式 delta 与 canonical done 都要复核 retry 快照",
  );
});
