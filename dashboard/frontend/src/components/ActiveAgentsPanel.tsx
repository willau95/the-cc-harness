import { useQuery } from "@tanstack/react-query";
import { ExternalLink, Users } from "lucide-react";
import { Link } from "@/lib/router";
import { fleetApi } from "@/api/fleet";
import { queryKeys } from "@/lib/queryKeys";
import { Identity } from "./Identity";
import { EmptyState } from "./EmptyState";
import { timeAgo } from "@/lib/timeAgo";
import { cn } from "@/lib/utils";
import { agentStatusDot, agentStatusDotDefault, deriveAgentStatus } from "@/lib/status-colors";
import { Skeleton } from "@/components/ui/skeleton";

interface ActiveAgentsPanelProps {
  limit?: number;
}

export function ActiveAgentsPanel({ limit = 8 }: ActiveAgentsPanelProps) {
  const { data, isLoading } = useQuery({
    queryKey: queryKeys.fleet,
    queryFn: () => fleetApi.list(),
    refetchInterval: 5_000,
  });

  if (isLoading) {
    return (
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            Agents
          </h2>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-2 sm:gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-40 w-full rounded-lg" />
          ))}
        </div>
      </section>
    );
  }

  const live = (data?.agents ?? []).filter((a) => !a.stale).slice(0, limit);

  if (!live.length) {
    return (
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            Agents
          </h2>
        </div>
        <div className="border border-border rounded-lg">
          <EmptyState icon={Users} message="No live agents." />
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Agents
        </h2>
        <Link
          to="/fleet"
          className="text-xs text-muted-foreground hover:text-foreground no-underline"
        >
          View fleet &rarr;
        </Link>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-2 sm:gap-4">
        {live.map((agent) => {
          const status = deriveAgentStatus({ stale: agent.stale, paused: agent.paused, process_alive: agent.process_alive as boolean | null | undefined, last_beat: agent.last_beat as string | null | undefined });
          const dotClass = agentStatusDot[status] ?? agentStatusDotDefault;
          const isActive = status === "running" || status === "online";
          return (
            <Link
              key={agent.agent_id}
              to={`/agents/${encodeURIComponent(agent.agent_id)}`}
              className={cn(
                "group relative rounded-lg border px-3 py-3 flex flex-col gap-2 no-underline text-inherit transition-colors",
                isActive
                  ? "border-cyan-500/25 bg-cyan-500/[0.04] shadow-[0_16px_40px_rgba(6,182,212,0.08)]"
                  : "border-border bg-card/60 hover:bg-accent/40",
              )}
            >
              <div className="flex items-start gap-2">
                <span className={cn("mt-1 h-2 w-2 rounded-full shrink-0", dotClass)} />
                <div className="flex-1 min-w-0">
                  <Identity name={agent.name ?? agent.agent_id} size="sm" />
                  <div className="mt-0.5 text-[11px] text-muted-foreground truncate">
                    {agent.role ?? "agent"}
                  </div>
                </div>
                <ExternalLink className="h-2.5 w-2.5 text-muted-foreground/60 opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
              <div className="mt-auto flex items-center justify-between">
                <span className="text-[11px] text-muted-foreground truncate">
                  {agent.folder ?? ""}
                </span>
                <span className="text-[11px] text-muted-foreground shrink-0">
                  {agent.last_beat ? timeAgo(agent.last_beat) : "—"}
                </span>
              </div>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
