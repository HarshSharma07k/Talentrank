import { useEffect, useId, useRef, useState } from "react";
import { useOutletContext } from "react-router";
import type { RootLayoutContext } from "../layouts/RootLayout";
import {
  addSavedListItem,
  ApiError,
  createSavedList,
  getSavedLists,
  type SavedListSummary,
} from "../lib/api";

interface SaveToListButtonProps {
  jobId: number;
  jobTitle: string;
  jobFamily: string;
}

/**
 * "Save to list" on a `JobCard`. Only rendered for signed-in users -- see
 * enhancements/23. Lists are fetched lazily on first open, not eagerly on every
 * card mount: a page of ten results would otherwise fire ten `GET /me/lists`
 * calls before the user has clicked anything.
 */
export function SaveToListButton({ jobId, jobTitle, jobFamily }: SaveToListButtonProps) {
  const { auth } = useOutletContext<RootLayoutContext>();
  const [open, setOpen] = useState(false);
  const [lists, setLists] = useState<SavedListSummary[] | null>(null);
  const [savedListIds, setSavedListIds] = useState<Set<string>>(new Set());
  const [newListName, setNewListName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const menuId = useId();
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    function handlePointerDown(event: PointerEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [open]);

  // Renders nothing for anonymous visitors -- see enhancements/23's own "do not
  // show to anonymous users" rule. After all hooks, per the rules of hooks.
  if (auth.status !== "authenticated") return null;

  async function ensureListsLoaded() {
    if (lists !== null) return;
    try {
      setLists(await getSavedLists());
    } catch {
      setLists([]);
      setError("Couldn't load your lists.");
    }
  }

  function toggleOpen() {
    setOpen((current) => {
      const next = !current;
      if (next) void ensureListsLoaded();
      return next;
    });
  }

  async function saveTo(listId: string) {
    setBusy(true);
    setError("");
    try {
      await addSavedListItem(listId, jobId, jobTitle, jobFamily);
      setSavedListIds((current) => new Set(current).add(listId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save this job.");
    } finally {
      setBusy(false);
    }
  }

  async function createAndSave() {
    const name = newListName.trim();
    if (!name) return;
    setBusy(true);
    setError("");
    try {
      const created = await createSavedList(name);
      const summary: SavedListSummary = {
        id: created.id,
        name: created.name,
        created_at: created.created_at,
        updated_at: created.updated_at,
        item_count: 0,
      };
      setLists((current) => [summary, ...(current ?? [])]);
      setNewListName("");
      await saveTo(created.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't create the list.");
      setBusy(false);
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={toggleOpen}
        aria-expanded={open}
        aria-controls={menuId}
        className="flex h-6 items-center gap-1 rounded-full border border-slate-200 px-2 text-[11px] font-medium text-slate-500 transition hover:border-slate-300 hover:text-slate-700 dark:border-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
      >
        <svg viewBox="0 0 24 24" fill="none" className="h-3 w-3">
          <path
            d="M6 4h12a1 1 0 0 1 1 1v15l-7-4-7 4V5a1 1 0 0 1 1-1Z"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinejoin="round"
          />
        </svg>
        Save
      </button>

      {open && (
        <div
          id={menuId}
          className="absolute right-0 z-10 mt-1 w-56 rounded-xl border border-slate-200 bg-white p-2 shadow-lg dark:border-slate-700 dark:bg-slate-800"
        >
          {lists === null && <p className="px-2 py-1.5 text-xs text-slate-400">Loading…</p>}

          {lists !== null && lists.length === 0 && (
            <p className="px-2 py-1.5 text-xs text-slate-400 dark:text-slate-500">No lists yet.</p>
          )}

          {lists !== null && lists.length > 0 && (
            <ul className="max-h-40 space-y-0.5 overflow-y-auto">
              {lists.map((list) => {
                const saved = savedListIds.has(list.id);
                return (
                  <li key={list.id}>
                    <button
                      type="button"
                      disabled={busy || saved}
                      onClick={() => void saveTo(list.id)}
                      className="flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left text-xs text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed dark:text-slate-300 dark:hover:bg-slate-700"
                    >
                      <span className="truncate">{list.name}</span>
                      {saved && <span className="shrink-0 text-emerald-600 dark:text-emerald-400">Saved</span>}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}

          <form
            onSubmit={(event) => {
              event.preventDefault();
              void createAndSave();
            }}
            className="mt-2 flex items-center gap-1 border-t border-slate-100 pt-2 dark:border-slate-700"
          >
            <input
              value={newListName}
              onChange={(event) => setNewListName(event.target.value)}
              placeholder="New list…"
              disabled={busy}
              className="min-w-0 flex-1 rounded-lg border border-slate-200 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            />
            <button
              type="submit"
              disabled={busy || newListName.trim().length === 0}
              className="shrink-0 rounded-lg bg-indigo-600 px-2 py-1 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              Add
            </button>
          </form>

          {error && <p className="mt-1 px-2 text-[11px] text-red-600 dark:text-red-400">{error}</p>}
        </div>
      )}
    </div>
  );
}
