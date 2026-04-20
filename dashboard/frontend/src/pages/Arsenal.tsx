import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Copy,
  ExternalLink,
  Library,
  MoreHorizontal,
  Plus,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { useNavigate, useParams } from "@/lib/router";
import { arsenalApi } from "@/api/arsenal";
import type { ArsenalItem } from "@/api/types";
import { ApiError } from "@/api/client";
import { queryKeys } from "@/lib/queryKeys";
import { timeAgo } from "@/lib/timeAgo";
import { useBreadcrumbs } from "@/context/BreadcrumbContext";
import { useToast } from "@/context/ToastContext";
import { PageTabBar } from "@/components/PageTabBar";
import { Tabs, TabsContent } from "@/components/ui/tabs";
import { EmptyState } from "@/components/EmptyState";
import { PageSkeleton } from "@/components/PageSkeleton";
import { TrustBadge } from "@/components/TrustBadge";
import { PageHelp } from "@/components/PageHelp";
import { BackLink } from "@/components/BackLink";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const ALLOWED_TABS = new Set([
  "all",
  "verified",
  "peer_verified",
  "agent_summary",
  "hypothesis",
  "retracted",
]);

const TABS = [
  { value: "all", label: "All" },
  { value: "verified", label: "Verified" },
  { value: "peer_verified", label: "Peer-verified" },
  { value: "agent_summary", label: "Agent-summary" },
  { value: "hypothesis", label: "Hypothesis" },
  { value: "retracted", label: "Retracted" },
];

function parseSourceRefs(raw: string | null | undefined): string[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed.filter((v) => typeof v === "string");
  } catch {
    // not JSON — treat as csv fallback
  }
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function parseTags(raw: string | null | undefined): string[] {
  if (!raw) return [];
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export function ArsenalPage() {
  const [tab, setTab] = useState<string>("all");
  const [query, setQuery] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { pushToast } = useToast();

  const { setBreadcrumbs } = useBreadcrumbs();
  useEffect(() => {
    const label = tab === "all" ? "Arsenal" : `Arsenal · ${tab.replace(/_/g, " ")}`;
    setBreadcrumbs([{ label }]);
  }, [tab, setBreadcrumbs]);

  const trustParam = tab === "all" ? undefined : tab;
  const { data, isLoading } = useQuery({
    queryKey: queryKeys.arsenal.list(tab),
    queryFn: () => arsenalApi.list(trustParam, 100),
    refetchInterval: 10_000,
  });

  const items = useMemo(() => {
    const all = data?.items ?? [];
    if (!query.trim()) return all;
    const q = query.toLowerCase();
    return all.filter((it) => {
      if (it.title.toLowerCase().includes(q)) return true;
      if (it.slug.toLowerCase().includes(q)) return true;
      const tags = parseTags(it.tags);
      return tags.some((t) => t.toLowerCase().includes(q));
    });
  }, [data, query]);

  const setTrust = useMutation({
    mutationFn: ({ slug, trust }: { slug: string; trust: string }) => arsenalApi.setTrust(slug, trust),
    onSuccess: (_res, vars) => {
      qc.invalidateQueries({ queryKey: queryKeys.arsenal.all });
      qc.invalidateQueries({ queryKey: queryKeys.arsenal.detail(vars.slug) });
      pushToast(`Trust → ${vars.trust.replace(/_/g, " ")}`, "success");
    },
    onError: (err: unknown) => {
      const msg = err instanceof ApiError ? err.message : "Failed to update trust";
      pushToast(msg, "error");
    },
  });

  const onChangeTab = (v: string) => {
    if (ALLOWED_TABS.has(v)) setTab(v);
  };

  if (isLoading && !data) return <PageSkeleton />;

  const dist = data?.trust_distribution ?? {};

  return (
    <div className="space-y-4">
      <PageHelp
        storageKey="arsenal"
        title="Arsenal — shared knowledge base (武器库)"
        summary="Every peer writes findings here; the best get promoted to human-verified."
        bullets={[
          <><b>Who writes to it:</b> agents call <code>arsenal_add</code> after researching something worth keeping</>,
          <><b>Trust tiers:</b> agent-summary (default) → peer-verified (critic) → human-verified (you)</>,
          <><b>Your job:</b> browse, Mark verified the ones that are actually correct, Retract the wrong ones</>,
          <><b>Cross-machine:</b> items from all peers aggregate here; the owning machine is shown on each row</>,
        ]}
      />
      <Tabs value={tab} onValueChange={onChangeTab}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <PageTabBar items={TABS} value={tab} onValueChange={onChangeTab} />
          <div className="flex items-center gap-3">
            <div className="hidden md:flex items-center gap-2 text-xs text-muted-foreground">
              {Object.entries(dist)
                .filter(([, n]) => (n as number) > 0)
                .map(([k, n]) => (
                  <span key={k} className="inline-flex items-center gap-1">
                    <TrustBadge trust={k} />
                    <span className="tabular-nums">{n as number}</span>
                  </span>
                ))}
            </div>
            <Button size="sm" onClick={() => setAddOpen(true)}>
              <Plus className="h-4 w-4" />
              Add item
            </Button>
          </div>
        </div>

        <TabsContent value={tab} className="mt-3 space-y-3">
          <div className="flex items-center gap-2">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter by title, slug, or tag…"
              className="max-w-sm"
            />
            <span className="ml-auto text-xs text-muted-foreground tabular-nums">
              {items.length} item{items.length === 1 ? "" : "s"}
            </span>
          </div>

          <div className="border border-border rounded-lg overflow-hidden">
            {items.length === 0 ? (
              <EmptyState icon={Library} message="No arsenal items match this view." />
            ) : (
              items.map((it) => (
                <ArsenalRow
                  key={it.slug}
                  item={it}
                  onOpen={() => navigate(`/arsenal/${encodeURIComponent(it.slug)}`)}
                  onSetTrust={(trust) => setTrust.mutate({ slug: it.slug, trust })}
                />
              ))
            )}
          </div>
        </TabsContent>
      </Tabs>

      <AddArsenalDialog open={addOpen} onOpenChange={setAddOpen} />
    </div>
  );
}

function ArsenalRow({
  item,
  onOpen,
  onSetTrust,
}: {
  item: ArsenalItem;
  onOpen: () => void;
  onSetTrust: (trust: string) => void;
}) {
  const { pushToast } = useToast();
  const tags = parseTags(item.tags);
  const refs = parseSourceRefs(item.source_refs ?? null);
  const firstUrl = refs.find((r) => r.startsWith("http"));

  return (
    <div
      className="flex items-center gap-3 px-4 py-2 text-sm border-b border-border last:border-b-0 hover:bg-accent/50 cursor-pointer transition-colors"
      onClick={onOpen}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs text-muted-foreground font-mono shrink-0 relative top-[1px] truncate max-w-[12rem]">
            {item.slug}
          </span>
          <span className="truncate">{item.title}</span>
        </div>
        <div className="mt-0.5 flex items-center gap-2 flex-wrap text-xs text-muted-foreground">
          {item.produced_by && (
            <span className="font-mono truncate max-w-[10rem]">{item.produced_by}</span>
          )}
          {item.produced_at && <span>· {timeAgo(item.produced_at)}</span>}
          {tags.slice(0, 4).map((t) => (
            <span
              key={t}
              className="inline-flex items-center rounded bg-muted/60 px-1.5 py-0.5 text-[10px] text-muted-foreground"
            >
              {t}
            </span>
          ))}
          {tags.length > 4 && <span className="text-[10px]">+{tags.length - 4}</span>}
        </div>
      </div>
      <TrustBadge trust={item.trust} />
      <DropdownMenu>
        <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
          <Button
            variant="ghost"
            size="icon-xs"
            aria-label="More"
            onClick={(e) => e.stopPropagation()}
          >
            <MoreHorizontal className="h-3.5 w-3.5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
          <DropdownMenuItem
            onSelect={(e) => {
              e.preventDefault();
              onSetTrust("human_verified");
            }}
          >
            <ShieldCheck className="h-4 w-4" />
            Mark human-verified
          </DropdownMenuItem>
          <DropdownMenuItem
            variant="destructive"
            onSelect={(e) => {
              e.preventDefault();
              onSetTrust("retracted");
            }}
          >
            <XCircle className="h-4 w-4" />
            Retract
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onSelect={(e) => {
              e.preventDefault();
              navigator.clipboard.writeText(item.slug).then(() => {
                pushToast("Slug copied", "success");
              });
            }}
          >
            <Copy className="h-4 w-4" />
            Copy slug
          </DropdownMenuItem>
          {firstUrl && (
            <DropdownMenuItem
              onSelect={(e) => {
                e.preventDefault();
                window.open(firstUrl, "_blank", "noopener");
              }}
            >
              <ExternalLink className="h-4 w-4" />
              Open source URL
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

function AddArsenalDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const qc = useQueryClient();
  const { pushToast } = useToast();
  const [slug, setSlug] = useState("");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [tags, setTags] = useState("");
  const [sourceType, setSourceType] = useState("");
  const [sourceRefs, setSourceRefs] = useState("");

  useEffect(() => {
    if (!open) {
      setSlug("");
      setTitle("");
      setContent("");
      setTags("");
      setSourceType("");
      setSourceRefs("");
    }
  }, [open]);

  const add = useMutation({
    mutationFn: () =>
      arsenalApi.add({
        slug: slug.trim() || undefined,
        title: title.trim(),
        content,
        tags: tags
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        source_type: sourceType.trim(),
        source_refs: sourceRefs
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.arsenal.all });
      pushToast("Arsenal item added", "success");
      onOpenChange(false);
    },
    onError: (err: unknown) => {
      const msg = err instanceof ApiError ? err.message : "Failed to add item";
      pushToast(msg, "error");
    },
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!title.trim() || !content.trim()) return;
    add.mutate();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={onSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Add arsenal item</DialogTitle>
            <DialogDescription>
              Contribute a finding, fact, or snippet to the shared knowledge base.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="arsenal-title">Title</Label>
              <Input
                id="arsenal-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="arsenal-slug">Slug (optional)</Label>
              <Input
                id="arsenal-slug"
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                placeholder="auto-generated if empty"
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="arsenal-content">Content (markdown)</Label>
              <Textarea
                id="arsenal-content"
                value={content}
                onChange={(e) => setContent(e.target.value)}
                rows={8}
                required
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="arsenal-tags">Tags (comma-separated)</Label>
              <Input
                id="arsenal-tags"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                placeholder="e.g. security, performance"
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="arsenal-source-type">Source type</Label>
              <Input
                id="arsenal-source-type"
                value={sourceType}
                onChange={(e) => setSourceType(e.target.value)}
                placeholder="e.g. docs, research, incident"
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="arsenal-source-refs">Source refs (comma-separated)</Label>
              <Input
                id="arsenal-source-refs"
                value={sourceRefs}
                onChange={(e) => setSourceRefs(e.target.value)}
                placeholder="e.g. https://..., arsenal:other-slug"
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
              disabled={add.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={add.isPending || !title.trim() || !content.trim()}
            >
              {add.isPending ? "Saving…" : "Add item"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function ArsenalDetailPage() {
  const { slug = "" } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { pushToast } = useToast();

  const { setBreadcrumbs } = useBreadcrumbs();
  useEffect(() => {
    setBreadcrumbs([
      { label: "Arsenal", href: "/arsenal" },
      { label: slug },
    ]);
  }, [slug, setBreadcrumbs]);

  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys.arsenal.detail(slug),
    queryFn: () => arsenalApi.get(slug),
    enabled: !!slug,
    refetchInterval: 15_000,
  });

  const setTrust = useMutation({
    mutationFn: (trust: string) => arsenalApi.setTrust(slug, trust),
    onSuccess: (_res, trust) => {
      qc.invalidateQueries({ queryKey: queryKeys.arsenal.all });
      qc.invalidateQueries({ queryKey: queryKeys.arsenal.detail(slug) });
      pushToast(`Trust → ${trust.replace(/_/g, " ")}`, "success");
    },
    onError: (err: unknown) => {
      const msg = err instanceof ApiError ? err.message : "Failed to update trust";
      pushToast(msg, "error");
    },
  });

  if (isLoading && !data) return <PageSkeleton variant="detail" />;
  if (error || !data) {
    return (
      <div className="border border-border rounded-lg">
        <EmptyState
          icon={Library}
          message={`Arsenal item not found: ${slug}`}
          action="Back to arsenal"
          onAction={() => navigate("/arsenal")}
        />
      </div>
    );
  }

  const tagsList = Array.isArray(data.tags)
    ? data.tags
    : parseTags(typeof data.tags === "string" ? data.tags : null);
  const refsList = Array.isArray(data.source_refs)
    ? data.source_refs
    : parseSourceRefs(typeof data.source_refs === "string" ? data.source_refs : null);
  const derivedList = Array.isArray(data.derived_from)
    ? data.derived_from
    : typeof data.derived_from === "string"
      ? parseSourceRefs(data.derived_from)
      : [];

  const trustHint = (() => {
    switch (data.trust) {
      case "human_verified": return "You marked this verified. Agents cite it with high confidence.";
      case "retracted":      return "Retracted. Agents will skip this item.";
      case "peer_verified":  return "A critic agent cross-checked this. Promote to verified if you agree.";
      case "agent_summary":  return "Raw agent output — not yet reviewed. Verify or retract to close the loop.";
      case "hypothesis":     return "An unproven claim. Needs evidence before being trusted.";
      default: return null;
    }
  })();

  return (
    <div className="space-y-2">
      <BackLink to="/arsenal" label="Arsenal" />
    <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
      <div className="space-y-4 min-w-0">
        <section className="rounded-lg border border-border bg-card/60 p-4 md:p-5 space-y-3">
          <div className="flex items-center gap-2 text-xs text-muted-foreground font-mono">
            <Library className="h-3 w-3" />
            <span className="truncate">{data.slug}</span>
            {data.machine && (
              <span className="ml-auto text-[11px] px-1.5 py-0.5 rounded bg-muted/60 text-muted-foreground">
                on {data.machine}
              </span>
            )}
          </div>
          <div className="flex items-start gap-3 flex-wrap">
            <h2 className="text-lg font-semibold flex-1 min-w-0 break-words">{data.title}</h2>
            <TrustBadge trust={data.trust} />
          </div>
          {trustHint && (
            <p className="text-xs text-muted-foreground">{trustHint}</p>
          )}
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              onClick={() => setTrust.mutate("human_verified")}
              disabled={setTrust.isPending || data.trust === "human_verified"}
            >
              <ShieldCheck className="h-4 w-4" />
              {data.trust === "human_verified" ? "Verified ✓" : "Mark verified"}
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => setTrust.mutate("retracted")}
              disabled={setTrust.isPending || data.trust === "retracted"}
            >
              <XCircle className="h-4 w-4" />
              {data.trust === "retracted" ? "Retracted" : "Retract"}
            </Button>
            {setTrust.isPending && (
              <span className="text-xs text-muted-foreground">Updating…</span>
            )}
          </div>
        </section>

        <section className="space-y-2">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            Content
          </h3>
          <pre className="rounded-lg border border-border bg-card/60 p-4 text-sm font-mono whitespace-pre-wrap break-words max-h-[640px] overflow-auto">
            {data.content ?? ""}
          </pre>
        </section>
      </div>

      <aside className="space-y-4">
        <section className="rounded-lg border border-border bg-card/60 p-4 space-y-3 text-sm">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Metadata
          </h3>
          <MetaRow label="Slug" value={<span className="font-mono">{data.slug}</span>} />
          <MetaRow label="Trust" value={<TrustBadge trust={data.trust} />} />
          {data.source_type && <MetaRow label="Source type" value={data.source_type} />}
          {data.produced_by && (
            <MetaRow label="Produced by" value={<span className="font-mono">{data.produced_by}</span>} />
          )}
          {data.produced_at && (
            <MetaRow label="Produced" value={timeAgo(data.produced_at)} />
          )}
          {data.verification_status && (
            <MetaRow label="Verification" value={data.verification_status} />
          )}
          {typeof data.chain_depth === "number" && (
            <MetaRow label="Chain depth" value={String(data.chain_depth)} />
          )}
        </section>

        {tagsList.length > 0 && (
          <section className="rounded-lg border border-border bg-card/60 p-4 space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Tags
            </h3>
            <div className="flex flex-wrap gap-1">
              {tagsList.map((t) => (
                <span
                  key={t}
                  className="inline-flex items-center rounded bg-muted/60 px-1.5 py-0.5 text-[11px] text-muted-foreground"
                >
                  {t}
                </span>
              ))}
            </div>
          </section>
        )}

        {refsList.length > 0 && (
          <section className="rounded-lg border border-border bg-card/60 p-4 space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Source refs
            </h3>
            <ul className="space-y-1 text-xs">
              {refsList.map((r, i) => {
                const isUrl = r.startsWith("http");
                return (
                  <li key={`${r}-${i}`}>
                    {isUrl ? (
                      <a
                        href={r}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary hover:underline break-all inline-flex items-center gap-1"
                      >
                        <ExternalLink className="h-3 w-3" />
                        {r}
                      </a>
                    ) : (
                      <span className="font-mono break-all">{r}</span>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        {derivedList.length > 0 && (
          <section className="rounded-lg border border-border bg-card/60 p-4 space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Derived from
            </h3>
            <ul className="space-y-1 text-xs">
              {derivedList.map((r, i) => (
                <li key={`${r}-${i}`}>
                  <button
                    onClick={() => navigate(`/arsenal/${encodeURIComponent(r)}`)}
                    className="text-primary hover:underline font-mono break-all"
                  >
                    {r}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}
      </aside>
    </div>
    </div>
  );
}

function MetaRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-foreground text-right truncate">{value}</span>
    </div>
  );
}
