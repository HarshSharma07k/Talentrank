import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { checkHealth, extractText, getMe } from "./api";
import { AUTH_EXPIRED_EVENT, type AuthUser, loadAuth, saveAuth, type StoredAuth } from "./auth";

function makeUser(): AuthUser {
  return { id: "u1", email: "person@example.com", display_name: null, created_at: "2026-01-01T00:00:00Z" };
}

function makeStored(): StoredAuth {
  return { version: 1, token: "tok_abc123", expiresAt: Date.now() + 60_000, user: makeUser() };
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("apiFetch", () => {
  it("attaches_bearer_when_token_present", async () => {
    saveAuth(makeStored());
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, makeUser()));
    vi.stubGlobal("fetch", fetchMock);

    await getMe();

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer tok_abc123");
  });

  it("omits_authorization_when_anonymous", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { status: "healthy" }));
    vi.stubGlobal("fetch", fetchMock);

    await checkHealth();

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;
    expect(headers.has("Authorization")).toBe(false);
  });

  it("does_not_set_content_type_for_formdata", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, { text: "", char_count: 0, page_count: null, filename: "a.pdf", truncated: false }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const file = new File(["content"], "resume.pdf", { type: "application/pdf" });
    await extractText(file);

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;
    expect(headers.has("Content-Type")).toBe(false);
    expect(init.body).toBeInstanceOf(FormData);
  });

  it("clears_token_and_emits_event_on_401", async () => {
    saveAuth(makeStored());
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(401, { detail: "Not authenticated." }));
    vi.stubGlobal("fetch", fetchMock);

    const eventSpy = vi.fn();
    window.addEventListener(AUTH_EXPIRED_EVENT, eventSpy);

    await expect(getMe()).rejects.toThrow();

    expect(loadAuth()).toBeNull();
    expect(eventSpy).toHaveBeenCalledTimes(1);

    window.removeEventListener(AUTH_EXPIRED_EVENT, eventSpy);
  });

  it("does_not_clear_token_on_403", async () => {
    saveAuth(makeStored());
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(403, { detail: "Registration is currently disabled." }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getMe()).rejects.toThrow();

    expect(loadAuth()).not.toBeNull();
  });

  it("propagates_abort_error", async () => {
    const abortError = new DOMException("The operation was aborted.", "AbortError");
    const fetchMock = vi.fn().mockRejectedValue(abortError);
    vi.stubGlobal("fetch", fetchMock);

    const controller = new AbortController();
    let caught: unknown;
    try {
      await checkHealth(controller.signal);
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeInstanceOf(DOMException);
    expect((caught as DOMException).name).toBe("AbortError");
  });
});
