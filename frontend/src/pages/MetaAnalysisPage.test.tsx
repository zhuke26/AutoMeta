import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import type { ArtifactView, FileView, JobView } from "../api/types";


const review = { id: "review-1", name: "Meta review", entry_mode: "meta_analysis", status: "active", current_stage: "meta_analysis", created_at: "2026-09-01T08:00:00Z", updated_at: "2026-09-05T09:30:00Z" };
const pico: ArtifactView = { artifact_id: "pico-1", review_id: review.id, stage: "setup", kind: "question_pico", state: "approved", version: 1, payload: { pico: { P: "Adults", I: "Therapy", C: "Usual care", O: "Recovery" } }, content_hash: "hash", created_at: "2026-09-05T09:00:00Z", approved: true };
const csvFile: FileView = { id: "csv-1", review_id: review.id, original_name: "effects.csv", kind: "csv", mime_type: "text/csv", size_bytes: 100, parse_status: "pending", created_at: "2026-09-05T09:00:00Z" };
const plan: ArtifactView = {
  artifact_id: "plan-1", review_id: review.id, stage: "meta_analysis", kind: "plan", state: "draft", version: 1, content_hash: "hash", created_at: "2026-09-05T09:00:00Z", approved: false,
  payload: { file_ids: [csvFile.id], user_hint: "", csv_summaries: [{ csv_file: "effects.csv", columns: ["study", "mean_t", "mean_c"], row_count: 2, sample_rows: [] }], plans: [{ csv_file: "effects.csv", outcome_name: "Recovery", method_text: "Pool mean differences.", analysis_type: "continuous", effect_measure: "MD", effect_source: "arm_level_data", model: { type: "fixed", fixed_method: "inverse_variance", random_method: "dersimonian_laird", i2_threshold: 50 }, columns: { study_label: "study", experimental_mean: "mean_t", control_mean: "mean_c" }, continuity_correction: null, exclusion_rules: [], output: { include_study_effects: true, include_weights: true, include_pooled_effect: true, include_heterogeneity: true, include_output_csv: true }, assumptions: [], warnings: [] }] },
};
const result: ArtifactView = {
  artifact_id: "result-1", review_id: review.id, stage: "meta_analysis", kind: "result", state: "draft", version: 1, content_hash: "hash", created_at: "2026-09-05T09:00:00Z", approved: false,
  payload: { results: [{ csv_file: "effects.csv", outcome_name: "Recovery", pooled_effect: { model_used: "fixed", effect_measure: "MD", effect: 2, standard_error: 0.2, ci_lower: 1.6, ci_upper: 2.4, z_value: 10, p_value: 0.001 }, heterogeneity: { q: 1, df: 1, p_value: 0.3, i2_percent: 0, tau2: 0 }, study_effects: [{ study_label: "Study A", effect: 2, standard_error: 0.3, ci_lower: 1.4, ci_upper: 2.6, weight_percent: 50 }], output_csv: "study,effect\nStudy A,2\n", logs: ["Validated 2 studies"], warnings: [] }] },
};
const code: ArtifactView = { artifact_id: "code-1", review_id: review.id, stage: "meta_analysis", kind: "code", state: "draft", version: 1, content_hash: "hash", created_at: "2026-09-05T09:00:00Z", approved: false, payload: { generated_code: { "effects.csv": "print('validated')" } } };


function metaFetch(initialArtifacts: ArtifactView[], initialFiles: FileView[] = []) {
  let artifacts = initialArtifacts;
  let files = initialFiles;
  let jobs: JobView[] = [];
  return vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/artifacts")) return Response.json(artifacts);
    if (url.includes("/jobs?")) return Response.json(jobs);
    if (url.endsWith("/datasets")) {
      if (init?.method === "POST") files = [csvFile];
      return Response.json(files, { status: init?.method === "POST" ? 201 : 200 });
    }
    if (url.endsWith("/artifacts/plan") && init?.method === "PUT") {
      const body = JSON.parse(String(init.body));
      const saved = { ...plan, version: 2, payload: body.payload };
      artifacts = artifacts.filter((item) => item.kind !== "plan").concat(saved);
      return Response.json(saved);
    }
    if (url.endsWith("/artifacts/plan/approve")) {
      const current = artifacts.find((item) => item.kind === "plan") ?? plan;
      const approved = { ...current, state: "approved" as const, approved: true };
      artifacts = artifacts.filter((item) => item.kind !== "plan").concat(approved);
      return Response.json(approved);
    }
    if (url.includes("/workflow/meta/")) {
      jobs = [{ id: url.endsWith("/plan") ? "plan-job" : "run-job", review_id: review.id, stage: "meta_analysis", state: "queued", progress: null, result_reference: null, error: null, created_at: "2026-09-05T10:00:00Z", updated_at: "2026-09-05T10:00:00Z", started_at: null, finished_at: null }];
      return Response.json(jobs[0], { status: 202 });
    }
    return Response.json(review);
  });
}


function renderPage(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={["/reviews/review-1/meta-analysis"]}><App /></MemoryRouter></QueryClientProvider>);
}


afterEach(() => vi.unstubAllGlobals());


describe("MetaAnalysisPage", () => {
  it("uploads a CSV dataset and starts a durable planning job", async () => {
    const fetchMock = metaFetch([pico]);
    renderPage(fetchMock);
    const file = new File(["study,mean_t,mean_c\nA,5,3\n"], "effects.csv", { type: "text/csv" });
    await userEvent.upload(await screen.findByLabelText("Upload CSV datasets"), file);
    expect(await screen.findByText("effects.csv")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: "Use effects.csv" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Planning guidance" }), "Prefer mean difference");
    await userEvent.click(screen.getByRole("button", { name: "Generate method plan" }));

    expect(await screen.findByText("Queued")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/reviews/review-1/workflow/meta/plan",
      expect.objectContaining({ method: "POST", body: expect.stringContaining('"file_ids":["csv-1"]') }),
    );
  });

  it("autosaves structured plan edits and gates execution on approval", async () => {
    const fetchMock = metaFetch([pico, plan], [csvFile]);
    renderPage(fetchMock);
    const editor = await screen.findByRole("textbox", { name: "Method description for effects.csv" });
    await userEvent.clear(editor);
    await userEvent.type(editor, "Use a prespecified fixed-effect model.");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Effect measure for effects.csv" }), "SMD");

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/reviews/review-1/artifacts/plan",
      expect.objectContaining({ method: "PUT", body: expect.stringContaining('"effect_measure":"SMD"') }),
    ), { timeout: 1500 });
    await userEvent.click(await screen.findByRole("button", { name: "Approve Plan" }));
    const runButton = await screen.findByRole("button", { name: "Run meta-analysis" });
    await waitFor(() => expect(runButton).toBeEnabled());
    await userEvent.click(runButton);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/reviews/review-1/workflow/meta/run",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ confirm_strict_execution: true }) }),
    );
  });

  it("renders persisted pooled estimates, heterogeneity, logs, and generated code", async () => {
    renderPage(metaFetch([pico, { ...plan, state: "approved", approved: true }, code, result], [csvFile]));

    expect(await screen.findByRole("heading", { name: "Recovery" })).toBeInTheDocument();
    const summary = screen.getByLabelText("Recovery statistical summary");
    expect(within(summary).getByText("2.000")).toBeInTheDocument();
    expect(within(summary).getByText("1.600 to 2.400")).toBeInTheDocument();
    expect(within(summary).getByText("0.0%")).toBeInTheDocument();
    expect(screen.getByText("Validated 2 studies")).toBeInTheDocument();
    expect(screen.getByText("print('validated')")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export analysis JSON" })).toBeEnabled();
    expect(screen.queryByText(/forest plot/i)).not.toBeInTheDocument();
  });
});
