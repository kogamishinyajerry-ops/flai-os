// Pure QuestionCard state/validation helpers.  This module intentionally has
// no Vue or Element Plus dependency so invalid/expiry/stale behavior stays a
// mechanically testable contract shared by the component and Node tests.

const TERMINAL = new Set(["answered", "expired", "superseded"]);
const MAX_TEXT = 4000;
const RFC3339_MICROS = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.(\d{1,6}))?(?:Z|[+-]\d{2}:\d{2})$/;

function timestampMicros(value) {
  if (typeof value !== "string") return null;
  const match = RFC3339_MICROS.exec(value);
  const epochMs = Date.parse(value);
  if (!match || !Number.isFinite(epochMs)) return null;
  const microsWithinSecond = Number((match[1] || "").padEnd(6, "0") || "0");
  return BigInt(Math.trunc(epochMs)) * 1_000n + BigInt(microsWithinSecond % 1_000);
}

export function createSecureSubmissionId(cryptoLike = globalThis.crypto) {
  if (typeof cryptoLike?.randomUUID === "function") {
    return cryptoLike.randomUUID();
  }
  if (typeof cryptoLike?.getRandomValues !== "function") {
    throw new Error("secure random source unavailable");
  }

  const bytes = new Uint8Array(16);
  cryptoLike.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function effectiveQuestionStatus(question, nowMs = Date.now()) {
  if (!question || typeof question !== "object") return "unknown";
  if (TERMINAL.has(question.status)) return question.status;
  if (question.status !== "pending") return "unknown";
  const expires = timestampMicros(question.expires_at);
  if (expires === null || !Number.isFinite(nowMs)) return "unknown";
  const now = BigInt(Math.floor(nowMs * 1_000));
  return now >= expires ? "expired" : "pending";
}

export function hasPendingConversationQuestion(messages, nowMs = Date.now()) {
  if (!Array.isArray(messages)) return false;
  return messages.some(
    (message) => effectiveQuestionStatus(message?.question, nowMs) === "pending",
  );
}

function invalid(error) {
  return { ok: false, payload: null, error };
}

export function validateQuestionSubmission(question, draft, options = {}) {
  if (options.stale === true) return invalid("问题状态尚未重新核对，请恢复连接后再提交");
  const status = effectiveQuestionStatus(question, options.nowMs ?? Date.now());
  if (status !== "pending") {
    const labels = {
      answered: "这个问题已经回答，不能重复提交",
      expired: "这个问题已经过期",
      superseded: "这个问题已被后续对话替代",
      unknown: "无法确认问题状态，已停止提交",
    };
    return invalid(labels[status] || labels.unknown);
  }
  if (!draft || typeof draft !== "object") return invalid("请选择或填写回答");

  if (question.kind === "single_choice") {
    if (!Array.isArray(question.options) || question.options.length < 2) {
      return invalid("问题选项合同无效，已停止提交");
    }
    if (draft.mode === "option") {
      const optionId = typeof draft.optionId === "string" ? draft.optionId : "";
      if (!question.options.some((option) => option && option.id === optionId)) {
        return invalid("请选择一个有效选项");
      }
      return { ok: true, payload: { kind: "option", option_id: optionId }, error: "" };
    }
    if (draft.mode !== "text") return invalid("请选择一个选项或使用自定义回答");
  } else if (question.kind === "free_text") {
    if (!Array.isArray(question.options) || question.options.length !== 0) {
      return invalid("自由文本问题合同无效，已停止提交");
    }
    if (draft.mode !== "text") return invalid("请填写回答");
  } else {
    return invalid("未知的问题类型，已停止提交");
  }

  const text = typeof draft.text === "string" ? draft.text.trim() : "";
  if (!text) return invalid("回答不能为空");
  if (text.length > MAX_TEXT) return invalid(`回答不能超过 ${MAX_TEXT} 字`);
  return { ok: true, payload: { kind: "text", text }, error: "" };
}

export function mergeQuestionSnapshot(current, incoming) {
  if (!incoming || typeof incoming !== "object") return current;
  if (!current || typeof current !== "object" || current.id !== incoming.id) return incoming;
  const currentRevision = Number.isInteger(current.revision) ? current.revision : -1;
  const incomingRevision = Number.isInteger(incoming.revision) ? incoming.revision : -1;
  if (incomingRevision < currentRevision) return current;
  if (incomingRevision === currentRevision && TERMINAL.has(current.status)) return current;
  return incoming;
}

export function questionAnswerLabel(question) {
  const payload = question?.answer?.payload;
  if (question?.status !== "answered" || !payload) return "";
  if (payload.kind === "text") return typeof payload.text === "string" ? payload.text : "";
  if (payload.kind !== "option" || !Array.isArray(question.options)) return "";
  const option = question.options.find((item) => item && item.id === payload.option_id);
  return option && typeof option.label === "string" ? option.label : "";
}
