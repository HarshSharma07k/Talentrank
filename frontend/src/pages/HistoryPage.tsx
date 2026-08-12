import { useId, useState } from "react";
import { useNavigate } from "react-router";
import { useHistory } from "../hooks/useHistory";
import type { HistoryEntry } from "../lib/history";
import { encodeShare } from "../lib/share";

function formatTimestamp(createdAt: number): string {
  return new Date(createdAt).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function HistoryRow({
  entry,
  selected,
  onToggleSelect,
  onRename,
  onRemove,
  onView,
  viewing,
}: {
  entry: HistoryEntry;
  selected: boolean;
  onToggleSelect: () => void;
  onRename: (label: string) => void;
  onRemove: () => void;
  onView: () => void;
  viewing: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draftLabel, setDraftLabel] = useState(entry.label);
  const checkboxId = useId();

  function commitRename() {
    const trimmed = draftLabel.trim();
    if (trimmed) onRename(trimmed);
    setEditing(false);
  }

  return (
    <li className="flex items-start gap-3 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <input
        id={checkboxId}
        type="checkbox"
        checked={selected}
        onChange={onToggleSelect}
        aria-label={`Select "${entry.label}" for comparison`}
        className="mt-1 h-4 w-4 shrink-0 accent-indigo-600"
      />

      <div className="min-w-0 flex-1">
        {editing ? (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              commitRename();
            }}
            className="flex items-center gap-2"
          >
            <input
              autoFocus
              value={draftLabel}
              onChange={(event) => setDraftLabel(event.target.value)}
              onBlur={commitRename}
              className="w-full rounded-lg border border-slate-200 px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
          </form>
        ) : (
          <button
            type="button"
            onClick={() => {
              setDraftLabel(entry.label);
              setEditing(true);
            }}
            className="text-left text-sm font-semibold text-slate-900 hover:text-indigo-600 dark:text-white dark:hover:text-indigo-400"
            title="Click to rename"
          >
            {entry.label}
          </button>
        )}

        <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
          {formatTimestamp(entry.createdAt)} · {entry.results.length} result
          {entry.results.length === 1 ? "" : "s"} · top_k={entry.topK}, top_n={entry.topN}
        </p>
      </div>

      <div className="flex shrink-0 items-center gap-1">
        <button
          type="button"
          onClick={onView}
          disabled={viewing}
          className="rounded-lg px-2 py-1 text-xs font-medium text-indigo-600 hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-50 dark:text-indigo-400 dark:hover:bg-indigo-950/30"
        >
          {viewing ? "Loading…" : "View"}
        </button>
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Delete "${entry.label}"`}
          className="rounded-lg px-2 py-1 text-xs font-medium text-slate-400 hover:bg-red-50 hover:text-red-600 dark:text-slate-500 dark:hover:bg-red-950/30 dark:hover:text-red-400"
        >
          Delete
        </button>
      </div>
    </li>
  );
}

export function HistoryPage() {
  const { entries, remove, rename, clear, getDetail, source, loading } = useHistory();
  const [selected, setSelected] = useState<string[]>([]);
  const [viewingId, setViewingId] = useState<string | null>(null);
  const navigate = useNavigate();

  function toggleSelect(id: string) {
    setSelected((current) => {
      if (current.includes(id)) return current.filter((existing) => existing !== id);
      // At most two selected at a time -- comparison is always exactly two runs.
      return current.length >= 2 ? [current[1], id] : [...current, id];
    });
  }

  async function viewEntry(entry: HistoryEntry) {
    // Server-backed list entries carry an empty `resumeText` (GET /me/history
    // omits it -- see serverHistory.ts); fetch the real detail before building the
    // share link, or a signed-in user's "View" would re-run an empty resume.
    setViewingId(entry.id);
    try {
      const full = source === "server" ? await getDetail(entry.id) : entry;
      if (!full) return;

      // Reuses the share-link mechanism (enhancements/12) to reload a past search:
      // MatchPage's own hash-on-mount handling populates the form and re-runs it
      // against the current model, exactly like a link a friend sent you.
      const encoded = encodeShare({
        v: 1,
        r: full.resumeText,
        k: full.topK,
        n: full.topN,
        f: full.filters,
      });
      navigate(`/#s=${encoded}`);
    } finally {
      setViewingId(null);
    }
  }

  if (loading) {
    return <p className="text-sm text-slate-500 dark:text-slate-400">Loading…</p>;
  }

  if (entries.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-slate-200 py-16 text-center dark:border-slate-800">
        <svg viewBox="0 0 24 24" fill="none" className="h-8 w-8 text-slate-300 dark:text-slate-700">
          <path
            d="M12 8v5l3 3M21 12a9 9 0 1 1-9-9"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <p className="text-sm font-medium text-slate-600 dark:text-slate-300">No matches yet</p>
        <p className="max-w-xs text-xs text-slate-400 dark:text-slate-500">
          {source === "server"
            ? "Matches you run are saved to your account automatically."
            : "Matches you run are saved here automatically, in this browser only."}
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold text-slate-900 dark:text-white">History</h1>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={selected.length !== 2}
            onClick={() => navigate(`/compare?a=${selected[0]}&b=${selected[1]}`)}
            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Compare selected ({selected.length}/2)
          </button>
          <button
            type="button"
            onClick={() => void clear()}
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-500 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-800"
          >
            Clear all
          </button>
        </div>
      </div>

      <ul className="space-y-2">
        {entries.map((entry) => (
          <HistoryRow
            key={entry.id}
            entry={entry}
            selected={selected.includes(entry.id)}
            onToggleSelect={() => toggleSelect(entry.id)}
            onRename={(label) => void rename(entry.id, label)}
            onRemove={() => void remove(entry.id)}
            onView={() => void viewEntry(entry)}
            viewing={viewingId === entry.id}
          />
        ))}
      </ul>
    </div>
  );
}
