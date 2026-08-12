import { useEffect, useRef, useState } from "react";
import { useOutletContext } from "react-router";
import type { RootLayoutContext } from "../layouts/RootLayout";
import { postFeedback } from "../lib/api";

interface FeedbackButtonsProps {
  jobId: number;
  rank: number;
  resumeHash: string;
  runId: string | null;
  /** The server's own state, once `useFeedbackState` has resolved it -- `undefined`
   * while still loading, so this component doesn't flash "no signal" before the
   * real state is known. */
  initialSignal?: "up" | "down";
  /** Whether this result's "Why this match?" panel is currently open -- the
   * trigger for the one-time `click` relevance signal. See enhancements/23's own
   * warning that an accordion toggled four times must fire one signal, not four. */
  expanded: boolean;
}

/**
 * Thumbs up/down on a `JobCard`, plus the fire-once `click` signal when the
 * result is expanded. Renders nothing for anonymous visitors -- see
 * enhancements/23's own "do not show to anonymous users" rule; an anonymous
 * visitor is using the product as designed, not missing out on a disabled
 * control. Self-contained (reads auth state itself) so it's directly testable
 * without threading an `authenticated` prop through every caller.
 */
export function FeedbackButtons({ jobId, rank, resumeHash, runId, initialSignal, expanded }: FeedbackButtonsProps) {
  const { auth } = useOutletContext<RootLayoutContext>();
  const [signal, setSignal] = useState<"up" | "down" | null>(null);
  const seededRef = useRef(false);
  // undefined (not null) is the "hasn't fired yet" sentinel -- runId itself is
  // legitimately `null` (persistence can fail for a signed-in user too), so `null`
  // cannot double as "not fired".
  const clickFiredForRunRef = useRef<string | null | undefined>(undefined);

  useEffect(() => {
    if (!seededRef.current && initialSignal !== undefined) {
      setSignal(initialSignal);
      seededRef.current = true;
    }
  }, [initialSignal]);

  useEffect(() => {
    if (auth.status !== "authenticated") return;
    if (!expanded) return;
    if (clickFiredForRunRef.current === runId) return; // already fired for this run
    clickFiredForRunRef.current = runId;
    void postFeedback(jobId, "click", rank, resumeHash, runId).catch(() => {
      // A missed click signal is not worth surfacing to the user -- it's a
      // background relevance ping, not a user-visible action.
    });
  }, [auth.status, expanded, runId, jobId, rank, resumeHash]);

  if (auth.status !== "authenticated") return null;

  async function toggle(clicked: "up" | "down") {
    const previous = signal;
    const next = clicked === previous ? null : clicked;
    setSignal(next); // optimistic

    try {
      await postFeedback(jobId, clicked, rank, resumeHash, runId);
    } catch {
      setSignal(previous); // roll back -- the UI must not disagree with the server after an error
    }
  }

  const baseButton =
    "flex h-6 w-6 items-center justify-center rounded-full border text-xs transition disabled:cursor-not-allowed disabled:opacity-50";

  return (
    <div className="flex items-center gap-1">
      <button
        type="button"
        onClick={() => void toggle("up")}
        aria-pressed={signal === "up"}
        aria-label="This match is relevant"
        title="This match is relevant"
        className={`${baseButton} ${
          signal === "up"
            ? "border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400"
            : "border-slate-200 text-slate-400 hover:border-slate-300 hover:text-slate-600 dark:border-slate-700 dark:text-slate-500 dark:hover:text-slate-300"
        }`}
      >
        <svg viewBox="0 0 24 24" fill="none" className="h-3.5 w-3.5">
          <path
            d="M7 11v9H4a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1h3Zm0 0 4.5-8a2 2 0 0 1 2 2.2L12.6 9H19a2 2 0 0 1 1.94 2.5l-1.6 7A2 2 0 0 1 17.4 20H7"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
      <button
        type="button"
        onClick={() => void toggle("down")}
        aria-pressed={signal === "down"}
        aria-label="This match is not relevant"
        title="This match is not relevant"
        className={`${baseButton} ${
          signal === "down"
            ? "border-red-300 bg-red-50 text-red-700 dark:border-red-700 dark:bg-red-500/10 dark:text-red-400"
            : "border-slate-200 text-slate-400 hover:border-slate-300 hover:text-slate-600 dark:border-slate-700 dark:text-slate-500 dark:hover:text-slate-300"
        }`}
      >
        <svg viewBox="0 0 24 24" fill="none" className="h-3.5 w-3.5">
          <path
            d="M17 13V4h3a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1h-3Zm0 0-4.5 8a2 2 0 0 1-2-2.2l.9-5.8H5a2 2 0 0 1-1.94-2.5l1.6-7A2 2 0 0 1 6.6 4H17"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
    </div>
  );
}
