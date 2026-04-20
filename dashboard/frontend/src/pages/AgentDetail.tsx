import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Inbox, ListChecks, MessageSquare, Users } from "lucide-react";
import { Link, useNavigate, useParams } from "@/lib/router";
import { agentsApi } from "@/api/agents";
import { fleetApi } from "@/api/fleet";
import { queryKeys } from "@/lib/queryKeys";
import { useBreadcrumbs } from "@/context/BreadcrumbContext";
import { useToast } from "@/context/ToastContext";
import { ApiError } from "@/api/client";
import { Identity } from "@/components/Identity";
import { StatusBadge } from "@/components/StatusBadge";
import { PageSkeleton } from "@/components/PageSkeleton";
import { EmptyState } from "@/components/EmptyState";
import { EventRow } from "@/components/EventRow";
import { KillButton, PauseResumeButton } from "@/components/AgentActionButtons";
import { BackLink } from "@/components/BackLink";
import { AgentLiveView } from "@/components/AgentLiveView";
import { AgentChanges } from "@/components/AgentChanges";
import { PageTabBar } from "@/components/PageTabBar";
import { Button } from "@/components/ui/button";
import { timeAgo } from "@/lib/timeAgo";
import { deriveAgentStatus } from "@/lib/status-colors";

export function AgentDetailPage() {
  const { agentId = "" } = useParams<{ agentId: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { pushToast } = useToast();
  const { setBreadcrumbs } = useBreadcrumbs();

  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys.agents.detail(agentId),
    queryFn: () => agentsApi.get(agentId),
    enabled: !!agentId,
    refetchInterval: 5_000,
  });

  useEffect(() => {
    setBreadcrumbs([
      { label: "Fleet", href: "/fleet" },
      { label: data?.agent?.name ?? agentId },
    ]);
  }, [agentId, data?.agent?.name, setBreadcrumbs]);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: queryKeys.agents.detail(agentId) });
    qc.invalidateQueries({ queryKey: queryKeys.fleet });
    qc.invalidateQueries({ queryKey: queryKeys.stats });
  };

  const action = useMutation({
    mutationFn: (act: "pause" | "resume" | "kill") => {
      if (act === "pause") return fleetApi.pause(agentId);
      if (act === "resume") return fleetApi.resume(agentId);
      return fleetApi.kill(agentId);
    },
    onSuccess: (_res, act) => {
      invalidate();
      if (act === "kill") {
        pushToast(`Killed ${agentId}`, "success");
        navigate("/fleet");
      } else {
        pushToast(`${act}: ${agentId}`, "success");
      }
    },
    onError: (err: unknown) => {
      const msg = err instanceof ApiError ? err.message : "Action failed";
      pushToast(msg, "error");
    },
  });

  if (isLoading && !data) return <PageSkeleton variant="detail" />;
  if (error || !data) {
    return (
      <div className="space-y-2">
        <BackLink to="/fleet" label="Fleet" />
        <div className="border border-border rounded-lg">
          <EmptyState icon={Users} message={`Agent not found: ${agentId}`} />
        </div>
      </div>
    );
  }

  const status = deriveAgentStatus({ stale: data.stale, paused: data.agent.paused, process_alive: (data.agent as { process_alive?: boolean | null }).process_alive });
  const isPaused = Boolean(data.agent.paused);

  return (
    <div className="space-y-6">
      <BackLink to="/fleet" label="Fleet" />
      <section className="rounded-lg border border-border bg-card/60 p-4 md:p-5 space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex-1 min-w-0 space-y-1">
            <div className="flex items-center gap-2 text-xs text-muted-foreground font-mono">
              <span className="truncate">{agentId}</span>
            </div>
            <div className="flex items-center gap-3 flex-wrap">
              <Identity name={data.agent.name ?? agentId} size="lg" />
              <StatusBadge status={status} />
            </div>
            <div className="text-xs text-muted-foreground">
              role: <span className="text-foreground">{data.agent.role ?? "—"}</span>
              {" · "}folder: <span className="font-mono">{data.agent.folder ?? "—"}</span>
              {data.last_beat && <> · last beat <span>{timeAgo(data.last_beat)}</span></>}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" asChild>
              <Link to={`/chat/${encodeURIComponent(agentId)}`}>
                <MessageSquare className="h-4 w-4" />
                Chat
              </Link>
            </Button>
            <PauseResumeButton
              isPaused={isPaused}
              onPause={() => action.mutate("pause")}
              onResume={() => action.mutate("resume")}
              disabled={action.isPending}
            />
            <KillButton
              onClick={() => {
                if (confirm(`Kill agent ${agentId}?`)) action.mutate("kill");
              }}
              disabled={action.isPending}
            />
          </div>
        </div>
      </section>

      <AgentDetailTabs agentId={agentId} data={data} />
    </div>
  );
}

type TabKey = "live" | "changes" | "overview" | "events";
const TABS = [
  { value: "live", label: "Live view" },
  { value: "changes", label: "Changes" },
  { value: "overview", label: "Overview" },
  { value: "events", label: "Events" },
];

function AgentDetailTabs({ agentId, data }: { agentId: string; data: NonNullable<ReturnType<typeof import("@/api/agents").agentsApi.get> extends Promise<infer T> ? T : never> }) {
  const [tab, setTab] = useState<TabKey>("live");
  return (
    <div className="space-y-4">
      <PageTabBar
        items={TABS}
        value={tab}
        onValueChange={(v) => setTab(v as TabKey)}
      />
      {tab === "live" && <AgentLiveView agentId={agentId} />}
      {tab === "changes" && <AgentChanges agentId={agentId} />}
      {tab === "overview" && <AgentOverview data={data} />}
      {tab === "events" && <AgentEvents data={data} agentId={agentId} />}
    </div>
  );
}

function AgentOverview({ data }: { data: NonNullable<ReturnType<typeof import("@/api/agents").agentsApi.get> extends Promise<infer T> ? T : never> }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section className="space-y-2">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Active tasks
            </h2>
          </div>
          <div className="border border-border rounded-lg overflow-hidden">
            {!data.tasks?.length ? (
              <EmptyState icon={ListChecks} message="No active tasks." />
            ) : (
              data.tasks.map((task, i) => (
                <div
                  key={task.task_id ?? i}
                  className="flex items-center gap-3 px-4 py-2 text-sm border-b border-border last:border-b-0"
                >
                  <div className="flex-1 min-w-0">
                    <p className="truncate">{task.title ?? task.task_id ?? "Untitled task"}</p>
                    {task.task_id && (
                      <p className="text-xs text-muted-foreground font-mono truncate">{task.task_id}</p>
                    )}
                  </div>
                  {task.status && <StatusBadge status={task.status} />}
                </div>
              ))
            )}
          </div>
        </section>

        <section className="space-y-2">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Inbox pending
            </h2>
          </div>
          <div className="border border-border rounded-lg overflow-hidden">
            {!data.inbox_pending?.length ? (
              <EmptyState icon={Inbox} message="Inbox empty." />
            ) : (
              data.inbox_pending.map((item, i) => (
                <div
                  key={item.id ?? i}
                  className="flex items-center gap-3 px-4 py-2 text-sm border-b border-border last:border-b-0"
                >
                  <div className="flex-1 min-w-0">
                    <p className="truncate">
                      {item.kind ?? "message"}
                      {item.id && (
                        <span className="ml-2 text-xs text-muted-foreground font-mono">{item.id}</span>
                      )}
                    </p>
                  </div>
                  {item.ts && (
                    <span className="text-xs text-muted-foreground shrink-0">{timeAgo(item.ts)}</span>
                  )}
                </div>
              ))
            )}
          </div>
        </section>
    </div>
  );
}

function AgentEvents({ data, agentId }: { data: NonNullable<ReturnType<typeof import("@/api/agents").agentsApi.get> extends Promise<infer T> ? T : never>; agentId: string }) {
  return (
    <section className="space-y-2">
      <div className="border border-border rounded-lg overflow-hidden">
        {!data.recent_events?.length ? (
          <EmptyState icon={Activity} message="No events yet." />
        ) : (
          data.recent_events
            .slice(0, 50)
            .map((event, i) => <EventRow key={`${event.ts}-${i}`} event={{ ...event, agent: agentId }} />)
        )}
      </div>
    </section>
  );
}
