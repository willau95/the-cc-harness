import { api } from "./client";
import type { BulkBody, FleetResponse, SpawnBody } from "./types";

export const fleetApi = {
  list: () => api.get<FleetResponse>("/fleet"),
  pause: (agentId: string) => api.post<{ ok: boolean }>(`/agents/${encodeURIComponent(agentId)}/pause`),
  resume: (agentId: string) => api.post<{ ok: boolean }>(`/agents/${encodeURIComponent(agentId)}/resume`),
  kill: (agentId: string) => api.post<{ ok: boolean }>(`/agents/${encodeURIComponent(agentId)}/kill`),
  spawn: (body: SpawnBody) =>
    api.post<{ ok: boolean; agent_id?: string; folder?: string }>("/fleet/spawn", body),
  bulk: (action: BulkBody["action"], agent_ids: string[]) =>
    api.post<{ ok: boolean; results?: Record<string, unknown> }>("/fleet/bulk", { action, agent_ids }),
};
