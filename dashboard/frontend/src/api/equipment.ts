import { api } from "./client";

export interface EquipmentItem {
  slug: string;
  kind: "skill" | "command" | "subagent" | "mcp" | "hook" | "repo" | "preamble";
  name: string;
  description?: string | null;
  source_url?: string | null;
  topics?: string[];
  trust?: "experimental" | "analyst_reviewed" | "human_verified" | "retracted";
  added_by?: string;
  added_at?: string;
}

export interface EquipmentDetail extends EquipmentItem {
  analysis?: string;
  path?: string;
}

export interface EquipmentListResponse {
  count: number;
  items: EquipmentItem[];
}

export interface EquipmentAddRequest {
  slug?: string;
  kind: EquipmentItem["kind"];
  source: string;
  name?: string;
  description?: string;
  topics?: string[];
  source_url?: string;
  trust?: EquipmentItem["trust"];
}

export const equipmentApi = {
  list: (kind?: string) =>
    api.get<EquipmentListResponse>(
      `/equipment${kind ? `?kind=${encodeURIComponent(kind)}` : ""}`,
    ),
  get: (slug: string) =>
    api.get<EquipmentDetail>(`/equipment/${encodeURIComponent(slug)}`),
  add: (req: EquipmentAddRequest) =>
    api.post<{ ok: boolean; meta: EquipmentDetail; error?: string }>(
      `/equipment/add`,
      req,
    ),
  search: (query: string) =>
    api.get<EquipmentListResponse>(
      `/equipment/search/${encodeURIComponent(query)}`,
    ),
};
