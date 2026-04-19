import { api } from "./client";
import type { ArsenalItemDetail, ArsenalListResponse } from "./types";

export interface ArsenalAddBody {
  slug?: string;
  title: string;
  content: string;
  tags: string[];
  source_type: string;
  source_refs: string[];
}

export const arsenalApi = {
  list: (trust?: string, limit = 100) => {
    const params = new URLSearchParams();
    if (trust && trust !== "all") params.set("trust", trust);
    params.set("limit", String(limit));
    return api.get<ArsenalListResponse>(`/arsenal/list?${params.toString()}`);
  },
  get: (slug: string) => api.get<ArsenalItemDetail>(`/arsenal/${encodeURIComponent(slug)}`),
  add: (body: ArsenalAddBody) =>
    api.post<{ ok: boolean; meta?: Record<string, unknown> }>("/arsenal/add", body),
  setTrust: (slug: string, trust: string) =>
    api.post<{ ok: boolean; slug: string; trust: string }>(
      `/arsenal/${encodeURIComponent(slug)}/trust`,
      { trust },
    ),
};
