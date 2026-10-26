import type { AnalyticsOverview, Application, Job, JobPage, LocalJobMeta, Notification, SavedSearch, SearchCriteria, SearchRun, SourceHealth } from "./types";

// Set VITE_API_URL for a separate backend origin. Otherwise use the Vite
// development proxy, which keeps the browser on the frontend origin.
const API_BASE = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers);
  if (options?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export function fetchJobs(params: URLSearchParams): Promise<JobPage> {
  return request(`/api/jobs?${params.toString()}`);
}

export function fetchJob(id: string): Promise<Job> {
  return request(`/api/jobs/${id}`);
}

export function launchSearch(
  criteria: SearchCriteria,
  sources: string[],
  includeDetails: boolean,
): Promise<{ id: string; status: string }> {
  return request("/api/search-runs", {
    method: "POST",
    body: JSON.stringify({ criteria, sources, include_details: includeDetails }),
  });
}

export function fetchRun(id: string): Promise<SearchRun> {
  return request(`/api/search-runs/${id}`);
}

export function cancelRun(id: string): Promise<{ id: string; status: string }> {
  return request(`/api/search-runs/${id}/cancel`, { method: "POST" });
}

export function eventUrl(id: string): string {
  return `${API_BASE}/api/search-runs/${id}/events`;
}

export function updateJob(id: string, patch: Partial<LocalJobMeta>): Promise<Job> {
  return request(`/api/jobs/${id}`, {
    method: "PATCH",
    body: JSON.stringify({
      ...(patch.saved !== undefined && { saved: patch.saved }),
      ...(patch.hidden !== undefined && { hidden: patch.hidden }),
      ...(patch.notes !== undefined && { user_notes: patch.notes }),
      ...(patch.tags !== undefined && { user_tags: patch.tags }),
    }),
  });
}

export function fetchApplications(): Promise<Application[]> {
  return request("/api/applications");
}

export function createApplication(jobId: string): Promise<Application> {
  return request("/api/applications", {
    method: "POST",
    body: JSON.stringify({ job_id: jobId, stage: "saved" }),
  });
}

export function updateApplication(id: string, patch: Record<string, unknown>): Promise<Application> {
  return request(`/api/applications/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function fetchAnalytics(): Promise<AnalyticsOverview> {
  return request("/api/analytics/overview");
}

export function fetchSavedSearches(): Promise<SavedSearch[]> {
  return request("/api/saved-searches");
}

export function createSavedSearch(payload: {
  name: string;
  criteria: SearchCriteria;
  sources: string[];
  include_details: boolean;
  schedule_enabled: boolean;
  schedule_interval_minutes?: number;
}): Promise<SavedSearch> {
  return request("/api/saved-searches", { method: "POST", body: JSON.stringify(payload) });
}

export function updateSavedSearch(id: string, patch: Partial<SavedSearch>): Promise<SavedSearch> {
  return request(`/api/saved-searches/${id}`, { method: "PATCH", body: JSON.stringify(patch) });
}

export function deleteSavedSearch(id: string): Promise<void> {
  return fetch(`${API_BASE}/api/saved-searches/${id}`, { method: "DELETE" }).then((response) => {
    if (!response.ok) throw new Error(`Request failed (${response.status})`);
  });
}

export function runSavedSearch(id: string): Promise<{ id: string; status: string }> {
  return request(`/api/saved-searches/${id}/run`, { method: "POST" });
}

export function fetchNotifications(): Promise<Notification[]> {
  return request("/api/notifications");
}

export function markNotificationRead(id: string): Promise<Notification> {
  return request(`/api/notifications/${id}/read`, { method: "PATCH" });
}

export function fetchSourceHealth(): Promise<{ items: SourceHealth[] }> {
  return request("/api/health/sources");
}
