import type { ReviewEventView } from "../api/types";


function eventLabel(eventType: string) {
  return eventType
    .replaceAll(".", " ")
    .replaceAll("_", " ")
    .replace(/^./, (value) => value.toUpperCase());
}


export function ProvenanceTimeline({
  events,
  onRerun,
}: {
  events: ReviewEventView[];
  onRerun: (event: ReviewEventView) => void;
}) {
  return (
    <ol aria-label="Review event timeline" className="event-timeline">
      {events.map((event) => (
        <li key={event.id}>
          <div className="event-sequence">#{event.sequence}</div>
          <div className="event-copy">
            <strong>{eventLabel(event.event_type)}</strong>
            <span>{event.stage ?? "Review"} · {event.producer}</span>
            <time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString()}</time>
            <details>
              <summary>Event details</summary>
              <dl className="event-details">
                <div><dt>Stage run</dt><dd>{event.stage_run_id ?? "—"}</dd></div>
                <div><dt>Job</dt><dd>{event.job_id ?? "—"}</dd></div>
                <div><dt>Artifact version</dt><dd>{event.artifact_version_id ?? "—"}</dd></div>
                <div><dt>Elapsed</dt><dd>{event.elapsed_ms === null ? "—" : `${event.elapsed_ms} ms`}</dd></div>
              </dl>
              <pre>{JSON.stringify(event.payload, null, 2)}</pre>
            </details>
          </div>
          {event.event_type === "stage.completed" && event.stage_run_id ? (
            <button className="button" onClick={() => onRerun(event)} type="button">
              Rerun {eventLabel(event.event_type)}
            </button>
          ) : null}
        </li>
      ))}
    </ol>
  );
}
