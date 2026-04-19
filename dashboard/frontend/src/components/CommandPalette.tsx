import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  CheckSquare,
  FolderKanban,
  LayoutDashboard,
  Library,
  ListChecks,
  MessageSquare,
  Plus,
  Users,
} from "lucide-react";
import { useNavigate } from "@/lib/router";
import { fleetApi } from "@/api/fleet";
import { projectsApi } from "@/api/projects";
import { queryKeys } from "@/lib/queryKeys";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { useDialogs } from "@/context/DialogContext";

export function CommandPalette() {
  const { commandPaletteOpen, setCommandPaletteOpen, openSpawn } = useDialogs();
  const navigate = useNavigate();

  const { data: fleet } = useQuery({
    queryKey: queryKeys.fleet,
    queryFn: () => fleetApi.list(),
    enabled: commandPaletteOpen,
    staleTime: 5_000,
  });
  const { data: projects } = useQuery({
    queryKey: queryKeys.projects.all,
    queryFn: () => projectsApi.list(),
    enabled: commandPaletteOpen,
    staleTime: 30_000,
  });

  function go(path: string) {
    setCommandPaletteOpen(false);
    navigate(path);
  }

  return (
    <CommandDialog open={commandPaletteOpen} onOpenChange={setCommandPaletteOpen}>
      <CommandInput placeholder="Search agents, projects, pages…" />
      <CommandList>
        <CommandEmpty>No matches.</CommandEmpty>

        <CommandGroup heading="Actions">
          <CommandItem onSelect={() => { setCommandPaletteOpen(false); openSpawn(); }}>
            <Plus />
            <span>Spawn agent</span>
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="Pages">
          <CommandItem onSelect={() => go("/dashboard")}>
            <LayoutDashboard />
            <span>Dashboard</span>
          </CommandItem>
          <CommandItem onSelect={() => go("/fleet")}>
            <Users />
            <span>Fleet</span>
          </CommandItem>
          <CommandItem onSelect={() => go("/events")}>
            <Activity />
            <span>Events</span>
          </CommandItem>
          <CommandItem onSelect={() => go("/arsenal")}>
            <Library />
            <span>Arsenal</span>
          </CommandItem>
          <CommandItem onSelect={() => go("/tasks")}>
            <ListChecks />
            <span>Tasks</span>
          </CommandItem>
          <CommandItem onSelect={() => go("/proposals")}>
            <CheckSquare />
            <span>Proposals</span>
          </CommandItem>
          <CommandItem onSelect={() => go("/projects")}>
            <FolderKanban />
            <span>Projects</span>
          </CommandItem>
        </CommandGroup>

        {!!fleet?.agents?.length && (
          <>
            <CommandSeparator />
            <CommandGroup heading="Agents">
              {fleet.agents.slice(0, 10).map((a) => (
                <CommandItem
                  key={a.agent_id}
                  value={`${a.agent_id} ${a.name ?? ""} ${a.role ?? ""}`}
                  onSelect={() => go(`/agents/${encodeURIComponent(a.agent_id)}`)}
                >
                  <Users />
                  <span className="truncate">{a.name ?? a.agent_id}</span>
                  <span className="ml-auto text-xs text-muted-foreground font-mono">
                    {a.role ?? ""}
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
            <CommandSeparator />
            <CommandGroup heading="Chat with agent">
              {fleet.agents.slice(0, 10).map((a) => (
                <CommandItem
                  key={`chat-${a.agent_id}`}
                  value={`chat ${a.agent_id} ${a.name ?? ""}`}
                  onSelect={() => go(`/chat/${encodeURIComponent(a.agent_id)}`)}
                >
                  <MessageSquare />
                  <span className="truncate">Chat: {a.name ?? a.agent_id}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        )}

        {!!projects?.projects?.length && (
          <>
            <CommandSeparator />
            <CommandGroup heading="Projects">
              {projects.projects.slice(0, 10).map((p) => (
                <CommandItem
                  key={p.project}
                  value={p.project}
                  onSelect={() => go(`/projects/${encodeURIComponent(p.project)}`)}
                >
                  <FolderKanban />
                  <span className="truncate">{p.project}</span>
                  <span className="ml-auto text-xs text-muted-foreground">
                    {p.member_count} member{p.member_count === 1 ? "" : "s"}
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        )}
      </CommandList>
    </CommandDialog>
  );
}
