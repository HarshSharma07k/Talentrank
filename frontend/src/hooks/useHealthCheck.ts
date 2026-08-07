import { useEffect, useState } from "react";
import { checkHealth } from "../lib/api";

export type HealthState = "checking" | "online" | "offline";

const POLL_INTERVAL_MS = 20_000;

export function useHealthCheck(): HealthState {
  const [state, setState] = useState<HealthState>("checking");

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    async function poll() {
      try {
        await checkHealth(controller.signal);
        if (!cancelled) setState("online");
      } catch {
        if (!cancelled) setState("offline");
      }
    }

    poll();
    const interval = setInterval(poll, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      controller.abort();
      clearInterval(interval);
    };
  }, []);

  return state;
}
