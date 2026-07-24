// Workspace Shell 视图模型：纯函数、无 I/O、无 DOM。
// 输入是 fixtures.js 给出的合成观察投影快照，输出是界面可渲染的
// glyph / motion / 信任槽 / Focus Surface / 徽标 / 队列描述。
// 信任不变量在此层再次 clamp：
//   - motion 只在 fresh 的活动观察（projector motion=true）且信任槽为
//     active 时成立；waiting_review / completed / failed / cancelled /
//     stale / evidence-missing / permission-denied / UNKNOWN 一律静止；
//   - completed 只用中性 terminal，绝不给绿；
//   - 合成夹具永不进入 real（绿）或 sign（teal）槽；
//   - 缺口态（mode=unknown）不暴露任何此前敏感的 Focus 预览。

// 六类动态动作 glyph + 静态 glyph。合同 action → glyph 的映射是本层的
// 独立重表达，不复制任何外部产品的图标或命名。
const GLYPH_BY_ACTION = Object.freeze({
  inspect: "search",
  receive: "read",
  guard: "parse",
  rewrite: "compute",
  map: "compute",
  render: "render",
  hold: "waiting-review",
  deny: "failed",
  signal: "unknown",
  idle: "idle",
});

export const GLYPH_LABELS = Object.freeze({
  search: "检索",
  read: "读取",
  parse: "解析",
  compute: "计算",
  render: "渲染",
  "waiting-review": "等待真人审阅",
  failed: "失败停止",
  cancelled: "已停止",
  unknown: "状态未知",
  idle: "待命",
});

export function glyphFor(action, mode) {
  if (action === "stop") return mode === "stopped" ? "cancelled" : "failed";
  return GLYPH_BY_ACTION[action] || "unknown";
}

// 信任槽五值：active / attention / terminal / fail / unverified。
// 没有 real 槽也没有 sign 槽：合成原型在任何路径都不可达绿与 teal。
export function trustSlotFor(snapshot) {
  if (snapshot.mode === "unknown") return "unverified";
  if (snapshot.mode === "failed") return "fail";
  if (snapshot.mode === "stopped") return "terminal";
  if (snapshot.mode === "preview") return "terminal";
  if (snapshot.mode === "attention") return "attention";
  return "active";
}

export function motionFor(snapshot) {
  return snapshot.motion === true && trustSlotFor(snapshot) === "active";
}

// 显示形态徽标。即使请求 REAL 形态，source 仍是 synthetic-fixture，
// 文案明示“非真实见证”，data-slot 永远不是 real。
// fail-closed（mode=unknown）优先于形态字段：一律 UNKNOWN 未核徽标。
export function badgeFor(snapshot, requestedForm) {
  if (snapshot.mode === "unknown") {
    return {
      form: "UNKNOWN",
      slot: "unverified",
      sourceKind: "synthetic-fixture",
      text: "合成夹具 · UNKNOWN · 未核，非真实见证",
    };
  }
  const form = LEGAL_FORM.has(requestedForm) ? requestedForm : "UNKNOWN";
  if (form === "UNKNOWN" || snapshot.source !== "synthetic-fixture") {
    // 本原型只消费合成夹具；任何非合成 source 都按未核处理（fail closed）。
    return {
      form: "UNKNOWN",
      slot: "unverified",
      sourceKind: "synthetic-fixture",
      text: "合成夹具 · UNKNOWN · 未核，非真实见证",
    };
  }
  return {
    form,
    slot: "synthetic",
    sourceKind: "synthetic-fixture",
    text: `合成夹具 · ${form} 显示形态 · 非真实见证`,
  };
}
const LEGAL_FORM = new Set(["REAL", "MOCK", "TEST"]);

// Focus Surface 选择：右栏始终承载“此刻最值得看”的对象；
// 缺口态只给公开原因码，不复用、不残留任何产物预览字段。
export function focusFor(snapshot, scenario, state, stateFacts) {
  const art = scenario.artifact;
  const witnessRef = (snapshot.evidenceRefs || []).find((ref) => (
    ref.startsWith("reality-witness:")
  )) || "无可用见证引用";
  const artifactLines = [
    `合成摘要：SHA-256 ${art.digest.slice(0, 16)}…`,
    `密级标注：${art.classification}（合成样例）`,
    `来源见证：${witnessRef}`,
  ];
  if (snapshot.mode === "unknown") {
    return {
      kind: "gap",
      title: "当前没有可验证的对象",
      reasonCode: snapshot.reasonCode,
      lines: [snapshot.detail, "缺口状态不保留此前的产物预览；等待可靠观察恢复。"],
    };
  }
  if (state === "permission-denied") {
    return {
      kind: "denied",
      title: scenario.object,
      reasonCode: stateFacts?.publicCode || "PERMISSION_DENIED_SYNTHETIC",
      lines: [
        `被拒对象密级：${art.classification}（合成样例）`,
        "执行已在权限边界停止，不会悄悄降级继续。",
        "可申请权限，或改用已获权的工作对象。",
      ],
    };
  }
  if (snapshot.mode === "failed") {
    return {
      kind: "exception",
      title: "最后可信对象",
      reasonCode: stateFacts?.publicCode || "EXECUTION_FAILED_SYNTHETIC",
      lines: [
        snapshot.preview.title,
        `影响：${snapshot.title}。`,
        "可在 Composer 修正指令后重新提交目标。",
      ],
    };
  }
  if (snapshot.mode === "stopped") {
    return {
      kind: "stopped",
      title: "停止点与保留产物",
      reasonCode: stateFacts?.publicCode || "EXECUTION_CANCELLED_SYNTHETIC",
      lines: [
        snapshot.preview.title,
        "中性终止：这不是失败；已有只读对象仍可检查。",
      ],
    };
  }
  if (state === "waiting_review") {
    return {
      kind: "diff",
      title: `${art.filename}（对照差异稿）`,
      lines: [
        "逐段对照：新增 6 段、改写 5 段、删除 1 段（合成计数）。",
        ...artifactLines,
        "系统不会自动签发；请检查后由真人决定。",
      ],
    };
  }
  if (state === "completed") {
    return {
      kind: "artifact",
      title: art.filename,
      lines: [
        ...artifactLines,
        "任务终态与产物引用一致；正式签发仍只由真人完成。",
      ],
    };
  }
  // running：正在形成的预览 / 当前步骤运行输出
  return {
    kind: "runtime",
    title: snapshot.preview.title,
    lines: [
      snapshot.preview.caption,
      ...artifactLines,
      `当前步骤输出：${snapshot.stepLabel}（合成样例）。`,
    ],
  };
}

// 紧凑执行历史：只取投影可证明的字段（时间、动作、标题）。
export function historyFor(events) {
  return events.map((event) => ({
    seq: event.sequence,
    observedAt: event.observedAt,
    glyph: glyphFor(event.action, event.kind),
    title: event.title,
    stepLabel: event.step?.label || "",
  }));
}

// 命令队列：每条补充指令是独立条目，稳定 ID、保序、各自 receipt；
// 绝不把多条指令拼接成一个不可审计的字符串。
// synthetic receipt 只表示“已受理/已排队”，不代表任务完成。
export function createCommandQueue() {
  return { nextSeq: 1, items: [] };
}

export function appendInstruction(queue, text) {
  const trimmed = typeof text === "string" ? text.trim() : "";
  if (!trimmed) return null;
  const seq = queue.nextSeq;
  const item = Object.freeze({
    id: `cmd-${seq}`,
    seq,
    kind: "append_instruction",
    idempotencyKey: `idem-cmd-${seq}`,
    text: trimmed,
    receipt: Object.freeze({
      status: "ACCEPTED",
      receiptRef: `synthetic-receipt:cmd-${seq}`,
      note: "已受理并入队；仅表示接受，不代表完成",
    }),
  });
  queue.nextSeq += 1;
  queue.items.push(item);
  return item;
}

export function resolveView(fixture) {
  const { snapshot, scenario, state, stateFacts, form, events } = fixture;
  const trustSlot = trustSlotFor(snapshot);
  return {
    glyph: glyphFor(snapshot.action, snapshot.mode),
    motion: motionFor(snapshot),
    trustSlot,
    badge: badgeFor(snapshot, form),
    focus: focusFor(snapshot, scenario, state, stateFacts),
    history: historyFor(events),
    title: snapshot.title,
    detail: snapshot.detail,
    stepLabel: snapshot.stepLabel,
    overline: snapshot.overline,
    reasonCode: snapshot.reasonCode,
  };
}
