import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, ListChecks } from "lucide-react";
import { Link, useNavigate, useParams } from "@/lib/router";
import { tasksApi } from "@/api/tasks";
import { fleetApi } from "@/api/fleet";
import type { TaskItem } from "@/api/types";
import { queryKeys } from "@/lib/queryKeys";
import { timeAgo } from "@/lib/timeAgo";
import { cn } from "@/lib/utils";
import { useBreadcrumbs } from "@/context/BreadcrumbContext";
import { PageTabBar } from "@/components/PageTabBar";
import { Tabs, TabsContent } from "@/components/ui/tabs";
import { EmptyState } from "@/components/EmptyState";
import { PageSkeleton } from "@/components/PageSkeleton";
import { StatusBadge } from "@/components/StatusBadge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const ALLOWED_TABS = new Set([
  "all",
  "in_progress",
  "blocked",
  "awaiting_review",
  "proposed",
  "done",
  "abandoned",
]);

const TABS = [
  { value: "all", label: "All" },
  { value: "in_progress", label: "In-progress" },
  { value: "blocked", label: "Blocked" },
  { value: "awaiting_review", label: "Awaiting-review" },
  { value: "proposed", label: "Proposed" },
  { value: "done", label: "Done" },
  { value: "abandoned", label: "Abandoned" },
];

function truncate(text: string | null | undefined, n = 160): string {
  if (!text) return "";
  return text.length > n ? `${text.slice(0, n - 1)}…` : text;
}

function budgetProgress(budget: Record<string, unknown> | null | undefined): {
  used: number;
  total: number;
  pct: number;
} | null {
  if (!budget || typeof budget !== "object") return null;
  const used = Number(budget.used ?? budget.consumed ?? budget.spent ?? NaN);
  const total = Number(budget.total ?? budget.limit ?? budget.max ?? NaN);
  if (!Number.isFinite(used) || !Number.isFinite(total) || total <= 0) return null;
  return { used, total, pct: Math.max(0, Math.min(100, (used / total) * 100)) };
}

export function TasksPage() {
  const { tab: raw } = useParams<{ tab?: string }>();
  const tab = raw && ALLOWED_TABS.has(raw) ? raw : "all";
  const navigate = useNavigate();

  const [agentFilter, setAgentFilter] = useState<string>("all");
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const { setBreadcrumbs } = useBreadcrumbs();
  useEffect(() => {
    const label = tab === "all" ? "Tasks" : `Tasks · ${tab.replace(/_/g, " ")}`;
    setBreadcrumbs([{ label }]);
  }, [tab, setBreadcrumbs]);

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.tasks.all,
    queryFn: () => tasksApi.list(),
    refetchInterval: 10_000,
  });

  const { data: fleet } = useQuery({
    queryKey: queryKeys.fleet,
    queryFn: () => fleetApi.list(),
    staleTime: 5_000,
  });

  const filtered = useMemo(() => {
    let tasks = data?.tasks ?? [];
    if (tab !== "all") tasks = tasks.filter((t) => t.state === tab);
    if (agentFilter !== "all") tasks = tasks.filter((t) => t.agent_id === agentFilter);
    return tasks;
  }, [data, tab, agentFilter]);

  const grouped = useMemo(() => {
    const map = new Map<string, TaskItem[]>();
    for (const t of filtered) {
      const key = t.project || "(unassigned)";
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(t);
    }
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [filtered]);

  if (isLoading && !data) return <PageSkeleton />;

  const onChangeTab = (v: string) => {
    if (v === "all") navigate("/tasks");
    else navigate(`/tasks/${v}`);
  };

  return (
    <div className="space-y-4">
      <Tabs value={tab} onValueChange={onChangeTab}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <PageTabBar items={TABS} value={tab} onValueChange={onChangeTab} />
          <div className="flex items-center gap-2">
            <Select value={agentFilter} onValueChange={setAgentFilter}>
              <SelectTrigger size="sm">
                <SelectValue placeholder="All agents" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All agents</SelectItem>
                {(fleet?.agents ?? []).map((a) => (
                  <SelectItem key={a.agent_id} value={a.agent_id}>
                    {a.name ?? a.agent_id}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span className="text-xs text-muted-foreground tabular-nums">
              {filtered.length} task{filtered.length === 1 ? "" : "s"}
            </span>
          </div>
        </div>

        <TabsContent value={tab} className="mt-3 space-y-4">
          {grouped.length === 0 ? (
            <div className="border border-border rounded-lg">
              <EmptyState icon={ListChecks} message="No tasks match this filter." />
            </div>
          ) : (
            grouped.map(([project, tasks]) => {
              const isCollapsed = !!collapsed[project];
              return (
                <section key={project} className="space-y-2">
                  <button
                    type="button"
                    onClick={() =>
                      setCollapsed((prev) => ({ ...prev, [project]: !prev[project] }))
                    }
                    className="w-full flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground"
                  >
                    {isCollapsed ? (
                      <ChevronRight className="h-4 w-4" />
                    ) : (
                      <ChevronDown className="h-4 w-4" />
                    )}
                    <span>{project}</span>
                    <span className="ml-auto text-xs tabular-nums normal-case font-medium tracking-normal">
                      {tasks.length}
                    </span>
                  </button>
                  {!isCollapsed && (
                    <div className="border border-border rounded-lg overflow-hidden">
                      {tasks.map((t) => (
                        <TaskRow key={t.task_id} task={t} />
                      ))}
                    </div>
                  )}
                </section>
              );
            })
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

function TaskRow({ task }: { task: TaskItem }) {
  const progress = budgetProgress(task.task_budget);
  const href = task.agent_id
    ? `/agents/${encodeURIComponent(task.agent_id)}#task-${encodeURIComponent(task.task_id)}`
    : null;

  const content = (
    <div className="flex items-center gap-3 px-4 py-2 text-sm border-b border-border last:border-b-0 hover:bg-accent/50 transition-colors">
      <StatusBadge status={task.state} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs text-muted-foreground font-mono shrink-0 truncate max-w-[10rem]">
            {task.task_id}
          </span>
          <span className="truncate">{truncate(task.original_goal, 140) || "—"}</span>
        </div>
        <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
          {task.agent_id && (
            <span className="inline-flex items-center rounded bg-muted/60 px-1.5 py-0.5 font-mono text-[10px]">
              {task.agent_id}
            </span>
          )}
          {task.role && <span>· {task.role}</span>}
          {task.ts && <span>· {timeAgo(task.ts)}</span>}
          {task.blocked_on && (
            <span className="text-red-600 dark:text-red-400 truncate">
              · blocked: {truncate(task.blocked_on, 60)}
            </span>
          )}
        </div>
      </div>
      {progress && (
        <div className="hidden md:flex flex-col items-end gap-1 shrink-0 w-28">
          <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
            <div
              className={cn(
                "h-full rounded-full",
                progress.pct >= 90 ? "bg-red-500" : progress.pct >= 70 ? "bg-yellow-500" : "bg-primary",
              )}
              style={{ width: `${progress.pct}%` }}
            />
          </div>
          <span className="text-[10px] text-muted-foreground tabular-nums">
            {progress.used.toLocaleString()} / {progress.total.toLocaleString()}
          </span>
        </div>
      )}
    </div>
  );

  if (href) {
    return (
      <Link to={href} className="block no-underline text-inherit">
        {content}
      </Link>
    );
  }
  return content;
}
