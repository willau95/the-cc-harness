import { useEffect } from "react";
import { useNavigate, useParams } from "@/lib/router";
import { FleetControlPanel } from "@/components/FleetControlPanel";
import { useBreadcrumbs } from "@/context/BreadcrumbContext";

const ALLOWED_TABS = new Set(["all", "online", "stale", "paused"]);

export function FleetPage() {
  const { tab: raw } = useParams<{ tab?: string }>();
  const tab = raw && ALLOWED_TABS.has(raw) ? raw : "all";
  const navigate = useNavigate();
  const { setBreadcrumbs } = useBreadcrumbs();

  useEffect(() => {
    const label = tab === "all" ? "Fleet" : `Fleet · ${tab}`;
    setBreadcrumbs([{ label }]);
  }, [tab, setBreadcrumbs]);

  return (
    <FleetControlPanel
      tab={tab}
      onTabChange={(next) => {
        if (next === "all") navigate("/fleet");
        else navigate(`/fleet/${next}`);
      }}
    />
  );
}
