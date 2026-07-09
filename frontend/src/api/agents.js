import { request } from "./client";

export const listAgents = () => request("/api/agents");
export const getAgent = (agentId) => request(`/api/agents/${agentId}`);
