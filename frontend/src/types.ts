export type SourceName = "linkedin" | "hellowork" | "francetravail" | "adzuna" | "wttj";

export interface JobSource {
  source: string;
  external_id: string;
  url: string;
  scraped_at: string;
  last_seen_at: string;
}

export interface Job {
  id: string;
  title: string;
  company: string;
  location: string;
  description: string | null;
  canonical_url: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string;
  contract_type: string | null;
  experience_level: string | null;
  remote: boolean | null;
  posted_at: string | null;
  skills: string[];
  benefits: string[];
  first_seen_at: string;
  last_seen_at: string;
  saved: boolean;
  hidden: boolean;
  user_notes: string | null;
  user_tags: string[];
  sources: JobSource[];
}

export interface JobPage {
  items: Job[];
  total: number;
  limit: number;
  offset: number;
}

export interface SearchCriteria {
  keywords: string[];
  title?: string;
  location: string;
  radius_km?: number;
  contract_types: string[];
  experience_levels: string[];
  workplace_types: string[];
  date_posted: string;
  sort_by: string;
  max_results: number;
}

export interface SourceProgress {
  source: string;
  status: string;
  job_count: number;
  error?: string | null;
}

export interface SearchRun {
  id: string;
  status: string;
  total_jobs: number;
  sources: SourceProgress[];
}

export interface LocalJobMeta {
  saved?: boolean;
  hidden?: boolean;
  notes?: string;
  tags?: string[];
}

export interface ApplicationTask {
  id: string;
  title: string;
  due_at: string | null;
  completed: boolean;
  created_at: string;
}

export interface ApplicationEvent {
  id: string;
  event_type: string;
  from_stage: string | null;
  to_stage: string | null;
  note: string | null;
  created_at: string;
}

export interface Application {
  id: string;
  stage: string;
  applied_at: string | null;
  next_action_at: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  job: Job;
  events: ApplicationEvent[];
  tasks: ApplicationTask[];
}

export interface AnalyticsOverview {
  total_applications: number;
  active_applications: number;
  overdue_tasks: number;
  stage_counts: Record<string, number>;
}

export interface SavedSearch {
  id: string;
  name: string | null;
  criteria: SearchCriteria;
  sources: string[];
  include_details: boolean;
  schedule_enabled: boolean;
  schedule_interval_minutes: number | null;
  next_run_at: string | null;
  last_run_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Notification {
  id: string;
  kind: string;
  title: string;
  message: string;
  read: boolean;
  entity_type: string | null;
  entity_id: string | null;
  created_at: string;
}

export interface SourceHealth {
  name: string;
  enabled: boolean;
  last_status: string;
  last_error: string | null;
}
