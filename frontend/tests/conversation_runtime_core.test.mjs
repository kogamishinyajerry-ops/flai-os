import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  ConversationRuntimeContractError,
  conversationWriteEligibility,
  createConversationRuntimeGate,
  shouldReconcileConversationMutation,
  validateConversationAnswerResponse,
  validateConversationPostResponse,
  validateConversationSnapshot,
} from "../src/utils/conversationRuntimeCore.js";

const CONVERSATION_ID = `conv_${"a".repeat(32)}`;
const QUESTION_ID = `q_${"b".repeat(32)}`;
const PROMPT_MESSAGE_ID = `msg_${"1".repeat(32)}`;
const ANSWER_MESSAGE_ID = `msg_${"2".repeat(32)}`;
const RESPONSE_MESSAGE_ID = `msg_${"3".repeat(32)}`;
const NEXT_QUESTION_ID = `q_${"c".repeat(32)}`;
const NOW = "2026-07-19T10:00:00+08:00";
const LATER = "2026-07-20T10:00:00+08:00";

const clone = (value) => structuredClone(value);

function answeredQuestion() {
  return {
    schema_version: "conversation-question/v1",
    id: QUESTION_ID,
    conversation_id: CONVERSATION_ID,
    prompt_message_id: PROMPT_MESSAGE_ID,
    revision: 1,
    kind: "single_choice",
    prompt: "请选择核对范围。",
    description: null,
    options: [
      { id: "option_1", label: "当前任务", description: null },
      { id: "option_2", label: "全部任务", description: null },
    ],
    asked_to_username: "alice",
    status: "answered",
    created_at: NOW,
    expires_at: LATER,
    answer: {
      schema_version: "conversation-answer/v1",
      question_id: QUESTION_ID,
      question_revision: 1,
      submission_id: "submission-0001",
      payload: { kind: "option", option_id: "option_1" },
      answered_by_username: "alice",
      answered_at: NOW,
      answer_message_id: ANSWER_MESSAGE_ID,
      response_message_id: RESPONSE_MESSAGE_ID,
    },
    closed_at: NOW,
  };
}

function validSnapshot() {
  return {
    id: CONVERSATION_ID,
    agent_id: "guide_agent",
    status: "active",
    created_by: "Alice",
    title: null,
    lifecycle_revision: 0,
    archived_at: null,
    recommendation: null,
    messages: [
      {
        message_id: PROMPT_MESSAGE_ID,
        conversation_id: CONVERSATION_ID,
        role: "assistant",
        content: "请选择核对范围。",
        recommendation: null,
        file_ids: [],
        created_at: NOW,
        question: answeredQuestion(),
      },
      {
        message_id: ANSWER_MESSAGE_ID,
        conversation_id: CONVERSATION_ID,
        role: "user",
        content: "回答：当前任务",
        recommendation: null,
        file_ids: [],
        created_at: NOW,
      },
      {
        message_id: RESPONSE_MESSAGE_ID,
        conversation_id: CONVERSATION_ID,
        role: "assistant",
        content: "已按当前任务继续。",
        recommendation: null,
        file_ids: [],
        created_at: NOW,
      },
    ],
  };
}

function validAnswerResponse() {
  const snapshot = validSnapshot();
  return {
    answer_message: snapshot.messages[1],
    message: snapshot.messages[2],
    question: answeredQuestion(),
    conversation: {
      id: CONVERSATION_ID,
      agent_id: "guide_agent",
      status: "active",
      created_by: "Alice",
      title: null,
      lifecycle_revision: 0,
      archived_at: null,
      recommendation: null,
    },
    replayed: false,
  };
}

function pendingNextQuestion() {
  return {
    ...answeredQuestion(),
    id: NEXT_QUESTION_ID,
    prompt_message_id: RESPONSE_MESSAGE_ID,
    status: "pending",
    answer: null,
    closed_at: null,
  };
}

test("conversation runtime generations reject A to B to A late continuations", () => {
  const gate = createConversationRuntimeGate();

  gate.enterSession("conv_a");
  const firstLoad = gate.begin("load");
  const firstSend = gate.begin("send");

  gate.enterSession("conv_b");
  gate.enterSession("conv_a");
  const currentLoad = gate.begin("load");

  assert.equal(gate.isCurrent(firstLoad, "conv_a"), false);
  assert.equal(gate.isCurrent(firstSend, "conv_a"), false);
  assert.equal(gate.isCurrent(currentLoad, "conv_a"), true);
});

test("a newer operation in one session invalidates only the same operation scope", () => {
  const gate = createConversationRuntimeGate();
  gate.enterSession("conv_a");

  const firstLoad = gate.begin("load");
  const send = gate.begin("send");
  const secondLoad = gate.begin("load");

  assert.equal(gate.isCurrent(firstLoad, "conv_a"), false);
  assert.equal(gate.isCurrent(secondLoad, "conv_a"), true);
  assert.equal(gate.isCurrent(send, "conv_a"), true);
});

test("a new conversation can be bound to the current send without reopening its generation", () => {
  const gate = createConversationRuntimeGate();
  gate.enterSession("");
  const unboundSend = gate.begin("send");

  const boundSend = gate.bindSession(unboundSend, "conv_created");

  assert.equal(gate.isCurrent(unboundSend, "conv_created"), false);
  assert.equal(gate.isCurrent(boundSend, "conv_created"), true);
  assert.equal(gate.currentSession(), "conv_created");
});

test("a routed conversation is never writable until its exact GET snapshot is ready", () => {
  assert.deepEqual(conversationWriteEligibility({
    routeConversationId: CONVERSATION_ID,
    loadedConversationId: "",
    loadState: "loading",
    snapshotInFlight: true,
  }), { allowed: false, reason: "loading" });
  assert.deepEqual(conversationWriteEligibility({
    routeConversationId: CONVERSATION_ID,
    loadedConversationId: "",
    loadState: "error",
    snapshotInFlight: false,
  }), { allowed: false, reason: "load_error" });
  assert.deepEqual(conversationWriteEligibility({
    routeConversationId: CONVERSATION_ID,
    loadedConversationId: CONVERSATION_ID,
    loadState: "ready",
    snapshotInFlight: false,
  }), { allowed: true, reason: null });
  assert.deepEqual(conversationWriteEligibility({
    routeConversationId: "",
    loadedConversationId: "",
    loadState: "fresh",
    snapshotInFlight: false,
  }), { allowed: true, reason: null });
  assert.deepEqual(conversationWriteEligibility({
    routeConversationId: "",
    loadedConversationId: CONVERSATION_ID,
    loadState: "ready",
    snapshotInFlight: false,
  }), { allowed: false, reason: "route_transition" });
});

test("late or ambiguous mutation outcomes share one reconciliation decision", () => {
  for (const outcome of [
    { isCurrent: false, outcome: "success", status: 200 },
    { isCurrent: false, outcome: "error", status: 0 },
    { isCurrent: false, outcome: "error", status: null },
    { isCurrent: false, outcome: "error", status: 409 },
    { isCurrent: true, outcome: "error", status: 409 },
    { isCurrent: false, outcome: "error", status: 500 },
    { isCurrent: true, outcome: "error", status: 504 },
  ]) {
    assert.equal(shouldReconcileConversationMutation(outcome), true);
  }
  assert.equal(shouldReconcileConversationMutation({
    isCurrent: false,
    outcome: "error",
    status: 422,
  }), false);
  assert.equal(shouldReconcileConversationMutation({
    isCurrent: true,
    outcome: "success",
    status: 200,
  }), false);
});

test("conversation contract assertions require an exact boolean true verdict", () => {
  const source = readFileSync(
    new URL("../src/utils/conversationRuntimeCore.js", import.meta.url),
    "utf8",
  );
  assert.match(source, /function contract\(condition, detail\)\s*\{\s*if \(condition !== true\)/);
  assert.doesNotMatch(source, /function contract\(condition, detail\)\s*\{\s*if \(!condition\)/);
});

test("GET conversation snapshots accept only stable, internally linked Question facts", () => {
  const valid = validSnapshot();
  assert.equal(validateConversationSnapshot(valid, CONVERSATION_ID), valid);

  const malformed = [
    ["wrong conversation id", (snapshot) => { snapshot.id = `conv_${"c".repeat(32)}`; }],
    ["missing stable message id", (snapshot) => { delete snapshot.messages[1].message_id; }],
    ["Question on a user role", (snapshot) => {
      snapshot.messages[0].role = "user";
    }],
    ["broken prompt link", (snapshot) => {
      snapshot.messages[0].question.prompt_message_id = RESPONSE_MESSAGE_ID;
    }],
    ["answer link to the wrong role", (snapshot) => {
      snapshot.messages[0].question.answer.answer_message_id = PROMPT_MESSAGE_ID;
    }],
    ["answer link to a missing response", (snapshot) => {
      snapshot.messages[0].question.answer.response_message_id = `msg_${"4".repeat(32)}`;
    }],
    ["answer message before its Question prompt", (snapshot) => {
      snapshot.messages = [snapshot.messages[1], snapshot.messages[0], snapshot.messages[2]];
    }],
    ["assistant response before its answer message", (snapshot) => {
      snapshot.messages = [snapshot.messages[0], snapshot.messages[2], snapshot.messages[1]];
    }],
    ["hour 24 is not RFC3339", (snapshot) => {
      snapshot.messages[0].question.created_at = "2026-07-18T24:00:00+08:00";
    }],
    ["year zero is not RFC3339", (snapshot) => {
      snapshot.messages[0].question.created_at = "0000-07-19T10:00:00+08:00";
    }],
    ["normalized February 30 is not RFC3339", (snapshot) => {
      snapshot.messages[0].question.created_at = "2026-02-30T10:00:00+08:00";
    }],
    ["a Question TTL shorter than the frozen 24 hours", (snapshot) => {
      snapshot.messages[0].question.expires_at = "2026-07-20T09:59:59+08:00";
    }],
    ["a Question TTL longer than the frozen 24 hours", (snapshot) => {
      snapshot.messages[0].question.expires_at = "2026-07-20T10:00:01+08:00";
    }],
  ];

  for (const [label, mutate] of malformed) {
    const snapshot = clone(valid);
    mutate(snapshot);
    assert.throws(
      () => validateConversationSnapshot(snapshot, CONVERSATION_ID),
      ConversationRuntimeContractError,
      label,
    );
  }
});

test("GET conversation snapshots reject more than one pending Question", () => {
  const snapshot = validSnapshot();
  snapshot.messages[0].question.status = "pending";
  snapshot.messages[0].question.answer = null;
  snapshot.messages[0].question.closed_at = null;
  snapshot.messages[2].question = pendingNextQuestion();

  assert.throws(
    () => validateConversationSnapshot(snapshot, CONVERSATION_ID),
    ConversationRuntimeContractError,
  );
});

test("terminal Question timestamps preserve the frozen expiry and supersession relations", () => {
  const expired = validSnapshot();
  expired.messages[0].question.status = "expired";
  expired.messages[0].question.answer = null;
  expired.messages[0].question.closed_at = "2026-07-20T02:00:00Z";
  assert.equal(validateConversationSnapshot(expired, CONVERSATION_ID), expired);

  const expiredEarly = clone(expired);
  expiredEarly.messages[0].question.closed_at = "2026-07-20T01:59:59.999999Z";
  assert.throws(
    () => validateConversationSnapshot(expiredEarly, CONVERSATION_ID),
    ConversationRuntimeContractError,
  );

  const superseded = validSnapshot();
  superseded.messages[0].question.status = "superseded";
  superseded.messages[0].question.answer = null;
  superseded.messages[0].question.closed_at = "2026-07-19T02:00:00Z";
  assert.equal(validateConversationSnapshot(superseded, CONVERSATION_ID), superseded);

  for (const closedAt of [
    "2026-07-19T01:59:59.999999Z",
    "2026-07-20T02:00:00Z",
  ]) {
    const malformed = clone(superseded);
    malformed.messages[0].question.closed_at = closedAt;
    assert.throws(
      () => validateConversationSnapshot(malformed, CONVERSATION_ID),
      ConversationRuntimeContractError,
    );
  }
});

test("Answer 2xx responses must preserve question, message roles, stable ids, and immutable links", () => {
  const expected = {
    conversationId: CONVERSATION_ID,
    questionId: QUESTION_ID,
    questionRevision: 1,
    promptMessageId: PROMPT_MESSAGE_ID,
    submissionId: "submission-0001",
    payload: { kind: "option", option_id: "option_1" },
  };
  const valid = validAnswerResponse();
  assert.equal(validateConversationAnswerResponse(valid, expected), valid);

  const malformed = [
    ["wrong question id", (response) => { response.question.id = `q_${"c".repeat(32)}`; }],
    ["wrong answer role", (response) => { response.answer_message.role = "assistant"; }],
    ["wrong response role", (response) => { response.message.role = "user"; }],
    ["missing response message id", (response) => { delete response.message.message_id; }],
    ["broken answer message link", (response) => {
      response.question.answer.answer_message_id = PROMPT_MESSAGE_ID;
    }],
    ["broken response message link", (response) => {
      response.question.answer.response_message_id = PROMPT_MESSAGE_ID;
    }],
    ["wrong submission replay", (response) => {
      response.question.answer.submission_id = "submission-other";
    }],
  ];

  for (const [label, mutate] of malformed) {
    const response = clone(valid);
    mutate(response);
    assert.throws(
      () => validateConversationAnswerResponse(response, expected),
      ConversationRuntimeContractError,
      label,
    );
  }

  const beforeCreation = clone(valid);
  beforeCreation.question.answer.answered_at = "2026-07-19T09:59:59+08:00";
  beforeCreation.question.closed_at = beforeCreation.question.answer.answered_at;
  assert.throws(
    () => validateConversationAnswerResponse(beforeCreation, expected),
    ConversationRuntimeContractError,
  );

  const atExpiry = clone(valid);
  atExpiry.question.answer.answered_at = atExpiry.question.expires_at;
  atExpiry.question.closed_at = atExpiry.question.answer.answered_at;
  assert.throws(
    () => validateConversationAnswerResponse(atExpiry, expected),
    ConversationRuntimeContractError,
  );

  const oneMicrosecondBeforeExpiry = clone(valid);
  oneMicrosecondBeforeExpiry.question.created_at = "2026-07-19T10:00:00.123456+08:00";
  oneMicrosecondBeforeExpiry.question.expires_at = "2026-07-20T11:00:00.123456+09:00";
  oneMicrosecondBeforeExpiry.question.answer.answered_at = "2026-07-20T11:00:00.123455+09:00";
  oneMicrosecondBeforeExpiry.question.closed_at = oneMicrosecondBeforeExpiry.question.answer.answered_at;
  assert.equal(
    validateConversationAnswerResponse(oneMicrosecondBeforeExpiry, expected),
    oneMicrosecondBeforeExpiry,
  );

  const exactMicrosecondExpiry = clone(oneMicrosecondBeforeExpiry);
  exactMicrosecondExpiry.question.answer.answered_at = exactMicrosecondExpiry.question.expires_at;
  exactMicrosecondExpiry.question.closed_at = exactMicrosecondExpiry.question.answer.answered_at;
  assert.throws(
    () => validateConversationAnswerResponse(exactMicrosecondExpiry, expected),
    ConversationRuntimeContractError,
  );

  const zuluFractionalTimestamp = clone(valid);
  zuluFractionalTimestamp.question.created_at = "2026-07-19T02:00:00.1Z";
  zuluFractionalTimestamp.question.expires_at = "2026-07-20T02:00:00.100000Z";
  zuluFractionalTimestamp.question.answer.answered_at = "2026-07-20T02:00:00.099999Z";
  zuluFractionalTimestamp.question.closed_at = zuluFractionalTimestamp.question.answer.answered_at;
  assert.equal(
    validateConversationAnswerResponse(zuluFractionalTimestamp, expected),
    zuluFractionalTimestamp,
  );

  const sameNextQuestion = clone(valid);
  sameNextQuestion.message.question = pendingNextQuestion();
  sameNextQuestion.message.question.id = QUESTION_ID;
  assert.throws(
    () => validateConversationAnswerResponse(sameNextQuestion, expected),
    ConversationRuntimeContractError,
  );

  const transferredNextQuestion = clone(valid);
  transferredNextQuestion.message.question = pendingNextQuestion();
  transferredNextQuestion.message.question.asked_to_username = "bob";
  assert.throws(
    () => validateConversationAnswerResponse(transferredNextQuestion, expected),
    ConversationRuntimeContractError,
  );
});

test("message POST 2xx responses require both canonical stable message identities", () => {
  const response = {
    user_message: validSnapshot().messages[1],
    message: validSnapshot().messages[2],
    conversation: validAnswerResponse().conversation,
  };
  assert.equal(validateConversationPostResponse(response, {
    conversationId: CONVERSATION_ID,
    userContent: response.user_message.content,
  }), response);

  const missingUserId = clone(response);
  delete missingUserId.user_message.message_id;
  assert.throws(
    () => validateConversationPostResponse(missingUserId, {
      conversationId: CONVERSATION_ID,
      userContent: response.user_message.content,
    }),
    ConversationRuntimeContractError,
  );

  const wrongAssistantRole = clone(response);
  wrongAssistantRole.message.role = "user";
  assert.throws(
    () => validateConversationPostResponse(wrongAssistantRole, {
      conversationId: CONVERSATION_ID,
      userContent: response.user_message.content,
    }),
    ConversationRuntimeContractError,
  );

  const forgedAnsweredQuestion = clone(response);
  forgedAnsweredQuestion.message.question = {
    ...answeredQuestion(),
    id: NEXT_QUESTION_ID,
    prompt_message_id: RESPONSE_MESSAGE_ID,
    answer: {
      ...answeredQuestion().answer,
      question_id: NEXT_QUESTION_ID,
    },
  };
  assert.throws(
    () => validateConversationPostResponse(forgedAnsweredQuestion, {
      conversationId: CONVERSATION_ID,
      userContent: response.user_message.content,
    }),
    ConversationRuntimeContractError,
  );
});

test("Guide wires every conversation continuation through the generation and contract gates", () => {
  const guide = readFileSync(new URL("../src/views/GuidePage.vue", import.meta.url), "utf8");

  assert.match(guide, /createConversationRuntimeGate/);
  assert.match(guide, /conversationRuntimeGate\.enterSession\(/);
  assert.match(guide, /conversationRuntimeGate\.begin\("load"\)/);
  assert.match(guide, /conversationRuntimeGate\.begin\("send"\)/);
  assert.match(guide, /conversationRuntimeGate\.isCurrent\(/);
  assert.match(guide, /validateConversationSnapshot\(/);
  assert.match(guide, /validateConversationAnswerResponse\(/);
  assert.match(guide, /async function reconcileLateConversationMutation[\s\S]{0,800}reconcileConversationSnapshot\(/);
  assert.match(guide, /async function reconcileConversationMutationOutcome[\s\S]{0,300}shouldReconcileConversationMutation[\s\S]{0,300}reconcileLateConversationMutation/);
  assert.ok((guide.match(/reconcileConversationMutationOutcome\(/g) || []).length >= 4);
  assert.match(guide, /const conversationLoadState = ref\("fresh"\)/);
  assert.match(guide, /const conversationSnapshotInFlight = ref\(false\)/);
  assert.match(guide, /conversationWriteEligibility\(/);
  assert.match(guide, /const conversationWriteReady = computed\(/);
  assert.match(guide, /:disabled="sending \|\| !composerWriteReady"/);
  assert.match(guide, /重新加载/);
  assert.match(guide, /新对话/);
  assert.match(guide, /retryFailedConversation/);
  assert.match(guide, /startFreshAfterLoadFailure/);

  const sendStart = guide.indexOf("async function send()");
  const sendPush = guide.indexOf("messages.value.push(optimisticMessage)", sendStart);
  const sendEligibility = guide.indexOf("conversationWriteDecision.value", sendStart);
  assert.ok(sendEligibility > sendStart && sendEligibility < sendPush);
  assert.ok((guide.match(/shouldReconcileConversationMutation\(/g) || []).length >= 2);
});
