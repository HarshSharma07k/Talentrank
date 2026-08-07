export interface JobMatch {
  job_id: number;
  job_title: string;
  description: string;
  skills: string;
  job_category: string;
  bi_encoder_score: number;
  cross_encoder_score: number;
}

export interface HealthStatus {
  status: string;
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

export async function checkHealth(signal?: AbortSignal): Promise<HealthStatus> {
  const response = await fetch(`${API_BASE_URL}/health`, { signal });
  if (!response.ok) {
    throw new ApiError(await parseErrorMessage(response), response.status);
  }
  return (await response.json()) as HealthStatus;
}

export async function matchResume(
  resumeText: string,
  signal?: AbortSignal,
): Promise<JobMatch[]> {
  const response = await fetch(`${API_BASE_URL}/match`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resume_text: resumeText }),
    signal,
  });

  if (!response.ok) {
    throw new ApiError(await parseErrorMessage(response), response.status);
  }

  return (await response.json()) as JobMatch[];
}
