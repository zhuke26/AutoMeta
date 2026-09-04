import { useQuery } from "@tanstack/react-query";

import { apiRequest } from "../api/client";
import type { ArtifactView } from "../api/types";


export const artifactKeys = {
  list: (reviewId: string) => ["reviews", "detail", reviewId, "artifacts"] as const,
};


export function listReviewArtifacts(reviewId: string): Promise<ArtifactView[]> {
  return apiRequest<ArtifactView[]>(`/reviews/${reviewId}/artifacts`);
}


export function useReviewArtifacts(reviewId: string, enabled = true) {
  return useQuery({
    queryKey: artifactKeys.list(reviewId),
    queryFn: () => listReviewArtifacts(reviewId),
    enabled: Boolean(reviewId) && enabled,
  });
}
