// Stage C 原型合成夹具的状态/合同测试。夹具只驱动 UI，不证明任何真实执行。
import assert from "node:assert/strict";
import test from "node:test";

import { OBSERVER_CONTRACT_VERSION } from "./observer-contract.js";
import {
  FIXTURE_REALITIES,
  FIXTURE_REALITY_FORMS,
  FIXTURE_SCENARIOS,
  FIXTURE_STATES,
  REQUIRED_STATES,
  getFixtureSnapshot,
  listFixtureKeys,
} from "./fixtures.js";

test("fixtures: 覆盖三种场景与全部要求状态", () => {
  assert.deepEqual(Object.keys(FIXTURE_SCENARIOS).sort(), ["cfd", "docx", "meeting"]);
  assert.equal(REQUIRED_STATES.length, 9);
  for (const state of REQUIRED_STATES) {
    assert.ok(FIXTURE_STATES.includes(state), `missing state ${state}`);
  }
  const keys = listFixtureKeys();
  for (const scene of ["docx", "meeting", "cfd"]) {
    for (const state of FIXTURE_STATES) {
      assert.ok(keys.includes(`${scene}:${state}`), `missing fixture ${scene}:${state}`);
    }
  }
});

test("fixtures: 活动状态才有 motion，且来自投影器而非自报", () => {
  for (const scene of ["docx", "meeting", "cfd"]) {
    const snap = getFixtureSnapshot(`${scene}:running`);
    assert.equal(snap.reasonCode, "observed");
    assert.equal(snap.motion, true);
    assert.ok(["working", "scanning"].includes(snap.mode));
  }
  const guard = getFixtureSnapshot("cfd:validating");
  assert.equal(guard.action, "guard");
  assert.equal(guard.motion, true);
});

test("fixtures: 终态与等待真人一律停止动画", () => {
  for (const scene of ["docx", "meeting", "cfd"]) {
    for (const state of ["waiting_review", "completed", "failed", "cancelled"]) {
      const snap = getFixtureSnapshot(`${scene}:${state}`);
      assert.equal(snap.motion, false, `${scene}:${state} must not animate`);
      assert.equal(snap.reasonCode, "observed");
    }
  }
});

test("fixtures: completed 是终态事实，不携带成功签发语义", () => {
  const snap = getFixtureSnapshot("docx:completed");
  assert.equal(snap.mode, "preview");
  assert.equal(snap.action, "render");
  assert.ok(!/已签发|签发成功|进展显著|可直接交付/.test(snap.title + snap.detail));
});

test("fixtures: evidence-missing / unknown / stale 全部 fail-closed", () => {
  const missing = getFixtureSnapshot("docx:evidence-missing");
  assert.equal(missing.mode, "unknown");
  assert.equal(missing.motion, false);
  assert.equal(missing.reality, "UNKNOWN");
  assert.equal(missing.reasonCode, "observation_invalid");

  const unknown = getFixtureSnapshot("meeting:unknown");
  assert.equal(unknown.mode, "unknown");
  assert.equal(unknown.motion, false);
  assert.equal(unknown.reasonCode, "observation_missing");

  const stale = getFixtureSnapshot("cfd:stale");
  assert.equal(stale.mode, "unknown");
  assert.equal(stale.motion, false);
  assert.equal(stale.reasonCode, "observation_stale");
});

test("fixtures: permission-denied 是权限边界而非普通失败", () => {
  const snap = getFixtureSnapshot("meeting:permission-denied");
  assert.equal(snap.mode, "failed");
  assert.equal(snap.action, "deny");
  assert.equal(snap.motion, false);
});

test("fixtures: 所有观察态默认 REAL 形态（无隐式 MOCK 特例）", () => {
  // @3 P2 修复：permission-denied 不再隐式默认 MOCK；同源夹具默认形态一致。
  for (const scene of ["docx", "meeting", "cfd"]) {
    for (const state of ["running", "waiting_review", "completed", "failed", "cancelled", "permission-denied"]) {
      const snap = getFixtureSnapshot(`${scene}:${state}`);
      assert.equal(snap.reality, "REAL", `${scene}:${state} 默认形态必须是 REAL`);
    }
  }
  // 显式覆盖仍然生效
  assert.equal(getFixtureSnapshot("meeting:permission-denied@MOCK").reality, "MOCK");
});

test("fixtures: 快照字段满足合同形状且不含虚构百分比", () => {
  for (const key of listFixtureKeys()) {
    const snap = getFixtureSnapshot(key);
    assert.equal(snap.contractVersion, OBSERVER_CONTRACT_VERSION);
    assert.ok(typeof snap.title === "string" && snap.title.length > 0);
    assert.ok(!snap.stepLabel.includes("%"), `${key} stepLabel 禁止百分比`);
    for (const field of ["kind", "title", "caption", "primary", "secondary"]) {
      assert.ok(
        typeof snap.preview[field] === "string" && snap.preview[field].length > 0,
        `${key} preview.${field} 缺失`,
      );
    }
  }
});

test("fixtures: 已观察状态带 reality-witness 证据且 reality 单一", () => {
  for (const scene of ["docx", "meeting", "cfd"]) {
    const snap = getFixtureSnapshot(`${scene}:running`);
    assert.ok(["REAL", "MOCK", "TEST"].includes(snap.reality));
    assert.ok(
      snap.evidenceRefs.some((ref) => ref.startsWith(`reality-witness:${snap.reality}:`)),
      `${scene}:running 缺少 reality-witness 证据`,
    );
  }
});

test("fixtures: REAL / MOCK / TEST / UNKNOWN 四种形态明确区分", () => {
  assert.deepEqual([...FIXTURE_REALITIES], ["REAL", "MOCK", "TEST"]);
  assert.deepEqual([...FIXTURE_REALITY_FORMS], ["REAL", "MOCK", "TEST", "UNKNOWN"]);
  for (const reality of FIXTURE_REALITIES) {
    const snap = getFixtureSnapshot(`docx:running@${reality}`);
    assert.equal(snap.reality, reality, `running@${reality} reality 不匹配`);
    assert.equal(snap.source, "synthetic-fixture");
    assert.ok(
      snap.evidenceRefs.some((ref) => ref.startsWith(`reality-witness:${reality}:`)),
      `running@${reality} 缺少对应 reality-witness`,
    );
  }
  // UNKNOWN 形态：不是可观察形态（observer 合同只接受 REAL/MOCK/TEST），
  // 只能由 fail-closed 快照给出（reality=UNKNOWN，mode=unknown）；
  // stale 保留最后观察的 reality 字段但 mode=unknown（停动画、不携带见证语义），
  // UI 层对 mode=unknown 一律压到 UNKNOWN 未核徽标（见 e2e 四形态 DOM 矩阵）。
  for (const state of ["evidence-missing", "unknown"]) {
    const snap = getFixtureSnapshot(`docx:${state}`);
    assert.equal(snap.reality, "UNKNOWN", `${state} 必须 fail-closed 到 UNKNOWN`);
    assert.equal(snap.mode, "unknown");
  }
  const stale = getFixtureSnapshot("docx:stale");
  assert.equal(stale.mode, "unknown");
  assert.equal(stale.reasonCode, "observation_stale");
  assert.equal(stale.motion, false);
  assert.throws(() => getFixtureSnapshot("docx:running@FAKE"), /unknown fixture reality/);
  // UNKNOWN 不能作为显式覆盖形态（不可编造可观察 UNKNOWN 事件）
  assert.throws(() => getFixtureSnapshot("docx:running@UNKNOWN"), /unknown fixture reality/);
});

test("fixtures: 合成 source 不产生真实见证语义（绿槽前置负例）", () => {
  // UI 规则：source !== "control-kernel" 时不得渲染 data-slot=real / “有执行见证”。
  // 夹具层保证：任何已观察快照的 source 都是 synthetic-fixture，reality 字段
  // 只描述形态，不构成真实见证。
  for (const key of listFixtureKeys()) {
    const snap = getFixtureSnapshot(key);
    if (snap.mode === "unknown") continue; // fail-closed 快照不携带 source
    assert.equal(snap.source, "synthetic-fixture", `${key} source 必须是合成标注`);
  }
});

test("fixtures: 快照文案不得出现签发完成或进度伪造措辞", () => {
  for (const key of listFixtureKeys()) {
    const snap = getFixtureSnapshot(key);
    const text = `${snap.title} ${snap.detail} ${snap.stepLabel}`;
    assert.ok(!/已签发|签发成功|有执行见证/.test(text), `${key} 出现越权信任措辞`);
    assert.ok(!text.includes("%"), `${key} 禁止百分比`);
  }
});
