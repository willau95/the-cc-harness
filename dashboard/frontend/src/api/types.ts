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
  type: string;
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

export interface ProjectMember {
  agent_id: string;
  role?: string;
  ts?: string;
  kind?: string;
  [key: string]: unknown;
}

export interface ProjectSummary {
  project: string;
  state: Record<string, unknown>;
  member_count: number;
  members: ProjectMember[];
}

export interface ProjectsResponse {
  count: number;
  projects: ProjectSummary[];
}

export interface ProjectDetailResponse {
  project: string;
  state: Record<string, unknown>;
  members: ProjectMember[];
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
  machine?: string;
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

// ─── Arsenal ────────────────────────────────────────────────────────────────

export interface ArsenalItem {
  slug: string;
  title: string;
  trust: string;
  produced_by?: string | null;
  produced_at?: string | null;
  source_refs?: string | null;
  tags?: string | null;
  chain_depth?: number | null;
  [key: string]: unknown;
}

export interface ArsenalListResponse {
  count: number;
  items: ArsenalItem[];
  trust_distribution: Record<string, number>;
}

export interface ArsenalItemDetail {
  slug: string;
  title: string;
  trust: string;
  content?: string;
  tags?: string | string[] | null;
  source_type?: string | null;
  source_refs?: string | string[] | null;
  produced_by?: string | null;
  produced_at?: string | null;
  verification_status?: string | null;
  chain_depth?: number | null;
  derived_from?: string | string[] | null;
  machine?: string | null;
  [key: string]: unknown;
}

// ─── Tasks ──────────────────────────────────────────────────────────────────

export interface TaskItem {
  task_id: string;
  state: string;
  original_goal?: string | null;
  next_step?: string | null;
  blocked_on?: string | null;
  task_budget?: Record<string, unknown> | null;
  agent_id?: string | null;
  role?: string | null;
  folder?: string | null;
  project?: string | null;
  ts?: string | null;
  [key: string]: unknown;
}

export interface TasksResponse {
  count: number;
  tasks: TaskItem[];
}

// ─── Chat ───────────────────────────────────────────────────────────────────

export interface ChatMessage {
  msg_id: string;
  from?: string | null;
  to?: string | null;
  subject?: string | null;
  body?: string | null;
  created_at?: string | null;
  direction: "inbound" | "outbound";
  [key: string]: unknown;
}

export interface ChatThread {
  agent_id: string;
  count: number;
  thread: ChatMessage[];
}

// ─── Machines ───────────────────────────────────────────────────────────────

export interface Machine {
  name: string;
  user?: string | null;
  ip?: string | null;
  is_local?: boolean;
  [key: string]: unknown;
}

export interface MachinesResponse {
  count: number;
  machines: Machine[];
  fleet_ssh_available: boolean;
}
