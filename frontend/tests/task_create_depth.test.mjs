// frontend/tests/task_create_depth.test.mjs — 批 B（创建任务与输入确认）深度打磨核：
// 旅程节点 state/stateLabel 三通道派生、fail-closed 分支、快照严格布尔收口。
import test from "node:test";
import assert from "node:assert/strict";

import {
  buildTaskCreateJourney,
  captureTaskSubmission,
} from "../src/utils/taskCreateVisual.js";

const byId = (steps, id) => steps.find((step) => step.id === id);
const KNOWN_STATES = new Set(["ready", "review", "pending", "working", "error"]);

const FULL_AGENT = {
  id: "agent-1",
  name: "试验 Agent",
  category: "structured_gen",
  maturity: "L0",
  clearance: "internal",
  evidence_policy_required: true,
  limitations: ["不替代工程签字"],
};

test("旅程五节点恒有 state+stateLabel 三通道，顺序与标识不变", () => {
  const scenarios = [
    {},
    { agentId: "agent-1", selectedAgent: FULL_AGENT },
    { agentId: "agent-1", selectedAgent: FULL_AGENT, submitting: true, uploadingFiles: true },
    { agentId: "agent-1", selectedAgent: FULL_AGENT, submitError: "后端拒绝" },
    { prefillOrigin: "guide" },
  ];
  for (const scenario of scenarios) {
    const steps = buildTaskCreateJourney(scenario);
    assert.deepEqual(
      steps.map((s) => s.id),
      ["agent", "capability", "input", "policy", "submit"]
    );
    for (const step of steps) {
      assert.ok(KNOWN_STATES.has(step.state), `未知 state：${step.state}`);
      assert.ok(
        typeof step.stateLabel === "string" && step.stateLabel.trim() !== "",
        `${step.id} 缺 stateLabel`
      );
      // 创建页永不出现签发/绿/真实核验语义。
      assert.ok(!["success", "green", "signed", "real"].includes(step.tone));
      assert.ok(!["success", "green", "signed", "real"].includes(step.state));
      assert.doesNotMatch(step.stateLabel, /签发|已核验|已通过/);
    }
  }
});

test("初始空态：全节点待处理，提交节点明示「待你提交」而非签发", () => {
  const steps = buildTaskCreateJourney({});
  assert.equal(byId(steps, "agent").state, "pending");
  assert.equal(byId(steps, "agent").stateLabel, "待选择");
  assert.equal(byId(steps, "capability").state, "pending");
  assert.equal(byId(steps, "input").state, "pending");
  assert.equal(byId(steps, "policy").state, "pending");
  assert.equal(byId(steps, "submit").state, "pending");
  assert.equal(byId(steps, "submit").stateLabel, "待你提交");
});

test("Agent 选定后：agent 节点 ready，能力/边界只到「请核对」（review，不预支人核）", () => {
  const steps = buildTaskCreateJourney({
    agentId: "agent-1",
    selectedAgent: FULL_AGENT,
    schemaRenderable: true,
  });
  assert.equal(byId(steps, "agent").state, "ready");
  assert.equal(byId(steps, "agent").stateLabel, "已选定");
  assert.equal(byId(steps, "capability").state, "review");
  assert.equal(byId(steps, "capability").stateLabel, "请核对");
  assert.equal(byId(steps, "policy").state, "review");
  assert.equal(byId(steps, "policy").stateLabel, "请核对");
  // 前端不做合法性预支：无错误记录≠输入已就绪。
  assert.equal(byId(steps, "input").state, "review");
  assert.equal(byId(steps, "input").stateLabel, "待你填写");
});

test("附件就位：input 标「附件已就绪」但仍是 review 而非 ready/绿", () => {
  const steps = buildTaskCreateJourney({
    agentId: "agent-1",
    selectedAgent: FULL_AGENT,
    schemaRenderable: true,
    uploadItems: [{ status: "done" }, { status: "done" }],
  });
  const input = byId(steps, "input");
  assert.equal(input.state, "review");
  assert.equal(input.stateLabel, "附件已就绪");
  assert.equal(input.tone, "neutral");
});

test("预填草案与未知策略保持 amber 待核，fail-closed 不升级为就绪", () => {
  const prefill = buildTaskCreateJourney({
    agentId: "agent-1",
    selectedAgent: FULL_AGENT,
    schemaRenderable: true,
    prefillOrigin: "retry",
  });
  assert.equal(byId(prefill, "input").tone, "pending");
  assert.equal(byId(prefill, "input").state, "pending");
  assert.equal(byId(prefill, "input").stateLabel, "草案待核");

  const unknownPolicy = buildTaskCreateJourney({
    agentId: "agent-1",
    selectedAgent: {
      ...FULL_AGENT,
      clearance: "top_secret_strange",
      evidence_policy_required: "yes",
      limitations: "不是数组",
    },
  });
  const policy = byId(unknownPolicy, "policy");
  assert.equal(policy.tone, "pending");
  assert.equal(policy.state, "pending");
  assert.equal(policy.stateLabel, "策略待核");
});

test("错配 Agent 详情：stateLabel 同样不泄漏旧身份，能力/边界保持待核", () => {
  const steps = buildTaskCreateJourney({
    agentId: "agent-b",
    selectedAgent: { ...FULL_AGENT, id: "agent-a", name: "旧 Agent", clearance: "public" },
  });
  assert.equal(byId(steps, "agent").state, "pending");
  assert.equal(byId(steps, "agent").stateLabel, "核对中");
  assert.equal(byId(steps, "capability").state, "pending");
  assert.equal(byId(steps, "policy").state, "pending");
  for (const step of steps) {
    assert.doesNotMatch(step.stateLabel, /旧 Agent/);
    assert.doesNotMatch(step.detail, /旧 Agent/);
  }
});

test("真实错误与在途：error/working 双态齐备，且绝不混入 ready", () => {
  const failed = buildTaskCreateJourney({
    agentId: "agent-1",
    selectedAgent: FULL_AGENT,
    uploadItems: [{ status: "error", error: "网络中断" }],
  });
  assert.equal(byId(failed, "input").state, "error");
  assert.equal(byId(failed, "input").stateLabel, "有错误");

  const submitFailed = buildTaskCreateJourney({
    agentId: "agent-1",
    selectedAgent: FULL_AGENT,
    submitError: "422 输入不合法",
  });
  assert.equal(byId(submitFailed, "submit").state, "error");
  assert.equal(byId(submitFailed, "submit").stateLabel, "创建失败");
  assert.equal(byId(submitFailed, "input").state, "error");

  const working = buildTaskCreateJourney({
    agentId: "agent-1",
    selectedAgent: FULL_AGENT,
    submitting: true,
    uploadingFiles: true,
    uploadItems: [{ status: "uploading" }],
  });
  assert.equal(byId(working, "input").state, "working");
  assert.equal(byId(working, "input").stateLabel, "进行中");
  assert.equal(byId(working, "submit").state, "working");
  // agent 已选定是既成事实可保持 ready；在途的 input/submit 绝不标就绪。
  assert.notEqual(byId(working, "input").state, "ready");
  assert.notEqual(byId(working, "submit").state, "ready");
});

test("提交快照：会话收口与返回方向严格布尔（truthy 杂值一律 false）", () => {
  const draft = captureTaskSubmission({
    form: { agentId: "agent-a", name: "" },
    inputs: null,
    uploadItems: null,
    concludeAfter: "true",
    returnToChat: 1,
  });
  assert.equal(draft.concludeAfter, false);
  assert.equal(draft.returnToChat, false);
  assert.deepEqual(draft.inputs, {});
  assert.deepEqual(draft.uploadItems, []);
  assert.equal(draft.name, null);

  const strict = captureTaskSubmission({
    form: { agentId: "agent-a" },
    inputs: {},
    uploadItems: [],
    concludeAfter: true,
    returnToChat: true,
  });
  assert.equal(strict.concludeAfter, true);
  assert.equal(strict.returnToChat, true);
});
