import assert from "node:assert/strict";
import test from "node:test";

import {
  buildAgentShellOverview,
  buildAgentShellNavigator,
  stageAgentPrompt,
} from "../src/utils/agentShell.js";

function unavailableSchema(filename) {
  return {
    state: "unavailable",
    reason: "file_missing",
    filename,
    property_count: 0,
    required_count: 0,
  };
}

function snapshot(overrides = {}) {
  return {
    schema_version: "agent_shell.v1",
    source: { kind: "registry_snapshot", read_only: true },
    summary: {
      agent_count: 3,
      work_type_count: 2,
      domain_count: 1,
      unresolved_reference_count: 1,
      defaulted_clearance_count: 1,
      mock_tool_reference_count: 1,
    },
    facets: {
      work_types: [
        {
          id: "tool_automation",
          total_count: 2,
          task_count: 1,
          conversation_count: 0,
          unknown_launch_count: 1,
        },
        {
          id: "knowledge_qa",
          total_count: 1,
          task_count: 1,
          conversation_count: 0,
          unknown_launch_count: 0,
        },
      ],
      domains: [
        {
          id: "fault_history",
          total_count: 1,
          task_count: 1,
          conversation_count: 0,
          unknown_launch_count: 0,
        },
      ],
      launch_kinds: [
        {
          id: "task",
          total_count: 2,
          task_count: 2,
          conversation_count: 0,
          unknown_launch_count: 0,
        },
        {
          id: "conversation",
          total_count: 0,
          task_count: 0,
          conversation_count: 0,
          unknown_launch_count: 0,
        },
        {
          id: "unknown",
          total_count: 1,
          task_count: 0,
          conversation_count: 0,
          unknown_launch_count: 1,
        },
      ],
    },
    agents: [
      {
        identity: {
          agent_id: "performance_disk_agent",
          name: "性能盘批量计算 Agent（模拟阶段）",
          version: "0.1.0",
          summary: "批量核算并生成可审阅汇总",
        },
        classification: {
          category: "tool_automation",
          domain: null,
          specialty: null,
          usefulness_level: null,
        },
        capability: {
          input: { type: "params", schema: unavailableSchema("input_schema.json") },
          output: {
            formats: [".json"],
            schema: unavailableSchema("output_schema.json"),
          },
          tools: [
            {
              id: "mock_echo",
              name: "Mock Echo",
              version: "0.1.0",
              state: "resolved",
              mock: true,
              output_classification: "internal",
            },
          ],
          knowledge_scopes: [],
        },
        trust: {
          status: "draft",
          maturity: "L0",
          limitations: ["不替代工程师签发"],
          visibility: "all",
          allowed_roles: ["business_user"],
          clearance: { effective: "internal", source: "defaulted" },
          requires_human_review: false,
          evidence: { required: false, kinds: [] },
        },
        launch: { kind: "task" },
      },
      {
        identity: {
          agent_id: "fault_history_agent",
          name: "故障史问答 Agent",
          version: "0.1.0",
          summary: "查找故障案例和可核验证据",
        },
        classification: {
          category: "knowledge_qa",
          domain: "fault_history",
          specialty: "按故障现象定位历史案例",
          usefulness_level: "L2",
        },
        capability: {
          input: { type: "params", schema: unavailableSchema("input_schema.json") },
          output: {
            formats: [".json"],
            schema: unavailableSchema("output_schema.json"),
          },
          tools: [],
          knowledge_scopes: [
            {
              id: "missing_fault_cases",
              name: null,
              kind: null,
              confidentiality: null,
              state: "unresolved",
            },
          ],
        },
        trust: {
          status: "draft",
          maturity: "L0",
          limitations: ["无受控依据时拒答"],
          visibility: "department_trial",
          allowed_roles: ["business_user"],
          clearance: { effective: "internal", source: "declared" },
          requires_human_review: true,
          evidence: { required: true, kinds: ["fault_case"] },
        },
        launch: { kind: "task" },
      },
      {
        identity: {
          agent_id: "malformed_launch",
          name: "启动方式待核 Agent",
          version: "0.1.0",
          summary: "不应进入可选列表",
        },
        classification: {
          category: "tool_automation",
          domain: null,
          specialty: null,
          usefulness_level: null,
        },
        capability: {
          input: { type: null, schema: unavailableSchema("input_schema.json") },
          output: {
            formats: [],
            schema: unavailableSchema("output_schema.json"),
          },
          tools: [],
          knowledge_scopes: [],
        },
        trust: {
          status: "draft",
          maturity: "L0",
          limitations: [],
          visibility: null,
          allowed_roles: [],
          clearance: { effective: "internal", source: "invalid_defaulted" },
          requires_human_review: null,
          evidence: { required: null, kinds: [] },
        },
        launch: { kind: "unknown" },
      },
    ],
    diagnostics: [],
    ...overrides,
  };
}

test("invalid snapshot stays unavailable instead of becoming a fake empty catalog", () => {
  const result = buildAgentShellNavigator({ agents: [] });
  assert.equal(result.available, false);
  assert.equal(result.totalCount, null);
  assert.equal(result.visibleCount, null);
  assert.deepEqual(result.items, []);
  assert.deepEqual(result.workTypes, []);

  const malformedAgent = buildAgentShellNavigator({
    ...snapshot(),
    agents: [{}],
  });
  assert.equal(malformedAgent.available, false);
  assert.equal(malformedAgent.totalCount, null);

  const malformedFacets = buildAgentShellNavigator({
    ...snapshot(),
    facets: {},
  });
  assert.equal(malformedFacets.available, false);
  assert.equal(malformedFacets.totalCount, null);

  const malformedFacetCount = structuredClone(snapshot());
  malformedFacetCount.facets.work_types[0].total_count = "1";
  const malformedFacetResult = buildAgentShellNavigator(malformedFacetCount);
  assert.equal(malformedFacetResult.available, false);
  assert.equal(malformedFacetResult.totalCount, null);

  const malformedLaunchFacets = structuredClone(snapshot());
  malformedLaunchFacets.facets.launch_kinds[1].id = "task";
  const malformedLaunchResult = buildAgentShellNavigator(malformedLaunchFacets);
  assert.equal(malformedLaunchResult.available, false);
  assert.equal(malformedLaunchResult.totalCount, null);
});

test("only exact task launch records enter the selectable Agent list", () => {
  const malformedStatus = structuredClone(snapshot().agents[0]);
  malformedStatus.identity.agent_id = "status_unknown";
  malformedStatus.identity.name = "状态待核 Agent";
  malformedStatus.trust.status = null;
  const disabled = structuredClone(snapshot().agents[0]);
  disabled.identity.agent_id = "disabled_agent";
  disabled.identity.name = "已停用 Agent";
  disabled.trust.status = "disabled";
  const result = buildAgentShellNavigator({
    ...snapshot(),
    agents: [...snapshot().agents, malformedStatus, disabled],
  });
  assert.equal(result.available, true);
  assert.equal(result.totalCount, 2);
  assert.equal(result.visibleCount, 2);
  assert.deepEqual(
    result.items.map((item) => item.id),
    ["performance_disk_agent", "fault_history_agent"],
  );
  assert.deepEqual(
    result.workTypes.map((item) => [item.id, item.count]),
    [["tool_automation", 1], ["knowledge_qa", 1]],
  );
  assert.equal(
    result.items.some((item) => item.id === "status_unknown"),
    false,
    "unknown status must fail closed instead of becoming selectable",
  );
  assert.equal(
    result.items.some((item) => item.id === "disabled_agent"),
    false,
    "disabled status must not inflate candidate counts",
  );
});

test("work type and text filters use server relations without inventing counts", () => {
  const byType = buildAgentShellNavigator(snapshot(), { workType: "knowledge_qa" });
  assert.deepEqual(byType.items.map((item) => item.id), ["fault_history_agent"]);

  const bySpecialty = buildAgentShellNavigator(snapshot(), { query: "历史案例" });
  assert.deepEqual(bySpecialty.items.map((item) => item.id), ["fault_history_agent"]);

  const invalidType = buildAgentShellNavigator(snapshot(), { workType: "not_declared" });
  assert.equal(invalidType.selectionInvalid, true);
  assert.deepEqual(invalidType.items, []);
});

test("unresolved references and literal trust booleans remain explicit", () => {
  const result = buildAgentShellNavigator(snapshot());
  const fault = result.items.find((item) => item.id === "fault_history_agent");
  assert.equal(fault.referenceState, "unresolved");
  assert.equal(fault.unresolvedReferenceCount, 1);
  assert.equal(fault.reviewRequired, true);
  assert.equal(fault.evidenceRequired, true);

  const mocked = result.items.find((item) => item.id === "performance_disk_agent");
  assert.equal(mocked.mockToolCount, 1, "mock tool truth must survive into the shell");

  const unknownMockSnapshot = structuredClone(snapshot());
  unknownMockSnapshot.agents[0].capability.tools[0].mock = null;
  const unknownMock = buildAgentShellNavigator(unknownMockSnapshot).items.find(
    (item) => item.id === "performance_disk_agent",
  );
  assert.equal(unknownMock.mockToolCount, 0);
  assert.equal(unknownMock.unknownMockToolCount, 1, "unknown mock truth must stay pending");

  const malformed = buildAgentShellNavigator({
    ...snapshot(),
    agents: [snapshot().agents[2]],
    facets: {
      ...snapshot().facets,
      work_types: [
        {
          id: "tool_automation",
          total_count: 1,
          task_count: 1,
          conversation_count: 0,
          unknown_launch_count: 0,
        },
      ],
    },
  });
  assert.equal(malformed.totalCount, 0, "unknown launch must never be counted as selectable");
});

test("staging an Agent produces a visible draft and never an action payload", () => {
  const agent = buildAgentShellNavigator(snapshot()).items[0];
  assert.equal(stageAgentPrompt(agent), "我想用「性能盘批量计算 Agent（模拟阶段）」做：");
  assert.equal(stageAgentPrompt(null), null);
});

test("portal overview renders server facet counts and keeps malformed summary unavailable", () => {
  const overview = buildAgentShellOverview(snapshot());
  assert.equal(overview.available, true);
  assert.deepEqual(overview.items[0], {
    id: "tool_automation",
    total: 2,
    task: 1,
    conversation: 0,
    unknown: 1,
  });
  assert.equal(overview.domainCount, 1);
  assert.equal(overview.unresolvedReferenceCount, 1);
  assert.equal(overview.defaultedClearanceCount, 1);
  assert.equal(overview.mockToolReferenceCount, 1);
  assert.equal(overview.unknownMockToolReferenceCount, 0);

  const unknownMockSnapshot = structuredClone(snapshot());
  unknownMockSnapshot.agents[0].capability.tools[0].mock = null;
  assert.equal(
    buildAgentShellOverview(unknownMockSnapshot).unknownMockToolReferenceCount,
    1,
  );

  const invalid = buildAgentShellOverview({ ...snapshot(), summary: {} });
  assert.equal(invalid.available, false);
  assert.equal(invalid.domainCount, null);
  assert.equal(invalid.mockToolReferenceCount, null);
  assert.equal(invalid.unknownMockToolReferenceCount, null);
});
