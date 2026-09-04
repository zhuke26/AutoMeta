import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiRequest } from "./client";
import type { FileView } from "./types";


export function listReviewFiles(reviewId: string): Promise<FileView[]> {
  return apiRequest<FileView[]>(`/reviews/${reviewId}/files`);
}


export function uploadReviewFiles(reviewId: string, files: File[]): Promise<FileView[]> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }
  return apiRequest<FileView[]>(`/reviews/${reviewId}/files`, {
    method: "POST",
    body: formData,
  });
}


export function listReviewDatasets(reviewId: string): Promise<FileView[]> {
  return apiRequest<FileView[]>(`/reviews/${reviewId}/datasets`);
}


export function uploadReviewDatasets(reviewId: string, files: File[]): Promise<FileView[]> {
  const formData = new FormData();
  for (const file of files) formData.append("files", file);
  return apiRequest<FileView[]>(`/reviews/${reviewId}/datasets`, {
    method: "POST",
    body: formData,
  });
}


export const fileKeys = {
  review: (reviewId: string) => ["reviews", reviewId, "files"] as const,
  datasets: (reviewId: string) => ["reviews", reviewId, "datasets"] as const,
};


export function useReviewFiles(reviewId: string) {
  return useQuery({
    queryKey: fileKeys.review(reviewId),
    queryFn: () => listReviewFiles(reviewId),
    enabled: Boolean(reviewId),
  });
}


export function useUploadReviewFiles(reviewId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (files: File[]) => uploadReviewFiles(reviewId, files),
    onSuccess: (uploaded) => {
      queryClient.setQueryData<FileView[]>(
        fileKeys.review(reviewId),
        (current = []) => {
          const byId = new Map(current.map((file) => [file.id, file]));
          for (const file of uploaded) byId.set(file.id, file);
          return [...byId.values()];
        },
      );
    },
  });
}


export function useReviewDatasets(reviewId: string) {
  return useQuery({
    queryKey: fileKeys.datasets(reviewId),
    queryFn: () => listReviewDatasets(reviewId),
    enabled: Boolean(reviewId),
  });
}


export function useUploadReviewDatasets(reviewId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (files: File[]) => uploadReviewDatasets(reviewId, files),
    onSuccess: (uploaded) => {
      queryClient.setQueryData<FileView[]>(
        fileKeys.datasets(reviewId),
        (current = []) => {
          const byId = new Map(current.map((file) => [file.id, file]));
          for (const file of uploaded) byId.set(file.id, file);
          return [...byId.values()];
        },
      );
    },
  });
}
