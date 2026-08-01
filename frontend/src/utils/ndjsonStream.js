const DEFAULT_MAX_LINE_CHARS = 1_000_000;

export const STREAM_NOT_PERSISTED_TITLE = "流式中断 · 本轮未保存";
export const STREAM_PERSISTENCE_UNKNOWN_TITLE = "流式中断 · 保存状态待核";

/**
 * 会话流失败后的恢复策略。
 *
 * 只有服务端 error 事件明确给出 persisted:false，客户端才能断言零落库并
 * 自动还稿。网络中断、超时、畸形 done 或提前 EOF 都可能发生在 COMMIT 之后，
 * 因此一律保留本地轮次、禁止自动还稿，并要求刷新会话核对。
 */
export function conversationStreamFailurePolicy(error, { hasPartial = false } = {}) {
  const explicitlyNotPersisted = error && error.persisted === false;
  if (explicitlyNotPersisted) {
    return {
      title: STREAM_NOT_PERSISTED_TITLE,
      persisted: false,
      restoreDraft: true,
      discardOptimisticUser: !hasPartial,
      retainUnconfirmedTurn: false,
      canRetry: true,
      reconciliationRequired: false,
    };
  }
  return {
    title: STREAM_PERSISTENCE_UNKNOWN_TITLE,
    persisted: null,
    restoreDraft: false,
    discardOptimisticUser: false,
    retainUnconfirmedTurn: true,
    canRetry: false,
    reconciliationRequired: true,
  };
}

export function conversationInteractionPolicy({
  sending = false,
  restoring = false,
  reconciliationRequired = false,
} = {}) {
  const reconciliationLocked = reconciliationRequired === true;
  const busy = sending === true || restoring === true;
  const locked = reconciliationLocked || busy;
  return {
    locked,
    reconciliationLocked,
    canSend: !locked,
    canAttach: !locked,
  };
}

export function reconciliationLockAfterRefresh({
  required = false,
  succeeded = false,
} = {}) {
  if (required !== true) return false;
  return succeeded !== true;
}

function parseEventLine(line, onEvent) {
  if (!line.trim()) return;

  let event;
  try {
    event = JSON.parse(line);
  } catch {
    throw new Error("流式响应不是合法 NDJSON");
  }

  if (
    event === null ||
    typeof event !== "object" ||
    Array.isArray(event) ||
    typeof event.type !== "string"
  ) {
    throw new Error("流式响应不是合法 NDJSON 事件");
  }

  onEvent(event);
}

/**
 * 增量 NDJSON 解析器。
 *
 * fetch 的 ReadableStream 分片边界与 JSON 行边界无关；这里保留半行缓冲，
 * 只在收到换行或 finish() 时解析完整事件。单行上限防止损坏的上游响应让
 * 浏览器持续累积无界字符串。
 */
export function createNdjsonParser(
  onEvent,
  { maxLineChars = DEFAULT_MAX_LINE_CHARS } = {},
) {
  if (typeof onEvent !== "function") {
    throw new TypeError("onEvent 必须是函数");
  }
  if (!Number.isSafeInteger(maxLineChars) || maxLineChars <= 0) {
    throw new TypeError("maxLineChars 必须是正整数");
  }

  let buffer = "";

  function assertBounded(value) {
    if (value.length > maxLineChars) {
      throw new Error("流式响应单行超过上限");
    }
  }

  return {
    push(chunk) {
      if (typeof chunk !== "string") {
        throw new TypeError("NDJSON 分片必须是字符串");
      }

      buffer += chunk;
      let newline = buffer.indexOf("\n");
      while (newline !== -1) {
        let line = buffer.slice(0, newline);
        buffer = buffer.slice(newline + 1);
        if (line.endsWith("\r")) line = line.slice(0, -1);
        assertBounded(line);
        parseEventLine(line, onEvent);
        newline = buffer.indexOf("\n");
      }
      assertBounded(buffer);
    },

    finish() {
      if (buffer.endsWith("\r")) buffer = buffer.slice(0, -1);
      assertBounded(buffer);
      parseEventLine(buffer, onEvent);
      buffer = "";
    },
  };
}
