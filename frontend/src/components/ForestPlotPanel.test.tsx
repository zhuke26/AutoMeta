import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ForestPlotPanel } from "./ForestPlotPanel";


describe("ForestPlotPanel", () => {
  it("previews the Review-owned SVG and exposes every generated format", () => {
    render(<ForestPlotPanel
      figures={[
        { file_id: "svg-1", filename: "forest-plot-01.svg", mime_type: "image/svg+xml" },
        { file_id: "png-1", filename: "forest-plot-01.png", mime_type: "image/png" },
        { file_id: "pdf-1", filename: "forest-plot-01.pdf", mime_type: "application/pdf" },
      ]}
      outcomeName="Recovery"
      reviewId="review-1"
    />);

    expect(screen.getByRole("img", { name: "Recovery forest plot" })).toHaveAttribute(
      "src",
      "/api/v1/reviews/review-1/figures/svg-1/content",
    );
    expect(screen.getByRole("link", { name: "Download SVG" })).toHaveAttribute("download", "forest-plot-01.svg");
    expect(screen.getByRole("link", { name: "Download PNG" })).toHaveAttribute("href", "/api/v1/reviews/review-1/figures/png-1/content");
    expect(screen.getByRole("link", { name: "Download PDF" })).toHaveAttribute("href", "/api/v1/reviews/review-1/figures/pdf-1/content");
  });

  it("states that a forest plot is unavailable instead of fabricating one", () => {
    render(<ForestPlotPanel figures={[]} outcomeName="Recovery" reviewId="review-1" />);

    expect(screen.getByText("Forest plot unavailable for this result.")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
