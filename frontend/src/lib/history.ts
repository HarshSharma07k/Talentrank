import type { JobMatch, MatchFilters } from "./api";

/**
 * Match history lives entirely in localStorage -- no server, no auth. See
 * enhancements/12. Exposes plain, directly-testable functions operating on a
 * `HistoryEntry[]`; `useHistory.ts` is the thin React hook wrapper around these.
 */
export interface HistoryEntry {
  id: string;
  createdAt: number;
  label: string; // first ~50 chars of the resume, user-editable
  resumeText: string;
  topK: number;
  topN: number;
  filters: MatchFilters;
  results: JobMatch[]; // descriptions trimmed before storing -- see trimResultsForStorage
}

export const STORAGE_KEY = "talentrank.history.v1";
export const MAX_HISTORY_ENTRIES = 20;

// Full descriptions average 3,766 chars (measured-facts.md); twenty entries x ten
// results each at that size would blow localStorage's ~5 MB per-origin quota on
// its own. Trimming before storage is not optional -- see the doc's risk note.
const DESCRIPTION_STORAGE_MAX_CHARS = 400;
const LABEL_MAX_CHARS = 50;

interface StoredHistory {
  version: 1;
  entries: HistoryEntry[];
}

function trimResultsForStorage(results: JobMatch[]): JobMatch[] {
  return results.map((result) => ({
    ...result,
    description: result.description.slice(0, DESCRIPTION_STORAGE_MAX_CHARS),
  }));
}

export function makeLabel(resumeText: string): string {
  const trimmed = resumeText.trim().replace(/\s+/g, " ");
  return trimmed.length > LABEL_MAX_CHARS ? `${trimmed.slice(0, LABEL_MAX_CHARS).trimEnd()}…` : trimmed;
}

function readRaw(): HistoryEntry[] {
  let raw: string | null;
  try {
    raw = localStorage.getItem(STORAGE_KEY);
  } catch {
    // Safari private mode has historically thrown on localStorage access outright,
    // not just on writes over quota -- covered broadly, not just QuotaExceededError.
    return [];
  }
  if (!raw) return [];

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return [];
  }

  // Versioned (STORAGE_KEY itself carries the .v1 suffix, and the payload repeats
  // it) so a future schema change can be detected and discarded cleanly rather than
  // crashing on parse or serving stale-shaped entries to new code.
  if (
    typeof parsed !== "object" ||
    parsed === null ||
    (parsed as StoredHistory).version !== 1 ||
    !Array.isArray((parsed as StoredHistory).entries)
  ) {
    return [];
  }

  return (parsed as StoredHistory).entries;
}

function writeRaw(entries: HistoryEntry[]): boolean {
  const payload: StoredHistory = { version: 1, entries };
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    return true;
  } catch {
    return false;
  }
}

/**
 * Writes `entries`; on any storage failure (quota exceeded, private-mode
 * restrictions, ...) drops the single oldest entry and retries exactly once, then
 * gives up silently -- a full history is never worth breaking the match flow over.
 */
function persist(entries: HistoryEntry[]): HistoryEntry[] {
  if (writeRaw(entries)) return entries;
  if (entries.length === 0) return entries;

  const droppedOldest = entries.slice(0, entries.length - 1);
  if (writeRaw(droppedOldest)) return droppedOldest;

  return entries;
}

export function loadHistory(): HistoryEntry[] {
  return readRaw();
}

export function saveEntry(existing: HistoryEntry[], entry: HistoryEntry): HistoryEntry[] {
  const trimmedEntry: HistoryEntry = { ...entry, results: trimResultsForStorage(entry.results) };
  const next = [trimmedEntry, ...existing].slice(0, MAX_HISTORY_ENTRIES);
  return persist(next);
}

export function removeEntry(existing: HistoryEntry[], id: string): HistoryEntry[] {
  return persist(existing.filter((entry) => entry.id !== id));
}

export function renameEntry(existing: HistoryEntry[], id: string, label: string): HistoryEntry[] {
  return persist(existing.map((entry) => (entry.id === id ? { ...entry, label } : entry)));
}

export function clearHistory(): HistoryEntry[] {
  return persist([]);
}
