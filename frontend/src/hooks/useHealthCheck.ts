import { useEffect, useState } from "react";
import { checkHealth, type HealthResponse } from "../lib/api";

export type HealthState = "checking" | "online" | "warming" | "offline";

const POLL_INTERVAL_MS = 20_000;
// Backs off polling when the tab is hidden -- the previous unconditional 20s poll
// ran forever in a background tab. See enhancements/10.
const HIDDEN_POLL_INTERVAL_MS = 60_000;

// A sleeping Hugging Face Space doesn't serve /health with warm: false while it
// boots -- the platform proxy fails the request outright (connection refused,
// timeout, or a non-JSON "starting up" page) until the container is up. Without
// this grace period, every visitor who arrives at a cold Space sees a hard red
// "API offline" for the entire boot window, indistinguishable from a genuinely
// broken deployment. Treat the first few consecutive failures as "warming" and
// retry quickly; only fall back to "offline" once failures persist past a boot-
// sized window. See enhancements/13, item 2.
const WARMING_GRACE_FAILURES = 4;
const WARMING_RETRY_INTERVAL_MS = 5_000;

export interface UseHealthCheckResult {
  state: HealthState;
  health: HealthResponse | null;
}

export function useHealthCheck(): UseHealthCheckResult {
  const [state, setState] = useState<HealthState>("checking");
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    let consecutiveFailures = 0;
    const controller = new AbortController();
    let timeoutId: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      let nextIntervalMs = document.visibilityState === "hidden" ? HIDDEN_POLL_INTERVAL_MS : POLL_INTERVAL_MS;

      try {
        const response = await checkHealth(controller.signal);
        if (cancelled) return;
        consecutiveFailures = 0;
        setHealth(response);
        setState(response.warm ? "online" : "warming");
      } catch {
        if (!cancelled) {
          consecutiveFailures += 1;
          if (consecutiveFailures <= WARMING_GRACE_FAILURES) {
            setState("warming");
            nextIntervalMs = WARMING_RETRY_INTERVAL_MS;
          } else {
            setState("offline");
          }
          setHealth(null);
        }
      } finally {
        if (!cancelled) {
          timeoutId = setTimeout(poll, nextIntervalMs);
        }
      }
    }

    poll();

    return () => {
      cancelled = true;
      controller.abort();
      if (timeoutId !== undefined) clearTimeout(timeoutId);
    };
  }, []);

  return { state, health };
}
