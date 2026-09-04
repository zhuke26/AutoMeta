import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useCreateReview } from "../api/reviews";
import type { ReviewEntryMode } from "../api/types";
import { AppShell } from "../components/AppShell";
import { EntryModeCard } from "../components/EntryModeCard";


const entryModes: Array<{
  mode: ReviewEntryMode;
  label: string;
  description: string;
}> = [
  {
    mode: "guided",
    label: "Guided Review",
    description: "Start with a research question and move through all four review stages.",
  },
  {
    mode: "search",
    label: "Search",
    description: "Start with PICO and PubMed retrieval settings.",
  },
  {
    mode: "screening",
    label: "Screening",
    description: "Import PubMed, CSV, or JSON records and provide PICO context.",
  },
  {
    mode: "extraction",
    label: "Extraction",
    description: "Provide study context, define fields, and upload PDFs.",
  },
  {
    mode: "meta_analysis",
    label: "Meta-analysis",
    description: "Upload CSV datasets and configure a statistical plan.",
  },
];


const entryRoutes: Record<ReviewEntryMode, string> = {
  guided: "setup",
  search: "search",
  screening: "screening",
  extraction: "extraction",
  meta_analysis: "meta-analysis",
};


export function NewReviewPage() {
  const [name, setName] = useState("");
  const [entryMode, setEntryMode] = useState<ReviewEntryMode | null>(null);
  const createReview = useCreateReview();
  const navigate = useNavigate();
  const trimmedName = name.trim();

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!trimmedName || !entryMode) {
      return;
    }
    createReview.mutate(
      { name: trimmedName, entry_mode: entryMode },
      {
        onSuccess: (review) => navigate(`/reviews/${review.id}/${entryRoutes[entryMode]}`),
      },
    );
  };

  return (
    <AppShell>
      <main className="page-stack new-review-page">
        <header className="page-heading">
          <div>
            <p className="eyebrow">New local workspace</p>
            <h1>Create a review</h1>
            <p>Choose where to enter the evidence-synthesis workflow.</p>
          </div>
          <Link className="button button--quiet" to="/library">Back to Library</Link>
        </header>

        <form className="panel new-review-form" onSubmit={submit}>
          <section className="new-review-form__section">
            <label className="field-label" htmlFor="new-review-name">Review name</label>
            <input
              autoFocus
              className="text-input review-name-input"
              id="new-review-name"
              maxLength={160}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. Rehabilitation after stroke"
              value={name}
            />
            <p className="field-help">Stored only in this local AutoMeta Library.</p>
          </section>

          <fieldset className="new-review-form__section mode-fieldset">
            <legend>Entry mode</legend>
            <p className="field-help">Each option creates a normal Review that can continue downstream.</p>
            <div className="entry-mode-grid">
              {entryModes.map((option) => (
                <EntryModeCard
                  description={option.description}
                  key={option.mode}
                  label={option.label}
                  mode={option.mode}
                  onSelect={setEntryMode}
                  selected={entryMode === option.mode}
                />
              ))}
            </div>
          </fieldset>

          {createReview.isError ? (
            <p className="form-error" role="alert">{createReview.error.message}</p>
          ) : null}

          <footer className="form-actions">
            <Link className="button button--quiet" to="/library">Cancel</Link>
            <button
              className="button button--primary"
              disabled={!trimmedName || !entryMode || createReview.isPending}
              type="submit"
            >
              {createReview.isPending ? "Creating…" : "Create review"}
            </button>
          </footer>
        </form>
      </main>
    </AppShell>
  );
}
