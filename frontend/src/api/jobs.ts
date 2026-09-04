import { apiRequest } from "./client";
import type { JobView } from "./types";


export const jobKeys = {
  review: (reviewId: string, stage: string) => ["reviews", reviewId, "jobs", stage] as const,
  detail: (jobId: string) => ["jobs", jobId] as const,
};


export function listReviewJobs(
  reviewId: string,
  stage: string,
  limit = 1,
): Promise<JobView[]> {
  const query = new URLSearchParams({ stage, limit: String(limit) });
  return apiRequest<JobView[]>(`/reviews/${reviewId}/jobs?${query}`);
}


export function getJob(jobId: string): Promise<JobView> {
  return apiRequest<JobView>(`/jobs/${jobId}`);
}


export function jobEventsUrl(jobId: string, afterSequence = 0) {
  return `/api/v1/jobs/${jobId}/events?after=${afterSequence}`;
}
