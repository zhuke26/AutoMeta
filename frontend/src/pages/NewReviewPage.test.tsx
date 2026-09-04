import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NewReviewPage } from "./NewReviewPage";


function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}</output>;
}


function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/reviews/new"]}>
        <Routes>
          <Route path="/reviews/new" element={<NewReviewPage />} />
          <Route path="*" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}


function createdReview(entryMode: string) {
  return {
    id: "new-review-id",
    name: "My review",
    entry_mode: entryMode,
    status: "draft",
    current_stage: null,
    created_at: "2026-09-05T00:00:00Z",
    updated_at: "2026-09-05T00:00:00Z",
  };
}


afterEach(() => vi.unstubAllGlobals());


describe("NewReviewPage", () => {
  it("offers all five real entry modes without example-data controls", () => {
    renderPage();

    expect(screen.getByRole("radio", { name: /Guided Review/i })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /^Search/i })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /^Screening/i })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /^Extraction/i })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /^Meta-analysis/i })).toBeInTheDocument();
    expect(screen.queryByText(/Load Example/i)).not.toBeInTheDocument();
  });

  it("requires a trimmed name and an entry mode", async () => {
    renderPage();
    const createButton = screen.getByRole("button", { name: "Create review" });
    expect(createButton).toBeDisabled();

    await userEvent.type(screen.getByRole("textbox", { name: "Review name" }), "   My review   ");
    expect(createButton).toBeDisabled();

    await userEvent.click(screen.getByRole("radio", { name: /Guided Review/i }));
    expect(createButton).toBeEnabled();

    await userEvent.clear(screen.getByRole("textbox", { name: "Review name" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Review name" }), "   ");
    expect(createButton).toBeDisabled();
  });

  it.each([
    ["Guided Review", "guided", "/reviews/new-review-id/setup"],
    ["Search", "search", "/reviews/new-review-id/search"],
    ["Screening", "screening", "/reviews/new-review-id/screening"],
    ["Extraction", "extraction", "/reviews/new-review-id/extraction"],
    ["Meta-analysis", "meta_analysis", "/reviews/new-review-id/meta-analysis"],
  ])("creates and routes the %s entry mode", async (label, entryMode, destination) => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(createdReview(entryMode)), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderPage();

    await userEvent.type(screen.getByRole("textbox", { name: "Review name" }), "  My review  ");
    await userEvent.click(screen.getByRole("radio", { name: new RegExp(`^${label}`, "i") }));
    await userEvent.click(screen.getByRole("button", { name: "Create review" }));

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent(destination));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/reviews",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ name: "My review", entry_mode: entryMode }),
      }),
    );
  });

  it("shows a structured API error and stays on the form", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Review creation failed" }), {
          status: 500,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    renderPage();

    await userEvent.type(screen.getByRole("textbox", { name: "Review name" }), "My review");
    await userEvent.click(screen.getByRole("radio", { name: /^Search/i }));
    await userEvent.click(screen.getByRole("button", { name: "Create review" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Review creation failed");
    expect(screen.getByRole("heading", { name: "Create a review" })).toBeInTheDocument();
  });
});
