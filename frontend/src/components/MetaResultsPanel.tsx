interface MetaResult {
  csv_file: string;
  outcome_name?: string;
  pooled_effect?: { model_used: string; effect_measure: string; effect: number; ci_lower: number; ci_upper: number; p_value?: number | null } | null;
  heterogeneity?: { q?: number | null; df?: number | null; p_value?: number | null; i2_percent?: number | null; tau2?: number | null } | null;
  study_effects?: Array<{ study_label: string; effect: number; ci_lower: number; ci_upper: number; weight_percent?: number | null }>;
  logs?: string[];
  warnings?: string[];
}


function number(value: number | null | undefined, digits = 3) {
  return value == null ? "—" : value.toFixed(digits);
}


export function MetaResultsPanel({ results, generatedCode }: { results: MetaResult[]; generatedCode: Record<string, string> }) {
  return <section className="meta-results">{results.map((result) => (
    <article className="panel meta-result-card" key={result.csv_file}>
      <header className="section-heading"><div><p className="eyebrow">{result.csv_file}</p><h2>{result.outcome_name || "Meta-analysis result"}</h2></div></header>
      {result.pooled_effect ? <dl aria-label={`${result.outcome_name || result.csv_file} statistical summary`} className="meta-stat-grid">
        <div><dt>Pooled effect</dt><dd>{number(result.pooled_effect.effect)}</dd></div>
        <div><dt>95% CI</dt><dd>{number(result.pooled_effect.ci_lower)} to {number(result.pooled_effect.ci_upper)}</dd></div>
        <div><dt>Model</dt><dd>{result.pooled_effect.model_used}</dd></div>
        <div><dt>Measure</dt><dd>{result.pooled_effect.effect_measure}</dd></div>
        <div><dt>Q</dt><dd>{number(result.heterogeneity?.q)}</dd></div>
        <div><dt>I²</dt><dd>{number(result.heterogeneity?.i2_percent, 1)}%</dd></div>
        <div><dt>Tau²</dt><dd>{number(result.heterogeneity?.tau2)}</dd></div>
      </dl> : <p className="form-error">No pooled estimate was produced.</p>}
      {result.study_effects?.length ? <div className="table-scroll"><table className="status-table"><thead><tr><th>Study</th><th>Effect</th><th>95% CI</th><th>Weight</th></tr></thead><tbody>{result.study_effects.map((study) => <tr key={study.study_label}><td>{study.study_label}</td><td>{number(study.effect)}</td><td>{number(study.ci_lower)} to {number(study.ci_upper)}</td><td>{study.weight_percent == null ? "—" : `${number(study.weight_percent, 1)}%`}</td></tr>)}</tbody></table></div> : null}
      {result.warnings?.length ? <div className="plan-notes plan-notes--warning"><strong>Warnings</strong><ul>{result.warnings.map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
      {result.logs?.length ? <div className="plan-notes"><strong>Run log</strong><ul>{result.logs.map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
      {generatedCode[result.csv_file] ? <details><summary>Generated calculation code</summary><pre className="code-block">{generatedCode[result.csv_file]}</pre></details> : null}
    </article>
  ))}</section>;
}
