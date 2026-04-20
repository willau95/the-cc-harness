import { ChevronLeft } from "lucide-react";
import { Link } from "@/lib/router";

/** Prominent "← Back to X" link for detail pages. Sits above the page title. */
export function BackLink({ to, label }: { to: string; label: string }) {
  return (
    <Link
      to={to}
      className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors mb-3"
    >
      <ChevronLeft className="h-4 w-4" />
      Back to {label}
    </Link>
  );
}
