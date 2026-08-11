import { useMemo } from "react";
import type { JobMatch } from "../lib/api";
import { aggregateSkillGaps, SKILL_GAP_SAMPLE_SIZE } from "../lib/skillGap";

// Zero backend work: a client-side aggregate over explanation.missing_skills
// already returned on every reranked result. See enhancements/13, item 1.
export function SkillGapStrip({ results }: { results: JobMatch[] }) {
  const gaps = useMemo(() => aggregateSkillGaps(results), [results]);
  const sampleSize = Math.min(results.length, SKILL_GAP_SAMPLE_SIZE);

  if (gaps.length === 0) return null;

  return (
    <div className="mb-4 rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-900/60">
      <p className="text-xs font-medium text-slate-600 dark:text-slate-300">
        Across your top {sampleSize} matches, these skills appear most often and are missing from your
        resume:
      </p>
      <ul className="mt-2 flex flex-wrap gap-1.5">
        {gaps.map(({ skill, count }) => (
          <li
            key={skill}
            className="inline-flex items-center gap-1 rounded-full border border-dashed border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-600 dark:border-slate-600 dark:text-slate-300"
          >
            {skill}
            <span className="text-slate-400 dark:text-slate-500">×{count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
