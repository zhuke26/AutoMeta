export type ReviewEntryMode =
  | "guided"
  | "search"
  | "screening"
  | "extraction"
  | "meta_analysis";

export type ReviewStatus = "draft" | "active" | "complete" | "failed" | "deleting";

export interface ReviewSummary {
  id: string;
  name: string;
  entry_mode: ReviewEntryMode;
  status: ReviewStatus;
  current_stage: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReviewList {
  items: ReviewSummary[];
  total: number;
}

export type ArtifactState = "draft" | "approved" | "stale";

export type ArtifactKind =
  | "question_pico"
  | "query"
  | "records"
  | "selected_studies"
  | "sources"
  | "plan"
  | "code"
  | "result";

export interface ArtifactView {
  artifact_id: string;
  review_id: string;
  stage: string;
  kind: ArtifactKind;
  state: ArtifactState;
  version: number;
  payload: Record<string, unknown>;
  content_hash: string;
  created_at: string;
  approved: boolean;
}

export type JobState =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "interrupted"
  | "cancelled";

export interface JobView {
  id: string;
  review_id: string;
  stage: string;
  state: JobState;
  progress: Record<string, unknown> | null;
  result_reference: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface FileView {
  id: string;
  review_id: string;
  original_name: string;
  mime_type: string;
  size_bytes: number;
  parse_status: string;
  created_at: string;
}

export interface SystemStatus {
  product: string;
  version: string;
  database: "ready" | "unavailable";
  provider_base_url: string;
  provider_configured: boolean;
  models: Record<string, string>;
  data_directory: string;
  host: string;
  port: number;
}
