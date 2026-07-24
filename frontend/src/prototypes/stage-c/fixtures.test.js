// Stage C 原型合成夹具的状态/合同测试。夹具只驱动 UI，不证明任何真实执行。
import assert from "node:assert/strict";
import test from "node:test";

import { OBSERVER_CONTRACT_VERSION } from "./observer-contract.js";
import {
  FIXTURE_SCENARIOS,
  FIXTURE_STATES,
  getFixtureSnapshot,
  listFixtureKeys,
} from "./fixtures.js";

test("fixtures: 覆盖三种场景与全部要求状态", () => {
  assert.deepEqual(Object.keys(FIXTURE_SCENARIOS).sort(), ["cfd", "docx", "meeting"]);
  for (const state of [
    "running",
    "waiting_review",
    "completed",
    "failed",
    "cancelled",
    "evidence-missing",
    "permission-denied",
    "unknown",
    "stale",
  ]) {
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
