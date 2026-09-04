import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { artifactKeys } from "../api/artifacts";
import { fileKeys, useReviewFiles, useUploadReviewFiles } from "../api/files";
import { usePdfDisclosure, useSetPdfDisclosure } from "../api/settings";
import { useStartWorkflowJob } from "../api/workflows";
import type { ArtifactView } from "../api/types";
import { ArtifactApprovalBar } from "../components/ArtifactApprovalBar";
import { JobProgressPanel } from "../components/JobProgressPanel";
import { useAutosavedArtifact } from "../hooks/useAutosavedArtifact";
import { useDurableJob } from "../hooks/useDurableJob";
import { useReviewWorkspace } from "./ReviewWorkspace";


interface FieldDefinition {
  name: string;
  description: string;
}

interface ExtractedField {
  field_name: string;
  value: string;
  citation: string;
  confidence: string;
  researcher_edited?: boolean;
}

interface ExtractionRow {
  filename: string;
  outcome_label?: string;
  selected_for_meta?: boolean;
  extractions: ExtractedField[];
}

interface SourcesPayload {
  file_ids: string[];
  study_characteristics_fields: FieldDefinition[];
  study_results_fields: FieldDefinition[];
  characteristics: ExtractionRow[];
  results: ExtractionRow[];
  [key: string]: unknown;
}


function fieldDefinitions(value: unknown): FieldDefinition[] {
  if (!Array.isArray(value)) return [];
  return value.map((field) => {
    const record = field as Record<string, unknown>;
    return { name: String(record.name ?? ""), description: String(record.description ?? "") };
  });
}


function extractionRows(value: unknown): ExtractionRow[] {
  return Array.isArray(value) ? value as ExtractionRow[] : [];
}


function sourcesPayload(artifact: ArtifactView | undefined): SourcesPayload {
  return {
    ...(artifact?.payload ?? {}),
    file_ids: Array.isArray(artifact?.payload.file_ids) ? artifact.payload.file_ids.map(String) : [],
    study_characteristics_fields: fieldDefinitions(artifact?.payload.study_characteristics_fields),
    study_results_fields: fieldDefinitions(artifact?.payload.study_results_fields),
    characteristics: extractionRows(artifact?.payload.characteristics),
    results: extractionRows(artifact?.payload.results),
  };
}


function csvCell(value: unknown) {
  return `"${String(value ?? "").replaceAll('"', '""')}"`;
}


function exportExtraction(format: "json" | "csv", payload: SourcesPayload) {
  const csvRows = (["characteristics", "results"] as const).flatMap((table) =>
    payload[table].flatMap((row) => row.extractions.map((field) => [
      table,
      row.filename,
      row.outcome_label ?? "",
      field.field_name,
      field.value,
      field.confidence,
      field.citation,
      field.researcher_edited ? "true" : "false",
    ].map(csvCell).join(","))),
  );
  const content = format === "json"
    ? JSON.stringify(payload, null, 2)
    : [
      ["Table", "Filename", "Outcome", "Field", "Value", "Confidence", "Citation", "Researcher Edited"].map(csvCell).join(","),
      ...csvRows,
    ].join("\n");
  const url = URL.createObjectURL(new Blob([content], {
    type: format === "json" ? "application/json" : "text/csv",
  }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `autometa-extraction.${format}`;
  anchor.click();
  URL.revokeObjectURL(url);
}


function FieldList({
  fields,
  kind,
  onChange,
  onAdd,
}: {
  fields: FieldDefinition[];
  kind: "Characteristic" | "Result";
  onChange: (index: number, field: FieldDefinition) => void;
  onAdd: () => void;
}) {
  return (
    <section className="field-definition-list">
      <header><h3>{kind} fields</h3><button className="button" onClick={onAdd} type="button">Add {kind.toLocaleLowerCase()} field</button></header>
      {fields.map((field, index) => (
        <div className="field-definition-row" key={`${kind}-${index}`}>
          <input aria-label={`${kind} field name ${index + 1}`} className="text-input" onChange={(event) => onChange(index, { ...field, name: event.target.value })} placeholder="Field name" value={field.name} />
          <input aria-label={`${kind} field description ${index + 1}`} className="text-input" onChange={(event) => onChange(index, { ...field, description: event.target.value })} placeholder="Extraction guidance" value={field.description} />
        </div>
      ))}
    </section>
  );
}


export function ExtractionPage() {
  const { artifacts, review } = useReviewWorkspace();
  const picoArtifact = artifacts.find((artifact) => artifact.kind === "question_pico");
  const existingSources = artifacts.find((artifact) => artifact.kind === "sources");
  const disclosure = usePdfDisclosure();
  const acknowledge = useSetPdfDisclosure();
  const files = useReviewFiles(review.id);
  const upload = useUploadReviewFiles(review.id);
  const extractionJob = useDurableJob(review.id, "extraction");
  const runExtraction = useStartWorkflowJob(review.id, "extraction", "extraction/run");
  const queryClient = useQueryClient();
  const [selectedFileIds, setSelectedFileIds] = useState<string[]>(() => sourcesPayload(existingSources).file_ids);
  const [characteristicFields, setCharacteristicFields] = useState<FieldDefinition[]>(() => {
    const existing = sourcesPayload(existingSources).study_characteristics_fields;
    return existing.length ? existing : [{ name: "", description: "" }];
  });
  const [resultFields, setResultFields] = useState<FieldDefinition[]>(() => sourcesPayload(existingSources).study_results_fields);
  const [draft, setDraft] = useState(() => sourcesPayload(existingSources));
  const [resultsChanged, setResultsChanged] = useState(false);
  const hydratedVersion = useRef(existingSources?.version);
  const autosave = useAutosavedArtifact(review.id, "sources", draft, resultsChanged);
  const effectiveSources = autosave.artifact ?? existingSources;

  useEffect(() => {
    if (existingSources && existingSources.version !== hydratedVersion.current) {
      hydratedVersion.current = existingSources.version;
      const next = sourcesPayload(existingSources);
      setDraft(next);
      setSelectedFileIds(next.file_ids);
      if (next.study_characteristics_fields.length) setCharacteristicFields(next.study_characteristics_fields);
      setResultFields(next.study_results_fields);
      setResultsChanged(false);
    }
  }, [existingSources]);
  useEffect(() => {
    if (extractionJob.job?.state === "succeeded") {
      queryClient.invalidateQueries({ queryKey: artifactKeys.all(review.id) });
      queryClient.invalidateQueries({ queryKey: fileKeys.review(review.id) });
    }
  }, [extractionJob.job?.state, queryClient, review.id]);

  const updateExtraction = (table: "characteristics" | "results", rowIndex: number, fieldIndex: number, value: string) => {
    setDraft((current) => ({
      ...current,
      [table]: current[table].map((row, index) => index === rowIndex ? {
        ...row,
        extractions: row.extractions.map((field, innerIndex) => innerIndex === fieldIndex
          ? { ...field, value, researcher_edited: true }
          : field),
      } : row),
    }));
    setResultsChanged(true);
  };

  const toggleMetaRow = (rowIndex: number) => {
    setDraft((current) => ({
      ...current,
      results: current.results.map((row, index) => index === rowIndex
        ? { ...row, selected_for_meta: !row.selected_for_meta }
        : row),
    }));
    setResultsChanged(true);
  };

  const toggleFile = (fileId: string) => {
    setSelectedFileIds((current) => {
      const next = current.includes(fileId)
        ? current.filter((id) => id !== fileId)
        : [...current, fileId];
      setDraft((draftValue) => ({ ...draftValue, file_ids: next }));
      return next;
    });
    setResultsChanged(true);
  };

  const updateCharacteristicField = (index: number, field: FieldDefinition) => {
    setCharacteristicFields((current) => {
      const next = current.map((item, itemIndex) => itemIndex === index ? field : item);
      setDraft((draftValue) => ({ ...draftValue, study_characteristics_fields: next }));
      return next;
    });
    setResultsChanged(true);
  };

  const addCharacteristicField = () => {
    setCharacteristicFields((current) => {
      const next = [...current, { name: "", description: "" }];
      setDraft((draftValue) => ({ ...draftValue, study_characteristics_fields: next }));
      return next;
    });
    setResultsChanged(true);
  };

  const updateResultField = (index: number, field: FieldDefinition) => {
    setResultFields((current) => {
      const next = current.map((item, itemIndex) => itemIndex === index ? field : item);
      setDraft((draftValue) => ({ ...draftValue, study_results_fields: next }));
      return next;
    });
    setResultsChanged(true);
  };

  const addResultField = () => {
    setResultFields((current) => {
      const next = [...current, { name: "", description: "" }];
      setDraft((draftValue) => ({ ...draftValue, study_results_fields: next }));
      return next;
    });
    setResultsChanged(true);
  };

  const validFields = [...characteristicFields, ...resultFields].filter((field) => field.name.trim());
  const canRun = Boolean(
    disclosure.data?.acknowledged
    && picoArtifact?.approved
    && selectedFileIds.length
    && validFields.length
    && !extractionJob.isActive,
  );

  return (
    <main className="page-stack extraction-page">
      <header className="page-heading"><div><p className="eyebrow">Stage 03</p><h1>Extraction Agent</h1><p>Extract user-defined values from manually uploaded full-text PDFs.</p></div></header>

      {disclosure.isSuccess && !disclosure.data.acknowledged ? (
        <div aria-labelledby="pdf-notice-title" aria-modal="true" className="dialog-backdrop" role="dialog">
          <div className="dialog-card">
            <p className="eyebrow">Privacy notice</p>
            <h2 id="pdf-notice-title">PDF processing notice</h2>
            <p>During Extraction, relevant PDF text passages will be sent to the model service configured in your local `.env` file.</p>
            <p>The acknowledgement is stored only in this local AutoMeta database.</p>
            <div className="dialog-actions"><button className="button button--primary" disabled={acknowledge.isPending} onClick={() => acknowledge.mutate(true)} type="button">I understand and continue</button></div>
          </div>
        </div>
      ) : null}

      {!picoArtifact?.approved ? <section className="prerequisite-notice"><span>Approve PICO in Review Setup before Extraction.</span><Link className="button" to={`/reviews/${review.id}/setup`}>Open Review Setup</Link></section> : null}

      <section className="panel extraction-inputs">
        <header className="section-heading"><div><p className="eyebrow">Local files</p><h2>PDF sources</h2></div><label className="button"><span>Upload PDFs</span><input accept="application/pdf,.pdf" aria-label="Upload PDF files" hidden multiple onChange={(event: ChangeEvent<HTMLInputElement>) => { if (event.target.files?.length) upload.mutate([...event.target.files]); }} type="file" /></label></header>
        <div className="file-list">
          {files.isPending ? <p>Loading PDF files…</p> : null}
          {files.data?.length === 0 ? <p>No PDFs uploaded.</p> : null}
          {files.data?.map((file) => (
            <label className="file-row" key={file.id}>
              <input aria-label={`Use ${file.original_name}`} checked={selectedFileIds.includes(file.id)} onChange={() => toggleFile(file.id)} type="checkbox" />
              <strong>{file.original_name}</strong><span>{Math.ceil(file.size_bytes / 1024)} KB · {file.parse_status}</span>
            </label>
          ))}
        </div>
        {upload.isError ? <p className="form-error" role="alert">{upload.error.message}</p> : null}
      </section>

      <section className="panel extraction-fields">
        <header className="section-heading"><div><p className="eyebrow">Schema</p><h2>Extraction fields</h2></div></header>
        <div className="field-lists">
          <FieldList fields={characteristicFields} kind="Characteristic" onAdd={addCharacteristicField} onChange={updateCharacteristicField} />
          <FieldList fields={resultFields} kind="Result" onAdd={addResultField} onChange={updateResultField} />
        </div>
        <div className="workflow-footer-actions"><button className="button button--primary" disabled={!canRun || runExtraction.isPending} onClick={() => runExtraction.mutate({ file_ids: selectedFileIds, study_characteristics_fields: characteristicFields.filter((field) => field.name.trim()), study_results_fields: resultFields.filter((field) => field.name.trim()), top_k: 15, max_concurrency: 10 })} type="button">Run extraction</button></div>
      </section>

      <JobProgressPanel job={extractionJob.job} />
      {runExtraction.isError || autosave.error ? <p className="form-error" role="alert">{(runExtraction.error ?? autosave.error)?.message}</p> : null}

      {existingSources ? (
        <section className="panel extraction-results">
          <header className="section-heading"><div><p className="eyebrow">Review values</p><h2>Source-linked extraction</h2></div><div className="export-actions"><button className="button" onClick={() => exportExtraction("json", draft)} type="button">Export extraction JSON</button><button className="button" onClick={() => exportExtraction("csv", draft)} type="button">Export extraction CSV</button></div></header>
          {(["characteristics", "results"] as const).map((table) => draft[table].length ? (
            <div className="extraction-table-block" key={table}>
              <h3>{table === "characteristics" ? "Study characteristics" : "Outcome results"}</h3>
              {draft[table].map((row, rowIndex) => (
                <article className="extraction-row" key={`${table}-${row.filename}-${rowIndex}`}>
                  <header><strong>{row.filename}</strong>{row.outcome_label ? <span>{row.outcome_label}</span> : null}{table === "results" ? <label><input aria-label={`Use ${row.outcome_label || "result"} from ${row.filename} in meta-analysis`} checked={Boolean(row.selected_for_meta)} onChange={() => toggleMetaRow(rowIndex)} type="checkbox" />Use in meta-analysis</label> : null}</header>
                  {row.extractions.map((field, fieldIndex) => (
                    <div className="extracted-field" key={`${field.field_name}-${fieldIndex}`}>
                      <label><span className="field-label">{field.field_name}</span><input aria-label={`${field.field_name} for ${row.filename}`} className="text-input" onChange={(event) => updateExtraction(table, rowIndex, fieldIndex, event.target.value)} value={field.value} /></label>
                      <blockquote>{field.citation || "Exact citation unavailable"}</blockquote>
                      <span className="confidence-label">{field.confidence} confidence</span>
                      {field.researcher_edited ? <span className="researcher-edit-badge">Researcher edited</span> : null}
                    </div>
                  ))}
                </article>
              ))}
            </div>
          ) : null)}
        </section>
      ) : null}

      {effectiveSources ? (
        <ArtifactApprovalBar
          artifact={effectiveSources}
          canApprove={draft.characteristics.length > 0 || draft.results.length > 0}
          reviewId={review.id}
        />
      ) : null}
    </main>
  );
}
