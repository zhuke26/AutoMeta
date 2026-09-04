import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { artifactKeys, currentArtifact } from "../api/artifacts";
import { useStartWorkflowJob } from "../api/workflows";
import { useRenameReview } from "../api/reviews";
import type { ArtifactView, ReviewEntryMode } from "../api/types";
import { ArtifactApprovalBar } from "../components/ArtifactApprovalBar";
import { JobProgressPanel } from "../components/JobProgressPanel";
import { useAutosavedArtifact } from "../hooks/useAutosavedArtifact";
import { useDurableJob } from "../hooks/useDurableJob";
import { useReviewWorkspace } from "./ReviewWorkspace";


const modeLabels: Record<ReviewEntryMode, string> = {
  guided: "Guided Review",
  search: "Search",
  screening: "Screening",
  extraction: "Extraction",
  meta_analysis: "Meta-analysis",
};

interface PicoDraft {
  research_question: string;
  pico: { P: string; I: string; C: string; O: string };
  recommended_outcomes: unknown[];
  rationale: string;
}


const emptyDraft: PicoDraft = {
  research_question: "",
  pico: { P: "", I: "", C: "", O: "" },
  recommended_outcomes: [],
  rationale: "",
};


function stringValue(value: unknown) {
  return typeof value === "string" ? value : "";
}


function draftFromArtifact(artifact: ArtifactView | undefined): PicoDraft {
  if (!artifact) {
    return emptyDraft;
  }
  const pico = artifact.payload.pico;
  const picoRecord = pico && typeof pico === "object" ? pico as Record<string, unknown> : {};
  return {
    research_question: stringValue(artifact.payload.research_question),
    pico: {
      P: stringValue(picoRecord.P),
      I: stringValue(picoRecord.I),
      C: stringValue(picoRecord.C),
      O: stringValue(picoRecord.O),
    },
    recommended_outcomes: Array.isArray(artifact.payload.recommended_outcomes)
      ? artifact.payload.recommended_outcomes
      : [],
    rationale: stringValue(artifact.payload.rationale),
  };
}


export function ReviewSetupPage() {
  const { artifacts, review } = useReviewWorkspace();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(review.name);
  const picoArtifact = artifacts.find((artifact) => artifact.kind === "question_pico");
  const [draft, setDraft] = useState<PicoDraft>(() => draftFromArtifact(picoArtifact));
  const [draftChanged, setDraftChanged] = useState(false);
  const hydratedVersion = useRef(picoArtifact?.version);
  const renameReview = useRenameReview();
  const protocolJob = useDurableJob(review.id, "protocol");
  const startProtocol = useStartWorkflowJob(
    review.id,
    "protocol",
    "protocol/draft",
  );
  const queryClient = useQueryClient();
  const payload = useMemo(() => ({
    research_question: draft.research_question,
    pico: draft.pico,
    recommended_outcomes: draft.recommended_outcomes,
    rationale: draft.rationale,
  }), [draft]);
  const autosave = useAutosavedArtifact(
    review.id,
    "question_pico",
    payload,
    draftChanged,
  );
  const effectiveArtifact = currentArtifact(picoArtifact, autosave.artifact);
  const picoComplete = Object.values(draft.pico).every((value) => value.trim());

  useEffect(() => setName(review.name), [review.name]);
  useEffect(() => {
    if (picoArtifact && picoArtifact.version !== hydratedVersion.current) {
      hydratedVersion.current = picoArtifact.version;
      setDraft(draftFromArtifact(picoArtifact));
      setDraftChanged(false);
    }
  }, [picoArtifact]);
  useEffect(() => {
    if (protocolJob.job?.state === "succeeded") {
      queryClient.invalidateQueries({ queryKey: artifactKeys.all(review.id) });
    }
  }, [protocolJob.job?.state, queryClient, review.id]);

  const updateQuestion = (value: string) => {
    setDraft((current) => ({ ...current, research_question: value }));
    setDraftChanged(true);
  };

  const updatePico = (key: keyof PicoDraft["pico"], value: string) => {
    setDraft((current) => ({
      ...current,
      pico: { ...current.pico, [key]: value },
    }));
    setDraftChanged(true);
  };

  const save = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextName = name.trim();
    if (!nextName || nextName === review.name) {
      setName(review.name);
      setEditing(false);
      return;
    }
    renameReview.mutate(
      { reviewId: review.id, name: nextName },
      { onSuccess: () => setEditing(false) },
    );
  };

  return (
    <main className="page-stack review-setup-page">
      <header className="page-heading">
        <div>
          <p className="eyebrow">Review workspace</p>
          <h1>Review setup</h1>
          <p>Confirm the local Review identity before entering a workflow stage.</p>
        </div>
      </header>

      <section aria-label="Review details" className="panel review-details">
        <div className="review-details__heading">
          {editing ? (
            <form className="inline-form" onSubmit={save}>
              <label className="sr-only" htmlFor="workspace-review-name">Review name</label>
              <input
                autoFocus
                className="text-input"
                id="workspace-review-name"
                maxLength={160}
                onChange={(event) => setName(event.target.value)}
                value={name}
              />
              <button className="button button--primary" disabled={!name.trim() || renameReview.isPending} type="submit">
                Save Review name
              </button>
              <button className="button button--quiet" onClick={() => setEditing(false)} type="button">Cancel</button>
            </form>
          ) : (
            <>
              <div>
                <p className="eyebrow">Review</p>
                <h2>{review.name}</h2>
              </div>
              <button className="button button--quiet" onClick={() => setEditing(true)} type="button">
                Edit Review name
              </button>
            </>
          )}
        </div>
        {renameReview.isError ? <p className="form-error" role="alert">{renameReview.error.message}</p> : null}
        <dl className="review-metadata">
          <div><dt>Entry mode</dt><dd>{modeLabels[review.entry_mode]}</dd></div>
          <div><dt>Status</dt><dd className={`status-pill status-pill--${review.status}`}>{review.status.replace(/^./, (value) => value.toUpperCase())}</dd></div>
          <div><dt>Created</dt><dd>{new Date(review.created_at).toLocaleString()}</dd></div>
          <div><dt>Last updated</dt><dd>{new Date(review.updated_at).toLocaleString()}</dd></div>
        </dl>
      </section>

      <section className="panel protocol-editor">
        <header className="protocol-editor__heading">
          <div>
            <p className="eyebrow">Review protocol</p>
            <h2>Research question and PICO</h2>
            <p>Enter PICO manually or ask the configured model to draft fields for review.</p>
          </div>
          <span className="autosave-state" aria-live="polite">
            {autosave.state === "saving" ? "Saving…" : null}
            {autosave.state === "saved" ? "Saved locally" : null}
            {autosave.state === "error" ? "Save failed" : null}
          </span>
        </header>
        <div className="protocol-editor__body">
          <label className="field-label" htmlFor="research-question">Research question</label>
          <textarea
            className="text-input protocol-question"
            id="research-question"
            onChange={(event) => updateQuestion(event.target.value)}
            placeholder="Describe the population, intervention, comparison, and outcomes of interest."
            rows={4}
            value={draft.research_question}
          />
          <div className="protocol-generate-row">
            <span className="field-help">Relevant text is sent only when you start model-assisted drafting.</span>
            <button
              className="button"
              disabled={draft.research_question.trim().length < 10 || protocolJob.isActive || startProtocol.isPending}
              onClick={() => startProtocol.mutate({
                research_question: draft.research_question.trim(),
              })}
              type="button"
            >
              Generate PICO draft
            </button>
          </div>

          <div className="pico-grid">
            {([
              ["P", "Population"],
              ["I", "Intervention"],
              ["C", "Comparator"],
              ["O", "Outcomes"],
            ] as const).map(([key, label]) => (
              <label key={key}>
                <span className="field-label">{label}</span>
                <textarea
                  className="text-input"
                  onChange={(event) => updatePico(key, event.target.value)}
                  rows={3}
                  value={draft.pico[key]}
                />
              </label>
            ))}
          </div>
        </div>
      </section>

      <JobProgressPanel job={protocolJob.job} />
      {startProtocol.isError ? <p className="form-error" role="alert">{startProtocol.error.message}</p> : null}
      {autosave.error ? <p className="form-error" role="alert">{autosave.error.message}</p> : null}

      {effectiveArtifact ? (
        <ArtifactApprovalBar
          artifact={effectiveArtifact}
          canApprove={picoComplete}
          key={`${effectiveArtifact.artifact_id}:${effectiveArtifact.version}`}
          reviewId={review.id}
        />
      ) : null}

      <div className="workflow-footer-actions">
        {effectiveArtifact?.approved ? (
          <Link className="button button--primary" to={`/reviews/${review.id}/search`}>
            Continue to Search
          </Link>
        ) : (
          <button className="button button--primary" disabled type="button">
            Continue to Search
          </button>
        )}
      </div>
    </main>
  );
}
