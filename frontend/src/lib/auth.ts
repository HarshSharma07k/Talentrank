/**
 * Session token storage. See enhancements/22. No React here -- `useAuthSession.ts`
 * is the thin hook wrapper around these plain functions, same split as
 * `history.ts` / `useHistory.ts`.
 *
 * localStorage, deliberately, not an httpOnly cookie: the deployed topology is a
 * Vercel frontend calling a cross-site Hugging Face Spaces API, which would need
 * `SameSite=None; Secure` -- exactly the category Safari blocks outright and
 * Firefox partitions by default. Not memory-only either: enhancements/20 chose
 * opaque sessions with no refresh-token mechanism, so a memory-only token logs
 * the user out on every reload and every new tab. The honest cost is that an XSS
 * gets the session token; that cost is bounded by the token being revocable and
 * expiring server-side, and by this app rendering no untrusted HTML (see the
 * enhancements/22 audit -- zero `dangerouslySetInnerHTML` in the codebase).
 */

export interface AuthUser {
  id: string;
  email: string;
  display_name: string | null;
  created_at: string;
}

export const AUTH_STORAGE_KEY = "talentrank.auth.v1";

/** Dispatched on `window` when `apiFetch` clears a token the server rejected --
 * `useAuthSession` listens for this to update the signed-in state in the same
 * tab (the `storage` event only reaches *other* tabs). */
export const AUTH_EXPIRED_EVENT = "talentrank:auth-expired";

export interface StoredAuth {
  version: 1;
  token: string;
  expiresAt: number; // epoch ms, from SessionResponse.expires_at
  user: AuthUser;
}

/** Returns `null` on any failure -- corrupt JSON, a future schema version, or
 * Safari private mode throwing outright -- exactly `history.ts`'s `readRaw`
 * shape, never propagating. */
export function loadAuth(): StoredAuth | null {
  let raw: string | null;
  try {
    raw = localStorage.getItem(AUTH_STORAGE_KEY);
  } catch {
    return null;
  }
  if (!raw) return null;

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }

  if (
    typeof parsed !== "object" ||
    parsed === null ||
    (parsed as StoredAuth).version !== 1 ||
    typeof (parsed as StoredAuth).token !== "string" ||
    typeof (parsed as StoredAuth).expiresAt !== "number" ||
    typeof (parsed as StoredAuth).user !== "object" ||
    (parsed as StoredAuth).user === null
  ) {
    return null;
  }

  return parsed as StoredAuth;
}

export function saveAuth(value: StoredAuth): void {
  try {
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(value));
  } catch {
    // Best-effort: a failed write just means this tab won't survive a reload
    // signed in, not a crash. Unlike history.ts there is nothing to prune and
    // retry -- one auth record is already the smallest possible payload.
  }
}

export function clearAuth(): void {
  try {
    localStorage.removeItem(AUTH_STORAGE_KEY);
  } catch {
    // ignore -- nothing meaningful to recover from a private-mode throw here
  }
}

export function isExpired(value: StoredAuth): boolean {
  return Date.now() >= value.expiresAt;
}
