import { cn } from "@/lib/utils";
import { issueStatusIcon, issueStatusIconDefault } from "@/lib/status-colors";

interface StatusIconProps {
  status: string;
  className?: string;
  showLabel?: boolean;
}

function statusLabel(status: string | undefined | null): string {
  if (!status) return "Unknown";
  return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function StatusIcon({ status, className, showLabel }: StatusIconProps) {
  const s = status ?? "unknown";
  const colorClass = issueStatusIcon[s] ?? issueStatusIconDefault;
  const isDone = s === "done";

  const circle = (
    <span
      className={cn(
        "relative inline-flex h-4 w-4 rounded-full border-2 shrink-0",
        colorClass,
        className,
      )}
    >
      {isDone && <span className="absolute inset-0 m-auto h-2 w-2 rounded-full bg-current" />}
    </span>
  );

  if (showLabel) {
    return (
      <span className="inline-flex items-center gap-1.5">
        {circle}
        <span className="text-sm">{statusLabel(status)}</span>
      </span>
    );
  }
  return circle;
}
