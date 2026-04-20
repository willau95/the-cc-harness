import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fleetApi } from "@/api/fleet";
import { rolesApi } from "@/api/roles";
import { machinesApi } from "@/api/machines";
import { fsApi } from "@/api/fs";
import { equipmentApi } from "@/api/equipment";
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

// Project name is what becomes the folder basename. Strict: lowercase,
// alphanumeric, dash/underscore. No slashes or dots. Prevents a typo like
// ".." from escaping the chosen parent.
const NAME_RE = /^[a-z0-9][a-z0-9_-]{0,63}$/;

function isValidProjectName(n: string): boolean {
  return NAME_RE.test(n.trim());
}

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
  const [projectName, setProjectName] = useState("");
  const [parent, setParent] = useState<string>("");
  const [initialPrompt, setInitialPrompt] = useState("");
  const [machine, setMachine] = useState<string>("__local__");
  const [mode, setMode] = useState<"new" | "adopt">("new");
  const [adoptPath, setAdoptPath] = useState("");
  const [equip, setEquip] = useState<string[]>([]);

  const { data: equipData } = useQuery({
    queryKey: queryKeys.equipment,
    queryFn: () => equipmentApi.list(),
    enabled: spawnOpen,
    staleTime: 60_000,
  });
  const equipmentItems = equipData?.items ?? [];

  // Fetch parent-dir candidates for the selected machine
  const { data: parentDirs, isLoading: parentsLoading } = useQuery({
    queryKey: ["fs", "parent-dirs", machine],
    queryFn: () => fsApi.parentDirs(machine),
    enabled: spawnOpen,
    staleTime: 30_000,
  });

  // When candidates load, auto-pick the first one (harness-test if present, else home)
  useEffect(() => {
    if (!parentDirs || parent) return;
    const best =
      parentDirs.parents.find((p) => p.path.endsWith("/harness-test")) ??
      parentDirs.parents.find((p) => p.path.endsWith("/Desktop")) ??
      parentDirs.parents[0];
    if (best) setParent(best.path);
  }, [parentDirs, parent]);

  useEffect(() => {
    if (!spawnOpen) {
      setName("");
      setRole("");
      setProjectName("");
      setParent("");
      setInitialPrompt("");
      setMachine("__local__");
      setMode("new");
      setAdoptPath("");
      setEquip([]);
    }
  }, [spawnOpen]);

  // Reset parent when user switches machine — candidates on each host differ
  useEffect(() => {
    setParent("");
  }, [machine]);

  // Auto-sync project name → agent name if user hasn't typed one yet
  useEffect(() => {
    if (mode === "new" && projectName && !name) setName(projectName);
    if (mode === "adopt" && adoptPath && !name) {
      const basename = adoptPath.trim().replace(/\/+$/, "").split("/").pop() ?? "";
      const normalized = basename.toLowerCase().replace(/[^a-z0-9_-]/g, "-").replace(/^-+|-+$/g, "");
      if (normalized) setName(normalized);
    }
  }, [mode, projectName, adoptPath, name]);

  const fullFolder = useMemo(() => {
    if (mode === "adopt") return adoptPath.trim();
    if (!parent || !projectName.trim()) return "";
    return `${parent}/${projectName.trim()}`;
  }, [mode, parent, projectName, adoptPath]);

  const nameValid = mode === "adopt" ? name.trim().length > 0 : isValidProjectName(projectName);
  const adoptPathValid = mode === "adopt" ? adoptPath.trim().startsWith("/") && adoptPath.trim().length > 1 : true;
  const ready = Boolean(
    name.trim() && role.trim() && nameValid && adoptPathValid
    && (mode === "adopt" ? adoptPath.trim() : parent)
  );

  const spawn = useMutation({
    mutationFn: () =>
      fleetApi.spawn({
        name: name.trim(),
        role: role.trim(),
        folder: fullFolder,
        initial_prompt: initialPrompt.trim() || undefined,
        machine: machine && machine !== "__local__" ? machine : undefined,
        equip: equip.length > 0 ? equip : undefined,
      }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: queryKeys.fleet });
      qc.invalidateQueries({ queryKey: queryKeys.stats });
      qc.invalidateQueries({ queryKey: queryKeys.machines });
      pushToast(`Spawned ${res.agent_id ?? "agent"} · ${fullFolder}`, "success");
      closeSpawn();
    },
    onError: (err: unknown) => {
      const msg = err instanceof ApiError ? err.message : "Failed to spawn agent";
      pushToast(msg, "error");
    },
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!ready) return;
    spawn.mutate();
  }

  return (
    <Dialog open={spawnOpen} onOpenChange={(open) => { if (!open) closeSpawn(); }}>
      <DialogContent>
        <form onSubmit={onSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Spawn agent</DialogTitle>
            <DialogDescription>
              {mode === "new"
                ? <>Creates <code>{"<parent>/<project-name>"}</code> on the chosen Mac with harness scaffolding, then you <code>cd</code> + <code>claude</code>.</>
                : <>Adds harness to an <b>existing</b> folder (existing code untouched — only <code>.harness/</code> + <code>.claude/</code> added alongside).</>}
            </DialogDescription>
          </DialogHeader>

          <div className="flex rounded-lg border border-border bg-muted/30 p-0.5 text-xs">
            <button
              type="button"
              onClick={() => setMode("new")}
              className={`flex-1 rounded-md py-1.5 transition-colors ${
                mode === "new" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              + New project
            </button>
            <button
              type="button"
              onClick={() => setMode("adopt")}
              className={`flex-1 rounded-md py-1.5 transition-colors ${
                mode === "adopt" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              📂 Adopt existing folder
            </button>
          </div>

          <div className="grid gap-3">
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
                        {m.harness_installed === false ? " · no harness" : ""}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
              {machinesData && !machinesData.fleet_ssh_available && machine !== "__local__" && (
                <p className="text-xs text-yellow-600 dark:text-yellow-400">
                  Remote spawn requires fleet SSH to be available.
                </p>
              )}
              {machine !== "__local__" &&
                machines.find((m) => m.name === machine)?.harness_installed === false && (
                <p className="text-xs text-yellow-600 dark:text-yellow-400">
                  This peer has no harness installed. Install it from the Machines page first.
                </p>
              )}
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

            {mode === "new" ? (
              <>
                <div className="grid gap-1.5">
                  <Label htmlFor="spawn-parent">Parent directory</Label>
                  <Select value={parent} onValueChange={setParent} disabled={parentsLoading}>
                    <SelectTrigger id="spawn-parent" className="w-full">
                      <SelectValue placeholder={parentsLoading ? "Loading…" : "Pick a parent"} />
                    </SelectTrigger>
                    <SelectContent>
                      {(parentDirs?.parents ?? []).map((p) => (
                        <SelectItem key={p.path} value={p.path}>
                          <span className="font-mono text-xs">{p.display}</span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {parentDirs && parentDirs.parents.length === 0 && (
                    <p className="text-xs text-muted-foreground">
                      No common directories found. Make one (e.g. <code>mkdir ~/harness-test</code>) and refresh.
                    </p>
                  )}
                </div>

                <div className="grid gap-1.5">
                  <Label htmlFor="spawn-project-name">Project name (folder)</Label>
                  <Input
                    id="spawn-project-name"
                    placeholder="e.g. gamedev1"
                    value={projectName}
                    onChange={(e) => setProjectName(e.target.value.toLowerCase())}
                    required
                    pattern={NAME_RE.source}
                    autoComplete="off"
                  />
                  {projectName && !isValidProjectName(projectName) && (
                    <p className="text-xs text-destructive">
                      Use lowercase letters, digits, dashes or underscores. No slashes, dots or spaces.
                    </p>
                  )}
                  {fullFolder && isValidProjectName(projectName) && (
                    <p className="text-xs text-muted-foreground font-mono break-all">
                      Will create: <span className="text-foreground">{fullFolder}</span>
                    </p>
                  )}
                </div>
              </>
            ) : (
              <div className="grid gap-1.5">
                <Label htmlFor="spawn-adopt-path">Existing folder (absolute path)</Label>
                <Input
                  id="spawn-adopt-path"
                  placeholder="/Users/you/my-projects/existing-project"
                  value={adoptPath}
                  onChange={(e) => setAdoptPath(e.target.value)}
                  required
                  autoComplete="off"
                  className="font-mono"
                />
                {adoptPath && !adoptPathValid && (
                  <p className="text-xs text-destructive">
                    Must be an absolute path starting with <code>/</code>.
                  </p>
                )}
                <p className="text-xs text-muted-foreground">
                  This folder will get <code>.harness/</code> + <code>.claude/</code> added next to your existing files. Nothing you already have is modified.
                  {machine !== "__local__" && <> The path must exist on <b>{machine}</b>, not here.</>}
                </p>
              </div>
            )}

            <div className="grid gap-1.5">
              <Label htmlFor="spawn-name">Agent name <span className="text-muted-foreground font-normal">(shown in fleet)</span></Label>
              <Input
                id="spawn-name"
                placeholder="defaults to project name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>

            <div className="grid gap-1.5">
              <Label>
                Pre-equip <span className="text-muted-foreground font-normal">(optional — 武器库 items to install at spawn)</span>
              </Label>
              {equipmentItems.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  No equipment in library yet. Add some from <code>/equipment</code>.
                </p>
              ) : (
                <div className="max-h-40 overflow-y-auto rounded border border-border bg-background/50 p-2 space-y-1">
                  {equipmentItems.map((item) => {
                    const checked = equip.includes(item.slug);
                    return (
                      <label
                        key={item.slug}
                        className="flex items-start gap-2 text-xs cursor-pointer hover:bg-accent/30 rounded px-1 py-0.5"
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(e) => {
                            if (e.target.checked) setEquip([...equip, item.slug]);
                            else setEquip(equip.filter((s) => s !== item.slug));
                          }}
                          className="mt-0.5 shrink-0"
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="font-mono text-[11px]">{item.slug}</span>
                            <span className="text-[9px] px-1 py-0.5 rounded bg-muted font-mono">
                              {item.kind}
                            </span>
                          </div>
                          {item.description && (
                            <div className="text-muted-foreground text-[10px] line-clamp-1">{item.description}</div>
                          )}
                        </div>
                      </label>
                    );
                  })}
                </div>
              )}
              {equip.length > 0 && (
                <p className="text-xs text-muted-foreground">
                  Will equip {equip.length}: <code className="text-foreground">{equip.join(", ")}</code>
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
            <Button type="submit" disabled={spawn.isPending || !ready}>
              {spawn.isPending ? "Spawning…" : "Spawn"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
