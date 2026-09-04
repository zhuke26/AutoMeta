import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiRequest } from "./client";
import type { ReviewEntryMode, ReviewList, ReviewSummary } from "./types";


export const reviewKeys = {
  all: ["reviews"] as const,
  list: (query: string) => ["reviews", "list", query] as const,
  detail: (reviewId: string) => ["reviews", "detail", reviewId] as const,
};


export function listReviews(query = ""): Promise<ReviewList> {
  const suffix = query.trim() ? `?query=${encodeURIComponent(query.trim())}` : "";
  return apiRequest<ReviewList>(`/reviews${suffix}`);
}


export function getReview(reviewId: string): Promise<ReviewSummary> {
  return apiRequest<ReviewSummary>(`/reviews/${reviewId}`);
}


export function createReview(input: {
  name: string;
  entry_mode: ReviewEntryMode;
}): Promise<ReviewSummary> {
  return apiRequest<ReviewSummary>("/reviews", {
    method: "POST",
    body: JSON.stringify(input),
  });
}


export function renameReview(reviewId: string, name: string): Promise<ReviewSummary> {
  return apiRequest<ReviewSummary>(`/reviews/${reviewId}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}


export function deleteReview(reviewId: string, confirmationName: string): Promise<void> {
  return apiRequest<void>(`/reviews/${reviewId}`, {
    method: "DELETE",
    body: JSON.stringify({ confirmation_name: confirmationName }),
  });
}


export function useReviews(query = "") {
  return useQuery({
    queryKey: reviewKeys.list(query),
    queryFn: () => listReviews(query),
  });
}


export function useReview(reviewId: string) {
  return useQuery({
    queryKey: reviewKeys.detail(reviewId),
    queryFn: () => getReview(reviewId),
    enabled: Boolean(reviewId),
  });
}


export function useCreateReview() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createReview,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: reviewKeys.all }),
  });
}


export function useRenameReview() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ reviewId, name }: { reviewId: string; name: string }) =>
      renameReview(reviewId, name),
    onSuccess: (review) => {
      queryClient.setQueryData(reviewKeys.detail(review.id), review);
      queryClient.invalidateQueries({ queryKey: reviewKeys.all });
    },
  });
}


export function useDeleteReview() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ reviewId, confirmationName }: { reviewId: string; confirmationName: string }) =>
      deleteReview(reviewId, confirmationName),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: reviewKeys.all }),
  });
}
