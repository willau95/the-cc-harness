import { api } from "./client";
import type { AgentDetail } from "./types";

export const agentsApi = {
  get: (agentId: string) => api.get<AgentDetail>(`/agents/${encodeURIComponent(agentId)}`),
};
