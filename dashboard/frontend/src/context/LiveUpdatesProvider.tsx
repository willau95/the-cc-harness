import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/lib/queryKeys";

interface LiveUpdatesContextValue {
  connected: boolean;
  lastEventAt: number | null;
}

const LiveUpdatesContext = createContext<LiveUpdatesContextValue>({ connected: false, lastEventAt: null });

interface FileChange {
  change: string;
  path: string;
}

interface BatchMessage {
  type: "batch";
  changes: FileChange[];
}

function wsUrl(): string {
  if (typeof window === "undefined") return "";
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  // In dev the vite proxy forwards /ws to the FastAPI backend; in prod the
  // backend serves the frontend so same-origin always works.
  return `${proto}//${window.location.host}/ws/stream`;
}

export function LiveUpdatesProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [connected, setConnected] = useState(false);
  const [lastEventAt, setLastEventAt] = useState<number | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const attemptsRef = useRef(0);
  const reconnectTimerRef = useRef<number | null>(null);
  const stoppedRef = useRef(false);

  useEffect(() => {
    stoppedRef.current = false;

    function connect() {
      if (stoppedRef.current) return;
      let ws: WebSocket;
      try {
        ws = new WebSocket(wsUrl());
      } catch {
        scheduleReconnect();
        return;
      }
      wsRef.current = ws;

      ws.onopen = () => {
        attemptsRef.current = 0;
        setConnected(true);
      };

      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;
        scheduleReconnect();
      };

      ws.onerror = () => {
        // onclose will fire next — just swallow.
      };

      ws.onmessage = (ev) => {
        setLastEventAt(Date.now());
        try {
          const payload: BatchMessage = JSON.parse(ev.data);
          if (payload.type !== "batch" || !Array.isArray(payload.changes)) return;
          handleBatch(payload.changes);
        } catch {
          // ignore malformed messages
        }
      };
    }

    function scheduleReconnect() {
      if (stoppedRef.current) return;
      attemptsRef.current += 1;
      const delay = Math.min(15_000, 1_000 * Math.pow(2, Math.min(attemptsRef.current, 4)));
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current);
      }
      reconnectTimerRef.current = window.setTimeout(connect, delay);
    }

    function handleBatch(changes: FileChange[]) {
      // Deduplicate invalidation targets for a single batch.
      const invalidations = new Set<string>();

      for (const c of changes) {
        const rel = extractRelPath(c.path);
        if (!rel) continue;
        if (rel.startsWith("registry/")) {
          invalidations.add("fleet");
          invalidations.add("stats");
          invalidations.add("agents:all");
        } else if (rel.startsWith("heartbeats/")) {
          invalidations.add("fleet");
          invalidations.add("stats");
          const aid = extractAgentId(rel);
          if (aid) invalidations.add(`agent:${aid}`);
        } else if (rel.startsWith("events/")) {
          invalidations.add("events");
          const aid = extractAgentId(rel);
          if (aid) invalidations.add(`agent:${aid}`);
        } else if (rel.startsWith("mailbox/")) {
          const aid = extractAgentId(rel);
          if (aid) invalidations.add(`agent:${aid}`);
        } else if (rel.startsWith("proposals/")) {
          invalidations.add("proposals");
          invalidations.add("stats");
        } else if (rel.startsWith("projects/")) {
          invalidations.add("projects");
          invalidations.add("stats");
        }
      }

      for (const key of invalidations) {
        if (key === "fleet") qc.invalidateQueries({ queryKey: queryKeys.fleet });
        else if (key === "stats") qc.invalidateQueries({ queryKey: queryKeys.stats });
        else if (key === "agents:all") qc.invalidateQueries({ queryKey: queryKeys.agents.all });
        else if (key === "events") qc.invalidateQueries({ queryKey: queryKeys.eventsAll });
        else if (key === "proposals") qc.invalidateQueries({ queryKey: queryKeys.proposalsAll });
        else if (key === "projects") qc.invalidateQueries({ queryKey: queryKeys.projects.all });
        else if (key.startsWith("agent:")) {
          const aid = key.slice("agent:".length);
          qc.invalidateQueries({ queryKey: queryKeys.agents.detail(aid) });
        }
      }
    }

    // StrictMode-safe: connect after a short delay to avoid double-connects in dev
    const timer = window.setTimeout(connect, 80);

    return () => {
      stoppedRef.current = true;
      window.clearTimeout(timer);
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current);
      }
      if (wsRef.current) {
        wsRef.current.onclose = null;
        try {
          wsRef.current.close();
        } catch {
          // ignore
        }
        wsRef.current = null;
      }
      setConnected(false);
    };
  }, [qc]);

  const value = useMemo(() => ({ connected, lastEventAt }), [connected, lastEventAt]);

  return <LiveUpdatesContext.Provider value={value}>{children}</LiveUpdatesContext.Provider>;
}

/** Pull the relative path under ~/.harness/ out of an absolute path. */
function extractRelPath(absPath: string): string | null {
  if (!absPath) return null;
  const marker = "/.harness/";
  const i = absPath.indexOf(marker);
  if (i < 0) {
    // fallback: maybe the backend sends relative paths already
    return absPath.replace(/^\/+/, "");
  }
  return absPath.slice(i + marker.length);
}

/** Pull the agent_id out of a path like "events/<agent_id>/2025-04-20.jsonl". */
function extractAgentId(rel: string): string | null {
  const parts = rel.split("/");
  if (parts.length >= 2 && parts[1]) return parts[1];
  return null;
}

export function useLiveUpdates() {
  return useContext(LiveUpdatesContext);
}
