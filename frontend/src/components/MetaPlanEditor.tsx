interface MetaModel {
  type?: string;
  fixed_method?: string;
  random_method?: string;
  i2_threshold?: number;
}

interface ContinuityCorrection {
  enabled: boolean;
  value: number;
  apply_when: string;
}

interface MetaOutputs {
  include_study_effects: boolean;
  include_weights: boolean;
  include_pooled_effect: boolean;
  include_heterogeneity: boolean;
  include_output_csv: boolean;
  include_prediction_interval: boolean;
  include_leave_one_out: boolean;
  include_subgroup: boolean;
  include_forest_plot: boolean;
}

export interface MetaPlan {
  csv_file: string;
  outcome_name: string;
  method_text: string;
  analysis_type: string;
  effect_measure: string;
  effect_source: string;
  model: MetaModel;
  columns: Record<string, unknown>;
  subgroup_column?: string | null;
  continuity_correction?: ContinuityCorrection | null;
  exclusion_rules?: string[];
  output?: Partial<MetaOutputs>;
  assumptions?: string[];
  warnings?: string[];
}

const defaultOutputs: MetaOutputs = {
  include_study_effects: true,
  include_weights: true,
  include_pooled_effect: true,
  include_heterogeneity: true,
  include_output_csv: true,
  include_prediction_interval: false,
  include_leave_one_out: false,
  include_subgroup: false,
  include_forest_plot: false,
};

const outputLabels: Array<[keyof MetaOutputs, string]> = [
  ["include_study_effects", "Include study effects"],
  ["include_weights", "Include study weights"],
  ["include_pooled_effect", "Include pooled effect"],
  ["include_heterogeneity", "Include heterogeneity statistics"],
  ["include_output_csv", "Include result CSV"],
  ["include_prediction_interval", "Include prediction interval"],
  ["include_leave_one_out", "Include leave-one-out analysis"],
  ["include_subgroup", "Include subgroup analysis"],
  ["include_forest_plot", "Include forest plot"],
];

export function MetaPlanEditor({
  plan,
  onChange,
}: {
  plan: MetaPlan;
  onChange: (plan: MetaPlan) => void;
}) {
  const model = {
    type: "auto_by_i2",
    fixed_method: "inverse_variance",
    random_method: "dersimonian_laird",
    i2_threshold: 50,
    ...plan.model,
  };
  const output = { ...defaultOutputs, ...plan.output };
  const correction = plan.continuity_correction ?? {
    enabled: false,
    value: 0.5,
    apply_when: "zero_cell",
  };
  const supportsCorrection = plan.analysis_type === "dichotomous"
    && plan.effect_source === "arm_level_data";
  const update = (key: keyof MetaPlan, value: unknown) => {
    onChange({ ...plan, [key]: value });
  };
  const updateModel = (key: keyof MetaModel, value: string | number) => {
    const nextOutput = key === "type" && value === "fixed"
      ? { ...output, include_prediction_interval: false }
      : output;
    onChange({
      ...plan,
      model: { ...model, [key]: value },
      output: nextOutput,
    });
  };
  const updateOutput = (key: keyof MetaOutputs, checked: boolean) => {
    const next = { ...output, [key]: checked };
    if (key === "include_forest_plot" && checked) {
      next.include_study_effects = true;
      next.include_pooled_effect = true;
    }
    if (
      (key === "include_study_effects" || key === "include_pooled_effect")
      && !checked
    ) {
      next.include_forest_plot = false;
    }
    update("output", next);
  };
  return (
    <article className="meta-plan-card">
      <header><div><p className="eyebrow">Dataset</p><h3>{plan.csv_file}</h3></div><span>{plan.analysis_type.replaceAll("_", " ")}</span></header>
      <label><span className="field-label">Outcome name</span><input className="text-input" onChange={(event) => update("outcome_name", event.target.value)} value={plan.outcome_name} /></label>
      <label><span className="field-label">Method description</span><textarea aria-label={`Method description for ${plan.csv_file}`} className="text-input" onChange={(event) => update("method_text", event.target.value)} rows={4} value={plan.method_text} /></label>
      <div className="meta-plan-selects">
        <label><span className="field-label">Analysis type</span><select aria-label={`Analysis type for ${plan.csv_file}`} className="text-input" onChange={(event) => update("analysis_type", event.target.value)} value={plan.analysis_type}><option value="dichotomous">Dichotomous</option><option value="continuous">Continuous</option><option value="generic_effect">Generic effect</option></select></label>
        <label><span className="field-label">Effect measure</span><select aria-label={`Effect measure for ${plan.csv_file}`} className="text-input" onChange={(event) => update("effect_measure", event.target.value)} value={plan.effect_measure}>{["OR", "RR", "RD", "MD", "SMD", "Hedges_g"].map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <label><span className="field-label">Effect source</span><select aria-label={`Effect source for ${plan.csv_file}`} className="text-input" onChange={(event) => update("effect_source", event.target.value)} value={plan.effect_source}><option value="arm_level_data">Arm-level data</option><option value="reported_effect_and_ci">Reported effect and CI</option><option value="reported_effect_and_se">Reported effect and SE</option><option value="reported_effect_and_variance">Reported effect and variance</option></select></label>
        <label><span className="field-label">Pooling model</span><select aria-label={`Pooling model for ${plan.csv_file}`} className="text-input" onChange={(event) => updateModel("type", event.target.value)} value={model.type}><option value="fixed">Fixed</option><option value="random">Random</option><option value="auto_by_i2">Auto by I²</option></select></label>
        <label><span className="field-label">Fixed-effect estimator</span><select aria-label={`Fixed-effect estimator for ${plan.csv_file}`} className="text-input" disabled value={model.fixed_method}><option value="inverse_variance">Inverse variance</option></select></label>
        <label><span className="field-label">Random-effects estimator</span><select aria-label={`Random-effects estimator for ${plan.csv_file}`} className="text-input" onChange={(event) => updateModel("random_method", event.target.value)} value={model.random_method}><option value="dersimonian_laird">DerSimonian-Laird</option><option value="restricted_maximum_likelihood">REML</option></select></label>
        <label><span className="field-label">Auto-model I² threshold</span><input aria-label={`Auto-model I² threshold for ${plan.csv_file}`} className="text-input" max={100} min={0} onChange={(event) => updateModel("i2_threshold", Number(event.target.value))} type="number" value={model.i2_threshold} /></label>
        <label><span className="field-label">Subgroup column</span><input aria-label={`Subgroup column for ${plan.csv_file}`} className="text-input mono-value" onChange={(event) => {
          const value = event.target.value || null;
          onChange({
            ...plan,
            subgroup_column: value,
            output: value ? output : { ...output, include_subgroup: false },
          });
        }} value={plan.subgroup_column ?? ""} /></label>
      </div>
      <fieldset className="column-mapping"><legend>Column mapping</legend>{Object.entries(plan.columns).map(([role, column]) => <label key={role}><span className="field-label">{role.replaceAll("_", " ")}</span><input className="text-input mono-value" onChange={(event) => update("columns", { ...plan.columns, [role]: event.target.value || null })} value={String(column ?? "")} /></label>)}</fieldset>
      {supportsCorrection ? <fieldset className="meta-plan-options"><legend>Continuity correction</legend>
        <label><input aria-label={`Enable continuity correction for ${plan.csv_file}`} checked={correction.enabled} onChange={(event) => update("continuity_correction", { ...correction, enabled: event.target.checked })} type="checkbox" />Enable correction</label>
        <label><span className="field-label">Correction value</span><input aria-label={`Continuity correction value for ${plan.csv_file}`} className="text-input" disabled={!correction.enabled} min={0} onChange={(event) => update("continuity_correction", { ...correction, value: Number(event.target.value) })} step="0.1" type="number" value={correction.value} /></label>
        <label><span className="field-label">Apply when</span><select aria-label={`Continuity correction rule for ${plan.csv_file}`} className="text-input" disabled={!correction.enabled} onChange={(event) => update("continuity_correction", { ...correction, apply_when: event.target.value })} value={correction.apply_when}><option value="zero_cell">A zero cell is present</option><option value="always">Always</option><option value="never">Never</option></select></label>
      </fieldset> : null}
      <fieldset className="meta-output-options"><legend>Requested outputs</legend>{outputLabels.map(([key, label]) => <label key={key}><input aria-label={`${label} for ${plan.csv_file}`} checked={output[key]} disabled={key === "include_subgroup" && !plan.subgroup_column} onChange={(event) => updateOutput(key, event.target.checked)} type="checkbox" />{label.replace(/^Include /, "")}</label>)}<p className="field-help meta-output-options__help">Forest plots support up to 100 studies; leave-one-out supports up to 200.</p></fieldset>
      {plan.assumptions?.length ? <div className="plan-notes"><strong>Assumptions</strong><ul>{plan.assumptions.map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
      {plan.warnings?.length ? <div className="plan-notes plan-notes--warning"><strong>Warnings</strong><ul>{plan.warnings.map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
    </article>
  );
}
