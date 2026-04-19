import { FolderKanban, Users } from "lucide-react";
import { Link } from "@/lib/router";
import type { ProjectSummary } from "@/api/types";

export function ProjectCard({ project }: { project: ProjectSummary }) {
  return (
    <Link
      to={`/projects/${encodeURIComponent(project.project)}`}
      className="group no-underline text-inherit rounded-lg border border-border bg-card/60 p-4 hover:bg-accent/40 transition-colors flex flex-col gap-3"
    >
      <div className="flex items-start gap-2">
        <div className="mt-0.5 flex-1 min-w-0">
          <div className="flex items-center gap-2 text-xs text-muted-foreground font-mono">
            <FolderKanban className="h-3 w-3" />
            <span className="truncate">project</span>
          </div>
          <h3 className="text-sm font-semibold leading-snug truncate">{project.project}</h3>
        </div>
      </div>
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1">
          <Users className="h-3 w-3" />
          {project.member_count} member{project.member_count === 1 ? "" : "s"}
        </span>
        <span className="truncate">
          {project.members.slice(0, 3).map((m) => m.agent_id).join(", ")}
          {project.members.length > 3 ? ` +${project.members.length - 3}` : ""}
        </span>
      </div>
    </Link>
  );
}
