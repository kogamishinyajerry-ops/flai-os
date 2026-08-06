import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  agentExecutionReady,
  automaticTaskName,
  automaticTeamName,
  conversationSnapshotMatches,
  currentWorkSegmentFiles,
  internalConversationRouteBindingMatches,
  latestActionablePlanIndex,
  matchingAgentFiles,
  planAttachmentRouting,
  planHasIncompleteOrchestration,
  retryLineageForPlanItem,
  verifiedFailedRetryLineage,
} from "../src/utils/conversationPlans.js";

const guideSource = readFileSync(
  new URL("../src/views/GuidePage.vue", import.meta.url),
  "utf8",
);
const taskApiSource = readFileSync(
  new URL("../src/api/tasks.js", import.meta.url),
  "utf8",
);

test("最新用户轮次立即撤销旧方案动作，历史路由依据不再常驻展开", () => {
  const plan = { decision: "orchestrate", agents: [{ agent_id: "a" }] };
  assert.equal(
    latestActionablePlanIndex([{ role: "assistant", recommendation: plan, fresh: true }]),
    0,
  );
  assert.equal(
    latestActionablePlanIndex([{ role: "assistant", recommendation: plan, fresh: false }]),
    -1,
  );
  assert.equal(
    latestActionablePlanIndex([
      { role: "assistant", recommendation: plan, fresh: true },
      { role: "user", content: "再补充一个约束" },
    ]),
    -1,
  );
  assert.match(
    guideSource,
    /<details v-if="idx === latestPlanIdx" class="route-disclosure">/,
  );
});

test("失败恢复方案把 retry_of 绑定到 canonical 轮次，query 丢失即阻断", () => {
  const message = {
    role: "assistant",
    fresh: true,
    retryOf: "task_failed",
    recommendation: { decision: "orchestrate", agents: [{ agent_id: "a" }] },
  };
  assert.equal(
    latestActionablePlanIndex([message], {
      activeRetryOf: "task_failed",
      retryPlanArmed: true,
    }),
    0,
  );
  assert.equal(
    latestActionablePlanIndex([message], { activeRetryOf: null, retryPlanArmed: false }),
    -1,
  );
  assert.equal(
    latestActionablePlanIndex([message], {
      activeRetryOf: "task_other",
      retryPlanArmed: true,
    }),
    -1,
  );
});

test("团队与任务名称由方案自动生成，不弹出第二个填空框", () => {
  assert.doesNotMatch(guideSource, /window\.prompt/);
  assert.match(guideSource, /name: automaticTaskName\(plan, a,/);
  const plan = { goal: "  起落架   风险检查  ", agents: [{}, {}] };
  assert.equal(automaticTeamName(plan), "起落架 风险检查 · 专家团队");
  assert.equal(
    automaticTaskName(plan, { role: "结构核查" }, 0),
    "起落架 风险检查 · 结构核查",
  );
});

test("自动开工按 params、file_upload、none 三种输入契约 fail-closed 判定", () => {
  assert.equal(
    agentExecutionReady(
      {
        loaded: true,
        inputMode: "params",
        schema: { type: "object", required: ["case"], properties: { case: { type: "string" } } },
      },
      { case: "A" },
      [],
    ),
    true,
  );
  assert.equal(
    agentExecutionReady(
      {
        loaded: true,
        inputMode: "file_upload",
        allowedExtensions: [".xlsx"],
        schema: { type: "object", additionalProperties: false, properties: {} },
      },
      {},
      [{ name: "旧算例.xlsx" }, { name: "新算例.xlsx" }],
    ),
    false,
    "多个同后缀历史附件存在归属歧义，必须阻断而不是全部转发",
  );
  assert.equal(
    agentExecutionReady(
      {
        loaded: true,
        inputMode: "file_upload",
        allowedExtensions: [".xlsx"],
        schema: {
          type: "object",
          additionalProperties: false,
          properties: { sheet_name: { type: "string", minLength: 1 } },
        },
      },
      { sheet_name: "Sheet1" },
      [{ name: "检查表.XLSX" }],
    ),
    true,
  );
  assert.equal(
    agentExecutionReady(
      {
        loaded: true,
        inputMode: "file_upload",
        allowedExtensions: [".xlsx"],
        schema: { type: "object", additionalProperties: false, properties: {} },
      },
      {},
      [{ name: "说明.pdf" }],
    ),
    false,
  );
  assert.equal(
    agentExecutionReady({ loaded: true, inputMode: "none" }, {}, []),
    true,
  );
  assert.equal(agentExecutionReady({ loaded: true, inputMode: "unknown" }, {}, []), false);
});

test("文件型 Agent 自动挑出契约匹配附件，不被无关历史附件永久阻断", () => {
  const contract = { allowedExtensions: [".xlsx"] };
  const files = [
    { id: "file_old", name: "背景说明.pdf" },
    { id: "file_case", name: "检查表.XLSX" },
  ];
  assert.deepEqual(matchingAgentFiles(contract, files), [files[1]]);
  assert.deepEqual(matchingAgentFiles({ allowedExtensions: null }, files), []);
});

test("方案附件按输入模式确定性归属，params 不丢附件且 none 不静默吞附件", () => {
  const files = [
    { id: "file_note", name: "背景说明.pdf" },
    { id: "file_case", name: "检查表.xlsx" },
  ];
  const contracts = {
    fta: { loaded: true, inputMode: "params", allowedExtensions: [] },
    evaluator: { loaded: true, inputMode: "file_upload", allowedExtensions: [".xlsx"] },
    notifier: { loaded: true, inputMode: "none", allowedExtensions: [] },
  };

  assert.deepEqual(
    planAttachmentRouting([{ agent_id: "fta" }], contracts, [files[0]]),
    { ready: true, inputFileIdsByAgent: { fta: ["file_note"] } },
    "单 params Agent 必须保留本轮 canonical 附件，不能因没有后缀声明而静默丢弃",
  );
  assert.deepEqual(
    planAttachmentRouting([{ agent_id: "notifier" }], contracts, [files[0]]),
    { ready: false, inputFileIdsByAgent: {} },
    "none Agent 明确不消费输入，当前段有附件时必须回到对话澄清",
  );
  assert.deepEqual(
    planAttachmentRouting(
      [{ agent_id: "fta" }, { agent_id: "notifier" }],
      contracts,
      [files[0]],
    ),
    { ready: true, inputFileIdsByAgent: { fta: ["file_note"] } },
    "多 Agent 中只有一个 params 消费者时归属仍然唯一",
  );
  assert.deepEqual(
    planAttachmentRouting(
      [{ agent_id: "fta" }, { agent_id: "notifier" }],
      contracts,
      [],
    ),
    { ready: true, inputFileIdsByAgent: {} },
    "没有当前段附件时 params/none 多 Agent 方案不能被历史附件永久封锁",
  );
});

test("多 Agent 仅在唯一 file_upload 消费者拥有唯一契约匹配附件时自动路由", () => {
  const files = [
    { id: "file_note", name: "背景说明.pdf" },
    { id: "file_case", name: "检查表.xlsx" },
  ];
  const contracts = {
    params: { loaded: true, inputMode: "params", allowedExtensions: [] },
    xlsx: { loaded: true, inputMode: "file_upload", allowedExtensions: [".xlsx"] },
    xlsx2: { loaded: true, inputMode: "file_upload", allowedExtensions: [".xlsx"] },
  };
  assert.deepEqual(
    planAttachmentRouting(
      [{ agent_id: "params" }, { agent_id: "xlsx" }],
      contracts,
      [files[1]],
    ),
    { ready: true, inputFileIdsByAgent: { xlsx: ["file_case"] } },
  );
  assert.deepEqual(
    planAttachmentRouting(
      [{ agent_id: "params" }, { agent_id: "xlsx" }],
      contracts,
      files,
    ),
    { ready: false, inputFileIdsByAgent: {} },
    "唯一匹配文件之外仍有未分配附件时必须追问，不能把额外附件静默丢掉",
  );
  assert.deepEqual(
    planAttachmentRouting(
      [{ agent_id: "xlsx" }, { agent_id: "xlsx2" }],
      contracts,
      [files[1]],
    ),
    { ready: false, inputFileIdsByAgent: {} },
    "两个文件消费者即使都能读同一文件也不得猜归属",
  );
  assert.deepEqual(
    planAttachmentRouting(
      [{ agent_id: "xlsx" }],
      contracts,
      [files[1], { id: "file_case_2", name: "复核表.XLSX" }],
    ),
    { ready: false, inputFileIdsByAgent: {} },
    "同一契约匹配两份 canonical 文件时必须追问哪一份",
  );
  assert.deepEqual(
    planAttachmentRouting([{ agent_id: "xlsx" }], contracts, [{ name: "检查表.xlsx" }]),
    { ready: false, inputFileIdsByAgent: {} },
    "本地名称不能冒充已保存的 canonical file id",
  );
});

test("backend-resolved canonical 材料绑定是权威来源，覆盖 legacy 后缀猜测", () => {
  const files = [
    { id: "file_case", name: "检查表.xlsx" },
    { id: "file_note", name: "背景说明.pdf" },
    { id: "file_unused", name: "旧版说明.txt" },
  ];
  const contracts = {
    evaluator: { loaded: true, inputMode: "file_upload", allowedExtensions: [".xlsx"] },
    reporter: { loaded: true, inputMode: "params", allowedExtensions: [] },
    notifier: { loaded: true, inputMode: "none", allowedExtensions: [] },
  };
  const plan = {
    agents: [
      {
        agent_id: "evaluator",
        attachments: [{ file_id: "file_case", filename: "检查表.xlsx" }],
      },
      {
        agent_id: "reporter",
        attachments: [{ file_id: "file_note", filename: "背景说明.pdf" }],
      },
      { agent_id: "notifier", attachments: [] },
    ],
    ignored_attachments: [{ file_id: "file_unused", filename: "旧版说明.txt" }],
  };

  assert.deepEqual(planAttachmentRouting(plan, contracts, files), {
    ready: true,
    inputFileIdsByAgent: {
      evaluator: ["file_case"],
      reporter: ["file_note"],
    },
    attachmentsByAgent: {
      evaluator: [{ id: "file_case", name: "检查表.xlsx" }],
      reporter: [{ id: "file_note", name: "背景说明.pdf" }],
      notifier: [],
    },
    ignoredAttachments: [{ id: "file_unused", name: "旧版说明.txt" }],
    canonical: true,
  });
});

test("旧计划所有 canonical 字段均缺失时，Guide 的完整 plan 入参仍走 legacy 推断", () => {
  const contracts = {
    analyst: { loaded: true, inputMode: "params", allowedExtensions: [] },
    notifier: { loaded: true, inputMode: "none", allowedExtensions: [] },
  };
  assert.deepEqual(
    planAttachmentRouting(
      { agents: [{ agent_id: "analyst" }, { agent_id: "notifier" }] },
      contracts,
      [{ id: "file_legacy", name: "升级前材料.pdf" }],
    ),
    { ready: true, inputFileIdsByAgent: { analyst: ["file_legacy"] } },
  );
});

test("canonical 材料字段一旦出现就全量 fail-closed，不退回 legacy 猜测", () => {
  const files = [
    { id: "file_case", name: "检查表.xlsx" },
    { id: "file_note", name: "背景说明.pdf" },
  ];
  const contracts = {
    evaluator: { loaded: true, inputMode: "file_upload", allowedExtensions: [".xlsx"] },
    reporter: { loaded: true, inputMode: "params", allowedExtensions: [] },
    notifier: { loaded: true, inputMode: "none", allowedExtensions: [] },
  };
  const invalidPlans = [
    // 根 ignored 字段缺失：canonical shape 不完整。
    {
      agents: [
        { agent_id: "evaluator", attachments: [{ file_id: "file_case", filename: "检查表.xlsx" }] },
        { agent_id: "reporter", attachments: [{ file_id: "file_note", filename: "背景说明.pdf" }] },
      ],
    },
    // 根字段出现后，每个成员都必须显式给出 attachments（可为空）。
    {
      agents: [
        { agent_id: "evaluator", attachments: [{ file_id: "file_case", filename: "检查表.xlsx" }] },
        { agent_id: "reporter" },
      ],
      ignored_attachments: [{ file_id: "file_note", filename: "背景说明.pdf" }],
    },
    // 同一 file id 双重绑定。
    {
      agents: [
        { agent_id: "evaluator", attachments: [{ file_id: "file_case", filename: "检查表.xlsx" }] },
        { agent_id: "reporter", attachments: [{ file_id: "file_case", filename: "检查表.xlsx" }] },
      ],
      ignored_attachments: [{ file_id: "file_note", filename: "背景说明.pdf" }],
    },
    // 绑定与 ignored 之间同样不能双重记账。
    {
      agents: [
        { agent_id: "evaluator", attachments: [{ file_id: "file_case", filename: "检查表.xlsx" }] },
        { agent_id: "reporter", attachments: [] },
      ],
      ignored_attachments: [
        { file_id: "file_case", filename: "检查表.xlsx" },
        { file_id: "file_note", filename: "背景说明.pdf" },
      ],
    },
    // 当前工作段材料没有被绑定或明确忽略。
    {
      agents: [
        { agent_id: "evaluator", attachments: [{ file_id: "file_case", filename: "检查表.xlsx" }] },
        { agent_id: "reporter", attachments: [] },
      ],
      ignored_attachments: [],
    },
    // 非当前工作段 file id 不能借 canonical 字段越界带入。
    {
      agents: [
        { agent_id: "evaluator", attachments: [{ file_id: "file_ghost", filename: "检查表.xlsx" }] },
        { agent_id: "reporter", attachments: [{ file_id: "file_note", filename: "背景说明.pdf" }] },
      ],
      ignored_attachments: [],
    },
    // none 不能消费材料。
    {
      agents: [
        { agent_id: "evaluator", attachments: [{ file_id: "file_case", filename: "检查表.xlsx" }] },
        { agent_id: "notifier", attachments: [{ file_id: "file_note", filename: "背景说明.pdf" }] },
      ],
      ignored_attachments: [],
    },
    // file_upload 必须正好一份且后缀匹配。
    {
      agents: [
        { agent_id: "evaluator", attachments: [{ file_id: "file_note", filename: "背景说明.pdf" }] },
        { agent_id: "reporter", attachments: [{ file_id: "file_case", filename: "检查表.xlsx" }] },
      ],
      ignored_attachments: [],
    },
    // 绑定 filename 必须与当前 canonical 消息一致，不能用旧标签冒名。
    {
      agents: [
        { agent_id: "evaluator", attachments: [{ file_id: "file_case", filename: "被篡改.xlsx" }] },
        { agent_id: "reporter", attachments: [{ file_id: "file_note", filename: "背景说明.pdf" }] },
      ],
      ignored_attachments: [],
    },
  ];
  for (const plan of invalidPlans) {
    assert.deepEqual(planAttachmentRouting(plan, contracts, files), {
      ready: false,
      inputFileIdsByAgent: {},
    });
  }
});

test("Guide 开工门与 batch payload 复用同一份附件路由裁决", () => {
  assert.match(guideSource, /planAttachmentRouting,/);
  assert.match(
    guideSource,
    /const attachmentRouting = planAttachmentRouting\([\s\S]*?attachmentRouting\.ready === true/,
  );
  assert.match(
    guideSource,
    /inputFileIds:\s*attachmentRouting\.inputFileIdsByAgent\[a\.agent_id\]\s*\|\|\s*\[\]/,
  );
  assert.doesNotMatch(
    guideSource,
    /plan\.agents\.length === 1\s*\?\s*matchingAgentFiles/,
    "openPlan 不得再按单 Agent + 后缀临时重算，否则 params 附件会被静默丢失",
  );
});

test("被剔除或截断的 orchestrate 方案一律视为不完整，不能降级开工", () => {
  const complete = {
    decision: "orchestrate",
    agents: [{ agent_id: "analyst" }],
    dropped_agents: [],
    capped: false,
  };
  assert.equal(planHasIncompleteOrchestration(complete), false);
  assert.equal(
    planHasIncompleteOrchestration({ ...complete, dropped_agents: ["missing_agent"] }),
    true,
  );
  assert.equal(planHasIncompleteOrchestration({ ...complete, capped: true }), true);
  assert.equal(planHasIncompleteOrchestration({ ...complete, truncated: true }), true);
  assert.equal(
    planHasIncompleteOrchestration({ ...complete, roster_truncated_count: 1 }),
    true,
    "未知但明确激活的 capped/truncated 信号同样必须 fail-closed",
  );
  assert.equal(
    planHasIncompleteOrchestration({ ...complete, roster_truncated_count: 0 }),
    false,
  );
  assert.equal(
    planHasIncompleteOrchestration({ decision: "refuse", dropped_agents: ["x"], capped: true }),
    false,
  );
});

test("Guide 对不完整编排只给同一 composer 恢复动作，开工门与 batch 双重阻断", () => {
  assert.match(
    guideSource,
    /planHasIncompleteOrchestration\(plan\) === true\) return false;[\s\S]*?attachmentRouting\.ready === true/,
    "planOpenable 必须在附件就绪之外独立阻断不完整编排",
  );
  assert.match(
    guideSource,
    /v-if="planHasIncompleteOrchestration\(m\.recommendation\)"[\s\S]*?@click="focusComposer"[\s\S]*?>继续说明或重新安排<\/button>/,
  );
  assert.match(
    guideSource,
    /方案有成员未能纳入，请继续说明或让系统重新安排/,
  );
  const footStart = guideSource.indexOf('<div v-if="idx === latestPlanIdx" class="plan-foot">');
  const footEnd = guideSource.indexOf("</div>", footStart);
  assert.ok(footStart >= 0 && footEnd > footStart);
  const planFoot = guideSource.slice(footStart, footEnd);
  const incompleteStart = planFoot.indexOf(
    'v-if="planHasIncompleteOrchestration(m.recommendation)"',
  );
  const reconciliationStart = planFoot.indexOf(
    'v-else-if="batchCreationNeedsReconciliation"',
  );
  const existingTasksStart = planFoot.indexOf(
    'v-else-if="planHasTasks(m.recommendation)"',
  );
  assert.ok(
    incompleteStart >= 0 &&
      reconciliationStart > incompleteStart &&
      existingTasksStart > reconciliationStart,
    "不完整门必须先于对账、开工和历史任务分支，旧任务只能保留只读展示",
  );
  const incompleteBranch = planFoot.slice(incompleteStart, reconciliationStart);
  assert.match(incompleteBranch, /@click="focusComposer"/);
  assert.doesNotMatch(
    incompleteBranch,
    /openPlan|openWorkbench|reconcileBatchCreation|createTasksBatch|<input|<textarea|<select|<form/,
    "恢复 CTA 只能聚焦既有 composer，不能藏第二条任务或字段入口",
  );
  assert.doesNotMatch(
    guideSource,
    /dropped_agents\.join/,
    "不得把内部成员标识作为恢复字段墙暴露给工程师",
  );
});

test("开工响应只允许修改提交时的会话与 retry 快照", () => {
  const submitted = { conversationId: "conv_A", retryOf: "task_failed_A" };
  assert.equal(
    conversationSnapshotMatches(submitted, {
      conversationId: "conv_A",
      routeConversationId: "conv_A",
      retryOf: "task_failed_A",
      requestedRetryOf: "task_failed_A",
    }),
    true,
  );
  assert.equal(
    conversationSnapshotMatches(submitted, {
      conversationId: "conv_B",
      routeConversationId: "conv_B",
      retryOf: "task_failed_A",
      requestedRetryOf: "task_failed_A",
    }),
    false,
    "A 的 batch 在途时切到 B，响应不得更新 B 的附件边界或动作状态",
  );
  assert.equal(
    conversationSnapshotMatches(submitted, {
      conversationId: "conv_A",
      routeConversationId: "conv_A",
      retryOf: "task_failed_B",
      requestedRetryOf: "task_failed_B",
    }),
    false,
    "同一会话切换失败恢复来源后，旧响应不得消费新 retry query",
  );

  const batchAwait = guideSource.indexOf("await createTasksBatch");
  const responseGuard = guideSource.indexOf("conversationSnapshotMatches", batchAwait);
  assert.ok(batchAwait >= 0 && responseGuard > batchAwait, "batch 返回后必须先复核提交快照");
  for (const sideEffect of [
    "attachmentSegmentBoundaryMs.value =",
    "retryPlanArmed.value = false",
    "ensureConversationTasksFeed();",
  ]) {
    assert.ok(
      guideSource.indexOf(sideEffect, batchAwait) > responseGuard,
      `${sideEffect} 必须位于响应快照 guard 之后`,
    );
  }
});

test("已挂载 Guide 对 c + retry_of 使用同一个串行导航事务", () => {
  assert.match(
    guideSource,
    /async function syncRouteContext\([\s\S]*?await validateRetryContext\(rawRetryOf\)[\s\S]*?await loadConversation\(conversationRouteId/,
    "必须先核对 retry 权威状态，再加载 query 指向的 concluded conversation",
  );
  assert.match(
    guideSource,
    /watch\(\s*\(\) => \[route\.query\.c, route\.query\.retry_of\]/,
    "c 与 retry_of 必须作为一个快照观察，不能由两个 watcher 竞跑",
  );
  assert.doesNotMatch(guideSource, /watch\(\s*\(\) => route\.query\.c,/);
  assert.doesNotMatch(guideSource, /watch\(\s*\(\) => route\.query\.retry_of,/);
  assert.match(guideSource, /const navigationSeq = \+\+routeNavigationSeq;/);
  assert.match(
    guideSource,
    /loadConversation\(id, \{ preserveOnFailure = false, isCurrent = \(\) => true \} = \{\}\)/,
  );
  assert.match(
    guideSource,
    /const conv = await getConversation\(id\);\s*if \(isCurrent\(\) !== true\) return false;/,
    "迟到的 A 会话读取必须在触碰 B 的 messages/status 前失效",
  );
});

test("新会话第一次发送用一次性内部路由绑定消费 c 更新，不重载并抹掉乐观轮次", () => {
  const token = { conversationId: "conv_new", retryOf: "task_failed", epoch: 7 };
  assert.equal(
    internalConversationRouteBindingMatches(token, "conv_new", "task_failed"),
    true,
  );
  assert.equal(
    internalConversationRouteBindingMatches(token, "conv_other", "task_failed"),
    false,
  );
  assert.equal(
    internalConversationRouteBindingMatches(token, "conv_new", "task_other"),
    false,
  );
  assert.match(
    guideSource,
    /armInternalRouteBinding\(conv\.id, submittedRetryOf\)[\s\S]*?await router\.replace/,
    "router.replace 前必须先挂一次性 token；只 await replace 仍会让 watcher 重载会话",
  );
  assert.match(
    guideSource,
    /if \(consumeInternalRouteBinding\(rawConversationId, rawRetryOf\)\) \{[\s\S]*?routeNavigationSeq \+= 1;[\s\S]*?retryValidationSeq \+= 1;[\s\S]*?return;\s*\}/,
    "内部 c + retry 镜像既不能重载空会话，也必须使旧外部路由与 retry 请求失效",
  );
});

test("任务创建时点切开工作段，旧附件不再永久阻断后续纯文本多 Agent 方案", () => {
  const oldFile = { id: "file_old", filename: "上一项工作.xlsx" };
  const newFile = { id: "file_new", filename: "本项工作.pdf" };
  const messages = [
    {
      role: "user",
      createdAt: "2026-08-01T10:00:00.000Z",
      attachments: [oldFile],
    },
    {
      role: "user",
      createdAt: "2026-08-01T10:02:00.000Z",
      attachments: [newFile],
    },
  ];
  const tasks = [{ id: "task_previous", created_at: "2026-08-01T10:01:00.000Z" }];

  assert.deepEqual(currentWorkSegmentFiles(messages, tasks), [
    { id: "file_new", name: "本项工作.pdf" },
  ]);
  assert.deepEqual(
    currentWorkSegmentFiles([messages[0]], tasks),
    [],
    "当前请求只有文字时，上一工作段附件必须完全退出路由上下文",
  );
  assert.deepEqual(
    currentWorkSegmentFiles([messages[0]], [], Date.parse("2026-08-01T10:01:00.000Z")),
    [],
    "batch 成功而 live feed 尚未刷新时，本地边界也必须立即生效",
  );
});

test("附件工作段只接受有确定时序的 canonical 用户轮次", () => {
  const taskBoundary = [{ created_at: "2026-08-01T10:01:00.000Z" }];
  const file = { id: "file_case", filename: "算例.xlsx" };
  assert.deepEqual(
    currentWorkSegmentFiles([
      { role: "user", createdAt: null, attachments: [file] },
      { role: "user", createdAt: "2026-08-01T10:02:00.000Z", attachments: [file], transient: true },
      { role: "user", createdAt: "2026-08-01T10:03:00.000Z", attachments: [file], persistenceUnknown: true },
    ], taskBoundary),
    [],
  );
  assert.deepEqual(
    currentWorkSegmentFiles([{ role: "user", attachments: [file, file] }], []),
    [{ id: "file_case", name: "算例.xlsx" }],
    "尚无任务边界时兼容先发附件再补充文字，并按真实 file id 去重",
  );
});

test("没有任务创建边界时，已完成的问答或拒绝也切开附件工作段", () => {
  const oldFile = { id: "file_old", filename: "上一件事.xlsx" };
  const oldTurn = {
    role: "user",
    createdAt: "2026-08-01T10:00:00.000Z",
    attachments: [oldFile],
  };
  const currentTurn = {
    role: "user",
    createdAt: "2026-08-01T10:02:00.000Z",
    content: "现在做另一项纯参数检查",
  };

  assert.deepEqual(
    currentWorkSegmentFiles([
      oldTurn,
      {
        role: "assistant",
        createdAt: "2026-08-01T10:01:00.000Z",
        recommendation: { findings: [{ summary: "已回答" }], refusals: [] },
      },
      currentTurn,
    ], []),
    [],
    "垂类问答已经交付后，旧附件不能黏住下一项没有任务记录的工作",
  );
  assert.deepEqual(
    currentWorkSegmentFiles([
      oldTurn,
      {
        role: "assistant",
        createdAt: "2026-08-01T10:01:00.000Z",
        recommendation: { decision: "refuse", reason: "无能力承接" },
      },
      currentTurn,
    ], []),
    [],
    "明确拒绝是上一工作段的终点，即使没有创建 task 也要切段",
  );
  assert.deepEqual(
    currentWorkSegmentFiles([
      oldTurn,
      { role: "assistant", createdAt: "2026-08-01T10:01:00.000Z", content: "还需要哪个工况？" },
      currentTurn,
    ], []),
    [{ id: "file_old", name: "上一件事.xlsx" }],
    "普通澄清不是工作段终点，不能让多轮补充丢失已保存附件",
  );
});

test("retry URL 只有经权威 failed 任务核对后才成为可用血缘", () => {
  assert.equal(
    verifiedFailedRetryLineage({ id: "task_failed", status: "failed" }, " task_failed "),
    "task_failed",
  );
  assert.equal(verifiedFailedRetryLineage({ id: "task_q", status: "queued" }, "task_q"), null);
  assert.equal(verifiedFailedRetryLineage({ id: "task_done", status: "completed" }, "task_done"), null);
  assert.equal(verifiedFailedRetryLineage({ id: "other", status: "failed" }, "task_failed"), null);
  assert.match(guideSource, /const task = await getTask\(candidate\)/);
  assert.match(guideSource, /retryContextChecking\.value/);
});

test("正式 Guide 壳不再暴露字段式资产抽屉入口", () => {
  assert.doesNotMatch(guideSource, /aria-label="沉淀本次工作"/);
  assert.doesNotMatch(guideSource, /@click="openAssetBuilder"/);
  assert.match(guideSource, /v-if="acceptanceMode && assetBuilderOpen"/);
});

test("自动开工对当前 JSON Schema 做递归校验，未知约束保守阻断", () => {
  const schema = {
    type: "object",
    additionalProperties: false,
    required: ["zeta", "label", "components", "boundary"],
    properties: {
      zeta: { type: "number", exclusiveMinimum: 0, exclusiveMaximum: 1 },
      label: { type: "string", minLength: 3, maxLength: 12, pattern: "^[A-Z]" },
      components: {
        type: "array",
        minItems: 1,
        maxItems: 3,
        items: { type: "string", minLength: 1 },
      },
      boundary: {
        type: "object",
        additionalProperties: false,
        required: ["condition"],
        properties: { condition: { type: "string", enum: ["fixed", "free"] } },
      },
    },
  };
  const valid = {
    zeta: 0.3,
    label: "CASE-A",
    components: ["wing"],
    boundary: { condition: "fixed" },
  };
  assert.equal(agentExecutionReady({ loaded: true, inputMode: "params", schema }, valid, []), true);
  assert.equal(agentExecutionReady({ loaded: true, inputMode: "params", schema }, { ...valid, zeta: 99 }, []), false);
  assert.equal(agentExecutionReady({ loaded: true, inputMode: "params", schema }, { ...valid, label: "bad" }, []), false);
  assert.equal(agentExecutionReady({ loaded: true, inputMode: "params", schema }, { ...valid, components: [3] }, []), false);
  assert.equal(agentExecutionReady({ loaded: true, inputMode: "params", schema }, { ...valid, boundary: {} }, []), false);
  assert.equal(
    agentExecutionReady(
      { loaded: true, inputMode: "params", schema: { ...schema, allOf: [] } },
      valid,
      [],
    ),
    false,
  );

  const falsyButSchemaValid = {
    type: "object",
    additionalProperties: false,
    required: ["count", "enabled", "tags", "emoji"],
    properties: {
      count: { type: "integer", minimum: 0 },
      enabled: { type: "boolean" },
      tags: { type: "array", maxItems: 0, items: { type: "string" } },
      emoji: { type: "string", minLength: 1, maxLength: 1 },
    },
  };
  assert.equal(
    agentExecutionReady(
      { loaded: true, inputMode: "params", schema: falsyButSchemaValid },
      { count: 0, enabled: false, tags: [], emoji: "✈️" },
      [],
    ),
    false,
    "✈️ 含两个 Unicode code point，不得被 UTF-16 长度或视觉字形误判为 maxLength=1",
  );
  assert.equal(
    agentExecutionReady(
      {
        loaded: true,
        inputMode: "params",
        schema: {
          ...falsyButSchemaValid,
          properties: { ...falsyButSchemaValid.properties, emoji: { type: "string", maxLength: 2 } },
        },
      },
      { count: 0, enabled: false, tags: [], emoji: "✈️" },
      [],
    ),
    true,
    "0、false 与 schema 允许的空数组都是有效输入，不能用字符串化猜测空值",
  );
  assert.equal(
    agentExecutionReady({ loaded: true, inputMode: "none" }, [], []),
    false,
    "非 object 输入形状必须 fail-closed",
  );
});

test("移动端方案主按钮满足 44px 触控目标", () => {
  assert.match(
    guideSource,
    /@media \(max-width: 640px\)[\s\S]*?\.open-plan-btn,[\s\S]*?\.workbench-btn[\s\S]*?min-height: 44px;/,
  );
});

test("失败回流血缘由系统写入恢复方案根任务，并在成功后消费 query", () => {
  assert.equal(retryLineageForPlanItem(" task_origin ", []), "task_origin");
  assert.equal(retryLineageForPlanItem("task_origin", [0]), null);
  assert.equal(retryLineageForPlanItem(" ", []), null);
  assert.equal(retryLineageForPlanItem("x".repeat(65), []), null);
  assert.match(guideSource, /retryOf: retryLineageForPlanItem\(approvedRetryOf, after\)/);
  assert.match(guideSource, /const submittedRetryOf = activeRetryOf\.value/);
  assert.match(guideSource, /retryOf: submittedRetryOf/);
  assert.match(guideSource, /retryUrlCleaned = await removeRetryQuery\(\)/);
  assert.match(guideSource, /任务已创建，但地址栏恢复标记未清理/);
  assert.match(taskApiSource, /retry_of:\s*it\.retryOf\s*\|\|\s*null/);
  assert.match(guideSource, /正在处理失败任务 · 审计血缘会自动保留/);
  assert.match(guideSource, /if \(activeRetryOf\.value && conv\.status !== "active"\)/);
});
