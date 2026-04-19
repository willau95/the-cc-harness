import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fleetApi } from "@/api/fleet";
import { rolesApi } from "@/api/roles";
import { machinesApi } from "@/api/machines";
import { queryKeys } from "@/lib/queryKeys";
import { useDialogs } from "@/context/DialogContext";
import { useToast } from "@/context/ToastContext";
import { ApiError } from "@/api/client";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export function SpawnAgentDialog() {
  const { spawnOpen, closeSpawn } = useDialogs();
  const qc = useQueryClient();
  const { pushToast } = useToast();

  const { data: rolesData } = useQuery({
    queryKey: queryKeys.roles,
    queryFn: () => rolesApi.list(),
    enabled: spawnOpen,
    staleTime: 60_000,
  });
  const roles = rolesData?.roles ?? [];

  const { data: machinesData } = useQuery({
    queryKey: queryKeys.machines,
    queryFn: () => machinesApi.list(),
    enabled: spawnOpen,
    staleTime: 30_000,
  });
  const machines = machinesData?.machines ?? [];

  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [folder, setFolder] = useState("");
  const [initialPrompt, setInitialPrompt] = useState("");
  const [machine, setMachine] = useState<string>("__local__");

  useEffect(() => {
    if (!spawnOpen) {
      // reset on close
      setName("");
      setRole("");
      setFolder("");
      setInitialPrompt("");
      setMachine("__local__");
    }
  }, [spawnOpen]);

  const spawn = useMutation({
    mutationFn: () =>
      fleetApi.spawn({
        name: name.trim(),
        role: role.trim(),
        folder: folder.trim(),
        initial_prompt: initialPrompt.trim() || undefined,
        machine: machine && machine !== "__local__" ? machine : undefined,
      }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: queryKeys.fleet });
      qc.invalidateQueries({ queryKey: queryKeys.stats });
      pushToast(`Spawned ${res.agent_id ?? "agent"}`, "success");
      closeSpawn();
    },
    onError: (err: unknown) => {
      const msg = err instanceof ApiError ? err.message : "Failed to spawn agent";
      pushToast(msg, "error");
    },
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim() || !role.trim() || !folder.trim()) return;
    spawn.mutate();
  }

  return (
    <Dialog open={spawnOpen} onOpenChange={(open) => { if (!open) closeSpawn(); }}>
      <DialogContent>
        <form onSubmit={onSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Spawn agent</DialogTitle>
            <DialogDescription>
              Start a new harness-managed process against a project folder.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="spawn-name">Name</Label>
              <Input
                id="spawn-name"
                placeholder="e.g. claude-local-42"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>

            <div className="grid gap-1.5">
              <Label htmlFor="spawn-role">Role</Label>
              {roles.length > 0 ? (
                <Select value={role} onValueChange={setRole}>
                  <SelectTrigger id="spawn-role" className="w-full">
                    <SelectValue placeholder="Select a role" />
                  </SelectTrigger>
                  <SelectContent>
                    {roles.map((r) => (
                      <SelectItem key={r.slug} value={r.slug}>
                        {r.slug}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <Input
                  id="spawn-role"
                  placeholder="e.g. coder"
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  required
                />
              )}
            </div>

            <div className="grid gap-1.5">
              <Label htmlFor="spawn-folder">Folder</Label>
              <Input
                id="spawn-folder"
                placeholder="/absolute/path/to/project"
                value={folder}
                onChange={(e) => setFolder(e.target.value)}
                required
              />
            </div>

            <div className="grid gap-1.5">
              <Label htmlFor="spawn-machine">Machine</Label>
              <Select value={machine} onValueChange={setMachine}>
                <SelectTrigger id="spawn-machine" className="w-full">
                  <SelectValue placeholder="This machine (local)" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__local__">This machine (local)</SelectItem>
                  {machines
                    .filter((m) => !m.is_local)
                    .map((m) => (
                      <SelectItem key={m.name} value={m.name}>
                        {m.name}
                        {m.user && m.ip ? ` · ${m.user}@${m.ip}` : ""}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
              {machinesData && !machinesData.fleet_ssh_available && machine !== "__local__" && (
                <p className="text-xs text-yellow-600 dark:text-yellow-400">
                  Remote spawn requires fleet SSH to be available.
                </p>
              )}
            </div>

            <div className="grid gap-1.5">
              <Label htmlFor="spawn-prompt">Initial prompt (optional)</Label>
              <Textarea
                id="spawn-prompt"
                placeholder="What should this agent work on?"
                value={initialPrompt}
                onChange={(e) => setInitialPrompt(e.target.value)}
                rows={4}
              />
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={closeSpawn} disabled={spawn.isPending}>
              Cancel
            </Button>
            <Button type="submit" disabled={spawn.isPending || !name.trim() || !role.trim() || !folder.trim()}>
              {spawn.isPending ? "Spawning…" : "Spawn"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
