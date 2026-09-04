import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import type { ArtifactView, FileView, JobView } from "../api/types";


const review = {
  id: "review-1", name: "Extraction review", entry_mode: "extraction", status: "active",
  current_stage: "extraction", created_at: "2026-09-01T08:00:00Z", updated_at: "2026-09-05T09:30:00Z",
};
const pico: ArtifactView = {
  artifact_id: "pico-1", review_id: review.id, stage: "setup", kind: "question_pico",
  state: "approved", version: 1, payload: { pico: { P: "Adults", I: "Therapy", C: "Usual care", O: "Recovery" } },
  content_hash: "hash", created_at: "2026-09-05T09:00:00Z", approved: true,
};
const pdf: FileView = {
  id: "pdf-1", review_id: review.id, original_name: "study.pdf", mime_type: "application/pdf",
  size_bytes: 1200, parse_status: "pending", created_at: "2026-09-05T09:00:00Z",
};
const sources: ArtifactView = {
  artifact_id: "sources-1", review_id: review.id, stage: "extraction", kind: "sources",
  state: "draft", version: 1, content_hash: "hash", created_at: "2026-09-05T09:00:00Z", approved: false,
  payload: {
    file_ids: [pdf.id],
    study_characteristics_fields: [{ name: "Sample size", description: "Participants randomized" }],
    study_results_fields: [{ name: "Mean difference", description: "Final follow-up" }],
    characteristics: [{ filename: "study.pdf", extractions: [{ field_name: "Sample size", value: "120", citation: "We randomized 120 participants.", confidence: "HIGH" }] }],
    results: [{ filename: "study.pdf", outcome_label: "Recovery", selected_for_meta: false, extractions: [{ field_name: "Mean difference", value: "2.4", citation: "Mean difference was 2.4 points.", confidence: "HIGH" }] }],
  },
};


function extractionFetch(options: { acknowledged?: boolean; files?: FileView[]; artifacts?: ArtifactView[] } = {}) {
  let acknowledged = options.acknowledged ?? true;
  let files = options.files ?? [];
  let artifacts = options.artifacts ?? [pico];
  let jobs: JobView[] = [];
  return vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/artifacts")) return Response.json(artifacts);
    if (url.includes("/jobs?")) return Response.json(jobs);
    if (url.endsWith("/settings/pdf-disclosure")) {
      if (init?.method === "PUT") acknowledged = JSON.parse(String(init.body)).acknowledged;
      return Response.json({ acknowledged });
    }
    if (url.endsWith("/files")) {
      if (init?.method === "POST") files = [pdf];
      return Response.json(files, { status: init?.method === "POST" ? 201 : 200 });
    }
    if (url.endsWith("/workflow/extraction/run")) {
      jobs = [{ id: "extract-job", review_id: review.id, stage: "extraction", state: "queued", progress: null, result_reference: null, error: null, created_at: "2026-09-05T10:00:00Z", updated_at: "2026-09-05T10:00:00Z", started_at: null, finished_at: null }];
      return Response.json(jobs[0], { status: 202 });
    }
    if (url.endsWith("/artifacts/sources") && init?.method === "PUT") {
      const body = JSON.parse(String(init.body));
      const saved = { ...sources, version: 2, payload: body.payload };
      artifacts = artifacts.filter((item) => item.kind !== "sources").concat(saved);
      return Response.json(saved);
    }
    if (url.endsWith("/artifacts/sources/approve")) {
      const current = artifacts.find((item) => item.kind === "sources") ?? sources;
      const approved = { ...current, state: "approved" as const, approved: true };
      artifacts = artifacts.filter((item) => item.kind !== "sources").concat(approved);
      return Response.json(approved);
    }
    return Response.json(review);
  });
}


function renderPage(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={["/reviews/review-1/extraction"]}><App /></MemoryRouter></QueryClientProvider>);
}


afterEach(() => vi.unstubAllGlobals());


describe("ExtractionPage", () => {
  it("requires an explicit first-run PDF model disclosure acknowledgement", async () => {
    const fetchMock = extractionFetch({ acknowledged: false });
    renderPage(fetchMock);
    const dialog = await screen.findByRole("dialog", { name: "PDF processing notice" });
    expect(dialog).toHaveTextContent("relevant PDF text passages will be sent");
    await userEvent.click(screen.getByRole("button", { name: "I understand and continue" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/settings/pdf-disclosure",
      expect.objectContaining({ method: "PUT", body: JSON.stringify({ acknowledged: true }) }),
    );
  });

  it("uploads PDFs into the persisted Review file list", async () => {
    const fetchMock = extractionFetch();
    renderPage(fetchMock);
    const file = new File(["%PDF-1.4\nlocal"], "study.pdf", { type: "application/pdf" });
    await userEvent.upload(await screen.findByLabelText("Upload PDF files"), file);

    expect(await screen.findByText("study.pdf")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/reviews/review-1/files",
      expect.objectContaining({ method: "POST", body: expect.any(FormData) }),
    );
  });

  it("starts a persistent extraction job with selected PDFs and fields", async () => {
    const fetchMock = extractionFetch({ files: [pdf] });
    renderPage(fetchMock);
    await screen.findByText("study.pdf");
    await userEvent.click(screen.getByRole("checkbox", { name: "Use study.pdf" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Characteristic field name 1" }), "Sample size");
    await userEvent.click(screen.getByRole("button", { name: "Add result field" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Result field name 1" }), "Mean difference");

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/reviews/review-1/artifacts/sources",
      expect.objectContaining({ method: "PUT", body: expect.stringContaining('"study_characteristics_fields"') }),
    ), { timeout: 1500 });
    await userEvent.click(screen.getByRole("button", { name: "Run extraction" }));

    expect(await screen.findByText("Queued")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/reviews/review-1/workflow/extraction/run",
      expect.objectContaining({ method: "POST", body: expect.stringContaining('"file_ids":["pdf-1"]') }),
    );
  });

  it("shows source citations and autosaves researcher edits and meta selection", async () => {
    const fetchMock = extractionFetch({ files: [pdf], artifacts: [pico, sources] });
    renderPage(fetchMock);
    expect(await screen.findByText("We randomized 120 participants.")).toBeInTheDocument();
    const value = screen.getByRole("textbox", { name: "Sample size for study.pdf" });
    await userEvent.clear(value);
    await userEvent.type(value, "118");
    expect(screen.getByText("Researcher edited")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: "Use Recovery from study.pdf in meta-analysis" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/reviews/review-1/artifacts/sources",
      expect.objectContaining({ method: "PUT", body: expect.stringContaining('"researcher_edited":true') }),
    ), { timeout: 1500 });
    expect(screen.getByRole("button", { name: "Export extraction JSON" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Export extraction CSV" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Approve Sources" })).toBeEnabled();
  });
});
