import { useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { artifactKeys } from "../api/artifacts";
import { useStartWorkflowJob } from "../api/workflows";
import type { ArtifactView } from "../api/types";
import { ArtifactApprovalBar } from "../components/ArtifactApprovalBar";
import { JobProgressPanel } from "../components/JobProgressPanel";
import { RecordsTable, type SearchRecord } from "../components/RecordsTable";
import { useAutosavedArtifact } from "../hooks/useAutosavedArtifact";
import { useDurableJob } from "../hooks/useDurableJob";
import { useReviewWorkspace } from "./ReviewWorkspace";


function stringValue(value: unknown) {
  return typeof value === "string" ? value : "";
}


function recordsFrom(artifact: ArtifactView | undefined): SearchRecord[] {
  const papers = artifact?.payload.papers;
  return Array.isArray(papers) ? papers as SearchRecord[] : [];
}


function csvCell(value: unknown) {
  const text = String(value ?? "");
  return `"${text.replaceAll('"', '""')}"`;
}


function exportRecords(format: "json" | "csv" | "ris", papers: SearchRecord[]) {
  let content: string;
  let type: string;
  if (format === "json") {
    content = JSON.stringify(papers, null, 2);
    type = "application/json";
  } else if (format === "csv") {
    const header = ["PMID", "Title", "Year", "Journal", "Authors", "Publication Type", "Abstract"];
    const rows = papers.map((paper) => [
      paper.pmid,
      paper.title,
      paper.year,
      paper.journal,
      paper.authors,
      paper.publication_type,
      paper.abstract,
    ].map(csvCell).join(","));
    content = [header.map(csvCell).join(","), ...rows].join("\n");
    type = "text/csv";
  } else {
    content = papers.map((paper) => [
      "TY  - JOUR",
      `TI  - ${paper.title}`,
      `AN  - ${paper.pmid}`,
      paper.authors ? `AU  - ${paper.authors}` : "",
      paper.year ? `PY  - ${paper.year}` : "",
      paper.journal ? `JO  - ${paper.journal}` : "",
      paper.abstract ? `AB  - ${paper.abstract}` : "",
      "ER  -",
    ].filter(Boolean).join("\n")).join("\n\n");
    type = "application/x-research-info-systems";
  }
  const url = URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `autometa-records.${format}`;
  anchor.click();
  URL.revokeObjectURL(url);
}


export function SearchPage() {
  const { artifacts, review } = useReviewWorkspace();
  const picoArtifact = artifacts.find((artifact) => artifact.kind === "question_pico");
  const queryArtifact = artifacts.find((artifact) => artifact.kind === "query");
  const recordsArtifact = artifacts.find((artifact) => artifact.kind === "records");
  const [rawQuery, setRawQuery] = useState(() => stringValue(queryArtifact?.payload.raw_query));
  const [queryChanged, setQueryChanged] = useState(false);
  const [retmax, setRetmax] = useState(1000);
  const [fetchAll, setFetchAll] = useState(false);
  const [minYear, setMinYear] = useState("");
  const [maxYear, setMaxYear] = useState("");
  const hydratedVersion = useRef(queryArtifact?.version);
  const queryClient = useQueryClient();
  const searchJob = useDurableJob(review.id, "search");
  const generateQuery = useStartWorkflowJob(review.id, "search", "search/query");
  const runSearch = useStartWorkflowJob(review.id, "search", "search/run");
  const queryPayload = useMemo(() => ({
    ...(queryArtifact?.payload ?? {}),
    raw_query: rawQuery,
  }), [queryArtifact?.payload, rawQuery]);
  const autosave = useAutosavedArtifact(
    review.id,
    "query",
    queryPayload,
    queryChanged && Boolean(queryArtifact),
  );
  const effectiveQuery = autosave.artifact ?? queryArtifact;
  const papers = recordsFrom(recordsArtifact);

  useEffect(() => {
    if (queryArtifact && queryArtifact.version !== hydratedVersion.current) {
      hydratedVersion.current = queryArtifact.version;
      setRawQuery(stringValue(queryArtifact.payload.raw_query));
      setQueryChanged(false);
    }
  }, [queryArtifact]);
  useEffect(() => {
    if (searchJob.job?.state === "succeeded") {
      queryClient.invalidateQueries({ queryKey: artifactKeys.all(review.id) });
    }
  }, [queryClient, review.id, searchJob.job?.state]);

  const runPayload = {
    retmax,
    fetch_all: fetchAll,
    min_year: minYear ? Number(minYear) : null,
    max_year: maxYear ? Number(maxYear) : null,
  };

  return (
    <main className="page-stack search-page">
      <header className="page-heading">
        <div>
          <p className="eyebrow">Stage 01</p>
          <h1>Search Agent</h1>
          <p>Compose, approve, and execute a transparent PubMed query.</p>
        </div>
      </header>

      {!picoArtifact?.approved ? (
        <section className="prerequisite-notice">
          <span>Approve PICO in Review Setup before generating a query.</span>
          <Link className="button" to={`/reviews/${review.id}/setup`}>Open Review Setup</Link>
        </section>
      ) : null}

      <section className="panel search-query-panel">
        <header className="section-heading">
          <div><p className="eyebrow">Query</p><h2>Field-tagged PubMed query</h2></div>
          <button
            className="button"
            disabled={!picoArtifact?.approved || searchJob.isActive || generateQuery.isPending}
            onClick={() => generateQuery.mutate({ strategy_mode: "field_tagged_balanced" })}
            type="button"
          >Generate query</button>
        </header>
        {queryArtifact ? (
          <div className="section-body">
            <label className="field-label" htmlFor="pubmed-query">PubMed query</label>
            <textarea
              className="text-input query-editor"
              id="pubmed-query"
              onChange={(event) => { setRawQuery(event.target.value); setQueryChanged(true); }}
              rows={6}
              value={rawQuery}
            />
            <p className="field-help">The generated form is retained separately; edits create a new draft version.</p>
          </div>
        ) : <div className="state-panel">No query draft yet.</div>}
      </section>

      {effectiveQuery ? (
        <ArtifactApprovalBar
          artifact={effectiveQuery}
          canApprove={Boolean(rawQuery.trim())}
          key={`${effectiveQuery.artifact_id}:${effectiveQuery.version}`}
          reviewId={review.id}
        />
      ) : null}

      <section className="panel search-run-panel">
        <header className="section-heading"><div><p className="eyebrow">Retrieval</p><h2>PubMed settings</h2></div></header>
        <div className="search-settings">
          <label><span className="field-label">Maximum records</span><input aria-label="Maximum records" className="text-input" min={1} max={100000} onChange={(event) => setRetmax(Number(event.target.value))} type="number" value={retmax} /></label>
          <label><span className="field-label">Start year</span><input aria-label="Start year" className="text-input" min={1900} max={2100} onChange={(event) => setMinYear(event.target.value)} type="number" value={minYear} /></label>
          <label><span className="field-label">End year</span><input aria-label="End year" className="text-input" min={1900} max={2100} onChange={(event) => setMaxYear(event.target.value)} type="number" value={maxYear} /></label>
          <label className="checkbox-field"><input checked={fetchAll} onChange={(event) => setFetchAll(event.target.checked)} type="checkbox" />Retrieve the largest safe PubMed window</label>
          <button
            className="button button--primary"
            disabled={!effectiveQuery?.approved || searchJob.isActive || runSearch.isPending}
            onClick={() => runSearch.mutate(runPayload)}
            type="button"
          >Run PubMed search</button>
        </div>
      </section>

      <JobProgressPanel job={searchJob.job} />
      {generateQuery.isError || runSearch.isError || autosave.error ? (
        <p className="form-error" role="alert">{(generateQuery.error ?? runSearch.error ?? autosave.error)?.message}</p>
      ) : null}

      {recordsArtifact ? (
        <section className="panel records-panel">
          <header className="section-heading">
            <div><p className="eyebrow">Records</p><h2>{papers.length} retrieved records</h2></div>
            <div className="export-actions">
              <button className="button" onClick={() => exportRecords("json", papers)} type="button">Export JSON</button>
              <button className="button" onClick={() => exportRecords("csv", papers)} type="button">Export CSV</button>
              <button className="button" onClick={() => exportRecords("ris", papers)} type="button">Export RIS</button>
            </div>
          </header>
          <RecordsTable papers={papers} />
        </section>
      ) : null}

      {recordsArtifact ? (
        <ArtifactApprovalBar artifact={recordsArtifact} reviewId={review.id} />
      ) : null}
    </main>
  );
}
