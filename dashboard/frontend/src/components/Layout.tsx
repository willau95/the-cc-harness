import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { BreadcrumbBar } from "./BreadcrumbBar";
import { useSidebar } from "@/context/SidebarContext";
import { cn } from "@/lib/utils";
import { CommandPalette } from "./CommandPalette";
import { SpawnAgentDialog } from "./SpawnAgentDialog";
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";

export function Layout() {
  const { sidebarOpen, isMobile, setSidebarOpen } = useSidebar();
  useKeyboardShortcuts();

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
      {/* Mobile overlay */}
      {isMobile && sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <div
        className={cn(
          "z-50 h-full",
          isMobile
            ? cn(
                "fixed left-0 top-0 transition-transform",
                sidebarOpen ? "translate-x-0" : "-translate-x-full",
              )
            : cn(sidebarOpen ? "block" : "hidden"),
        )}
      >
        <Sidebar />
      </div>

      {/* Main column */}
      <div className="flex flex-col flex-1 min-w-0">
        <BreadcrumbBar />
        <main className="flex-1 overflow-auto p-4 md:p-6">
          <Outlet />
        </main>
      </div>

      <CommandPalette />
      <SpawnAgentDialog />
    </div>
  );
}
