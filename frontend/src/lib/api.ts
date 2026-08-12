import { AUTH_EXPIRED_EVENT, type AuthUser, clearAuth, isExpired, loadAuth } from "./auth";

export interface MatchFilters {
  job_families?: string[] | null;
  min_score?: number | null;
}

export interface MatchRequestBody {
  resume_text: string;
  top_k?: number;
  top_n?: number;
  filters?: MatchFilters;
  explain?: boolean;
}

export interface ScoreBreakdown {
  bi_encoder: number;
  cross_encoder: number;
  cross_encoder_probability: number;
  skill_overlap: number;
}

export interface MatchedTerm {
  term: string;
  weight: number;
}

export interface Explanation {
  matched_skills: string[];
  missing_skills: string[];
  matched_terms: MatchedTerm[];
  overlap_score: number;
}

export interface JobMatch {
  job_id: number;
  job_title: string;
  description: string;
  skills: string;
  job_category: string;
  job_family: string;
  bi_encoder_score: number;
  cross_encoder_score: number;
  scores: ScoreBreakdown;
  explanation: Explanation | null;
  retrieval_rank: number;
  rank: number;
}

export interface MatchResponse {
  results: JobMatch[];
  stage: "retrieve" | "rerank";
  top_k: number;
  top_n: number;
  total_candidates: number;
  filtered_candidates: number;
  took_ms: number;
  cached: boolean;
  corpus_size: number;
  resume_hash: string;
  run_id: string | null;
}

export interface HealthResponse {
  status: string;
  version: string;
  device: string;
  warm: boolean;
  corpus_profile: string;
  corpus_size: number;
  index_size: number;
  bi_encoder: string;
  cross_encoder: string;
  cache_backend: string;
  uptime_seconds: number;
}

export interface JobFamilyCount {
  family: string;
  label: string;
  count: number;
}

export interface ExtractTextResponse {
  text: string;
  char_count: number;
  page_count: number | null;
  filename: string;
  truncated: boolean;
}

const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

export class ApiError extends Error {
  status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function parseErrorMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (
      body &&
      typeof body === "object" &&
      "detail" in body &&
      typeof (body as { detail: unknown }).detail === "string"
    ) {
      return (body as { detail: string }).detail;
    }
  } catch {
    // response body wasn't JSON; fall through to status text
  }
  return response.statusText || `Request failed with status ${response.status}`;
}

// A 401 from these two is about the credentials in *this* request, not about an
// existing stored session's token -- a signed-in user who mistypes a password
// while trying to sign into a *different* account must not get silently logged
// out of their current, still-valid session as a side effect. Not in
// enhancements/22's own `apiFetch` sketch, which would clear-and-dispatch on
// every 401 unconditionally; added here because that's a real, reachable bug
// (LoginPage/RegisterPage are not behind RequireAuth, so a signed-in user can
// land on them with a live session still attached to every apiFetch call).
const AUTH_ENTRY_ENDPOINTS = new Set(["/auth/login", "/auth/register"]);

/**
 * The one chokepoint every request goes through -- see enhancements/22. Attaches
 * `Authorization` when a non-expired token is stored, and treats a 401 from an
 * already-authenticated call as "the server no longer honours this token":
 * clears it and notifies the app exactly once, never retries (a 401 handler that
 * itself calls the API can loop).
 *
 * Deliberately does not set `Content-Type` here -- `extractText` posts
 * `FormData`, and the browser must be left to set the multipart boundary itself.
 * Callers that need JSON set `Content-Type` themselves, same as before this
 * wrapper existed.
 */
async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const stored = loadAuth();
  const headers = new Headers(init.headers);
  if (stored && !isExpired(stored)) headers.set("Authorization", `Bearer ${stored.token}`);

  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });

  if (response.status === 401 && stored && !AUTH_ENTRY_ENDPOINTS.has(path)) {
    clearAuth();
    window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
  }
  if (!response.ok) {
    throw new ApiError(await parseErrorMessage(response), response.status);
  }
  return response;
}

export async function checkHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await apiFetch("/health", { signal });
  return (await response.json()) as HealthResponse;
}

export async function getJobFamilies(signal?: AbortSignal): Promise<JobFamilyCount[]> {
  const response = await apiFetch("/job-families", { signal });
  return (await response.json()) as JobFamilyCount[];
}

export async function extractText(file: File, signal?: AbortSignal): Promise<ExtractTextResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await apiFetch("/extract-text", { method: "POST", body: formData, signal });

  return (await response.json()) as ExtractTextResponse;
}

export interface MatchOptions {
  topK?: number;
  topN?: number;
  filters?: MatchFilters;
  explain?: boolean;
}

async function postMatchRequest(
  path: "/match" | "/retrieve",
  resumeText: string,
  options: MatchOptions,
  signal?: AbortSignal,
): Promise<MatchResponse> {
  const body: MatchRequestBody = { resume_text: resumeText };
  if (options.topK !== undefined) body.top_k = options.topK;
  if (options.topN !== undefined) body.top_n = options.topN;
  if (options.filters !== undefined) body.filters = options.filters;
  if (options.explain !== undefined) body.explain = options.explain;

  const response = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  return (await response.json()) as MatchResponse;
}

export async function matchResume(
  resumeText: string,
  options: MatchOptions = {},
  signal?: AbortSignal,
): Promise<MatchResponse> {
  return postMatchRequest("/match", resumeText, options, signal);
}

export async function retrieveOnly(
  resumeText: string,
  options: MatchOptions = {},
  signal?: AbortSignal,
): Promise<MatchResponse> {
  return postMatchRequest("/retrieve", resumeText, options, signal);
}

// --- Auth (enhancements/22) ----------------------------------------------------

export interface SessionResponse {
  token: string;
  expires_at: string;
  user: AuthUser;
}

export async function register(email: string, password: string, displayName?: string): Promise<SessionResponse> {
  const response = await apiFetch("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, display_name: displayName }),
  });
  return (await response.json()) as SessionResponse;
}

export async function login(email: string, password: string): Promise<SessionResponse> {
  const response = await apiFetch("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return (await response.json()) as SessionResponse;
}

export async function logout(): Promise<void> {
  await apiFetch("/auth/logout", { method: "POST" });
}

export async function logoutAll(): Promise<void> {
  await apiFetch("/auth/logout-all", { method: "POST" });
}

export async function getMe(): Promise<AuthUser> {
  const response = await apiFetch("/auth/me");
  return (await response.json()) as AuthUser;
}

export async function updateMe(displayName: string | null): Promise<AuthUser> {
  const response = await apiFetch("/auth/me", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ display_name: displayName }),
  });
  return (await response.json()) as AuthUser;
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  await apiFetch("/auth/change-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}

// --- /me: history, saved lists, feedback (enhancements/23) ---------------------

export interface MatchRunSummary {
  id: string;
  label: string;
  created_at: string;
  top_k: number;
  top_n: number;
  filters: MatchFilters;
  corpus_profile: string;
  result_count: number;
  top_job_titles: string[];
}

export interface MatchRunDetail {
  id: string;
  label: string;
  resume_hash: string;
  resume_text: string;
  top_k: number;
  top_n: number;
  filters: MatchFilters;
  corpus_profile: string;
  took_ms: number;
  created_at: string;
  results: JobMatch[];
}

export interface ImportEntryPayload {
  created_at: number; // epoch ms, matching HistoryEntry.createdAt
  label: string;
  resume_text: string;
  top_k: number;
  top_n: number;
  filters: MatchFilters;
  results: JobMatch[];
}

export interface ImportResult {
  imported: number;
  skipped_duplicate: number;
  skipped_quota: number;
}

export async function getHistoryList(page = 1, signal?: AbortSignal): Promise<MatchRunSummary[]> {
  const response = await apiFetch(`/me/history?page=${page}`, { signal });
  return (await response.json()) as MatchRunSummary[];
}

export async function getHistoryDetail(runId: string, signal?: AbortSignal): Promise<MatchRunDetail> {
  const response = await apiFetch(`/me/history/${runId}`, { signal });
  return (await response.json()) as MatchRunDetail;
}

export async function renameHistoryEntry(runId: string, label: string): Promise<MatchRunDetail> {
  const response = await apiFetch(`/me/history/${runId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label }),
  });
  return (await response.json()) as MatchRunDetail;
}

export async function deleteHistoryEntry(runId: string): Promise<void> {
  await apiFetch(`/me/history/${runId}`, { method: "DELETE" });
}

export async function clearServerHistory(): Promise<void> {
  await apiFetch("/me/history", { method: "DELETE" });
}

export async function importHistory(entries: ImportEntryPayload[]): Promise<ImportResult> {
  const response = await apiFetch("/me/history/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ entries }),
  });
  return (await response.json()) as ImportResult;
}

export interface SavedListSummary {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  item_count: number;
}

export interface SavedListItemOut {
  job_id: number;
  job_title: string;
  job_family: string;
  note: string | null;
  created_at: string;
}

export interface SavedListDetail {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  items: SavedListItemOut[];
}

export async function getSavedLists(): Promise<SavedListSummary[]> {
  const response = await apiFetch("/me/lists");
  return (await response.json()) as SavedListSummary[];
}

export async function createSavedList(name: string): Promise<SavedListDetail> {
  const response = await apiFetch("/me/lists", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  return (await response.json()) as SavedListDetail;
}

export async function getSavedListDetail(listId: string): Promise<SavedListDetail> {
  const response = await apiFetch(`/me/lists/${listId}`);
  return (await response.json()) as SavedListDetail;
}

export async function renameSavedList(listId: string, name: string): Promise<SavedListDetail> {
  const response = await apiFetch(`/me/lists/${listId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  return (await response.json()) as SavedListDetail;
}

export async function deleteSavedList(listId: string): Promise<void> {
  await apiFetch(`/me/lists/${listId}`, { method: "DELETE" });
}

export async function addSavedListItem(
  listId: string,
  jobId: number,
  jobTitle: string,
  jobFamily: string,
  note?: string | null,
): Promise<SavedListItemOut> {
  const response = await apiFetch(`/me/lists/${listId}/items`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id: jobId, job_title: jobTitle, job_family: jobFamily, note: note ?? null }),
  });
  return (await response.json()) as SavedListItemOut;
}

export async function removeSavedListItem(listId: string, jobId: number): Promise<void> {
  await apiFetch(`/me/lists/${listId}/items/${jobId}`, { method: "DELETE" });
}

export type FeedbackSignal = "up" | "down" | "click";

export interface FeedbackState {
  job_id: number;
  signal: "up" | "down";
}

export interface FeedbackResult {
  id: string | null;
  action: "created" | "removed";
}

export async function getFeedbackState(runId: string, signal?: AbortSignal): Promise<FeedbackState[]> {
  const response = await apiFetch(`/me/feedback?run_id=${runId}`, { signal });
  return (await response.json()) as FeedbackState[];
}

export async function postFeedback(
  jobId: number,
  signal: FeedbackSignal,
  rank: number,
  resumeHash: string,
  runId: string | null,
): Promise<FeedbackResult> {
  const response = await apiFetch("/me/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id: jobId, signal, rank, resume_hash: resumeHash, run_id: runId }),
  });
  return (await response.json()) as FeedbackResult;
}
