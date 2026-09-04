import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import type { ArtifactView, JobView } from "../api/types";


const review = {
  id: "review-1",
  name: "Search review",
  entry_mode: "search",
  status: "active",
  current_stage: "search",
  created_at: "2026-09-01T08:00:00Z",
  updated_at: "2026-09-05T09:30:00Z",
};


function artifact(
  kind: ArtifactView["kind"],
  payload: Record<string, unknown>,
  state: "draft" | "approved" = "approved",
): ArtifactView {
  return {
    artifact_id: `${kind}-1`,
    review_id: review.id,
    stage: kind === "question_pico" ? "setup" : "search",
    kind,
    state,
    version: 1,
    payload,
    content_hash: "hash",
    created_at: "2026-09-05T09:00:00Z",
    approved: state === "approved",
  };
}


const pico = artifact("question_pico", {
  research_question: "Does rehabilitation improve recovery after stroke?",
  pico: { P: "Adults", I: "Rehabilitation", C: "Usual care", O: "Recovery" },
});

const query = artifact("query", {
  strategy_mode: "field_tagged_balanced",
  generated_raw_query: "stroke[Title/Abstract]",
  raw_query: "stroke[Title/Abstract]",
  strategy: {},
}, "draft");

const records = artifact("records", {
  query_url: "https://pubmed.ncbi.nlm.nih.gov/?term=stroke",
  total_count: 2,
  retrieved_count: 2,
  raw_query: "stroke[Title/Abstract]",
  papers: [
    { pmid: "100", title: "Stroke rehabilitation trial", authors: "Doe J", year: "2024", journal: "Journal A", publication_type: "RCT", abstract: "Abstract A" },
    { pmid: "200", title: "Community exercise", authors: "Roe K", year: "2022", journal: "Journal B", publication_type: "Trial", abstract: "Abstract B" },
  ],
}, "draft");


function renderPage(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/reviews/review-1/search"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}


function searchFetch(initialArtifacts: ArtifactView[]) {
  let artifacts = initialArtifacts;
  let jobs: JobView[] = [];
  const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/artifacts")) {
      return Response.json(artifacts);
    }
    if (url.includes("/jobs?")) {
      return Response.json(jobs);
    }
    if (url.endsWith("/artifacts/query") && init?.method === "PUT") {
      const body = JSON.parse(String(init.body));
      const saved = { ...query, payload: body.payload, version: query.version + 1 };
      artifacts = artifacts.filter((item) => item.kind !== "query").concat(saved);
      return Response.json(saved);
    }
    const approvalKind = url.includes("/artifacts/records/") ? "records" : "query";
    if (url.endsWith(`/artifacts/${approvalKind}/approve`)) {
      const current = artifacts.find((item) => item.kind === approvalKind)!;
      const approved = { ...current, state: "approved" as const, approved: true };
      artifacts = artifacts.filter((item) => item.kind !== approvalKind).concat(approved);
      return Response.json(approved);
    }
    if (url.includes("/workflow/search/")) {
      jobs = [{
        id: url.endsWith("/query") ? "query-job" : "records-job",
        review_id: review.id,
        stage: "search",
        state: "queued",
        progress: null,
        result_reference: null,
        error: null,
        created_at: "2026-09-05T10:00:00Z",
        updated_at: "2026-09-05T10:00:00Z",
        started_at: null,
        finished_at: null,
      }];
      return Response.json(jobs[0], { status: 202 });
    }
    return Response.json(review);
  });
  return fetchMock;
}


afterEach(() => vi.unstubAllGlobals());


describe("SearchPage", () => {
  it("blocks query generation until PICO is approved", async () => {
    renderPage(searchFetch([{ ...pico, state: "draft", approved: false }]));

    expect(await screen.findByRole("heading", { name: "Search Agent" })).toBeInTheDocument();
    expect(screen.getByText("Approve PICO in Review Setup before generating a query.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate query" })).toBeDisabled();
  });

  it("starts query generation as a persistent Search job", async () => {
    const fetchMock = searchFetch([pico]);
    renderPage(fetchMock);

    await userEvent.click(await screen.findByRole("button", { name: "Generate query" }));

    expect(await screen.findByText("Queued")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/reviews/review-1/workflow/search/query",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("autosaves an edited query and approves the current version", async () => {
    const fetchMock = searchFetch([pico, query]);
    renderPage(fetchMock);
    const editor = await screen.findByRole("textbox", { name: "PubMed query" });
    await userEvent.clear(editor);
    await userEvent.type(editor, "stroke AND rehabilitation");

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/reviews/review-1/artifacts/query",
      expect.objectContaining({ method: "PUT" }),
    ), { timeout: 1500 });
    await userEvent.click(await screen.findByRole("button", { name: "Approve Query" }));
    expect(await within(screen.getByLabelText("Query approval")).findByText("Approved")).toBeInTheDocument();
  });

  it("runs approved queries and renders real persisted records", async () => {
    const fetchMock = searchFetch([pico, { ...query, state: "approved", approved: true }, records]);
    renderPage(fetchMock);

    expect(await screen.findByText("Stroke rehabilitation trial")).toBeInTheDocument();
    expect(screen.getByText("Community exercise")).toBeInTheDocument();
    await userEvent.type(screen.getByRole("searchbox", { name: "Filter records" }), "community");
    expect(screen.queryByText("Stroke rehabilitation trial")).not.toBeInTheDocument();
    expect(screen.getByText("Community exercise")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export JSON" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Export CSV" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Export RIS" })).toBeEnabled();

    await userEvent.click(screen.getByRole("button", { name: "Run PubMed search" }));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/reviews/review-1/workflow/search/run",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ retmax: 1000, fetch_all: false, min_year: null, max_year: null }),
      }),
    );
    expect(screen.getByRole("button", { name: "Approve Records" })).toBeEnabled();
  });
});
