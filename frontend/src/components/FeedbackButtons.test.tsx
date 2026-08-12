import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AuthSession } from "../hooks/useAuthSession";
import * as api from "../lib/api";
import { FeedbackButtons } from "./FeedbackButtons";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, postFeedback: vi.fn() };
});

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

function renderWithAuth(auth: AuthSession, props: Partial<React.ComponentProps<typeof FeedbackButtons>> = {}) {
  const defaultProps: React.ComponentProps<typeof FeedbackButtons> = {
    jobId: 42,
    rank: 3,
    resumeHash: "a".repeat(16),
    runId: "run-1",
    expanded: false,
    ...props,
  };
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/" element={<Outlet context={{ state: "online", health: null, auth }} />}>
          <Route index element={<FeedbackButtons {...defaultProps} />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.mocked(api.postFeedback).mockReset();
  vi.mocked(api.postFeedback).mockResolvedValue({ id: "fb-1", action: "created" });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("FeedbackButtons", () => {
  it("hidden_when_anonymous", () => {
    const { container } = renderWithAuth(makeAuth("anonymous"));
    expect(container.innerHTML).toBe("");
    expect(api.postFeedback).not.toHaveBeenCalled();
  });

  it("sends_rank_with_signal", async () => {
    renderWithAuth(makeAuth("authenticated"), { jobId: 7, rank: 5, resumeHash: "b".repeat(16), runId: "run-9" });

    fireEvent.click(screen.getByLabelText("This match is relevant"));

    await waitFor(() => expect(api.postFeedback).toHaveBeenCalledTimes(1));
    expect(api.postFeedback).toHaveBeenCalledWith(7, "up", 5, "b".repeat(16), "run-9");
  });

  it("second_click_toggles_off", async () => {
    renderWithAuth(makeAuth("authenticated"));
    const upButton = screen.getByLabelText("This match is relevant");

    fireEvent.click(upButton);
    await waitFor(() => expect(upButton.getAttribute("aria-pressed")).toBe("true"));

    fireEvent.click(upButton);
    await waitFor(() => expect(upButton.getAttribute("aria-pressed")).toBe("false"));

    expect(api.postFeedback).toHaveBeenCalledTimes(2);
    expect(vi.mocked(api.postFeedback).mock.calls[0][1]).toBe("up");
    expect(vi.mocked(api.postFeedback).mock.calls[1][1]).toBe("up"); // same signal both times -- the server does the toggle
  });

  it("click_signal_fires_once_per_result", async () => {
    const { rerender } = renderWithAuth(makeAuth("authenticated"), { expanded: false });

    await waitFor(() => expect(api.postFeedback).not.toHaveBeenCalled());

    const auth = makeAuth("authenticated");
    function rerenderWith(expanded: boolean) {
      rerender(
        <MemoryRouter initialEntries={["/"]}>
          <Routes>
            <Route path="/" element={<Outlet context={{ state: "online", health: null, auth }} />}>
              <Route
                index
                element={
                  <FeedbackButtons
                    jobId={42}
                    rank={3}
                    resumeHash={"a".repeat(16)}
                    runId="run-1"
                    expanded={expanded}
                  />
                }
              />
            </Route>
          </Routes>
        </MemoryRouter>,
      );
    }

    rerenderWith(true); // open once
    await waitFor(() =>
      expect(api.postFeedback).toHaveBeenCalledWith(42, "click", 3, "a".repeat(16), "run-1"),
    );

    rerenderWith(false); // close
    rerenderWith(true); // reopen -- an accordion toggled again is still one signal, not two
    rerenderWith(false);
    rerenderWith(true);

    const clickCalls = vi.mocked(api.postFeedback).mock.calls.filter((call) => call[1] === "click");
    expect(clickCalls).toHaveLength(1);
  });
});
