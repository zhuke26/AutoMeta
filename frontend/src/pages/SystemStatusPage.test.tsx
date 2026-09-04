import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SystemStatusPage } from "./SystemStatusPage";


const status = {
  product: "AutoMeta",
  version: "0.1.0",
  database: "ready",
  provider_base_url: "https://models.example.test/v1",
  provider_configured: false,
  models: {
    default: "research-model",
    extraction: "extraction-model",
  },
  data_directory: "/local/autometa/data",
  host: "127.0.0.1",
  port: 8016,
};


function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SystemStatusPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}


afterEach(() => vi.unstubAllGlobals());


describe("SystemStatusPage", () => {
  it("renders safe local runtime and model configuration without credentials", async () => {
    let resolveFetch: (response: Response) => void = () => undefined;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => { resolveFetch = resolve; })));
    renderPage();
    expect(screen.getByText("Loading system status…")).toBeInTheDocument();

    resolveFetch(new Response(JSON.stringify(status), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));

    expect(await screen.findByRole("heading", { name: "System status" })).toBeInTheDocument();
    expect(await screen.findByText("Ready")).toBeInTheDocument();
    expect(screen.getAllByText("Not configured")).toHaveLength(2);
    expect(screen.getByText("https://models.example.test/v1")).toBeInTheDocument();
    expect(screen.getByText("127.0.0.1:8016")).toBeInTheDocument();
    expect(screen.getByText("research-model")).toBeInTheDocument();
    expect(screen.getByText("extraction-model")).toBeInTheDocument();
    expect(document.body.textContent?.toLowerCase()).not.toContain("api key value");
  });

  it("warns when the server is intentionally exposed beyond localhost", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ ...status, host: "0.0.0.0" }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    )));
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This server is reachable beyond localhost and has no authentication.",
    );
  });

  it("shows a clear API failure state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: "Status unavailable" }),
      { status: 503, headers: { "Content-Type": "application/json" } },
    )));
    renderPage();

    expect(await screen.findByRole("heading", { name: "Could not load system status" })).toBeInTheDocument();
    expect(screen.getByText("Status unavailable")).toBeInTheDocument();
  });
});
