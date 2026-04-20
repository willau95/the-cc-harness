import { api } from "./client";
import type { MachinesResponse } from "./types";

export const machinesApi = {
  list: () => api.get<MachinesResponse>("/machines"),
  ping: (name: string) =>
    api.post<{ ok: boolean; machine: string; latency_ms: number; stdout: string; stderr: string }>(
      `/machines/${encodeURIComponent(name)}/ping`,
      {},
    ),
  bootstrap: (name: string) =>
    api.post<{ ok: boolean; peers_count?: number }>(
      `/machines/${encodeURIComponent(name)}/bootstrap`,
      {},
    ),
  installHarness: (name: string) =>
    api.post<{ ok: boolean; action: "update" | "clone"; machine: string; tail: string; stderr: string }>(
      `/machines/${encodeURIComponent(name)}/install-harness`,
      {},
    ),
};
