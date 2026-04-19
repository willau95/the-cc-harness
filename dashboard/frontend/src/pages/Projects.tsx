import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { FolderKanban } from "lucide-react";
import { projectsApi } from "@/api/projects";
import { queryKeys } from "@/lib/queryKeys";
import { useBreadcrumbs } from "@/context/BreadcrumbContext";
import { ProjectCard } from "@/components/ProjectCard";
import { EmptyState } from "@/components/EmptyState";
import { PageSkeleton } from "@/components/PageSkeleton";

export function ProjectsPage() {
  const { setBreadcrumbs } = useBreadcrumbs();
  useEffect(() => setBreadcrumbs([{ label: "Projects" }]), [setBreadcrumbs]);

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.projects.all,
    queryFn: () => projectsApi.list(),
    refetchInterval: 30_000,
  });

  if (isLoading && !data) return <PageSkeleton />;

  const projects = data?.projects ?? [];
  if (projects.length === 0) {
    return (
      <div className="border border-border rounded-lg">
        <EmptyState icon={FolderKanban} message="No projects yet." />
      </div>
    );
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {projects.map((p) => (
        <ProjectCard key={p.project} project={p} />
      ))}
    </div>
  );
}
