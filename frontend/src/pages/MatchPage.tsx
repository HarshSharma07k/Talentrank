import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useOutletContext } from "react-router";
import { PipelineStepper, type PipelineStage } from "../components/PipelineStepper";
import { ResumeForm } from "../components/ResumeForm";
import { ResultsList } from "../components/ResultsList";
import type { SearchControlsValue } from "../components/SearchControls";
import { SkillGapStrip } from "../components/SkillGapStrip";
import { EmptyState, ErrorState, LoadingState, WarmingState } from "../components/StatePanels";
import { useHistory } from "../hooks/useHistory";
import type { RootLayoutContext } from "../layouts/RootLayout";
import { ApiError, matchResume, retrieveOnly, type JobMatch, type MatchFilters } from "../lib/api";
import { makeLabel } from "../lib/history";
import { resultsToJson, resultsToMarkdown } from "../lib/resultsExport";
import { decodeShare, encodeShare, isShareOversize } from "../lib/share";

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

function controlsToFilters(controls: SearchControlsValue): MatchFilters {
  return {
    job_families: controls.jobFamilies.length > 0 ? controls.jobFamilies : null,
    min_score: controls.minScore > 0 ? controls.minScore : null,
  };
}

export function MatchPage() {
  const { state: healthState, health } = useOutletContext<RootLayoutContext>();
  const { save: saveHistoryEntry } = useHistory();

  const [resumeText, setResumeText] = useState("");
  const [controls, setControls] = useState<SearchControlsValue>(DEFAULT_CONTROLS);
  const [stage, setStage] = useState<PipelineStage>("idle");
  const [rawResults, setRawResults] = useState<JobMatch[]>([]);
  const [errorMessage, setErrorMessage] = useState("");
  const [counts, setCounts] = useState<{ filtered: number; total: number } | null>(null);
  const [sharedBanner, setSharedBanner] = useState(false);
  const [shareStatus, setShareStatus] = useState<"idle" | "copied" | "oversize" | "error">("idle");
  const [exportStatus, setExportStatus] = useState<"idle" | "copied" | "error">("idle");

  // A monotonically-increasing sequence number, not just two AbortControllers: a
  // late /retrieve response arriving after a newer submit's /match has already
  // landed must not overwrite it, even if it technically wasn't aborted in time.
  // See enhancements/11's risk note on this exact race.
  const requestSeqRef = useRef(0);
  const retrieveAbortRef = useRef<AbortController | null>(null);
  const matchAbortRef = useRef<AbortController | null>(null);
  // Guards the share-link auto-run: a hash is processed once, ever, per distinct
  // value -- never re-run on a hash change that repeats a value already handled,
  // and never on incidental re-renders. See enhancements/12's risk note.
  const processedHashRef = useRef<string | null>(null);

  const results = useMemo(() => sortResults(rawResults, controls.sort), [rawResults, controls.sort]);

  const runMatch = useCallback(async (overrideResumeText?: string, overrideControls?: SearchControlsValue) => {
    // Explicit overrides (used by the share-link auto-run) rather than relying on
    // component state having propagated yet -- setResumeText/setControls called
    // moments earlier in the same effect would not be visible via closure here.
    const effectiveResumeText = overrideResumeText ?? resumeText;
    const effectiveControls = overrideControls ?? controls;

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

    const filters = controlsToFilters(effectiveControls);

    try {
      // Stage 1: bi-encoder retrieval only, no reranking -- returns in tens of
      // milliseconds and never touches the cross-encoder's inference semaphore
      // (pipeline.retrieve_response never calls rerank()), so it can't contend with
      // stage 2 for the single-slot semaphore on a max_concurrent_inferences=1
      // backend.
      const retrieveResponse = await retrieveOnly(
        effectiveResumeText,
        { topK: effectiveControls.topK, topN: effectiveControls.topN },
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
        effectiveResumeText,
        { topK: effectiveControls.topK, topN: effectiveControls.topN, filters },
        matchController.signal,
      );
      if (seq !== requestSeqRef.current) return;
      setRawResults(matchResponse.results);
      setCounts({ filtered: matchResponse.filtered_candidates, total: matchResponse.total_candidates });
      setStage("ranked");

      if (matchResponse.results.length > 0) {
        saveHistoryEntry({
          id: crypto.randomUUID(),
          createdAt: Date.now(),
          label: makeLabel(effectiveResumeText),
          resumeText: effectiveResumeText,
          topK: effectiveControls.topK,
          topN: effectiveControls.topN,
          filters,
          results: matchResponse.results,
        });
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      if (seq !== requestSeqRef.current) return;
      setErrorMessage(error instanceof ApiError ? error.message : "Something went wrong. Please try again.");
      setStage("error");
    }
    // Stable identity except when resumeText/controls actually change, so the
    // share-link effect below can correctly list it as a dependency without
    // re-attaching its hashchange listener on every unrelated render.
  }, [resumeText, controls, saveHistoryEntry]);

  useEffect(() => {
    function handleHashShare() {
      const hash = window.location.hash;
      if (!hash || hash === processedHashRef.current) return;
      processedHashRef.current = hash;

      const decoded = decodeShare(hash);
      if (!decoded) return;

      const decodedControls: SearchControlsValue = {
        topK: decoded.k,
        topN: decoded.n,
        jobFamilies: decoded.f.job_families ?? [],
        minScore: decoded.f.min_score ?? 0,
        sort: "relevance",
      };

      setResumeText(decoded.r);
      setControls(decodedControls);
      setSharedBanner(true);
      void runMatch(decoded.r, decodedControls);
    }

    handleHashShare();
    window.addEventListener("hashchange", handleHashShare);
    return () => window.removeEventListener("hashchange", handleHashShare);
  }, [runMatch]);

  function dismissSharedBanner() {
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    processedHashRef.current = null;
    setSharedBanner(false);
  }

  async function copyShareLink() {
    // Encodes inputs only, never results -- see enhancements/12: the payload stays
    // small, and a shared link always reflects the current model rather than
    // freezing someone else's scores from weeks ago. Never sent to any server; the
    // fragment lives entirely in the URL bar.
    const encoded = encodeShare({
      v: 1,
      r: resumeText,
      k: controls.topK,
      n: controls.topN,
      f: controlsToFilters(controls),
    });
    const url = `${window.location.origin}${window.location.pathname}#s=${encoded}`;

    try {
      await navigator.clipboard.writeText(url);
      setShareStatus(isShareOversize(encoded) ? "oversize" : "copied");
    } catch {
      setShareStatus("error");
    }
    setTimeout(() => setShareStatus("idle"), 4000);
  }

  async function copyMarkdown() {
    try {
      await navigator.clipboard.writeText(resultsToMarkdown(results));
      setExportStatus("copied");
    } catch {
      setExportStatus("error");
    }
    setTimeout(() => setExportStatus("idle"), 4000);
  }

  function downloadJson() {
    const blob = new Blob([resultsToJson(results)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "talentrank-matches.json";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  const corpusDescription =
    health !== null ? `a ${health.corpus_size.toLocaleString()}-posting corpus` : "the job corpus";

  const isLoading = stage === "retrieving";
  const showWarming = stage === "idle" && healthState === "warming";
  const showEmptyIdle = stage === "idle" && healthState !== "warming";

  // aria-live region announcing pipeline progress and results to screen reader
  // users, who otherwise get no signal that anything happened when a match
  // completes. See enhancements/13's accessibility section.
  const liveMessage =
    stage === "error"
      ? errorMessage || "Something went wrong."
      : stage === "ranked"
        ? `${results.length} ${results.length === 1 ? "match" : "matches"} found`
        : stage === "shortlisted"
          ? "Shortlist ready, reranking with the cross-encoder"
          : stage === "retrieving"
            ? "Searching for matches"
            : "";

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

        {sharedBanner && (
          <div className="mt-3 flex items-center justify-between gap-3 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-xs text-indigo-700 dark:border-indigo-900/50 dark:bg-indigo-950/30 dark:text-indigo-300">
            <span>Viewing a shared resume. Results reflect the current model, not a frozen snapshot.</span>
            <button
              type="button"
              onClick={dismissSharedBanner}
              className="shrink-0 font-semibold underline hover:no-underline"
            >
              Start fresh
            </button>
          </div>
        )}
      </div>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <section>
          <div className="lg:sticky lg:top-6">
            <ResumeForm
              resumeText={resumeText}
              onResumeTextChange={setResumeText}
              onSubmit={() => void runMatch()}
              loading={stage === "retrieving" || stage === "shortlisted"}
              searchControls={controls}
              onSearchControlsChange={setControls}
              resultSummary={counts}
            />
          </div>
        </section>

        <section aria-busy={isLoading}>
          {/* Announces pipeline progress/results to screen readers; always mounted so
              text changes are what trigger the announcement, not mount/unmount. */}
          <div aria-live="polite" className="sr-only">
            {liveMessage}
          </div>

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

          {stage === "ranked" && results.length > 0 && (
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => void copyShareLink()}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                Copy share link
              </button>
              <button
                type="button"
                onClick={() => void copyMarkdown()}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                Copy as Markdown
              </button>
              <button
                type="button"
                onClick={downloadJson}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                Download JSON
              </button>
              {shareStatus === "copied" && (
                <span className="text-xs text-emerald-600 dark:text-emerald-400">Link copied.</span>
              )}
              {shareStatus === "oversize" && (
                <span className="text-xs text-amber-600 dark:text-amber-400">
                  Link copied, but this resume is long enough that some apps may truncate it.
                </span>
              )}
              {shareStatus === "error" && (
                <span className="text-xs text-red-600 dark:text-red-400">
                  Couldn't copy automatically -- select the URL bar after sharing manually.
                </span>
              )}
              {exportStatus === "copied" && (
                <span className="text-xs text-emerald-600 dark:text-emerald-400">Markdown copied.</span>
              )}
              {exportStatus === "error" && (
                <span className="text-xs text-red-600 dark:text-red-400">
                  Couldn't copy automatically -- your browser may be blocking clipboard access.
                </span>
              )}
            </div>
          )}

          {showWarming && <WarmingState />}
          {showEmptyIdle && <EmptyState />}
          {isLoading && <LoadingState />}
          {stage === "error" && <ErrorState message={errorMessage} onRetry={() => void runMatch()} />}
          {stage === "ranked" && results.length > 0 && <SkillGapStrip results={results} />}
          {(stage === "shortlisted" || stage === "ranked") &&
            (results.length > 0 ? <ResultsList results={results} /> : <EmptyState />)}
        </section>
      </div>
    </>
  );
}
