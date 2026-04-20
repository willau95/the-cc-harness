import { MoreHorizontal, Plus, Users } from "lucide-react";
import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@/lib/router";
import { fleetApi } from "@/api/fleet";
import { queryKeys } from "@/lib/queryKeys";
import { useBulkSelection } from "@/hooks/useBulkSelection";
import { useDialogs } from "@/context/DialogContext";
import { useToast } from "@/context/ToastContext";
import { ApiError } from "@/api/client";
import type { FleetAgent } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { EntityRow } from "./EntityRow";
import { EmptyState } from "./EmptyState";
import { PageSkeleton } from "./PageSkeleton";
import { PageTabBar } from "./PageTabBar";
import { StatusBadge } from "./StatusBadge";
import { FleetControlBar } from "./FleetControlBar";
import { Tabs, TabsContent } from "@/components/ui/tabs";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { timeAgo } from "@/lib/timeAgo";
import { cn } from "@/lib/utils";
import { agentStatusDot, agentStatusDotDefault, deriveAgentStatus } from "@/lib/status-colors";

const TABS = [
  { value: "all", label: "All" },
  { value: "online", label: "Online" },
  { value: "stale", label: "Stale" },
  { value: "paused", label: "Paused" },
];

interface FleetControlPanelProps {
  tab?: string;
  onTabChange?: (tab: string) => void;
}

export function FleetControlPanel({ tab = "all", onTabChange }: FleetControlPanelProps) {
  const qc = useQueryClient();
  const { openSpawn } = useDialogs();
  const { pushToast } = useToast();
  const selection = useBulkSelection<string>();

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.fleet,
    queryFn: () => fleetApi.list(),
    refetchInterval: 5_000,
  });

  const agents: FleetAgent[] = data?.agents ?? [];

  const filtered = useMemo(() => {
    if (tab === "all") return agents;
    return agents.filter((a) => deriveAgentStatus({ stale: a.stale, paused: a.paused, process_alive: a.process_alive as boolean | null | undefined, last_beat: a.last_beat as string | null | undefined }) === tab);
  }, [agents, tab]);

  const bulkInvalidate = () => {
    qc.invalidateQueries({ queryKey: queryKeys.fleet });
    qc.invalidateQueries({ queryKey: queryKeys.stats });
  };

  const bulk = useMutation({
    mutationFn: ({ action, ids }: { action: "pause" | "resume" | "kill"; ids: string[] }) =>
      fleetApi.bulk(action, ids),
    onSuccess: (_res, vars) => {
      bulkInvalidate();
      selection.clear();
      pushToast(`${vars.action} sent to ${vars.ids.length} agent${vars.ids.length === 1 ? "" : "s"}`, "success");
    },
    onError: (err: unknown) => {
      const msg = err instanceof ApiError ? err.message : "Bulk action failed";
      pushToast(msg, "error");
    },
  });

  const singleAction = useMutation({
    mutationFn: ({ action, id }: { action: "pause" | "resume" | "kill"; id: string }) => {
      if (action === "pause") return fleetApi.pause(id);
      if (action === "resume") return fleetApi.resume(id);
      return fleetApi.kill(id);
    },
    onSuccess: (_res, vars) => {
      bulkInvalidate();
      pushToast(`${vars.action}: ${vars.id}`, "success");
    },
    onError: (err: unknown) => {
      const msg = err instanceof ApiError ? err.message : "Action failed";
      pushToast(msg, "error");
    },
  });

  const runBulk = (action: "pause" | "resume" | "kill") => {
    const ids = Array.from(selection.selected);
    if (ids.length === 0) return;
    if (action === "kill" && !confirm(`Kill ${ids.length} agent${ids.length === 1 ? "" : "s"}?`)) return;
    bulk.mutate({ action, ids });
  };

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Fleet
        </h2>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground tabular-nums">
            {data?.count ?? 0} agent{(data?.count ?? 0) === 1 ? "" : "s"}
          </span>
          <Button size="sm" onClick={openSpawn}>
            <Plus className="h-3.5 w-3.5" />
            Spawn Agent
          </Button>
        </div>
      </div>

      <Tabs value={tab} onValueChange={(v) => onTabChange?.(v)}>
        <div className="flex items-center justify-between gap-2">
          <PageTabBar items={TABS} value={tab} onValueChange={(v) => onTabChange?.(v)} />
        </div>

        <TabsContent value={tab} className="mt-3">
          <FleetControlBar
            count={selection.count}
            onPause={() => runBulk("pause")}
            onResume={() => runBulk("resume")}
            onKill={() => runBulk("kill")}
            onClear={selection.clear}
            busy={bulk.isPending}
          />

          {isLoading ? (
            <PageSkeleton />
          ) : filtered.length === 0 ? (
            <div className="border border-border rounded-lg">
              <EmptyState icon={Users} message="No agents in this view." action="Spawn Agent" onAction={openSpawn} />
            </div>
          ) : (
            <div className="border border-border rounded-lg overflow-hidden">
              {filtered.map((agent) => {
                const status = deriveAgentStatus({ stale: agent.stale, paused: agent.paused, process_alive: agent.process_alive as boolean | null | undefined, last_beat: agent.last_beat as string | null | undefined });
                const dotClass = agentStatusDot[status] ?? agentStatusDotDefault;
                return (
                  <EntityRow
                    key={agent.agent_id}
                    leading={
                      <>
                        <div
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                          }}
                        >
                          <Checkbox
                            checked={selection.isSelected(agent.agent_id)}
                            onCheckedChange={() => selection.toggle(agent.agent_id)}
                            aria-label={`Select ${agent.agent_id}`}
                          />
                        </div>
                        <span className={cn("h-2 w-2 rounded-full", dotClass)} />
                      </>
                    }
                    identifier={agent.agent_id.slice(0, 8)}
                    title={agent.name ?? agent.agent_id}
                    subtitle={`${agent.role ?? "—"} · ${agent.folder ?? "—"}`}
                    to={`/agents/${encodeURIComponent(agent.agent_id)}`}
                    trailing={
                      <>
                        <span className="text-xs text-muted-foreground shrink-0">
                          {agent.last_beat ? timeAgo(agent.last_beat) : "—"}
                        </span>
                        <StatusBadge status={status} />
                        <RowMenu
                          agent={agent}
                          onAction={(action) => singleAction.mutate({ action, id: agent.agent_id })}
                        />
                      </>
                    }
                  />
                );
              })}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </section>
  );
}

interface RowMenuProps {
  agent: FleetAgent;
  onAction: (action: "pause" | "resume" | "kill") => void;
}

function RowMenu({ agent, onAction }: RowMenuProps) {
  return (
    <div onClick={(e) => { e.preventDefault(); e.stopPropagation(); }}>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon-xs" aria-label="Actions">
            <MoreHorizontal className="h-3.5 w-3.5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem asChild>
            <Link to={`/agents/${encodeURIComponent(agent.agent_id)}`}>View details</Link>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => onAction("pause")}>Pause</DropdownMenuItem>
          <DropdownMenuItem onClick={() => onAction("resume")}>Resume</DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            variant="destructive"
            onClick={() => {
              if (confirm(`Kill agent ${agent.agent_id}?`)) onAction("kill");
            }}
          >
            Kill
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={() => {
              void navigator.clipboard?.writeText(agent.agent_id);
            }}
          >
            Copy id
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
