import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";


const review = {
  id: "review-1", name: "Provenance review", entry_mode: "guided", status: "active",
  current_stage: "search", created_at: "2026-09-01T08:00:00Z", updated_at: "2026-09-05T09:30:00Z",
};
const artifacts = [{
  artifact_id: "query-1", version_id: "version-2", review_id: review.id,
  stage: "search", kind: "query", state: "draft", version: 2,
  payload: { raw_query: "A AND B" }, content_hash: "hash-2",
  created_at: "2026-09-05T09:00:00Z", approved: false,
}];
const events = [
  { id: "event-1", review_id: review.id, sequence: 1, stage: "search", event_type: "artifact.version_created", producer: "agent", stage_run_id: "run-1", job_id: "job-1", artifact_version_id: "version-1", elapsed_ms: 120, payload: { kind: "query", model: "test-model" }, created_at: "2026-09-05T09:00:00Z" },
  { id: "event-2", review_id: review.id, sequence: 2, stage: "search", event_type: "stage.completed", producer: "system", stage_run_id: "run-1", job_id: "job-1", artifact_version_id: "version-1", elapsed_ms: 200, payload: { operation_kind: "search.run" }, created_at: "2026-09-05T09:00:01Z" },
];
const versions = [
  { version_id: "version-1", artifact_id: "query-1", review_id: review.id, stage: "search", kind: "query", version: 1, payload: { raw_query: "A" }, content_hash: "hash-1", created_at: "2026-09-05T08:59:00Z", approval_status: "revoked", approved_at: "2026-09-05T08:59:10Z", revoked_at: "2026-09-05T09:00:00Z" },
  { version_id: "version-2", artifact_id: "query-1", review_id: review.id, stage: "search", kind: "query", version: 2, payload: { raw_query: "A AND B" }, content_hash: "hash-2", created_at: "2026-09-05T09:00:00Z", approval_status: null, approved_at: null, revoked_at: null },
];


function renderPage() {
  const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/artifacts")) return Response.json(artifacts);
    if (url.endsWith("/provenance")) return Response.json(events);
    if (url.endsWith("/provenance/graph")) return Response.json({ events, edges: [], edits: [], reruns: [] });
    if (url.endsWith("/artifacts/query/versions")) return Response.json(versions);
    if (url.includes("/artifacts/query/diff")) return Response.json({
      artifact_id: "query-1", kind: "query", from_version: 1, to_version: 2,
      changes: [{ op: "replace", path: "/raw_query", before: "A", after: "A AND B" }],
    });
    if (url.endsWith("/events/event-2/rerun") && init?.method === "POST") {
      return Response.json({ id: "job-2", review_id: review.id, stage: "search", state: "queued", progress: null, result_reference: null, error: null, created_at: "2026-09-05T10:00:00Z", updated_at: "2026-09-05T10:00:00Z", started_at: null, finished_at: null }, { status: 202 });
    }
    return Response.json(review);
  });
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={["/reviews/review-1/provenance"]}><App /></MemoryRouter></QueryClientProvider>);
  return fetchMock;
}


afterEach(() => vi.unstubAllGlobals());


describe("ProvenancePage", () => {
  it("shows ordered events, deterministic version diffs, export, and confirmed reruns", async () => {
    const fetchMock = renderPage();
    expect(await screen.findByRole("heading", { name: "Evidence provenance" })).toBeInTheDocument();
    const timeline = screen.getByLabelText("Review event timeline");
    expect(await within(timeline).findByText("Artifact version created")).toBeInTheDocument();
    expect(within(timeline).getByText("Stage completed")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Filter by producer"), "agent");
    expect(within(timeline).queryByText("Stage completed")).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Filter by producer"), "all");
    await userEvent.click(within(timeline).getAllByText("Event details")[0]);
    expect(within(timeline).getByText(/test-model/)).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("From version"), "1");
    await userEvent.selectOptions(screen.getByLabelText("To version"), "2");
    expect(await screen.findByText("/raw_query")).toBeInTheDocument();
    expect(screen.getByText(/A AND B/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download audit JSON" })).toHaveAttribute(
      "href", "/api/v1/reviews/review-1/audit-export",
    );

    await userEvent.click(screen.getByRole("button", { name: "Rerun Stage completed" }));
    const dialog = screen.getByRole("dialog", { name: "Rerun workflow" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Rerun" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/reviews/review-1/provenance/events/event-2/rerun",
      expect.objectContaining({ method: "POST" }),
    ));
    expect(await screen.findByText("Rerun queued as job job-2.")).toBeInTheDocument();
  });

  it("keeps non-completed events non-rerunnable", async () => {
    renderPage();
    await screen.findByRole("heading", { name: "Evidence provenance" });
    expect(screen.queryByRole("button", { name: "Rerun Artifact version created" })).not.toBeInTheDocument();
  });
});
