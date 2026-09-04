import { apiRequest } from "./client";
import type { JobView } from "./types";


export function startWorkflowJob(
  reviewId: string,
  action: string,
  body: Record<string, unknown>,
): Promise<JobView> {
  return apiRequest<JobView>(`/reviews/${reviewId}/workflow/${action}`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}
