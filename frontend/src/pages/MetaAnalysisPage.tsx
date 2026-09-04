import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { artifactKeys, currentArtifact } from "../api/artifacts";
import { useReviewDatasets, useUploadReviewDatasets } from "../api/files";
import { useStartWorkflowJob } from "../api/workflows";
import { ArtifactApprovalBar } from "../components/ArtifactApprovalBar";
import { JobProgressPanel } from "../components/JobProgressPanel";
import { MetaPlanEditor, type MetaPlan } from "../components/MetaPlanEditor";
import { MetaResultsPanel } from "../components/MetaResultsPanel";
import { useAutosavedArtifact } from "../hooks/useAutosavedArtifact";
import { useDurableJob } from "../hooks/useDurableJob";
import { useReviewWorkspace } from "./ReviewWorkspace";


function planList(value: unknown): MetaPlan[] {
  return Array.isArray(value) ? value as MetaPlan[] : [];
}


function downloadJson(payload: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "autometa-analysis.json";
  anchor.click();
  URL.revokeObjectURL(url);
}


export function MetaAnalysisPage() {
  const { artifacts, review } = useReviewWorkspace();
  const picoArtifact = artifacts.find((artifact) => artifact.kind === "question_pico");
  const planArtifact = artifacts.find((artifact) => artifact.kind === "plan");
  const codeArtifact = artifacts.find((artifact) => artifact.kind === "code");
  const resultArtifact = artifacts.find((artifact) => artifact.kind === "result");
  const datasets = useReviewDatasets(review.id);
  const upload = useUploadReviewDatasets(review.id);
  const [selectedFileIds, setSelectedFileIds] = useState<string[]>(() => Array.isArray(planArtifact?.payload.file_ids) ? planArtifact.payload.file_ids.map(String) : []);
  const [userHint, setUserHint] = useState(() => String(planArtifact?.payload.user_hint ?? ""));
  const [plans, setPlans] = useState<MetaPlan[]>(() => planList(planArtifact?.payload.plans));
  const [planChanged, setPlanChanged] = useState(false);
  const hydratedVersion = useRef(planArtifact?.version);
  const metaJob = useDurableJob(review.id, "meta_analysis");
  const startPlan = useStartWorkflowJob(review.id, "meta_analysis", "meta/plan");
  const runAnalysis = useStartWorkflowJob(review.id, "meta_analysis", "meta/run");
  const queryClient = useQueryClient();
  const planPayload = useMemo(() => ({
    ...(planArtifact?.payload ?? {}),
    file_ids: selectedFileIds,
    user_hint: userHint,
    plans,
  }), [planArtifact?.payload, plans, selectedFileIds, userHint]);
  const autosave = useAutosavedArtifact(review.id, "plan", planPayload, planChanged && Boolean(planArtifact));
  const effectivePlan = currentArtifact(planArtifact, autosave.artifact);

  useEffect(() => {
    if (planArtifact && planArtifact.version !== hydratedVersion.current) {
      hydratedVersion.current = planArtifact.version;
      setSelectedFileIds(Array.isArray(planArtifact.payload.file_ids) ? planArtifact.payload.file_ids.map(String) : []);
      setUserHint(String(planArtifact.payload.user_hint ?? ""));
      setPlans(planList(planArtifact.payload.plans));
      setPlanChanged(false);
    }
  }, [planArtifact]);
  useEffect(() => {
    if (metaJob.job?.state === "succeeded") {
      queryClient.invalidateQueries({ queryKey: artifactKeys.all(review.id) });
    }
  }, [metaJob.job?.state, queryClient, review.id]);

  const results = Array.isArray(resultArtifact?.payload.results)
    ? resultArtifact.payload.results as Parameters<typeof MetaResultsPanel>[0]["results"]
    : [];
  const generatedCode = codeArtifact?.payload.generated_code && typeof codeArtifact.payload.generated_code === "object"
    ? codeArtifact.payload.generated_code as Record<string, string>
    : {};

  return (
    <main className="page-stack meta-page">
      <header className="page-heading"><div><p className="eyebrow">Stage 04</p><h1>Meta-analysis Agent</h1><p>Review a prespecified method plan before deterministic calculation.</p></div></header>
      {!picoArtifact?.approved ? <section className="prerequisite-notice"><span>Approve PICO in Review Setup before planning an analysis.</span><Link className="button" to={`/reviews/${review.id}/setup`}>Open Review Setup</Link></section> : null}

      <section className="panel dataset-panel">
        <header className="section-heading"><div><p className="eyebrow">Local data</p><h2>CSV datasets</h2></div><label className="button"><span>Upload CSV</span><input accept=".csv,text/csv" aria-label="Upload CSV datasets" hidden multiple onChange={(event: ChangeEvent<HTMLInputElement>) => { if (event.target.files?.length) upload.mutate([...event.target.files]); }} type="file" /></label></header>
        <div className="file-list">{datasets.isPending ? <p>Loading datasets…</p> : null}{datasets.data?.length === 0 ? <p>No CSV datasets uploaded.</p> : null}{datasets.data?.map((file) => <label className="file-row" key={file.id}><input aria-label={`Use ${file.original_name}`} checked={selectedFileIds.includes(file.id)} onChange={() => setSelectedFileIds((current) => current.includes(file.id) ? current.filter((id) => id !== file.id) : [...current, file.id])} type="checkbox" /><strong>{file.original_name}</strong><span>{Math.ceil(file.size_bytes / 1024)} KB</span></label>)}</div>
        {upload.isError ? <p className="form-error" role="alert">{upload.error.message}</p> : null}
      </section>

      <section className="panel meta-planning-controls">
        <header className="section-heading"><div><p className="eyebrow">Method planning</p><h2>Analysis intent</h2></div></header>
        <div className="section-body"><label className="field-label" htmlFor="planning-guidance">Planning guidance</label><textarea aria-label="Planning guidance" className="text-input" id="planning-guidance" onChange={(event) => setUserHint(event.target.value)} rows={3} value={userHint} /><div className="workflow-footer-actions"><button className="button button--primary" disabled={!picoArtifact?.approved || selectedFileIds.length === 0 || metaJob.isActive || startPlan.isPending} onClick={() => startPlan.mutate({ file_ids: selectedFileIds, user_hint: userHint, sample_rows: 5, max_concurrency: 1 })} type="button">Generate method plan</button></div></div>
      </section>

      <JobProgressPanel job={metaJob.job} />
      {startPlan.isError || runAnalysis.isError || autosave.error ? <p className="form-error" role="alert">{(startPlan.error ?? runAnalysis.error ?? autosave.error)?.message}</p> : null}

      {plans.length ? <section className="meta-plan-list">{plans.map((plan, index) => <MetaPlanEditor key={`${plan.csv_file}-${index}`} onChange={(next) => { setPlans((current) => current.map((item, itemIndex) => itemIndex === index ? next : item)); setPlanChanged(true); }} plan={plan} />)}</section> : null}
      {effectivePlan ? <ArtifactApprovalBar artifact={effectivePlan} canApprove={plans.length > 0} key={`${effectivePlan.artifact_id}:${effectivePlan.version}`} reviewId={review.id} /> : null}
      <div className="workflow-footer-actions"><button className="button button--primary" disabled={!effectivePlan?.approved || metaJob.isActive || runAnalysis.isPending} onClick={() => runAnalysis.mutate({ confirm_strict_execution: true })} type="button">Run meta-analysis</button></div>

      {results.length ? <><div className="result-export"><button className="button" onClick={() => downloadJson({ results, generated_code: generatedCode })} type="button">Export analysis JSON</button></div><MetaResultsPanel generatedCode={generatedCode} results={results} /></> : null}
    </main>
  );
}
