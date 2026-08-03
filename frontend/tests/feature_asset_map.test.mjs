import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  buildFeatureAssetMapView,
  candidatePresentation,
  packagePresentation,
} from "../src/utils/featureAssetMap.js";

const FEATURE_ASSET_MAP_COMPONENT = readFileSync(
  new URL("../src/components/FeatureAssetMapDisclosure.vue", import.meta.url),
  "utf8",
);

const VALID_MAP = {
  schema_version: "feature_asset_map.v1",
  source: {
    kind: "owner_scoped_cold_projection",
    owner_username: "engineer_a",
    owner_scoped: true,
    read_only: true,
  },
  summary: {
    capability_count: 1,
    asset_candidate_count: 1,
    accepted_candidate_count: 1,
    skill_package_count: 1,
    approved_skill_package_count: 0,
    unresolved_reference_count: 0,
  },
  functionality: {
    work_types: [{ id: "analysis", total_count: 1 }],
    domains: [{ id: "general", total_count: 1 }],
    capabilities: [
      {
        agent_id: "analysis_agent",
        name: "分析 Agent",
        summary: "整理工程依据",
        category: "analysis",
        domain: "general",
        specialty: null,
        launch_kind: "task",
        status: "active",
        maturity: "L1",
        requires_human_review: true,
        tool_count: 1,
        knowledge_scope_count: 0,
        unresolved_reference_count: 0,
        mock_tool_count: 0,
      },
    ],
  },
  assets: [
    {
      candidate_id: "asset_candidate_0123456789abcdef01234567",
      candidate_digest: `sha256:${"a".repeat(64)}`,
      revision: 1,
      state: "accepted",
      source: {
        task_id: "task_1",
        conversation_id: "conv_1",
        agent_id: "analysis_agent",
        finished_at: "2026-08-03T00:00:00Z",
      },
      task_pattern: {
        title: "工程分析任务模式",
        state: "approved_revision",
        digest: `sha256:${"b".repeat(64)}`,
      },
      skill: {
        name: "工程分析方法",
        description: "按证据完成分析",
        state: "approved_revision",
        digest: `sha256:${"c".repeat(64)}`,
      },
      skill_package: {
        id: "skill_package_0123456789abcdef01234567",
        name: "engineering-analysis",
        version: "0.1.0",
        package_digest: `sha256:${"d".repeat(64)}`,
        state: "pending_review",
        reuse_eligible: false,
      },
      workflow: {
        state: "not_formed",
        digest: null,
        gate: "需要组合证据",
      },
      agent: {
        state: "not_formed",
        digest: null,
        gate: "需要 Workflow 与晋级门",
      },
      updated_at: "2026-08-03T00:00:00Z",
    },
  ],
  effects: {
    writes_database: false,
    executes_work: false,
    registers_asset: false,
    promotes_asset: false,
  },
};

test("坏包络不会被渲染成空地图", () => {
  for (const invalid of [null, {}, { ...VALID_MAP, assets: null }]) {
    assert.deepEqual(buildFeatureAssetMapView(invalid), {
      available: false,
      summary: null,
      capabilities: [],
      assets: [],
    });
  }

  const notReadOnly = structuredClone(VALID_MAP);
  notReadOnly.source.read_only = false;
  assert.equal(buildFeatureAssetMapView(notReadOnly).available, false);

  const notOwnerScoped = structuredClone(VALID_MAP);
  notOwnerScoped.source.owner_scoped = false;
  assert.equal(buildFeatureAssetMapView(notOwnerScoped).available, false);

  const inventedAuthority = structuredClone(VALID_MAP);
  inventedAuthority.assets[0].can_launch = true;
  assert.equal(buildFeatureAssetMapView(inventedAuthority).available, false);

  const oversized = structuredClone(VALID_MAP);
  oversized.functionality.capabilities = Array.from(
    { length: 201 },
    (_, index) => ({
      ...structuredClone(VALID_MAP.functionality.capabilities[0]),
      agent_id: `analysis_agent_${index}`,
    }),
  );
  oversized.summary.capability_count = 201;
  assert.equal(buildFeatureAssetMapView(oversized).available, false);

  const oversizedAssets = structuredClone(VALID_MAP);
  oversizedAssets.assets = Array.from(
    { length: 101 },
    (_, index) => ({
      ...structuredClone(VALID_MAP.assets[0]),
      candidate_id: `asset_candidate_${String(index).padStart(24, "0")}`,
    }),
  );
  oversizedAssets.summary.asset_candidate_count = 101;
  oversizedAssets.summary.accepted_candidate_count = 101;
  oversizedAssets.summary.skill_package_count = 101;
  assert.equal(buildFeatureAssetMapView(oversizedAssets).available, false);

  const inventedFormation = structuredClone(VALID_MAP);
  inventedFormation.assets[0].workflow.state = "formed";
  assert.equal(buildFeatureAssetMapView(inventedFormation).available, false);
});

test("功能与资产只使用服务端明确投影，不发明已注册或已形成状态", () => {
  const view = buildFeatureAssetMapView(VALID_MAP);

  assert.equal(view.available, true);
  assert.equal(view.summary.capabilityCount, 1);
  assert.equal(view.summary.assetCandidateCount, 1);
  assert.deepEqual(view.capabilities[0], {
    id: "analysis_agent",
    name: "分析 Agent",
    summary: "整理工程依据",
    category: "analysis",
    domain: "general",
    launchKind: "task",
    status: "active",
    maturity: "L1",
    requiresHumanReview: true,
    unresolvedReferenceCount: 0,
    mockToolCount: 0,
  });
  assert.deepEqual(view.assets[0], {
    id: "asset_candidate_0123456789abcdef01234567",
    state: "accepted",
    taskPatternTitle: "工程分析任务模式",
    skillName: "工程分析方法",
    skillDescription: "按证据完成分析",
    packageName: "engineering-analysis",
    packageVersion: "0.1.0",
    packageState: "pending_review",
    reuseEligible: false,
    workflowState: "not_formed",
    agentState: "not_formed",
    sourceAgentId: "analysis_agent",
    updatedAt: "2026-08-03T00:00:00Z",
  });
});

test("资产状态显示锁定人审与未形成语义", () => {
  assert.deepEqual(candidatePresentation("accepted"), {
    label: "Candidate 已由人接受",
    shortLabel: "人已接受",
    className: "is-signed",
  });
  assert.deepEqual(packagePresentation("pending_review"), {
    label: "待独立人审",
    className: "is-pending",
  });
  assert.deepEqual(packagePresentation(null), {
    label: "尚未形成",
    className: "is-unformed",
  });
});

test("Candidate 与 Skill Package 拒绝态保持中性，不占真失败红槽", () => {
  assert.deepEqual(candidatePresentation("rejected"), {
    label: "Candidate 已驳回",
    shortLabel: "已驳回",
    className: "is-rejected",
  });
  assert.deepEqual(packagePresentation("rejected"), {
    label: "已驳回",
    className: "is-rejected",
  });

  const rejectedRule =
    FEATURE_ASSET_MAP_COMPONENT.match(/\.is-rejected\s*\{([^}]+)\}/)?.[1] || "";
  assert.match(rejectedRule, /color:\s*var\(--ink-soft\)/);
  assert.match(rejectedRule, /background:\s*var\(--hover-tint\)/);
  assert.doesNotMatch(rejectedRule, /trust-fail/);
});
