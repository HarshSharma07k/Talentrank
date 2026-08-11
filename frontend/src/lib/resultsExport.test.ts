import { describe, expect, it } from "vitest";
import type { JobMatch } from "./api";
import { resultsToJson, resultsToMarkdown } from "./resultsExport";

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
    scores: { bi_encoder: 0.812, cross_encoder: 0.5, cross_encoder_probability: 0.734, skill_overlap: 0.3 },
    explanation: null,
    retrieval_rank: 1,
    rank: 1,
    ...overrides,
  };
}

describe("resultsToMarkdown", () => {
  it("renders a header, divider, and one row per result", () => {
    const table = resultsToMarkdown([job()]);
    const lines = table.split("\n");
    expect(lines[0]).toBe("| Rank | Job title | Family | Relevance | Semantic match |");
    expect(lines[1]).toBe("|---|---|---|---|---|");
    expect(lines[2]).toBe("| 1 | Registered Nurse | Healthcare | 73.4% | 81.2% |");
  });

  it("escapes pipe characters and strips newlines in titles", () => {
    const table = resultsToMarkdown([job({ job_title: "Nurse | ICU\nNight shift" })]);
    expect(table).toContain("Nurse \\| ICU Night shift");
  });

  it("returns just header and divider for an empty result set", () => {
    expect(resultsToMarkdown([]).split("\n")).toHaveLength(2);
  });
});

describe("resultsToJson", () => {
  it("round-trips the exact result array", () => {
    const results = [job(), job({ job_id: 2, rank: 2 })];
    expect(JSON.parse(resultsToJson(results))).toEqual(results);
  });
});
