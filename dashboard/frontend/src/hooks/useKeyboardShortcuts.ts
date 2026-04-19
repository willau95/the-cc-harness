import { useEffect } from "react";
import { useDialogs } from "@/context/DialogContext";
import { useSidebar } from "@/context/SidebarContext";

function isEditable(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  if (el.isContentEditable) return true;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
}

/** Wires up global shortcuts: Cmd/Ctrl+K → palette, Cmd/Ctrl+B → sidebar. */
export function useKeyboardShortcuts() {
  const { toggleCommandPalette } = useDialogs();
  const { toggleSidebar } = useSidebar();

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === "k") {
        e.preventDefault();
        toggleCommandPalette();
        return;
      }
      if (mod && e.key.toLowerCase() === "b") {
        e.preventDefault();
        toggleSidebar();
        return;
      }
      if (e.key === "?" && !isEditable(e.target) && !mod) {
        // Reserved — could open a cheatsheet. No-op for v1.
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleCommandPalette, toggleSidebar]);
}
