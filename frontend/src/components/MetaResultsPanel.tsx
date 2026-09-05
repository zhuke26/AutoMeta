import { ForestPlotPanel, type FigureFile } from "./ForestPlotPanel";


interface PooledEffect {
  model_used: string;
  effect_measure: string;
  effect: number;
  ci_lower: number;
  ci_upper: number;
  p_value?: number | null;
}


interface Heterogeneity {
  q?: number | null;
  df?: number | null;
  p_value?: number | null;
  i2_percent?: number | null;
  tau2?: number | null;
  tau?: number | null;
}


interface MetaResult {
  csv_file: string;
  outcome_name?: string;
  pooled_effect?: PooledEffect | null;
  heterogeneity?: Heterogeneity | null;
  prediction_interval?: { lower: number; upper: number } | null;
  study_effects?: Array<{ study_label: string; effect: number; ci_lower: number; ci_upper: number; weight_percent?: number | null }>;
  leave_one_out?: Array<{ omitted_study: string; pooled_effect: PooledEffect; heterogeneity: Heterogeneity }>;
  subgroup_analysis?: {
    groups: Array<{ label: string; study_count: number; pooled_effect: PooledEffect; heterogeneity: Heterogeneity }>;
    between_group_q: number;
    between_group_df: number;
    between_group_p_value: number;
  } | null;
  figure_files?: FigureFile[];
  logs?: string[];
  warnings?: string[];
}


function number(value: number | null | undefined, digits = 3) {
  return value == null ? "Not available" : value.toFixed(digits);
}


function interval(value: { lower: number; upper: number } | null | undefined) {
  return value ? `${number(value.lower)} to ${number(value.upper)}` : "Not available";
}


function confidenceInterval(value: PooledEffect) {
  return `${number(value.ci_lower)} to ${number(value.ci_upper)}`;
}


export function MetaResultsPanel({
  results,
  generatedCode,
  reviewId,
}: {
  results: MetaResult[];
  generatedCode: Record<string, string>;
  reviewId: string;
}) {
  return <section className="meta-results">{results.map((result) => (
    <article className="panel meta-result-card" key={result.csv_file}>
      <header className="section-heading"><div><p className="eyebrow">{result.csv_file}</p><h2>{result.outcome_name || "Meta-analysis result"}</h2></div></header>
      {result.pooled_effect ? <dl aria-label={`${result.outcome_name || result.csv_file} statistical summary`} className="meta-stat-grid">
        <div><dt>Pooled effect</dt><dd>{number(result.pooled_effect.effect)}</dd></div>
        <div><dt>95% CI</dt><dd>{number(result.pooled_effect.ci_lower)} to {number(result.pooled_effect.ci_upper)}</dd></div>
        <div><dt>Model</dt><dd>{result.pooled_effect.model_used}</dd></div>
        <div><dt>Measure</dt><dd>{result.pooled_effect.effect_measure}</dd></div>
        <div><dt>Q</dt><dd>{number(result.heterogeneity?.q)}</dd></div>
        <div><dt>Q p-value</dt><dd>{number(result.heterogeneity?.p_value)}</dd></div>
        <div><dt>I²</dt><dd>{result.heterogeneity?.i2_percent == null ? "Not available" : `${number(result.heterogeneity.i2_percent, 1)}%`}</dd></div>
        <div><dt>Tau²</dt><dd>{number(result.heterogeneity?.tau2)}</dd></div>
        <div><dt>Tau</dt><dd>{number(result.heterogeneity?.tau)}</dd></div>
        <div><dt>Prediction interval</dt><dd>{interval(result.prediction_interval)}</dd></div>
      </dl> : <p className="form-error">No pooled estimate was produced.</p>}
      {result.study_effects?.length ? <div className="table-scroll"><table className="status-table"><thead><tr><th>Study</th><th>Effect</th><th>95% CI</th><th>Weight</th></tr></thead><tbody>{result.study_effects.map((study) => <tr key={study.study_label}><td>{study.study_label}</td><td>{number(study.effect)}</td><td>{number(study.ci_lower)} to {number(study.ci_upper)}</td><td>{study.weight_percent == null ? "—" : `${number(study.weight_percent, 1)}%`}</td></tr>)}</tbody></table></div> : null}
      {result.leave_one_out?.length ? <section aria-label="Leave-one-out sensitivity" className="meta-diagnostic-section">
        <h3>Leave-one-out sensitivity</h3>
        <div className="table-scroll"><table className="status-table"><thead><tr><th>Omitted study</th><th>Pooled effect</th><th>95% CI</th><th>I²</th></tr></thead><tbody>{result.leave_one_out.map((item) => <tr key={item.omitted_study}><td>{item.omitted_study}</td><td>{number(item.pooled_effect.effect)}</td><td>{confidenceInterval(item.pooled_effect)}</td><td>{item.heterogeneity.i2_percent == null ? "Not available" : `${number(item.heterogeneity.i2_percent, 1)}%`}</td></tr>)}</tbody></table></div>
      </section> : null}
      {result.subgroup_analysis?.groups.length ? <section className="meta-diagnostic-section">
        <h3>Subgroup analysis</h3>
        <p>Between-group Q {number(result.subgroup_analysis.between_group_q)} (df {result.subgroup_analysis.between_group_df}), p = {number(result.subgroup_analysis.between_group_p_value)}</p>
        <div className="table-scroll"><table className="status-table"><thead><tr><th>Subgroup</th><th>Studies</th><th>Pooled effect</th><th>95% CI</th><th>I²</th></tr></thead><tbody>{result.subgroup_analysis.groups.map((group) => <tr key={group.label}><td>{group.label}</td><td>{group.study_count}</td><td>{number(group.pooled_effect.effect)}</td><td>{confidenceInterval(group.pooled_effect)}</td><td>{group.heterogeneity.i2_percent == null ? "Not available" : `${number(group.heterogeneity.i2_percent, 1)}%`}</td></tr>)}</tbody></table></div>
      </section> : null}
      <ForestPlotPanel figures={result.figure_files ?? []} outcomeName={result.outcome_name || result.csv_file} reviewId={reviewId} />
      {result.warnings?.length ? <div className="plan-notes plan-notes--warning"><strong>Warnings</strong><ul>{result.warnings.map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
      {result.logs?.length ? <div className="plan-notes"><strong>Run log</strong><ul>{result.logs.map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
      {generatedCode[result.csv_file] ? <details><summary>Generated calculation code</summary><pre className="code-block">{generatedCode[result.csv_file]}</pre></details> : null}
    </article>
  ))}</section>;
}
