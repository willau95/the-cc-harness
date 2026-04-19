import { cn } from "@/lib/utils";
import { trustBadge, trustBadgeDefault } from "@/lib/status-colors";

export function TrustBadge({ trust, className }: { trust: string | undefined | null; className?: string }) {
  const t = trust ?? "unknown";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap shrink-0",
        trustBadge[t] ?? trustBadgeDefault,
        className,
      )}
    >
      {t.replace(/_/g, " ")}
    </span>
  );
}
