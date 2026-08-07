import { useState } from "react";
import type { JobMatch } from "../lib/api";
import { formatCategory, normalizeScore } from "../lib/format";
import { ScoreBar } from "./ScoreBar";

interface JobCardProps {
  job: JobMatch;
  rank: number;
  biScoreRange: [number, number];
  crossScoreRange: [number, number];
}

const DESCRIPTION_PREVIEW_LENGTH = 260;

export function JobCard({ job, rank, biScoreRange, crossScoreRange }: JobCardProps) {
  const [expanded, setExpanded] = useState(false);

  const description = job.description.trim();
  const isLong = description.length > DESCRIPTION_PREVIEW_LENGTH;
  const shownDescription =
    expanded || !isLong ? description : `${description.slice(0, DESCRIPTION_PREVIEW_LENGTH).trimEnd()}…`;

  const skills = job.skills?.trim();

  return (
    <li className="rounded-xl border border-slate-200 bg-white p-4 transition hover:border-slate-300 sm:p-5 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-slate-700">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-indigo-50 text-xs font-semibold text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-400">
          {rank}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-white">{job.job_title}</h3>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
              {formatCategory(job.job_category)}
            </span>
          </div>

          {skills && (
            <p className="mt-1.5 text-xs text-slate-500 dark:text-slate-400">
              <span className="font-medium text-slate-600 dark:text-slate-300">Skills: </span>
              {skills}
            </p>
          )}

          <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
            {shownDescription}
            {isLong && (
              <button
                type="button"
                onClick={() => setExpanded((value) => !value)}
                className="ml-1.5 font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400 dark:hover:text-indigo-300"
              >
                {expanded ? "Show less" : "Read more"}
              </button>
            )}
          </p>

          <div className="mt-3 space-y-1.5">
            <ScoreBar
              label="Relevance"
              percent={normalizeScore(job.cross_encoder_score, crossScoreRange[0], crossScoreRange[1])}
              rawValue={job.cross_encoder_score}
              colorClassName="bg-indigo-600"
            />
            <ScoreBar
              label="Semantic match"
              percent={normalizeScore(job.bi_encoder_score, biScoreRange[0], biScoreRange[1])}
              rawValue={job.bi_encoder_score}
              colorClassName="bg-slate-400 dark:bg-slate-500"
            />
          </div>
        </div>
      </div>
    </li>
  );
}
