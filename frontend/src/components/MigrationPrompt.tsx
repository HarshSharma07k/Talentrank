import { useEffect, useState } from "react";
import type { AuthSession } from "../hooks/useAuthSession";
import { type ImportResult, importHistory } from "../lib/api";
import { clearHistory, loadHistory } from "../lib/history";
import { readMigrationFlag, shouldOfferMigration, toImportPayload, writeMigrationFlag } from "../lib/historyMigration";

/**
 * The one-time offer to import `localStorage` history into a newly-signed-in
 * account. See enhancements/23. Wired into `RootLayout` so it appears regardless
 * of route -- a banner, not a modal, matching `12`'s existing shared-link banner
 * style, and it never blocks the app.
 *
 * The four rules that make this safe, each mirrored directly in the code below:
 * never auto-delete local entries: `handleClearLocal` is the only thing that
 * calls `clearHistory()`, and it's a separate, explicit user action, never
 * triggered by a successful import on its own. The flag is written only after a
 * confirmed success response (`writeMigrationFlag()` sits after `await
 * importHistory(...)` resolves, not before). The import itself is idempotent
 * server-side (dedup in `history.import_entries`), so this component does not
 * need to guard against a double-click. And the prompt is dismissible
 * (`handleNotNow`) without touching the flag, so it asks again next session
 * rather than forcing a decision now.
 */
export function MigrationPrompt({ auth }: { auth: AuthSession }) {
  const [visible, setVisible] = useState(false);
  const [entryCount, setEntryCount] = useState(0);
  const [status, setStatus] = useState<"idle" | "importing" | "done" | "error">("idle");
  const [result, setResult] = useState<ImportResult | null>(null);

  useEffect(() => {
    if (auth.status !== "authenticated") {
      setVisible(false);
      setStatus("idle");
      return;
    }
    const entries = loadHistory();
    setEntryCount(entries.length);
    setVisible(shouldOfferMigration(entries, readMigrationFlag()));
  }, [auth.status]);

  async function handleImport() {
    setStatus("importing");
    try {
      const imported = await importHistory(toImportPayload(loadHistory()));
      writeMigrationFlag();
      setResult(imported);
      setStatus("done");
    } catch {
      setStatus("error");
    }
  }

  function handleNotNow() {
    setVisible(false); // flag stays unset -- offered again next session
  }

  function handleNever() {
    writeMigrationFlag();
    setVisible(false);
  }

  function handleClearLocal() {
    clearHistory();
    setVisible(false);
  }

  if (!visible) return null;

  return (
    <div className="mx-auto mt-4 flex w-full max-w-5xl flex-col gap-2 rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm text-indigo-800 sm:flex-row sm:items-center sm:justify-between dark:border-indigo-900/50 dark:bg-indigo-950/30 dark:text-indigo-200">
      {status === "idle" && (
        <>
          <p>
            You have <span className="font-semibold">{entryCount}</span> match{entryCount === 1 ? "" : "es"} saved in
            this browser. Import them into your account?
          </p>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={() => void handleImport()}
              className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500"
            >
              Import
            </button>
            <button
              type="button"
              onClick={handleNotNow}
              className="rounded-lg px-3 py-1.5 text-xs font-medium text-indigo-700 hover:bg-indigo-100 dark:text-indigo-300 dark:hover:bg-indigo-900/40"
            >
              Not now
            </button>
            <button
              type="button"
              onClick={handleNever}
              className="rounded-lg px-3 py-1.5 text-xs font-medium text-indigo-700 hover:bg-indigo-100 dark:text-indigo-300 dark:hover:bg-indigo-900/40"
            >
              Never
            </button>
          </div>
        </>
      )}

      {status === "importing" && <p>Importing…</p>}

      {status === "done" && result && (
        <>
          <p>
            Imported <span className="font-semibold">{result.imported}</span>, skipped{" "}
            <span className="font-semibold">{result.skipped_duplicate}</span> already in your account
            {result.skipped_quota > 0 && (
              <>
                {" "}
                and <span className="font-semibold">{result.skipped_quota}</span> over the history limit
              </>
            )}
            . The local copy in this browser is untouched.
          </p>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={handleClearLocal}
              className="rounded-lg border border-indigo-300 px-3 py-1.5 text-xs font-medium text-indigo-700 hover:bg-indigo-100 dark:border-indigo-700 dark:text-indigo-300 dark:hover:bg-indigo-900/40"
            >
              Clear the local copy
            </button>
            <button
              type="button"
              onClick={() => setVisible(false)}
              className="rounded-lg px-3 py-1.5 text-xs font-medium text-indigo-700 hover:bg-indigo-100 dark:text-indigo-300 dark:hover:bg-indigo-900/40"
            >
              Dismiss
            </button>
          </div>
        </>
      )}

      {status === "error" && (
        <>
          <p>Couldn't import right now -- your local history is untouched.</p>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={() => void handleImport()}
              className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500"
            >
              Try again
            </button>
            <button
              type="button"
              onClick={handleNotNow}
              className="rounded-lg px-3 py-1.5 text-xs font-medium text-indigo-700 hover:bg-indigo-100 dark:text-indigo-300 dark:hover:bg-indigo-900/40"
            >
              Dismiss
            </button>
          </div>
        </>
      )}
    </div>
  );
}
