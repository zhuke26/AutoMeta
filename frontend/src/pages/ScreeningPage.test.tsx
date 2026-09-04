import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import type { ArtifactView, JobView } from "../api/types";


const review = {
  id: "review-1",
  name: "Screening review",
  entry_mode: "screening",
  status: "active",
  current_stage: "screening",
  created_at: "2026-09-01T08:00:00Z",
  updated_at: "2026-09-05T09:30:00Z",
};


function artifact(
  kind: ArtifactView["kind"],
  payload: Record<string, unknown>,
  state: "draft" | "approved" = "approved",
): ArtifactView {
  return {
    artifact_id: `${kind}-1`, review_id: review.id,
    stage: kind === "question_pico" ? "setup" : kind === "selected_studies" ? "screening" : "search",
    kind, state, version: 1, payload, content_hash: "hash",
    created_at: "2026-09-05T09:00:00Z", approved: state === "approved",
  };
}


const pico = artifact("question_pico", {
  pico: { P: "Adults", I: "Rehabilitation", C: "Usual care", O: "Recovery" },
});
const papers = [
  { pmid: "100", title: "High score trial", abstract: "Relevant", year: "2024", authors: "Doe", journal: "A", publication_type: "RCT" },
  { pmid: "200", title: "Uncertain study", abstract: "Unclear", year: "2023", authors: "Roe", journal: "B", publication_type: "Trial" },
];
const records = artifact("records", { papers, retrieved_count: 2, total_count: 2 });
const selected = artifact("selected_studies", {
  decisions: [
    { pmid: "100", title: "High score trial", final_decision: "INCLUDE", decision_stage: "ranking", score_result: { scores: { P: 1, I: 1, C: 0, O: 1 }, confidence: { P: 0.9, I: 0.8, C: 0.5, O: 0.9 }, evidence: { P: "Adults", I: "Rehabilitation", C: "Not reported", O: "Recovery" }, weighted_score: 3, max_score: 4, reasoning: "Relevant" } },
    { pmid: "200", title: "Uncertain study", final_decision: "UNCERTAIN", decision_stage: "ranking", score_result: { scores: { P: 1, I: 0, C: 0, O: 0 }, confidence: { P: 0.8, I: 0.4, C: 0.3, O: 0.4 }, evidence: { P: "Stroke", I: "Unclear", C: "Not reported", O: "Unclear" }, weighted_score: 1, max_score: 4, reasoning: "Needs review" } },
  ],
  summary: { total: 2, final_included: 2, final_excluded: 0 },
  screening_mode: "pico_ranking",
  selected_pmids: ["100", "200"],
}, "draft");


function screeningFetch(initialArtifacts: ArtifactView[]) {
  let artifacts = initialArtifacts;
  let jobs: JobView[] = [];
  return vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/artifacts")) return Response.json(artifacts);
    if (url.includes("/jobs?")) return Response.json(jobs);
    if (url.endsWith("/workflow/screening/records") && init?.method === "PUT") {
      const body = JSON.parse(String(init.body));
      const imported = artifact("records", { papers: body.papers, retrieved_count: body.papers.length, total_count: body.papers.length }, "draft");
      artifacts = artifacts.filter((item) => item.kind !== "records").concat(imported);
      return Response.json(imported);
    }
    if (url.endsWith("/artifacts/selected_studies") && init?.method === "PUT") {
      const body = JSON.parse(String(init.body));
      const saved = { ...selected, payload: body.payload, version: 2 };
      artifacts = artifacts.filter((item) => item.kind !== "selected_studies").concat(saved);
      return Response.json(saved);
    }
    if (url.includes("/approve")) {
      const kind = url.includes("selected_studies") ? "selected_studies" : "records";
      const current = artifacts.find((item) => item.kind === kind)!;
      const approved = { ...current, state: "approved" as const, approved: true };
      artifacts = artifacts.filter((item) => item.kind !== kind).concat(approved);
      return Response.json(approved);
    }
    if (url.endsWith("/workflow/screening/run")) {
      jobs = [{ id: "screen-job", review_id: review.id, stage: "screening", state: "queued", progress: null, result_reference: null, error: null, created_at: "2026-09-05T10:00:00Z", updated_at: "2026-09-05T10:00:00Z", started_at: null, finished_at: null }];
      return Response.json(jobs[0], { status: 202 });
    }
    return Response.json(review);
  });
}


function renderPage(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/reviews/review-1/screening"]}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
}


afterEach(() => vi.unstubAllGlobals());


describe("ScreeningPage", () => {
  it("blocks screening until PICO and Records are approved", async () => {
    renderPage(screeningFetch([{ ...pico, state: "draft", approved: false }]));
    expect(await screen.findByRole("heading", { name: "Screening Agent" })).toBeInTheDocument();
    expect(screen.getByText("Approve PICO and Records before screening.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run screening" })).toBeDisabled();
  });

  it.each([
    ["records.json", "application/json", JSON.stringify(papers), "json"],
    [
      "records.csv",
      "text/csv",
      "pmid,title,abstract,year\n100,High score trial,Relevant,2024\n200,Uncertain study,Unclear,2023",
      "csv",
    ],
  ])("imports local %s records as a draft artifact", async (filename, mimeType, content, sourceFormat) => {
    const fetchMock = screeningFetch([pico]);
    renderPage(fetchMock);
    const file = new File([content], filename, { type: mimeType });

    await userEvent.upload(await screen.findByLabelText("Import records file"), file);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/reviews/review-1/workflow/screening/records",
      expect.objectContaining({
        method: "PUT",
        body: expect.stringContaining(`"source_format":"${sourceFormat}"`),
      }),
    ));
    expect(await screen.findByRole("button", { name: "Approve Records" })).toBeEnabled();
  });

  it("starts durable screening with approved inputs", async () => {
    const fetchMock = screeningFetch([pico, records]);
    renderPage(fetchMock);

    await userEvent.click(await screen.findByRole("button", { name: "Run screening" }));

    expect(await screen.findByText("Queued")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/reviews/review-1/workflow/screening/run",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ study_design_filter: "both", max_concurrency: 50 }),
      }),
    );
  });

  it("shows dimension evidence and autosaves human Top N selection", async () => {
    const fetchMock = screeningFetch([pico, records, selected]);
    renderPage(fetchMock);

    const row = await screen.findByRole("row", { name: /High score trial/ });
    expect(within(row).getByText("Adults")).toBeInTheDocument();
    expect(within(row).getByText("3 / 4")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Select Uncertain study" })).toBeChecked();
    await userEvent.clear(screen.getByRole("spinbutton", { name: "Top N" }));
    await userEvent.type(screen.getByRole("spinbutton", { name: "Top N" }), "1");
    await userEvent.click(screen.getByRole("button", { name: "Select top N" }));
    expect(screen.getByRole("checkbox", { name: "Select High score trial" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Select Uncertain study" })).not.toBeChecked();

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/reviews/review-1/artifacts/selected_studies",
      expect.objectContaining({ method: "PUT" }),
    ), { timeout: 1500 });
    expect(screen.getByRole("button", { name: "Approve Selected studies" })).toBeEnabled();
  });
});
