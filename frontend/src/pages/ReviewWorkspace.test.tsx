import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";


const review = {
  id: "review-1",
  name: "Stroke rehabilitation",
  entry_mode: "guided",
  status: "active",
  current_stage: "screening",
  created_at: "2026-09-01T08:00:00Z",
  updated_at: "2026-09-05T09:30:00Z",
};


function artifact(kind: string, stage: string, state: "draft" | "approved" | "stale") {
  return {
    artifact_id: `artifact-${kind}`,
    review_id: review.id,
    stage,
    kind,
    state,
    version: 1,
    payload: {},
    content_hash: "abc123",
    created_at: "2026-09-05T09:00:00Z",
    approved: state === "approved",
  };
}


function LocationProbe() {
  return <output data-testid="location">{useLocation().pathname}</output>;
}


function renderWorkspace(path = "/reviews/review-1/setup") {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <App />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}


function mockWorkspace(
  reviewOverride: Partial<typeof review> = {},
  artifacts: unknown[] = [],
) {
  let currentReview = { ...review, ...reviewOverride };
  return vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/artifacts")) {
      return new Response(JSON.stringify(artifacts), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (init?.method === "PATCH") {
      const body = JSON.parse(String(init.body));
      currentReview = { ...currentReview, name: body.name };
      return new Response(JSON.stringify(currentReview), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify(currentReview), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
}


afterEach(() => vi.unstubAllGlobals());


describe("ReviewWorkspace", () => {
  it("shows a loading state and a specific not-found state", async () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)));
    const view = renderWorkspace();
    expect(screen.getByText("Loading Review…")).toBeInTheDocument();
    view.unmount();

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Review not found: review-1" }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    renderWorkspace();
    expect(await screen.findByRole("heading", { name: "Review not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Return to Library" })).toHaveAttribute("href", "/library");
  });

  it.each([
    ["guided", "setup"],
    ["search", "search"],
    ["screening", "screening"],
    ["extraction", "extraction"],
    ["meta_analysis", "meta-analysis"],
  ])("routes a %s Review to its persisted entry stage", async (entryMode, route) => {
    vi.stubGlobal("fetch", mockWorkspace({ entry_mode: entryMode }));
    renderWorkspace("/reviews/review-1");

    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent(`/reviews/review-1/${route}`);
    });
  });

  it("derives stage and provenance states from persisted artifacts", async () => {
    const artifacts = [
      artifact("query", "search", "approved"),
      artifact("selected_studies", "screening", "stale"),
      artifact("sources", "extraction", "draft"),
    ];
    vi.stubGlobal("fetch", mockWorkspace({}, artifacts));
    const { container } = renderWorkspace("/reviews/review-1/extraction");

    expect(await screen.findByText("Stroke rehabilitation")).toBeInTheDocument();
    const searchStage = container.querySelector('[data-stage="search"]');
    const screeningStage = container.querySelector('[data-stage="screening"]');
    const extractionStage = container.querySelector('[data-stage="extraction"]');
    expect(searchStage).toHaveAttribute("data-state", "approved");
    expect(screeningStage).toHaveAttribute("data-state", "stale");
    expect(extractionStage).toHaveAttribute("data-state", "draft");
    expect(within(screeningStage as HTMLElement).getByText("Stale")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Search Agent/i })).toHaveAttribute(
      "href",
      "/reviews/review-1/search",
    );

    const queryItem = screen.getByRole("listitem", { name: "Query approved" });
    const selectedStudiesItem = screen.getByRole("listitem", { name: "Selected studies stale" });
    expect(queryItem).toHaveAttribute("data-state", "approved");
    expect(selectedStudiesItem).toHaveAttribute("data-state", "stale");
  });

  it("shows persisted metadata and renames the Review from setup", async () => {
    const fetchMock = mockWorkspace();
    vi.stubGlobal("fetch", fetchMock);
    renderWorkspace();

    expect(await screen.findByRole("heading", { name: "Review setup" })).toBeInTheDocument();
    expect(screen.getByText("Guided Review")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Edit Review name" }));
    const input = screen.getByRole("textbox", { name: "Review name" });
    await userEvent.clear(input);
    await userEvent.type(input, "Updated title");
    await userEvent.click(screen.getByRole("button", { name: "Save Review name" }));

    expect(await screen.findByRole("heading", { name: "Updated title" })).toBeInTheDocument();
    expect(screen.getAllByText("Updated title")).toHaveLength(2);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/reviews/review-1",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ name: "Updated title" }),
      }),
    );
  });

  it("renders unavailable stage work as explicitly disabled", async () => {
    vi.stubGlobal("fetch", mockWorkspace());
    renderWorkspace("/reviews/review-1/meta-analysis");

    expect(await screen.findByRole("heading", { name: "Meta-analysis Agent" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run Meta-analysis" })).toBeDisabled();
    expect(screen.getByText("Workflow migration pending")).toBeInTheDocument();
  });
});
