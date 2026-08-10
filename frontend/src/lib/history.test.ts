import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { JobMatch } from "./api";
import {
  clearHistory,
  type HistoryEntry,
  loadHistory,
  MAX_HISTORY_ENTRIES,
  removeEntry,
  renameEntry,
  saveEntry,
  STORAGE_KEY,
} from "./history";

function makeEntry(id: string, results: JobMatch[] = []): HistoryEntry {
  return {
    id,
    createdAt: Date.now(),
    label: `Entry ${id}`,
    resumeText: "some resume text",
    topK: 30,
    topN: 10,
    filters: {},
    results,
  };
}

function makeJobMatch(description: string): JobMatch {
  return {
    job_id: 1,
    job_title: "Test Job",
    description,
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

beforeEach(() => {
  localStorage.clear();
});

// A test that throws partway through its own assertions would otherwise leave a
// mocked Storage.prototype.setItem in place for every test that runs after it --
// this is what actually broke version_mismatch_discards_cleanly the first time
// this suite was written, since the previous test's failed assertion happened
// before its own mockRestore() call. Always-restore regardless of pass/fail.
afterEach(() => {
  vi.restoreAllMocks();
});

describe("history", () => {
  it("prunes_to_cap", () => {
    let entries: HistoryEntry[] = [];
    for (let i = 0; i < MAX_HISTORY_ENTRIES + 5; i++) {
      entries = saveEntry(entries, makeEntry(String(i)));
    }
    expect(entries.length).toBe(MAX_HISTORY_ENTRIES);
    // Newest-first: the most recently added entry is first, the oldest were pruned.
    expect(entries[0].id).toBe(String(MAX_HISTORY_ENTRIES + 4));
    expect(loadHistory().length).toBe(MAX_HISTORY_ENTRIES);
  });

  it("quota_exceeded_drops_oldest_and_retries_once", () => {
    let stored: HistoryEntry[] = [];
    stored = saveEntry(stored, makeEntry("a"));
    stored = saveEntry(stored, makeEntry("b"));
    stored = saveEntry(stored, makeEntry("c"));
    expect(stored.map((e) => e.id)).toEqual(["c", "b", "a"]);

    const setItemSpy = vi.spyOn(Storage.prototype, "setItem").mockImplementationOnce(() => {
      throw new DOMException("The quota has been exceeded.", "QuotaExceededError");
    });

    const afterAdd = saveEntry(stored, makeEntry("d"));

    // First attempt (4 entries) failed; the retry (oldest of the attempted set
    // dropped, 3 entries) succeeded via the real implementation.
    expect(afterAdd.map((e) => e.id)).toEqual(["d", "c", "b"]);
    expect(setItemSpy).toHaveBeenCalledTimes(2);

    setItemSpy.mockRestore();
  });

  it("quota_exceeded gives up silently once the retry also fails", () => {
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("nope", "QuotaExceededError");
    });

    let result: HistoryEntry[] = [];
    expect(() => {
      result = saveEntry([], makeEntry("a"));
    }).not.toThrow();

    expect(result.map((e) => e.id)).toEqual(["a"]); // best-effort in-memory result
    expect(setItemSpy).toHaveBeenCalledTimes(2);
  });

  it("version_mismatch_discards_cleanly", () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 2, entries: [makeEntry("a")] }));
    expect(loadHistory()).toEqual([]);
  });

  it("version_mismatch_discards_cleanly: malformed JSON never throws", () => {
    localStorage.setItem(STORAGE_KEY, "{not valid json");
    expect(() => loadHistory()).not.toThrow();
    expect(loadHistory()).toEqual([]);
  });

  it("saveEntry trims description before storing", () => {
    const entry = makeEntry("a", [makeJobMatch("x".repeat(2000))]);

    const saved = saveEntry([], entry);

    expect(saved[0].results[0].description.length).toBeLessThanOrEqual(400);
    expect(saved[0].results[0].description.length).toBeLessThan(2000);
  });

  it("removeEntry, renameEntry, clearHistory", () => {
    let entries = saveEntry([], makeEntry("a"));
    entries = saveEntry(entries, makeEntry("b"));

    entries = renameEntry(entries, "a", "Renamed");
    expect(entries.find((e) => e.id === "a")?.label).toBe("Renamed");

    entries = removeEntry(entries, "b");
    expect(entries.map((e) => e.id)).toEqual(["a"]);

    entries = clearHistory();
    expect(entries).toEqual([]);
    expect(loadHistory()).toEqual([]);
  });
});
