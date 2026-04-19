import { Pause, Play, Skull, X } from "lucide-react";
import { Button } from "@/components/ui/button";

interface FleetControlBarProps {
  count: number;
  onPause: () => void;
  onResume: () => void;
  onKill: () => void;
  onClear: () => void;
  busy?: boolean;
}

export function FleetControlBar({ count, onPause, onResume, onKill, onClear, busy }: FleetControlBarProps) {
  if (count === 0) return null;
  return (
    <div className="sticky top-0 z-20 -mx-4 md:-mx-6 px-4 md:px-6 py-2 bg-background/95 backdrop-blur border-b border-border flex flex-wrap items-center gap-2">
      <span className="text-sm font-medium">
        <span className="tabular-nums">{count}</span> selected
      </span>
      <div className="ml-auto flex items-center gap-2">
        <Button variant="outline" size="sm" onClick={onPause} disabled={busy}>
          <Pause className="h-3.5 w-3.5" />
          Pause
        </Button>
        <Button variant="outline" size="sm" onClick={onResume} disabled={busy}>
          <Play className="h-3.5 w-3.5" />
          Resume
        </Button>
        <Button variant="destructive" size="sm" onClick={onKill} disabled={busy}>
          <Skull className="h-3.5 w-3.5" />
          Kill
        </Button>
        <Button variant="ghost" size="sm" onClick={onClear} disabled={busy}>
          <X className="h-3.5 w-3.5" />
          Clear
        </Button>
      </div>
    </div>
  );
}
