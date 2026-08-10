interface SkillChipsProps {
  matchedSkills: string[];
  missingSkills: string[];
  onHoverMatchedSkill: (skill: string | null) => void;
}

export function SkillChips({ matchedSkills, missingSkills, onHoverMatchedSkill }: SkillChipsProps) {
  if (matchedSkills.length === 0 && missingSkills.length === 0) {
    return <p className="text-xs text-slate-400 dark:text-slate-500">No skills detected for this posting.</p>;
  }

  return (
    <div className="space-y-3">
      {matchedSkills.length > 0 && (
        <div>
          <p className="mb-1.5 text-xs font-medium text-slate-500 dark:text-slate-400">Matched skills</p>
          <div className="flex flex-wrap gap-1.5">
            {matchedSkills.map((skill) => (
              <button
                key={skill}
                type="button"
                onMouseEnter={() => onHoverMatchedSkill(skill)}
                onMouseLeave={() => onHoverMatchedSkill(null)}
                onFocus={() => onHoverMatchedSkill(skill)}
                onBlur={() => onHoverMatchedSkill(null)}
                className="rounded-full bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white transition hover:bg-indigo-500"
              >
                {skill}
              </button>
            ))}
          </div>
        </div>
      )}

      {missingSkills.length > 0 && (
        <div>
          <p className="mb-1.5 text-xs font-medium text-slate-500 dark:text-slate-400">This role also asks for</p>
          <div className="flex flex-wrap gap-1.5">
            {missingSkills.map((skill) => (
              <span
                key={skill}
                className="rounded-full border border-dashed border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-500 dark:border-slate-600 dark:text-slate-400"
              >
                {skill}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
