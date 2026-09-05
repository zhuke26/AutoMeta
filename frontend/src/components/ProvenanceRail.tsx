const artifacts = [
  "PICO",
  "Query",
  "Records",
  "Selected studies",
  "Sources",
  "Plan",
  "Code",
  "Result",
] as const;

export type ProvenanceArtifact = (typeof artifacts)[number];
export type ProvenanceState = "not_started" | "draft" | "approved" | "stale";


interface ProvenanceRailProps {
  completed?: ReadonlyArray<ProvenanceArtifact>;
  reviewId?: string;
  states?: Partial<Record<ProvenanceArtifact, ProvenanceState>>;
}


export function ProvenanceRail({ completed = [], reviewId, states = {} }: ProvenanceRailProps) {
  const completedSet = new Set(completed);
  return (
    <footer className="provenance-rail">
      {reviewId ? <Link className="provenance-rail__label" to={`/reviews/${reviewId}/provenance`}>Evidence provenance</Link> : <span className="provenance-rail__label">Evidence provenance</span>}
      <ol>
        {artifacts.map((artifact) => {
          const state = states[artifact] ?? (completedSet.has(artifact) ? "approved" : "not_started");
          const label = state.replaceAll("_", " ");
          return (
            <li aria-label={`${artifact} ${label}`} data-state={state} key={artifact}>
              <span aria-hidden="true" className="provenance-rail__tick" />
              <span>{artifact}</span>
              <small>{label}</small>
            </li>
          );
        })}
      </ol>
    </footer>
  );
}
import { Link } from "react-router-dom";
