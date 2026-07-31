import { categoryLabel } from "./format.js";

const normalizedText = (value) => String(value ?? "").trim().toLocaleLowerCase("zh-CN");

const matchesQuery = (agent, query) => {
  if (!query) return true;
  const fields = [
    agent.id,
    agent.name,
    agent.summary,
    agent.category,
    categoryLabel(agent.category),
    ...(Array.isArray(agent.limitations) ? agent.limitations : []),
  ];
  return fields.some((field) => normalizedText(field).includes(query));
};

export function agentPickerDetail(agent) {
  const limitation = Array.isArray(agent?.limitations)
    ? agent.limitations.find((item) => normalizedText(item))
    : null;
  if (limitation) return `边界：${String(limitation).trim()}`;

  const summary = String(agent?.summary ?? "").trim();
  return summary || "能力说明待核";
}

export function filterAgentPickerItems(agents, query = "") {
  if (!Array.isArray(agents)) return [];
  const needle = normalizedText(query);
  return agents.filter(
    (agent) => agent && typeof agent === "object" && matchesQuery(agent, needle),
  );
}
