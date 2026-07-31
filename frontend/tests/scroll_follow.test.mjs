import test from "node:test";
import assert from "node:assert/strict";

import {
  FOLLOW_THRESHOLD_PX,
  distanceFromBottom,
  shouldFollowScroll,
} from "../src/utils/scrollFollow.js";
import { streamRequest } from "../src/api/client.js";
import { postMessageStream } from "../src/api/conversations.js";

const nativeFetch = globalThis.fetch;

test.afterEach(() => {
  globalThis.fetch = nativeFetch;
});

test("distanceFromBottom：视口底到文档底的距离，内容不足一屏为 0", () => {
  assert.equal(
    distanceFromBottom({ scrollHeight: 2000, clientHeight: 800, scrollTop: 900 }),
    300,
  );
  assert.equal(
    distanceFromBottom({ scrollHeight: 700, clientHeight: 800, scrollTop: 0 }),
    0,
  );
  assert.equal(
    distanceFromBottom({ scrollHeight: 2000, clientHeight: 800, scrollTop: 1200 }),
    0,
  );
  assert.throws(() => distanceFromBottom({ scrollHeight: "x", clientHeight: 1, scrollTop: 0 }), TypeError);
});

test("shouldFollowScroll：阈值内跟随，超出脱离", () => {
  assert.equal(shouldFollowScroll(0), true);
  assert.equal(shouldFollowScroll(FOLLOW_THRESHOLD_PX), true);
  assert.equal(shouldFollowScroll(FOLLOW_THRESHOLD_PX + 1), false);
  assert.equal(shouldFollowScroll(200), false);
});

test("shouldFollowScroll：程序性滚动在飞期间不改判（防中途误杀跟随）", () => {
  // 平滑滚动中途经过距底 >阈值 区间：仍判跟随
  assert.equal(shouldFollowScroll(500, { programmatic: true }), true);
  assert.equal(shouldFollowScroll(0, { programmatic: true }), true);
});

test("streamRequest：外部 signal 联动内部 AbortController（流式停止钮底座）", async () => {
  // 悬挂的长流：与浏览器 fetch 同语义——init.signal abort 时以 AbortError 落地。
  globalThis.fetch = (url, init) =>
    new Promise((_, reject) => {
      init.signal.addEventListener("abort", () => {
        const err = new Error("The operation was aborted");
        err.name = "AbortError";
        reject(err);
      });
    });

  const external = new AbortController();
  const pending = streamRequest("/api/x", {
    timeoutMs: 60_000, // 超时不参与本测试：外部 abort 必须先于它落地
    signal: external.signal,
  });
  external.abort();

  // 现有语义：AbortError 统一折成「保存状态未知」超时型——调用方（GuidePage）
  // 靠自己的停止标记先于失败策略拦截，本层语义不变。
  await assert.rejects(pending, (err) => err.timeout === true && err.status === 0);
});

test("postMessageStream：signal 透传到 fetch 层（abort 后连接真断开）", async () => {
  let capturedSignal = null;
  globalThis.fetch = (url, init) => {
    capturedSignal = init.signal;
    return new Promise((_, reject) => {
      init.signal.addEventListener("abort", () => {
        const err = new Error("The operation was aborted");
        err.name = "AbortError";
        reject(err);
      });
    });
  };

  const external = new AbortController();
  const pending = postMessageStream("conv-1", "你好", [], { signal: external.signal });
  assert.equal(capturedSignal.aborted, false);

  external.abort();
  await assert.rejects(pending, (err) => err.status === 0);
  assert.equal(capturedSignal.aborted, true);
});

test("streamRequest：signal 缺省时行为与原来一致（纯 additive）", async () => {
  const encoder = new TextEncoder();
  globalThis.fetch = async () => ({
    ok: true,
    body: new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('{"type":"done","message":{"content":"好"},"conversation":{}}\n'));
        controller.close();
      },
    }),
  });

  const events = [];
  await streamRequest("/api/x", { onEvent: (e) => events.push(e) });
  assert.deepEqual(events.map((e) => e.type), ["done"]);
});
