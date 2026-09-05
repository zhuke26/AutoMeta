interface Comparison {
  seed_query?: string;
  expanded_query?: string;
  added_terms?: string[];
  removed_terms?: string[];
  seed_result_count?: number | null;
  expanded_result_count?: number | null;
  known_study_total?: number;
  seed_known_hits?: number | null;
  expanded_known_hits?: number | null;
}


export function SearchStrategyComparison({ payload }: { payload: Record<string, unknown> }) {
  const comparison = payload.comparison as Comparison | undefined;
  if (!comparison) return null;
  const knownTotal = comparison.known_study_total ?? 0;
  return (
    <section aria-label="Retrieval feedback comparison" className="panel strategy-comparison">
      <header className="section-heading"><div><p className="eyebrow">Retrieval feedback</p><h2>Seed and expanded strategy</h2></div></header>
      <div className="strategy-counts">
        <div><span>Seed results</span><strong>{comparison.seed_result_count ?? "—"}</strong></div>
        <div><span>Expanded results</span><strong>{comparison.expanded_result_count ?? "—"}</strong></div>
        {knownTotal > 0 ? <div><span>Known-study coverage</span><strong>{comparison.seed_known_hits ?? 0}/{knownTotal} → {comparison.expanded_known_hits ?? 0}/{knownTotal}</strong></div> : null}
      </div>
      <div className="strategy-query-grid">
        <article><h3>Seed query</h3><pre>{comparison.seed_query}</pre></article>
        <article><h3>Expanded query</h3><pre>{comparison.expanded_query}</pre></article>
      </div>
      <div className="term-diff"><div><strong>Added terms</strong><p>{comparison.added_terms?.length ? comparison.added_terms.join(" · ") : "None"}</p></div><div><strong>Removed terms</strong><p>{comparison.removed_terms?.length ? comparison.removed_terms.join(" · ") : "None"}</p></div></div>
    </section>
  );
}
