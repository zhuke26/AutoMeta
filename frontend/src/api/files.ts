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
