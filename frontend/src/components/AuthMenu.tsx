import { Link } from "react-router";
import type { AuthSession } from "../hooks/useAuthSession";

/** The header's signed-in/signed-out control. See enhancements/22. */
export function AuthMenu({ auth }: { auth: AuthSession }) {
  if (auth.status === "anonymous") {
    return (
      <Link
        to="/login"
        className="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
      >
        Sign in
      </Link>
    );
  }

  const label = auth.user?.display_name || auth.user?.email || "Account";

  return (
    <Link
      to="/account"
      className="flex max-w-[10rem] items-center gap-1.5 truncate rounded-lg px-3 py-1.5 text-sm font-medium text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
      title={label}
    >
      <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4 shrink-0">
        <circle cx="12" cy="8" r="3.25" stroke="currentColor" strokeWidth="1.6" />
        <path d="M4.5 19.5c1.5-3.5 4.5-5.25 7.5-5.25s6 1.75 7.5 5.25" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
      <span className="truncate">{label}</span>
    </Link>
  );
}
