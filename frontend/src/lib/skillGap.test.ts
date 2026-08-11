import { describe, expect, it } from "vitest";
import type { JobMatch } from "./api";
import { aggregateSkillGaps } from "./skillGap";

function job(overrides: Partial<JobMatch> = {}): JobMatch {
  return {
    job_id: 1,
    job_title: "Registered Nurse",
    description: "",
    skills: "",
    job_category: "REGISTERED NURSE",
    job_family: "HEALTHCARE",
    bi_encoder_score: 0.5,
    cross_encoder_score: 0.5,
    scores: { bi_encoder: 0.5, cross_encoder: 0.5, cross_encoder_probability: 0.6, skill_overlap: 0.3 },
    explanation: null,
    retrieval_rank: 1,
    rank: 1,
    ...overrides,
  };
}

function withMissing(missingSkills: string[], rank: number): JobMatch {
  return job({
    rank,
    explanation: { matched_skills: [], missing_skills: missingSkills, matched_terms: [], overlap_score: 0 },
  });
}

describe("aggregateSkillGaps", () => {
  it("counts frequency across results and sorts descending", () => {
    const results = [
      withMissing(["ACLS", "BLS"], 1),
      withMissing(["ACLS"], 2),
      withMissing(["ACLS", "ICU"], 3),
    ];
    expect(aggregateSkillGaps(results)).toEqual([
      { skill: "ACLS", count: 3 },
      { skill: "BLS", count: 1 },
      { skill: "ICU", count: 1 },
    ]);
  });

  it("ignores results with no explanation (retrieve-stage)", () => {
    const results = [job({ rank: 1, explanation: null }), withMissing(["Python"], 2)];
    expect(aggregateSkillGaps(results)).toEqual([{ skill: "Python", count: 1 }]);
  });

  it("returns empty when nothing is missing anywhere", () => {
    const results = [
      job({ rank: 1, explanation: { matched_skills: ["ACLS"], missing_skills: [], matched_terms: [], overlap_score: 1 } }),
    ];
    expect(aggregateSkillGaps(results)).toEqual([]);
  });

  it("only samples the first sampleSize results, not the whole list", () => {
    const results = [withMissing(["A"], 1), withMissing(["B"], 2)];
    expect(aggregateSkillGaps(results, 1)).toEqual([{ skill: "A", count: 1 }]);
  });

  it("caps output at maxShown, keeping the highest counts", () => {
    const results = [withMissing(["A", "B", "C"], 1), withMissing(["A", "B"], 2), withMissing(["A"], 3)];
    expect(aggregateSkillGaps(results, 10, 2)).toEqual([
      { skill: "A", count: 3 },
      { skill: "B", count: 2 },
    ]);
  });
});
