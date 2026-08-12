import type { ImportEntryPayload } from "./api";
import type { HistoryEntry } from "./history";

/**
 * The one-time import of `localStorage` history into a newly-signed-in account.
 * See enhancements/23. Pure functions only, no React and no network -- the
 * component (`MigrationPrompt.tsx`) owns the actual `POST /me/history/import`
 * call and the flag write.
 *
 * The flag lives in `localStorage`, separate from `history.ts`'s own storage key
 * so clearing local history never resets it (a cleared history must not make the
 * banner reappear and re-offer an import of nothing).
 */
export const MIGRATION_FLAG_KEY = "talentrank.history.migrated.v1";

/** `null` on any failure, same defensive shape as `history.ts`/`auth.ts`'s own
 * storage reads -- Safari private mode has historically thrown on `localStorage`
 * access outright, not just on writes over quota. */
export function readMigrationFlag(): string | null {
  try {
    return localStorage.getItem(MIGRATION_FLAG_KEY);
  } catch {
    return null;
  }
}

/** Best-effort: a failed write just means the prompt may reappear next session,
 * never silent data loss (there is nothing destructive gated on this flag alone
 * -- see `shouldOfferMigration`'s own risk note in enhancements/23). */
export function writeMigrationFlag(): void {
  try {
    localStorage.setItem(MIGRATION_FLAG_KEY, "1");
  } catch {
    // ignore
  }
}

/**
 * Decides whether `MigrationPrompt` should render. Never true when there is
 * nothing to import -- an empty local history offering to import zero entries
 * is not a real choice for the user to make.
 */
export function shouldOfferMigration(entries: HistoryEntry[], flag: string | null): boolean {
  return entries.length > 0 && flag === null;
}

/**
 * Adapts `HistoryEntry[]` (camelCase, local-storage shape) into the server's
 * `ImportEntry` shape (snake_case) -- mirrors how `MatchOptions`/`MatchRequestBody`
 * already convert `topK` -> `top_k` for `/match`. Deliberately does not include a
 * `resume_hash`: the server recomputes it itself (`resume_digest`) rather than
 * trusting a client-supplied value, exactly like every other digest in this
 * codebase.
 */
export function toImportPayload(entries: HistoryEntry[]): ImportEntryPayload[] {
  return entries.map((entry) => ({
    created_at: entry.createdAt,
    label: entry.label,
    resume_text: entry.resumeText,
    top_k: entry.topK,
    top_n: entry.topN,
    filters: entry.filters,
    results: entry.results,
  }));
}
