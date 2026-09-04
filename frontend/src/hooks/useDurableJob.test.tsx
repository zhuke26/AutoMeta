import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useDurableJob } from "./useDurableJob";


const runningJob = {
  id: "job-1",
  review_id: "review-1",
  stage: "search",
  state: "running",
  progress: { completed: 2, total: 4 },
  result_reference: null,
  error: null,
  created_at: "2026-09-05T00:00:00Z",
  updated_at: "2026-09-05T00:00:01Z",
  started_at: "2026-09-05T00:00:01Z",
  finished_at: null,
};


class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readonly listeners = new Map<string, Array<(event: Event) => void>>();
  readonly close = vi.fn();
  onerror: (() => void) | null = null;

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: (event: Event) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }

  emit(type: string, lastEventId: string) {
    for (const listener of this.listeners.get(type) ?? []) {
      listener({ lastEventId } as MessageEvent);
    }
  }
}


function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}


afterEach(() => {
  FakeEventSource.instances = [];
  vi.useRealTimers();
  vi.unstubAllGlobals();
});


describe("useDurableJob", () => {
  it("restores the latest active job and closes SSE on browser-view unmount", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      const body = url.includes("/reviews/") ? [runningJob] : runningJob;
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }));

    const { result, unmount } = renderHook(
      () => useDurableJob("review-1", "search"),
      { wrapper },
    );

    await waitFor(() => expect(result.current.job?.id).toBe("job-1"));
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    expect(FakeEventSource.instances[0].url).toBe("/api/v1/jobs/job-1/events?after=0");
    unmount();
    expect(FakeEventSource.instances[0].close).toHaveBeenCalledOnce();
  });

  it("exposes an interrupted job as retryable without opening SSE", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify([{ ...runningJob, state: "interrupted" }]),
      { status: 200, headers: { "Content-Type": "application/json" } },
    )));

    const { result } = renderHook(
      () => useDurableJob("review-1", "search"),
      { wrapper },
    );

    await waitFor(() => expect(result.current.retryable).toBe(true));
    expect(result.current.job?.state).toBe("interrupted");
    expect(FakeEventSource.instances).toHaveLength(0);
  });

  it("reconnects after the last observed sequence when SSE drops", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify([runningJob]),
      { status: 200, headers: { "Content-Type": "application/json" } },
    )));
    const { result } = renderHook(
      () => useDurableJob("review-1", "search"),
      { wrapper },
    );

    await vi.waitFor(() => expect(result.current.job?.id).toBe("job-1"));
    await vi.waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    FakeEventSource.instances[0].emit("progress", "5");
    FakeEventSource.instances[0].onerror?.();
    await vi.advanceTimersByTimeAsync(1000);

    expect(FakeEventSource.instances).toHaveLength(2);
    expect(FakeEventSource.instances[1].url).toBe("/api/v1/jobs/job-1/events?after=5");
  });
});
