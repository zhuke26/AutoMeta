import { useQuery } from "@tanstack/react-query";

import { artifactKeys, listArtifacts } from "../api/artifacts";


export function useReviewArtifacts(reviewId: string, enabled = true) {
  return useQuery({
    queryKey: artifactKeys.all(reviewId),
    queryFn: () => listArtifacts(reviewId),
    enabled: Boolean(reviewId) && enabled,
  });
}
