import { useCallback, useEffect, useState } from "react";
import {
  clearHistory,
  type HistoryEntry,
  loadHistory,
  removeEntry,
  renameEntry,
  saveEntry,
  STORAGE_KEY,
} from "../lib/history";

export interface UseHistoryResult {
  entries: HistoryEntry[];
  save: (entry: HistoryEntry) => void;
  remove: (id: string) => void;
  rename: (id: string, label: string) => void;
  clear: () => void;
}

export function useHistory(): UseHistoryResult {
  const [entries, setEntries] = useState<HistoryEntry[]>(() => loadHistory());

  useEffect(() => {
    // `storage` does NOT fire in the tab that made the change, only in other
    // tabs/windows sharing the origin -- exactly the cross-tab sync this is for.
    // The writing tab updates its own state directly in the callbacks below.
    function handleStorage(event: StorageEvent) {
      if (event.key === STORAGE_KEY || event.key === null) {
        setEntries(loadHistory());
      }
    }
    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, []);

  const save = useCallback((entry: HistoryEntry) => {
    setEntries((current) => saveEntry(current, entry));
  }, []);

  const remove = useCallback((id: string) => {
    setEntries((current) => removeEntry(current, id));
  }, []);

  const rename = useCallback((id: string, label: string) => {
    setEntries((current) => renameEntry(current, id, label));
  }, []);

  const clear = useCallback(() => {
    setEntries(clearHistory());
  }, []);

  return { entries, save, remove, rename, clear };
}
