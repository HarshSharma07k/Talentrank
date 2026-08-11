export function EmptyState() {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-slate-200 py-16 text-center dark:border-slate-800">
      <svg viewBox="0 0 24 24" fill="none" className="h-8 w-8 text-slate-300 dark:text-slate-700">
        <path
          d="M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16Zm10 2-4.35-4.35"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <p className="text-sm font-medium text-slate-600 dark:text-slate-300">No matches yet</p>
      <p className="max-w-xs text-xs text-slate-400 dark:text-slate-500">
        Paste a resume above and run a match to see ranked job results here.
      </p>
    </div>
  );
}

export function WarmingState() {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-amber-200 bg-amber-50 py-16 text-center dark:border-amber-900/50 dark:bg-amber-950/30">
      <svg className="h-6 w-6 animate-spin text-amber-500" viewBox="0 0 24 24" fill="none">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8v3a5 5 0 0 0-5 5H4Z" />
      </svg>
      <div>
        <p className="text-sm font-medium text-amber-700 dark:text-amber-300">Waking the demo</p>
        <p className="mt-1 max-w-xs text-xs text-amber-600/80 dark:text-amber-400/80">
          This runs on a free hosting tier that sleeps when idle. The first match takes longer while it
          starts back up -- it'll retry automatically.
        </p>
      </div>
    </div>
  );
}

export function LoadingState() {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-slate-200 py-16 text-center dark:border-slate-800">
      <svg className="h-6 w-6 animate-spin text-indigo-600" viewBox="0 0 24 24" fill="none">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8v3a5 5 0 0 0-5 5H4Z" />
      </svg>
      <div>
        <p className="text-sm font-medium text-slate-600 dark:text-slate-300">Ranking candidates…</p>
        <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
          Retrieving top matches with FAISS, then reranking with a cross-encoder. This can take a few
          seconds on CPU.
        </p>
      </div>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-red-200 bg-red-50 py-12 text-center dark:border-red-900/50 dark:bg-red-950/30">
      <svg viewBox="0 0 24 24" fill="none" className="h-7 w-7 text-red-500">
        <path
          d="M12 9v4m0 4h.01M10.29 3.86 1.82 18a1.5 1.5 0 0 0 1.3 2.25h17.76a1.5 1.5 0 0 0 1.3-2.25L13.71 3.86a1.5 1.5 0 0 0-2.42 0Z"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <p className="text-sm font-medium text-red-700 dark:text-red-300">Couldn't match this resume</p>
      <p className="max-w-sm text-xs text-red-600/80 dark:text-red-400/80">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-2 rounded-lg border border-red-300 bg-white px-3 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-100 dark:border-red-800 dark:bg-transparent dark:text-red-300 dark:hover:bg-red-950/50"
      >
        Try again
      </button>
    </div>
  );
}
