import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import type { ArtifactView, FileView, JobView } from "../api/types";


const review = {
  id: "review-1",
  name: "Guided review",
  entry_mode: "guided",
  status: "active",
  current_stage: "screening",
  created_at: "2026-09-01T08:00:00Z",
  updated_at: "2026-09-05T09:30:00Z",
};


function artifact(
  kind: ArtifactView["kind"],
  stage: ArtifactView["stage"],
  payload: Record<string, unknown>,
): ArtifactView {
  return {
    artifact_id: `${kind}-1`,
    review_id: review.id,
    stage,
    kind,
    state: "draft",
    version: 1,
    payload,
    content_hash: "hash",
    created_at: "2026-09-05T09:00:00Z",
    approved: false,
  };
}


const paper = {
  pmid: "100",
  title: "Stroke rehabilitation trial",
  abstract: "Adults received supervised rehabilitation.",
  authors: "Doe J",
  year: "2024",
  journal: "Journal A",
  publication_type: "RCT",
};

const pdf: FileView = {
  id: "pdf-1",
  review_id: review.id,
  original_name: "study.pdf",
  kind: "pdf",
  mime_type: "application/pdf",
  size_bytes: 1200,
  parse_status: "pending",
  created_at: "2026-09-05T09:00:00Z",
};

const csv: FileView = {
  id: "csv-1",
  review_id: review.id,
  original_name: "effects.csv",
  kind: "csv",
  mime_type: "text/csv",
  size_bytes: 100,
  parse_status: "pending",
  created_at: "2026-09-05T09:00:00Z",
};

const initialArtifacts: ArtifactView[] = [
  artifact("question_pico", "setup", {
    research_question: "Does rehabilitation improve recovery after stroke?",
    pico: { P: "Adults", I: "Rehabilitation", C: "Usual care", O: "Recovery" },
    recommended_outcomes: [],
    rationale: "",
  }),
  artifact("query", "search", {
    strategy_mode: "field_tagged_balanced",
    generated_raw_query: "stroke[Title/Abstract]",
    raw_query: "stroke[Title/Abstract]",
    strategy: {},
  }),
  artifact("records", "search", {
    query_url: "https://pubmed.ncbi.nlm.nih.gov/?term=stroke",
    total_count: 1,
    retrieved_count: 1,
    papers: [paper],
  }),
  artifact("selected_studies", "screening", {
    decisions: [{
      pmid: paper.pmid,
      title: paper.title,
      final_decision: "INCLUDE",
      decision_stage: "ranking",
      score_result: {
        scores: { P: 1, I: 1, C: 0, O: 1 },
        confidence: { P: 0.9, I: 0.8, C: 0.5, O: 0.9 },
        evidence: { P: "Adults", I: "Rehabilitation", C: "Not reported", O: "Recovery" },
        weighted_score: 3,
        max_score: 4,
        reasoning: "Relevant",
      },
    }],
    selected_pmids: [paper.pmid],
  }),
  artifact("sources", "extraction", {
    file_ids: [pdf.id],
    study_characteristics_fields: [{ name: "Sample size", description: "Participants" }],
    study_results_fields: [{ name: "Mean difference", description: "Final follow-up" }],
    characteristics: [{
      filename: pdf.original_name,
      extractions: [{
        field_name: "Sample size",
        value: "120",
        citation: "We randomized 120 participants.",
        confidence: "HIGH",
      }],
    }],
    results: [{
      filename: pdf.original_name,
      outcome_label: "Recovery",
      selected_for_meta: true,
      extractions: [{
        field_name: "Mean difference",
        value: "2.4",
        citation: "Mean difference was 2.4 points.",
        confidence: "HIGH",
      }],
    }],
  }),
  artifact("plan", "meta_analysis", {
    file_ids: [csv.id],
    user_hint: "",
    csv_summaries: [{
      csv_file: csv.original_name,
      columns: ["study", "mean_t", "mean_c"],
      row_count: 2,
      sample_rows: [],
    }],
    plans: [{
      csv_file: csv.original_name,
      outcome_name: "Recovery",
      method_text: "Pool mean differences.",
      analysis_type: "continuous",
      effect_measure: "MD",
      effect_source: "arm_level_data",
      model: {
        type: "fixed",
        fixed_method: "inverse_variance",
        random_method: "dersimonian_laird",
        i2_threshold: 50,
      },
      columns: {
        study_label: "study",
        experimental_mean: "mean_t",
        control_mean: "mean_c",
      },
      continuity_correction: null,
      exclusion_rules: [],
      output: {
        include_study_effects: true,
        include_weights: true,
        include_pooled_effect: true,
        include_heterogeneity: true,
        include_output_csv: true,
      },
      assumptions: [],
      warnings: [],
    }],
  }),
];

const interruptedJob: JobView = {
  id: "screening-job",
  review_id: review.id,
  stage: "screening",
  state: "interrupted",
  progress: { completed: 1, total: 2 },
  result_reference: null,
  error: "Application restarted before the job completed.",
  created_at: "2026-09-05T10:00:00Z",
  updated_at: "2026-09-05T10:01:00Z",
  started_at: "2026-09-05T10:00:01Z",
  finished_at: "2026-09-05T10:01:00Z",
};


function guidedFetch() {
  let artifacts = initialArtifacts;
  return vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/artifacts")) return Response.json(artifacts);
    if (url.includes("/jobs?")) {
      return Response.json(url.includes("stage=screening") ? [interruptedJob] : []);
    }
    if (url.endsWith("/settings/pdf-disclosure")) {
      return Response.json({ acknowledged: true });
    }
    if (url.endsWith("/files")) return Response.json([pdf]);
    if (url.endsWith("/datasets")) return Response.json([csv]);

    const approvalMatch = url.match(/\/artifacts\/([^/]+)\/approve$/);
    if (approvalMatch && init?.method === "POST") {
      const kind = approvalMatch[1];
      const current = artifacts.find((item) => item.kind === kind);
      if (!current) return Response.json({ detail: "Artifact not found" }, { status: 404 });
      const approved = { ...current, state: "approved" as const, approved: true };
      artifacts = artifacts.map((item) => item.kind === kind ? approved : item);
      return Response.json(approved);
    }
    return Response.json(review);
  });
}


function renderFlow() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/reviews/review-1/setup"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}


async function approve(label: string, regionLabel: string) {
  await userEvent.click(await screen.findByRole("button", { name: label }));
  expect(await within(screen.getByLabelText(regionLabel)).findByText("Approved")).toBeInTheDocument();
}


afterEach(() => vi.unstubAllGlobals());


describe("Guided Review flow", () => {
  it("restores interrupted work and approves every handoff before navigating downstream", async () => {
    vi.stubGlobal("fetch", guidedFetch());
    renderFlow();

    await screen.findByRole("heading", { name: "Review setup" });
    await approve("Approve PICO", "PICO approval");

    await userEvent.click(screen.getByRole("link", { name: /Search Agent/ }));
    await screen.findByRole("heading", { name: "Search Agent" });
    expect(screen.getByRole("button", { name: "Run PubMed search" })).toBeDisabled();
    await approve("Approve Query", "Query approval");
    expect(await screen.findByRole("button", { name: "Run PubMed search" })).toBeEnabled();
    await approve("Approve Records", "Records approval");

    await userEvent.click(screen.getByRole("link", { name: /Screening Agent/ }));
    await screen.findByRole("heading", { name: "Screening Agent" });
    expect(await screen.findByText("Interrupted")).toBeInTheDocument();
    await approve("Approve Selected studies", "Selected studies approval");

    await userEvent.click(screen.getByRole("link", { name: /Extraction Agent/ }));
    await screen.findByRole("heading", { name: "Extraction Agent" });
    await approve("Approve Sources", "Sources approval");

    await userEvent.click(screen.getByRole("link", { name: /Meta-analysis Agent/ }));
    await screen.findByRole("heading", { name: "Meta-analysis Agent" });
    expect(screen.getByRole("button", { name: "Run meta-analysis" })).toBeDisabled();
    await approve("Approve Plan", "Plan approval");
    await waitFor(() => expect(screen.getByRole("button", { name: "Run meta-analysis" })).toBeEnabled());
  });
});
