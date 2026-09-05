import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { MetaPlanEditor, type MetaPlan } from "./MetaPlanEditor";


const plan: MetaPlan = {
  csv_file: "effects.csv",
  outcome_name: "Recovery",
  method_text: "Prespecified analysis",
  analysis_type: "dichotomous",
  effect_measure: "OR",
  effect_source: "arm_level_data",
  model: {
    type: "random",
    fixed_method: "inverse_variance",
    random_method: "dersimonian_laird",
    i2_threshold: 50,
  },
  columns: { study_label: "study", experimental_events: "events_t", experimental_total: "n_t", control_events: "events_c", control_total: "n_c" },
  subgroup_column: null,
  continuity_correction: { enabled: false, value: 0.5, apply_when: "zero_cell" },
  output: {
    include_study_effects: true,
    include_weights: true,
    include_pooled_effect: true,
    include_heterogeneity: true,
    include_output_csv: true,
    include_prediction_interval: false,
    include_leave_one_out: false,
    include_subgroup: false,
    include_forest_plot: false,
  },
};


function Harness() {
  const [value, setValue] = useState(plan);
  return <><MetaPlanEditor onChange={setValue} plan={value} /><output>{JSON.stringify(value)}</output></>;
}


describe("MetaPlanEditor", () => {
  it("exposes estimators, subgroup mapping, continuity correction, and advanced outputs", async () => {
    render(<Harness />);

    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: "Random-effects estimator for effects.csv" }),
      "restricted_maximum_likelihood",
    );
    await userEvent.type(
      screen.getByRole("textbox", { name: "Subgroup column for effects.csv" }),
      "group",
    );
    await userEvent.click(screen.getByRole("checkbox", { name: "Enable continuity correction for effects.csv" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Include prediction interval for effects.csv" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Include leave-one-out analysis for effects.csv" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Include subgroup analysis for effects.csv" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Include forest plot for effects.csv" }));

    expect(screen.getByText("Forest plots support up to 100 studies; leave-one-out supports up to 200.")).toBeInTheDocument();
    const value = screen.getByRole("status").textContent ?? "";
    expect(value).toContain('"random_method":"restricted_maximum_likelihood"');
    expect(value).toContain('"subgroup_column":"group"');
    expect(value).toContain('"enabled":true');
    expect(value).toContain('"include_prediction_interval":true');
    expect(value).toContain('"include_leave_one_out":true');
    expect(value).toContain('"include_subgroup":true');
    expect(value).toContain('"include_forest_plot":true');
  });
});
