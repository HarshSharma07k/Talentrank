import { createBrowserRouter } from "react-router";
import { RequireAuth } from "./components/RequireAuth";
import { RootLayout } from "./layouts/RootLayout";
import { AccountPage } from "./pages/AccountPage";
import { ComparePage } from "./pages/ComparePage";
import { HistoryPage } from "./pages/HistoryPage";
import { HowItWorksPage } from "./pages/HowItWorksPage";
import { LoginPage } from "./pages/LoginPage";
import { MatchPage } from "./pages/MatchPage";
import { RegisterPage } from "./pages/RegisterPage";

export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      { index: true, element: <MatchPage /> },
      { path: "history", element: <HistoryPage /> },
      { path: "compare", element: <ComparePage /> },
      { path: "how-it-works", element: <HowItWorksPage /> },
      { path: "login", element: <LoginPage /> },
      { path: "register", element: <RegisterPage /> },
      {
        path: "account",
        element: (
          <RequireAuth>
            <AccountPage />
          </RequireAuth>
        ),
      },
    ],
  },
]);
