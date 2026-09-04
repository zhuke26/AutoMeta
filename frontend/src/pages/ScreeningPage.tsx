import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { artifactKeys, currentArtifact } from "../api/artifacts";
import {
  useImportScreeningRecords,
  useStartWorkflowJob,
  type ImportedPaper,
} from "../api/workflows";
import { ArtifactApprovalBar } from "../components/ArtifactApprovalBar";
import { JobProgressPanel } from "../components/JobProgressPanel";
import { ScreeningTable, type ScreeningDecision } from "../components/ScreeningTable";
import type { SearchRecord } from "../components/RecordsTable";
import { useAutosavedArtifact } from "../hooks/useAutosavedArtifact";
import { useDurableJob } from "../hooks/useDurableJob";
import { useReviewWorkspace } from "./ReviewWorkspace";


function readText(file: File): Promise<string> {
  if (typeof file.text === "function") return file.text();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error);
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.readAsText(file);
  });
}


function parseCsvLine(line: string) {
  const values: string[] = [];
  let value = "";
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const character = line[index];
    if (character === '"' && quoted && line[index + 1] === '"') {
      value += '"';
      index += 1;
    } else if (character === '"') {
      quoted = !quoted;
    } else if (character === "," && !quoted) {
      values.push(value);
      value = "";
    } else {
      value += character;
    }
  }
  values.push(value);
  return values;
}


function normalizePaper(record: Record<string, unknown>): ImportedPaper {
  const normalized = new Map(
    Object.entries(record).map(([key, value]) => [key.toLocaleLowerCase().replaceAll(" ", "_"), value]),
  );
  return {
    pmid: String(normalized.get("pmid") ?? "").trim(),
    title: String(normalized.get("title") ?? "").trim(),
    abstract: String(normalized.get("abstract") ?? ""),
    authors: String(normalized.get("authors") ?? "") || null,
    year: String(normalized.get("year") ?? "") || null,
    journal: String(normalized.get("journal") ?? "") || null,
    publication_type: String(normalized.get("publication_type") ?? "") || null,
  };
}


async function parseRecordFile(file: File) {
  const text = await readText(file);
  if (file.name.toLocaleLowerCase().endsWith(".json")) {
    const parsed = JSON.parse(text) as unknown;
    const rows = Array.isArray(parsed)
      ? parsed
      : (parsed && typeof parsed === "object" && Array.isArray((parsed as { papers?: unknown[] }).papers)
        ? (parsed as { papers: unknown[] }).papers
        : []);
    return { papers: rows.map((row) => normalizePaper(row as Record<string, unknown>)), sourceFormat: "json" as const };
  }
  const lines = text.split(/\r?\n/).filter((line) => line.trim());
  const headers = parseCsvLine(lines[0] ?? "");
  const rows = lines.slice(1).map((line) => Object.fromEntries(
    parseCsvLine(line).map((value, index) => [headers[index], value]),
  ));
  return { papers: rows.map(normalizePaper), sourceFormat: "csv" as const };
}


function decisionsFrom(value: unknown): ScreeningDecision[] {
  return Array.isArray(value) ? value as ScreeningDecision[] : [];
}


export function ScreeningPage() {
  const { artifacts, review } = useReviewWorkspace();
  const picoArtifact = artifacts.find((artifact) => artifact.kind === "question_pico");
  const recordsArtifact = artifacts.find((artifact) => artifact.kind === "records");
  const selectedArtifact = artifacts.find((artifact) => artifact.kind === "selected_studies");
  const decisions = decisionsFrom(selectedArtifact?.payload.decisions);
  const papers = Array.isArray(recordsArtifact?.payload.papers)
    ? recordsArtifact.payload.papers as SearchRecord[]
    : [];
  const initialSelection = Array.isArray(selectedArtifact?.payload.selected_pmids)
    ? selectedArtifact.payload.selected_pmids.map(String)
    : [];
  const [selected, setSelected] = useState(() => new Set(initialSelection));
  const [selectionChanged, setSelectionChanged] = useState(false);
  const [topN, setTopN] = useState(Math.min(10, Math.max(1, decisions.length)));
  const [studyDesign, setStudyDesign] = useState("both");
  const [maxConcurrency, setMaxConcurrency] = useState(50);
  const [importError, setImportError] = useState("");
  const hydratedVersion = useRef(selectedArtifact?.version);
  const queryClient = useQueryClient();
  const screeningJob = useDurableJob(review.id, "screening");
  const runScreening = useStartWorkflowJob(review.id, "screening", "screening/run");
  const importRecords = useImportScreeningRecords(review.id);
  const selectionPayload = useMemo(() => ({
    ...(selectedArtifact?.payload ?? {}),
    selected_pmids: [...selected],
  }), [selected, selectedArtifact?.payload]);
  const autosave = useAutosavedArtifact(
    review.id,
    "selected_studies",
    selectionPayload,
    selectionChanged && Boolean(selectedArtifact),
  );
  const effectiveSelected = currentArtifact(selectedArtifact, autosave.artifact);

  useEffect(() => {
    if (selectedArtifact && selectedArtifact.version !== hydratedVersion.current) {
      hydratedVersion.current = selectedArtifact.version;
      setSelected(new Set(
        Array.isArray(selectedArtifact.payload.selected_pmids)
          ? selectedArtifact.payload.selected_pmids.map(String)
          : [],
      ));
      setSelectionChanged(false);
    }
  }, [selectedArtifact]);
  useEffect(() => {
    if (screeningJob.job?.state === "succeeded") {
      queryClient.invalidateQueries({ queryKey: artifactKeys.all(review.id) });
    }
  }, [queryClient, review.id, screeningJob.job?.state]);

  const toggle = (pmid: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(pmid)) next.delete(pmid); else next.add(pmid);
      return next;
    });
    setSelectionChanged(true);
  };

  const selectTop = () => {
    const ranked = [...decisions].sort(
      (left, right) => (right.score_result?.weighted_score ?? -Infinity)
        - (left.score_result?.weighted_score ?? -Infinity),
    );
    setSelected(new Set(ranked.slice(0, topN).map((decision) => decision.pmid)));
    setSelectionChanged(true);
  };

  const importFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setImportError("");
    try {
      const parsed = await parseRecordFile(file);
      if (!parsed.papers.length || parsed.papers.some((paper) => !paper.pmid || !paper.title)) {
        throw new Error("Every imported record requires PMID and title");
      }
      importRecords.mutate(parsed);
    } catch (error) {
      setImportError(error instanceof Error ? error.message : "Could not read records file");
    }
  };

  const prerequisitesReady = Boolean(picoArtifact?.approved && recordsArtifact?.approved);

  return (
    <main className="page-stack screening-page">
      <header className="page-heading"><div><p className="eyebrow">Stage 02</p><h1>Screening Agent</h1><p>Rank records by PICO evidence and preserve researcher control of final selection.</p></div></header>

      {!prerequisitesReady ? (
        <section className="prerequisite-notice">
          <span>Approve PICO and Records before screening.</span>
          <Link className="button" to={`/reviews/${review.id}/setup`}>Review prerequisites</Link>
        </section>
      ) : null}

      <section className="panel screening-inputs">
        <header className="section-heading"><div><p className="eyebrow">Inputs</p><h2>Records and ranking settings</h2></div></header>
        <div className="screening-controls">
          <label><span className="field-label">Import records file</span><input accept=".json,.csv,application/json,text/csv" aria-label="Import records file" onChange={importFile} type="file" /></label>
          <label><span className="field-label">Study designs</span><select aria-label="Study designs" className="text-input" onChange={(event) => setStudyDesign(event.target.value)} value={studyDesign}><option value="both">RCT and observational</option><option value="rct_only">RCT only</option><option value="obs_only">Observational only</option></select></label>
          <label><span className="field-label">Maximum concurrency</span><input aria-label="Maximum concurrency" className="text-input" min={1} max={200} onChange={(event) => setMaxConcurrency(Number(event.target.value))} type="number" value={maxConcurrency} /></label>
          <button className="button button--primary" disabled={!prerequisitesReady || screeningJob.isActive || runScreening.isPending} onClick={() => runScreening.mutate({ study_design_filter: studyDesign, max_concurrency: maxConcurrency })} type="button">Run screening</button>
        </div>
        {importError || importRecords.isError ? <p className="form-error" role="alert">{importError || importRecords.error?.message}</p> : null}
      </section>

      {recordsArtifact && !recordsArtifact.approved ? <ArtifactApprovalBar artifact={recordsArtifact} reviewId={review.id} /> : null}
      <JobProgressPanel job={screeningJob.job} />

      {selectedArtifact ? (
        <section className="panel screening-results">
          <header className="section-heading">
            <div><p className="eyebrow">Human selection</p><h2>{decisions.length} ranked records</h2></div>
            <div className="selection-tools">
              <label><span className="sr-only">Top N</span><input aria-label="Top N" className="text-input" min={1} max={Math.max(1, decisions.length)} onChange={(event) => setTopN(Number(event.target.value))} type="number" value={topN} /></label>
              <button className="button" onClick={selectTop} type="button">Select top N</button>
              <button className="button" onClick={() => { setSelected(new Set(decisions.map((decision) => decision.pmid))); setSelectionChanged(true); }} type="button">Select all</button>
            </div>
          </header>
          <ScreeningTable decisions={decisions} onToggle={toggle} papers={papers} selected={selected} />
        </section>
      ) : null}

      {effectiveSelected ? (
        <ArtifactApprovalBar
          artifact={effectiveSelected}
          canApprove={decisions.length > 0}
          key={`${effectiveSelected.artifact_id}:${effectiveSelected.version}`}
          reviewId={review.id}
        />
      ) : null}
    </main>
  );
}
