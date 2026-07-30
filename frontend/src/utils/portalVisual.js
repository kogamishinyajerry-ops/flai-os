const CATEGORY_IDS = [
  "tool_automation",
  "knowledge_qa",
  "structured_gen",
  "reasoning_assist",
];

/**
 * 门户能力地图只计数服务端明确投影的分类。
 *
 * 非数组不是“零 Agent”，而是数据形状未知；未知分类单独计数，不能悄悄塞进
 * 任一已知分类。
 */
export function buildPortalCategoryOverview(agents) {
  if (!Array.isArray(agents)) {
    return { available: false, items: [], unknownCount: null };
  }

  const counts = new Map(CATEGORY_IDS.map((id) => [id, 0]));
  let unknownCount = 0;
  for (const agent of agents) {
    const category = agent?.category;
    if (counts.has(category)) counts.set(category, counts.get(category) + 1);
    else unknownCount += 1;
  }

  return {
    available: true,
    items: CATEGORY_IDS.map((id) => ({ id, count: counts.get(id) })),
    unknownCount,
  };
}
