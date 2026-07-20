/**
 * Conversation-page async generation gate.
 *
 * A session epoch changes on every navigation, including A -> B -> A. Operation
 * sequences are scoped within that epoch so a newer load does not invalidate an
 * unrelated send, while an older load can never overwrite a newer one.
 */
export function createConversationRuntimeGate() {
  let epoch = 0;
  let session = "";
  const operations = new Map();

  function enterSession(nextSession = "") {
    epoch += 1;
    session = nextSession;
    operations.clear();
    return Object.freeze({ epoch, session });
  }

  function begin(scope) {
    if (typeof scope !== "string" || !scope) {
      throw new TypeError("conversation runtime operation scope is required");
    }
    const sequence = (operations.get(scope) || 0) + 1;
    operations.set(scope, sequence);
    return Object.freeze({ epoch, session, scope, sequence });
  }

  function isCurrent(token, expectedSession = token?.session) {
    return Boolean(
      token
      && token.epoch === epoch
      && token.session === session
      && session === expectedSession
      && operations.get(token.scope) === token.sequence,
    );
  }

  function bindSession(token, nextSession) {
    if (!isCurrent(token)) {
      throw new Error("cannot bind a stale conversation runtime operation");
    }
    session = nextSession;
    return Object.freeze({ ...token, session: nextSession });
  }

  return {
    enterSession,
    begin,
    bindSession,
    isCurrent,
    currentSession: () => session,
  };
}

/** Pure write gate used before any optimistic conversation mutation. */
export function conversationWriteEligibility({
  routeConversationId = "",
  loadedConversationId = "",
  loadState = "fresh",
  snapshotInFlight = false,
} = {}) {
  if (routeConversationId) {
    if (loadState === "error") return { allowed: false, reason: "load_error" };
    if (loadState !== "ready") return { allowed: false, reason: "loading" };
    if (loadedConversationId !== routeConversationId) {
      return { allowed: false, reason: "route_transition" };
    }
    if (snapshotInFlight === true) return { allowed: false, reason: "syncing" };
    return { allowed: true, reason: null };
  }
  if (loadedConversationId) return { allowed: false, reason: "route_transition" };
  if (loadState === "error") return { allowed: false, reason: "load_error" };
  if (loadState === "loading" || snapshotInFlight === true) {
    return { allowed: false, reason: "loading" };
  }
  return { allowed: true, reason: null };
}

/** Decide whether a mutation completion may have changed server truth. */
export function shouldReconcileConversationMutation({ isCurrent, outcome, status }) {
  if (outcome === "success") return isCurrent !== true;
  if (outcome !== "error") return false;
  return status === 409
    || status === 0
    || status == null
    || (Number.isInteger(status) && status >= 500 && status <= 599);
}

const CONVERSATION_ID = /^conv_[a-f0-9]{32}$/;
const QUESTION_ID = /^q_[a-f0-9]{32}$/;
const MESSAGE_ID = /^msg_[a-f0-9]{32}$/;
const OPTION_ID = /^option_[1-9][0-9]*$/;
const TIMESTAMP = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(?:Z|([+-])(\d{2}):(\d{2}))$/;
const QUESTION_TTL_MICROS = 86_400_000_000n;
const QUESTION_STATUSES = new Set(["pending", "answered", "expired", "superseded"]);
const CONVERSATION_STATUSES = new Set(["active", "concluded"]);
const CONVERSATION_TITLE_CONTROL = /[\u0000-\u001f\u007f-\u009f]/;

export class ConversationRuntimeContractError extends Error {
  constructor(detail) {
    super(`会话响应合同不可信：${detail}`);
    this.name = "ConversationRuntimeContractError";
    this.code = "conversation_contract_invalid";
  }
}

function contract(condition, detail) {
  if (condition !== true) throw new ConversationRuntimeContractError(detail);
}

function object(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function exactKeys(value, expected, path) {
  contract(object(value), `${path} 必须是对象`);
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  contract(
    actual.length === wanted.length && actual.every((key, index) => key === wanted[index]),
    `${path} 字段不完整或含未知字段`,
  );
}

function validText(value, maximum) {
  return typeof value === "string" && value.trim().length > 0 && value.length <= maximum;
}

function validConversationTitle(value) {
  return typeof value === "string"
    && value.length >= 1
    && value.length <= 60
    && value === value.trim()
    && CONVERSATION_TITLE_CONTROL.test(value) !== true;
}

function parseTimestampMicros(value) {
  if (typeof value !== "string") return null;
  const match = TIMESTAMP.exec(value);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6]);
  const fraction = match[7] || "";
  const offsetSign = match[8];
  const offsetHour = match[9] === undefined ? 0 : Number(match[9]);
  const offsetMinute = match[10] === undefined ? 0 : Number(match[10]);
  if (
    year < 1
    || month < 1
    || month > 12
    || hour > 23
    || minute > 59
    || second > 59
    || offsetHour > 23
    || offsetMinute > 59
  ) return null;
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const daysInMonth = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (day < 1 || day > daysInMonth[month - 1]) return null;

  // Gregorian civil date to days since Unix epoch. Keeping the whole-second
  // epoch and the six-digit fraction separate avoids Date.parse's millisecond
  // truncation at the fail-closed answer-expiry boundary.
  const adjustedYear = month <= 2 ? year - 1 : year;
  const era = Math.floor(adjustedYear / 400);
  const yearOfEra = adjustedYear - era * 400;
  const adjustedMonth = month + (month > 2 ? -3 : 9);
  const dayOfYear = Math.floor((153 * adjustedMonth + 2) / 5) + day - 1;
  const dayOfEra = yearOfEra * 365
    + Math.floor(yearOfEra / 4)
    - Math.floor(yearOfEra / 100)
    + dayOfYear;
  const daysSinceEpoch = era * 146097 + dayOfEra - 719468;
  const localSeconds = BigInt(daysSinceEpoch) * 86_400n
    + BigInt(hour * 3600 + minute * 60 + second);
  const unsignedOffsetSeconds = offsetHour * 3600 + offsetMinute * 60;
  const offsetSeconds = offsetSign === "+"
    ? unsignedOffsetSeconds
    : offsetSign === "-" ? -unsignedOffsetSeconds : 0;
  const utcSeconds = localSeconds - BigInt(offsetSeconds);
  const micros = BigInt((fraction || "0").padEnd(6, "0"));
  return utcSeconds * 1_000_000n + micros;
}

function validTimestamp(value) {
  return parseTimestampMicros(value) !== null;
}

function samePayload(left, right) {
  if (!object(left) || !object(right) || left.kind !== right.kind) return false;
  if (left.kind === "option") return left.option_id === right.option_id;
  if (left.kind === "text") return left.text === right.text;
  return false;
}

function validateAnswer(answer, question, path) {
  exactKeys(answer, [
    "schema_version",
    "question_id",
    "question_revision",
    "submission_id",
    "payload",
    "answered_by_username",
    "answered_at",
    "answer_message_id",
    "response_message_id",
  ], path);
  contract(answer.schema_version === "conversation-answer/v1", `${path}.schema_version 非法`);
  contract(answer.question_id === question.id, `${path}.question_id 未指向当前问题`);
  contract(answer.question_revision === question.revision, `${path}.question_revision 不匹配`);
  contract(validText(answer.submission_id, 128) && answer.submission_id.length >= 8, `${path}.submission_id 非法`);
  contract(validText(answer.answered_by_username, 100), `${path}.answered_by_username 非法`);
  contract(answer.answered_by_username === question.asked_to_username, `${path}.answered_by_username 与接收人不一致`);
  contract(validTimestamp(answer.answered_at), `${path}.answered_at 非法`);
  contract(MESSAGE_ID.test(answer.answer_message_id), `${path}.answer_message_id 非法`);
  contract(MESSAGE_ID.test(answer.response_message_id), `${path}.response_message_id 非法`);
  contract(answer.answer_message_id !== answer.response_message_id, `${path} 的消息链接重复`);

  if (answer.payload?.kind === "option") {
    exactKeys(answer.payload, ["kind", "option_id"], `${path}.payload`);
    contract(question.kind === "single_choice", `${path}.payload 不适用于自由文本问题`);
    contract(OPTION_ID.test(answer.payload.option_id), `${path}.payload.option_id 非法`);
    contract(
      question.options.some((option) => option.id === answer.payload.option_id),
      `${path}.payload.option_id 不在冻结选项中`,
    );
  } else if (answer.payload?.kind === "text") {
    exactKeys(answer.payload, ["kind", "text"], `${path}.payload`);
    contract(validText(answer.payload.text, 4000), `${path}.payload.text 非法`);
  } else {
    throw new ConversationRuntimeContractError(`${path}.payload.kind 非法`);
  }
}

function validateQuestion(question, { conversationId, promptMessageId, path = "question" } = {}) {
  exactKeys(question, [
    "schema_version",
    "id",
    "conversation_id",
    "prompt_message_id",
    "revision",
    "kind",
    "prompt",
    "description",
    "options",
    "asked_to_username",
    "status",
    "created_at",
    "expires_at",
    "answer",
    "closed_at",
  ], path);
  contract(question.schema_version === "conversation-question/v1", `${path}.schema_version 非法`);
  contract(QUESTION_ID.test(question.id), `${path}.id 非法`);
  contract(CONVERSATION_ID.test(question.conversation_id), `${path}.conversation_id 非法`);
  if (conversationId !== undefined) {
    contract(question.conversation_id === conversationId, `${path}.conversation_id 与当前会话不一致`);
  }
  contract(MESSAGE_ID.test(question.prompt_message_id), `${path}.prompt_message_id 非法`);
  if (promptMessageId !== undefined) {
    contract(question.prompt_message_id === promptMessageId, `${path}.prompt_message_id 未指向承载消息`);
  }
  contract(question.revision === 1, `${path}.revision 非法`);
  contract(question.kind === "single_choice" || question.kind === "free_text", `${path}.kind 非法`);
  contract(validText(question.prompt, 500), `${path}.prompt 非法`);
  contract(
    question.description === null || validText(question.description, 1000),
    `${path}.description 非法`,
  );
  contract(Array.isArray(question.options), `${path}.options 必须是数组`);
  if (question.kind === "single_choice") {
    contract(question.options.length >= 2 && question.options.length <= 6, `${path}.options 数量非法`);
  } else {
    contract(question.options.length === 0, `${path}.free_text 不得携带 options`);
  }
  const optionIds = new Set();
  question.options.forEach((option, index) => {
    const optionPath = `${path}.options[${index}]`;
    exactKeys(option, ["id", "label", "description"], optionPath);
    contract(option.id === `option_${index + 1}` && OPTION_ID.test(option.id), `${optionPath}.id 非法`);
    contract(!optionIds.has(option.id), `${optionPath}.id 重复`);
    optionIds.add(option.id);
    contract(validText(option.label, 200), `${optionPath}.label 非法`);
    contract(option.description === null || validText(option.description, 500), `${optionPath}.description 非法`);
  });
  contract(validText(question.asked_to_username, 100), `${path}.asked_to_username 非法`);
  contract(QUESTION_STATUSES.has(question.status), `${path}.status 非法`);
  contract(validTimestamp(question.created_at), `${path}.created_at 非法`);
  contract(validTimestamp(question.expires_at), `${path}.expires_at 非法`);
  const createdAt = parseTimestampMicros(question.created_at);
  const expiresAt = parseTimestampMicros(question.expires_at);
  contract(expiresAt - createdAt === QUESTION_TTL_MICROS, `${path} 的 TTL 不是平台冻结的 24 小时`);

  if (question.status === "pending") {
    contract(question.answer === null && question.closed_at === null, `${path}.pending 闭合事实非法`);
  } else if (question.status === "answered") {
    contract(validTimestamp(question.closed_at), `${path}.closed_at 非法`);
    validateAnswer(question.answer, question, `${path}.answer`);
    contract(question.answer.answered_at === question.closed_at, `${path}.answered_at 与 closed_at 不一致`);
    const answeredAt = parseTimestampMicros(question.answer.answered_at);
    contract(createdAt <= answeredAt && answeredAt < expiresAt, `${path}.answered_at 超出问题有效期`);
  } else if (question.status === "expired") {
    contract(question.answer === null, `${path}.expired 不得携带回答`);
    contract(validTimestamp(question.closed_at), `${path}.closed_at 非法`);
    const closedAt = parseTimestampMicros(question.closed_at);
    contract(closedAt === expiresAt, `${path}.expired 必须精确闭合在 expires_at`);
  } else {
    contract(question.answer === null, `${path}.superseded 不得携带回答`);
    contract(validTimestamp(question.closed_at), `${path}.closed_at 非法`);
    const closedAt = parseTimestampMicros(question.closed_at);
    contract(
      createdAt <= closedAt && closedAt < expiresAt,
      `${path}.superseded 的 closed_at 超出问题有效期`,
    );
  }
  return question;
}

function validateMessage(message, conversationId, path) {
  contract(object(message), `${path} 必须是对象`);
  contract(MESSAGE_ID.test(message.message_id), `${path}.message_id 缺失或非法`);
  contract(message.conversation_id === conversationId, `${path}.conversation_id 与当前会话不一致`);
  contract(message.role === "user" || message.role === "assistant", `${path}.role 非法`);
  contract(typeof message.content === "string", `${path}.content 非法`);
  if (message.question !== undefined && message.question !== null) {
    contract(message.role === "assistant", `${path} 的 Question 只能挂在 assistant 消息`);
    validateQuestion(message.question, {
      conversationId,
      promptMessageId: message.message_id,
      path: `${path}.question`,
    });
  }
  return message;
}

function validateConversationSummary(conversation, expectedId, { requireMessages }) {
  contract(object(conversation), "conversation 必须是对象");
  contract(CONVERSATION_ID.test(conversation.id), "conversation.id 非法");
  contract(conversation.id === expectedId, "conversation.id 与请求路径不一致");
  contract(validText(conversation.agent_id, 200), "conversation.agent_id 非法");
  contract(CONVERSATION_STATUSES.has(conversation.status), "conversation.status 非法");
  contract(validText(conversation.created_by, 200), "conversation.created_by 非法");
  contract(
    conversation.title === null || validConversationTitle(conversation.title),
    "conversation.title 非法",
  );
  contract(
    Number.isInteger(conversation.lifecycle_revision) && conversation.lifecycle_revision >= 0,
    "conversation.lifecycle_revision 非法",
  );
  contract(
    conversation.archived_at === null || validTimestamp(conversation.archived_at),
    "conversation.archived_at 非法",
  );
  if (requireMessages) contract(Array.isArray(conversation.messages), "conversation.messages 必须是数组");
}

/** Validate one conversation projection that intentionally omits the message history. */
export function validateConversationSummaryProjection(conversation, expectedId = conversation?.id) {
  validateConversationSummary(conversation, expectedId, { requireMessages: false });
  return conversation;
}

/** Validate a complete list authority before any row can drive labels or CAS mutations. */
export function validateConversationListProjection(conversations) {
  contract(Array.isArray(conversations), "conversation list 必须是数组");
  const ids = new Set();
  conversations.forEach((conversation, index) => {
    try {
      validateConversationSummaryProjection(conversation);
      contract(!ids.has(conversation.id), `conversation list[${index}].id 重复`);
      ids.add(conversation.id);
    } catch (error) {
      if (error instanceof ConversationRuntimeContractError) {
        throw new ConversationRuntimeContractError(`conversation list[${index}] 非法：${error.message}`);
      }
      throw error;
    }
  });
  return conversations;
}

/** Validate a GET /conversations/:id snapshot before it can replace UI truth. */
export function validateConversationSnapshot(conversation, expectedId) {
  validateConversationSummary(conversation, expectedId, { requireMessages: true });
  const byId = new Map();
  let pendingQuestionCount = 0;
  conversation.messages.forEach((message, index) => {
    validateMessage(message, expectedId, `conversation.messages[${index}]`);
    contract(!byId.has(message.message_id), `conversation.messages[${index}].message_id 重复`);
    if (message.question?.status === "pending") pendingQuestionCount += 1;
    contract(pendingQuestionCount <= 1, "conversation.messages 含多个 pending Question");
    byId.set(message.message_id, { message, index });
  });

  for (const [index, message] of conversation.messages.entries()) {
    const question = message.question;
    if (!question || question.status !== "answered") continue;
    const answerMessage = byId.get(question.answer.answer_message_id);
    const responseMessage = byId.get(question.answer.response_message_id);
    contract(answerMessage?.message.role === "user", `conversation.messages[${index}].question 的回答消息链接断裂`);
    contract(responseMessage?.message.role === "assistant", `conversation.messages[${index}].question 的回复消息链接断裂`);
    contract(
      index < answerMessage.index && answerMessage.index < responseMessage.index,
      `conversation.messages[${index}].question 的回答链顺序非法`,
    );
  }
  return conversation;
}

/** Validate a dedicated Answer 2xx before appending any canonical messages. */
export function validateConversationAnswerResponse(response, expected) {
  exactKeys(response, ["answer_message", "message", "question", "conversation", "replayed"], "answer response");
  contract(typeof response.replayed === "boolean", "answer response.replayed 非法");
  validateConversationSummary(response.conversation, expected.conversationId, { requireMessages: false });
  validateMessage(response.answer_message, expected.conversationId, "answer response.answer_message");
  validateMessage(response.message, expected.conversationId, "answer response.message");
  contract(response.answer_message.role === "user", "answer response.answer_message 不是 user 消息");
  contract(response.message.role === "assistant", "answer response.message 不是 assistant 消息");
  contract(response.answer_message.message_id !== response.message.message_id, "answer response 消息 id 重复");
  validateQuestion(response.question, {
    conversationId: expected.conversationId,
    promptMessageId: expected.promptMessageId,
    path: "answer response.question",
  });
  contract(response.question.id === expected.questionId, "answer response.question.id 与请求路径不一致");
  contract(response.question.revision === expected.questionRevision, "answer response.question.revision 与提交不一致");
  contract(response.question.status === "answered", "answer response.question 未形成 answered 事实");
  const answer = response.question.answer;
  contract(answer.submission_id === expected.submissionId, "answer response.submission_id 与提交不一致");
  contract(samePayload(answer.payload, expected.payload), "answer response.payload 与提交不一致");
  contract(answer.answer_message_id === response.answer_message.message_id, "answer response 的回答消息链接断裂");
  contract(answer.response_message_id === response.message.message_id, "answer response 的回复消息链接断裂");
  if (response.message.question !== undefined && response.message.question !== null) {
    contract(response.message.question.status === "pending", "answer response 的下一问题不是 pending");
    contract(response.message.question.id !== response.question.id, "answer response 的下一问题复用了已回答问题 id");
    contract(
      response.message.question.asked_to_username === response.question.asked_to_username,
      "answer response 的下一问题接收人与会话所有者不一致",
    );
  }
  return response;
}

/** Validate a normal message POST before replacing its optimistic user bubble. */
export function validateConversationPostResponse(response, expected) {
  exactKeys(response, ["user_message", "message", "conversation"], "message response");
  validateConversationSummary(response.conversation, expected.conversationId, { requireMessages: false });
  validateMessage(response.user_message, expected.conversationId, "message response.user_message");
  validateMessage(response.message, expected.conversationId, "message response.message");
  contract(response.user_message.role === "user", "message response.user_message 不是 user 消息");
  contract(response.message.role === "assistant", "message response.message 不是 assistant 消息");
  contract(response.user_message.content === expected.userContent, "message response.user_message.content 与提交不一致");
  contract(response.user_message.message_id !== response.message.message_id, "message response 消息 id 重复");
  if (response.message.question !== undefined && response.message.question !== null) {
    contract(response.message.question.status === "pending", "message response 的新问题不是 pending");
  }
  return response;
}
