// Real content (localStorage-backed match history) lands in enhancements/12.
// This route exists now so the nav/router shell is complete in enhancements/10.
export function HistoryPage() {
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
      <p className="text-sm font-medium text-slate-600 dark:text-slate-300">History coming soon</p>
      <p className="max-w-xs text-xs text-slate-400 dark:text-slate-500">
        Past matches you've run in this browser will show up here.
      </p>
    </div>
  );
}
