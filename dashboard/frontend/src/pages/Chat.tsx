import { useEffect, useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { MessageSquare, Send, Settings2 } from "lucide-react";
import { useParams } from "@/lib/router";
import { chatApi } from "@/api/chat";
import { agentsApi } from "@/api/agents";
import type { ChatMessage } from "@/api/types";
import { ApiError } from "@/api/client";
import { queryKeys } from "@/lib/queryKeys";
import { timeAgo } from "@/lib/timeAgo";
import { cn } from "@/lib/utils";
import { useBreadcrumbs } from "@/context/BreadcrumbContext";
import { useToast } from "@/context/ToastContext";
import { EmptyState } from "@/components/EmptyState";
import { PageSkeleton } from "@/components/PageSkeleton";
import { Identity } from "@/components/Identity";
import { BackLink } from "@/components/BackLink";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { deriveAgentStatus, agentStatusDot, agentStatusDotDefault } from "@/lib/status-colors";

export function ChatPage() {
  const { agentId = "" } = useParams<{ agentId: string }>();
  const qc = useQueryClient();
  const { pushToast } = useToast();

  const [body, setBody] = useState("");
  const [subject, setSubject] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const { setBreadcrumbs } = useBreadcrumbs();
  useEffect(() => {
    setBreadcrumbs([
      { label: "Fleet", href: "/fleet" },
      { label: agentId, href: `/agents/${encodeURIComponent(agentId)}` },
      { label: "Chat" },
    ]);
  }, [agentId, setBreadcrumbs]);

  const { data: thread, isLoading } = useQuery({
    queryKey: queryKeys.chat(agentId),
    queryFn: () => chatApi.thread(agentId, 100),
    enabled: !!agentId,
    refetchInterval: 3_000,
  });

  const { data: agentDetail } = useQuery({
    queryKey: queryKeys.agents.detail(agentId),
    queryFn: () => agentsApi.get(agentId),
    enabled: !!agentId,
    refetchInterval: 5_000,
  });

  const messages = thread?.thread ?? [];

  // Auto-scroll on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages.length]);

  const send = useMutation({
    mutationFn: () => chatApi.send(agentId, body, subject.trim() || undefined),
    onSuccess: () => {
      setBody("");
      qc.invalidateQueries({ queryKey: queryKeys.chat(agentId) });
    },
    onError: (err: unknown) => {
      const msg = err instanceof ApiError ? err.message : "Failed to send";
      pushToast(msg, "error");
    },
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!body.trim()) return;
    send.mutate();
  }

  if (isLoading && !thread) return <PageSkeleton variant="detail" />;

  const status = agentDetail
    ? deriveAgentStatus({ stale: agentDetail.stale, paused: agentDetail.agent.paused, process_alive: (agentDetail.agent as { process_alive?: boolean | null }).process_alive })
    : undefined;
  const dotClass = status ? agentStatusDot[status] ?? agentStatusDotDefault : agentStatusDotDefault;

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] min-h-0">
      <div className="shrink-0">
        <BackLink to="/chat" label="Chat list" />
      </div>
      <header className="shrink-0 rounded-lg border border-border bg-card/60 p-4 mb-3">
        <div className="flex items-center gap-3 flex-wrap">
          <span className={cn("inline-block h-2 w-2 rounded-full", dotClass)} />
          <Identity name={agentDetail?.agent.name ?? agentId} />
          <span className="text-xs text-muted-foreground font-mono">{agentId}</span>
          {agentDetail?.agent.role && (
            <span className="text-xs text-muted-foreground">· {agentDetail.agent.role}</span>
          )}
          {agentDetail?.agent.folder && (
            <span className="text-xs text-muted-foreground font-mono truncate max-w-[20rem]">
              · {agentDetail.agent.folder}
            </span>
          )}
          {agentDetail?.last_beat && (
            <span className="ml-auto text-xs text-muted-foreground">
              last beat {timeAgo(agentDetail.last_beat)}
            </span>
          )}
        </div>
      </header>

      <div
        ref={scrollRef}
        className="flex-1 min-h-0 overflow-y-auto rounded-lg border border-border bg-card/30 p-4 space-y-3"
      >
        {messages.length === 0 ? (
          <EmptyState icon={MessageSquare} message="No messages yet. Say hello." />
        ) : (
          messages.map((m) => <MessageBubble key={m.msg_id} message={m} />)
        )}
      </div>

      <form
        onSubmit={onSubmit}
        className="shrink-0 mt-3 rounded-lg border border-border bg-card/60 p-3 space-y-2"
      >
        {showAdvanced && (
          <Input
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="Subject (optional)"
            className="h-8 text-sm"
          />
        )}
        <div className="flex items-end gap-2">
          <Textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder={`Message ${agentDetail?.agent.name ?? agentId}…`}
            rows={2}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                if (body.trim()) send.mutate();
              }
            }}
          />
          <div className="flex flex-col gap-2">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label="Toggle subject"
              onClick={() => setShowAdvanced((v) => !v)}
            >
              <Settings2 className="h-4 w-4" />
            </Button>
            <Button
              type="submit"
              size="sm"
              disabled={send.isPending || !body.trim()}
              aria-label="Send"
            >
              <Send className="h-4 w-4" />
              {send.isPending ? "Sending" : "Send"}
            </Button>
          </div>
        </div>
        <p className="text-[10px] text-muted-foreground">⌘/Ctrl + Enter to send</p>
      </form>
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isOutbound = message.direction === "outbound";
  return (
    <div
      className={cn(
        "flex flex-col gap-1 max-w-[80%]",
        isOutbound ? "ml-auto items-end" : "mr-auto items-start",
      )}
    >
      {!isOutbound && message.from && (
        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <Identity name={message.from} size="xs" />
        </div>
      )}
      <div
        className={cn(
          "rounded-lg border px-3 py-2 text-sm break-words",
          isOutbound
            ? "bg-primary/10 border-primary/20 text-foreground"
            : "bg-card border-border text-foreground",
        )}
      >
        {message.subject && (
          <div className="italic text-xs text-muted-foreground mb-1">{message.subject}</div>
        )}
        <div className="prose prose-sm prose-invert max-w-none prose-p:my-1.5 prose-headings:mt-3 prose-headings:mb-1.5 prose-pre:my-2 prose-pre:bg-muted prose-pre:text-xs prose-code:text-[0.85em] prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:before:content-none prose-code:after:content-none prose-ul:my-1.5 prose-ol:my-1.5 prose-li:my-0 prose-a:text-primary">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.body ?? ""}</ReactMarkdown>
        </div>
      </div>
      <div className="text-[10px] text-muted-foreground flex items-center gap-1.5">
        {isOutbound && message.to && <span className="font-mono">→ {message.to} · </span>}
        {message.created_at ? timeAgo(message.created_at) : ""}
        {!isOutbound && message.read === false && (
          <span
            className="px-1.5 py-0.5 rounded-full text-[9px] font-semibold bg-blue-500/20 text-blue-500 dark:text-blue-400"
            title="Agent hasn't read this yet. Auto-surfaces on its next tool call, or user can type /inbox in the terminal."
          >
            UNREAD
          </span>
        )}
        {!isOutbound && message.read === true && (
          <span className="text-muted-foreground/60">· read</span>
        )}
      </div>
    </div>
  );
}
