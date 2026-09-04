import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiRequest } from "./client";
import type { ArtifactKind, ArtifactView } from "./types";


export const artifactKeys = {
  all: (reviewId: string) => ["reviews", "detail", reviewId, "artifacts"] as const,
  detail: (reviewId: string, kind: ArtifactKind) =>
    ["reviews", "detail", reviewId, "artifacts", kind] as const,
};


export function listArtifacts(reviewId: string): Promise<ArtifactView[]> {
  return apiRequest<ArtifactView[]>(`/reviews/${reviewId}/artifacts`);
}


export function getArtifact(reviewId: string, kind: ArtifactKind): Promise<ArtifactView> {
  return apiRequest<ArtifactView>(`/reviews/${reviewId}/artifacts/${kind}`);
}


export function saveArtifact(
  reviewId: string,
  kind: ArtifactKind,
  payload: Record<string, unknown>,
): Promise<ArtifactView> {
  return apiRequest<ArtifactView>(`/reviews/${reviewId}/artifacts/${kind}`, {
    method: "PUT",
    body: JSON.stringify({ payload }),
  });
}


export function approveArtifact(reviewId: string, artifact: ArtifactView): Promise<ArtifactView> {
  return apiRequest<ArtifactView>(
    `/reviews/${reviewId}/artifacts/${artifact.kind}/approve`,
    {
      method: "POST",
      body: JSON.stringify({ artifact_id: artifact.artifact_id, version: artifact.version }),
    },
  );
}


export function revokeArtifact(reviewId: string, kind: ArtifactKind): Promise<ArtifactView> {
  return apiRequest<ArtifactView>(`/reviews/${reviewId}/artifacts/${kind}/revoke`, {
    method: "POST",
  });
}


export function currentArtifact(
  serverArtifact: ArtifactView | undefined,
  locallySavedArtifact: ArtifactView | undefined,
) {
  if (!locallySavedArtifact) return serverArtifact;
  if (!serverArtifact) return locallySavedArtifact;
  return serverArtifact.version >= locallySavedArtifact.version
    ? serverArtifact
    : locallySavedArtifact;
}


function updateArtifactCache(
  queryClient: ReturnType<typeof useQueryClient>,
  artifact: ArtifactView,
) {
  queryClient.setQueryData(artifactKeys.detail(artifact.review_id, artifact.kind), artifact);
  queryClient.invalidateQueries({ queryKey: artifactKeys.all(artifact.review_id) });
}


export function useSaveArtifact() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      reviewId,
      kind,
      payload,
    }: {
      reviewId: string;
      kind: ArtifactKind;
      payload: Record<string, unknown>;
    }) => saveArtifact(reviewId, kind, payload),
    onSuccess: (artifact) => updateArtifactCache(queryClient, artifact),
  });
}


export function useApproveArtifact() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ reviewId, artifact }: { reviewId: string; artifact: ArtifactView }) =>
      approveArtifact(reviewId, artifact),
    onSuccess: (artifact) => updateArtifactCache(queryClient, artifact),
  });
}


export function useRevokeArtifact() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ reviewId, kind }: { reviewId: string; kind: ArtifactKind }) =>
      revokeArtifact(reviewId, kind),
    onSuccess: (artifact) => updateArtifactCache(queryClient, artifact),
  });
}
