import { describe, expect, it } from "vitest";
import type { JobMatch } from "./api";
import type { HistoryEntry } from "./history";
import { shouldOfferMigration, toImportPayload } from "./historyMigration";

function makeJobMatch(): JobMatch {
  return {
    job_id: 1,
    job_title: "Test Job",
    description: "desc",
    skills: "",
    job_category: "TEST",
    job_family: "OTHER",
    bi_encoder_score: 0.5,
    cross_encoder_score: 1.0,
    scores: { bi_encoder: 0.5, cross_encoder: 1.0, cross_encoder_probability: 0.7, skill_overlap: 0.1 },
    explanation: null,
    retrieval_rank: 1,
    rank: 1,
  };
}

function makeEntry(overrides: Partial<HistoryEntry> = {}): HistoryEntry {
  return {
    id: "a",
    createdAt: 1_700_000_000_000,
    label: "Entry a",
    resumeText: "some resume text",
    topK: 30,
    topN: 10,
    filters: { job_families: null, min_score: null },
    results: [makeJobMatch()],
    ...overrides,
  };
}

describe("shouldOfferMigration", () => {
  it("should_offer_when_entries_exist_and_flag_unset", () => {
    expect(shouldOfferMigration([makeEntry()], null)).toBe(true);
  });

  it("should_not_offer_when_flag_set", () => {
    expect(shouldOfferMigration([makeEntry()], "1")).toBe(false);
  });

  it("should_not_offer_when_local_history_empty", () => {
    expect(shouldOfferMigration([], null)).toBe(false);
  });
});

describe("toImportPayload", () => {
  it("payload_preserves_created_at", () => {
    const entries = [makeEntry({ createdAt: 1_650_000_000_000 })];
    const payload = toImportPayload(entries);
    expect(payload[0].created_at).toBe(1_650_000_000_000);
  });

  it("payload_survives_unicode_and_emoji_in_resume_text", () => {
    const resumeText = "Café résumé writer 🚀 with naïve enthusiasm — 日本語 also present.";
    const entries = [makeEntry({ resumeText })];
    const payload = toImportPayload(entries);
    const roundtripped = JSON.parse(JSON.stringify(payload)) as typeof payload;
    expect(roundtripped[0].resume_text).toBe(resumeText);
  });

  it("maps every field to its snake_case counterpart", () => {
    const entries = [makeEntry({ topK: 25, topN: 8, label: "My run" })];
    const payload = toImportPayload(entries);
    expect(payload[0]).toEqual({
      created_at: entries[0].createdAt,
      label: "My run",
      resume_text: entries[0].resumeText,
      top_k: 25,
      top_n: 8,
      filters: entries[0].filters,
      results: entries[0].results,
    });
  });
});
