import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useAutosavedArtifact } from "./useAutosavedArtifact";


function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}


afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});


describe("useAutosavedArtifact", () => {
  it("debounces a changed draft for 600 ms and reports the saved version", async () => {
    vi.useFakeTimers();
    const saved = {
      artifact_id: "artifact-1",
      review_id: "review-1",
      stage: "setup",
      kind: "question_pico",
      state: "draft",
      version: 3,
      payload: { research_question: "Updated question" },
      content_hash: "hash",
      created_at: "2026-09-05T00:00:00Z",
      approved: false,
    };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(saved), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(
      () => useAutosavedArtifact(
        "review-1",
        "question_pico",
        { research_question: "Updated question" },
        true,
      ),
      { wrapper },
    );

    await act(async () => vi.advanceTimersByTimeAsync(599));
    expect(fetchMock).not.toHaveBeenCalled();
    await act(async () => vi.advanceTimersByTimeAsync(1));
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(result.current.state).toBe("saved");
    expect(result.current.artifact?.version).toBe(3);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not save while disabled", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(
      () => useAutosavedArtifact("review-1", "question_pico", { P: "Adults" }, false),
      { wrapper },
    );
    await act(async () => vi.advanceTimersByTimeAsync(1000));

    expect(result.current.state).toBe("idle");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
