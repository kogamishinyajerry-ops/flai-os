import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import {
  GUIDE_DAG_CONTRACT,
  guidePlanAgents,
  guidePlanAllowsManualCreate,
  guidePlanTaskMappingIssue,
  indexGuidePlanTasks,
  tasksForGuidePlanAgent,
} from "../src/utils/guidePlan.js";


test("versioned DAG nodes remain in backend topological order", () => {
  const nodes = [{ node_id: "prepare" }, { node_id: "review" }];
  const plan = {
    decision: "orchestrate",
    contract: "guide_dag.v1",
    nodes,
    agents: [{ agent_id: "legacy_must_not_win" }],
  };

  assert.equal(guidePlanAgents(plan), nodes);
  assert.deepEqual(guidePlanAgents(plan).map((node) => node.node_id), ["prepare", "review"]);
});


test("legacy agents stay compatible and non-plans project an empty roster", () => {
  const agents = [{ agent_id: "legacy" }];
  assert.equal(guidePlanAgents({ decision: "orchestrate", agents }), agents);
  assert.deepEqual(guidePlanAgents({ decision: "refuse", agents }), []);
  assert.deepEqual(guidePlanAgents(null), []);
});


function dagPlan(nodeTasks) {
  return {
    decision: "orchestrate",
    contract: GUIDE_DAG_CONTRACT,
    nodes: [
      { node_id: "prepare", agent_id: "deterministic" },
      { node_id: "review", agent_id: "reviewer", depends_on: ["prepare"] },
    ],
    execution: {
      status: "dispatched",
      graph_version: GUIDE_DAG_CONTRACT,
      node_tasks: nodeTasks,
    },
  };
}


test("DAG task projection uses exact node_id to task_id bindings, never agent fallback", () => {
  const plan = dagPlan([
    { node_id: "prepare", agent_id: "deterministic", task_id: "task-p" },
    { node_id: "review", agent_id: "reviewer", task_id: "task-r" },
  ]);
  const tasks = [
    { id: "task-p", agent_id: "deterministic" },
    { id: "task-r", agent_id: "reviewer" },
    { id: "task-unrelated-same-agent", agent_id: "reviewer" },
  ];
  const index = indexGuidePlanTasks(plan, tasks);

  assert.equal(index.valid, true);
  assert.deepEqual(tasksForGuidePlanAgent(index, plan.nodes[0]).map((task) => task.id), ["task-p"]);
  assert.deepEqual(tasksForGuidePlanAgent(index, plan.nodes[1]).map((task) => task.id), ["task-r"]);
  assert.deepEqual([...index.claimedTaskIds].sort(), ["task-p", "task-r"]);
  assert.equal(index.claimedTaskIds.has("task-unrelated-same-agent"), false);
});


test("missing, duplicate, or inconsistent DAG mappings fail closed for the whole graph", () => {
  const cases = [
    dagPlan([{ node_id: "prepare", agent_id: "deterministic", task_id: "task-p" }]),
    dagPlan([
      { node_id: "prepare", agent_id: "deterministic", task_id: "same" },
      { node_id: "review", agent_id: "reviewer", task_id: "same" },
    ]),
    dagPlan([
      { node_id: "prepare", agent_id: "wrong-agent", task_id: "task-p" },
      { node_id: "review", agent_id: "reviewer", task_id: "task-r" },
    ]),
  ];

  for (const plan of cases) {
    const index = indexGuidePlanTasks(plan, [
      { id: "task-p", agent_id: "deterministic" },
      { id: "task-r", agent_id: "reviewer" },
      { id: "same", agent_id: "reviewer" },
    ]);
    assert.equal(index.valid, false);
    assert.deepEqual(tasksForGuidePlanAgent(index, plan.nodes[0]), []);
    assert.deepEqual(tasksForGuidePlanAgent(index, plan.nodes[1]), []);
    assert.deepEqual([...index.claimedTaskIds], []);
  }
});


test("a versioned DAG rejects duplicate agent ids even when node ids are distinct", () => {
  const plan = dagPlan([
    { node_id: "prepare", agent_id: "deterministic", task_id: "task-p" },
    { node_id: "review", agent_id: "deterministic", task_id: "task-r" },
  ]);
  plan.nodes[1].agent_id = "deterministic";
  const index = indexGuidePlanTasks(plan, [
    { id: "task-p", agent_id: "deterministic" },
    { id: "task-r", agent_id: "deterministic" },
  ]);

  assert.equal(index.valid, false);
  assert.match(index.reason, /Agent.*重复/);
  assert.deepEqual([...index.claimedTaskIds], []);
});


test("a mapped task row with the wrong agent fails closed instead of being attached by id", () => {
  const plan = dagPlan([
    { node_id: "prepare", agent_id: "deterministic", task_id: "task-p" },
    { node_id: "review", agent_id: "reviewer", task_id: "task-r" },
  ]);
  const index = indexGuidePlanTasks(plan, [
    { id: "task-p", agent_id: "reviewer" },
    { id: "task-r", agent_id: "reviewer" },
  ]);
  assert.equal(index.valid, false);
  assert.match(index.reason, /Agent/);
});


test("a mapped task may arrive one polling tick later without enabling Agent fallback", () => {
  const plan = dagPlan([
    { node_id: "prepare", agent_id: "deterministic", task_id: "task-p" },
    { node_id: "review", agent_id: "reviewer", task_id: "task-r" },
  ]);
  const index = indexGuidePlanTasks(plan, [{ id: "unbound", agent_id: "reviewer" }]);

  assert.equal(index.valid, true);
  assert.deepEqual(tasksForGuidePlanAgent(index, plan.nodes[0]), []);
  assert.deepEqual(tasksForGuidePlanAgent(index, plan.nodes[1]), []);
  assert.deepEqual([...index.claimedTaskIds].sort(), ["task-p", "task-r"]);
});


test("legacy plans alone retain agent_id task grouping and manual-create fallback", () => {
  const legacy = {
    decision: "orchestrate",
    agents: [{ agent_id: "legacy" }],
  };
  const tasks = [
    { id: "legacy-1", agent_id: "legacy" },
    { id: "other", agent_id: "other" },
  ];
  const index = indexGuidePlanTasks(legacy, tasks);
  assert.equal(index.mode, "legacy");
  assert.equal(index.valid, true);
  assert.deepEqual(tasksForGuidePlanAgent(index, legacy.agents[0]), [tasks[0]]);
  assert.equal(guidePlanAllowsManualCreate(legacy), true);
  assert.equal(guidePlanAllowsManualCreate(dagPlan([])), false);
  assert.equal(guidePlanAllowsManualCreate({ ...dagPlan([]), execution: null }), false);
});


test("a dispatched legacy plan binds only its receipt task id", () => {
  const legacy = {
    decision: "orchestrate",
    agents: [{ agent_id: "legacy" }],
    execution: { status: "dispatched", task_ids: ["task-old"] },
  };
  const tasks = [
    { id: "task-new", agent_id: "legacy" },
    { id: "task-old", agent_id: "legacy" },
  ];
  const index = indexGuidePlanTasks(legacy, tasks);

  assert.equal(index.valid, true);
  assert.deepEqual(tasksForGuidePlanAgent(index, legacy.agents[0]).map((task) => task.id), ["task-old"]);
  assert.deepEqual([...index.claimedTaskIds], ["task-old"]);
});


test("a malformed dispatched legacy receipt fails closed", () => {
  const cases = [
    { status: "dispatched", task_ids: [] },
    { status: "dispatched", task_ids: ["task-old", "task-new"] },
    { status: "dispatched", task_ids: ["task-old", "task-old"] },
    { status: "pending", task_ids: ["task-old"] },
  ];
  for (const execution of cases) {
    const legacy = {
      decision: "orchestrate",
      agents: [{ agent_id: "legacy" }],
      execution,
    };
    const index = indexGuidePlanTasks(legacy, [{ id: "task-old", agent_id: "legacy" }]);
    assert.equal(index.valid, false);
    assert.deepEqual(tasksForGuidePlanAgent(index, legacy.agents[0]), []);
    assert.deepEqual([...index.claimedTaskIds], []);
  }
});


test("unknown versioned contracts never fall back to legacy Agent matching or manual creation", () => {
  const unknown = {
    decision: "orchestrate",
    contract: "guide_dag.v2",
    nodes: [{ node_id: "future", agent_id: "legacy" }],
    agents: [{ agent_id: "legacy" }],
  };
  const index = indexGuidePlanTasks(unknown, [{ id: "task-1", agent_id: "legacy" }]);

  assert.deepEqual(guidePlanAgents(unknown), []);
  assert.equal(guidePlanAllowsManualCreate(unknown), false);
  assert.equal(index.valid, false);
  assert.equal(index.mode, "unsupported");
  assert.deepEqual(tasksForGuidePlanAgent(index, unknown.agents[0]), []);

  const claimedDispatched = {
    ...unknown,
    execution: { status: "dispatched", task_ids: ["task-1"] },
  };
  assert.match(guidePlanTaskMappingIssue(claimedDispatched, []), /未知版本/);
});


test("malformed falsy contracts and empty DAGs fail closed", () => {
  for (const contract of [null, ""]) {
    const malformed = {
      decision: "orchestrate",
      contract,
      agents: [{ agent_id: "legacy" }],
    };
    assert.deepEqual(guidePlanAgents(malformed), []);
    assert.equal(guidePlanAllowsManualCreate(malformed), false);
    assert.equal(indexGuidePlanTasks(malformed, []).valid, false);
  }

  const emptyDag = {
    decision: "orchestrate",
    contract: GUIDE_DAG_CONTRACT,
    nodes: [],
    execution: {
      status: "dispatched",
      graph_version: GUIDE_DAG_CONTRACT,
      node_tasks: [],
    },
  };
  assert.equal(indexGuidePlanTasks(emptyDag, []).valid, false);
});


test("Guide and Workbench wire roster tasks through the authoritative projection", async () => {
  const [guide, workbench] = await Promise.all([
    readFile(new URL("../src/views/GuidePage.vue", import.meta.url), "utf8"),
    readFile(new URL("../src/views/WorkbenchSession.vue", import.meta.url), "utf8"),
  ]);

  assert.match(guide, /indexGuidePlanTasks\(plan, conversationTasks\.value\)/);
  assert.match(guide, /guidePlanTaskMappingIssue\(plan, conversationTasks\.value\)/);
  assert.match(guide, /tasksForGuidePlanAgent\(index, agent\)/);
  assert.match(guide, /guidePlanAllowsManualCreate\(m\.recommendation\)/);
  assert.match(
    guide,
    /conversationStatus === ['"]active['"]\s*&&\s*!m\.recommendation\.execution/,
  );
  assert.match(
    guide,
    /function createOneTask\(agent, plan\)[\s\S]*conversationStatus\.value !== ['"]active['"]/,
  );
  assert.doesNotMatch(guide, /conversationTasks\.value\.filter\(\(t\) => t\.agent_id === agent\.agent_id\)/);

  assert.match(workbench, /indexGuidePlanTasks\(plan\.value, memberTasks\.value\)/);
  assert.match(workbench, /guidePlanTaskMappingIssue\(plan\.value, memberTasks\.value\)/);
  assert.match(workbench, /tasksForGuidePlanAgent\(planTaskIndex\.value, agent\)/);
  assert.match(workbench, /planTaskIndex\.value\.claimedTaskIds\.has\(t\.id\)/);
  assert.match(workbench, /guidePlanAllowsManualCreate\(plan\)/);
  assert.doesNotMatch(workbench, /memberTasks\.value\.filter\(\(t\) => t\.agent_id === agent\.agent_id\)/);
});


test("dispatched DAG copy states roots are queued and leaves still require human signoff", async () => {
  const [guide, workbench] = await Promise.all([
    readFile(new URL("../src/views/GuidePage.vue", import.meta.url), "utf8"),
    readFile(new URL("../src/views/WorkbenchSession.vue", import.meta.url), "utf8"),
  ]);
  const contractCopy = "任务图已原子创建，根节点已入队，下游等待依赖推进，叶节点仍需真人签发";

  assert.match(guide, new RegExp(contractCopy));
  assert.match(workbench, new RegExp(contractCopy));
});
