import { useEffect } from "react";
import { Link } from "@/lib/router";
import { useBreadcrumbs } from "@/context/BreadcrumbContext";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  const { setBreadcrumbs } = useBreadcrumbs();
  useEffect(() => setBreadcrumbs([{ label: "Not found" }]), [setBreadcrumbs]);

  return (
    <div className="flex flex-col items-center justify-center py-24 text-center space-y-4">
      <div className="text-5xl font-semibold tracking-tight tabular-nums">404</div>
      <p className="text-sm text-muted-foreground">That page doesn't exist.</p>
      <Button asChild>
        <Link to="/dashboard">Back to dashboard</Link>
      </Button>
    </div>
  );
}
