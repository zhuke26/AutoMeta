import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MetaResultsPanel } from "./MetaResultsPanel";


describe("MetaResultsPanel", () => {
  it("labels undefined diagnostics and does not invent numeric values", () => {
    render(<MetaResultsPanel
      generatedCode={{}}
      results={[{
        csv_file: "single-study.csv",
        outcome_name: "Single-study outcome",
        pooled_effect: {
          model_used: "fixed",
          effect_measure: "MD",
          effect: 1,
          ci_lower: 0.5,
          ci_upper: 1.5,
        },
      }]}
      reviewId="review-1"
    />);

    const summary = screen.getByLabelText("Single-study outcome statistical summary");
    for (const label of ["Q", "Q p-value", "I²", "Tau²", "Tau", "Prediction interval"]) {
      const row = within(summary).getByText(label).closest("div");
      expect(row).toHaveTextContent("Not available");
    }
    expect(screen.getByText("Forest plot unavailable for this result.")).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /forest plot/i })).not.toBeInTheDocument();
  });
});
