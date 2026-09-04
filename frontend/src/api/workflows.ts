import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiRequest } from "./client";
import { jobKeys } from "./jobs";
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


export function useStartWorkflowJob(
  reviewId: string,
  stage: string,
  action: string,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      startWorkflowJob(reviewId, action, body),
    onSuccess: (job) => {
      queryClient.setQueryData(jobKeys.review(reviewId, stage), [job]);
    },
  });
}
