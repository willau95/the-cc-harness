import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity } from "lucide-react";
import { eventsApi } from "@/api/events";
import { fleetApi } from "@/api/fleet";
import { queryKeys } from "@/lib/queryKeys";
import { useBreadcrumbs } from "@/context/BreadcrumbContext";
import { EventRow } from "@/components/EventRow";
import { EmptyState } from "@/components/EmptyState";
import { PageSkeleton } from "@/components/PageSkeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";

const PAGE_SIZE = 50;

export function EventsPage() {
  const { setBreadcrumbs } = useBreadcrumbs();
  useEffect(() => setBreadcrumbs([{ label: "Events" }]), [setBreadcrumbs]);

  const [agentFilter, setAgentFilter] = useState<string>("all");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.events(500),
    queryFn: () => eventsApi.list(500),
    refetchInterval: 10_000,
  });

  const { data: fleet } = useQuery({
    queryKey: queryKeys.fleet,
    queryFn: () => fleetApi.list(),
    staleTime: 5_000,
  });

  const filtered = useMemo(() => {
    let events = data?.events ?? [];
    if (agentFilter !== "all") {
      events = events.filter((e) => e.agent === agentFilter);
    }
    if (query.trim()) {
      const q = query.toLowerCase();
      events = events.filter((e) =>
        [e.agent, e.type, JSON.stringify(e)].some((v) => typeof v === "string" && v.toLowerCase().includes(q)),
      );
    }
    return events;
  }, [data, agentFilter, query]);

  const pageEvents = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));

  if (isLoading && !data) return <PageSkeleton />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          value={query}
          onChange={(e) => {
            setPage(0);
            setQuery(e.target.value);
          }}
          placeholder="Filter events…"
          className="max-w-sm"
        />
        <Select
          value={agentFilter}
          onValueChange={(v) => {
            setPage(0);
            setAgentFilter(v);
          }}
        >
          <SelectTrigger>
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
        <span className="ml-auto text-xs text-muted-foreground tabular-nums">
          {filtered.length} event{filtered.length === 1 ? "" : "s"}
        </span>
      </div>

      <div className="border border-border rounded-lg overflow-hidden">
        {pageEvents.length === 0 ? (
          <EmptyState icon={Activity} message="No events match this filter." />
        ) : (
          pageEvents.map((event, i) => (
            <EventRow key={`${event.agent}-${event.ts}-${i}`} event={event} />
          ))
        )}
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-end gap-2 text-xs text-muted-foreground">
          <button
            className="h-8 px-3 border border-border rounded-md hover:bg-accent/50 disabled:opacity-50"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
          >
            Previous
          </button>
          <span className="tabular-nums">
            {page + 1} / {totalPages}
          </span>
          <button
            className="h-8 px-3 border border-border rounded-md hover:bg-accent/50 disabled:opacity-50"
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
