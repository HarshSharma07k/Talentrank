import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AUTH_STORAGE_KEY, type AuthUser, clearAuth, isExpired, loadAuth, saveAuth, type StoredAuth } from "./auth";

function makeUser(): AuthUser {
  return { id: "u1", email: "person@example.com", display_name: "Person", created_at: "2026-01-01T00:00:00Z" };
}

function makeStored(overrides: Partial<StoredAuth> = {}): StoredAuth {
  return { version: 1, token: "tok_abc123", expiresAt: Date.now() + 60_000, user: makeUser(), ...overrides };
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("auth", () => {
  it("roundtrip: save then load returns the same session", () => {
    const stored = makeStored();
    saveAuth(stored);

    expect(loadAuth()).toEqual(stored);
  });

  it("load_returns_null_on_corrupt_json", () => {
    localStorage.setItem(AUTH_STORAGE_KEY, "{not valid json");

    expect(() => loadAuth()).not.toThrow();
    expect(loadAuth()).toBeNull();
  });

  it("load_returns_null_on_version_mismatch", () => {
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify({ ...makeStored(), version: 2 }));

    expect(loadAuth()).toBeNull();
  });

  it("load_survives_localstorage_throwing", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("SecurityError", "SecurityError");
    });

    expect(() => loadAuth()).not.toThrow();
    expect(loadAuth()).toBeNull();
  });

  it("is_expired_respects_expires_at", () => {
    const past = makeStored({ expiresAt: Date.now() - 1000 });
    const future = makeStored({ expiresAt: Date.now() + 60_000 });

    expect(isExpired(past)).toBe(true);
    expect(isExpired(future)).toBe(false);
  });

  it("clear_removes_the_key", () => {
    saveAuth(makeStored());
    expect(loadAuth()).not.toBeNull();

    clearAuth();

    expect(loadAuth()).toBeNull();
    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toBeNull();
  });
});
