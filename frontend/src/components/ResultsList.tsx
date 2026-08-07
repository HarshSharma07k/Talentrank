import type { JobMatch } from "../lib/api";
import { JobCard } from "./JobCard";

function scoreRange(values: number[]): [number, number] {
  if (values.length === 0) return [0, 1];
  return [Math.min(...values), Math.max(...values)];
}

export function ResultsList({ results }: { results: JobMatch[] }) {
  const biScoreRange = scoreRange(results.map((job) => job.bi_encoder_score));
  const crossScoreRange = scoreRange(results.map((job) => job.cross_encoder_score));

  return (
    <ul className="space-y-3">
      {results.map((job, index) => (
        <JobCard
          key={job.job_id}
          job={job}
          rank={index + 1}
          biScoreRange={biScoreRange}
          crossScoreRange={crossScoreRange}
        />
      ))}
    </ul>
  );
}
