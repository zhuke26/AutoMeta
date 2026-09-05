from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd
from fastapi.encoders import jsonable_encoder

from autometa.agents.extraction_agent import ExtractionAgent
from autometa.agents.meta_analysis_planner_agent import MetaAnalysisPlannerAgent
from autometa.agents.meta_analysis_runner_agent import MetaAnalysisRunnerAgent
from autometa.agents.protocol_agent import ProtocolAgent
from autometa.agents.screening_agent_v2 import ScreeningAgentV2
from autometa.agents.search_agent import SearchAgent
from autometa.jobs.manager import JobContext
from autometa.schemas.artifacts import ArtifactVersionView, ArtifactView
from autometa.schemas.extraction_models import ExtractionFieldDefinition
from autometa.schemas.meta_models import CSVSummary, MetaAnalysisMethodPlan
from autometa.schemas.models import Paper, PICODefinition, StudyDesignFilter
from autometa.schemas.workflows import (
    ExtractionWorkflowRequest,
    MetaPlanWorkflowRequest,
    MetaRunWorkflowRequest,
    ProtocolWorkflowRequest,
    ScreeningRunWorkflowRequest,
    SearchExpansionRequest,
    SearchQueryWorkflowRequest,
    SearchRunWorkflowRequest,
)
from autometa.services.artifacts import ArtifactService
from autometa.services.files import FileStorage, StoredFileNotFound
from autometa.services.settings import LocalSettingsService


@dataclass(frozen=True)
class WorkflowExecution:
    review_id: str
    request_payload: dict
    input_versions: tuple[ArtifactView | ArtifactVersionView, ...]
    context: JobContext


WorkflowHandler = Callable[[WorkflowExecution], dict | None]


class WorkflowOperationRegistry:
    def __init__(
        self,
        *,
        artifacts: ArtifactService | None = None,
        storage: FileStorage | None = None,
        local_settings: LocalSettingsService | None = None,
    ):
        self._handlers: dict[str, WorkflowHandler] = {}
        self.artifacts = artifacts
        self.storage = storage
        self.local_settings = local_settings
        if artifacts is not None and storage is not None and local_settings is not None:
            self._register_defaults()

    def register(self, operation_kind: str, handler: WorkflowHandler) -> None:
        if not operation_kind or operation_kind in self._handlers:
            raise ValueError(f"Workflow operation is already registered: {operation_kind}")
        self._handlers[operation_kind] = handler

    def contains(self, operation_kind: str) -> bool:
        return operation_kind in self._handlers

    def operation(
        self,
        operation_kind: str,
        review_id: str,
        request_payload: dict,
        input_versions: list[ArtifactView | ArtifactVersionView],
    ) -> Callable[[JobContext], dict | None]:
        def execute(context: JobContext) -> dict | None:
            return self.execute(
                operation_kind,
                WorkflowExecution(
                    review_id=review_id,
                    request_payload=request_payload,
                    input_versions=tuple(input_versions),
                    context=context,
                ),
            )

        return execute

    def execute(self, operation_kind: str, execution: WorkflowExecution) -> dict | None:
        handler = self._handlers.get(operation_kind)
        if handler is None:
            raise LookupError(f"Workflow operation is not registered: {operation_kind}")
        return handler(execution)

    def _register_defaults(self) -> None:
        self.register("protocol.draft", self._protocol_draft)
        self.register("search.query", self._search_query)
        self.register("search.expand", self._search_expand)
        self.register("search.run", self._search_run)
        self.register("screening.run", self._screening_run)
        self.register("extraction.run", self._extraction_run)
        self.register("meta.plan", self._meta_plan)
        self.register("meta.run", self._meta_run)

    def _artifact(self, execution: WorkflowExecution, kind: str):
        for artifact in execution.input_versions:
            if artifact.kind == kind:
                return artifact
        raise ValueError(f"Historical input is missing: {kind}")

    def _require_services(self) -> tuple[ArtifactService, FileStorage]:
        if self.artifacts is None or self.storage is None:
            raise RuntimeError("Default workflow operations are not configured")
        return self.artifacts, self.storage

    def _protocol_draft(self, execution: WorkflowExecution) -> dict:
        artifacts, _ = self._require_services()
        request = ProtocolWorkflowRequest.model_validate(execution.request_payload)
        research_question = request.research_question.strip()
        execution.context.emit("drafting", {"message": "Drafting PICO protocol"})
        draft = ProtocolAgent().run(research_question)
        output = artifacts.save_draft(
            execution.review_id,
            "question_pico",
            {"research_question": research_question, **draft.model_dump()},
            context=execution.context.artifact_context(),
        )
        return self._saved(execution.context, output)

    def _search_query(self, execution: WorkflowExecution) -> dict:
        artifacts, _ = self._require_services()
        request = SearchQueryWorkflowRequest.model_validate(execution.request_payload)
        pico = PICODefinition.model_validate(
            self._artifact(execution, "question_pico").payload.get("pico")
        )
        execution.context.emit("planning", {"message": "Generating PubMed query"})
        strategy = SearchAgent().generate_field_tagged_strategy(pico=pico)
        raw_query = strategy.balanced.query.strip()
        if not raw_query:
            raise ValueError("Generated PubMed query is empty")
        output = artifacts.save_draft(
            execution.review_id,
            "query",
            {
                "strategy_mode": request.strategy_mode,
                "generated_raw_query": raw_query,
                "raw_query": raw_query,
                "strategy": strategy.model_dump(),
            },
            context=execution.context.artifact_context(),
        )
        return self._saved(execution.context, output)

    def _search_run(self, execution: WorkflowExecution) -> dict:
        artifacts, _ = self._require_services()
        request = SearchRunWorkflowRequest.model_validate(execution.request_payload)
        PICODefinition.model_validate(
            self._artifact(execution, "question_pico").payload.get("pico")
        )
        raw_query = str(
            self._artifact(execution, "query").payload.get("raw_query") or ""
        ).strip()
        if not raw_query:
            raise ValueError("Approved Query is empty")
        execution.context.emit("retrieving", {"message": "Retrieving PubMed records"})
        result = SearchAgent().search_with_raw_query(
            raw_query=raw_query,
            retmax=request.retmax,
            min_year=request.min_year,
            max_year=request.max_year,
            fetch_all=request.fetch_all,
        )
        output = artifacts.save_draft(
            execution.review_id,
            "records",
            {
                "query_url": result.query_url,
                "total_count": result.total_count,
                "retrieved_count": result.retrieved_count,
                "search_terms": result.search_terms.model_dump(),
                "papers": [paper.model_dump() for paper in result.papers],
                "strategy_mode": "field_tagged_balanced",
                "raw_query": raw_query,
            },
            context=execution.context.artifact_context(),
        )
        return self._saved(execution.context, output)

    def _search_expand(self, execution: WorkflowExecution) -> dict:
        artifacts, _ = self._require_services()
        request = SearchExpansionRequest.model_validate(execution.request_payload)
        pico = PICODefinition.model_validate(
            self._artifact(execution, "question_pico").payload.get("pico")
        )
        execution.context.emit(
            "seed_retrieval",
            {"message": "Retrieving a bounded seed set from PubMed"},
        )
        result = SearchAgent().expand_with_retrieval_feedback(
            pico,
            seed_retmax=request.seed_retmax,
            included_pmids=request.included_pmids,
            min_year=request.min_year,
            max_year=request.max_year,
        )
        payload = result.model_dump()
        payload.update({
            "strategy_mode": "retrieval_informed",
            "included_pmids": request.included_pmids,
            "generated_raw_query": result.expanded.strategy.balanced.query,
            "raw_query": result.expanded.strategy.balanced.query,
            "strategy": result.expanded.strategy.model_dump(),
        })
        output = artifacts.save_draft(
            execution.review_id,
            "query",
            payload,
            context=execution.context.artifact_context(),
        )
        return self._saved(execution.context, output)

    def _screening_run(self, execution: WorkflowExecution) -> dict:
        artifacts, _ = self._require_services()
        request = ScreeningRunWorkflowRequest.model_validate(execution.request_payload)
        pico = PICODefinition.model_validate(
            self._artifact(execution, "question_pico").payload.get("pico")
        )
        raw_papers = self._artifact(execution, "records").payload.get("papers")
        if not isinstance(raw_papers, list) or not raw_papers:
            raise ValueError("Approved Records contain no papers")
        papers = [Paper.model_validate(paper) for paper in raw_papers]
        execution.context.emit(
            "screening",
            {"message": "Ranking records", "total": len(papers)},
        )
        result = ScreeningAgentV2().run_scored_direct(
            papers=papers,
            pico=pico,
            study_design_filter=StudyDesignFilter(request.study_design_filter),
            max_concurrency=request.max_concurrency,
        ).model_dump()
        decisions = result.get("decisions", [])
        result["selected_pmids"] = [
            str(decision.get("pmid"))
            for decision in decisions
            if decision.get("final_decision") in {"INCLUDE", "UNCERTAIN"}
        ]
        output = artifacts.save_draft(
            execution.review_id,
            "selected_studies",
            result,
            context=execution.context.artifact_context(),
        )
        return self._saved(execution.context, output)

    def _extraction_run(self, execution: WorkflowExecution) -> dict:
        artifacts, storage = self._require_services()
        if self.local_settings is None or not self.local_settings.pdf_disclosure_acknowledged():
            raise ValueError("PDF model disclosure acknowledgement is required")
        request = ExtractionWorkflowRequest.model_validate(execution.request_payload)
        pico = PICODefinition.model_validate(
            self._artifact(execution, "question_pico").payload.get("pico")
        )
        records = self._files(execution.review_id, request.file_ids, "pdf", storage)
        characteristic_fields = [
            ExtractionFieldDefinition.model_validate(item.model_dump())
            for item in request.study_characteristics_fields
        ]
        result_fields = [
            ExtractionFieldDefinition.model_validate(item.model_dump())
            for item in request.study_results_fields
        ]
        execution.context.emit("parsing", {"message": "Parsing locally stored PDFs"})
        paths = [str(storage.resolve(record)) for record in records]
        execution.context.emit(
            "extracting",
            {"message": "Sending relevant PDF text to the configured model service"},
        )
        result = ExtractionAgent().run(
            file_paths=paths,
            file_ids=[record.id for record in records],
            pico=pico,
            char_fields=characteristic_fields,
            result_fields=result_fields,
            top_k=request.top_k,
            max_concurrency=request.max_concurrency,
        )
        output = artifacts.save_draft(
            execution.review_id,
            "sources",
            {
                **result.model_dump(),
                "file_ids": [record.id for record in records],
                "study_characteristics_fields": [
                    item.model_dump() for item in characteristic_fields
                ],
                "study_results_fields": [item.model_dump() for item in result_fields],
            },
            context=execution.context.artifact_context(),
        )
        return self._saved(execution.context, output)

    def _meta_plan(self, execution: WorkflowExecution) -> dict:
        artifacts, storage = self._require_services()
        request = MetaPlanWorkflowRequest.model_validate(execution.request_payload)
        pico = PICODefinition.model_validate(
            self._artifact(execution, "question_pico").payload.get("pico")
        )
        records = self._files(execution.review_id, request.file_ids, "csv", storage)
        execution.context.emit("planning", {"message": "Validating CSV datasets"})
        summaries: list[CSVSummary] = []
        for record in records:
            frame = pd.read_csv(storage.resolve(record), encoding="utf-8-sig")
            if frame.empty:
                raise ValueError(f"CSV dataset has no data rows: {record.original_name}")
            head = frame.head(request.sample_rows)
            sample = head.astype(object).where(pd.notnull(head), None)
            summaries.append(CSVSummary(
                csv_file=record.original_name,
                columns=[str(column) for column in frame.columns],
                row_count=int(len(frame)),
                sample_rows=sample.to_dict(orient="records"),
            ))
        response = MetaAnalysisPlannerAgent().run(
            pico=pico,
            csv_summaries=summaries,
            user_hint=request.user_hint,
            max_concurrency=request.max_concurrency,
        )
        raw = response.model_dump()
        plans = [MetaAnalysisMethodPlan.model_validate(item) for item in raw.get("plans", [])]
        if {plan.csv_file for plan in plans} != {record.original_name for record in records}:
            raise ValueError("Planner must return exactly one plan for each CSV dataset")
        output = artifacts.save_draft(
            execution.review_id,
            "plan",
            jsonable_encoder({
                "file_ids": [record.id for record in records],
                "user_hint": request.user_hint,
                "csv_summaries": [summary.model_dump() for summary in summaries],
                "plans": [plan.model_dump() for plan in plans],
            }),
            context=execution.context.artifact_context(),
        )
        return self._saved(execution.context, output)

    def _meta_run(self, execution: WorkflowExecution) -> dict:
        artifacts, storage = self._require_services()
        MetaRunWorkflowRequest.model_validate(execution.request_payload)
        plan_payload = self._artifact(execution, "plan").payload
        raw_file_ids = plan_payload.get("file_ids")
        raw_plans = plan_payload.get("plans")
        if not isinstance(raw_file_ids, list) or not isinstance(raw_plans, list):
            raise ValueError("Approved Plan is missing datasets or methods")
        records = self._files(
            execution.review_id,
            [str(file_id) for file_id in raw_file_ids],
            "csv",
            storage,
        )
        plans = [MetaAnalysisMethodPlan.model_validate(plan) for plan in raw_plans]
        if {plan.csv_file for plan in plans} != {record.original_name for record in records}:
            raise ValueError("Approved Plan does not match the stored CSV datasets")
        execution.context.emit(
            "analyzing",
            {"message": "Validating and fitting meta-analysis models"},
        )
        frames = {
            record.original_name: pd.read_csv(storage.resolve(record), encoding="utf-8-sig")
            for record in records
        }
        response = MetaAnalysisRunnerAgent().run(plans=plans, csv_frames=frames)
        raw = jsonable_encoder(response.model_dump())
        results = raw.get("results", [])
        if len(results) != len(plans):
            raise ValueError("Meta-analysis did not return one result per approved plan")
        for plan, result in zip(plans, results):
            if plan.output.include_pooled_effect and result.get("pooled_effect") is None:
                details = "; ".join(result.get("warnings", []))
                raise ValueError(
                    f"Analysis failed for {plan.csv_file}: "
                    f"{details or 'pooled effect unavailable'}"
                )
        saved = artifacts.save_drafts(
            execution.review_id,
            {
                "code": {"generated_code": raw.get("generated_code", {})},
                "result": {"results": results},
            },
            context=execution.context.artifact_context(),
        )
        reference = {
            "code_artifact_id": saved["code"].artifact_id,
            "code_version_id": saved["code"].version_id,
            "result_artifact_id": saved["result"].artifact_id,
            "result_version_id": saved["result"].version_id,
        }
        execution.context.emit("artifact_saved", reference)
        return reference

    @staticmethod
    def _saved(context: JobContext, artifact: ArtifactView) -> dict:
        reference = {
            "artifact_id": artifact.artifact_id,
            "version_id": artifact.version_id,
            "kind": artifact.kind,
            "version": artifact.version,
        }
        context.emit("artifact_saved", reference)
        return reference

    @staticmethod
    def _files(review_id: str, file_ids: list[str], kind: str, storage: FileStorage):
        records = []
        for file_id in file_ids:
            try:
                record = storage.get(file_id)
            except StoredFileNotFound as exc:
                raise ValueError(f"Stored file not found: {file_id}") from exc
            if record.review_id != review_id:
                raise ValueError("Stored file does not belong to this Review")
            if record.kind != kind:
                raise ValueError(f"Workflow accepts {kind.upper()} files only")
            records.append(record)
        return records
