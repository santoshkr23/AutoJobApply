/**
 * Thin fetch wrapper for the FastAPI backend (proxied at /api on the same origin).
 * Authentication uses HttpOnly cookies; unsafe requests echo the CSRF cookie in X-CSRF-Token.
 */

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

function readCookie(name: string): string {
  if (typeof document === "undefined") return "";
  const m = document.cookie.match(new RegExp("(?:^|; )" + name.replace(/[.$?*|{}()[\]\\/+^]/g, "\\$&") + "=([^;]*)"));
  return m ? decodeURIComponent(m[1]) : "";
}

type Opts = { method?: string; body?: unknown; form?: FormData; admin?: boolean; signal?: AbortSignal };

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  const method = opts.method ?? (opts.body || opts.form ? "POST" : "GET");
  const headers: Record<string, string> = {};
  if (method !== "GET") headers["X-CSRF-Token"] = readCookie(opts.admin ? "admin_csrf" : "csrf");
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { method, headers, body, credentials: "same-origin", signal: opts.signal });
  } catch {
    throw new ApiError(0, "network_error", "Cannot reach the server. Check your connection and try again.");
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") ?? "";
  const data = ct.includes("application/json") ? await res.json().catch(() => null) : null;
  if (!res.ok) {
    const err = (data as any)?.error;
    const detail = (data as any)?.detail;
    const message = err?.message ?? (Array.isArray(detail) ? detail.map((d: any) => d.msg).join("; ") : detail) ?? `Request failed (${res.status})`;
    throw new ApiError(res.status, err?.code ?? "error", message, err?.details);
  }
  return data as T;
}

export const adminApi = <T = any>(path: string, opts: Opts = {}) => api<T>(`/admin${path}`, { ...opts, admin: true });

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : "Something went wrong";
}

/** Types shared with the backend responses (only the fields the UI reads). */
export type User = {
  id: string; email: string; full_name: string | null; email_verified: boolean; onboarding_step: number;
  onboarding_completed: boolean; has_password: boolean; plan: string; created_at: string;
};
export type Job = {
  id: string; title: string; company: string; location_text: string | null; country: string | null; work_mode: string | null;
  salary_min: number | null; salary_max: number | null; salary_currency: string | null; salary_period: string | null;
  skills: string[]; url: string; source: string; attribution: string | null; is_sample: boolean; match_score: number | null;
  posted_at: string | null; employment_type: string | null; category: string | null;
};
export type Match = {
  id: string; score: number; status: string; recommendation: string; skills_matched: string[]; missing_skills: string[];
  explanation: string; location_match: any; salary_match: any; experience_match: any; job: Job;
};
export type Page<T> = { items: T[]; total: number; page: number; page_size: number };
export type AppRow = {
  id: string; job_id: string; status: string; title: string; company: string; location: string | null; job_url: string;
  source: string; match_score: number | null; needs_user_action: boolean; approved: boolean; failure_code: string | null;
  failure_reason: string | null; attempts: number; submitted_at: string | null; confirmation_ref: string | null;
  notes: string | null; interview_at: string | null; created_at: string; updated_at: string; is_sample: boolean;
};
