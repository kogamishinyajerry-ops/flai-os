// frontend/tests/task_journey.test.mjs — 任务执行链的 fail-closed 视觉派生核。
import test from "node:test";
import assert from "node:assert/strict";
import { buildTaskJourney } from "../src/utils/taskJourney.js";

const byId = (steps, id) => steps.find((step) => step.id === id);

test("buildTaskJourney: 缺任务时不渲染示意链，畸形明细输入不抛错", () => {
  assert.deepEqual(buildTaskJourney({ task: null }), []);

  const steps = buildTaskJourney({
    task: {
      status: "waiting_review",
      inputs: null,
      input_file_ids: null,
      output_file_ids: null,
    },
    events: null,
    modelCalls: null,
    modelCallsError: "请求超时",
  });

  assert.deepEqual(steps.map((step) => step.id), [
    "input",
    "execution",
    "calls",
    "artifacts",
    "review",
    "delivery",
  ]);
  assert.equal(byId(steps, "input").tone, "pending");
  assert.match(byId(steps, "input").detail, /待核/);
  assert.equal(byId(steps, "calls").tone, "pending");
  assert.match(byId(steps, "calls").detail, /不可用/);
  assert.equal(byId(steps, "artifacts").tone, "pending");
  assert.match(byId(steps, "artifacts").detail, /待核/);
  assert.equal(byId(steps, "review").tone, "pending");
  assert.equal(byId(steps, "delivery").tone, "pending");
});

test("buildTaskJourney: 真失败只染失败节点，待签与待交付保持 amber", () => {
  const steps = buildTaskJourney({
    task: {
      status: "waiting_review",
      inputs: { top_event: "双通道失效" },
      input_file_ids: ["f1"],
      output_file_ids: ["o1", "o2"],
    },
    events: [
      { event_type: "tool_started" },
      { event_type: "tool_failed" },
    ],
    modelCalls: [
      { status: "success" },
      { status: "failed" },
    ],
    modelCallsLoaded: true,
  });

  assert.equal(byId(steps, "input").detail, "1 个输入文件 · 1 项参数");
  assert.equal(byId(steps, "execution").tone, "neutral");
  assert.equal(byId(steps, "calls").tone, "fail");
  assert.equal(byId(steps, "artifacts").detail, "2 件文件产物");
  assert.equal(byId(steps, "review").tone, "pending");
  assert.equal(byId(steps, "delivery").tone, "pending");
});

test("buildTaskJourney: 人工批准只给签发节点 teal，completed 与产物不得假绿", () => {
  const steps = buildTaskJourney({
    task: {
      status: "completed",
      inputs: {},
      input_file_ids: [],
      output_file_ids: ["o1"],
    },
    events: [
      {
        event_type: "review_approved",
        payload: { reviewer: "验收工程师" },
      },
    ],
    modelCalls: [],
    modelCallsLoaded: true,
  });

  assert.equal(byId(steps, "review").tone, "signed");
  assert.match(byId(steps, "review").detail, /验收工程师/);
  assert.equal(byId(steps, "execution").tone, "neutral");
  assert.equal(byId(steps, "artifacts").tone, "neutral");
  assert.equal(byId(steps, "delivery").tone, "neutral");
  assert.equal(steps.some((step) => step.tone === "success" || step.tone === "real"), false);
});

test("buildTaskJourney: 受限或不完整签发记录不冒充已签，也不冒充未签", () => {
  const redacted = buildTaskJourney({
    task: { status: "completed", output_file_ids: [] },
    events: [{ event_type: "review_approved", payload: {}, content_withheld: true }],
  });
  assert.equal(byId(redacted, "review").tone, "neutral");
  assert.equal(byId(redacted, "review").detail, "签发记录受限");

  const incomplete = buildTaskJourney({
    task: { status: "completed", output_file_ids: [] },
    events: [{ event_type: "review_approved", payload: {} }],
  });
  assert.equal(byId(incomplete, "review").tone, "neutral");
  assert.equal(byId(incomplete, "review").detail, "签发记录不完整");
});

test("buildTaskJourney: 失败任务只把真实执行与交付画成红色", () => {
  const steps = buildTaskJourney({
    task: { status: "failed", inputs: {}, input_file_ids: [], output_file_ids: [] },
    events: [{ event_type: "task_failed" }],
    modelCalls: [],
    modelCallsLoaded: true,
  });

  assert.equal(byId(steps, "execution").tone, "fail");
  assert.equal(byId(steps, "delivery").tone, "fail");
  assert.equal(byId(steps, "calls").tone, "neutral");
  assert.equal(byId(steps, "review").tone, "neutral");
});

test("buildTaskJourney: 人工驳回不污名 Agent 执行，签发与交付明确标红", () => {
  const steps = buildTaskJourney({
    task: { status: "failed", inputs: {}, input_file_ids: [], output_file_ids: ["o1"] },
    events: [
      {
        event_type: "review_rejected",
        payload: { reviewer: "验收工程师" },
      },
    ],
    modelCalls: [],
    modelCallsLoaded: true,
  });

  assert.equal(byId(steps, "execution").tone, "neutral");
  assert.equal(byId(steps, "review").tone, "fail");
  assert.match(byId(steps, "review").detail, /驳回/);
  assert.equal(byId(steps, "delivery").tone, "fail");
  assert.match(byId(steps, "delivery").detail, /驳回/);
});

test("buildTaskJourney: 模型事件先到而明细未到时保持 amber，不能假报零调用", () => {
  const steps = buildTaskJourney({
    task: { status: "running", inputs: {}, input_file_ids: [], output_file_ids: [] },
    events: [{ event_type: "model_call", level: "info", payload: { profile: "reasoning" } }],
    modelCalls: [],
    modelCallsLoaded: false,
  });

  assert.equal(byId(steps, "calls").tone, "pending");
  assert.match(byId(steps, "calls").detail, /模型 1 次/);
  assert.match(byId(steps, "calls").detail, /明细待核/);
  assert.doesNotMatch(byId(steps, "calls").detail, /^无/);
});

test("buildTaskJourney: 已加载但格式畸形的模型明细保持 amber，不能压成零调用", () => {
  const steps = buildTaskJourney({
    task: { status: "running", inputs: {}, input_file_ids: [], output_file_ids: [] },
    events: [],
    modelCalls: { items: [] },
    modelCallsLoaded: true,
  });

  assert.equal(byId(steps, "calls").tone, "pending");
  assert.equal(byId(steps, "calls").detail, "模型明细格式待核");
});

test("buildTaskJourney: mock 工具调用保持 amber，并明确真实性仍看核验段", () => {
  const steps = buildTaskJourney({
    task: { status: "waiting_review", inputs: {}, input_file_ids: [], output_file_ids: ["o1"] },
    events: [
      { event_type: "tool_started", payload: { tool_id: "solver", mock: true } },
      { event_type: "tool_finished", payload: { tool_id: "solver", mock: true } },
    ],
    modelCalls: [],
    modelCallsLoaded: true,
  });

  assert.equal(byId(steps, "calls").tone, "pending");
  assert.match(byId(steps, "calls").detail, /工具 1 次/);
  assert.match(byId(steps, "calls").detail, /mock/);
});

test("buildTaskJourney: completed 但签发请求无决策时，签发与交付均 fail-closed", () => {
  const steps = buildTaskJourney({
    task: { status: "completed", inputs: {}, input_file_ids: [], output_file_ids: ["o1"] },
    events: [{ event_type: "review_requested" }],
    modelCalls: [],
    modelCallsLoaded: true,
  });

  assert.equal(byId(steps, "review").tone, "pending");
  assert.equal(byId(steps, "review").detail, "签发决策记录缺失");
  assert.equal(byId(steps, "delivery").tone, "pending");
  assert.equal(byId(steps, "delivery").detail, "完成状态待核");
});

test("buildTaskJourney: completed 不推导「所有环节都可信」，各环节只投影各自真值", () => {
  // 批次 D P1 锁定：completed 是中性落定，不是信任通行证——无签发事件时
  // 签发/交付不得借 completed 染任何通过色；无调用记录时调用节点如实报「无」，
  // 不得反推「调用都成功」。
  const steps = buildTaskJourney({
    task: { status: "completed", inputs: {}, input_file_ids: [], output_file_ids: ["o1"] },
    events: [],
    modelCalls: [],
    modelCallsLoaded: true,
  });

  assert.equal(byId(steps, "execution").tone, "neutral");
  assert.equal(byId(steps, "calls").tone, "neutral");
  assert.equal(byId(steps, "calls").detail, "无工具或模型调用记录");
  assert.equal(byId(steps, "review").tone, "neutral");
  assert.equal(byId(steps, "review").detail, "未进入人工签发");
  assert.equal(byId(steps, "delivery").tone, "neutral");
  assert.equal(
    steps.every((step) => ["neutral", "pending", "fail", "work", "signed"].includes(step.tone)),
    true,
  );
  assert.equal(steps.some((step) => step.tone === "signed"), false);
});

test("buildTaskJourney: 输入校验失败只归因输入节点，未知任务状态保持 amber", () => {
  const invalid = buildTaskJourney({
    task: { status: "failed", inputs: {}, input_file_ids: [], output_file_ids: [] },
    events: [{ event_type: "validation_failed" }],
    modelCalls: [],
    modelCallsLoaded: true,
  });
  assert.equal(byId(invalid, "input").tone, "fail");
  assert.equal(byId(invalid, "execution").tone, "neutral");
  assert.equal(byId(invalid, "delivery").tone, "fail");

  const unknown = buildTaskJourney({
    task: { status: "future_state", inputs: {}, input_file_ids: [], output_file_ids: [] },
    events: [],
    modelCalls: [],
    modelCallsLoaded: true,
  });
  assert.equal(byId(unknown, "execution").tone, "pending");
  assert.equal(unknown.some((step) => ["success", "real", "green"].includes(step.tone)), false);
});
