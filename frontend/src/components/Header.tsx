import { NavLink } from "react-router";
import type { HealthState } from "../hooks/useHealthCheck";
import { useTheme } from "../hooks/useTheme";

const STATUS_COPY: Record<HealthState, { label: string; dot: string }> = {
  checking: { label: "Checking API…", dot: "bg-amber-400" },
  online: { label: "API online", dot: "bg-emerald-500" },
  warming: { label: "Waking up…", dot: "bg-amber-400" },
  offline: { label: "API offline", dot: "bg-red-500" },
};

const NAV_LINKS = [
  { to: "/", label: "Match", end: true },
  { to: "/history", label: "History" },
  { to: "/compare", label: "Compare" },
  { to: "/how-it-works", label: "How it works" },
];

function navLinkClassName({ isActive }: { isActive: boolean }): string {
  return [
    "rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
    isActive
      ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300"
      : "text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white",
  ].join(" ");
}

export function Header({ state }: { state: HealthState }) {
  const [theme, toggleTheme] = useTheme();
  const status = STATUS_COPY[state];

  return (
    <header className="border-b border-slate-200 dark:border-slate-800">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-6">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-600">
            <svg viewBox="0 0 32 32" fill="none" className="h-5 w-5">
              <path d="M8 22V14" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" />
              <path d="M16 22V9" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" />
              <path d="M24 22V17" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" />
            </svg>
          </div>
          <div>
            <p className="text-base font-semibold leading-tight text-slate-900 dark:text-white">
              TalentRank
            </p>
            <p className="text-xs leading-tight text-slate-500 dark:text-slate-400">
              Semantic resume-to-job matching
            </p>
          </div>
        </div>

        <nav className="flex items-center gap-1" aria-label="Primary">
          {NAV_LINKS.map((link) => (
            <NavLink key={link.to} to={link.to} end={link.end} className={navLinkClassName}>
              {link.label}
            </NavLink>
          ))}
        </nav>

        <div className="flex items-center gap-3">
          <span
            className="flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300"
            title={status.label}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${status.dot}`} />
            {status.label}
          </span>

          <button
            type="button"
            onClick={toggleTheme}
            aria-label="Toggle color theme"
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-100 dark:border-slate-800 dark:text-slate-400 dark:hover:bg-slate-800"
          >
            {theme === "dark" ? (
              <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4">
                <path
                  d="M12 3v1.5M12 19.5V21M4.5 12H3M21 12h-1.5M6 6l1 1M18 18l-1-1M6 18l1-1M18 6l-1 1"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                />
                <circle cx="12" cy="12" r="4.5" stroke="currentColor" strokeWidth="1.6" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4">
                <path
                  d="M20.5 14.5A8.5 8.5 0 1 1 9.5 3.5a7 7 0 0 0 11 11Z"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinejoin="round"
                />
              </svg>
            )}
          </button>
        </div>
      </div>
    </header>
  );
}
