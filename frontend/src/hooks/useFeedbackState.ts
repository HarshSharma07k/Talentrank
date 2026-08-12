import { useEffect, useState } from "react";
import { getFeedbackState } from "../lib/api";

/**
 * The signed-in caller's own `up`/`down` feedback for every job in one run,
 * fetched once per run rather than once per `JobCard` -- `GET /me/feedback`
 * already returns the whole run's state in one call, so fetching it per-card
 * would re-download the same list N times for an N-result page. See
 * enhancements/23.
 */
export function useFeedbackState(enabled: boolean, runId: string | null): Map<number, "up" | "down"> {
  const [state, setState] = useState<Map<number, "up" | "down">>(new Map());

  useEffect(() => {
    if (!enabled || !runId) {
      setState(new Map());
      return;
    }

    let cancelled = false;
    getFeedbackState(runId)
      .then((rows) => {
        if (cancelled) return;
        setState(new Map(rows.map((row) => [row.job_id, row.signal])));
      })
      .catch(() => {
        if (!cancelled) setState(new Map());
      });

    return () => {
      cancelled = true;
    };
  }, [enabled, runId]);

  return state;
}
