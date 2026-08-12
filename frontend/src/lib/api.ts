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

export async function checkHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/health`, { signal });
  if (!response.ok) {
    throw new ApiError(await parseErrorMessage(response), response.status);
  }
  return (await response.json()) as HealthResponse;
}

export async function getJobFamilies(signal?: AbortSignal): Promise<JobFamilyCount[]> {
  const response = await fetch(`${API_BASE_URL}/job-families`, { signal });
  if (!response.ok) {
    throw new ApiError(await parseErrorMessage(response), response.status);
  }
  return (await response.json()) as JobFamilyCount[];
}

export async function extractText(file: File, signal?: AbortSignal): Promise<ExtractTextResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/extract-text`, {
    method: "POST",
    body: formData,
    signal,
  });

  if (!response.ok) {
    throw new ApiError(await parseErrorMessage(response), response.status);
  }

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

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    throw new ApiError(await parseErrorMessage(response), response.status);
  }

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
