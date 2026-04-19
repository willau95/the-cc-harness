import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { FolderKanban, ListChecks, Users } from "lucide-react";
import { Link, useParams } from "@/lib/router";
import { projectsApi } from "@/api/projects";
import { tasksApi } from "@/api/tasks";
import { queryKeys } from "@/lib/queryKeys";
import { timeAgo } from "@/lib/timeAgo";
import { useBreadcrumbs } from "@/context/BreadcrumbContext";
import { EmptyState } from "@/components/EmptyState";
import { PageSkeleton } from "@/components/PageSkeleton";
import { StatusBadge } from "@/components/StatusBadge";

export function ProjectDetailPage() {
  const { proj = "" } = useParams<{ proj: string }>();
  const { setBreadcrumbs } = useBreadcrumbs();
  useEffect(() => {
    setBreadcrumbs([
      { label: "Projects", href: "/projects" },
      { label: proj },
    ]);
  }, [proj, setBreadcrumbs]);

  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys.projects.detail(proj),
    queryFn: () => projectsApi.get(proj),
    enabled: !!proj,
    refetchInterval: 30_000,
  });

  const { data: tasksData } = useQuery({
    queryKey: queryKeys.tasks.all,
    queryFn: () => tasksApi.list(),
    refetchInterval: 10_000,
  });

  const projectTasks = useMemo(
    () => (tasksData?.tasks ?? []).filter((t) => t.project === proj),
    [tasksData, proj],
  );

  if (isLoading && !data) return <PageSkeleton variant="detail" />;
  if (error || !data) {
    return (
      <div className="border border-border rounded-lg">
        <EmptyState icon={FolderKanban} message={`Project not found: ${proj}`} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-border bg-card/60 p-4 md:p-5">
        <div className="text-xs text-muted-foreground font-mono flex items-center gap-2">
          <FolderKanban className="h-3 w-3" />
          <span>project</span>
        </div>
        <h2 className="mt-1 text-lg font-semibold truncate">{data.project}</h2>
      </section>

      <section className="space-y-2">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Active tasks</h3>
        <div className="border border-border rounded-lg overflow-hidden">
          {projectTasks.length === 0 ? (
            <EmptyState icon={ListChecks} message="No active tasks." />
          ) : (
            projectTasks.map((t) => {
              const href = t.agent_id
                ? `/agents/${encodeURIComponent(t.agent_id)}#task-${encodeURIComponent(t.task_id)}`
                : null;
              const inner = (
                <div className="flex items-center gap-3 px-4 py-2 text-sm border-b border-border last:border-b-0 hover:bg-accent/50 transition-colors">
                  <StatusBadge status={t.state} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-xs text-muted-foreground font-mono shrink-0 truncate max-w-[10rem]">
                        {t.task_id}
                      </span>
                      <span className="truncate">{t.original_goal ?? "—"}</span>
                    </div>
                    <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
                      {t.agent_id && (
                        <span className="inline-flex items-center rounded bg-muted/60 px-1.5 py-0.5 font-mono text-[10px]">
                          {t.agent_id}
                        </span>
                      )}
                      {t.ts && <span>· {timeAgo(t.ts)}</span>}
                    </div>
                  </div>
                </div>
              );
              return href ? (
                <Link key={t.task_id} to={href} className="block no-underline text-inherit">
                  {inner}
                </Link>
              ) : (
                <div key={t.task_id}>{inner}</div>
              );
            })
          )}
        </div>
      </section>

      <section className="space-y-2">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Members</h3>
        <div className="border border-border rounded-lg overflow-hidden">
          {data.members.length === 0 ? (
            <EmptyState icon={Users} message="No active members." />
          ) : (
            data.members.map((m) => (
              <div
                key={m.agent_id}
                className="flex items-center gap-3 px-4 py-2 text-sm border-b border-border last:border-b-0"
              >
                <span className="font-mono text-xs text-muted-foreground">{m.agent_id}</span>
                {m.role && (
                  <span className="text-xs text-muted-foreground">· {m.role}</span>
                )}
              </div>
            ))
          )}
        </div>
      </section>

      <section className="space-y-2">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">State</h3>
        <pre className="rounded-lg border border-border bg-card/60 p-4 text-xs overflow-auto max-h-[480px] font-mono whitespace-pre">
          {JSON.stringify(data.state, null, 2)}
        </pre>
      </section>
    </div>
  );
}
