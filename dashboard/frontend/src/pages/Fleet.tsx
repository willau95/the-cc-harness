import { useEffect } from "react";
import { useNavigate, useParams } from "@/lib/router";
import { FleetControlPanel } from "@/components/FleetControlPanel";
import { PageHelp } from "@/components/PageHelp";
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
    <div className="space-y-4">
      <PageHelp
        storageKey="fleet"
        title="Fleet — your Claude Code agents across every Mac"
        summary="Spawn, pause, resume, or kill any agent. Click a row to open its detail."
        bullets={[
          <><b>One agent = one Claude Code process.</b> Each has its own folder, role, and persistent memory</>,
          <><b>Spawn Agent</b> → pick a role from 161 presets, pick a machine (local or a peer over fleet-ssh), give a name</>,
          <><b>Pause</b> writes a sentinel file; the agent's next skill-tool call short-circuits until you Resume</>,
          <><b>Kill</b> terminates the Claude Code process. The identity stays on disk so you can re-spawn it later</>,
          <><b>Stale</b> = no heartbeat in the timeout window (default 30 min). Usually means zombie or offline</>,
        ]}
      />
      <FleetControlPanel
        tab={tab}
        onTabChange={(next) => {
          if (next === "all") navigate("/fleet");
          else navigate(`/fleet/${next}`);
        }}
      />
    </div>
  );
}
