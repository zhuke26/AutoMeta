import { useEffect, useState, type FormEvent } from "react";

import { useRenameReview } from "../api/reviews";
import type { ReviewEntryMode } from "../api/types";
import { useReviewWorkspace } from "./ReviewWorkspace";


const modeLabels: Record<ReviewEntryMode, string> = {
  guided: "Guided Review",
  search: "Search",
  screening: "Screening",
  extraction: "Extraction",
  meta_analysis: "Meta-analysis",
};


export function ReviewSetupPage() {
  const { review } = useReviewWorkspace();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(review.name);
  const renameReview = useRenameReview();

  useEffect(() => setName(review.name), [review.name]);

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

      <section className="panel pending-panel">
        <p className="eyebrow">Workflow migration pending</p>
        <h2>Research question and PICO setup</h2>
        <p>The persisted setup editor will replace this guarded placeholder in the workflow migration phase.</p>
        <button className="button button--primary" disabled type="button">Continue to Search</button>
      </section>
    </main>
  );
}
