import { cleanup, render, waitFor } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AuthSession } from "./useAuthSession";
import { useHistory, type UseHistoryResult } from "./useHistory";
import type { JobMatch } from "../lib/api";
import { saveEntry, type HistoryEntry } from "../lib/history";
import * as serverHistory from "../lib/serverHistory";

vi.mock("../lib/serverHistory");

function makeJobMatch(): JobMatch {
  return {
    job_id: 1,
    job_title: "Test Job",
    description: "desc",
    skills: "",
    job_category: "TEST",
    job_family: "OTHER",
    bi_encoder_score: 0.5,
    cross_encoder_score: 1.0,
    scores: { bi_encoder: 0.5, cross_encoder: 1.0, cross_encoder_probability: 0.7, skill_overlap: 0.1 },
    explanation: null,
    retrieval_rank: 1,
    rank: 1,
  };
}

function makeEntry(id: string): HistoryEntry {
  return {
    id,
    createdAt: Date.now(),
    label: `Entry ${id}`,
    resumeText: "some resume text",
    topK: 30,
    topN: 10,
    filters: {},
    results: [makeJobMatch()],
  };
}

function makeAuth(status: "anonymous" | "authenticated"): AuthSession {
  return {
    user:
      status === "authenticated"
        ? { id: "u1", email: "person@example.com", display_name: null, created_at: "2026-01-01T00:00:00Z" }
        : null,
    status,
    signIn: vi.fn(),
    signUp: vi.fn(),
    signOut: vi.fn(),
    refresh: vi.fn(),
  };
}

function HookProbe({ onResult }: { onResult: (result: UseHistoryResult) => void }) {
  const result = useHistory();
  onResult(result);
  return null;
}

function Harness({ auth, onResult }: { auth: AuthSession; onResult: (result: UseHistoryResult) => void }) {
  return (
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/" element={<Outlet context={{ state: "online", health: null, auth }} />}>
          <Route index element={<HookProbe onResult={onResult} />} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("useHistory", () => {
  it("uses_local_storage_when_anonymous", async () => {
    saveEntry([], makeEntry("local-a"));

    const results: UseHistoryResult[] = [];
    render(<Harness auth={makeAuth("anonymous")} onResult={(r) => results.push(r)} />);

    await waitFor(() => expect(results.at(-1)?.loading).toBe(false));

    const latest = results.at(-1)!;
    expect(latest.source).toBe("local");
    expect(latest.entries.map((e) => e.id)).toEqual(["local-a"]);
    expect(serverHistory.fetchEntries).not.toHaveBeenCalled();
  });

  it("uses_server_when_authenticated", async () => {
    vi.mocked(serverHistory.fetchEntries).mockResolvedValue([makeEntry("server-a")]);

    const results: UseHistoryResult[] = [];
    render(<Harness auth={makeAuth("authenticated")} onResult={(r) => results.push(r)} />);

    await waitFor(() => expect(results.at(-1)?.loading).toBe(false));

    const latest = results.at(-1)!;
    expect(latest.source).toBe("server");
    expect(latest.entries.map((e) => e.id)).toEqual(["server-a"]);
  });

  it("switches_source_on_sign_out", async () => {
    vi.mocked(serverHistory.fetchEntries).mockResolvedValue([makeEntry("server-a")]);
    saveEntry([], makeEntry("local-a"));

    const results: UseHistoryResult[] = [];
    const { rerender } = render(<Harness auth={makeAuth("authenticated")} onResult={(r) => results.push(r)} />);

    await waitFor(() => expect(results.at(-1)?.source).toBe("server"));

    rerender(<Harness auth={makeAuth("anonymous")} onResult={(r) => results.push(r)} />);

    await waitFor(() => expect(results.at(-1)?.source).toBe("local"));
    expect(results.at(-1)?.entries.map((e) => e.id)).toEqual(["local-a"]);
  });

  it("falls_back_to_local_when_server_history_fails", async () => {
    vi.mocked(serverHistory.fetchEntries).mockRejectedValue(new Error("server unreachable"));
    saveEntry([], makeEntry("local-fallback"));

    const results: UseHistoryResult[] = [];
    render(<Harness auth={makeAuth("authenticated")} onResult={(r) => results.push(r)} />);

    await waitFor(() => expect(results.at(-1)?.loading).toBe(false));

    // History must not be stuck empty/erroring after a server outage -- the local
    // copy (still intact, never deleted by server mode) is shown instead.
    expect(results.at(-1)?.entries.map((e) => e.id)).toEqual(["local-fallback"]);
  });
});
