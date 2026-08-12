import { type FormEvent, useId, useState } from "react";
import { useNavigate, useOutletContext } from "react-router";
import type { RootLayoutContext } from "../layouts/RootLayout";
import { ApiError, changePassword as apiChangePassword, logoutAll as apiLogoutAll, updateMe } from "../lib/api";

const INPUT_CLASS =
  "mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-600";
const PASSWORD_MIN_CHARS = 12; // mirrors TALENTRANK_PASSWORD_MIN_CHARS's default -- see RegisterPage.tsx

function ProfileSection() {
  const { auth } = useOutletContext<RootLayoutContext>();
  const displayNameId = useId();
  const [displayName, setDisplayName] = useState(auth.user?.display_name ?? "");
  const [status, setStatus] = useState<"idle" | "saving" | "saved">("idle");
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setStatus("saving");
    try {
      await updateMe(displayName.trim() || null);
      await auth.refresh();
      setStatus("saved");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save your profile. Please try again.");
      setStatus("idle");
    }
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
      <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Profile</h2>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{auth.user?.email}</p>

      <form onSubmit={handleSubmit} className="mt-4 space-y-3">
        <div>
          <label htmlFor={displayNameId} className="text-sm font-medium text-slate-700 dark:text-slate-200">
            Display name
          </label>
          <input
            id={displayNameId}
            type="text"
            maxLength={80}
            value={displayName}
            onChange={(event) => {
              setDisplayName(event.target.value);
              setStatus("idle");
            }}
            className={INPUT_CLASS}
          />
        </div>

        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={status === "saving"}
            className="rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50 dark:disabled:opacity-40"
          >
            {status === "saving" ? "Saving…" : "Save"}
          </button>
          {status === "saved" && <span className="text-xs text-emerald-600 dark:text-emerald-400">Saved.</span>}
        </div>
      </form>
    </section>
  );
}

function ChangePasswordSection() {
  const currentId = useId();
  const newId = useId();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [status, setStatus] = useState<"idle" | "saving" | "saved">("idle");
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setStatus("saving");
    try {
      await apiChangePassword(current, next);
      setCurrent("");
      setNext("");
      setStatus("saved");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't change your password. Please try again.");
      setStatus("idle");
    }
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
      <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Change password</h2>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
        Changing your password signs out every other session, but not this one.
      </p>

      <form onSubmit={handleSubmit} className="mt-4 space-y-3">
        <div>
          <label htmlFor={currentId} className="text-sm font-medium text-slate-700 dark:text-slate-200">
            Current password
          </label>
          <input
            id={currentId}
            type="password"
            required
            autoComplete="current-password"
            value={current}
            onChange={(event) => {
              setCurrent(event.target.value);
              setStatus("idle");
            }}
            className={INPUT_CLASS}
          />
        </div>
        <div>
          <label htmlFor={newId} className="text-sm font-medium text-slate-700 dark:text-slate-200">
            New password
          </label>
          <input
            id={newId}
            type="password"
            required
            minLength={PASSWORD_MIN_CHARS}
            autoComplete="new-password"
            value={next}
            onChange={(event) => {
              setNext(event.target.value);
              setStatus("idle");
            }}
            className={INPUT_CLASS}
          />
        </div>

        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={status === "saving"}
            className="rounded-lg border border-slate-300 bg-white px-4 py-1.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-transparent dark:text-slate-200 dark:hover:bg-slate-800"
          >
            {status === "saving" ? "Updating…" : "Update password"}
          </button>
          {status === "saved" && <span className="text-xs text-emerald-600 dark:text-emerald-400">Updated.</span>}
        </div>
      </form>
    </section>
  );
}

function SessionsSection() {
  const [status, setStatus] = useState<"idle" | "working" | "done">("idle");
  const [error, setError] = useState<string | null>(null);

  async function handleSignOutEverywhere() {
    setError(null);
    setStatus("working");
    try {
      await apiLogoutAll();
      setStatus("done");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't sign out other sessions. Please try again.");
      setStatus("idle");
    }
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
      <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Sessions</h2>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
        Sign out of this account on every other device or browser. This one stays signed in.
      </p>

      {error && <p className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}

      <button
        type="button"
        onClick={handleSignOutEverywhere}
        disabled={status === "working"}
        className="mt-4 rounded-lg border border-slate-300 bg-white px-4 py-1.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-transparent dark:text-slate-200 dark:hover:bg-slate-800"
      >
        {status === "working" ? "Signing out…" : "Sign out other sessions"}
      </button>
      {status === "done" && (
        <span className="ml-3 text-xs text-emerald-600 dark:text-emerald-400">Done -- other sessions signed out.</span>
      )}
    </section>
  );
}

export function AccountPage() {
  const { auth } = useOutletContext<RootLayoutContext>();
  const navigate = useNavigate();

  async function handleSignOut() {
    await auth.signOut();
    navigate("/", { replace: true });
  }

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-900 dark:text-white">Account</h1>
        <button
          type="button"
          onClick={handleSignOut}
          className="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
        >
          Sign out
        </button>
      </div>

      <ProfileSection />
      <ChangePasswordSection />
      <SessionsSection />
    </div>
  );
}
