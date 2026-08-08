import { useRef, useState } from "react";
import { Header } from "./components/Header";
import { ResumeForm } from "./components/ResumeForm";
import { ResultsList } from "./components/ResultsList";
import { EmptyState, ErrorState, LoadingState } from "./components/StatePanels";
import { useHealthCheck } from "./hooks/useHealthCheck";
import { ApiError, matchResume, type JobMatch } from "./lib/api";

type RequestState = "idle" | "loading" | "success" | "error";

function App() {
  const health = useHealthCheck();

  const [resumeText, setResumeText] = useState("");
  const [results, setResults] = useState<JobMatch[]>([]);
  const [requestState, setRequestState] = useState<RequestState>("idle");
  const [errorMessage, setErrorMessage] = useState("");

  const abortControllerRef = useRef<AbortController | null>(null);

  async function runMatch() {
    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setRequestState("loading");
    setErrorMessage("");

    try {
      const response = await matchResume(resumeText, controller.signal);
      setResults(response.results);
      setRequestState("success");
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setErrorMessage(error instanceof ApiError ? error.message : "Something went wrong. Please try again.");
      setRequestState("error");
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <Header health={health} />

      <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6 sm:py-10">
        <div className="mb-8 max-w-2xl">
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl dark:text-white">
            Find the jobs that fit a resume
          </h1>
          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
            TalentRank retrieves the top candidate jobs from a 123k-posting corpus with a bi-encoder,
            then reranks them with a cross-encoder for precision.
          </p>
        </div>

        <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
          <section>
            <div className="lg:sticky lg:top-6">
              <ResumeForm
                resumeText={resumeText}
                onResumeTextChange={setResumeText}
                onSubmit={runMatch}
                loading={requestState === "loading"}
              />
            </div>
          </section>

          <section>
            <h2 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
              {requestState === "success" ? `Top ${results.length} matches` : "Results"}
            </h2>

            {requestState === "idle" && <EmptyState />}
            {requestState === "loading" && <LoadingState />}
            {requestState === "error" && <ErrorState message={errorMessage} onRetry={runMatch} />}
            {requestState === "success" &&
              (results.length > 0 ? <ResultsList results={results} /> : <EmptyState />)}
          </section>
        </div>
      </main>
    </div>
  );
}

export default App;
