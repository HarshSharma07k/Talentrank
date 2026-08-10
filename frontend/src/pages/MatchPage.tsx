import { useMemo, useRef, useState } from "react";
import { useOutletContext } from "react-router";
import { PipelineStepper, type PipelineStage } from "../components/PipelineStepper";
import { ResumeForm } from "../components/ResumeForm";
import { ResultsList } from "../components/ResultsList";
import type { SearchControlsValue } from "../components/SearchControls";
import { EmptyState, ErrorState, LoadingState, WarmingState } from "../components/StatePanels";
import type { RootLayoutContext } from "../layouts/RootLayout";
import { ApiError, matchResume, retrieveOnly, type JobMatch, type MatchFilters } from "../lib/api";

const DEFAULT_CONTROLS: SearchControlsValue = {
  topK: 30,
  topN: 10,
  jobFamilies: [],
  minScore: 0,
  sort: "relevance",
};

// Client-side only, re-sorting the array already in hand -- instant, no refetch.
// See enhancements/11.
function sortResults(results: JobMatch[], sort: SearchControlsValue["sort"]): JobMatch[] {
  const sorted = [...results];
  switch (sort) {
    case "relevance":
      sorted.sort((a, b) => b.scores.cross_encoder_probability - a.scores.cross_encoder_probability);
      break;
    case "semantic":
      sorted.sort((a, b) => b.scores.bi_encoder - a.scores.bi_encoder);
      break;
    case "skill_coverage":
      sorted.sort((a, b) => b.scores.skill_overlap - a.scores.skill_overlap);
      break;
  }
  return sorted;
}

export function MatchPage() {
  const { state: healthState, health } = useOutletContext<RootLayoutContext>();

  const [resumeText, setResumeText] = useState("");
  const [controls, setControls] = useState<SearchControlsValue>(DEFAULT_CONTROLS);
  const [stage, setStage] = useState<PipelineStage>("idle");
  const [rawResults, setRawResults] = useState<JobMatch[]>([]);
  const [errorMessage, setErrorMessage] = useState("");
  const [counts, setCounts] = useState<{ filtered: number; total: number } | null>(null);

  // A monotonically-increasing sequence number, not just two AbortControllers: a
  // late /retrieve response arriving after a newer submit's /match has already
  // landed must not overwrite it, even if it technically wasn't aborted in time.
  // See enhancements/11's risk note on this exact race.
  const requestSeqRef = useRef(0);
  const retrieveAbortRef = useRef<AbortController | null>(null);
  const matchAbortRef = useRef<AbortController | null>(null);

  const results = useMemo(() => sortResults(rawResults, controls.sort), [rawResults, controls.sort]);

  async function runMatch() {
    const seq = ++requestSeqRef.current;

    retrieveAbortRef.current?.abort();
    matchAbortRef.current?.abort();
    const retrieveController = new AbortController();
    retrieveAbortRef.current = retrieveController;
    const matchController = new AbortController();
    matchAbortRef.current = matchController;

    setErrorMessage("");
    setCounts(null);
    setStage("retrieving");

    const filters: MatchFilters = {
      job_families: controls.jobFamilies.length > 0 ? controls.jobFamilies : null,
      min_score: controls.minScore > 0 ? controls.minScore : null,
    };

    try {
      // Stage 1: bi-encoder retrieval only, no reranking -- returns in tens of
      // milliseconds and never touches the cross-encoder's inference semaphore
      // (pipeline.retrieve_response never calls rerank()), so it can't contend with
      // stage 2 for the single-slot semaphore on a max_concurrent_inferences=1
      // backend.
      const retrieveResponse = await retrieveOnly(
        resumeText,
        { topK: controls.topK, topN: controls.topN },
        retrieveController.signal,
      );
      if (seq !== requestSeqRef.current) return;
      setRawResults(retrieveResponse.results);
      setStage("shortlisted");
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      if (seq !== requestSeqRef.current) return;
      setErrorMessage(error instanceof ApiError ? error.message : "Something went wrong. Please try again.");
      setStage("error");
      return;
    }

    try {
      // Stage 2: retrieve + cross-encoder rerank. Replacing `results` here is what
      // ResultsList's FLIP effect animates as a reorder.
      const matchResponse = await matchResume(
        resumeText,
        { topK: controls.topK, topN: controls.topN, filters },
        matchController.signal,
      );
      if (seq !== requestSeqRef.current) return;
      setRawResults(matchResponse.results);
      setCounts({ filtered: matchResponse.filtered_candidates, total: matchResponse.total_candidates });
      setStage("ranked");
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      if (seq !== requestSeqRef.current) return;
      setErrorMessage(error instanceof ApiError ? error.message : "Something went wrong. Please try again.");
      setStage("error");
    }
  }

  const corpusDescription =
    health !== null ? `a ${health.corpus_size.toLocaleString()}-posting corpus` : "the job corpus";

  const isLoading = stage === "retrieving";
  const showWarming = stage === "idle" && healthState === "warming";
  const showEmptyIdle = stage === "idle" && healthState !== "warming";

  return (
    <>
      <div className="mb-8 max-w-2xl">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl dark:text-white">
          Find the jobs that fit a resume
        </h1>
        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
          TalentRank retrieves the top candidate jobs from {corpusDescription} with a bi-encoder, then
          reranks them with a cross-encoder for precision.
        </p>
      </div>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <section>
          <div className="lg:sticky lg:top-6">
            <ResumeForm
              resumeText={resumeText}
              onResumeTextChange={setResumeText}
              onSubmit={runMatch}
              loading={stage === "retrieving" || stage === "shortlisted"}
              searchControls={controls}
              onSearchControlsChange={setControls}
              resultSummary={counts}
            />
          </div>
        </section>

        <section>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
            <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-200">
              {stage === "ranked"
                ? `Top ${results.length} matches`
                : stage === "shortlisted"
                  ? "Shortlist — reranking…"
                  : "Results"}
            </h2>
            <PipelineStepper stage={stage} />
          </div>

          {showWarming && <WarmingState />}
          {showEmptyIdle && <EmptyState />}
          {isLoading && <LoadingState />}
          {stage === "error" && <ErrorState message={errorMessage} onRetry={runMatch} />}
          {(stage === "shortlisted" || stage === "ranked") &&
            (results.length > 0 ? <ResultsList results={results} /> : <EmptyState />)}
        </section>
      </div>
    </>
  );
}
