import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

import { AutoMetaLogo } from "./AutoMetaLogo";
import { ProvenanceRail, type ProvenanceArtifact, type ProvenanceState } from "./ProvenanceRail";
import { StageRail, type StageId, type StageState } from "./StageRail";


interface AppShellProps {
  children: ReactNode;
  reviewId?: string;
  reviewLabel?: string;
  activeStage?: StageId;
  stageStates?: Partial<Record<StageId, StageState>>;
  provenanceStates?: Partial<Record<ProvenanceArtifact, ProvenanceState>>;
}


export function AppShell({
  children,
  reviewId,
  reviewLabel,
  activeStage,
  stageStates,
  provenanceStates,
}: AppShellProps) {
  const showWorkflow = Boolean(
    reviewLabel || activeStage || Object.keys(stageStates ?? {}).length,
  );
  return (
    <div className="app-shell">
      <header className="topbar">
        <NavLink aria-label="AutoMeta Library" className="brand" to="/library">
          <AutoMetaLogo />
          <span className="brand__name">AutoMeta</span>
        </NavLink>
        <span className="brand__descriptor">Evidence synthesis workspace</span>
        {reviewLabel ? (
          <span className="review-chip">
            <strong>Review</strong>
            <span aria-hidden="true" />
            {reviewLabel}
          </span>
        ) : null}
        <nav aria-label="Primary navigation" className="topbar__nav">
          <NavLink to="/reviews/new">New review</NavLink>
          <NavLink to="/library">Library</NavLink>
          <NavLink to="/system">System status</NavLink>
        </nav>
        <span className="version-badge">v0.1.0</span>
      </header>
      {showWorkflow ? (
        <StageRail reviewId={reviewId} activeStage={activeStage} stageStates={stageStates} />
      ) : null}
      <div className="workspace-canvas">{children}</div>
      {showWorkflow ? <ProvenanceRail states={provenanceStates} /> : null}
    </div>
  );
}
