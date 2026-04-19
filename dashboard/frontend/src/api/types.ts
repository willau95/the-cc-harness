/** Types modeled after the FastAPI backend at dashboard/backend/main.py. */

export interface FleetAgent {
  agent_id: string;
  role?: string;
  name?: string;
  folder?: string;
  last_beat?: string | null;
  stale?: boolean;
  paused?: boolean;
  [key: string]: unknown;
}

export interface FleetResponse {
  count: number;
  agents: FleetAgent[];
}

export interface HarnessEvent {
  agent: string;
  ts: string;
  kind: string;
  [key: string]: unknown;
}

export interface EventsResponse {
  count: number;
  events: HarnessEvent[];
}

export interface AgentTask {
  task_id?: string;
  title?: string;
  status?: string;
  [key: string]: unknown;
}

export interface InboxItem {
  id?: string;
  kind?: string;
  payload?: unknown;
  ts?: string;
  [key: string]: unknown;
}

export interface AgentDetail {
  agent: FleetAgent;
  last_beat: string | null;
  stale: boolean;
  tasks: AgentTask[];
  recent_events: HarnessEvent[];
  inbox_pending: InboxItem[];
}

export interface ProjectSummary {
  project: string;
  state: Record<string, unknown>;
  member_count: number;
  members: string[];
}

export interface ProjectsResponse {
  count: number;
  projects: ProjectSummary[];
}

export interface ProjectDetailResponse {
  project: string;
  state: Record<string, unknown>;
  members: string[];
}

export interface Proposal {
  id?: string;
  pid?: string;
  kind: string;
  status: string;
  summary?: string;
  title?: string;
  agent?: string;
  ts?: string;
  created_at?: string;
  payload?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface ProposalsResponse {
  count: number;
  proposals: Proposal[];
}

export interface Stats {
  online: number;
  zombies: number;
  total_agents: number;
  pending_proposals: number;
  pending_budgets: number;
  projects: number;
  trust_distribution: Record<string, number>;
}

export interface SpawnBody {
  role: string;
  name: string;
  folder: string;
  initial_prompt?: string;
}

export interface BulkBody {
  action: "pause" | "resume" | "kill";
  agent_ids: string[];
}

export interface Role {
  slug: string;
  description: string;
}

export interface RolesResponse {
  roles: Role[];
}
