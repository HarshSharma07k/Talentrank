import type { ReactNode } from "react";
import { Navigate, useLocation, useOutletContext } from "react-router";
import type { RootLayoutContext } from "../layouts/RootLayout";

/**
 * Route guard for `/account`. See enhancements/22. `replace` on the redirect
 * matters: the guarded URL must not land in the history stack, or Back returns
 * to it. `state={{ from: location }}` is how `LoginPage` knows where to send the
 * user back to after a successful sign-in.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { auth } = useOutletContext<RootLayoutContext>();
  const location = useLocation();

  if (auth.status === "anonymous") {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <>{children}</>;
}
