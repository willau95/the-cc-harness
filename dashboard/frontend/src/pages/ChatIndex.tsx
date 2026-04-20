import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { MessagesSquare } from "lucide-react";
import { Link } from "@/lib/router";
import { fleetApi } from "@/api/fleet";
import { queryKeys } from "@/lib/queryKeys";
import { useBreadcrumbs } from "@/context/BreadcrumbContext";
import { EmptyState } from "@/components/EmptyState";
import { PageSkeleton } from "@/components/PageSkeleton";
import { Identity } from "@/components/Identity";
import { PageHelp } from "@/components/PageHelp";
import { timeAgo } from "@/lib/timeAgo";

export function ChatIndexPage() {
  const { setBreadcrumbs } = useBreadcrumbs();
  useEffect(() => setBreadcrumbs([{ label: "Chat" }]), [setBreadcrumbs]);

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.fleet,
    queryFn: () => fleetApi.list(),
    refetchInterval: 10_000,
  });

  if (isLoading && !data) return <PageSkeleton variant="list" />;
  const agents = data?.agents ?? [];

  return (
    <div className="space-y-4">
      <PageHelp
        storageKey="chat-index"
        title="Chat — direct line to any agent"
        summary="Pick an agent to open its inbox. Your messages land in the same mailbox agents use to talk to each other."
        bullets={[
          <><b>You as <code>human@dashboard</code></b> — messages appear in the agent's inbox and events</>,
          <><b>Markdown is rendered</b> (bold, lists, links, code)</>,
          <><b>Persistent:</b> the thread is stored in <code>~/.harness/mailbox/&lt;agent_id&gt;/inbox.jsonl</code> — both sides see history</>,
          <><b>Cross-machine works:</b> sending to a peer agent routes over fleet-ssh to their inbox</>,
        ]}
      />
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Chat with agent
        </h2>
        <span className="text-xs text-muted-foreground">{agents.length} agent{agents.length === 1 ? "" : "s"}</span>
      </div>
      {agents.length === 0 ? (
        <div className="border border-border rounded-lg">
          <EmptyState icon={MessagesSquare} message="No agents in fleet yet." />
        </div>
      ) : (
        <div className="border border-border rounded-lg overflow-hidden">
          {agents.map((a) => (
            <Link
              key={a.agent_id}
              to={`/chat/${encodeURIComponent(a.agent_id)}`}
              className="flex items-center gap-3 px-4 py-3 text-sm border-b border-border last:border-b-0 hover:bg-accent/50 transition-colors no-underline text-inherit"
            >
              <span className={[
                "inline-block h-2 w-2 rounded-full shrink-0",
                a.stale ? "bg-muted-foreground/40" : "bg-green-500",
              ].join(" ")} />
              <Identity name={a.agent_id} size="sm" />
              <div className="flex-1 min-w-0">
                <div className="font-medium truncate">{a.agent_id}</div>
                <div className="text-xs text-muted-foreground truncate">
                  {(a.role as string) || "?"}
                  {a.machine ? ` · ${a.machine}` : ""}
                  {a.folder ? ` · ${a.folder as string}` : ""}
                </div>
              </div>
              <span className="text-xs text-muted-foreground shrink-0">
                {a.last_beat ? timeAgo(a.last_beat as string) : "—"}
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
