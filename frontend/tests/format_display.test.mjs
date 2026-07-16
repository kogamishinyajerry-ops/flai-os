// frontend/tests/format_display.test.mjs — 展示层格式化 SSOT 数字/签发口径。
import test from "node:test";
import assert from "node:assert/strict";
import { formatDuration, formatTokens, formatClockCompact, deriveSignoff, signoffText } from "../src/utils/format.js";

test("formatDuration: 合法毫秒按 disclosure-grammar 输出秒/分秒/小时分钟", () => {
  assert.equal(formatDuration(0), "0 秒");
  assert.equal(formatDuration(59999), "59 秒");
  assert.equal(formatDuration(60000), "1 分 00 秒");
  assert.equal(formatDuration(125000), "2 分 05 秒");
  assert.equal(formatDuration(599000), "9 分 59 秒");
  assert.equal(formatDuration(3660000), "1 小时 01 分");
});

test("formatDuration: 非数字/NaN/Infinity/负值诚实降级", () => {
  for (const value of [undefined, null, "125000", NaN, Infinity, -1]) {
    assert.equal(formatDuration(value), "—");
  }
});

test("formatTokens: 合法 token 数精确输出或按 k/M 压缩", () => {
  assert.equal(formatTokens(0), "0");
  assert.equal(formatTokens(999), "999");
  assert.equal(formatTokens(1000), "1k");
  assert.equal(formatTokens(12000), "12k");
  assert.equal(formatTokens(12345), "12.3k");
  assert.equal(formatTokens(999949), "999.9k");
  assert.equal(formatTokens(999950), "1M");
  assert.equal(formatTokens(999999), "1M");
  assert.equal(formatTokens(1000000), "1M");
  assert.equal(formatTokens(3400000), "3.4M");
});

test("formatTokens: 非数字/NaN/Infinity/负值诚实降级", () => {
  for (const value of [undefined, null, "1000", NaN, Infinity, -1]) {
    assert.equal(formatTokens(value), "—");
  }
});

test("deriveSignoff: 无 review 事件返回 null", () => {
  assert.equal(deriveSignoff([]), null);
  assert.equal(deriveSignoff(undefined), null);
  assert.equal(deriveSignoff([{ event_type: "task_completed", payload: { reviewer: "王工" } }]), null);
});

test("deriveSignoff: 倒序取第一条 review_* 并保留批准/驳回对称字段", () => {
  const events = [
    { event_type: "review_rejected", payload: { reviewer: "李工", comment: "退回修改" } },
    { event_type: "agent_log", payload: { reviewer: "无关" } },
    { event_type: "review_approved", payload: { reviewer: "王工", comment: "可放行" } },
  ];
  assert.deepEqual(deriveSignoff(events), { approved: true, reviewer: "王工", comment: "可放行" });

  const rejected = deriveSignoff([{ event_type: "review_rejected", payload: { reviewer: "王工" } }]);
  assert.deepEqual(rejected, { approved: false, reviewer: "王工", comment: "" });
});

test("deriveSignoff: 带后端遮蔽标记（content_withheld）才判 redacted", () => {
  assert.deepEqual(
    deriveSignoff([{ event_type: "review_approved", payload: null, content_withheld: true }]),
    { redacted: true },
  );
  assert.deepEqual(
    deriveSignoff([{ event_type: "review_rejected", payload: { comment: "已遮蔽" }, content_withheld: true }]),
    { redacted: true },
  );
});

test("deriveSignoff: 无遮蔽标记的缺 reviewer=unknown（不编造受限，Codex R0-P2）", () => {
  assert.deepEqual(deriveSignoff([{ event_type: "review_approved", payload: null }]), { unknown: true });
  assert.deepEqual(
    deriveSignoff([{ event_type: "review_rejected", payload: { comment: "缺字段" } }]),
    { unknown: true },
  );
});

test("signoffText: 批准与驳回口播文案对称", () => {
  assert.equal(signoffText({ approved: true, reviewer: "王工" }), "✓ 由 王工 批准放行");
  assert.equal(signoffText({ approved: false, reviewer: "王工" }), "✕ 由 王工 驳回");
});

test("formatClockCompact: 同日 HH:MM 补零 / 跨日 MM-DD HH:MM（批次三 G4）", () => {
  // todayKey 由调用方供给（响应式日界教训 R1-P3）——用固定 key 使断言与跑测时刻无关。
  const sameDay = new Date(2026, 6, 15, 9, 5); // 本地 2026-07-15 09:05
  const todayKey = sameDay.toDateString();
  assert.equal(formatClockCompact(sameDay.toISOString(), todayKey), "09:05");
  const otherDay = new Date(2026, 6, 3, 23, 7); // 本地 2026-07-03 23:07
  assert.equal(formatClockCompact(otherDay.toISOString(), todayKey), "07-03 23:07");
});

test("formatClockCompact: 非法/缺失诚实降级为「—」", () => {
  const todayKey = new Date().toDateString();
  for (const value of [undefined, null, ""]) {
    assert.equal(formatClockCompact(value, todayKey), "—");
  }
  assert.equal(formatClockCompact("not-a-date", todayKey), "—");
});
