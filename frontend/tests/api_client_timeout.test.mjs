// 批次五 C1：request() 硬超时纪律（craft state-coverage「spinner 绝不无限跑」底座）。
// fetch 对「连接已建立但后端挂起」会无限悬挂——所有 loading ref/轮询链依赖
// promise 落地，超时必须把挂起请求转为可展示的分型错误。
import test from "node:test";
import assert from "node:assert/strict";
import { request, ApiError, DEFAULT_TIMEOUT_MS } from "../src/api/client.js";

test("request: 挂起的 fetch 在 timeoutMs 到点必落地为超时分型（timeout=true）", async () => {
  globalThis.fetch = (_path, init) =>
    new Promise((_resolve, reject) => {
      // 模拟后端挂起：永不响应，只对 abort 信号让路（真实 fetch 的行为）。
      init.signal.addEventListener("abort", () => {
        const e = new Error("The operation was aborted.");
        e.name = "AbortError";
        reject(e);
      });
    });
  const t0 = Date.now();
  await assert.rejects(
    () => request("/api/hang", { timeoutMs: 80 }),
    (err) =>
      err instanceof ApiError &&
      err.timeout === true &&
      err.status === 0 &&
      err.detail.includes("请求超时"),
  );
  assert.ok(Date.now() - t0 < 5000, "超时必须按 timeoutMs 量级落地，不是无限等");
});

test("request: 连接失败保持原分型（timeout=false，文案不混同）", async () => {
  globalThis.fetch = () => Promise.reject(new TypeError("Failed to fetch"));
  await assert.rejects(
    () => request("/api/down"),
    (err) =>
      err instanceof ApiError &&
      err.timeout === false &&
      err.status === 0 &&
      err.detail.includes("无法连接后端服务"),
  );
});

test("request: 正常响应不受超时干扰；默认超时=20s 契约常量", async () => {
  globalThis.fetch = () => Promise.resolve({ ok: true, json: async () => ({ ok: 1 }) });
  assert.deepEqual(await request("/api/fast"), { ok: 1 });
  assert.equal(DEFAULT_TIMEOUT_MS, 20_000);
});
