import { useMutation, useQuery } from "@tanstack/react-query";

import { apiRequest } from "./client";
import type {
  ArtifactDiffView,
  ArtifactKind,
  ArtifactVersionView,
  JobView,
  ProvenanceGraphView,
  ReviewEventView,
} from "./types";


export const provenanceKeys = {
  events: (reviewId: string) => ["reviews", "detail", reviewId, "provenance", "events"] as const,
  graph: (reviewId: string) => ["reviews", "detail", reviewId, "provenance", "graph"] as const,
  versions: (reviewId: string, kind: ArtifactKind) => ["reviews", "detail", reviewId, "artifacts", kind, "versions"] as const,
  diff: (reviewId: string, kind: ArtifactKind, fromVersion: number, toVersion: number) => ["reviews", "detail", reviewId, "artifacts", kind, "diff", fromVersion, toVersion] as const,
};


export function useProvenanceEvents(reviewId: string) {
  return useQuery({
    queryKey: provenanceKeys.events(reviewId),
    queryFn: () => apiRequest<ReviewEventView[]>(`/reviews/${reviewId}/provenance`),
  });
}


export function useProvenanceGraph(reviewId: string) {
  return useQuery({
    queryKey: provenanceKeys.graph(reviewId),
    queryFn: () => apiRequest<ProvenanceGraphView>(`/reviews/${reviewId}/provenance/graph`),
  });
}


export function useArtifactVersions(reviewId: string, kind: ArtifactKind) {
  return useQuery({
    queryKey: provenanceKeys.versions(reviewId, kind),
    queryFn: () => apiRequest<ArtifactVersionView[]>(`/reviews/${reviewId}/artifacts/${kind}/versions`),
  });
}


export function useArtifactDiff(
  reviewId: string,
  kind: ArtifactKind,
  fromVersion: number,
  toVersion: number,
) {
  return useQuery({
    queryKey: provenanceKeys.diff(reviewId, kind, fromVersion, toVersion),
    queryFn: () => apiRequest<ArtifactDiffView>(
      `/reviews/${reviewId}/artifacts/${kind}/diff?from_version=${fromVersion}&to_version=${toVersion}`,
    ),
    enabled: fromVersion > 0 && toVersion > 0 && fromVersion !== toVersion,
  });
}


export function useRerunEvent() {
  return useMutation({
    mutationFn: ({ reviewId, eventId }: { reviewId: string; eventId: string }) =>
      apiRequest<JobView>(`/reviews/${reviewId}/provenance/events/${eventId}/rerun`, {
        method: "POST",
      }),
  });
}


export function auditExportUrl(reviewId: string) {
  return `/api/v1/reviews/${reviewId}/audit-export`;
}
