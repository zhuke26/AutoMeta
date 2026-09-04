import type { StageId } from "../components/StageRail";


const stageCopy: Record<StageId, { title: string; action: string; description: string }> = {
  search: {
    title: "Search Agent",
    action: "Run Search",
    description: "Query composition and PubMed retrieval will be enabled after the real workflow is migrated.",
  },
  screening: {
    title: "Screening Agent",
    action: "Run Screening",
    description: "Evidence-backed ranking and human study selection are not yet available in this React screen.",
  },
  extraction: {
    title: "Extraction Agent",
    action: "Run Extraction",
    description: "PDF upload and source-linked extraction will be enabled after the real workflow is migrated.",
  },
  meta_analysis: {
    title: "Meta-analysis Agent",
    action: "Run Meta-analysis",
    description: "Plan approval and deterministic calculation will be enabled after the real workflow is migrated.",
  },
};


export function StagePendingPage({ stage }: { stage: StageId }) {
  const copy = stageCopy[stage];
  return (
    <main className="page-stack stage-page">
      <header className="page-heading">
        <div>
          <p className="eyebrow">Workflow migration pending</p>
          <h1>{copy.title}</h1>
          <p>{copy.description}</p>
        </div>
      </header>
      <section className="panel pending-panel">
        <h2>Stage unavailable in this build</h2>
        <p>No placeholder action will run or fabricate results.</p>
        <button className="button button--primary" disabled type="button">{copy.action}</button>
      </section>
    </main>
  );
}
