import { type FormEvent, useId, useState } from "react";
import { Link, useLocation, useNavigate, useOutletContext } from "react-router";
import type { RootLayoutContext } from "../layouts/RootLayout";
import { ApiError } from "../lib/api";

const INPUT_CLASS =
  "mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-600";

interface LocationStateWithFrom {
  from?: { pathname: string; search: string };
}

export function LoginPage() {
  const { auth } = useOutletContext<RootLayoutContext>();
  const navigate = useNavigate();
  const location = useLocation();
  const emailId = useId();
  const passwordId = useId();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await auth.signIn(email, password);
      const from = (location.state as LocationStateWithFrom | null)?.from;
      navigate(from ? `${from.pathname}${from.search}` : "/account", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm">
      <h1 className="text-lg font-semibold text-slate-900 dark:text-white">Sign in</h1>
      <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
        Sign in to save match history and shortlists across devices.
      </p>

      <form onSubmit={handleSubmit} className="mt-6 space-y-4" noValidate>
        <div>
          <label htmlFor={emailId} className="text-sm font-medium text-slate-700 dark:text-slate-200">
            Email
          </label>
          <input
            id={emailId}
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className={INPUT_CLASS}
          />
        </div>

        <div>
          <label htmlFor={passwordId} className="text-sm font-medium text-slate-700 dark:text-slate-200">
            Password
          </label>
          <input
            id={passwordId}
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className={INPUT_CLASS}
          />
        </div>

        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50 dark:disabled:opacity-40"
        >
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>

      <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">
        Don't have an account?{" "}
        <Link to="/register" className="font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400 dark:hover:text-indigo-300">
          Register
        </Link>
      </p>
    </div>
  );
}
