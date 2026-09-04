import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ArtifactView } from "../api/types";
import { ArtifactApprovalBar } from "./ArtifactApprovalBar";


const draftArtifact = {
  artifact_id: "artifact-1",
  review_id: "review-1",
  stage: "search",
  kind: "query",
  state: "draft",
  version: 2,
  payload: { raw_query: "sleep[Title]" },
  content_hash: "abc",
  created_at: "2026-09-05T00:00:00Z",
  approved: false,
} satisfies ArtifactView;


function renderBar(artifact: ArtifactView) {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ArtifactApprovalBar artifact={artifact} reviewId="review-1" />
    </QueryClientProvider>,
  );
}


afterEach(() => vi.unstubAllGlobals());


describe("ArtifactApprovalBar", () => {
  it("approves the exact current artifact version", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ ...draftArtifact, state: "approved", approved: true }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ));
    vi.stubGlobal("fetch", fetchMock);
    renderBar(draftArtifact);

    await userEvent.click(screen.getByRole("button", { name: "Approve Query" }));

    await waitFor(() => expect(screen.getByText("Approved")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/reviews/review-1/artifacts/query/approve",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ artifact_id: "artifact-1", version: 2 }),
      }),
    );
  });

  it("does not allow a stale artifact to be approved", () => {
    renderBar({ ...draftArtifact, state: "stale" });

    expect(screen.getByText("Stale — regenerate before approval")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve Query" })).toBeDisabled();
  });
});
