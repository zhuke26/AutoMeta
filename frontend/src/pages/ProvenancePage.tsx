import { useEffect, useMemo, useState } from "react";

import type { ArtifactKind, ReviewEventView } from "../api/types";
import {
  auditExportUrl,
  useArtifactDiff,
  useArtifactVersions,
  useProvenanceEvents,
  useProvenanceGraph,
  useRerunEvent,
} from "../api/provenance";
import { ArtifactVersionDiff } from "../components/ArtifactVersionDiff";
import { ProvenanceTimeline } from "../components/ProvenanceTimeline";
import { RerunDialog } from "../components/RerunDialog";
import { useReviewWorkspace } from "./ReviewWorkspace";


export function ProvenancePage() {
  const { artifacts, review } = useReviewWorkspace();
  const events = useProvenanceEvents(review.id);
  const graph = useProvenanceGraph(review.id);
  const [stage, setStage] = useState("all");
  const [producer, setProducer] = useState("all");
  const [eventType, setEventType] = useState("all");
  const [kind, setKind] = useState<ArtifactKind>(artifacts[0]?.kind ?? "question_pico");
  const versions = useArtifactVersions(review.id, kind);
  const [fromVersion, setFromVersion] = useState(0);
  const [toVersion, setToVersion] = useState(0);
  const diff = useArtifactDiff(review.id, kind, fromVersion, toVersion);
  const rerun = useRerunEvent();
  const [rerunEvent, setRerunEvent] = useState<ReviewEventView | null>(null);
  const [queuedJobId, setQueuedJobId] = useState<string | null>(null);

  useEffect(() => {
    const items = versions.data ?? [];
    if (!items.length) return;
    setFromVersion((current) => current || items[0].version);
    setToVersion((current) => current || items.at(-1)!.version);
  }, [versions.data]);

  const filteredEvents = useMemo(() => (events.data ?? []).filter((event) => (
    (stage === "all" || event.stage === stage)
    && (producer === "all" || event.producer === producer)
    && (eventType === "all" || event.event_type === eventType)
  )), [eventType, events.data, producer, stage]);
  const eventTypes = useMemo(
    () => [...new Set((events.data ?? []).map((event) => event.event_type))].sort(),
    [events.data],
  );

  const confirmRerun = () => {
    if (!rerunEvent) return;
    rerun.mutate(
      { reviewId: review.id, eventId: rerunEvent.id },
      { onSuccess: (job) => { setQueuedJobId(job.id); setRerunEvent(null); } },
    );
  };

  return (
    <main className="page-stack provenance-page">
      <header className="page-heading">
        <div><p className="eyebrow">Audit trail</p><h1>Evidence provenance</h1><p>Inspect immutable versions, decisions, and workflow lineage.</p></div>
        <a className="button" download href={auditExportUrl(review.id)}>Download audit JSON</a>
      </header>
      {events.isError || graph.isError ? <section className="panel state-panel state-panel--error"><h2>Could not load provenance</h2></section> : null}
      {queuedJobId ? <p className="status-banner">Rerun queued as job {queuedJobId}.</p> : null}
      <section className="panel provenance-events">
        <header className="section-heading"><div><p className="eyebrow">Timeline</p><h2>Review events</h2></div><div className="provenance-filters"><label>Stage<select aria-label="Filter by stage" value={stage} onChange={(event) => setStage(event.target.value)}><option value="all">All stages</option><option value="setup">Setup</option><option value="search">Search</option><option value="screening">Screening</option><option value="extraction">Extraction</option><option value="meta_analysis">Meta-analysis</option></select></label><label>Producer<select aria-label="Filter by producer" value={producer} onChange={(event) => setProducer(event.target.value)}><option value="all">All producers</option><option value="researcher">Researcher</option><option value="agent">Agent</option><option value="system">System</option></select></label><label>Event<select aria-label="Filter by event type" value={eventType} onChange={(event) => setEventType(event.target.value)}><option value="all">All event types</option>{eventTypes.map((value) => <option key={value} value={value}>{value.replaceAll(".", " ")}</option>)}</select></label></div></header>
        {events.isPending ? <p className="state-inline">Loading provenance…</p> : null}
        {!events.isPending && filteredEvents.length === 0 ? <p className="state-inline">No provenance events match these filters.</p> : null}
        <ProvenanceTimeline events={filteredEvents} onRerun={setRerunEvent} />
        {graph.data ? <p className="graph-summary">{graph.data.edges.length} artifact links · {graph.data.edits.length} researcher edits · {graph.data.reruns.length} reruns</p> : null}
      </section>
      <section className="provenance-version-picker"><label>Artifact<select aria-label="Artifact" value={kind} onChange={(event) => { setKind(event.target.value as ArtifactKind); setFromVersion(0); setToVersion(0); }}>{artifacts.map((artifact) => <option key={artifact.artifact_id} value={artifact.kind}>{artifact.kind.replaceAll("_", " ")}</option>)}</select></label></section>
      <ArtifactVersionDiff versions={versions.data ?? []} fromVersion={fromVersion} toVersion={toVersion} onFromVersion={setFromVersion} onToVersion={setToVersion} diff={diff.data} />
      {rerunEvent ? <RerunDialog event={rerunEvent} busy={rerun.isPending} onCancel={() => setRerunEvent(null)} onConfirm={confirmRerun} /> : null}
      {rerun.isError ? <p className="form-error" role="alert">{rerun.error.message}</p> : null}
    </main>
  );
}
