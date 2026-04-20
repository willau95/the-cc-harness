import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, AlertTriangle, CheckSquare, FolderKanban, Users } from "lucide-react";
import { Link } from "@/lib/router";
import { MetricCard } from "@/components/MetricCard";
import { ActiveAgentsPanel } from "@/components/ActiveAgentsPanel";
import { EmptyState } from "@/components/EmptyState";
import { EventRow } from "@/components/EventRow";
import { ProjectCard } from "@/components/ProjectCard";
import { PageSkeleton } from "@/components/PageSkeleton";
import { PageHelp } from "@/components/PageHelp";
import { statsApi } from "@/api/stats";
import { eventsApi } from "@/api/events";
import { projectsApi } from "@/api/projects";
import { queryKeys } from "@/lib/queryKeys";
import { useBreadcrumbs } from "@/context/BreadcrumbContext";

export function DashboardPage() {
  const { setBreadcrumbs } = useBreadcrumbs();
  useEffect(() => setBreadcrumbs([{ label: "Dashboard" }]), [setBreadcrumbs]);

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: queryKeys.stats,
    queryFn: () => statsApi.get(),
    refetchInterval: 10_000,
  });

  const { data: events } = useQuery({
    queryKey: queryKeys.events(10),
    queryFn: () => eventsApi.list(10),
    refetchInterval: 10_000,
  });

  const { data: projects } = useQuery({
    queryKey: queryKeys.projects.all,
    queryFn: () => projectsApi.list(),
    refetchInterval: 30_000,
  });

  if (statsLoading && !stats) {
    return <PageSkeleton variant="dashboard" />;
  }

  const totalAgents = stats?.total_agents ?? 0;
  const online = stats?.online ?? 0;
  const zombies = stats?.zombies ?? 0;
  const pending = stats?.pending_proposals ?? 0;
  const pendingBudgets = stats?.pending_budgets ?? 0;
  const projectCount = stats?.projects ?? 0;

  return (
    <div className="space-y-6">
      <PageHelp
        storageKey="dashboard"
        title="Dashboard — single-glance fleet health"
        summary="Everything that matters in one screen. Click any tile to drill in."
        bullets={[
          <><b>Agents online</b> → who's heartbeating right now vs. stale</>,
          <><b>Stale agents</b> → haven't checked in within the timeout; may be crashed or sleeping</>,
          <><b>Proposals pending</b> → self-improvement suggestions from agents waiting for your approval</>,
          <><b>Projects</b> → active collaborations (group of agents sharing a goal)</>,
        ]}
      />
      <div className="grid grid-cols-2 gap-2 xl:grid-cols-4">
        <MetricCard
          icon={Users}
          value={online}
          label="Agents online"
          description={`${totalAgents} total`}
          to="/fleet/online"
        />
        <MetricCard
          icon={AlertTriangle}
          value={zombies}
          label="Stale agents"
          description="No recent heartbeat"
          to="/fleet/stale"
        />
        <MetricCard
          icon={CheckSquare}
          value={pending}
          label="Proposals pending"
          description={pendingBudgets ? `${pendingBudgets} budget` : undefined}
          to="/proposals"
        />
        <MetricCard
          icon={FolderKanban}
          value={projectCount}
          label="Projects"
          to="/projects"
        />
      </div>

      <ActiveAgentsPanel />

      <div className="grid gap-4 md:grid-cols-2">
        <section className="space-y-2">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Recent events
            </h2>
            <Link to="/events" className="text-xs text-muted-foreground hover:text-foreground no-underline">
              View all &rarr;
            </Link>
          </div>
          <div className="border border-border rounded-lg overflow-hidden">
            {!events?.events?.length ? (
              <EmptyState icon={Activity} message="No recent events." />
            ) : (
              events.events.slice(0, 8).map((event, i) => (
                <EventRow key={`${event.agent}-${event.ts}-${i}`} event={event} />
              ))
            )}
          </div>
        </section>

        <section className="space-y-2">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Projects
            </h2>
            <Link to="/projects" className="text-xs text-muted-foreground hover:text-foreground no-underline">
              View all &rarr;
            </Link>
          </div>
          {!projects?.projects?.length ? (
            <div className="border border-border rounded-lg">
              <EmptyState icon={FolderKanban} message="No projects yet." />
            </div>
          ) : (
            <div className="grid gap-2">
              {projects.projects.slice(0, 6).map((p) => (
                <ProjectCard key={p.project} project={p} />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
