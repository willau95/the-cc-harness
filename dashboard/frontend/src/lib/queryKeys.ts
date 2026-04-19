/**
 * Centralized TanStack Query keys — so WS-triggered invalidation can hit
 * well-known prefixes.
 */
export const queryKeys = {
  stats: ["stats"] as const,
  fleet: ["fleet"] as const,
  agents: {
    all: ["agents"] as const,
    detail: (id: string) => ["agents", id] as const,
  },
  events: (limit?: number) => (limit !== undefined ? (["events", limit] as const) : (["events"] as const)),
  eventsAll: ["events"] as const,
  projects: {
    all: ["projects"] as const,
    detail: (proj: string) => ["projects", proj] as const,
  },
  proposals: (status?: string, kind?: string) =>
    ["proposals", status ?? "any", kind ?? "any"] as const,
  proposalsAll: ["proposals"] as const,
  roles: ["roles"] as const,
};
