import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity as ActivityIcon,
  AlertCircle,
  Brain,
  FileText,
  Hammer,
  Send,
  Sparkles,
  Terminal,
  User,
  Wrench,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { agentViewApi, type TranscriptEntry } from "@/api/agent-view";
import { timeAgo } from "@/lib/timeAgo";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

/**
 * Live view of what an agent is currently doing, reading Claude Code's
 * per-session transcript. Shows user prompts, assistant text & thinking,
 * tool_use calls with input summary, and tool results.
 */
export function AgentLiveView({ agentId }: { agentId: string }) {
  const [showThinking, setShowThinking] = useState(false);

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["agent-transcript", agentId],
    queryFn: () => agentViewApi.transcript(agentId, 400),
    refetchInterval: 4_000, // poll every 4s for near-live feel
  });

  const { data: activity } = useQuery({
    queryKey: ["agent-activity", agentId],
    queryFn: () => agentViewApi.activity(agentId),
    refetchInterval: 2_000,
  });

  const entries = useMemo(() => {
    const t = data?.timeline ?? [];
    return showThinking ? t : t.filter((e) => e.kind !== "thinking");
  }, [data, showThinking]);

  if (isLoading && !data) {
    return <div className="text-sm text-muted-foreground p-8 text-center">Loading transcript…</div>;
  }

  if (!data?.available) {
    return (
      <div className="rounded-lg border border-border bg-muted/30 p-6 text-sm text-center space-y-2">
        <div className="text-muted-foreground">
          No live transcript available for this agent.
        </div>
        <div className="text-xs text-muted-foreground">
          {data?.reason === "folder not local to this machine"
            ? "This agent is on a peer. Live transcript requires running the dashboard where the agent's folder lives (v0.2 limitation — remote transcript streaming is P1)."
            : data?.reason === "no claude session found for this folder"
            ? "Start claude in the agent folder so a session.jsonl is created."
            : (data?.reason ?? "Reason unknown.")}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Activity banner */}
      <ActivityBanner activity={activity?.activity} />

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <div>
          {entries.length} entr{entries.length === 1 ? "y" : "ies"}
          {data.session && (
            <span className="ml-2 font-mono">
              · session {data.session.session_id.slice(0, 8)}…
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1 cursor-pointer">
            <input
              type="checkbox"
              checked={showThinking}
              onChange={(e) => setShowThinking(e.target.checked)}
              className="h-3 w-3"
            />
            Show thinking
          </label>
          <Button size="sm" variant="outline" onClick={() => refetch()}>
            Refresh
          </Button>
        </div>
      </div>

      <div className="border border-border rounded-lg divide-y divide-border bg-card/40 max-h-[calc(100vh-18rem)] overflow-y-auto">
        {entries.length === 0 ? (
          <div className="p-6 text-sm text-muted-foreground text-center">
            No transcript entries yet.
          </div>
        ) : (
          entries.map((e, i) => <TimelineRow key={i} entry={e} />)
        )}
      </div>
    </div>
  );
}

function ActivityBanner({ activity }: { activity: { tool_name?: string; tool_input_summary?: string; started_at?: string; status?: string } | null | undefined }) {
  if (!activity || !activity.tool_name) {
    return (
      <div className="rounded-lg border border-border/60 bg-muted/20 px-4 py-2 text-sm flex items-center gap-2">
        <span className="inline-block h-2 w-2 rounded-full bg-neutral-400" />
        <span className="text-muted-foreground">Idle — waiting for next prompt</span>
      </div>
    );
  }
  const running = activity.status === "running";
  return (
    <div className={cn(
      "rounded-lg border px-4 py-2 text-sm flex items-center gap-2 flex-wrap",
      running ? "border-cyan-500/40 bg-cyan-500/5" : "border-border bg-muted/20",
    )}>
      <span className={cn(
        "inline-block h-2 w-2 rounded-full",
        running ? "bg-cyan-400 animate-pulse" : "bg-green-400",
      )} />
      <span className="font-medium">{running ? "Currently" : "Last"}</span>
      <span className="font-mono text-xs px-1.5 py-0.5 rounded bg-background border border-border">
        {activity.tool_name}
      </span>
      {activity.tool_input_summary && (
        <span className="text-muted-foreground truncate font-mono text-xs max-w-[40rem]">
          {activity.tool_input_summary}
        </span>
      )}
      {activity.started_at && (
        <span className="text-xs text-muted-foreground ml-auto">
          {timeAgo(activity.started_at)}
        </span>
      )}
    </div>
  );
}

function TimelineRow({ entry }: { entry: TranscriptEntry }) {
  const time = entry.ts ? timeAgo(entry.ts) : "";
  switch (entry.kind) {
    case "prompt":
      return (
        <Row icon={User} label="User" tone="user" time={time}>
          <div className="whitespace-pre-wrap break-words text-sm">{entry.text}</div>
        </Row>
      );
    case "text":
      return (
        <Row icon={Sparkles} label="Assistant" tone="assistant" time={time}>
          <div className="prose prose-sm prose-invert max-w-none prose-p:my-1.5 prose-pre:my-2 prose-pre:bg-muted prose-code:text-[0.85em] prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:before:content-none prose-code:after:content-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{entry.text ?? ""}</ReactMarkdown>
          </div>
        </Row>
      );
    case "thinking":
      return (
        <Row icon={Brain} label="Thinking" tone="thinking" time={time}>
          <div className="whitespace-pre-wrap break-words text-xs text-muted-foreground italic">
            {entry.text}
          </div>
        </Row>
      );
    case "tool_use":
      return (
        <Row icon={Wrench} label={`${entry.tool_name ?? "tool"}`} tone="tool" time={time}>
          <div className="font-mono text-xs break-all text-muted-foreground">
            {entry.tool_input_summary || "(no args)"}
          </div>
        </Row>
      );
    case "tool_result":
      return (
        <Row icon={Hammer} label="Tool result" tone={entry.is_error ? "error" : "tool"} time={time}>
          <div className="font-mono text-xs break-all whitespace-pre-wrap max-h-64 overflow-y-auto text-muted-foreground bg-background/60 rounded p-2">
            {entry.text ?? "(empty)"}
            {entry.truncated && (
              <div className="mt-1 text-[10px] text-amber-500">— truncated —</div>
            )}
          </div>
        </Row>
      );
    case "hook":
      return (
        <Row icon={ActivityIcon} label={`hook · ${entry.hook_name}`} tone="hook" time={time}>
          {entry.text && entry.text.length > 0 && (
            <div className="font-mono text-xs break-all text-muted-foreground">{entry.text}</div>
          )}
        </Row>
      );
    default:
      return null;
  }
}

function Row({
  icon: Icon, label, tone, time, children,
}: {
  icon: typeof User;
  label: string;
  tone: "user" | "assistant" | "tool" | "thinking" | "error" | "hook";
  time: string;
  children: React.ReactNode;
}) {
  const toneClass = {
    user: "text-blue-500 dark:text-blue-400",
    assistant: "text-foreground",
    tool: "text-violet-500 dark:text-violet-400",
    thinking: "text-muted-foreground",
    error: "text-destructive",
    hook: "text-emerald-500 dark:text-emerald-400",
  }[tone];
  return (
    <div className="p-3 flex gap-3 items-start hover:bg-accent/20 transition-colors">
      <Icon className={cn("h-4 w-4 mt-0.5 shrink-0", toneClass)} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className={cn("text-xs font-semibold", toneClass)}>{label}</span>
          <span className="text-[10px] text-muted-foreground">{time}</span>
        </div>
        {children}
      </div>
    </div>
  );
}

// re-export alias so other files that import Send don't need a second import
export { Send, FileText, Terminal, AlertCircle };
