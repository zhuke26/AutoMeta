import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import type { ArtifactView, JobView } from "../api/types";


const review = {
  id: "review-1",
  name: "Stroke rehabilitation",
  entry_mode: "guided",
  status: "draft",
  current_stage: null,
  created_at: "2026-09-01T08:00:00Z",
  updated_at: "2026-09-05T09:30:00Z",
};


function renderPage() {
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


function artifact(payload: Record<string, unknown>, state: "draft" | "approved" = "draft") {
  return {
    artifact_id: "pico-1",
    review_id: review.id,
    stage: "setup",
    kind: "question_pico",
    state,
    version: 1,
    payload,
    content_hash: "hash",
    created_at: "2026-09-05T09:00:00Z",
    approved: state === "approved",
  } satisfies ArtifactView;
}


function workspaceFetch(initialArtifact?: ArtifactView) {
  let currentArtifact = initialArtifact;
  let jobs: JobView[] = [];
  const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/artifacts")) {
      return Response.json(currentArtifact ? [currentArtifact] : []);
    }
    if (url.includes("/jobs?")) {
      return Response.json(jobs);
    }
    if (url.endsWith("/artifacts/question_pico") && init?.method === "PUT") {
      const body = JSON.parse(String(init.body));
      currentArtifact = artifact(body.payload);
      return Response.json(currentArtifact);
    }
    if (url.endsWith("/artifacts/question_pico/approve")) {
      currentArtifact = { ...currentArtifact!, state: "approved", approved: true };
      return Response.json(currentArtifact);
    }
    if (url.endsWith("/workflow/protocol/draft")) {
      jobs = [{
        id: "job-protocol",
        review_id: review.id,
        stage: "protocol",
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


describe("ReviewSetupPage", () => {
  it("autosaves manually entered PICO and approves the saved version", async () => {
    const fetchMock = workspaceFetch();
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    await screen.findByRole("heading", { name: "Review setup" });

    await userEvent.type(screen.getByRole("textbox", { name: "Research question" }), "Does rehabilitation improve recovery after stroke?");
    await userEvent.type(screen.getByRole("textbox", { name: "Population" }), "Adults after stroke");
    await userEvent.type(screen.getByRole("textbox", { name: "Intervention" }), "Structured rehabilitation");
    await userEvent.type(screen.getByRole("textbox", { name: "Comparator" }), "Usual care");
    await userEvent.type(screen.getByRole("textbox", { name: "Outcomes" }), "Functional recovery");

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/reviews/review-1/artifacts/question_pico",
      expect.objectContaining({ method: "PUT" }),
    ), { timeout: 1500 });
    await userEvent.click(await screen.findByRole("button", { name: "Approve PICO" }));

    expect(await screen.findByText("Approved")).toBeInTheDocument();
    const saveCall = fetchMock.mock.calls.find(([url, init]) =>
      String(url).endsWith("/artifacts/question_pico") && init?.method === "PUT"
    );
    expect(JSON.parse(String(saveCall?.[1]?.body))).toEqual({
      payload: {
        research_question: "Does rehabilitation improve recovery after stroke?",
        pico: {
          P: "Adults after stroke",
          I: "Structured rehabilitation",
          C: "Usual care",
          O: "Functional recovery",
        },
        recommended_outcomes: [],
        rationale: "",
      },
    });
  });

  it("restores an approved PICO artifact", async () => {
    vi.stubGlobal("fetch", workspaceFetch(artifact({
      research_question: "Existing question",
      pico: { P: "Adults", I: "Therapy", C: "Usual care", O: "Recovery" },
      recommended_outcomes: [],
      rationale: "Existing rationale",
    }, "approved")));
    renderPage();

    expect(await screen.findByDisplayValue("Existing question")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Adults")).toBeInTheDocument();
    expect(screen.getByText("Approved")).toBeInTheDocument();
  });

  it("submits protocol drafting as a persistent job", async () => {
    const fetchMock = workspaceFetch();
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    const question = await screen.findByRole("textbox", { name: "Research question" });
    await userEvent.type(question, "Does rehabilitation improve recovery after stroke?");
    await userEvent.click(screen.getByRole("button", { name: "Generate PICO draft" }));

    expect(await screen.findByText("Queued")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/reviews/review-1/workflow/protocol/draft",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          research_question: "Does rehabilitation improve recovery after stroke?",
        }),
      }),
    );
  });
});
