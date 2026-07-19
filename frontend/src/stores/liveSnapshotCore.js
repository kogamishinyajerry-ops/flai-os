export const TASK_LIVE_SNAPSHOT_SCHEMA = "task-live-snapshot/v1";

const resnapshot = (reason) => ({ action: "resnapshot", reason });

const CONNECTION_ERROR_LABELS = Object.freeze({
  manual_resnapshot: "",
  unsupported_schema: "快照协议版本不受支持",
  server_resync_required: "服务端要求重新核对完整快照",
  invalid_envelope: "快照结构无效",
  task_mismatch: "快照任务身份不一致",
  invalid_cursor: "事件游标无效",
  base_mismatch: "本地事件锚点与服务端不一致",
  invalid_events: "事件列表结构无效",
  event_gap: "检测到事件序列缺口",
  duplicate_event: "检测到重复事件",
  cursor_mismatch: "快照尾游标不一致",
  anchor_mismatch: "事件锚点已变化",
  cursor_ahead: "本地游标超出当前事件流",
});

function autoRetryError(error) {
  const raw = String(error || "");
  const projected = Object.hasOwn(CONNECTION_ERROR_LABELS, raw)
    ? CONNECTION_ERROR_LABELS[raw]
    : raw;
  return projected.replace(/[，,]\s*请稍后重试[。.]?$/, "");
}

function validCursor(cursor) {
  if (!cursor || !Number.isSafeInteger(cursor.sequence) || cursor.sequence < 0) return false;
  if (cursor.sequence === 0) return cursor.event_id === null;
  return typeof cursor.event_id === "string" && cursor.event_id.length > 0;
}

export function initialResyncClock() {
  return { requested: 1, applied: 0 };
}

export function requestFullSnapshot(clock) {
  return { requested: clock.requested + 1, applied: clock.applied };
}

export function isSnapshotRequestCurrent(clock, generation) {
  return generation === clock.requested;
}

export function planTaskSnapshotRequest(clock, cursor) {
  const full = clock.applied < clock.requested;
  return {
    full,
    generation: clock.requested,
    base: full ? { sequence: 0, eventId: null } : cursor,
  };
}

export function acknowledgeFullSnapshot(clock, generation) {
  return {
    requested: clock.requested,
    applied: Math.max(clock.applied, Math.min(generation, clock.requested)),
  };
}

/**
 * Validate one authoritative task snapshot without mutating local state.
 * A caller may apply the returned replacement/delta only when this function
 * returns ``replace`` or ``append``; every malformed or discontinuous input
 * becomes a mandatory full resnapshot.
 */
export function evaluateTaskLiveSnapshot(current, payload) {
  if (!payload || payload.schema_version !== TASK_LIVE_SNAPSHOT_SCHEMA) {
    return resnapshot("unsupported_schema");
  }
  if (payload.resync_required === true) {
    return resnapshot(payload.resync_reason || "server_resync_required");
  }
  if (payload.resync_required !== false || !payload.task) {
    return resnapshot("invalid_envelope");
  }
  if (
    typeof current?.taskId === "string"
    && (payload.task.id !== current.taskId)
  ) {
    return resnapshot("task_mismatch");
  }
  if (!validCursor(payload.base) || !validCursor(payload.cursor)) {
    return resnapshot("invalid_cursor");
  }
  const currentEventId = current?.eventId ?? null;
  if (
    payload.base.sequence !== current?.sequence
    || payload.base.event_id !== currentEventId
  ) {
    return resnapshot("base_mismatch");
  }
  if (!Array.isArray(payload.events)) return resnapshot("invalid_events");

  let expected = current.sequence + 1;
  let finalEventId = currentEventId;
  const events = [];
  const seenEventIds = new Set(current?.eventIds || []);
  for (const item of payload.events) {
    if (
      !item
      || item.sequence !== expected
      || !item.event
      || typeof item.event.event_id !== "string"
      || item.event.event_id.length === 0
    ) {
      return resnapshot("event_gap");
    }
    if (
      (typeof current?.taskId === "string" && item.event.task_id !== current.taskId)
      || item.event.task_id !== payload.task.id
    ) {
      return resnapshot("task_mismatch");
    }
    if (seenEventIds.has(item.event.event_id)) return resnapshot("duplicate_event");
    seenEventIds.add(item.event.event_id);
    events.push(item.event);
    finalEventId = item.event.event_id;
    expected += 1;
  }

  const finalSequence = expected - 1;
  if (
    payload.cursor.sequence !== finalSequence
    || payload.cursor.event_id !== finalEventId
  ) {
    return resnapshot("cursor_mismatch");
  }
  return {
    action: current.sequence === 0 ? "replace" : "append",
    task: payload.task,
    events,
    cursor: { sequence: finalSequence, eventId: finalEventId },
  };
}

export function nextLiveConnection(previous, event) {
  const lastSuccessAt = previous?.lastSuccessAt ?? null;
  if (event?.type === "success") {
    return {
      connection: "connected",
      lastSuccessAt: event.at,
      stale: false,
      resyncing: false,
      error: "",
    };
  }
  if (event?.type === "resync") {
    return {
      connection: "disconnected",
      lastSuccessAt,
      stale: true,
      resyncing: true,
      error: event.error || "event_gap",
    };
  }
  if (event?.type === "failure") {
    return {
      connection: "disconnected",
      lastSuccessAt,
      stale: true,
      resyncing: false,
      error: event.error || "加载失败",
    };
  }
  return {
    connection: previous?.connection || "idle",
    lastSuccessAt,
    stale: previous?.stale !== false,
    resyncing: previous?.resyncing === true,
    error: previous?.error || "",
  };
}

export function describeLiveConnection(state) {
  if (
    state?.connection !== "disconnected"
    && state?.resyncing !== true
  ) return null;

  if (
    state?.resyncing === true
    && state?.error === "manual_resnapshot"
    && state?.loaded === true
    && state?.lastSuccessAt !== null
    && state?.lastSuccessAt !== undefined
  ) {
    return {
      kind: "resync",
      title: "正在重新核对完整快照",
      detail: "已按你的操作发起完整核对；完成前保留上次成功内容。",
      error: "",
      lastSuccessAt: state.lastSuccessAt,
    };
  }
  if (state?.resyncing === true && state?.error === "manual_resnapshot") {
    return {
      kind: "resync",
      title: "正在重新核对完整快照",
      detail: "已按你的操作发起完整核对；尚无可显示的真实快照。",
      error: "",
      lastSuccessAt: null,
    };
  }

  if (
    state?.resyncing === true
    && state?.loaded === true
    && state?.lastSuccessAt !== null
    && state?.lastSuccessAt !== undefined
  ) {
    return {
      kind: "resync",
      title: "正在重新核对完整快照",
      detail: "可疑增量已丢弃；核对完成前仅保留上次成功内容。",
      error: autoRetryError(state?.error),
      lastSuccessAt: state?.lastSuccessAt ?? null,
    };
  }
  if (state?.resyncing === true) {
    return {
      kind: "resync",
      title: "正在重新核对完整快照",
      detail: "可疑增量已丢弃；尚无可显示的真实快照。",
      error: autoRetryError(state?.error),
      lastSuccessAt: null,
    };
  }
  if (state?.loaded === true && state?.lastSuccessAt !== null && state?.lastSuccessAt !== undefined) {
    return {
      kind: "stale",
      title: "当前显示上次成功快照",
      detail: "连接恢复后将先重新核对权威数据，再恢复同步；系统会自动重试。",
      error: autoRetryError(state?.error),
      lastSuccessAt: state.lastSuccessAt,
    };
  }
  return {
    kind: "cold",
    title: "当前无法同步",
    detail: "尚未取得可显示的真实快照；系统会自动重试。",
    error: autoRetryError(state?.error),
    lastSuccessAt: null,
  };
}
