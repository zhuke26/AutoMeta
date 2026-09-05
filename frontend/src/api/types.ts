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
  version_id?: string;
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

export interface ArtifactVersionView {
  version_id: string;
  artifact_id: string;
  review_id: string;
  stage: string;
  kind: ArtifactKind;
  version: number;
  payload: Record<string, unknown>;
  content_hash: string;
  created_at: string;
  approval_status: string | null;
  approved_at: string | null;
  revoked_at: string | null;
}

export interface ArtifactDiffChange {
  op: "add" | "remove" | "replace";
  path: string;
  before: unknown;
  after: unknown;
}

export interface ArtifactDiffView {
  artifact_id: string;
  kind: ArtifactKind;
  from_version: number;
  to_version: number;
  changes: ArtifactDiffChange[];
}

export type ProvenanceProducer = "researcher" | "agent" | "system";

export interface ReviewEventView {
  id: string;
  review_id: string;
  sequence: number;
  stage: string | null;
  event_type: string;
  producer: ProvenanceProducer;
  stage_run_id: string | null;
  job_id: string | null;
  artifact_version_id: string | null;
  elapsed_ms: number | null;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface ProvenanceGraphView {
  events: ReviewEventView[];
  edges: Array<{ id: string; source_version_id: string; target_version_id: string; relation: string }>;
  edits: Array<{ id: string; artifact_id: string; from_version_id: string | null; to_version_id: string; changed_paths: string[] }>;
  reruns: Array<{ id: string; source_stage_run_id: string; rerun_stage_run_id: string; source_event_id: string }>;
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
  kind: "pdf" | "csv";
  mime_type: string;
  size_bytes: number;
  parse_status: string;
  created_at: string;
}

export interface PdfBoundingBox {
  left: number;
  bottom: number;
  right: number;
  top: number;
  page_width: number;
  page_height: number;
}

export interface SourceLocator {
  file_id?: string | null;
  source_id?: string | null;
  page_number?: number | null;
  element_type: "body" | "table" | "unknown";
  table_index?: number | null;
  row_index?: number | null;
  column_index?: number | null;
  bbox?: PdfBoundingBox | null;
  text_start?: number | null;
  text_end?: number | null;
  parser_name: string;
  parser_version: string;
  extraction_type: "direct" | "derived";
  derivation: string;
  quotation: string;
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
