import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, X } from "lucide-react";
import { proposalsApi } from "@/api/proposals";
import { queryKeys } from "@/lib/queryKeys";
import { useToast } from "@/context/ToastContext";
import { ApiError } from "@/api/client";
import type { Proposal } from "@/api/types";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "./StatusBadge";
import { timeAgo } from "@/lib/timeAgo";

function resolvePid(p: Proposal): string {
  return (p.pid as string) || (p.id as string) || "";
}

export function ProposalCard({ proposal }: { proposal: Proposal }) {
  const qc = useQueryClient();
  const { pushToast } = useToast();
  const pid = resolvePid(proposal);
  const kind = proposal.kind;

  const approve = useMutation({
    mutationFn: () => proposalsApi.approve(kind, pid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.proposalsAll });
      qc.invalidateQueries({ queryKey: queryKeys.stats });
      pushToast(`Approved ${kind}/${pid}`, "success");
    },
    onError: (err: unknown) => {
      const msg = err instanceof ApiError ? err.message : "Approve failed";
      pushToast(msg, "error");
    },
  });
  const reject = useMutation({
    mutationFn: () => proposalsApi.reject(kind, pid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.proposalsAll });
      qc.invalidateQueries({ queryKey: queryKeys.stats });
      pushToast(`Rejected ${kind}/${pid}`, "success");
    },
    onError: (err: unknown) => {
      const msg = err instanceof ApiError ? err.message : "Reject failed";
      pushToast(msg, "error");
    },
  });

  const title = proposal.title ?? proposal.summary ?? `${kind} · ${pid}`;
  const busy = approve.isPending || reject.isPending;
  const ts = proposal.ts ?? proposal.created_at ?? null;

  return (
    <div className="rounded-lg border border-border bg-card/60 p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0 space-y-1">
          <div className="flex items-center gap-2 text-xs text-muted-foreground font-mono">
            <span>{kind}</span>
            <span>·</span>
            <span className="truncate">{pid}</span>
            {proposal.agent && (
              <>
                <span>·</span>
                <span className="truncate">{proposal.agent}</span>
              </>
            )}
            {ts && (
              <>
                <span>·</span>
                <span>{timeAgo(ts)}</span>
              </>
            )}
          </div>
          <h3 className="text-sm font-medium leading-snug truncate">{title}</h3>
          {proposal.summary && proposal.summary !== title && (
            <p className="text-xs text-muted-foreground line-clamp-3">{proposal.summary}</p>
          )}
        </div>
        <StatusBadge status={proposal.status ?? "pending"} />
      </div>
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          onClick={() => approve.mutate()}
          disabled={busy || !pid}
        >
          <Check className="h-3.5 w-3.5" />
          Approve
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => reject.mutate()}
          disabled={busy || !pid}
        >
          <X className="h-3.5 w-3.5" />
          Reject
        </Button>
      </div>
    </div>
  );
}
