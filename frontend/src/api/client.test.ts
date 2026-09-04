import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiRequest } from "./client";


afterEach(() => {
  vi.unstubAllGlobals();
});


describe("apiRequest", () => {
  it("prefixes requests with the versioned API root and returns JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiRequest<{ status: string }>("/system/status")).resolves.toEqual({ status: "ok" });
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/system/status", expect.any(Object));
  });

  it("returns undefined for a 204 response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await expect(apiRequest<void>("/reviews/one", { method: "DELETE" })).resolves.toBeUndefined();
  });

  it("surfaces structured API errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Review not found" }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(apiRequest("/reviews/missing")).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
      message: "Review not found",
    });
  });

  it("wraps network failures without leaking request state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    await expect(apiRequest("/reviews")).rejects.toEqual(
      new ApiError("Unable to reach the local AutoMeta server", 0),
    );
  });
});
