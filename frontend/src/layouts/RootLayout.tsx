import { Outlet } from "react-router";
import { Header } from "../components/Header";
import { useHealthCheck, type UseHealthCheckResult } from "../hooks/useHealthCheck";

export type RootLayoutContext = UseHealthCheckResult;

export function RootLayout() {
  const { state, health } = useHealthCheck();
  const context: RootLayoutContext = { state, health };

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 dark:bg-slate-950">
      <Header state={state} />

      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:px-6 sm:py-10">
        <Outlet context={context} />
      </main>

      <footer className="border-t border-slate-200 py-6 text-center text-xs text-slate-400 dark:border-slate-800 dark:text-slate-600">
        <p>
          TalentRank — semantic resume-to-job matching.{" "}
          <a
            href="https://github.com/HarshSharma07k/Talentrank"
            target="_blank"
            rel="noreferrer"
            className="underline hover:text-slate-600 dark:hover:text-slate-400"
          >
            Source on GitHub
          </a>
        </p>
      </footer>
    </div>
  );
}
