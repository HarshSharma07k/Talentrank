// Real content (side-by-side comparison of two saved matches, ?a=<id>&b=<id>) lands
// in enhancements/12. This route exists now so the nav/router shell is complete in
// enhancements/10.
export function ComparePage() {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-slate-200 py-16 text-center dark:border-slate-800">
      <svg viewBox="0 0 24 24" fill="none" className="h-8 w-8 text-slate-300 dark:text-slate-700">
        <path
          d="M9 3v18M15 3v18M4 8h5M15 8h5M4 16h5M15 16h5"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <p className="text-sm font-medium text-slate-600 dark:text-slate-300">Compare coming soon</p>
      <p className="max-w-xs text-xs text-slate-400 dark:text-slate-500">
        Pick two saved matches from History to compare their results side by side.
      </p>
    </div>
  );
}
