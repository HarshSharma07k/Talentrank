import type { JobMatch } from "./api";

/**
 * Aggregates `explanation.missing_skills` across a resume's top matches -- the
 * skill-gap summary strip (enhancements/13, item 1). Pure so it's directly
 * testable without mounting the component. `explanation` is `null` for
 * `/retrieve`-stage results (no explain pass has run yet), so those contribute
 * nothing rather than throwing.
 */
export interface SkillGap {
  skill: string;
  count: number;
}

export const SKILL_GAP_SAMPLE_SIZE = 10;
export const SKILL_GAP_MAX_SHOWN = 8;

export function aggregateSkillGaps(
  results: JobMatch[],
  sampleSize: number = SKILL_GAP_SAMPLE_SIZE,
  maxShown: number = SKILL_GAP_MAX_SHOWN,
): SkillGap[] {
  const counts = new Map<string, number>();

  for (const job of results.slice(0, sampleSize)) {
    for (const skill of job.explanation?.missing_skills ?? []) {
      counts.set(skill, (counts.get(skill) ?? 0) + 1);
    }
  }

  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, maxShown)
    .map(([skill, count]) => ({ skill, count }));
}
