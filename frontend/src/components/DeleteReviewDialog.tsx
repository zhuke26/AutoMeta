import { useEffect, useState } from "react";

import type { ReviewSummary } from "../api/types";


interface DeleteReviewDialogProps {
  review: ReviewSummary;
  deleting: boolean;
  onCancel: () => void;
  onConfirm: (confirmationName: string) => void;
}


export function DeleteReviewDialog({
  review,
  deleting,
  onCancel,
  onConfirm,
}: DeleteReviewDialogProps) {
  const [confirmation, setConfirmation] = useState("");

  useEffect(() => setConfirmation(""), [review.id]);

  return (
    <div aria-labelledby="delete-review-title" aria-modal="true" className="dialog-backdrop" role="dialog">
      <div className="dialog-card">
        <p className="eyebrow">Permanent action</p>
        <h2 id="delete-review-title">Delete review</h2>
        <p>
          This permanently removes the Review, uploaded PDFs, parsed content,
          exports, and generated figures.
        </p>
        <label className="field-label" htmlFor="delete-confirmation">
          Type {review.name} to confirm
        </label>
        <input
          autoComplete="off"
          className="text-input"
          id="delete-confirmation"
          onChange={(event) => setConfirmation(event.target.value)}
          value={confirmation}
        />
        <div className="dialog-actions">
          <button className="button button--quiet" onClick={onCancel} type="button">
            Cancel
          </button>
          <button
            className="button button--danger"
            disabled={confirmation !== review.name || deleting}
            onClick={() => onConfirm(confirmation)}
            type="button"
          >
            {deleting ? "Deleting…" : "Delete permanently"}
          </button>
        </div>
      </div>
    </div>
  );
}
