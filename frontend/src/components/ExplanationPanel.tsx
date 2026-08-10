import { useId, useState } from "react";
import type { Explanation, ScoreBreakdown as ScoreBreakdownData } from "../lib/api";
import { ScoreBreakdown } from "./ScoreBreakdown";
import { SkillChips } from "./SkillChips";

interface ExplanationPanelProps {
  explanation: Explanation;
  scores: ScoreBreakdownData;
  onHoverMatchedSkill: (skill: string | null) => void;
}

// Collapsed by default, disclosed by "Why this match?" -- the ranking stays purely
// the cross-encoder's; this panel is the separate, honest evidence layer next to it.
// See enhancements/04's Do-NOT on blending a composite score.
export function ExplanationPanel({ explanation, scores, onHoverMatchedSkill }: ExplanationPanelProps) {
  const [open, setOpen] = useState(false);
  const panelId = useId();

  return (
    <div className="mt-3 border-t border-slate-100 pt-3 dark:border-slate-800/60">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls={panelId}
        className="flex items-center gap-1.5 text-xs font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400 dark:hover:text-indigo-300"
      >
        <svg viewBox="0 0 24 24" fill="none" className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-90" : ""}`}>
          <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        Why this match?
      </button>

      {open && (
        <div id={panelId} className="mt-3 space-y-4">
          <ScoreBreakdown scores={scores} />
          <SkillChips
            matchedSkills={explanation.matched_skills}
            missingSkills={explanation.missing_skills}
            onHoverMatchedSkill={onHoverMatchedSkill}
          />
        </div>
      )}
    </div>
  );
}
