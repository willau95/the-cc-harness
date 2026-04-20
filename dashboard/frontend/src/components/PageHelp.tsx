import { useEffect, useState, type ReactNode } from "react";
import { Info, X } from "lucide-react";

/**
 * Top-of-page "what is this" explainer. Collapses to a single line with a
 * caret; expands to show bullets the first time a user visits this page.
 * Once dismissed it stays collapsed — remembered in localStorage per key.
 */
export function PageHelp({
  storageKey,
  title,
  summary,
  bullets,
}: {
  storageKey: string;
  title: string;
  summary: string;
  bullets?: ReactNode[];
}) {
  const key = `help-dismissed:${storageKey}`;
  const [expanded, setExpanded] = useState<boolean>(() => {
    try { return localStorage.getItem(key) !== "1"; } catch { return true; }
  });
  useEffect(() => {
    try { localStorage.setItem(key, expanded ? "0" : "1"); } catch { /* ignore */ }
  }, [expanded, key]);

  return (
    <div className="rounded-lg border border-border/60 bg-muted/20 px-4 py-3 mb-4">
      <button
        onClick={() => setExpanded(v => !v)}
        className="flex items-start gap-2 text-left w-full"
        aria-expanded={expanded}
      >
        <Info className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-foreground">{title}</span>
            <span className="text-xs text-muted-foreground">· {summary}</span>
          </div>
          {expanded && bullets && bullets.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
              {bullets.map((b, i) => (
                <li key={i} className="pl-3 relative before:content-['›'] before:absolute before:left-0 before:text-primary/60">
                  {b}
                </li>
              ))}
            </ul>
          )}
        </div>
        {expanded && (
          <span className="text-muted-foreground hover:text-foreground shrink-0">
            <X className="h-3.5 w-3.5" />
          </span>
        )}
      </button>
    </div>
  );
}
