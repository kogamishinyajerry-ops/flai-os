import test from "node:test";
import assert from "node:assert/strict";

import { agentPickerDetail, filterAgentPickerItems } from "../src/utils/agentPickerVisual.js";

const AGENTS = [
  {
    id: "solver",
    name: "CFD 求解 Agent",
    category: "tool_automation",
    summary: "发起受控 OpenFOAM 求解",
    limitations: ["只支持登记过的算例"],
  },
  {
    id: "policy",
    name: "规范问答 Agent",
    category: "knowledge_qa",
    summary: "检索受控规范依据",
    limitations: ["不替代工程签字"],
  },
  {
    id: "future",
    name: "待分类 Agent",
    category: "future_category",
    summary: "试验能力",
    limitations: [],
  },
];

test("Agent 选择器保留服务端顺序，并可从名称、摘要与边界搜索", () => {
  const all = filterAgentPickerItems(AGENTS, "");
  assert.deepEqual(
    all.map((agent) => agent.id),
    ["solver", "policy", "future"],
  );

  assert.deepEqual(
    filterAgentPickerItems(AGENTS, "OpenFOAM").map((agent) => agent.id),
    ["solver"],
  );
  assert.deepEqual(
    filterAgentPickerItems(AGENTS, "不替代工程签字").map((agent) => agent.id),
    ["policy"],
  );
});

test("Agent 选择器优先展示一条边界，缺边界时才回退能力摘要", () => {
  assert.equal(agentPickerDetail(AGENTS[0]), "边界：只支持登记过的算例");
  assert.equal(
    agentPickerDetail({ summary: "只展示这一行能力摘要", limitations: [] }),
    "只展示这一行能力摘要",
  );
  assert.equal(agentPickerDetail({}), "能力说明待核");
});
