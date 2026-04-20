import { useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Download,
  HardDrive,
  Link2,
  Loader2,
  Network,
  Package,
  RefreshCw,
  XCircle,
  Users as UsersIcon,
  ShieldAlert,
} from "lucide-react";
import { Link } from "@/lib/router";
import { machinesApi } from "@/api/machines";
import type { Machine } from "@/api/types";
import { ApiError } from "@/api/client";
import { queryKeys } from "@/lib/queryKeys";
import { useBreadcrumbs } from "@/context/BreadcrumbContext";
import { useToast } from "@/context/ToastContext";
import { PageSkeleton } from "@/components/PageSkeleton";
import { PageHelp } from "@/components/PageHelp";
import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function MachinesPage() {
  const qc = useQueryClient();
  const { pushToast } = useToast();
  const { setBreadcrumbs } = useBreadcrumbs();
  useEffect(() => setBreadcrumbs([{ label: "Machines" }]), [setBreadcrumbs]);

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.machines,
    queryFn: () => machinesApi.list(),
    refetchInterval: 30_000,
  });

  const ping = useMutation({
    mutationFn: (name: string) => machinesApi.ping(name),
    onSuccess: (res, name) => {
      qc.invalidateQueries({ queryKey: queryKeys.machines });
      if (res.ok) pushToast(`${name} online · ${res.latency_ms}ms`, "success");
      else pushToast(`${name} unreachable`, "error");
    },
    onError: (err: unknown, name) => {
      const msg = err instanceof ApiError ? err.message : "Ping failed";
      pushToast(`${name}: ${msg}`, "error");
    },
  });

  const bootstrap = useMutation({
    mutationFn: (name: string) => machinesApi.bootstrap(name),
    onSuccess: (res, name) => {
      qc.invalidateQueries({ queryKey: queryKeys.machines });
      if (res.ok) pushToast(`${name}: peers.yaml updated (${res.peers_count} peers)`, "success");
      else pushToast(`${name}: bootstrap failed`, "error");
    },
  });

  const install = useMutation({
    mutationFn: (name: string) => machinesApi.installHarness(name),
    onSuccess: (res, name) => {
      qc.invalidateQueries({ queryKey: queryKeys.machines });
      if (res.ok) {
        pushToast(
          `${name}: harness ${res.action === "update" ? "updated" : "installed"}`,
          "success",
        );
      } else {
        pushToast(`${name}: install failed — check ${res.stderr?.slice(0, 80) ?? "logs"}`, "error");
      }
    },
    onError: (err: unknown, name) => {
      const msg = err instanceof ApiError ? err.message : "Install failed";
      pushToast(`${name}: ${msg}`, "error");
    },
  });

  if (isLoading && !data) return <PageSkeleton />;

  const machines = data?.machines ?? [];
  const fleetSsh = data?.fleet_ssh_available ?? false;

  return (
    <div className="space-y-4">
      <PageHelp
        storageKey="machines"
        title="Machines — which Macs can your fleet reach"
        summary="Infrastructure view. Every peer agents can spawn on or send messages to lives here."
        bullets={[
          <><b>Transport:</b> mac-fleet-control over Tailscale VPN. If <code>fleet-ssh</code> isn't on your PATH, you'll see a banner telling you how to install it.</>,
          <><b>Online</b> = we can SSH in &lt; 6s. <b>Harness</b> = <code>~/.local/bin/harness --version</code> responds. Both must be true to spawn agents remotely.</>,
          <><b>Test</b> forces a fresh SSH echo. <b>Bootstrap</b> writes <code>~/.harness/peers.yaml</code> on the peer so <i>its</i> mailbox can reach the rest of the fleet (needed after adding a new peer).</>,
          <><b>Agents</b> column counts how many agents are currently registered on that machine — click to jump to Fleet filtered by it.</>,
        ]}
      />

      {!fleetSsh && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 flex items-start gap-3">
          <ShieldAlert className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
          <div className="text-sm space-y-1">
            <div className="font-medium text-foreground">
              fleet-ssh not found on this machine
            </div>
            <div className="text-muted-foreground">
              Without mac-fleet-control installed, the dashboard can only see agents on the local Mac.
              Install it to add remote peers:
            </div>
            <pre className="mt-2 text-xs font-mono bg-muted/60 px-2 py-1 rounded border border-border overflow-auto">
{`git clone https://github.com/willau95/mac-fleet-control ~/mac-fleet-control
cd ~/mac-fleet-control && ./install.sh
fleet-ssh add <peer-name> <peer-tailscale-ip> <peer-user>`}
            </pre>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between gap-2">
        <div className="text-sm text-muted-foreground">
          {machines.length} machine{machines.length === 1 ? "" : "s"}{" "}
          {fleetSsh && <span>· fleet-ssh available</span>}
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => qc.invalidateQueries({ queryKey: queryKeys.machines })}
          disabled={isLoading}
        >
          <RefreshCw className={cn("h-4 w-4", isLoading && "animate-spin")} />
          Refresh
        </Button>
      </div>

      {machines.length === 0 ? (
        <div className="border border-border rounded-lg">
          <EmptyState
            icon={Network}
            message="No machines registered. Add peers via fleet-ssh (see banner above)."
          />
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {machines.map((m) => (
            <MachineCard
              key={m.name}
              m={m}
              onPing={() => ping.mutate(m.name)}
              onBootstrap={() => bootstrap.mutate(m.name)}
              onInstall={() => install.mutate(m.name)}
              pingBusy={ping.isPending && ping.variables === m.name}
              bootstrapBusy={bootstrap.isPending && bootstrap.variables === m.name}
              installBusy={install.isPending && install.variables === m.name}
            />
          ))}
        </div>
      )}

      <div className="rounded-lg border border-border bg-card/40 p-4 space-y-2 text-sm">
        <div className="font-medium text-foreground flex items-center gap-2">
          <Link2 className="h-4 w-4" />
          Adding a new peer — one-time setup
        </div>
        <ol className="list-decimal list-inside space-y-1 text-muted-foreground text-xs">
          <li>On the new Mac: install Tailscale, sign in with the same account</li>
          <li>On this Mac: <code className="px-1 py-0.5 bg-muted/60 rounded">fleet-ssh add &lt;name&gt; &lt;tailscale-ip&gt; &lt;user&gt;</code> (pushes your SSH key)</li>
          <li>On the new Mac: <code className="px-1 py-0.5 bg-muted/60 rounded">git clone https://github.com/willau95/the-cc-harness && cd the-cc-harness && ./install.sh</code></li>
          <li>Back here: Refresh — the peer should appear. Click Test to verify, then Bootstrap so its mailbox learns the fleet</li>
          <li>Spawn agents on it via <Link to="/fleet" className="text-primary hover:underline">Fleet → Spawn Agent</Link> (pick the machine in the dialog)</li>
        </ol>
      </div>
    </div>
  );
}

function MachineCard({
  m, onPing, onBootstrap, onInstall, pingBusy, bootstrapBusy, installBusy,
}: {
  m: Machine;
  onPing: () => void;
  onBootstrap: () => void;
  onInstall: () => void;
  pingBusy: boolean;
  bootstrapBusy: boolean;
  installBusy: boolean;
}) {
  const online = Boolean(m.online);
  const harnessOk = Boolean(m.harness_installed);
  const local = Boolean(m.is_local);

  return (
    <div className="rounded-lg border border-border bg-card/60 p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={cn(
            "inline-block h-2.5 w-2.5 rounded-full shrink-0",
            local ? "bg-primary" :
            online ? "bg-green-500" : "bg-muted-foreground/40"
          )} />
          <h3 className="font-semibold truncate">{m.name}</h3>
          {local && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/20 text-primary font-medium">
              local
            </span>
          )}
        </div>
        {!local && (
          <span className="text-xs text-muted-foreground tabular-nums shrink-0">
            {online && m.latency_ms != null ? `${m.latency_ms}ms` : online ? "" : "offline"}
          </span>
        )}
      </div>

      <dl className="grid grid-cols-[80px_1fr] gap-y-1.5 text-xs">
        {m.user && (
          <>
            <dt className="text-muted-foreground">User</dt>
            <dd className="font-mono text-foreground truncate">{m.user}</dd>
          </>
        )}
        {m.ip && (
          <>
            <dt className="text-muted-foreground">IP</dt>
            <dd className="font-mono text-foreground truncate">{m.ip}</dd>
          </>
        )}
        <dt className="text-muted-foreground">Harness</dt>
        <dd className="flex items-center gap-1.5">
          {harnessOk ? (
            <CheckCircle2 className="h-3 w-3 text-green-500 shrink-0" />
          ) : (
            <XCircle className="h-3 w-3 text-muted-foreground shrink-0" />
          )}
          <span className={cn("truncate", harnessOk ? "font-mono text-foreground" : "text-muted-foreground")}>
            {local ? "local" : harnessOk ? (m.harness_version ?? "installed") : "not installed"}
          </span>
        </dd>
        <dt className="text-muted-foreground">Agents</dt>
        <dd className="flex items-center gap-1.5">
          <UsersIcon className="h-3 w-3 text-muted-foreground" />
          <span className="tabular-nums">{m.agent_count ?? 0}</span>
        </dd>
      </dl>

      {!online && !local && (
        <div className="text-xs text-muted-foreground rounded border border-border/60 bg-muted/20 px-2 py-1.5">
          Last SSH probe failed. Check Tailscale on the peer, then click Test.
        </div>
      )}
      {online && !harnessOk && !local && (
        <div className="text-xs text-muted-foreground rounded border border-border/60 bg-muted/20 px-2 py-1.5 flex items-start gap-1.5">
          <Package className="h-3 w-3 shrink-0 mt-0.5" />
          <span>SSH works but harness is missing. Click <b>Install</b> below to clone + run <code>./install.sh</code> over fleet-ssh.</span>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 pt-1">
        {!local && (
          <Button size="sm" variant="outline" onClick={onPing} disabled={pingBusy}>
            <RefreshCw className={cn("h-3.5 w-3.5", pingBusy && "animate-spin")} />
            Test
          </Button>
        )}
        {!local && online && !harnessOk && (
          <Button size="sm" onClick={onInstall} disabled={installBusy}>
            {installBusy ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Download className="h-3.5 w-3.5" />
            )}
            {installBusy ? "Installing…" : "Install"}
          </Button>
        )}
        {!local && online && harnessOk && (
          <Button size="sm" variant="ghost" onClick={onInstall} disabled={installBusy}
                  title="Pull latest main + re-run install.sh">
            {installBusy ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Download className="h-3.5 w-3.5" />
            )}
            {installBusy ? "Updating…" : "Update"}
          </Button>
        )}
        {!local && online && (
          <Button size="sm" variant="outline" onClick={onBootstrap} disabled={bootstrapBusy}>
            <Link2 className="h-3.5 w-3.5" />
            Bootstrap
          </Button>
        )}
        <Link
          to={local ? "/fleet" : `/fleet?machine=${encodeURIComponent(m.name)}`}
          className="text-xs text-primary hover:underline ml-auto inline-flex items-center gap-1"
        >
          <HardDrive className="h-3 w-3" />
          View agents →
        </Link>
      </div>
    </div>
  );
}
