// 触发-浮现公理源码锚（map #46 · 票 #56，UI-PARADIGM.md「触发-浮现公理」节）：
// R-A 第一规则实现面锚 + R-G 地板负规则锚 + 负规则防回归扫描。
// 纯源码读锚（三段式：读源 → 分组断言 → 负规则扫描），不起栈不跑 e2e。
// R-B/R-D 行为锚在并行批的测试文件里，本文件不重复。
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const statusDockSource = readFileSync(
  new URL("../src/components/StatusDock.vue", import.meta.url),
  "utf8",
);
const statusCenterSource = readFileSync(
  new URL("../src/components/StatusCenter.vue", import.meta.url),
  "utf8",
);
const todayPageSource = readFileSync(
  new URL("../src/views/TodayPage.vue", import.meta.url),
  "utf8",
);
const verificationCardSource = readFileSync(
  new URL("../src/components/VerificationCard.vue", import.meta.url),
  "utf8",
);
const workLogSource = readFileSync(
  new URL("../src/components/WorkLog.vue", import.meta.url),
  "utf8",
);
const formatSource = readFileSync(
  new URL("../src/utils/format.js", import.meta.url),
  "utf8",
);
const classificationGateSource = readFileSync(
  new URL("../../backend/app/api/classification_gate.py", import.meta.url),
  "utf8",
);

// ── R-A：waiting_review ⟹ 可信面全量上浮并主动来找人（第一规则，追认现状） ──

test("R-A：StatusDock 只认 waiting_review 迁移触发回声，pill 与 title 徽章同源在场", () => {
  // 回声闸：handleTransition 只放行落地→waiting_review 的迁移
  assert.match(statusDockSource, /ev\.to !== "waiting_review"/);
  // 待签 pill 文案逐字（行动召唤最强的一枚）
  assert.ok(statusDockSource.includes("✍ 待你签发"));
  // 标签页召回徽章与坞内 pill 同源（真实轮询），卸载清零
  assert.match(statusDockSource, /setTitleBadge\(/);
});

test("R-A：StatusCenter 收件箱待签组置顶（先于进行中/最近落定）", () => {
  const waitingIdx = statusCenterSource.indexOf("sc-group-label waiting");
  const workingIdx = statusCenterSource.indexOf("sc-group-label working");
  const doneIdx = statusCenterSource.indexOf("最近落定");
  assert.ok(waitingIdx > -1, "待签组头不在场");
  assert.ok(workingIdx > -1, "进行中组头不在场");
  assert.ok(doneIdx > -1, "最近落定组不在场");
  assert.ok(waitingIdx < workingIdx, "待签组必须排在进行中之前");
  assert.ok(waitingIdx < doneIdx, "待签组必须排在最近落定之前");
});

test("R-A：TodayPage 待你签发版块置顶（先于进行中版块）", () => {
  const waitingIdx = todayPageSource.indexOf("today-section-head waiting");
  const workingIdx = todayPageSource.indexOf("today-section-head working");
  assert.ok(waitingIdx > -1, "待签版块头不在场");
  assert.ok(workingIdx > -1, "进行中版块头不在场");
  assert.ok(waitingIdx < workingIdx, "待签版块必须排在进行中之前");
  assert.ok(todayPageSource.includes("待你签发"));
});

// ── R-G：地板层五件永不触发、永不可关 ──

test("R-G：人签面诚实地板句逐字在场，且不被任何额外 v-if 开关包裹", () => {
  // 地板句逐字（与 pytest test_guide_auto_routing_contract posture 锚同一句）
  assert.ok(
    verificationCardSource.includes(
      "通识解释仅供参考；工程结论以确定性工具与人签为准",
    ),
  );
  // 地板行标签零 v-if：除组件渲染窗（外层 verify-card 的 v-if="visible"）外
  // 不得再挂任何偏好/简洁开关——加属性即破坏此精确匹配，测试转红。
  assert.ok(
    verificationCardSource.includes('<div class="verify-row verify-honesty">'),
    "诚实地板行不得挂 v-if 等额外开关",
  );
});

test("R-G：WorkLog 折叠态诚实闸常显（mock 如实标注 + 真实性未核 amber）", () => {
  assert.ok(workLogSource.includes("折叠常显的诚实闸"));
  assert.match(workLogSource, /toolAuthenticityUnknown/);
  assert.ok(workLogSource.includes("真实性未核"));
});

test("R-G：completed 恒中性（不给绿）与 amber 唯一未核语义锚", () => {
  // completed=中性 info（绿仅真实 REAL 结果，给绿即假 REAL）
  assert.ok(formatSource.includes('completed: { label: "已完成", type: "info" }'));
  assert.ok(formatSource.includes("不给绿"));
  // amber=未核·待人签唯一语义注释锚
  assert.ok(formatSource.includes("未核·待人签"));
  assert.match(formatSource, /status === "waiting_review"\) return "var\(--trust-pending\)"/);
});

test("R-G：密级门 chokepoint docstring 锚（一切派生内容出场面唯一遮蔽点）", () => {
  assert.ok(classificationGateSource.includes("唯一遮蔽 chokepoint"));
});

// ── 负规则防回归：无「简洁模式」类开关；地板文件无偏好开关缠绕 ──

test("负规则：frontend/src 全量源码零「简洁/极简/minimal/low-noise 模式」命中", () => {
  const srcDir = new URL("../src/", import.meta.url).pathname;
  const entries = readdirSync(srcDir, { recursive: true });
  const offenders = [];
  const pattern = /简洁模式|极简模式|minimal[-_ ]?mode|low[-_ ]?noise/i;
  for (const entry of entries) {
    if (!/\.(vue|js|mjs|ts)$/.test(entry)) continue;
    const content = readFileSync(join(srcDir, entry), "utf8");
    if (pattern.test(content)) offenders.push(entry);
  }
  assert.deepEqual(
    offenders,
    [],
    `地板层不可被「简洁模式」关掉（R-G）：以下文件引入疑似开关：${offenders.join(", ")}`,
  );
});

test("负规则：WorkLog 与 VerificationCard 无 localStorage/偏好开关缠绕", () => {
  for (const [name, source] of [
    ["WorkLog.vue", workLogSource],
    ["VerificationCard.vue", verificationCardSource],
  ]) {
    assert.ok(
      !source.includes("localStorage"),
      `${name} 不得读 localStorage 偏好——地板层常显不可关（R-G）`,
    );
  }
});
