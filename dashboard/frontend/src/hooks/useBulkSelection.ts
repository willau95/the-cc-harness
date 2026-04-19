import { useCallback, useMemo, useState } from "react";

export interface BulkSelection<T> {
  selected: Set<T>;
  isSelected: (id: T) => boolean;
  toggle: (id: T) => void;
  select: (id: T) => void;
  deselect: (id: T) => void;
  selectAll: (ids: T[]) => void;
  clear: () => void;
  count: number;
}

export function useBulkSelection<T>(): BulkSelection<T> {
  const [selected, setSelected] = useState<Set<T>>(() => new Set());

  const toggle = useCallback((id: T) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const select = useCallback((id: T) => {
    setSelected((current) => {
      if (current.has(id)) return current;
      const next = new Set(current);
      next.add(id);
      return next;
    });
  }, []);

  const deselect = useCallback((id: T) => {
    setSelected((current) => {
      if (!current.has(id)) return current;
      const next = new Set(current);
      next.delete(id);
      return next;
    });
  }, []);

  const selectAll = useCallback((ids: T[]) => {
    setSelected(new Set(ids));
  }, []);

  const clear = useCallback(() => setSelected(new Set()), []);

  const isSelected = useCallback((id: T) => selected.has(id), [selected]);

  return useMemo(
    () => ({
      selected,
      isSelected,
      toggle,
      select,
      deselect,
      selectAll,
      clear,
      count: selected.size,
    }),
    [selected, isSelected, toggle, select, deselect, selectAll, clear],
  );
}
