import { useMemo, useState } from "react";

import type { SearchRecord } from "./RecordsTable";


export interface ScreeningDecision {
  pmid: string;
  title: string;
  final_decision: string;
  decision_stage: string;
  score_result?: {
    scores?: Record<string, number>;
    confidence?: Record<string, number>;
    evidence?: Record<string, string>;
    weighted_score?: number;
    max_score?: number;
    reasoning?: string;
  } | null;
}


export function ScreeningTable({
  decisions,
  papers,
  selected,
  onToggle,
}: {
  decisions: ScreeningDecision[];
  papers: SearchRecord[];
  selected: Set<string>;
  onToggle: (pmid: string) => void;
}) {
  const [filter, setFilter] = useState("");
  const [sort, setSort] = useState("score-desc");
  const paperMap = useMemo(() => new Map(papers.map((paper) => [paper.pmid, paper])), [papers]);
  const visible = useMemo(() => {
    const needle = filter.trim().toLocaleLowerCase();
    const rows = needle
      ? decisions.filter((decision) => [decision.title, decision.pmid]
        .some((value) => value.toLocaleLowerCase().includes(needle)))
      : [...decisions];
    rows.sort((left, right) => {
      if (sort === "title") return left.title.localeCompare(right.title);
      const delta = (right.score_result?.weighted_score ?? -Infinity)
        - (left.score_result?.weighted_score ?? -Infinity);
      return sort === "score-asc" ? -delta : delta;
    });
    return rows;
  }, [decisions, filter, sort]);

  return (
    <div>
      <div className="records-toolbar">
        <input
          aria-label="Filter screening records"
          className="text-input"
          onChange={(event) => setFilter(event.target.value)}
          placeholder="Filter title or PMID"
          type="search"
          value={filter}
        />
        <select aria-label="Sort screening records" className="text-input" onChange={(event) => setSort(event.target.value)} value={sort}>
          <option value="score-desc">Highest score</option>
          <option value="score-asc">Lowest score</option>
          <option value="title">Title</option>
        </select>
        <span>{visible.length} records</span>
      </div>
      <div className="table-scroll">
        <table className="screening-table">
          <thead><tr><th>Select</th><th>Record</th><th>P</th><th>I</th><th>C</th><th>O</th><th>Score</th><th>Assessment</th></tr></thead>
          <tbody>
            {visible.map((decision) => {
              const paper = paperMap.get(decision.pmid);
              const scores = decision.score_result?.scores ?? {};
              const evidence = decision.score_result?.evidence ?? {};
              return (
                <tr key={decision.pmid}>
                  <td><input aria-label={`Select ${decision.title}`} checked={selected.has(decision.pmid)} onChange={() => onToggle(decision.pmid)} type="checkbox" /></td>
                  <td><strong>{decision.title}</strong><small>{decision.pmid}{paper?.year ? ` · ${paper.year}` : ""}</small></td>
                  {(["P", "I", "C", "O"] as const).map((dimension) => (
                    <td key={dimension}><strong>{scores[dimension] ?? "—"}</strong><small>{evidence[dimension] || "No evidence"}</small></td>
                  ))}
                  <td>{decision.score_result ? `${decision.score_result.weighted_score ?? 0} / ${decision.score_result.max_score ?? 0}` : "—"}</td>
                  <td><span className={`decision-badge decision-badge--${decision.final_decision.toLowerCase()}`}>{decision.final_decision}</span></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
