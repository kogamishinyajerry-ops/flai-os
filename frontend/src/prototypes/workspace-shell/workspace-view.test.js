// Workspace Shell 视图模型单元测试（SYNTHETIC ONLY）。
// 确定性矩阵：3 工作流 × 8 状态 × 4 显示形态 = 96 case，
// 外加 stale 过期叠加态、命令队列与 glyph 覆盖。
import test from "node:test";
import assert from "node:assert/strict";
import {
  DISPLAY_FORMS,
  WORKFLOWS,
  WORKSPACE_STATES,
  getWorkspaceFixture,
  listMatrixKeys,
} from "./fixtures.js";
import {
  appendInstruction,
  createCommandQueue,
  glyphFor,
  resolveView,
} from "./workspace-view.js";

const STATE_EXPECT = Object.freeze({
  running: { motion: true, trust: "active", focus: "runtime" },
  waiting_review: { motion: false, trust: "attention", focus: "diff", glyph: "waiting-review" },
  completed: { motion: false, trust: "terminal", focus: "artifact", glyph: "render" },
  failed: {
    motion: false, trust: "fail", focus: "exception", glyph: "failed",
    reasonCode: "EXECUTION_FAILED_SYNTHETIC",
  },
  cancelled: {
    motion: false, trust: "terminal", focus: "stopped", glyph: "cancelled",
    reasonCode: "EXECUTION_CANCELLED_SYNTHETIC",
  },
  "evidence-missing": {
    motion: false, trust: "unverified", focus: "gap", glyph: "unknown",
    reasonCode: "observation_missing",
  },
  "permission-denied": {
    motion: false, trust: "fail", focus: "denied", glyph: "failed",
    reasonCode: "PERMISSION_DENIED_SYNTHETIC",
  },
  "observation-invalid": {
    motion: false, trust: "unverified", focus: "gap", glyph: "unknown",
    reasonCode: "observation_invalid",
  },
});
const RUNNING_GLYPH = Object.freeze({ docx: "compute", meeting: "search", cfd: "parse" });
// fail-closed 状态：即使请求 REAL/MOCK/TEST 形态，徽标一律 UNKNOWN 未核。
const FAIL_CLOSED_STATES = new Set(["evidence-missing", "observation-invalid"]);

test("矩阵键精确为 3 × 8 × 4 = 96", () => {
  const keys = listMatrixKeys();
  assert.equal(keys.length, 96);
  assert.equal(new Set(keys).size, 96);
  assert.equal(Object.keys(WORKFLOWS).length, 3);
  assert.equal(WORKSPACE_STATES.length, 8);
  assert.equal(DISPLAY_FORMS.length, 4);
});

for (const key of listMatrixKeys()) {
  test(`矩阵 ${key}`, () => {
    const [workflow, state, form] = key.split(/[:@]/);
    const view = resolveView(getWorkspaceFixture(key));
    const expect = STATE_EXPECT[state];

    if (form === "UNKNOWN") {
      // UNKNOWN 不是合法 execution reality：任何状态下都派生 fail-closed 缺口。
      assert.equal(view.badge.form, "UNKNOWN");
      assert.equal(view.badge.slot, "unverified");
      assert.equal(view.focus.kind, "gap");
      assert.equal(view.motion, false);
      assert.equal(view.trustSlot, "unverified");
    } else {
      assert.equal(view.motion, expect.motion, "motion");
      assert.equal(view.trustSlot, expect.trust, "trustSlot");
      assert.equal(view.focus.kind, expect.focus, "focus.kind");
      const wantGlyph = state === "running" ? RUNNING_GLYPH[workflow] : expect.glyph;
      assert.equal(view.glyph, wantGlyph, "glyph");
      if (FAIL_CLOSED_STATES.has(state)) {
        assert.equal(view.badge.form, "UNKNOWN", "fail-closed 优先于形态字段");
        assert.equal(view.badge.slot, "unverified");
      } else {
        assert.equal(view.badge.form, form);
        assert.equal(view.badge.slot, "synthetic");
      }
    }
    if (expect.reasonCode && form !== "UNKNOWN") {
      assert.equal(view.focus.reasonCode ?? view.reasonCode, expect.reasonCode, "reasonCode");
    }
    // 信任不变量（全 96 case）：合成夹具永不进 real/sign 槽；
    // completed 永远中性；徽标永远标注合成与非真实见证。
    assert.notEqual(view.badge.slot, "real");
    assert.notEqual(view.badge.slot, "sign");
    assert.notEqual(view.trustSlot, "real");
    assert.notEqual(view.trustSlot, "sign");
    assert.equal(view.badge.sourceKind, "synthetic-fixture");
    assert.match(view.badge.text, /合成夹具/);
    assert.match(view.badge.text, /非真实见证/);
    if (state === "completed" && form !== "UNKNOWN") assert.equal(view.trustSlot, "terminal");
    // 缺口态不得残留敏感 Focus 预览（无产物摘要/见证行）。
    if (view.focus.kind === "gap") {
      const focusText = [view.focus.title, ...view.focus.lines].join(" ");
      assert.doesNotMatch(focusText, /SHA-256/);
      assert.doesNotMatch(focusText, /来源见证/);
    }
  });
}

test("stale 叠加态：docx:running 观察过期 → 停动画 + UNKNOWN 未核 + 清空敏感预览", () => {
  const view = resolveView(getWorkspaceFixture("docx:stale@REAL"));
  assert.equal(view.reasonCode, "observation_stale");
  assert.equal(view.motion, false);
  assert.equal(view.trustSlot, "unverified");
  assert.equal(view.badge.form, "UNKNOWN");
  assert.equal(view.badge.slot, "unverified");
  assert.equal(view.focus.kind, "gap");
  const focusText = [view.focus.title, ...view.focus.lines].join(" ");
  assert.doesNotMatch(focusText, /SHA-256/);
  assert.doesNotMatch(focusText, /来源见证/);
});

test("非法 fixture 输入直接抛错（不静默回退 REAL）", () => {
  assert.throws(() => getWorkspaceFixture("docx:running@FAKE"));
  assert.throws(() => getWorkspaceFixture("docx:hover@REAL"));
  assert.throws(() => getWorkspaceFixture("ppt:running@REAL"));
});

test("六类动态 glyph 均可由合成观察驱动", () => {
  assert.equal(glyphFor("inspect", "working"), "search");
  assert.equal(glyphFor("receive", "receiving"), "read");
  assert.equal(glyphFor("guard", "validating"), "parse");
  assert.equal(glyphFor("rewrite", "working"), "compute");
  assert.equal(glyphFor("map", "working"), "compute");
  assert.equal(glyphFor("render", "preview"), "render");
  assert.equal(glyphFor("hold", "attention"), "waiting-review");
  const running = resolveView(getWorkspaceFixture("docx:running@REAL"));
  const historyGlyphs = running.history.map((item) => item.glyph);
  assert.ok(historyGlyphs.includes("read"));
  assert.ok(historyGlyphs.includes("parse"));
});

test("命令队列：独立 ID、保序、各自 receipt，绝不拼接", () => {
  const queue = createCommandQueue();
  const first = appendInstruction(queue, "把第三节改写成更正式的措辞");
  const second = appendInstruction(queue, "补充一张对照表");
  const third = appendInstruction(queue, "检查引用格式");
  assert.deepEqual(
    queue.items.map((item) => item.id),
    ["cmd-1", "cmd-2", "cmd-3"],
  );
  assert.deepEqual(
    queue.items.map((item) => item.seq),
    [1, 2, 3],
  );
  assert.equal(first.text, "把第三节改写成更正式的措辞");
  assert.equal(second.text, "补充一张对照表");
  assert.equal(third.text, "检查引用格式");
  for (const item of queue.items) {
    assert.equal(item.kind, "append_instruction");
    assert.equal(item.receipt.status, "ACCEPTED");
    assert.match(item.receipt.note, /不代表完成/);
    assert.match(item.receipt.receiptRef, /^synthetic-receipt:cmd-\d+$/);
    assert.match(item.idempotencyKey, /^idem-cmd-\d+$/);
  }
  // 三条指令保持独立字符串，从未被拼接成一个 unauditable prompt。
  assert.equal(queue.items.length, 3);
  assert.ok(queue.items.every((item) => !item.text.includes("\n\n---")));
});

test("命令队列：空白指令不入队", () => {
  const queue = createCommandQueue();
  assert.equal(appendInstruction(queue, "   "), null);
  assert.equal(appendInstruction(queue, ""), null);
  assert.equal(queue.items.length, 0);
  assert.equal(queue.nextSeq, 1);
});
