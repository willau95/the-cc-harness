import { api } from "./client";

export interface TranscriptEntry {
  ts?: string;
  role: "user" | "assistant" | "tool" | "system";
  kind: "prompt" | "text" | "thinking" | "tool_use" | "tool_result" | "hook";
  text?: string;
  tool_name?: string;
  tool_input_summary?: string;
  tool_input?: Record<string, unknown>;
  tool_id?: string;
  hook_name?: string;
  truncated?: boolean;
  is_error?: boolean;
}

export interface TranscriptResponse {
  agent_id: string;
  available: boolean;
  reason?: string;
  session?: { session_id: string; file_path: string; mtime: number; size_bytes: number };
  count?: number;
  timeline: TranscriptEntry[];
}

export interface ActivityResponse {
  activity: {
    tool_name?: string;
    tool_input_summary?: string;
    started_at?: string;
    finished_at?: string;
    status?: "running" | "idle";
  } | null;
}

export interface ChangedFile {
  path: string;
  status?: string;
  added?: number;
  deleted?: number;
  mtime?: number;
  size?: number;
  recent?: boolean;
}

export interface ChangesResponse {
  agent_id: string;
  available: boolean;
  reason?: string;
  kind?: "git" | "mtime";
  files?: ChangedFile[];
  count?: number;
}

export interface FileDiffResponse {
  path: string;
  kind: "diff" | "untracked";
  diff?: string;
  content?: string;
}

export const agentViewApi = {
  transcript: (id: string, limit = 300) =>
    api.get<TranscriptResponse>(`/agents/${encodeURIComponent(id)}/transcript?limit=${limit}`),
  activity: (id: string) =>
    api.get<ActivityResponse>(`/agents/${encodeURIComponent(id)}/activity`),
  changes: (id: string) =>
    api.get<ChangesResponse>(`/agents/${encodeURIComponent(id)}/changes`),
  fileDiff: (id: string, path: string) =>
    api.get<FileDiffResponse>(
      `/agents/${encodeURIComponent(id)}/file-diff?path=${encodeURIComponent(path)}`,
    ),
};
