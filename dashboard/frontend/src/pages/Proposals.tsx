import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckSquare } from "lucide-react";
import { useNavigate, useParams } from "@/lib/router";
import { proposalsApi } from "@/api/proposals";
import { queryKeys } from "@/lib/queryKeys";
import { useBreadcrumbs } from "@/context/BreadcrumbContext";
import { Tabs, TabsContent } from "@/components/ui/tabs";
import { PageTabBar } from "@/components/PageTabBar";
import { EmptyState } from "@/components/EmptyState";
import { PageSkeleton } from "@/components/PageSkeleton";
import { ProposalCard } from "@/components/ProposalCard";
import { PageHelp } from "@/components/PageHelp";

const TABS = [
  { value: "pending", label: "Pending" },
  { value: "all", label: "All" },
];

export function ProposalsPage() {
  const { tab: raw } = useParams<{ tab?: string }>();
  const tab = raw === "all" ? "all" : "pending";
  const navigate = useNavigate();

  const { setBreadcrumbs } = useBreadcrumbs();
  useEffect(() => setBreadcrumbs([{ label: "Proposals" }]), [setBreadcrumbs]);

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.proposals(tab === "pending" ? "critic_approved" : undefined),
    queryFn: () =>
      proposalsApi.list(tab === "pending" ? { status: "critic_approved" } : undefined),
    refetchInterval: 15_000,
  });

  const proposals = useMemo(() => data?.proposals ?? [], [data]);

  if (isLoading && !data) return <PageSkeleton variant="approvals" />;

  return (
    <div className="space-y-4">
      <PageHelp
        storageKey="proposals"
        title="Proposals — self-improvement queue (awaiting your approval)"
        summary="Agents suggest changes to themselves or the harness; you're the last checkpoint."
        bullets={[
          <><b>Who creates them:</b> agents write a proposal when they discover a better way to do something (new skill, changed prompt, removed tool)</>,
          <><b>Critic check:</b> another agent reviews first. Only <i>critic_approved</i> proposals appear in "Pending"</>,
          <><b>Your role:</b> approve → the change is applied; reject → it's archived with reason</>,
          <><b>No approval = no change.</b> The fleet cannot mutate itself without your signoff</>,
        ]}
      />
      <Tabs
        value={tab}
        onValueChange={(v) => {
          if (v === "pending") navigate("/proposals");
          else navigate(`/proposals/${v}`);
        }}
      >
        <div className="flex items-center justify-between gap-2">
          <PageTabBar
            items={TABS}
            value={tab}
            onValueChange={(v) => {
              if (v === "pending") navigate("/proposals");
              else navigate(`/proposals/${v}`);
            }}
          />
          <span className="text-xs text-muted-foreground tabular-nums">
            {proposals.length} proposal{proposals.length === 1 ? "" : "s"}
          </span>
        </div>

        <TabsContent value={tab} className="mt-3">
          {proposals.length === 0 ? (
            <div className="border border-border rounded-lg">
              <EmptyState icon={CheckSquare} message="No proposals in this view." />
            </div>
          ) : (
            <div className="grid gap-3">
              {proposals.map((p, i) => (
                <ProposalCard
                  key={(p.pid as string) ?? (p.id as string) ?? `${p.kind}-${i}`}
                  proposal={p}
                />
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
