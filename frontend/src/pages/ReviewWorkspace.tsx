import { Link, Navigate, Outlet, useLocation, useOutletContext, useParams } from "react-router-dom";

import { ApiError } from "../api/client";
import { useReview } from "../api/reviews";
import type { ArtifactView, ReviewEntryMode, ReviewSummary } from "../api/types";
import { AppShell } from "../components/AppShell";
import type { ProvenanceArtifact, ProvenanceState } from "../components/ProvenanceRail";
import type { StageId, StageState } from "../components/StageRail";
import { useReviewArtifacts } from "../hooks/useReviewArtifacts";


export interface ReviewWorkspaceContext {
  artifacts: ArtifactView[];
  review: ReviewSummary;
}


const entryRoutes: Record<ReviewEntryMode, string> = {
  guided: "setup",
  search: "search",
  screening: "screening",
  extraction: "extraction",
  meta_analysis: "meta-analysis",
};

const routeStages: Record<string, StageId> = {
  search: "search",
  screening: "screening",
  extraction: "extraction",
  "meta-analysis": "meta_analysis",
};

const persistedStages: Record<string, StageId | undefined> = {
  search: "search",
  screening: "screening",
  extraction: "extraction",
  meta_analysis: "meta_analysis",
};

const artifactLabels: Record<ArtifactView["kind"], ProvenanceArtifact> = {
  question_pico: "PICO",
  query: "Query",
  records: "Records",
  selected_studies: "Selected studies",
  sources: "Sources",
  plan: "Plan",
  code: "Code",
  result: "Result",
};


function deriveStageStates(review: ReviewSummary, artifacts: ArtifactView[]) {
  const states: Partial<Record<StageId, StageState>> = {};
  for (const artifact of artifacts) {
    const stage = persistedStages[artifact.stage];
    if (!stage) {
      continue;
    }
    const existing = states[stage];
    if (artifact.state === "stale") {
      states[stage] = "stale";
    } else if (artifact.state === "draft" && existing !== "stale") {
      states[stage] = "draft";
    } else if (!existing) {
      states[stage] = "approved";
    }
  }
  const current = review.current_stage ? persistedStages[review.current_stage] : undefined;
  if (current && !states[current]) {
    states[current] = "running";
  }
  return states;
}


function deriveProvenanceStates(artifacts: ArtifactView[]) {
  const states: Partial<Record<ProvenanceArtifact, ProvenanceState>> = {};
  for (const artifact of artifacts) {
    states[artifactLabels[artifact.kind]] = artifact.state;
  }
  return states;
}


export function useReviewWorkspace() {
  return useOutletContext<ReviewWorkspaceContext>();
}


export function ReviewEntryRedirect() {
  const { review } = useReviewWorkspace();
  return <Navigate replace to={entryRoutes[review.entry_mode]} />;
}


export function ReviewWorkspace() {
  const { reviewId = "" } = useParams();
  const location = useLocation();
  const review = useReview(reviewId);
  const artifacts = useReviewArtifacts(reviewId, review.isSuccess);

  if (review.isPending || (review.isSuccess && artifacts.isPending)) {
    return (
      <AppShell>
        <main className="state-panel">Loading Review…</main>
      </AppShell>
    );
  }

  if (review.isError) {
    const notFound = review.error instanceof ApiError && review.error.status === 404;
    return (
      <AppShell>
        <main className="panel state-panel state-panel--error">
          <h1>{notFound ? "Review not found" : "Could not open Review"}</h1>
          <p>{review.error.message}</p>
          <Link className="button" to="/library">Return to Library</Link>
        </main>
      </AppShell>
    );
  }

  if (artifacts.isError) {
    return (
      <AppShell reviewId={reviewId} reviewLabel={review.data.name}>
        <main className="panel state-panel state-panel--error">
          <h1>Could not load Review artifacts</h1>
          <p>{artifacts.error.message}</p>
        </main>
      </AppShell>
    );
  }

  const route = location.pathname.split("/").filter(Boolean).at(-1) ?? "";
  const activeStage = routeStages[route];
  const artifactItems = artifacts.data ?? [];

  return (
    <AppShell
      activeStage={activeStage}
      provenanceStates={deriveProvenanceStates(artifactItems)}
      reviewId={reviewId}
      reviewLabel={review.data.name}
      stageStates={deriveStageStates(review.data, artifactItems)}
    >
      <Outlet context={{ artifacts: artifactItems, review: review.data } satisfies ReviewWorkspaceContext} />
    </AppShell>
  );
}
