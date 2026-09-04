import { Link } from "react-router-dom";


export type StageId = "search" | "screening" | "extraction" | "meta_analysis";
export type StageState =
  | "not_started"
  | "running"
  | "draft"
  | "awaiting_approval"
  | "approved"
  | "failed"
  | "interrupted"
  | "stale";

interface StageRailProps {
  reviewId?: string;
  activeStage?: StageId;
  stageStates?: Partial<Record<StageId, StageState>>;
}

const stages: Array<{
  id: StageId;
  index: string;
  name: string;
  tool: string;
  output?: string;
  checkpoint?: string;
}> = [
  {
    id: "search",
    index: "01",
    name: "Search Agent",
    tool: "Field-tagged Query Composer · PubMed Search",
    output: "Retrieved records",
    checkpoint: "Review & edit",
  },
  {
    id: "screening",
    index: "02",
    name: "Screening Agent",
    tool: "PICO-wise Eligibility Matcher",
    output: "Selected studies",
    checkpoint: "Reviewer select",
  },
  {
    id: "extraction",
    index: "03",
    name: "Extraction Agent",
    tool: "Full-text Structure Parser · Evidence Span Locator",
    output: "Source-linked values",
    checkpoint: "Human review",
  },
  {
    id: "meta_analysis",
    index: "04",
    name: "Meta-analysis Agent",
    tool: "Auditable Code Executor",
  },
];


const stageRoutes: Record<StageId, string> = {
  search: "search",
  screening: "screening",
  extraction: "extraction",
  meta_analysis: "meta-analysis",
};


function stateLabel(state: StageState) {
  return state.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}


export function StageRail({ reviewId, activeStage, stageStates = {} }: StageRailProps) {
  return (
    <nav aria-label="Review stages" className="stage-rail">
      {stages.map((stage) => {
        const state = stageStates[stage.id] ?? (stage.id === activeStage ? "running" : "not_started");
        const card = (
          <div
            className={`stage-card stage-card--${stage.id}`}
            data-stage={stage.id}
            data-state={state}
          >
            <div className="stage-card__title">
              <span aria-hidden="true" className="stage-card__mark" />
              <span className="stage-card__index">{stage.index}</span>
              <span>{stage.name}</span>
              <span className="stage-card__state">{stateLabel(state)}</span>
            </div>
            <div className="stage-card__tool">{stage.tool}</div>
          </div>
        );
        return (
          <div className="stage-segment" key={stage.id}>
            {reviewId ? (
              <Link
                aria-label={`${stage.name} — ${stateLabel(state)}`}
                className="stage-card-link"
                to={`/reviews/${reviewId}/${stageRoutes[stage.id]}`}
              >
                {card}
              </Link>
            ) : card}
            {stage.output ? (
              <div className="stage-handoff" aria-label={`${stage.output}: ${stage.checkpoint}`}>
                <span>{stage.output}</span>
                <span aria-hidden="true" className="stage-handoff__line" />
                <strong>✓ {stage.checkpoint}</strong>
              </div>
            ) : null}
          </div>
        );
      })}
    </nav>
  );
}
