import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileDiff, FileText, GitBranch, Clock, X } from "lucide-react";
import { agentViewApi, type ChangedFile } from "@/api/agent-view";
import { timeAgo } from "@/lib/timeAgo";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

/**
 * File-system changes in an agent's folder. Git-aware when the folder is a
 * repo (status marks + per-file added/deleted counts + clickable diff);
 * falls back to mtime-based recent files for non-git folders.
 */
export function AgentChanges({ agentId }: { agentId: string }) {
  const [selected, setSelected] = useState<string | null>(null);

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["agent-changes", agentId],
    queryFn: () => agentViewApi.changes(agentId),
    refetchInterval: 8_000,
  });

  if (isLoading && !data) {
    return <div className="text-sm text-muted-foreground p-8 text-center">Loading…</div>;
  }
  if (!data?.available) {
    return (
      <div className="rounded-lg border border-border bg-muted/30 p-6 text-sm text-center">
        <div className="text-muted-foreground">{data?.reason ?? "No changes available."}</div>
      </div>
    );
  }

  const files = data.files ?? [];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <div className="flex items-center gap-2">
          {data.kind === "git" ? (
            <>
              <GitBranch className="h-3.5 w-3.5" />
              git working tree · {files.length} file{files.length === 1 ? "" : "s"} changed
            </>
          ) : (
            <>
              <Clock className="h-3.5 w-3.5" />
              not a git repo — showing recently-modified files
            </>
          )}
        </div>
        <Button size="sm" variant="outline" onClick={() => refetch()}>Refresh</Button>
      </div>

      <div className="border border-border rounded-lg overflow-hidden">
        {files.length === 0 ? (
          <div className="p-6 text-sm text-muted-foreground text-center">
            No changes.
          </div>
        ) : (
          files.map((f) => (
            <FileRow
              key={f.path}
              file={f}
              kind={data.kind}
              selected={selected === f.path}
              onClick={() => setSelected(selected === f.path ? null : f.path)}
            />
          ))
        )}
      </div>

      {selected && <FileDiffPane agentId={agentId} path={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function FileRow({
  file, kind, selected, onClick,
}: {
  file: ChangedFile;
  kind?: "git" | "mtime";
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex items-center gap-3 px-4 py-2 text-sm border-b border-border last:border-b-0 w-full text-left hover:bg-accent/50 transition-colors",
        selected && "bg-accent/60",
      )}
    >
      <FileText className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
      <span className="font-mono text-xs flex-1 truncate">{file.path}</span>
      {kind === "git" && (
        <>
          {file.status && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted/60 text-muted-foreground font-mono">
              {file.status}
            </span>
          )}
          {typeof file.added === "number" && file.added > 0 && (
            <span className="text-xs text-green-500 tabular-nums">+{file.added}</span>
          )}
          {typeof file.deleted === "number" && file.deleted > 0 && (
            <span className="text-xs text-red-500 tabular-nums">-{file.deleted}</span>
          )}
        </>
      )}
      {kind === "mtime" && file.mtime && (
        <span className="text-xs text-muted-foreground">
          {timeAgo(new Date(file.mtime * 1000).toISOString())}
        </span>
      )}
    </button>
  );
}

function FileDiffPane({
  agentId, path, onClose,
}: {
  agentId: string;
  path: string;
  onClose: () => void;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["agent-file-diff", agentId, path],
    queryFn: () => agentViewApi.fileDiff(agentId, path),
  });

  return (
    <div className="rounded-lg border border-border bg-card/60 overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2 border-b border-border bg-muted/30">
        <FileDiff className="h-4 w-4" />
        <span className="font-mono text-xs flex-1 truncate">{path}</span>
        <span className="text-[10px] text-muted-foreground">
          {data?.kind ?? (isLoading ? "…" : "")}
        </span>
        <Button size="icon-xs" variant="ghost" onClick={onClose}>
          <X className="h-3 w-3" />
        </Button>
      </div>
      <pre className="text-xs font-mono whitespace-pre-wrap break-all max-h-[500px] overflow-y-auto p-4">
        {isLoading ? "Loading…" :
          data?.kind === "diff" ? colorizeDiff(data.diff ?? "") :
          data?.kind === "untracked" ? <span className="text-muted-foreground">(untracked — showing file contents)
{"\n"}{data.content}</span> :
          "No diff available."}
      </pre>
    </div>
  );
}

function colorizeDiff(diff: string) {
  // Render diff with +/- line coloring
  return diff.split("\n").map((line, i) => {
    let cls = "";
    if (line.startsWith("+++") || line.startsWith("---")) cls = "text-muted-foreground";
    else if (line.startsWith("+")) cls = "text-green-500";
    else if (line.startsWith("-")) cls = "text-red-500";
    else if (line.startsWith("@@")) cls = "text-cyan-500";
    return (
      <div key={i} className={cls}>
        {line || " "}
      </div>
    );
  });
}
