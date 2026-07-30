const CATEGORY_IDS = [
  "tool_automation",
  "knowledge_qa",
  "structured_gen",
  "reasoning_assist",
];

function nonblank(value) {
  return typeof value === "string" && value.trim() !== "";
}

/**
 * 门户能力地图只计数服务端明确投影的分类。
 *
 * 非数组不是“零 Agent”，而是数据形状未知；未知分类单独计数，不能悄悄塞进
 * 任一已知分类。关系字段（members/boundaryCount/launch）全部从 agent 投影
 * 真实派生，fail-closed：limitations 非数组=边界待核（绝不压成 0）、mode
 * 缺失或畸形=发起方式待核（绝不回退成任务发起）。
 */
export function buildPortalCategoryOverview(agents) {
  if (!Array.isArray(agents)) {
    return { available: false, items: [], unknownCount: null };
  }

  const buckets = new Map(CATEGORY_IDS.map((id) => [id, []]));
  let unknownCount = 0;
  for (const agent of agents) {
    const category = agent?.category;
    if (buckets.has(category)) buckets.get(category).push(agent);
    else unknownCount += 1;
  }

  return {
    available: true,
    items: CATEGORY_IDS.map((id) => {
      const members = buckets.get(id);
      let boundaryCount = 0;
      let boundaryKnown = members.length > 0;
      const launch = { chat: 0, task: 0, unknown: 0 };
      for (const agent of members) {
        // 适用边界：任一成员字段畸形 → 全分类待核；空数组=如实声明零边界。
        if (boundaryKnown) {
          if (Array.isArray(agent?.limitations)) boundaryCount += agent.limitations.length;
          else boundaryKnown = false;
        }
        // 发起方式：interactive=对话；其他非空字符串=任务；缺失/畸形=待核。
        if (agent?.mode === "interactive") launch.chat += 1;
        else if (nonblank(agent?.mode)) launch.task += 1;
        else launch.unknown += 1;
      }
      return {
        id,
        count: members.length,
        // 人话优先：name 缺省回退 id（技术锚），双缺占位「未具名」不编造。
        members: members.map((agent) =>
          nonblank(agent?.name) ? agent.name.trim() : nonblank(agent?.id) ? agent.id.trim() : "未具名",
        ),
        boundaryCount: boundaryKnown ? boundaryCount : null,
        launch,
      };
    }),
    unknownCount,
  };
}
