import test from "node:test";
import assert from "node:assert/strict";

import {
  createSecureSubmissionId,
  effectiveQuestionStatus,
  hasPendingConversationQuestion,
  mergeQuestionSnapshot,
  questionAnswerLabel,
  validateQuestionSubmission,
} from "../src/utils/questionCardCore.js";

const pendingChoice = {
  id: "q_1",
  revision: 1,
  kind: "single_choice",
  status: "pending",
  expires_at: "2026-07-20T00:00:00.000Z",
  options: [
    { id: "option_1", label: "供电系统", description: null },
    { id: "option_2", label: "液压系统", description: null },
  ],
  answer: null,
};
const PENDING_NOW_MS = Date.parse("2026-07-19T23:59:59Z");

test("secure submission id falls back to getRandomValues as an RFC 4122 UUID v4", () => {
  const seeded = Uint8Array.from([
    0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x06, 0x77,
    0xf8, 0x99, 0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff,
  ]);
  const cryptoLike = {
    getRandomValues(target) {
      target.set(seeded);
      return target;
    },
  };

  assert.equal(
    createSecureSubmissionId(cryptoLike),
    "00112233-4455-4677-b899-aabbccddeeff",
  );
});

test("secure submission id fails closed when no cryptographic random source exists", () => {
  assert.throws(() => createSecureSubmissionId({}), /secure random source unavailable/);
  assert.throws(() => createSecureSubmissionId(null), /secure random source unavailable/);
});

test("effective status expires exactly at expires_at and fails closed on unknown shapes", () => {
  assert.equal(effectiveQuestionStatus(pendingChoice, Date.parse("2026-07-19T23:59:59Z")), "pending");
  assert.equal(effectiveQuestionStatus(pendingChoice, Date.parse("2026-07-20T00:00:00Z")), "expired");
  assert.equal(effectiveQuestionStatus({ ...pendingChoice, status: "answered" }, 0), "answered");
  assert.equal(effectiveQuestionStatus({ ...pendingChoice, status: "mystery" }, 0), "unknown");
  assert.equal(
    effectiveQuestionStatus({ ...pendingChoice, expires_at: "not-a-date" }, Date.now()),
    "unknown",
  );
});

test("effective status preserves a six-microsecond expiry boundary", () => {
  const fractional = {
    ...pendingChoice,
    expires_at: "2026-07-20T00:00:00.999999Z",
  };
  const startOfLastMillisecond = Date.parse("2026-07-20T00:00:00.999000Z");

  assert.equal(effectiveQuestionStatus(fractional, startOfLastMillisecond), "pending");
  assert.equal(effectiveQuestionStatus(fractional, startOfLastMillisecond + 1), "expired");
});

test("the normal composer is blocked only while a Question is effectively pending", () => {
  const messages = [{ role: "assistant", question: pendingChoice }];
  assert.equal(
    hasPendingConversationQuestion(messages, Date.parse("2026-07-19T23:59:59.999Z")),
    true,
  );
  assert.equal(
    hasPendingConversationQuestion(messages, Date.parse("2026-07-20T00:00:00.000Z")),
    false,
  );
  assert.equal(
    hasPendingConversationQuestion([
      { role: "assistant", question: { ...pendingChoice, status: "answered" } },
    ], 0),
    false,
  );
});

test("single choice accepts a declared option or explicit custom text, never a guessed default", () => {
  assert.deepEqual(
    validateQuestionSubmission(
      pendingChoice,
      { mode: "option", optionId: "option_2", text: "" },
      { nowMs: PENDING_NOW_MS },
    ),
    { ok: true, payload: { kind: "option", option_id: "option_2" }, error: "" },
  );
  assert.deepEqual(
    validateQuestionSubmission(
      pendingChoice,
      { mode: "text", optionId: "", text: "  另一个系统  " },
      { nowMs: PENDING_NOW_MS },
    ),
    { ok: true, payload: { kind: "text", text: "另一个系统" }, error: "" },
  );
  assert.equal(
    validateQuestionSubmission(
      pendingChoice,
      { mode: "option", optionId: "", text: "" },
      { nowMs: PENDING_NOW_MS },
    ).ok,
    false,
  );
  assert.equal(
    validateQuestionSubmission(
      pendingChoice,
      { mode: "option", optionId: "option_9", text: "" },
      { nowMs: PENDING_NOW_MS },
    ).ok,
    false,
  );
});

test("free text rejects option payload, blanks, and oversize input", () => {
  const question = { ...pendingChoice, kind: "free_text", options: [] };
  assert.equal(
    validateQuestionSubmission(
      question,
      { mode: "option", optionId: "option_1", text: "" },
      { nowMs: PENDING_NOW_MS },
    ).ok,
    false,
  );
  assert.equal(
    validateQuestionSubmission(
      question,
      { mode: "text", optionId: "", text: "   " },
      { nowMs: PENDING_NOW_MS },
    ).ok,
    false,
  );
  assert.equal(
    validateQuestionSubmission(
      question,
      { mode: "text", optionId: "", text: "x".repeat(4001) },
      { nowMs: PENDING_NOW_MS },
    ).ok,
    false,
  );
  assert.deepEqual(
    validateQuestionSubmission(
      question,
      { mode: "text", optionId: "", text: "验收通过率 100%" },
      { nowMs: PENDING_NOW_MS },
    ),
    { ok: true, payload: { kind: "text", text: "验收通过率 100%" }, error: "" },
  );
});

test("terminal, expired, stale, and unknown questions cannot submit", () => {
  for (const status of ["answered", "expired", "superseded", "mystery"]) {
    const result = validateQuestionSubmission(
      { ...pendingChoice, status },
      { mode: "option", optionId: "option_1", text: "" },
    );
    assert.equal(result.ok, false, status);
  }
  assert.equal(
    validateQuestionSubmission(
      pendingChoice,
      { mode: "option", optionId: "option_1", text: "" },
      { stale: true },
    ).ok,
    false,
  );
});

test("terminal local truth cannot be overwritten by a late pending snapshot", () => {
  const answered = {
    ...pendingChoice,
    status: "answered",
    answer: { payload: { kind: "option", option_id: "option_1" } },
  };
  assert.equal(mergeQuestionSnapshot(answered, pendingChoice), answered);
  assert.equal(mergeQuestionSnapshot(pendingChoice, answered), answered);
  const next = { ...pendingChoice, id: "q_2" };
  assert.equal(mergeQuestionSnapshot(answered, next), next);
});

test("a terminal Question resolution is immutable across contradictory snapshots", () => {
  const answered = {
    ...pendingChoice,
    status: "answered",
    answer: { payload: { kind: "option", option_id: "option_1" } },
  };
  const expired = { ...pendingChoice, status: "expired" };
  const rewrittenAnswer = {
    ...answered,
    answer: { payload: { kind: "option", option_id: "option_2" } },
  };

  assert.equal(mergeQuestionSnapshot(answered, expired), answered);
  assert.equal(mergeQuestionSnapshot(answered, rewrittenAnswer), answered);
  assert.equal(mergeQuestionSnapshot(expired, answered), expired);
});

test("answered label is exact and never uses approval language", () => {
  assert.equal(
    questionAnswerLabel({
      ...pendingChoice,
      status: "answered",
      answer: { payload: { kind: "option", option_id: "option_2" } },
    }),
    "液压系统",
  );
  assert.equal(
    questionAnswerLabel({
      ...pendingChoice,
      status: "answered",
      answer: { payload: { kind: "text", text: "自定义范围" } },
    }),
    "自定义范围",
  );
  assert.equal(questionAnswerLabel(pendingChoice), "");
});
