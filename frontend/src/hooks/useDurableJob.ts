import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { jobEventsUrl, jobKeys, listReviewJobs } from "../api/jobs";
import type { JobState } from "../api/types";


const activeStates = new Set<JobState>(["queued", "running"]);
const retryableStates = new Set<JobState>(["failed", "interrupted"]);
const refreshEvents = [
  "queued",
  "running",
  "progress",
  "drafting",
  "artifact_saved",
  "retrieving",
  "screening",
  "parsing",
  "extracting",
  "planning",
  "analyzing",
  "succeeded",
  "failed",
  "interrupted",
  "cancelled",
] as const;


export function useDurableJob(reviewId: string, stage: string) {
  const queryClient = useQueryClient();
  const lastSequence = useRef(0);
  const [connectionAttempt, setConnectionAttempt] = useState(0);
  const jobs = useQuery({
    queryKey: jobKeys.review(reviewId, stage),
    queryFn: () => listReviewJobs(reviewId, stage, 1),
    enabled: Boolean(reviewId && stage),
    refetchInterval: (query) => {
      const latest = query.state.data?.[0];
      return latest && activeStates.has(latest.state) ? 1000 : false;
    },
  });
  const job = jobs.data?.[0];

  useEffect(() => {
    if (!job || !activeStates.has(job.state) || typeof EventSource === "undefined") {
      return;
    }
    const source = new EventSource(jobEventsUrl(job.id, lastSequence.current));
    let reconnectTimer: number | undefined;
    const refresh = (event: Event) => {
      const sequence = Number((event as MessageEvent).lastEventId);
      if (Number.isFinite(sequence) && sequence > 0) {
        lastSequence.current = sequence;
      }
      queryClient.invalidateQueries({ queryKey: jobKeys.review(reviewId, stage) });
    };
    for (const eventType of refreshEvents) {
      source.addEventListener(eventType, refresh);
    }
    source.onerror = () => {
      source.close();
      queryClient.invalidateQueries({ queryKey: jobKeys.review(reviewId, stage) });
      reconnectTimer = window.setTimeout(
        () => setConnectionAttempt((attempt) => attempt + 1),
        1000,
      );
    };
    return () => {
      source.close();
      if (reconnectTimer !== undefined) {
        window.clearTimeout(reconnectTimer);
      }
    };
  }, [connectionAttempt, job?.id, job?.state, queryClient, reviewId, stage]);

  return {
    error: jobs.error,
    isActive: Boolean(job && activeStates.has(job.state)),
    isLoading: jobs.isPending,
    job,
    refetch: jobs.refetch,
    retryable: Boolean(job && retryableStates.has(job.state)),
  };
}
