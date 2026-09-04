import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useDeleteReview, useRenameReview, useReviews } from "../api/reviews";
import type { ReviewSummary } from "../api/types";
import { AppShell } from "../components/AppShell";
import { DeleteReviewDialog } from "../components/DeleteReviewDialog";
import { ReviewCard } from "../components/ReviewCard";


export function LibraryPage() {
  const [search, setSearch] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<ReviewSummary | null>(null);
  const reviews = useReviews();
  const deleteReview = useDeleteReview();
  const renameReview = useRenameReview();

  const items = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    const source = reviews.data?.items ?? [];
    return query ? source.filter((review) => review.name.toLocaleLowerCase().includes(query)) : source;
  }, [reviews.data?.items, search]);

  return (
    <AppShell>
      <main className="page-stack">
        <header className="page-heading">
          <div>
            <p className="eyebrow">Local workspace</p>
            <h1>Library</h1>
            <p>Continue a saved review or start a new evidence-synthesis workflow.</p>
          </div>
          <Link className="button button--primary" to="/reviews/new">New review</Link>
        </header>

        <section className="panel library-panel" aria-label="Saved reviews">
          <div className="library-toolbar">
            <label className="sr-only" htmlFor="review-search">Search reviews</label>
            <input
              aria-label="Search reviews"
              className="text-input library-search"
              id="review-search"
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search reviews"
              type="search"
              value={search}
            />
            <span>{reviews.data?.total ?? 0} reviews</span>
          </div>

          {reviews.isPending ? <div className="state-panel">Loading reviews…</div> : null}
          {reviews.isError ? <div className="state-panel state-panel--error">Could not load your Library.</div> : null}
          {reviews.isSuccess && reviews.data.total === 0 ? (
            <div className="state-panel">
              <h2>No reviews yet</h2>
              <p>Create a Review to begin with a question, records, PDFs, or analysis data.</p>
            </div>
          ) : null}
          {reviews.isSuccess && reviews.data.total > 0 && items.length === 0 ? (
            <div className="state-panel">No reviews match your search.</div>
          ) : null}

          <div className="review-list">
            {items.map((review) => (
              <ReviewCard
                key={review.id}
                onDelete={() => setDeleteTarget(review)}
                onRename={(name) => renameReview.mutate({ reviewId: review.id, name })}
                renaming={renameReview.isPending && renameReview.variables?.reviewId === review.id}
                review={review}
              />
            ))}
          </div>
        </section>
      </main>

      {deleteTarget ? (
        <DeleteReviewDialog
          deleting={deleteReview.isPending}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={(confirmationName) => {
            deleteReview.mutate(
              { reviewId: deleteTarget.id, confirmationName },
              { onSuccess: () => setDeleteTarget(null) },
            );
          }}
          review={deleteTarget}
        />
      ) : null}
    </AppShell>
  );
}
