import { type FormEvent, useId, useState } from "react";
import { Link, useNavigate, useOutletContext } from "react-router";
import type { RootLayoutContext } from "../layouts/RootLayout";
import { ApiError } from "../lib/api";

const INPUT_CLASS =
  "mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-600";

// Mirrors the backend's TALENTRANK_PASSWORD_MIN_CHARS default (12) -- a client-
// side hint only; the server is the source of truth and still validates this.
const PASSWORD_MIN_CHARS = 12;

export function RegisterPage() {
  const { auth } = useOutletContext<RootLayoutContext>();
  const navigate = useNavigate();
  const emailId = useId();
  const passwordId = useId();
  const displayNameId = useId();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await auth.signUp(email, password, displayName.trim() || undefined);
      navigate("/account", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm">
      <h1 className="text-lg font-semibold text-slate-900 dark:text-white">Create an account</h1>
      <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
        Save match history and shortlists across devices. Matching itself never requires an
        account.
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
          <label htmlFor={displayNameId} className="text-sm font-medium text-slate-700 dark:text-slate-200">
            Display name <span className="font-normal text-slate-400 dark:text-slate-500">(optional)</span>
          </label>
          <input
            id={displayNameId}
            type="text"
            autoComplete="name"
            maxLength={80}
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
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
            minLength={PASSWORD_MIN_CHARS}
            autoComplete="new-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className={INPUT_CLASS}
          />
          <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">At least {PASSWORD_MIN_CHARS} characters.</p>
        </div>

        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50 dark:disabled:opacity-40"
        >
          {submitting ? "Creating account…" : "Create account"}
        </button>
      </form>

      <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">
        Already have an account?{" "}
        <Link to="/login" className="font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400 dark:hover:text-indigo-300">
          Sign in
        </Link>
      </p>
    </div>
  );
}
