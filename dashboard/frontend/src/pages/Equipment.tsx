import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Boxes,
  Plus,
  Search as SearchIcon,
  Wrench,
  Terminal,
  Bot,
  Server,
  Zap,
  FolderGit2,
  FileText as FileTextIcon,
  CircleCheck,
  CircleAlert,
  CircleHelp,
} from "lucide-react";
import { useParams, useNavigate, Link } from "@/lib/router";
import { equipmentApi, type EquipmentItem, type EquipmentAddRequest } from "@/api/equipment";
import { queryKeys } from "@/lib/queryKeys";
import { useBreadcrumbs } from "@/context/BreadcrumbContext";
import { useToast } from "@/context/ToastContext";
import { ApiError } from "@/api/client";
import { PageSkeleton } from "@/components/PageSkeleton";
import { PageHelp } from "@/components/PageHelp";
import { EmptyState } from "@/components/EmptyState";
import { BackLink } from "@/components/BackLink";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { EquipmentFileBrowser } from "@/components/EquipmentFileBrowser";
import { Tabs } from "@/components/ui/tabs";
import { PageTabBar } from "@/components/PageTabBar";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { timeAgo } from "@/lib/timeAgo";
import { cn } from "@/lib/utils";

const KIND_META: Record<EquipmentItem["kind"], { icon: typeof Wrench; label: string; color: string; desc: string }> = {
  skill:    { icon: Wrench,      label: "skill",    color: "text-cyan-500",    desc: "Claude Code skill — auto-discovered at session start, loaded on demand by description match" },
  command:  { icon: Terminal,    label: "command",  color: "text-violet-500",  desc: "Slash command — user types /<slug> in the claude terminal" },
  subagent: { icon: Bot,         label: "subagent", color: "text-blue-500",    desc: "Subagent — main agent invokes via Task(subagent_type=slug)" },
  mcp:      { icon: Server,      label: "mcp",      color: "text-emerald-500", desc: "MCP server — merged into settings.local.json mcpServers block" },
  hook:     { icon: Zap,         label: "hook",     color: "text-amber-500",   desc: "Lifecycle hook — merged into settings.local.json hooks block" },
  repo:     { icon: FolderGit2,  label: "repo",     color: "text-orange-500",  desc: "Reference repo — symlinked to .harness/equipment/<slug>/source/ for agent to Read" },
  preamble: { icon: FileTextIcon,label: "preamble", color: "text-pink-500",    desc: "CLAUDE.md snippet — appended between equipment markers" },
};

const TRUST_BADGE: Record<string, string> = {
  human_verified: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  analyst_reviewed: "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300",
  experimental: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300",
  retracted: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
};

export function EquipmentPage() {
  const { setBreadcrumbs } = useBreadcrumbs();
  useEffect(() => setBreadcrumbs([{ label: "Equipment (武器库)" }]), [setBreadcrumbs]);

  const [filterKind, setFilterKind] = useState<string>("all");
  const [query, setQuery] = useState("");
  const [addOpen, setAddOpen] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.equipment,
    queryFn: () => equipmentApi.list(),
    refetchInterval: 30_000,
  });

  const filtered = useMemo(() => {
    const items = data?.items ?? [];
    let out = filterKind === "all" ? items : items.filter((i) => i.kind === filterKind);
    if (query.trim()) {
      const q = query.toLowerCase();
      out = out.filter(
        (i) =>
          i.slug.toLowerCase().includes(q) ||
          i.name.toLowerCase().includes(q) ||
          (i.description ?? "").toLowerCase().includes(q) ||
          (i.topics ?? []).some((t) => t.toLowerCase().includes(q)),
      );
    }
    return out;
  }, [data, filterKind, query]);

  if (isLoading && !data) return <PageSkeleton />;

  return (
    <div className="space-y-4">
      <PageHelp
        storageKey="equipment"
        title="Equipment (武器库) — shared library of Claude Code artifacts"
        summary="Skills / commands / subagents / MCP servers / repos that agents can equip at spawn time."
        bullets={[
          <><b>Not arsenal:</b> arsenal = text knowledge. Equipment = installable Claude Code artifacts (runnable code/config)</>,
          <><b>Installation:</b> each item maps to Claude Code's native discovery slot — <code>.claude/skills/&lt;slug&gt;/</code>, <code>.claude/commands/&lt;slug&gt;.md</code>, etc. No custom loader.</>,
          <><b>Pre-equip at spawn:</b> the Spawn dialog lets you tick multiple items; they're installed before <code>claude</code> starts, so the agent boots already-equipped.</>,
          <><b>武器说明书:</b> every item has an <code>analysis.md</code> — a brief written report the agent reads to decide whether to use it, instead of re-analyzing the source itself (saves tokens for all downstream consumers).</>,
        ]}
      />

      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Select value={filterKind} onValueChange={setFilterKind}>
            <SelectTrigger className="w-40">
              <SelectValue placeholder="All kinds" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All kinds</SelectItem>
              {Object.keys(KIND_META).map((k) => (
                <SelectItem key={k} value={k}>{k}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="relative">
            <SearchIcon className="h-3.5 w-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search name / slug / topic…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="pl-8 w-72"
            />
          </div>
          <span className="text-xs text-muted-foreground tabular-nums">
            {filtered.length} item{filtered.length === 1 ? "" : "s"}
          </span>
        </div>
        <Button size="sm" onClick={() => setAddOpen(true)}>
          <Plus className="h-4 w-4" />
          Add equipment
        </Button>
      </div>

      {filtered.length === 0 ? (
        <div className="border border-border rounded-lg">
          <EmptyState icon={Boxes} message="No equipment items match. Add your first one →" />
        </div>
      ) : (
        <div className="grid gap-2">
          {filtered.map((item) => (
            <EquipmentRow key={item.slug} item={item} />
          ))}
        </div>
      )}

      <AddEquipmentDialog open={addOpen} onOpenChange={setAddOpen} />
    </div>
  );
}

function EquipmentRow({ item }: { item: EquipmentItem }) {
  const meta = KIND_META[item.kind] ?? KIND_META.skill;
  const Icon = meta.icon;
  const trustCls = TRUST_BADGE[item.trust ?? "experimental"] ?? TRUST_BADGE.experimental;
  return (
    <Link
      to={`/equipment/${encodeURIComponent(item.slug)}`}
      className="block no-underline text-inherit border border-border rounded-lg px-4 py-3 hover:bg-accent/40 transition-colors"
    >
      <div className="flex items-start gap-3">
        <Icon className={cn("h-4 w-4 shrink-0 mt-0.5", meta.color)} />
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className="font-mono text-xs text-muted-foreground">{item.slug}</span>
            <span className="text-sm font-medium truncate">{item.name}</span>
            <span className={cn("text-[10px] px-1.5 py-0.5 rounded font-mono", trustCls)}>
              {item.trust ?? "experimental"}
            </span>
            <span className={cn("text-[10px] px-1.5 py-0.5 rounded bg-muted font-mono", meta.color)}>
              {meta.label}
            </span>
          </div>
          {item.description && (
            <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{item.description}</p>
          )}
          {item.topics && item.topics.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1">
              {item.topics.map((t) => (
                <span key={t} className="text-[10px] px-1.5 py-0.5 rounded bg-muted/60 text-muted-foreground">
                  {t}
                </span>
              ))}
            </div>
          )}
        </div>
        {item.added_at && (
          <span className="text-[10px] text-muted-foreground shrink-0 pt-0.5">
            {timeAgo(item.added_at)}
          </span>
        )}
      </div>
    </Link>
  );
}

function AddEquipmentDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const { pushToast } = useToast();
  const [kind, setKind] = useState<EquipmentItem["kind"]>("skill");
  const [source, setSource] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const [topics, setTopics] = useState("");
  const [trust, setTrust] = useState<EquipmentItem["trust"]>("experimental");

  useEffect(() => {
    if (!open) {
      setSource("");
      setSlug("");
      setDescription("");
      setTopics("");
      setKind("skill");
      setTrust("experimental");
    }
  }, [open]);

  const add = useMutation({
    mutationFn: () => {
      const req: EquipmentAddRequest = {
        kind,
        source: source.trim(),
        slug: slug.trim() || undefined,
        description: description.trim() || undefined,
        topics: topics.split(",").map((t) => t.trim()).filter(Boolean),
        trust,
        source_url: source.trim().startsWith("http") ? source.trim() : undefined,
      };
      return equipmentApi.add(req);
    },
    onSuccess: (res) => {
      if (res.ok) {
        qc.invalidateQueries({ queryKey: queryKeys.equipment });
        pushToast(`Added ${res.meta.slug} (${res.meta.kind})`, "success");
        onOpenChange(false);
      } else {
        pushToast(res.error ?? "Add failed", "error");
      }
    },
    onError: (err: unknown) => {
      pushToast(err instanceof ApiError ? err.message : "Add failed", "error");
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!source.trim()) return;
    add.mutate();
  };

  const meta = KIND_META[kind];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={onSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Add equipment</DialogTitle>
            <DialogDescription>
              Import a Claude Code artifact into the shared library so agents can equip it at spawn.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="eq-kind">Kind</Label>
              <Select value={kind} onValueChange={(v) => setKind(v as EquipmentItem["kind"])}>
                <SelectTrigger id="eq-kind">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(KIND_META).map(([k, m]) => (
                    <SelectItem key={k} value={k}>
                      <span className="font-mono text-xs mr-2">{k}</span>
                      <span className="text-xs text-muted-foreground">{m.desc.split("—")[0].trim()}</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">{meta.desc}</p>
            </div>

            <div className="grid gap-1.5">
              <Label htmlFor="eq-source">Source (local path or git URL)</Label>
              <Input
                id="eq-source"
                placeholder={
                  kind === "skill"
                    ? "/path/to/skill-dir  OR  https://github.com/x/skill-repo"
                    : kind === "command" || kind === "subagent" || kind === "preamble"
                    ? "/path/to/file.md"
                    : "/path/to/config.json or dir"
                }
                value={source}
                onChange={(e) => setSource(e.target.value)}
                required
                className="font-mono text-xs"
              />
            </div>

            <div className="grid gap-1.5">
              <Label htmlFor="eq-slug">Slug <span className="text-muted-foreground font-normal">(optional — auto from source name)</span></Label>
              <Input
                id="eq-slug"
                placeholder="e.g. twitter-client"
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                className="font-mono text-xs"
              />
            </div>

            <div className="grid gap-1.5">
              <Label htmlFor="eq-description">Description <span className="text-muted-foreground font-normal">(auto-read from SKILL.md if present)</span></Label>
              <Textarea
                id="eq-description"
                placeholder="When should agents use this?"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
              />
            </div>

            <div className="grid gap-1.5">
              <Label htmlFor="eq-topics">Topics <span className="text-muted-foreground font-normal">(comma-separated)</span></Label>
              <Input
                id="eq-topics"
                placeholder="e.g. twitter, social, scraping"
                value={topics}
                onChange={(e) => setTopics(e.target.value)}
              />
            </div>

            <div className="grid gap-1.5">
              <Label htmlFor="eq-trust">Trust</Label>
              <Select value={trust} onValueChange={(v) => setTrust(v as EquipmentItem["trust"])}>
                <SelectTrigger id="eq-trust">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="experimental">experimental — just added, not yet reviewed</SelectItem>
                  <SelectItem value="analyst_reviewed">analyst_reviewed — equipment manager wrote analysis.md</SelectItem>
                  <SelectItem value="human_verified">human_verified — you approved it</SelectItem>
                  <SelectItem value="retracted">retracted — do not use</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)} disabled={add.isPending}>
              Cancel
            </Button>
            <Button type="submit" disabled={add.isPending || !source.trim()}>
              {add.isPending ? "Adding…" : "Add"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function EquipmentDetailPage() {
  const { slug = "" } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { pushToast } = useToast();
  const { setBreadcrumbs } = useBreadcrumbs();
  useEffect(() => {
    setBreadcrumbs([{ label: "Equipment", href: "/equipment" }, { label: slug }]);
  }, [slug, setBreadcrumbs]);

  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys.equipment_detail(slug),
    queryFn: () => equipmentApi.get(slug),
    enabled: !!slug,
  });

  const setTrust = useMutation({
    mutationFn: (trust: string) => equipmentApi.setTrust(slug, trust),
    onSuccess: (_res, trust) => {
      qc.invalidateQueries({ queryKey: queryKeys.equipment });
      qc.invalidateQueries({ queryKey: queryKeys.equipment_detail(slug) });
      pushToast(`Trust → ${trust.replace(/_/g, " ")}`, "success");
    },
    onError: (err: unknown) => {
      pushToast(err instanceof ApiError ? err.message : "Trust update failed", "error");
    },
  });

  if (isLoading && !data) return <PageSkeleton />;
  if (error || !data) {
    return (
      <div className="space-y-2">
        <BackLink to="/equipment" label="Equipment" />
        <div className="border border-border rounded-lg">
          <EmptyState
            icon={Boxes}
            message={`Equipment not found: ${slug}`}
            action="Back"
            onAction={() => navigate("/equipment")}
          />
        </div>
      </div>
    );
  }

  const meta = KIND_META[data.kind] ?? KIND_META.skill;
  const Icon = meta.icon;
  const trustCls = TRUST_BADGE[data.trust ?? "experimental"] ?? TRUST_BADGE.experimental;

  return (
    <div className="space-y-4">
      <BackLink to="/equipment" label="Equipment" />
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-4 min-w-0">
          <section className="rounded-lg border border-border bg-card/60 p-4 md:p-5 space-y-3">
            <div className="flex items-center gap-2 text-xs text-muted-foreground font-mono">
              <Icon className={cn("h-4 w-4", meta.color)} />
              <span>{data.slug}</span>
            </div>
            <div className="flex items-start gap-3 flex-wrap">
              <h2 className="text-lg font-semibold flex-1 min-w-0 break-words">{data.name}</h2>
              <span className={cn("text-[10px] px-1.5 py-0.5 rounded font-mono", trustCls)}>
                {data.trust}
              </span>
              <span className={cn("text-[10px] px-1.5 py-0.5 rounded bg-muted font-mono", meta.color)}>
                {meta.label}
              </span>
            </div>
            {data.description && (
              <p className="text-sm text-muted-foreground">{data.description}</p>
            )}
            <div className="pt-2 border-t border-border/60 space-y-2">
              <p className="text-xs text-muted-foreground">
                {data.trust === "human_verified" && "You approved this. Agents can equip with high confidence."}
                {data.trust === "analyst_reviewed" && "A manager agent analyzed and wrote the report. Not yet your approval."}
                {data.trust === "experimental" && "Just added — not reviewed. Verify if the analysis looks right to you."}
                {data.trust === "retracted" && "Retracted. Agents will skip this at equip time."}
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  onClick={() => setTrust.mutate("human_verified")}
                  disabled={setTrust.isPending || data.trust === "human_verified"}
                >
                  <CircleCheck className="h-4 w-4" />
                  {data.trust === "human_verified" ? "Verified ✓" : "Mark verified"}
                </Button>
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={() => setTrust.mutate("retracted")}
                  disabled={setTrust.isPending || data.trust === "retracted"}
                >
                  <CircleAlert className="h-4 w-4" />
                  {data.trust === "retracted" ? "Retracted" : "Retract"}
                </Button>
                {setTrust.isPending && (
                  <span className="text-xs text-muted-foreground">Updating…</span>
                )}
              </div>
            </div>
          </section>

          <DetailContentTabs slug={data.slug} analysis={data.analysis ?? ""} />
        </div>

        <aside className="space-y-4">
          <section className="rounded-lg border border-border bg-card/60 p-4 space-y-3 text-sm">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              How it installs
            </h3>
            <div className="text-xs text-muted-foreground space-y-1.5">
              <p>{meta.desc}</p>
              <p>Path it lands on at equip time (Claude Code auto-discovers here):</p>
              <code className="block font-mono text-[11px] bg-background/60 px-2 py-1 rounded border border-border">
                {data.kind === "skill" && `<agent>/.claude/skills/${data.slug}/SKILL.md`}
                {data.kind === "command" && `<agent>/.claude/commands/${data.slug}.md`}
                {data.kind === "subagent" && `<agent>/.claude/agents/${data.slug}.md`}
                {data.kind === "mcp" && `<agent>/.claude/settings.local.json (mcpServers)`}
                {data.kind === "hook" && `<agent>/.claude/settings.local.json (hooks)`}
                {data.kind === "repo" && `<agent>/.harness/equipment/${data.slug}/source/`}
                {data.kind === "preamble" && `<agent>/CLAUDE.md (between <!-- equipment:${data.slug} --> markers)`}
              </code>
            </div>
          </section>

          <section className="rounded-lg border border-border bg-card/60 p-4 space-y-3 text-sm">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Metadata</h3>
            <MetaRow label="Slug" value={<span className="font-mono text-xs">{data.slug}</span>} />
            <MetaRow label="Kind" value={<span className="font-mono text-xs">{data.kind}</span>} />
            {data.source_url && (
              <MetaRow
                label="Source"
                value={
                  <a href={data.source_url} target="_blank" rel="noopener noreferrer"
                     className="text-primary hover:underline break-all text-xs">
                    {data.source_url}
                  </a>
                }
              />
            )}
            {data.topics && data.topics.length > 0 && (
              <MetaRow
                label="Topics"
                value={
                  <div className="flex flex-wrap gap-1 justify-end">
                    {data.topics.map((t) => (
                      <span key={t} className="text-[10px] px-1 py-0.5 rounded bg-muted/60">
                        {t}
                      </span>
                    ))}
                  </div>
                }
              />
            )}
            <MetaRow label="Added" value={data.added_at ? timeAgo(data.added_at) : "—"} />
            {data.added_by && <MetaRow label="By" value={<span className="font-mono text-xs">{data.added_by}</span>} />}
          </section>

          <section className="rounded-lg border border-border bg-card/60 p-4 text-xs text-muted-foreground">
            <div className="flex items-center gap-2 text-foreground font-medium mb-2">
              <TrustIcon trust={data.trust} />
              Trust · {data.trust}
            </div>
            <TrustDescription trust={data.trust} />
          </section>
        </aside>
      </div>
    </div>
  );
}

function DetailContentTabs({ slug, analysis }: { slug: string; analysis: string }) {
  const [tab, setTab] = useState<"files" | "analysis">("files");
  const items = [
    { value: "files", label: "Files" },
    { value: "analysis", label: "武器说明书 · Analysis" },
  ];
  return (
    <Tabs value={tab} onValueChange={(v) => setTab(v as "files" | "analysis")} className="space-y-3">
      <PageTabBar items={items} value={tab} onValueChange={(v) => setTab(v as "files" | "analysis")} />
      {tab === "files" && <EquipmentFileBrowser slug={slug} />}
      {tab === "analysis" && (
        <div className="rounded-lg border border-border bg-card/60 p-4 prose prose-sm prose-invert max-w-none">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {analysis || "_(no analysis written yet — placeholder. The equipment-manager agent will fill this in automatically.)_"}
          </ReactMarkdown>
        </div>
      )}
    </Tabs>
  );
}

function MetaRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-2 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-foreground text-right min-w-0">{value}</span>
    </div>
  );
}

function TrustIcon({ trust }: { trust?: string }) {
  if (trust === "human_verified") return <CircleCheck className="h-3.5 w-3.5 text-emerald-500" />;
  if (trust === "retracted") return <CircleAlert className="h-3.5 w-3.5 text-red-500" />;
  if (trust === "analyst_reviewed") return <CircleCheck className="h-3.5 w-3.5 text-cyan-500" />;
  return <CircleHelp className="h-3.5 w-3.5 text-yellow-500" />;
}

function TrustDescription({ trust }: { trust?: string }) {
  switch (trust) {
    case "human_verified": return <>You approved this. Agents use it with high confidence.</>;
    case "analyst_reviewed": return <>The equipment manager ran an analysis and wrote the report above. Not yet human-blessed.</>;
    case "retracted": return <>Marked retracted. Agents will skip equipping this.</>;
    default: return <>Experimental — just added, no review yet. Agents may still equip it but should treat it as provisional.</>;
  }
}
