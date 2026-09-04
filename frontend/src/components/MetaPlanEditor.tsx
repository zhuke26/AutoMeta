export interface MetaPlan {
  csv_file: string;
  outcome_name: string;
  method_text: string;
  analysis_type: string;
  effect_measure: string;
  effect_source: string;
  model: Record<string, unknown>;
  columns: Record<string, unknown>;
  continuity_correction?: Record<string, unknown> | null;
  exclusion_rules?: string[];
  output?: Record<string, unknown>;
  assumptions?: string[];
  warnings?: string[];
}


export function MetaPlanEditor({
  plan,
  onChange,
}: {
  plan: MetaPlan;
  onChange: (plan: MetaPlan) => void;
}) {
  const update = (key: keyof MetaPlan, value: unknown) => onChange({ ...plan, [key]: value });
  return (
    <article className="meta-plan-card">
      <header><div><p className="eyebrow">Dataset</p><h3>{plan.csv_file}</h3></div><span>{plan.analysis_type.replaceAll("_", " ")}</span></header>
      <label><span className="field-label">Outcome name</span><input className="text-input" onChange={(event) => update("outcome_name", event.target.value)} value={plan.outcome_name} /></label>
      <label><span className="field-label">Method description</span><textarea aria-label={`Method description for ${plan.csv_file}`} className="text-input" onChange={(event) => update("method_text", event.target.value)} rows={4} value={plan.method_text} /></label>
      <div className="meta-plan-selects">
        <label><span className="field-label">Analysis type</span><select aria-label={`Analysis type for ${plan.csv_file}`} className="text-input" onChange={(event) => update("analysis_type", event.target.value)} value={plan.analysis_type}><option value="dichotomous">Dichotomous</option><option value="continuous">Continuous</option><option value="generic_effect">Generic effect</option></select></label>
        <label><span className="field-label">Effect measure</span><select aria-label={`Effect measure for ${plan.csv_file}`} className="text-input" onChange={(event) => update("effect_measure", event.target.value)} value={plan.effect_measure}>{["OR", "RR", "RD", "MD", "SMD", "Hedges_g"].map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <label><span className="field-label">Effect source</span><select aria-label={`Effect source for ${plan.csv_file}`} className="text-input" onChange={(event) => update("effect_source", event.target.value)} value={plan.effect_source}><option value="arm_level_data">Arm-level data</option><option value="reported_effect_and_ci">Reported effect and CI</option><option value="reported_effect_and_se">Reported effect and SE</option><option value="reported_effect_and_variance">Reported effect and variance</option></select></label>
        <label><span className="field-label">Pooling model</span><select aria-label={`Pooling model for ${plan.csv_file}`} className="text-input" onChange={(event) => update("model", { ...plan.model, type: event.target.value })} value={String(plan.model.type ?? "auto_by_i2")}><option value="fixed">Fixed</option><option value="random">Random</option><option value="auto_by_i2">Auto by I²</option></select></label>
      </div>
      <fieldset className="column-mapping"><legend>Column mapping</legend>{Object.entries(plan.columns).map(([role, column]) => <label key={role}><span className="field-label">{role.replaceAll("_", " ")}</span><input className="text-input mono-value" onChange={(event) => update("columns", { ...plan.columns, [role]: event.target.value || null })} value={String(column ?? "")} /></label>)}</fieldset>
      {plan.assumptions?.length ? <div className="plan-notes"><strong>Assumptions</strong><ul>{plan.assumptions.map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
      {plan.warnings?.length ? <div className="plan-notes plan-notes--warning"><strong>Warnings</strong><ul>{plan.warnings.map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
    </article>
  );
}
