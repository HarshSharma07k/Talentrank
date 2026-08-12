import { useEffect, useState } from "react";
import { getMe, login as apiLogin, logout as apiLogout, register as apiRegister } from "../lib/api";
import { AUTH_EXPIRED_EVENT, AUTH_STORAGE_KEY, type AuthUser, clearAuth, isExpired, loadAuth, saveAuth } from "../lib/auth";

export interface AuthSession {
  user: AuthUser | null;
  status: "anonymous" | "authenticated";
  signIn(email: string, password: string): Promise<void>;
  signUp(email: string, password: string, displayName?: string): Promise<void>;
  signOut(): Promise<void>;
  refresh(): Promise<void>;
}

function initialUser(): AuthUser | null {
  const stored = loadAuth();
  return stored && !isExpired(stored) ? stored.user : null;
}

/**
 * `RootLayout` calls this once. See enhancements/22.
 *
 * Hydrates from `localStorage` synchronously in `useState`'s initializer, not a
 * `useEffect` -- a signed-in user must never see a one-frame flash of the
 * signed-out header. Listens for `AUTH_EXPIRED_EVENT` (same-tab: `apiFetch`
 * cleared a rejected token) and the cross-tab `storage` event on
 * `AUTH_STORAGE_KEY` (a *different* tab signed out or in) -- `storage` does not
 * fire in the tab that made the change, which is exactly what
 * `AUTH_EXPIRED_EVENT` and the direct state updates in `signIn`/`signOut` below
 * are for. `12` hit this identical quirk with `history.ts`.
 */
export function useAuthSession(): AuthSession {
  const [user, setUser] = useState<AuthUser | null>(initialUser);

  useEffect(() => {
    function handleExpired() {
      setUser(null);
    }
    function handleStorage(event: StorageEvent) {
      if (event.key !== AUTH_STORAGE_KEY) return;
      const stored = loadAuth();
      setUser(stored && !isExpired(stored) ? stored.user : null);
    }

    window.addEventListener(AUTH_EXPIRED_EVENT, handleExpired);
    window.addEventListener("storage", handleStorage);
    return () => {
      window.removeEventListener(AUTH_EXPIRED_EVENT, handleExpired);
      window.removeEventListener("storage", handleStorage);
    };
  }, []);

  async function signIn(email: string, password: string): Promise<void> {
    const session = await apiLogin(email, password);
    saveAuth({
      version: 1,
      token: session.token,
      expiresAt: new Date(session.expires_at).getTime(),
      user: session.user,
    });
    setUser(session.user);
  }

  async function signUp(email: string, password: string, displayName?: string): Promise<void> {
    const session = await apiRegister(email, password, displayName);
    saveAuth({
      version: 1,
      token: session.token,
      expiresAt: new Date(session.expires_at).getTime(),
      user: session.user,
    });
    setUser(session.user);
  }

  async function signOut(): Promise<void> {
    try {
      await apiLogout();
    } catch {
      // A network failure must not leave a user staring at a sign-out button
      // that does nothing -- clear locally regardless of the outcome. The
      // server-side session expires on its own.
    }
    clearAuth();
    setUser(null);
  }

  async function refresh(): Promise<void> {
    const stored = loadAuth();
    if (stored === null) {
      setUser(null);
      return;
    }
    try {
      const freshUser = await getMe();
      saveAuth({ ...stored, user: freshUser });
      setUser(freshUser);
    } catch {
      // A 401 here already triggered apiFetch's own clear-and-dispatch, which
      // handleExpired above will pick up; any other failure just leaves the
      // cached user in place rather than surfacing a refresh error.
    }
  }

  return {
    user,
    status: user !== null ? "authenticated" : "anonymous",
    signIn,
    signUp,
    signOut,
    refresh,
  };
}
