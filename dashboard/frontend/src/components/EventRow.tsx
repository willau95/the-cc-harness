import { Link } from "@/lib/router";
import type { HarnessEvent } from "@/api/types";
import { Identity } from "./Identity";
import { timeAgo } from "@/lib/timeAgo";
import { cn } from "@/lib/utils";

interface EventRowProps {
  event: HarnessEvent;
  className?: string;
}

function kindLabel(kind: string | undefined | null): string {
  if (!kind) return "event";
  return kind.replace(/_/g, " ").replace(/\./g, " · ");
}

function summaryFromPayload(event: HarnessEvent): string | null {
  for (const key of ["message", "title", "summary", "text"]) {
    const v = (event as Record<string, unknown>)[key];
    if (typeof v === "string" && v.trim()) return v;
  }
  const payload = (event as Record<string, unknown>).payload;
  if (payload && typeof payload === "object") {
    const rec = payload as Record<string, unknown>;
    for (const key of ["message", "title", "summary", "text"]) {
      const v = rec[key];
      if (typeof v === "string" && v.trim()) return v;
    }
  }
  return null;
}

export function EventRow({ event, className }: EventRowProps) {
  const summary = summaryFromPayload(event);
  const agent = event.agent || "system";

  return (
    <Link
      to={`/agents/${encodeURIComponent(agent)}`}
      className={cn(
        "block no-underline text-inherit px-4 py-2 text-sm border-b border-border last:border-b-0 hover:bg-accent/50 transition-colors",
        className,
      )}
    >
      <div className="flex gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 min-w-0">
            <Identity name={agent} size="xs" />
            <span className="text-xs text-muted-foreground font-mono shrink-0">
              {kindLabel(event.type)}
            </span>
          </div>
          {summary && (
            <p className="text-xs text-muted-foreground truncate mt-0.5">{summary}</p>
          )}
        </div>
        <span className="text-xs text-muted-foreground shrink-0 pt-0.5">
          {event.ts ? timeAgo(event.ts) : ""}
        </span>
      </div>
    </Link>
  );
}
