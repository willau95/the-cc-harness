import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { FolderKanban } from "lucide-react";
import { projectsApi } from "@/api/projects";
import { queryKeys } from "@/lib/queryKeys";
import { useBreadcrumbs } from "@/context/BreadcrumbContext";
import { ProjectCard } from "@/components/ProjectCard";
import { EmptyState } from "@/components/EmptyState";
import { PageSkeleton } from "@/components/PageSkeleton";
import { PageHelp } from "@/components/PageHelp";

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
  const help = (
    <PageHelp
      storageKey="projects"
      title="Projects — groups of agents working toward a shared goal"
      summary="A project bundles members, active tasks, and shared state. Click a card to drill in."
      bullets={[
        <><b>Members</b> = agents assigned to the project (could span machines)</>,
        <><b>State</b> = key/value store any member can read/write to coordinate</>,
        <><b>Lifecycle:</b> create a project → assign agents → they coordinate via tasks + mailbox → close when done</>,
        <><b>Not the same as a folder</b> — one agent can belong to multiple projects simultaneously</>,
      ]}
    />
  );

  if (projects.length === 0) {
    return (
      <div className="space-y-4">
        {help}
        <div className="border border-border rounded-lg">
          <EmptyState icon={FolderKanban} message="No projects yet." />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {help}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {projects.map((p) => (
          <ProjectCard key={p.project} project={p} />
        ))}
      </div>
    </div>
  );
}
