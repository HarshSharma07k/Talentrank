import { createBrowserRouter } from "react-router";
import { RootLayout } from "./layouts/RootLayout";
import { ComparePage } from "./pages/ComparePage";
import { HistoryPage } from "./pages/HistoryPage";
import { HowItWorksPage } from "./pages/HowItWorksPage";
import { MatchPage } from "./pages/MatchPage";

export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      { index: true, element: <MatchPage /> },
      { path: "history", element: <HistoryPage /> },
      { path: "compare", element: <ComparePage /> },
      { path: "how-it-works", element: <HowItWorksPage /> },
    ],
  },
]);
