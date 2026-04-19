import { api } from "./client";
import type { ProposalsResponse } from "./types";

export const proposalsApi = {
  list: (opts?: { status?: string; kind?: string }) => {
    const params = new URLSearchParams();
    if (opts?.status) params.set("status", opts.status);
    if (opts?.kind) params.set("kind", opts.kind);
    const qs = params.toString();
    return api.get<ProposalsResponse>(`/proposals${qs ? `?${qs}` : ""}`);
  },
  approve: (kind: string, pid: string) =>
    api.post<{ ok: boolean; record?: unknown }>(
      `/proposals/${encodeURIComponent(kind)}/${encodeURIComponent(pid)}/approve`,
    ),
  reject: (kind: string, pid: string) =>
    api.post<{ ok: boolean; record?: unknown }>(
      `/proposals/${encodeURIComponent(kind)}/${encodeURIComponent(pid)}/reject`,
    ),
};
