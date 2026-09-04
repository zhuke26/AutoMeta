import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LibraryPage } from "./LibraryPage";


const reviews = [
  {
    id: "review-1",
    name: "Review one",
    entry_mode: "guided",
    status: "draft",
    current_stage: null,
    created_at: "2026-09-05T00:00:00Z",
    updated_at: "2026-09-05T01:00:00Z",
  },
  {
    id: "review-2",
    name: "Stroke review",
    entry_mode: "extraction",
    status: "active",
    current_stage: "extraction",
    created_at: "2026-09-04T00:00:00Z",
    updated_at: "2026-09-04T01:00:00Z",
  },
] as const;


function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <LibraryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}


afterEach(() => vi.unstubAllGlobals());


describe("LibraryPage", () => {
  it("shows loading, empty, and error states", async () => {
    let resolveFetch: (response: Response) => void = () => undefined;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => { resolveFetch = resolve; })));
    const view = renderPage();
    expect(screen.getByText("Loading reviews…")).toBeInTheDocument();
    resolveFetch(new Response(JSON.stringify({ items: [], total: 0 }), { status: 200 }));
    expect(await screen.findByText("No reviews yet")).toBeInTheDocument();
    view.unmount();

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("failed", { status: 500 })));
    renderPage();
    expect(await screen.findByText("Could not load your Library.")).toBeInTheDocument();
  });

  it("lists, searches, and links to persisted reviews", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ items: reviews, total: reviews.length }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    renderPage();
    expect(await screen.findByText("Review one")).toBeInTheDocument();
    expect(screen.getByText("Stroke review")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Review one" })).toHaveAttribute(
      "href",
      "/reviews/review-1/setup",
    );

    await userEvent.type(screen.getByRole("searchbox", { name: "Search reviews" }), "stroke");
    expect(screen.queryByText("Review one")).not.toBeInTheDocument();
    expect(screen.getByText("Stroke review")).toBeInTheDocument();
  });

  it("renames and permanently deletes with exact-name confirmation", async () => {
    let items = reviews.map((review) => ({ ...review }));
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (init?.method === "PATCH") {
        const body = JSON.parse(String(init.body));
        items[0] = { ...items[0], name: body.name };
        return new Response(JSON.stringify(items[0]), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (init?.method === "DELETE") {
        items = items.slice(1);
        return new Response(null, { status: 204 });
      }
      return new Response(JSON.stringify({ items, total: items.length }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();

    const card = await screen.findByTestId("review-card-review-1");
    await userEvent.click(within(card).getByRole("button", { name: "Rename Review one" }));
    const nameInput = within(card).getByRole("textbox", { name: "Review name" });
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, "Renamed review");
    await userEvent.click(within(card).getByRole("button", { name: "Save name" }));
    expect(await screen.findByText("Renamed review")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Delete Renamed review" }));
    const dialog = screen.getByRole("dialog", { name: "Delete review" });
    const deleteButton = within(dialog).getByRole("button", { name: "Delete permanently" });
    expect(deleteButton).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText("Type Renamed review to confirm"), "Renamed review");
    expect(deleteButton).toBeEnabled();
    await userEvent.click(deleteButton);

    await waitFor(() => expect(screen.queryByText("Renamed review")).not.toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/reviews/review-1",
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});
