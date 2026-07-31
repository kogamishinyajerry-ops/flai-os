// frontend/tests/conversation_title.test.mjs — node --test，零框架依赖。
// 侧栏标题 SSOT（conversationTitle）三层诚实回退：
//   列表投影 first_user_message → 本会话内存缓存 → 「与 X 的对话」，
// recommendation 裁决（orchestrate/refuse）优先于一切内容层。
import test from "node:test";
import assert from "node:assert/strict";
import {
  conversationTitle,
  recordConversationFirstUserContent,
} from "../src/utils/conversationTitles.js";

test("conversationTitle: 列表投影 first_user_message 直接作标题（刷新不依赖缓存）", () => {
  const c = { id: "p1", created_by: "甲", first_user_message: "帮我看看颤振边界" };
  assert.equal(conversationTitle(c), "帮我看看颤振边界");
});

test("conversationTitle: 投影超 18 字截断加 …（tamper：截断长度改动此条必红）", () => {
  const long = "这是一个非常非常长的用户需求描述需要被截断处理";
  const c = { id: "p2", created_by: "甲", first_user_message: long };
  assert.equal(conversationTitle(c), `${long.slice(0, 18)}…`);
  // 恰 18 字不加省略号
  const exact = "x".repeat(18);
  assert.equal(
    conversationTitle({ id: "p3", first_user_message: exact }),
    exact,
  );
});

test("conversationTitle: 投影优先于缓存（服务端权威盖过内存层）", () => {
  recordConversationFirstUserContent("p4", [
    { role: "user", content: "缓存里的旧标题" },
  ]);
  const c = { id: "p4", created_by: "甲", first_user_message: "投影里的新标题" };
  assert.equal(conversationTitle(c), "投影里的新标题");
});

test("conversationTitle: 投影 null/缺失 → 回退内存缓存（第二层）", () => {
  recordConversationFirstUserContent("p5", [
    { role: "assistant", content: "开场白" },
    { role: "user", content: "  缓存标题，带空白  " },
  ]);
  assert.equal(
    conversationTitle({ id: "p5", created_by: "甲", first_user_message: null }),
    "缓存标题，带空白",
  );
  assert.equal(
    conversationTitle({ id: "p5", created_by: "甲" }),
    "缓存标题，带空白",
  );
});

test("conversationTitle: 投影为空白串不当作标题（诚实下落到缓存/兜底）", () => {
  assert.equal(
    conversationTitle({ id: "p6", created_by: "甲", first_user_message: "   " }),
    "与 甲 的对话",
  );
});

test("conversationTitle: 两层都缺失 → 兜底「与 X 的对话」，created_by 缺失用「你」", () => {
  assert.equal(
    conversationTitle({ id: "p7", created_by: "乙", first_user_message: null }),
    "与 乙 的对话",
  );
  assert.equal(
    conversationTitle({ id: "p8", first_user_message: null }),
    "与 你 的对话",
  );
});

test("conversationTitle: recommendation 裁决优先于投影（orchestrate/refuse 口径不变）", () => {
  assert.equal(
    conversationTitle({
      id: "p9",
      first_user_message: "内容层标题",
      recommendation: { decision: "orchestrate", goal: "颤振评估编排" },
    }),
    "颤振评估编排",
  );
  assert.equal(
    conversationTitle({
      id: "p10",
      first_user_message: "内容层标题",
      recommendation: { decision: "refuse", reason: "超出能力边界" },
    }),
    "（未接住）超出能力边界",
  );
});
