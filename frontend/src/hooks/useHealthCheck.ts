import { useEffect, useState } from "react";
import { checkHealth, type HealthResponse } from "../lib/api";

export type HealthState = "checking" | "online" | "warming" | "offline";

const POLL_INTERVAL_MS = 20_000;
// Backs off polling when the tab is hidden -- the previous unconditional 20s poll
// ran forever in a background tab. See enhancements/10.
const HIDDEN_POLL_INTERVAL_MS = 60_000;

export interface UseHealthCheckResult {
  state: HealthState;
  health: HealthResponse | null;
}

export function useHealthCheck(): UseHealthCheckResult {
  const [state, setState] = useState<HealthState>("checking");
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    let timeoutId: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const response = await checkHealth(controller.signal);
        if (cancelled) return;
        setHealth(response);
        setState(response.warm ? "online" : "warming");
      } catch {
        if (!cancelled) {
          setState("offline");
          setHealth(null);
        }
      } finally {
        if (!cancelled) {
          const interval = document.visibilityState === "hidden" ? HIDDEN_POLL_INTERVAL_MS : POLL_INTERVAL_MS;
          timeoutId = setTimeout(poll, interval);
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
