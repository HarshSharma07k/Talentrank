import {
  clearServerHistory,
  deleteHistoryEntry,
  getHistoryDetail,
  getHistoryList,
  type JobMatch,
  type MatchRunDetail,
  type MatchRunSummary,
  renameHistoryEntry,
} from "./api";
import type { HistoryEntry } from "./history";

/**
 * The server-backed implementation of the history operations, for signed-in
 * users. See enhancements/23. `useHistory.ts` is the facade that picks between
 * this and `history.ts` based on auth state -- this module never touches
 * `localStorage` itself.
 *
 * `GET /me/history` returns `MatchRunSummary`, which omits `results` by design
 * (enhancements/21: a list view eagerly serialising twenty runs x ten results
 * each is a slow endpoint nobody's list view renders). `summaryToEntry` below
 * fills `HistoryEntry.results` with placeholder rows sized to `result_count` --
 * enough for `entries.length`/`results.length` (list-row "N results" display) to
 * be correct, using `top_job_titles` for whatever titles the summary actually
 * carries. These placeholders are not real match data (zeroed scores, no
 * description, synthetic negative `job_id`) and must never be fed to
 * `ComparePage`'s diff or `JobCard` -- callers that need real results call
 * `fetchDetail` instead, which returns the server's actual stored payload.
 */

const PLACEHOLDER_JOB_ID_BASE = -1;

function placeholderResult(title: string, index: number): JobMatch {
  return {
    job_id: PLACEHOLDER_JOB_ID_BASE - index,
    job_title: title,
    description: "",
    skills: "",
    job_category: "",
    job_family: "",
    bi_encoder_score: 0,
    cross_encoder_score: 0,
    scores: { bi_encoder: 0, cross_encoder: 0, cross_encoder_probability: 0, skill_overlap: 0 },
    explanation: null,
    retrieval_rank: index + 1,
    rank: index + 1,
  };
}

function summaryToEntry(row: MatchRunSummary): HistoryEntry {
  return {
    id: row.id,
    createdAt: new Date(row.created_at).getTime(),
    label: row.label,
    resumeText: "", // not in the summary -- fetchDetail() is required before this is needed
    topK: row.top_k,
    topN: row.top_n,
    filters: row.filters,
    results: Array.from({ length: row.result_count }, (_, i) => placeholderResult(row.top_job_titles[i] ?? "", i)),
  };
}

function detailToEntry(row: MatchRunDetail): HistoryEntry {
  return {
    id: row.id,
    createdAt: new Date(row.created_at).getTime(),
    label: row.label,
    resumeText: row.resume_text,
    topK: row.top_k,
    topN: row.top_n,
    filters: row.filters,
    results: row.results,
  };
}

export async function fetchEntries(signal?: AbortSignal): Promise<HistoryEntry[]> {
  const summaries = await getHistoryList(1, signal);
  return summaries.map(summaryToEntry);
}

export interface HistoryDetail extends HistoryEntry {
  /** Which corpus this run was matched against -- not part of `HistoryEntry`
   * itself (local entries never tracked it; a single anonymous deployment is
   * always one profile). `ComparePage` uses this to refuse to diff two runs from
   * different corpora rather than silently comparing incomparable job pools. */
  corpusProfile: string | null;
  /** `MatchResponse.resume_hash` for this run -- also not part of `HistoryEntry`
   * (local storage never tracked it either). `null` for local entries; required by
   * `FeedbackButtons`/`SaveToListButton` when `ComparePage` renders a `JobCard` for
   * a signed-in user's server-backed run. */
  resumeHash: string | null;
}

/** The real, full-fidelity entry (real `resumeText`, real `results`) -- fetched
 * lazily, only when a caller (viewing a past run, or `ComparePage` diffing two)
 * actually needs it, per enhancements/23's own contract. */
export async function fetchDetail(id: string, signal?: AbortSignal): Promise<HistoryDetail | null> {
  try {
    const detail = await getHistoryDetail(id, signal);
    return { ...detailToEntry(detail), corpusProfile: detail.corpus_profile, resumeHash: detail.resume_hash };
  } catch {
    return null;
  }
}

export async function rename(id: string, label: string): Promise<void> {
  await renameHistoryEntry(id, label);
}

export async function remove(id: string): Promise<void> {
  await deleteHistoryEntry(id);
}

export async function clear(): Promise<void> {
  await clearServerHistory();
}
