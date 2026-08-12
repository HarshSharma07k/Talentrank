import { useLayoutEffect, useRef } from "react";
import { useOutletContext } from "react-router";
import { useFeedbackState } from "../hooks/useFeedbackState";
import type { RootLayoutContext } from "../layouts/RootLayout";
import type { JobMatch } from "../lib/api";
import { captureRects, playFlip, type Rect } from "../lib/flip";
import { JobCard } from "./JobCard";

interface ResultsListProps {
  results: JobMatch[];
  // Identify the run these results came from -- passed through to JobCard so
  // FeedbackButtons/SaveToListButton can send a well-formed request. null while
  // the shortlist is showing pre-rerank results (retrieval only, not a real run).
  resumeHash?: string | null;
  runId?: string | null;
}

export function ResultsList({ results, resumeHash = null, runId = null }: ResultsListProps) {
  const { auth } = useOutletContext<RootLayoutContext>();
  const feedbackState = useFeedbackState(auth.status === "authenticated", runId);
  const elementsRef = useRef(new Map<string, HTMLLIElement>());
  const previousRectsRef = useRef<Map<string, Rect>>(new Map());

  // Runs after every commit that changes `results` (e.g. the rerank stage replacing
  // the shortlist, or a client-side sort). Plays the reorder from whatever position
  // each surviving card held a moment ago to its new one.
  useLayoutEffect(() => {
    playFlip(elementsRef.current, previousRectsRef.current);
    previousRectsRef.current = captureRects(elementsRef.current);
  }, [results]);

  return (
    <ul className="space-y-3">
      {results.map((job, index) => (
        <JobCard
          key={job.job_id}
          job={job}
          rank={index + 1}
          resumeHash={resumeHash}
          runId={runId}
          initialFeedbackSignal={feedbackState.get(job.job_id)}
          elementRef={(element) => {
            const key = String(job.job_id);
            if (element) elementsRef.current.set(key, element);
            else elementsRef.current.delete(key);
          }}
        />
      ))}
    </ul>
  );
}
