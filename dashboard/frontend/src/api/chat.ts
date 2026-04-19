import { api } from "./client";
import type { ChatThread } from "./types";

export const chatApi = {
  thread: (agentId: string, limit = 50) =>
    api.get<ChatThread>(
      `/chat/${encodeURIComponent(agentId)}?limit=${limit}`,
    ),
  send: (agentId: string, body: string, subject?: string, fromId?: string) =>
    api.post<{ ok: boolean; msg_id: string; envelope?: Record<string, unknown> }>(
      `/chat/${encodeURIComponent(agentId)}/send`,
      { body, subject, from_id: fromId },
    ),
};
