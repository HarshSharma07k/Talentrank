import type { ScoreBreakdown as ScoreBreakdownData } from "../lib/api";
import { toAbsolutePercent } from "../lib/format";
import { ScoreBar } from "./ScoreBar";

// No new bar component -- reuses ScoreBar three times. skill_overlap already equals
// explanation.overlap_score when explain=true (and 0 otherwise), so this only needs
// `scores`, not a separate explanation prop. See enhancements/11's score table.
export function ScoreBreakdown({ scores }: { scores: ScoreBreakdownData }) {
  return (
    <div className="space-y-1.5">
      <ScoreBar
        label="Relevance"
        percent={toAbsolutePercent(scores.cross_encoder_probability)}
        rawValue={scores.cross_encoder_probability}
        colorClassName="bg-indigo-600"
      />
      <ScoreBar
        label="Semantic match"
        percent={toAbsolutePercent(scores.bi_encoder)}
        rawValue={scores.bi_encoder}
        colorClassName="bg-slate-400 dark:bg-slate-500"
      />
      <ScoreBar
        label="Skill coverage"
        percent={toAbsolutePercent(scores.skill_overlap)}
        rawValue={scores.skill_overlap}
        colorClassName="bg-emerald-500"
      />
    </div>
  );
}
