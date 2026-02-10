export type ApiError = { error: string; [k: string]: unknown };

const configuredBase = (process.env.NEXT_PUBLIC_QVANTIFY_BASE_URL || "").replace(/\/$/, "");
const runtimeBase = typeof window === "undefined" ? "" : window.location.origin;
const apiBase = configuredBase || runtimeBase;

function resolveApiUrl(path: string) {
  if (/^https?:\/\//i.test(path)) return path;
  if (!apiBase) return path;
  if (path.startsWith("/")) return `${apiBase}${path}`;
  return `${apiBase}/${path}`;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(resolveApiUrl(path), {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    ...init,
  });

  const text = await res.text();
  const data = text ? (JSON.parse(text) as unknown) : null;

  if (!res.ok) {
    const err = (data && typeof data === "object" ? data : { error: res.statusText }) as ApiError;
    throw new Error(err.error || res.statusText);
  }

  return data as T;
}

export type AdminProject = {
  id: string;
  name: string | null;
  session_count: number;
  last_activity_at: string | null;
};

export interface AdminUsageTotals {
  total: number;
  interviews: number;
  summary: number;
  audio?: number;
  other?: number;
}

export interface AdminUsageTotalsUsd {
  total: number;
  interviews: number;
  summary: number;
  audio?: number;
  other?: number;
}

export interface AdminUsageService {
  service: string;
  tokens: number;
}

export interface AdminProjectUsageResponse {
  project: { id: string };
  totals: AdminUsageTotals;
  totals_usd?: AdminUsageTotalsUsd;
  rate_usd_per_1k?: number;
  rate_usd_per_1k_audio?: number;
  services: AdminUsageService[];
}

export type SessionListItem = {
  id: string;
  created_at: string | null;
  external_id: string | null;
  persona_label: string | null;
  findings_summary: string | null;
  match_snippet?: string | null;
  answer_count: number;
  last_activity_at: string | null;
  is_closed: boolean;
  admin_like?: number;
  admin_note?: string | null;
  audio_tokens?: number;
  audio_message_count?: number;
};

export type AdminProjectsResponse = { projects: AdminProject[] };
export type SessionsResponse = { total: number; sessions: SessionListItem[]; project?: { id: string } };
export type AdminProjectDetail = {
  id: string;
  name: string | null;
  logo?: string | null;
  colour?: string | null;
  welcome_title?: string | null;
  welcome_message?: string | null;
  success_title?: string | null;
  success_message?: string | null;
  abort_title?: string | null;
  abort_message?: string | null;
  welcome_second_title?: string | null;
  welcome_second_message?: string | null;
  consent?: string | null;
  cta_next?: string | null;
  cta_reply?: string | null;
  cta_abort?: string | null;
  cta_restart?: string | null;
  question_title?: string | null;
  answer_title?: string | null;
  answer_placeholder?: string | null;
  loading?: string | null;
  collect_email?: boolean | null;
  email_title?: string | null;
  email_placeholder?: string | null;
  consent_link?: string | null;
  skip_welcome?: boolean | null;
  dark_mode?: boolean | null;
  inline_consent?: boolean | null;
  voice_enabled?: boolean | null;
  model?: string | null;
  temperature?: number | null;
  max_tokens?: number | null;
  top_p?: number | null;
  api?: string | null;
  default_prompt?: string | null;
};
export interface AdminTopic {
  id: string | null;
  project: string | null;
  title?: string | null;
  system: string | null;
  group?: string | null;
  length: number | null;
  sequence: number | null;
  topic_type: string | null;
  expiration_strategy: string | null;
  defined_answers: unknown;
}

export interface AdminTopicLog {
  id: number | null;
  topic_id: string | null;
  user_id: string | null;
  started_at: string | null;
  status: number | null;
  responses: number | null;
}

export interface AdminTopicsResponse {
  topics: AdminTopic[];
}

export interface AdminTopicLogsResponse {
  logs: AdminTopicLog[];
}

export type AdminProjectResponse = { project: AdminProjectDetail };
export type AdminProjectUpdateResponse = { ok: true; project: { id: string; voice_enabled: boolean } };
export type ShareLink = {
  id: string;
  label: string | null;
  allowed_exports: boolean;
  created_at: string | null;
  revoked_at: string | null;
  expires_at: string | null;
  last_used_at: string | null;
  status: "active" | "revoked" | "expired";
  share_url: string | null;
  share_path: string | null;
  password: string | null;
};

export type SessionDetail = {
  session: {
    id: string;
    created_at: string | null;
    external_id?: string | null;
    email?: string | null;
    consent?: boolean | null;
    persona_label: string | null;
    findings_summary: string | null;
    admin_like?: number;
    admin_note?: string | null;
    analyzed_at?: string | null;
    answer_count?: number;
    last_activity_at?: string | null;
    is_closed?: boolean;
  };
  records: Array<{
    id: string;
    created_at: string | null;
    role: "user" | "assistant" | "system";
    content: string;
    topic: string | null;
    topic_label?: string | null;
    topic_group?: string | null;
    admin_like?: number;
    admin_note?: string | null;
    voice_input?: boolean;
    audio_tokens?: number;
  }>;
  project?: { id: string; name?: string | null } | null;
};

export async function adminListProjects() {
  return apiFetch<AdminProjectsResponse>("/api/projects");
}

export async function adminGetProject(projectId: string) {
  return apiFetch<AdminProjectResponse>(`/api/projects/${encodeURIComponent(projectId)}`);
}

export async function adminUpdateProject(projectId: string, patch: { voice_enabled: boolean }) {
  return apiFetch<AdminProjectUpdateResponse>(`/api/projects/${encodeURIComponent(projectId)}`, {
    method: "PUT",
    body: JSON.stringify(patch),
  });
}

export async function adminListTopics(projectId: string) {
  return apiFetch<AdminTopicsResponse>(`/api/projects/${encodeURIComponent(projectId)}/topics`);
}

export async function adminListTopicLogs(projectId: string) {
  return apiFetch<AdminTopicLogsResponse>(`/api/projects/${encodeURIComponent(projectId)}/topics_log`);
}

export async function adminGetProjectUsage(projectId: string) {
  return apiFetch<AdminProjectUsageResponse>(`/api/projects/${encodeURIComponent(projectId)}/usage`);
}

export async function adminListSessions(projectId: string, query: Record<string, string | number | undefined>) {
  const qs = new URLSearchParams();
  Object.entries(query).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    qs.set(k, String(v));
  });
  const suffix = qs.toString();
  return apiFetch<SessionsResponse>(
    `/api/projects/${encodeURIComponent(projectId)}/sessions${suffix ? `?${suffix}` : ""}`
  );
}

export async function adminGetSession(projectId: string, respondentId: string, includeSystem: boolean) {
  const qs = new URLSearchParams();
  if (includeSystem) qs.set("include_system", "1");
  const suffix = qs.toString();
  return apiFetch<SessionDetail>(
    `/api/projects/${encodeURIComponent(projectId)}/sessions/${encodeURIComponent(respondentId)}${suffix ? `?${suffix}` : ""}`
  );
}

export async function adminUpdateSessionAnnotation(
  projectId: string,
  respondentId: string,
  patch: { admin_note?: string | null; admin_like?: -1 | 0 | 1 }
) {
  return apiFetch<{ ok: true }>(`/api/projects/${encodeURIComponent(projectId)}/sessions/${encodeURIComponent(respondentId)}/annotation`, {
    method: "PUT",
    body: JSON.stringify(patch),
  });
}

export async function adminUpdateRecordAnnotation(
  projectId: string,
  recordId: string,
  patch: { admin_note?: string | null; admin_like?: -1 | 0 | 1 }
) {
  return apiFetch<{ ok: true }>(`/api/projects/${encodeURIComponent(projectId)}/records/${encodeURIComponent(recordId)}/annotation`, {
    method: "PUT",
    body: JSON.stringify(patch),
  });
}

export async function adminDeleteSessions(
  projectId: string,
  payload: {
    ids?: string[];
    select_all?: boolean;
    exclude_ids?: string[];
    filters?: Record<string, string>;
  }
) {
  return apiFetch<{ ok: true; deleted: number }>(
    `/api/projects/${encodeURIComponent(projectId)}/sessions/delete`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    }
  );
}

export async function adminAnalyzeStale(projectId: string, inactiveMinutes = 10) {
  const qs = new URLSearchParams({ inactive_minutes: String(inactiveMinutes) });
  return apiFetch<{ ok: true; analyzed: number; skipped: number }>(
    `/api/projects/${encodeURIComponent(projectId)}/analyze_stale?${qs.toString()}`,
    { method: "POST" }
  );
}

export async function adminListShareLinks(projectId: string) {
  return apiFetch<{ links: ShareLink[] }>(`/api/projects/${encodeURIComponent(projectId)}/share_links`);
}

export async function adminCreateShareLink(projectId: string, payload: { label?: string | null }) {
  return apiFetch<{ id: string; share_url: string; share_path: string; password: string }>(
    `/api/projects/${encodeURIComponent(projectId)}/share_links`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    }
  );
}

export async function adminRevokeShareLink(projectId: string, linkId: string) {
  return apiFetch<{ ok: true }>(`/api/projects/${encodeURIComponent(projectId)}/share_links/${encodeURIComponent(linkId)}/revoke`, {
    method: "POST",
  });
}

export type ShareInfoResponse = { project: { id: string; name: string | null }; requires_password: boolean };
export type ShareLoginResponse = { ok: true; project: { id: string } };

export async function shareInfo(token: string) {
  return apiFetch<ShareInfoResponse>(`/api/share/${encodeURIComponent(token)}/info`);
}

export async function shareLogin(token: string, password: string) {
  return apiFetch<ShareLoginResponse>(`/api/share/${encodeURIComponent(token)}/login`, {
    method: "POST",
    body: JSON.stringify({ password }),
  });
}

export async function shareListSessions(token: string, query: Record<string, string | number | undefined>) {
  const qs = new URLSearchParams();
  Object.entries(query).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    qs.set(k, String(v));
  });
  const suffix = qs.toString();
  return apiFetch<SessionsResponse>(
    `/api/share/${encodeURIComponent(token)}/sessions${suffix ? `?${suffix}` : ""}`
  );
}

export async function shareGetSession(token: string, respondentId: string) {
  return apiFetch<SessionDetail>(`/api/share/${encodeURIComponent(token)}/sessions/${encodeURIComponent(respondentId)}`);
}

export async function shareUpdateSessionAnnotation(
  token: string,
  respondentId: string,
  patch: { admin_note?: string | null; admin_like?: -1 | 0 | 1 }
) {
  return apiFetch<{ ok: true }>(
    `/api/share/${encodeURIComponent(token)}/sessions/${encodeURIComponent(respondentId)}/annotation`,
    {
      method: "PUT",
      body: JSON.stringify(patch),
    }
  );
}
