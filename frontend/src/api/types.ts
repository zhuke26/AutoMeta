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
