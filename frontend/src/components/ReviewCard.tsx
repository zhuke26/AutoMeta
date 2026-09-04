import { useState } from "react";
import { Link } from "react-router-dom";

import type { ReviewSummary } from "../api/types";


interface ReviewCardProps {
  review: ReviewSummary;
  renaming: boolean;
  onDelete: () => void;
  onRename: (name: string) => void;
}


const modeLabels: Record<ReviewSummary["entry_mode"], string> = {
  guided: "Guided review",
  search: "Search",
  screening: "Screening",
  extraction: "Extraction",
  meta_analysis: "Meta-analysis",
};


export function ReviewCard({ review, renaming, onDelete, onRename }: ReviewCardProps) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(review.name);

  const save = () => {
    const next = name.trim();
    if (!next || next === review.name) {
      setName(review.name);
      setEditing(false);
      return;
    }
    onRename(next);
    setEditing(false);
  };

  return (
    <article className="review-card" data-testid={`review-card-${review.id}`}>
      <div className="review-card__main">
        <div className="review-card__meta">
          <span className={`status-pill status-pill--${review.status}`}>{review.status}</span>
          <span>{modeLabels[review.entry_mode]}</span>
          <span>{review.current_stage ? `Current: ${review.current_stage}` : "Not started"}</span>
        </div>
        {editing ? (
          <div className="inline-form">
            <label className="sr-only" htmlFor={`review-name-${review.id}`}>Review name</label>
            <input
              aria-label="Review name"
              className="text-input"
              id={`review-name-${review.id}`}
              maxLength={160}
              onChange={(event) => setName(event.target.value)}
              value={name}
            />
            <button className="button button--primary" disabled={renaming} onClick={save} type="button">
              Save name
            </button>
            <button className="button button--quiet" onClick={() => setEditing(false)} type="button">
              Cancel
            </button>
          </div>
        ) : (
          <>
            <h2>{review.name}</h2>
            <p>Updated {new Date(review.updated_at).toLocaleString()}</p>
          </>
        )}
      </div>
      <div className="review-card__actions">
        <Link aria-label={`Open ${review.name}`} className="button button--primary" to={`/reviews/${review.id}/setup`}>
          Open
        </Link>
        <button aria-label={`Rename ${review.name}`} className="button button--quiet" onClick={() => setEditing(true)} type="button">
          Rename
        </button>
        <button aria-label={`Delete ${review.name}`} className="button button--quiet button--danger-text" onClick={onDelete} type="button">
          Delete
        </button>
      </div>
    </article>
  );
}
