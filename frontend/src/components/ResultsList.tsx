import { useLayoutEffect, useRef } from "react";
import type { JobMatch } from "../lib/api";
import { captureRects, playFlip, type Rect } from "../lib/flip";
import { JobCard } from "./JobCard";

export function ResultsList({ results }: { results: JobMatch[] }) {
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
