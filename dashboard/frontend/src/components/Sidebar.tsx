import {
  Activity,
  CheckSquare,
  FolderKanban,
  Gauge,
  LayoutDashboard,
  Library,
  ListChecks,
  Search,
  Users,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { SidebarNavItem } from "./SidebarNavItem";
import { SidebarSection } from "./SidebarSection";
import { statsApi } from "@/api/stats";
import { queryKeys } from "@/lib/queryKeys";
import { Button } from "@/components/ui/button";
import { useDialogs } from "@/context/DialogContext";
import { useLiveUpdates } from "@/context/LiveUpdatesProvider";
import { cn } from "@/lib/utils";

export function Sidebar() {
  const { data: stats } = useQuery({
    queryKey: queryKeys.stats,
    queryFn: () => statsApi.get(),
    refetchInterval: 10_000,
  });
  const { setCommandPaletteOpen } = useDialogs();
  const { connected } = useLiveUpdates();

  const liveCount = stats?.online ?? 0;
  const pending = stats?.pending_proposals ?? 0;

  return (
    <aside className="w-60 shrink-0 border-r border-border bg-sidebar flex flex-col">
      <div className="h-12 shrink-0 px-3 border-b border-border flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className="h-6 w-6 rounded-md bg-primary text-primary-foreground flex items-center justify-center text-xs font-semibold shrink-0">
            H
          </div>
          <span className="text-sm font-semibold truncate">Harness</span>
        </div>
        <Button
          variant="ghost"
          size="icon-xs"
          aria-label="Search"
          onClick={() => setCommandPaletteOpen(true)}
        >
          <Search className="h-3.5 w-3.5" />
        </Button>
      </div>

      <nav className="flex-1 overflow-y-auto p-2 space-y-3">
        <div className="flex flex-col gap-0.5">
          <SidebarNavItem to="/dashboard" label="Dashboard" icon={LayoutDashboard} />
          <SidebarNavItem to="/fleet" label="Fleet" icon={Users} liveCount={liveCount} />
          <SidebarNavItem to="/events" label="Events" icon={Activity} />
          <SidebarNavItem to="/arsenal" label="Arsenal" icon={Library} />
        </div>

        <SidebarSection label="Work">
          <SidebarNavItem to="/tasks" label="Tasks" icon={ListChecks} />
          <SidebarNavItem to="/proposals" label="Proposals" icon={CheckSquare} badge={pending} badgeTone="default" />
          <SidebarNavItem to="/projects" label="Projects" icon={FolderKanban} />
        </SidebarSection>
      </nav>

      <div className="shrink-0 border-t border-border px-3 py-2 text-[11px] text-muted-foreground flex items-center gap-2">
        <span className={cn(
          "inline-block h-2 w-2 rounded-full",
          connected ? "bg-green-500 animate-pulse" : "bg-muted-foreground/40",
        )} />
        <Gauge className="h-3 w-3" />
        <span>{connected ? "live" : "offline"}</span>
      </div>
    </aside>
  );
}
