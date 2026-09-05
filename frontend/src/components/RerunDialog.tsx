import type { ReviewEventView } from "../api/types";


export function RerunDialog({
  event,
  busy,
  onCancel,
  onConfirm,
}: {
  event: ReviewEventView;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="dialog-backdrop" role="presentation">
      <section aria-label="Rerun workflow" aria-modal="true" className="dialog-card" role="dialog">
        <p className="eyebrow">New immutable run</p>
        <h2>Rerun workflow</h2>
        <p>Rerun {event.payload.operation_kind as string} from event #{event.sequence} using its saved request and exact input versions.</p>
        <div className="dialog-actions">
          <button className="button" disabled={busy} onClick={onCancel} type="button">Cancel</button>
          <button className="button button--primary" disabled={busy} onClick={onConfirm} type="button">Rerun</button>
        </div>
      </section>
    </div>
  );
}
