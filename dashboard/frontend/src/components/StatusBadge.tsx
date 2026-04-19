import { cn } from "@/lib/utils";
import { statusBadge, statusBadgeDefault } from "@/lib/status-colors";

export function StatusBadge({ status, className }: { status: string | undefined | null; className?: string }) {
  const s = status ?? "unknown";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap shrink-0",
        statusBadge[s] ?? statusBadgeDefault,
        className,
      )}
    >
      {s.replace(/_/g, " ")}
    </span>
  );
}
