import { Pause, Play, Skull } from "lucide-react";
import { Button } from "@/components/ui/button";

type Size = "xs" | "sm" | "default";

interface ToggleProps {
  isPaused: boolean;
  onPause: () => void;
  onResume: () => void;
  disabled?: boolean;
  size?: Size;
}

export function PauseResumeButton({ isPaused, onPause, onResume, disabled, size = "sm" }: ToggleProps) {
  if (isPaused) {
    return (
      <Button variant="outline" size={size} onClick={onResume} disabled={disabled}>
        <Play className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">Resume</span>
      </Button>
    );
  }
  return (
    <Button variant="outline" size={size} onClick={onPause} disabled={disabled}>
      <Pause className="h-3.5 w-3.5" />
      <span className="hidden sm:inline">Pause</span>
    </Button>
  );
}

interface KillProps {
  onClick: () => void;
  disabled?: boolean;
  size?: Size;
  label?: string;
}

export function KillButton({ onClick, disabled, size = "sm", label = "Kill" }: KillProps) {
  return (
    <Button variant="destructive" size={size} onClick={onClick} disabled={disabled}>
      <Skull className="h-3.5 w-3.5" />
      <span className="hidden sm:inline">{label}</span>
    </Button>
  );
}
