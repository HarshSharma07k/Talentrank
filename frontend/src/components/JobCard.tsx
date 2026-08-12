import { useMemo, useState } from "react";
import type { JobMatch } from "../lib/api";
import { formatCategory, toAbsolutePercent } from "../lib/format";
import { ExplanationPanel } from "./ExplanationPanel";
import { FeedbackButtons } from "./FeedbackButtons";
import { HighlightedText } from "./HighlightedText";
import { SaveToListButton } from "./SaveToListButton";
import { ScoreBar } from "./ScoreBar";

const DESCRIPTION_PREVIEW_LENGTH = 260;

function RankDeltaBadge({ retrievalRank, rank }: { retrievalRank: number; rank: number }) {
  const delta = retrievalRank - rank;
  if (delta === 0) return null;

  const climbed = delta > 0;
  return (
    <span
      title={`Retrieved at #${retrievalRank}, reranked to #${rank}`}
      className={`inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
        climbed
          ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400"
          : "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-400"
      }`}
    >
      {climbed ? "▲" : "▼"}
      {Math.abs(delta)}
    </span>
  );
}

interface JobCardProps {
  job: JobMatch;
  rank: number;
  // Attached to the root <li> so ResultsList can measure it for the FLIP reorder
  // animation (enhancements/11) without a double-wrapping <li><li> layout.
  elementRef?: (element: HTMLLIElement | null) => void;
  // Identify the run this card belongs to -- required for FeedbackButtons to send
  // a well-formed request. null in contexts where there is no real run yet (the
  // pre-rerank shortlist) or the result isn't tied to one (enhancements/23).
  resumeHash?: string | null;
  runId?: string | null;
  // The signed-in caller's existing up/down signal for this job, once known --
  // see useFeedbackState. undefined while unknown/loading.
  initialFeedbackSignal?: "up" | "down";
}

export function JobCard({
  job,
  rank,
  elementRef,
  resumeHash = null,
  runId = null,
  initialFeedbackSignal,
}: JobCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [explanationOpen, setExplanationOpen] = useState(false);
  const [hoveredSkill, setHoveredSkill] = useState<string | null>(null);

  const description = job.description.trim();
  const isLong = description.length > DESCRIPTION_PREVIEW_LENGTH;
  const shownDescription =
    expanded || !isLong ? description : `${description.slice(0, DESCRIPTION_PREVIEW_LENGTH).trimEnd()}…`;

  const skills = job.skills?.trim();

  // The baseline highlight set is the IDF-weighted shared terms (enhancements/04);
  // hovering a matched skill chip in ExplanationPanel adds it on top. Works in both
  // the collapsed and expanded description states since both render through
  // HighlightedText, not a separate copy.
  const baseHighlightTerms = useMemo(
    () => job.explanation?.matched_terms.map((term) => term.term) ?? [],
    [job.explanation],
  );
  const highlightTerms = hoveredSkill ? [...baseHighlightTerms, hoveredSkill] : baseHighlightTerms;

  return (
    <li
      ref={elementRef}
      className="rounded-xl border border-slate-200 bg-white p-4 transition hover:border-slate-300 sm:p-5 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-slate-700"
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-indigo-50 text-xs font-semibold text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-400">
          {rank}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-white">{job.job_title}</h3>
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                {formatCategory(job.job_family)}
              </span>
              <RankDeltaBadge retrievalRank={job.retrieval_rank} rank={job.rank} />
            </div>

            {/* FeedbackButtons/SaveToListButton each render nothing for anonymous
                visitors themselves -- see enhancements/23's own "do not show to
                anonymous users" rule. */}
            <div className="flex shrink-0 items-center gap-1.5">
              {resumeHash && (
                <FeedbackButtons
                  jobId={job.job_id}
                  rank={job.rank}
                  resumeHash={resumeHash}
                  runId={runId}
                  initialSignal={initialFeedbackSignal}
                  expanded={explanationOpen}
                />
              )}
              <SaveToListButton jobId={job.job_id} jobTitle={job.job_title} jobFamily={job.job_family} />
            </div>
          </div>

          {skills && (
            <p className="mt-1.5 text-xs text-slate-500 dark:text-slate-400">
              <span className="font-medium text-slate-600 dark:text-slate-300">Skills: </span>
              {skills}
            </p>
          )}

          <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
            <HighlightedText text={shownDescription} terms={highlightTerms} />
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
              percent={toAbsolutePercent(job.scores.cross_encoder_probability)}
              rawValue={job.scores.cross_encoder_probability}
              colorClassName="bg-indigo-600"
            />
            <ScoreBar
              label="Semantic match"
              percent={toAbsolutePercent(job.scores.bi_encoder)}
              rawValue={job.scores.bi_encoder}
              colorClassName="bg-slate-400 dark:bg-slate-500"
            />
          </div>

          {job.explanation && (
            <ExplanationPanel
              explanation={job.explanation}
              scores={job.scores}
              onHoverMatchedSkill={setHoveredSkill}
              onToggle={setExplanationOpen}
            />
          )}
        </div>
      </div>
    </li>
  );
}
