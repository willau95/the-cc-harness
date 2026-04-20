/**
 * Canonical status & priority color definitions (ported from paperclip).
 */

export const issueStatusIcon: Record<string, string> = {
  backlog: "text-muted-foreground border-muted-foreground",
  todo: "text-blue-600 border-blue-600 dark:text-blue-400 dark:border-blue-400",
  in_progress: "text-yellow-600 border-yellow-600 dark:text-yellow-400 dark:border-yellow-400",
  in_review: "text-violet-600 border-violet-600 dark:text-violet-400 dark:border-violet-400",
  done: "text-green-600 border-green-600 dark:text-green-400 dark:border-green-400",
  cancelled: "text-neutral-500 border-neutral-500",
  blocked: "text-red-600 border-red-600 dark:text-red-400 dark:border-red-400",
};

export const issueStatusIconDefault = "text-muted-foreground border-muted-foreground";

export const statusBadge: Record<string, string> = {
  // Agent statuses
  online: "bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300",
  active: "bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300",
  running: "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/50 dark:text-cyan-300",
  paused: "bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300",
  idle: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-300",
  stale: "bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300",
  offline: "bg-neutral-200 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300",
  archived: "bg-muted text-muted-foreground",

  // Run / Proposal statuses
  failed: "bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300",
  succeeded: "bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300",
  error: "bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300",
  terminated: "bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300",
  pending: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-300",

  // Approval statuses
  critic_approved: "bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300",
  pending_approval: "bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300",
  approved: "bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300",
  rejected: "bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300",

  // Generic
  backlog: "bg-muted text-muted-foreground",
  todo: "bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300",
  in_progress: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-300",
  done: "bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300",
  cancelled: "bg-muted text-muted-foreground",
};

export const statusBadgeDefault = "bg-muted text-muted-foreground";

export const agentStatusDot: Record<string, string> = {
  running: "bg-cyan-400 animate-pulse",
  online: "bg-green-400",
  active: "bg-green-400",
  paused: "bg-yellow-400",
  idle: "bg-yellow-400",
  stale: "bg-red-400 animate-pulse",
  offline: "bg-neutral-400",
  pending: "bg-blue-400 animate-pulse",
  error: "bg-red-400",
  archived: "bg-neutral-400",
};

export const agentStatusDotDefault = "bg-neutral-400";

/**
 * Trust-level badge colors for arsenal items.
 * verified=green, peer_verified=cyan, agent_summary=gray,
 * hypothesis=yellow, retracted=red, human_verified=emerald.
 */
export const trustBadge: Record<string, string> = {
  verified: "bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300",
  human_verified: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300",
  peer_verified: "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/50 dark:text-cyan-300",
  agent_summary: "bg-muted text-muted-foreground",
  hypothesis: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-300",
  retracted: "bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300",
};

export const trustBadgeDefault = "bg-muted text-muted-foreground";

/**
 * Derive an agent status label from registry/heartbeat/liveness fields.
 *
 * Semantics:
 *   offline  — claude process is demonstrably dead (session.pid cant be
 *              signaled) → OR → we have no PID AND heartbeat is stale
 *   paused   — .harness/paused sentinel present (human clicked Pause)
 *   idle     — claude IS alive but no skill-tool call / hook fire in the
 *              heartbeat window. Normal when you leave a claude open but
 *              don't chat with it. Yellow, not alarming.
 *   stale    — unknown liveness (remote or pre-PID agent) AND heartbeat
 *              stale. Red.
 *   running  — has an active task checkpoint
 *   online   — heartbeat fresh, no flags
 */
export function deriveAgentStatus(ag: {
  stale?: boolean;
  paused?: boolean;
  hasActiveTask?: boolean;
  process_alive?: boolean | null;
  last_beat?: string | null;
}): string {
  if (ag.paused) return "paused";
  // Fresh heartbeat overrides a negative PID check. This is the case for
  // `claude --print` driven agents (captain orchestration): PID exits after
  // each invocation but heartbeat is current; they're clearly alive.
  const beatFresh = ag.last_beat
    ? (Date.now() - new Date(ag.last_beat).getTime()) < 5 * 60 * 1000
    : false;
  if (ag.process_alive === false && !beatFresh) return "offline";
  // Never-beat: registered but claude hasn't been started yet.
  if (!ag.last_beat && ag.process_alive !== true) return "pending";
  if (ag.stale) {
    return ag.process_alive === true ? "idle" : "stale";
  }
  if (ag.hasActiveTask) return "running";
  return "online";
}
