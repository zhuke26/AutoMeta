import type { JobView } from "../api/types";


function label(state: JobView["state"]) {
  return state.replace(/^./, (letter) => letter.toUpperCase());
}


export function JobProgressPanel({ job }: { job: JobView | undefined }) {
  if (!job) {
    return null;
  }
  return (
    <section aria-live="polite" className={`job-progress job-progress--${job.state}`}>
      <div>
        <p className="eyebrow">Persistent background job</p>
        <strong>{label(job.state)}</strong>
      </div>
      {job.progress ? <pre>{JSON.stringify(job.progress, null, 2)}</pre> : null}
      {job.error ? <p className="job-progress__error" role="alert">{job.error}</p> : null}
      {job.state === "interrupted" ? (
        <p>The server restarted before this job finished. Review the saved inputs and retry.</p>
      ) : null}
    </section>
  );
}
