import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { FolderKanban, Users } from "lucide-react";
import { useParams } from "@/lib/router";
import { projectsApi } from "@/api/projects";
import { queryKeys } from "@/lib/queryKeys";
import { useBreadcrumbs } from "@/context/BreadcrumbContext";
import { EmptyState } from "@/components/EmptyState";
import { PageSkeleton } from "@/components/PageSkeleton";

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
        <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Members</h3>
        <div className="border border-border rounded-lg overflow-hidden">
          {data.members.length === 0 ? (
            <EmptyState icon={Users} message="No active members." />
          ) : (
            data.members.map((m) => (
              <div
                key={m}
                className="flex items-center gap-3 px-4 py-2 text-sm border-b border-border last:border-b-0"
              >
                <span className="font-mono text-xs text-muted-foreground">{m}</span>
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
