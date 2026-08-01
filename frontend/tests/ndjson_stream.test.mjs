import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  conversationInteractionPolicy,
  conversationStreamFailurePolicy,
  createNdjsonParser,
  reconciliationLockAfterRefresh,
  STREAM_NOT_PERSISTED_TITLE,
  STREAM_PERSISTENCE_UNKNOWN_TITLE,
} from "../src/utils/ndjsonStream.js";
import { ApiError, streamRequest } from "../src/api/client.js";
import { postMessageStream } from "../src/api/conversations.js";

const nativeFetch = globalThis.fetch;
const guidePageSource = readFileSync(
  new URL("../src/views/GuidePage.vue", import.meta.url),
  "utf8",
);

function ndjsonResponse(chunks) {
  const encoder = new TextEncoder();
  return {
    ok: true,
    body: new ReadableStream({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
        controller.close();
      },
    }),
  };
}

test("NDJSON 解析器跨网络分片还原 start/delta/done 事件", () => {
  const events = [];
  const parser = createNdjsonParser((event) => events.push(event));

  parser.push('{"type":"start"}\n{"type":"del');
  parser.push('ta","text":"你');
  parser.push('好"}\n{"type":"done","message":{"content":"你好"}}');
  parser.finish();

  assert.deepEqual(events, [
    { type: "start" },
    { type: "delta", text: "你好" },
    { type: "done", message: { content: "你好" } },
  ]);
});

test("NDJSON 解析器拒绝畸形事件与无界单行", () => {
  assert.throws(() => {
    const parser = createNdjsonParser(() => {});
    parser.push('{"type":');
    parser.finish();
  }, /流式响应不是合法 NDJSON/);

  assert.throws(() => {
    const parser = createNdjsonParser(() => {}, { maxLineChars: 8 });
    parser.push("123456789");
  }, /流式响应单行超过上限/);
});

test("会话失败策略：只有 persisted:false 才自动还稿并允许安全重试", () => {
  const explicit = conversationStreamFailurePolicy(
    { persisted: false },
    { hasPartial: true },
  );
  assert.equal(explicit.title, STREAM_NOT_PERSISTED_TITLE);
  assert.equal(explicit.restoreDraft, true);
  assert.equal(explicit.discardOptimisticUser, false);
  assert.equal(explicit.retainUnconfirmedTurn, false);
  assert.equal(explicit.canRetry, true);
  assert.equal(explicit.reconciliationRequired, false);
  assert.equal(
    conversationStreamFailurePolicy(
      { persisted: false },
      { hasPartial: false },
    ).discardOptimisticUser,
    true,
  );

  const unknown = conversationStreamFailurePolicy(
    { persisted: undefined },
    { hasPartial: false },
  );
  assert.equal(unknown.title, STREAM_PERSISTENCE_UNKNOWN_TITLE);
  assert.equal(unknown.persisted, null);
  assert.equal(unknown.restoreDraft, false);
  assert.equal(unknown.discardOptimisticUser, false);
  assert.equal(unknown.retainUnconfirmedTurn, true);
  assert.equal(unknown.canRetry, false);
  assert.equal(unknown.reconciliationRequired, true);
  assert.equal(
    conversationStreamFailurePolicy(
      { persisted: undefined },
      { hasPartial: true },
    ).retainUnconfirmedTurn,
    true,
  );
});

test("保存状态待核时会话输入面整体锁定，显式未保存不额外加锁", () => {
  assert.deepEqual(
    conversationInteractionPolicy({ reconciliationRequired: true }),
    {
      locked: true,
      reconciliationLocked: true,
      canSend: false,
      canAttach: false,
    },
  );
  assert.deepEqual(
    conversationInteractionPolicy({ reconciliationRequired: false }),
    {
      locked: false,
      reconciliationLocked: false,
      canSend: true,
      canAttach: true,
    },
  );
});

test("对账锁只有刷新会话成功后解除，失败或异常结果继续保锁", () => {
  assert.equal(
    reconciliationLockAfterRefresh({ required: true, succeeded: true }),
    false,
  );
  assert.equal(
    reconciliationLockAfterRefresh({ required: true, succeeded: false }),
    true,
  );
  assert.equal(
    reconciliationLockAfterRefresh({ required: true, succeeded: undefined }),
    true,
  );
});

test("GuidePage 暴露刷新核对按钮，并把文字与附件入口接到同一锁", () => {
  assert.match(guidePageSource, /刷新会话核对/);
  assert.match(
    guidePageSource,
    /loadConversation\(id, \{ preserveOnFailure: true \}\)/,
  );
  assert.match(guidePageSource, /reconciliationLockAfterRefresh\(/);
  assert.match(
    guidePageSource,
    /:disabled="interactionPolicy\.canAttach !== true"/,
  );
  assert.match(
    guidePageSource,
    /:disabled="interactionPolicy\.canSend !== true \|\| \(!draft\.trim\(\) && pendingFiles\.length === 0\)"/,
  );
  assert.doesNotMatch(guidePageSource, /canSelectAgent|浏览可用 Agent/);
  assert.match(guidePageSource, /if \(failure\.canRetry\)/);
});

test("会话流只转交真实 delta，并以 canonical done 为成功结果", async (t) => {
  t.after(() => { globalThis.fetch = nativeFetch; });
  let requestSeen = null;
  const deltas = [];
  globalThis.fetch = async (path, init) => {
    requestSeen = { path, init };
    return ndjsonResponse([
      '{"type":"start"}\n{"type":"delta","text":"你',
      '好"}\n{"type":"delta","text":"，同事"}\n',
      '{"type":"done","message":{"content":"你好，同事","created_at":"2026-07-31T00:00:00Z"},',
      '"conversation":{"id":"conv-1","status":"active"}}\n',
    ]);
  };

  const result = await postMessageStream("conv-1", "测试", ["file-1"], {
    onDelta: (text) => deltas.push(text),
  });

  assert.deepEqual(deltas, ["你好", "，同事"]);
  assert.equal(result.message.content, "你好，同事");
  assert.equal(result.conversation.id, "conv-1");
  assert.equal(requestSeen.path, "/api/conversations/conv-1/messages/stream");
  assert.equal(requestSeen.init.headers.Accept, "application/x-ndjson");
  assert.deepEqual(JSON.parse(requestSeen.init.body), {
    content: "测试",
    file_ids: ["file-1"],
  });
});

test("会话流在部分 delta 后收到 error 时保留未保存分型", async (t) => {
  t.after(() => { globalThis.fetch = nativeFetch; });
  const deltas = [];
  globalThis.fetch = async () =>
    ndjsonResponse([
      '{"type":"start"}\n',
      '{"type":"delta","text":"临时片段"}\n',
      '{"type":"error","status":503,"detail":"模型暂不可用","retryable":true,"persisted":false}\n',
    ]);

  await assert.rejects(
    () =>
      postMessageStream("conv-2", "测试失败", [], {
        onDelta: (text) => deltas.push(text),
      }),
    (err) =>
      err instanceof ApiError &&
      err.status === 503 &&
      err.detail === "模型暂不可用" &&
      err.retryable === true &&
      err.persisted === false,
  );
  assert.deepEqual(deltas, ["临时片段"]);
});

test("会话流提前结束与畸形 done 的持久化状态均保持未知", async (t) => {
  t.after(() => { globalThis.fetch = nativeFetch; });

  globalThis.fetch = async () =>
    ndjsonResponse([
      '{"type":"start"}\n',
      '{"type":"delta","text":"已看见但未确认"}\n',
    ]);
  await assert.rejects(
    () => postMessageStream("conv-3", "测试提前结束"),
    (err) =>
      err instanceof ApiError &&
      err.persisted === undefined &&
      err.detail.includes("保存状态未知") &&
      err.detail.includes("刷新会话核对"),
  );

  globalThis.fetch = async () =>
    ndjsonResponse([
      '{"type":"start"}\n',
      '{"type":"done","message":{"content":"缺 conversation"}}\n',
    ]);
  await assert.rejects(
    () => postMessageStream("conv-4", "测试畸形 done"),
    (err) =>
      err instanceof ApiError &&
      err.persisted === undefined &&
      err.detail.includes("保存状态未知"),
  );
});

test("fetch/read 超时不冒充 persisted:false", async (t) => {
  t.after(() => { globalThis.fetch = nativeFetch; });
  globalThis.fetch = (_path, init) =>
    new Promise((_resolve, reject) => {
      init.signal.addEventListener("abort", () => {
        const error = new Error("aborted");
        error.name = "AbortError";
        reject(error);
      });
    });

  await assert.rejects(
    () => streamRequest("/api/conversations/conv-5/messages/stream", { timeoutMs: 30 }),
    (err) =>
      err instanceof ApiError &&
      err.timeout === true &&
      err.persisted === undefined &&
      err.detail.includes("保存状态未知"),
  );
});
