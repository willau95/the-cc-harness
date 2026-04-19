import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

interface DialogContextValue {
  spawnOpen: boolean;
  openSpawn: () => void;
  closeSpawn: () => void;
  commandPaletteOpen: boolean;
  setCommandPaletteOpen: (open: boolean) => void;
  toggleCommandPalette: () => void;
}

const DialogContext = createContext<DialogContextValue | null>(null);

export function DialogProvider({ children }: { children: ReactNode }) {
  const [spawnOpen, setSpawnOpen] = useState(false);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);

  const openSpawn = useCallback(() => setSpawnOpen(true), []);
  const closeSpawn = useCallback(() => setSpawnOpen(false), []);
  const toggleCommandPalette = useCallback(() => setCommandPaletteOpen((v) => !v), []);

  const value = useMemo(
    () => ({
      spawnOpen,
      openSpawn,
      closeSpawn,
      commandPaletteOpen,
      setCommandPaletteOpen,
      toggleCommandPalette,
    }),
    [spawnOpen, openSpawn, closeSpawn, commandPaletteOpen, toggleCommandPalette],
  );

  return <DialogContext.Provider value={value}>{children}</DialogContext.Provider>;
}

export function useDialogs() {
  const ctx = useContext(DialogContext);
  if (!ctx) throw new Error("useDialogs must be used within DialogProvider");
  return ctx;
}
