import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiRequest } from "./client";
import { artifactKeys } from "./artifacts";
import { jobKeys } from "./jobs";
import type { ArtifactView, JobView } from "./types";


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


export interface ImportedPaper {
  pmid: string;
  title: string;
  abstract: string;
  authors?: string | null;
  year?: string | null;
  journal?: string | null;
  publication_type?: string | null;
}


export function importScreeningRecords(
  reviewId: string,
  papers: ImportedPaper[],
  sourceFormat: "json" | "csv" | "pubmed",
): Promise<ArtifactView> {
  return apiRequest<ArtifactView>(`/reviews/${reviewId}/workflow/screening/records`, {
    method: "PUT",
    body: JSON.stringify({ papers, source_format: sourceFormat }),
  });
}


export function useImportScreeningRecords(reviewId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      papers,
      sourceFormat,
    }: {
      papers: ImportedPaper[];
      sourceFormat: "json" | "csv" | "pubmed";
    }) => importScreeningRecords(reviewId, papers, sourceFormat),
    onSuccess: (artifact) => {
      queryClient.setQueryData(
        artifactKeys.detail(reviewId, "records"),
        artifact,
      );
      queryClient.invalidateQueries({ queryKey: artifactKeys.all(reviewId) });
    },
  });
}
