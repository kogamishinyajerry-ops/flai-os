import test from "node:test";
import assert from "node:assert/strict";
import { workSegments, currentWorkSegmentFiles } from "../src/utils/conversationPlans.js";

// 切片 3（#31 方案 B）：UI 工作段分隔描述符纯函数核。
// 与附件路由（currentWorkSegmentFiles）同源三终点——同一消息流上两出口口径一致。

const u = (content, createdAt) => ({ role: "user", content, createdAt });
const a = (recommendation, createdAt) => ({ role: "assistant", content: "好。", recommendation, createdAt });
const refuse = (createdAt) => a({ decision: "refuse", reason: "超范围" }, createdAt);
const qa = (createdAt) => a({ answer: "制度原文…", findings: [{ id: "f1" }] }, createdAt);
const plan = (createdAt) => a({ decision: "orchestrate", agents: [] }, createdAt);

test("空消息流无段", () => {
  assert.deepEqual(workSegments([], []), []);
});

test("无终点单段覆盖", () => {
  const msgs = [u("一", "2026-08-04T10:00:00Z"), a(null, "2026-08-04T10:00:10Z"), u("二", "2026-08-04T10:01:00Z")];
  const segs = workSegments(msgs, []);
  assert.equal(segs.length, 1);
  assert.deepEqual([segs[0].start, segs[0].end, segs[0].ordinal], [0, 2, 0]);
});

test("refuse 终点切段（下一条开新段）", () => {
  const msgs = [u("一", "2026-08-04T10:00:00Z"), refuse("2026-08-04T10:00:10Z"), u("二", "2026-08-04T10:01:00Z")];
  const segs = workSegments(msgs, []);
  assert.equal(segs.length, 2);
  assert.deepEqual([segs[0].start, segs[0].end], [0, 1]);
  assert.deepEqual([segs[1].start, segs[1].end, segs[1].ordinal], [2, 2, 1]);
});

test("canonical QA 交付切段；orchestrate 不切", () => {
  const msgs = [u("一", "2026-08-04T10:00:00Z"), qa("2026-08-04T10:00:10Z"), u("二", "2026-08-04T10:01:00Z"), plan("2026-08-04T10:02:00Z"), u("三", "2026-08-04T10:03:00Z")];
  const segs = workSegments(msgs, []);
  assert.equal(segs.length, 2, "qa 切、orchestrate 不切");
  assert.equal(segs[1].start, 2);
});

test("任务创建戳投影：首条 createdAt 严格大于边界戳开新段", () => {
  const msgs = [
    u("一", "2026-08-04T10:00:00Z"),
    u("开工", "2026-08-04T10:05:00Z"),
    u("后", "2026-08-04T10:06:00Z"),
  ];
  const tasks = [{ created_at: "2026-08-04T10:05:30Z" }];
  const segs = workSegments(msgs, tasks);
  assert.equal(segs.length, 2);
  assert.equal(segs[1].start, 2, "10:06 > 10:05:30 开新段；10:05:00 不大于");
});

test("消息缺时序对该任务边界保守跳过", () => {
  const msgs = [u("一", "2026-08-04T10:00:00Z"), u("无时序"), u("仍无时序")];
  const tasks = [{ created_at: "2026-08-04T10:05:30Z" }];
  const segs = workSegments(msgs, tasks);
  assert.equal(segs.length, 1, "未知时序不切段");
});

test("本地权威边界与任务边界去重排序，ordinal 连续覆盖", () => {
  const msgs = [
    u("一", "2026-08-04T10:00:00Z"),
    refuse("2026-08-04T10:01:00Z"),
    u("二", "2026-08-04T10:02:00Z"),
    u("三", "2026-08-04T10:09:00Z"),
  ];
  const tasks = [{ created_at: "2026-08-04T10:05:00Z" }];
  const segs = workSegments(msgs, tasks, Date.parse("2026-08-04T10:05:00Z"));
  assert.equal(segs.length, 3);
  assert.deepEqual(segs.map((s) => s.start), [0, 2, 3]);
  assert.deepEqual(segs.map((s) => s.ordinal), [0, 1, 2]);
  assert.equal(segs[segs.length - 1].end, msgs.length - 1);
});

test("与附件路由同源：同流上 currentWorkSegmentFiles 只携带当前段附件", () => {
  const msgs = [
    { role: "user", content: "旧材料", createdAt: "2026-08-04T10:00:00Z", attachments: [{ id: "f-old", filename: "旧.txt" }] },
    refuse("2026-08-04T10:01:00Z"),
    { role: "user", content: "新材料", createdAt: "2026-08-04T10:02:00Z", attachments: [{ id: "f-new", filename: "新.txt" }] },
  ];
  const carried = currentWorkSegmentFiles(msgs, []);
  assert.deepEqual(carried.map((c) => c.id), ["f-new"]);
  const segs = workSegments(msgs, []);
  assert.equal(segs[segs.length - 1].start, 2, "当前段起点与附件路由终点同源");
});
