import { useCallback, useEffect, useState } from "react";
import { useOutletContext } from "react-router";
import type { RootLayoutContext } from "../layouts/RootLayout";
import {
  clearHistory,
  type HistoryEntry,
  loadHistory,
  removeEntry,
  renameEntry,
  saveEntry,
  STORAGE_KEY,
} from "../lib/history";
import * as serverHistory from "../lib/serverHistory";
import type { HistoryDetail } from "../lib/serverHistory";

/** What a caller hands to `save()` -- the id is assigned by whichever backend is
 * active (a fresh UUID locally, or the server's own `match_runs.id` -- see
 * enhancements/23), never by the caller. */
export type NewHistoryEntry = Omit<HistoryEntry, "id">;

export interface UseHistoryResult {
  entries: HistoryEntry[];
  save(entry: NewHistoryEntry): Promise<void>;
  remove(id: string): Promise<void>;
  rename(id: string, label: string): Promise<void>;
  clear(): Promise<void>;
  /** Fetches the full-fidelity entry (real `resumeText`, real `results`) for one
   * id. Local entries already have this; server list entries only carry
   * placeholder results (see `serverHistory.ts`), so this is what
   * `ComparePage`/"View" call before using an entry's `results`. Not in
   * enhancements/23's own five-member sketch, added because the server's
   * `MatchRunSummary` genuinely cannot support those callers without it. */
  getDetail(id: string): Promise<HistoryDetail | null>;
  source: "local" | "server";
  loading: boolean;
}

/**
 * Facade over local (`localStorage`, anonymous) vs server (`/me/history`,
 * signed-in) history. See enhancements/23. `lib/history.ts` stays exactly as it
 * was in `12` -- unmodified, still the anonymous path forever. This hook is the
 * only thing that decides which backend a given render sees, based on
 * `auth.status` from `RootLayoutContext`.
 */
export function useHistory(): UseHistoryResult {
  const { auth } = useOutletContext<RootLayoutContext>();
  const isServer = auth.status === "authenticated";
  const source: "local" | "server" = isServer ? "server" : "local";

  const [entries, setEntries] = useState<HistoryEntry[]>(() => (isServer ? [] : loadHistory()));
  const [loading, setLoading] = useState(isServer);

  useEffect(() => {
    if (!isServer) {
      setEntries(loadHistory());
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    serverHistory
      .fetchEntries()
      .then((fetched) => {
        if (!cancelled) setEntries(fetched);
      })
      .catch(() => {
        // A server outage must not leave History permanently empty and erroring --
        // the local copy is still intact (server mode never deletes it), so show
        // that instead. `source` stays "server": this is a degraded read, not a
        // real switch back to anonymous mode.
        if (!cancelled) setEntries(loadHistory());
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [isServer]);

  useEffect(() => {
    if (isServer) return;
    // `storage` does NOT fire in the tab that made the change, only in other
    // tabs/windows sharing the origin.
    function handleStorage(event: StorageEvent) {
      if (event.key === STORAGE_KEY || event.key === null) {
        setEntries(loadHistory());
      }
    }
    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, [isServer]);

  const save = useCallback(
    async (entry: NewHistoryEntry) => {
      if (isServer) {
        // The row was already written server-side as a side effect of the /match
        // call that produced this entry (enhancements/21's persist_run) -- there is
        // no "create history entry" endpoint to call here. Pick up the fresh list
        // so the new run appears.
        try {
          setEntries(await serverHistory.fetchEntries());
        } catch {
          // best effort -- the run is safely persisted server-side regardless
        }
        return;
      }
      setEntries((current) => saveEntry(current, { ...entry, id: crypto.randomUUID() }));
    },
    [isServer],
  );

  const remove = useCallback(
    async (id: string) => {
      if (isServer) {
        await serverHistory.remove(id);
        setEntries((current) => current.filter((entry) => entry.id !== id));
        return;
      }
      setEntries((current) => removeEntry(current, id));
    },
    [isServer],
  );

  const rename = useCallback(
    async (id: string, label: string) => {
      if (isServer) {
        await serverHistory.rename(id, label);
        setEntries((current) => current.map((entry) => (entry.id === id ? { ...entry, label } : entry)));
        return;
      }
      setEntries((current) => renameEntry(current, id, label));
    },
    [isServer],
  );

  const clear = useCallback(async () => {
    if (isServer) {
      await serverHistory.clear();
      setEntries([]);
      return;
    }
    setEntries(clearHistory());
  }, [isServer]);

  const getDetail = useCallback(
    async (id: string): Promise<HistoryDetail | null> => {
      if (isServer) return serverHistory.fetchDetail(id);
      const found = entries.find((entry) => entry.id === id);
      return found ? { ...found, corpusProfile: null, resumeHash: null } : null;
    },
    [isServer, entries],
  );

  return { entries, save, remove, rename, clear, getDetail, source, loading };
}
