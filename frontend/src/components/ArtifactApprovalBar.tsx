import { useState } from "react";

import { useApproveArtifact, useRevokeArtifact } from "../api/artifacts";
import type { ArtifactView } from "../api/types";


function artifactLabel(kind: ArtifactView["kind"]) {
  if (kind === "question_pico") {
    return "PICO";
  }
  return kind.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}


export function ArtifactApprovalBar({
  artifact,
  canApprove = true,
  reviewId,
}: {
  artifact: ArtifactView;
  canApprove?: boolean;
  reviewId: string;
}) {
  const approve = useApproveArtifact();
  const revoke = useRevokeArtifact();
  const [current, setCurrent] = useState(artifact);
  const label = artifactLabel(current.kind);
  const busy = approve.isPending || revoke.isPending;

  return (
    <section className="artifact-approval" aria-label={`${label} approval`}>
      <div>
        <span className={`status-pill status-pill--${current.state}`}>{current.state}</span>
        <strong>
          {current.state === "approved"
            ? "Approved"
            : current.state === "stale"
              ? "Stale — regenerate before approval"
              : "Draft changes do not flow downstream"}
        </strong>
      </div>
      <div className="artifact-approval__actions">
        {current.state === "approved" ? (
          <button
            className="button button--quiet"
            disabled={busy}
            onClick={() => revoke.mutate(
              { reviewId, kind: current.kind },
              { onSuccess: setCurrent },
            )}
            type="button"
          >
            Revoke approval
          </button>
        ) : (
          <button
            className="button button--primary"
            disabled={busy || current.state === "stale" || !canApprove}
            onClick={() => approve.mutate(
              { reviewId, artifact: current },
              { onSuccess: setCurrent },
            )}
            type="button"
          >
            Approve {label}
          </button>
        )}
      </div>
      {approve.isError || revoke.isError ? (
        <p className="form-error" role="alert">{(approve.error ?? revoke.error)?.message}</p>
      ) : null}
    </section>
  );
}
