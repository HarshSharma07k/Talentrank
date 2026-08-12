import { useEffect, useId, useState } from "react";
import {
  ApiError,
  createSavedList,
  deleteSavedList,
  getSavedListDetail,
  getSavedLists,
  removeSavedListItem,
  renameSavedList,
  type SavedListDetail,
  type SavedListSummary,
} from "../lib/api";
import { formatCategory } from "../lib/format";

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function CreateListForm({ onCreated }: { onCreated: (list: SavedListSummary) => void }) {
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit() {
    const trimmed = name.trim();
    if (!trimmed) return;
    setBusy(true);
    setError("");
    try {
      const created = await createSavedList(trimmed);
      onCreated({
        id: created.id,
        name: created.name,
        created_at: created.created_at,
        updated_at: created.updated_at,
        item_count: 0,
      });
      setName("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't create the list.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        void handleSubmit();
      }}
      className="flex items-center gap-2"
    >
      <input
        value={name}
        onChange={(event) => setName(event.target.value)}
        placeholder="New list name…"
        disabled={busy}
        className="min-w-0 flex-1 rounded-lg border border-slate-200 px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      />
      <button
        type="submit"
        disabled={busy || name.trim().length === 0}
        className="shrink-0 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
      >
        Create
      </button>
      {error && <span className="text-xs text-red-600 dark:text-red-400">{error}</span>}
    </form>
  );
}

function ListCard({ summary, onRemoved }: { summary: SavedListSummary; onRemoved: () => void }) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<SavedListDetail | null>(null);
  const [editing, setEditing] = useState(false);
  const [draftName, setDraftName] = useState(summary.name);
  const [name, setName] = useState(summary.name);
  const [itemCount, setItemCount] = useState(summary.item_count);
  const inputId = useId();

  async function toggleOpen() {
    const next = !open;
    setOpen(next);
    if (next && detail === null) {
      try {
        setDetail(await getSavedListDetail(summary.id));
      } catch {
        setDetail(null);
      }
    }
  }

  async function commitRename() {
    const trimmed = draftName.trim();
    setEditing(false);
    if (!trimmed || trimmed === name) return;
    try {
      const updated = await renameSavedList(summary.id, trimmed);
      setName(updated.name);
    } catch {
      setDraftName(name); // roll back on failure
    }
  }

  async function handleDeleteList() {
    try {
      await deleteSavedList(summary.id);
      onRemoved();
    } catch {
      // left in place -- the user can retry
    }
  }

  async function handleRemoveItem(jobId: number) {
    if (!detail) return;
    const previous = detail;
    setDetail({ ...detail, items: detail.items.filter((item) => item.job_id !== jobId) });
    setItemCount((count) => Math.max(0, count - 1));
    try {
      await removeSavedListItem(summary.id, jobId);
    } catch {
      setDetail(previous);
      setItemCount(summary.item_count);
    }
  }

  return (
    <li className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          {editing ? (
            <input
              id={inputId}
              autoFocus
              value={draftName}
              onChange={(event) => setDraftName(event.target.value)}
              onBlur={() => void commitRename()}
              onKeyDown={(event) => {
                if (event.key === "Enter") void commitRename();
              }}
              className="w-full rounded-lg border border-slate-200 px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
          ) : (
            <button
              type="button"
              onClick={() => {
                setDraftName(name);
                setEditing(true);
              }}
              className="text-left text-sm font-semibold text-slate-900 hover:text-indigo-600 dark:text-white dark:hover:text-indigo-400"
              title="Click to rename"
            >
              {name}
            </button>
          )}
          <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
            {itemCount} item{itemCount === 1 ? "" : "s"} · created {formatTimestamp(summary.created_at)}
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={() => void toggleOpen()}
            className="rounded-lg px-2 py-1 text-xs font-medium text-indigo-600 hover:bg-indigo-50 dark:text-indigo-400 dark:hover:bg-indigo-950/30"
          >
            {open ? "Hide" : "View"}
          </button>
          <button
            type="button"
            onClick={() => void handleDeleteList()}
            className="rounded-lg px-2 py-1 text-xs font-medium text-slate-400 hover:bg-red-50 hover:text-red-600 dark:text-slate-500 dark:hover:bg-red-950/30 dark:hover:text-red-400"
          >
            Delete
          </button>
        </div>
      </div>

      {open && (
        <div className="mt-3 border-t border-slate-100 pt-3 dark:border-slate-800/60">
          {detail === null ? (
            <p className="text-xs text-slate-400">Loading…</p>
          ) : detail.items.length === 0 ? (
            <p className="text-xs text-slate-400 dark:text-slate-500">No jobs saved to this list yet.</p>
          ) : (
            <ul className="space-y-1.5">
              {detail.items.map((item) => (
                <li
                  key={item.job_id}
                  className="flex items-center justify-between gap-2 rounded-lg bg-slate-50 px-2.5 py-1.5 text-xs dark:bg-slate-800/60"
                >
                  <span className="min-w-0 truncate text-slate-700 dark:text-slate-200">
                    {item.job_title}{" "}
                    <span className="text-slate-400 dark:text-slate-500">· {formatCategory(item.job_family)}</span>
                  </span>
                  <button
                    type="button"
                    onClick={() => void handleRemoveItem(item.job_id)}
                    className="shrink-0 text-slate-400 hover:text-red-600 dark:text-slate-500 dark:hover:text-red-400"
                    aria-label={`Remove "${item.job_title}" from this list`}
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}

/** `GET /me/lists` management page. Only reachable when signed in -- see
 * `routes.tsx`'s `RequireAuth` wrapper. See enhancements/23. */
export function SavedListsPage() {
  const [lists, setLists] = useState<SavedListSummary[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    getSavedLists()
      .then((fetched) => !cancelled && setLists(fetched))
      .catch(() => !cancelled && setError("Couldn't load your saved lists."));
    return () => {
      cancelled = true;
    };
  }, []);

  function handleCreated(list: SavedListSummary) {
    setLists((current) => [list, ...(current ?? [])]);
  }

  function handleRemoved(id: string) {
    setLists((current) => (current ?? []).filter((list) => list.id !== id));
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold text-slate-900 dark:text-white">Saved lists</h1>

      <CreateListForm onCreated={handleCreated} />

      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}

      {lists === null && !error && <p className="text-sm text-slate-500 dark:text-slate-400">Loading…</p>}

      {lists !== null && lists.length === 0 && (
        <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-slate-200 py-16 text-center dark:border-slate-800">
          <p className="text-sm font-medium text-slate-600 dark:text-slate-300">No saved lists yet</p>
          <p className="max-w-xs text-xs text-slate-400 dark:text-slate-500">
            Use "Save" on a job result to add it to a list.
          </p>
        </div>
      )}

      {lists !== null && lists.length > 0 && (
        <ul className="space-y-2">
          {lists.map((list) => (
            <ListCard key={list.id} summary={list} onRemoved={() => handleRemoved(list.id)} />
          ))}
        </ul>
      )}
    </div>
  );
}
