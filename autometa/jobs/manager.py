from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event, RLock

from autometa.persistence.models import JobState
from autometa.repositories.jobs import JobRepository
from autometa.schemas.artifacts import ArtifactWriteContext
from autometa.schemas.jobs import JobEventView, JobView
from autometa.schemas.provenance import Producer
from autometa.security import SecretRedactor


class JobNotFound(LookupError):
    pass


class JobConflict(RuntimeError):
    pass


class JobContext:
    def __init__(
        self,
        manager: "JobManager",
        job_id: str,
        cancellation: Event,
        *,
        stage_run_id: str | None = None,
        input_version_ids: tuple[str, ...] = (),
        metadata: dict | None = None,
    ):
        self._manager = manager
        self.job_id = job_id
        self._cancellation = cancellation
        self.stage_run_id = stage_run_id
        self.input_version_ids = input_version_ids
        self.metadata = dict(metadata or {})

    @property
    def cancelled(self) -> bool:
        return self._cancellation.is_set()

    def emit(self, event_type: str, payload: dict) -> JobEventView:
        return self._manager._emit(self.job_id, event_type, payload)

    def artifact_context(self) -> ArtifactWriteContext:
        return ArtifactWriteContext(
            producer=Producer.AGENT,
            stage_run_id=self.stage_run_id,
            job_id=self.job_id,
            input_version_ids=self.input_version_ids,
            metadata=self.metadata,
        )


JobOperation = Callable[[JobContext], dict | None]
JobCreatedHook = Callable[[JobView], str | None]
JobStateHook = Callable[[str, JobState], None]


class JobManager:
    def __init__(self, repository: JobRepository, max_workers: int):
        self.repository = repository
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="autometa-job",
        )
        self._lock = RLock()
        self._futures: dict[str, Future] = {}
        self._cancellations: dict[str, Event] = {}
        self._closed = False
        self._redactor = SecretRedactor(repository.database.settings)

    @property
    def closed(self) -> bool:
        return self._closed

    def submit(
        self,
        review_id: str,
        stage: str,
        operation: JobOperation,
        *,
        on_created: JobCreatedHook | None = None,
        on_state_change: JobStateHook | None = None,
        input_version_ids: tuple[str, ...] = (),
        metadata: dict | None = None,
    ) -> JobView:
        with self._lock:
            if self._closed:
                raise JobConflict("Job manager is shut down")
            try:
                job = self.repository.create(review_id, stage)
            except RuntimeError as exc:
                raise JobConflict(str(exc)) from exc
            job_view = JobView.model_validate(job)
            stage_run_id = None
            if on_created is not None:
                try:
                    stage_run_id = on_created(job_view)
                except Exception as exc:
                    self.repository.transition(
                        job.id,
                        JobState.FAILED,
                        error=self._safe_error(exc),
                    )
                    raise
            cancellation = Event()
            self._cancellations[job.id] = cancellation
            self._futures[job.id] = self._executor.submit(
                self._execute,
                job.id,
                operation,
                cancellation,
                on_state_change,
                stage_run_id,
                input_version_ids,
                metadata or {},
            )
            return job_view

    def get(self, job_id: str) -> JobView:
        job = self.repository.get(job_id)
        if job is None:
            raise JobNotFound(job_id)
        return JobView.model_validate(job)

    def events(self, job_id: str, after_sequence: int = 0) -> list[JobEventView]:
        if self.repository.get(job_id) is None:
            raise JobNotFound(job_id)
        return [
            JobEventView.model_validate(event)
            for event in self.repository.events(job_id, after_sequence)
        ]

    def list_for_review(
        self,
        review_id: str,
        *,
        stage: str | None = None,
        limit: int = 20,
    ) -> list[JobView]:
        return [
            JobView.model_validate(job)
            for job in self.repository.list_for_review(
                review_id,
                stage=stage,
                limit=limit,
            )
        ]

    def cancel_review(self, review_id: str) -> int:
        cancelled = 0
        with self._lock:
            for job in self.repository.active_for_review(review_id):
                cancellation = self._cancellations.get(job.id)
                if cancellation is not None:
                    cancellation.set()
                future = self._futures.get(job.id)
                if future is not None and future.cancel():
                    self.repository.transition(job.id, JobState.CANCELLED)
                    self._futures.pop(job.id, None)
                    self._cancellations.pop(job.id, None)
                cancelled += 1
        return cancelled

    def wait_for_review(self, review_id: str, timeout: float = 5.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.repository.active_for_review(review_id):
                return True
            time.sleep(0.01)
        return not self.repository.active_for_review(review_id)

    def shutdown(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for cancellation in self._cancellations.values():
                cancellation.set()
        self._executor.shutdown(wait=True, cancel_futures=True)

    def _execute(
        self,
        job_id: str,
        operation: JobOperation,
        cancellation: Event,
        on_state_change: JobStateHook | None,
        stage_run_id: str | None,
        input_version_ids: tuple[str, ...],
        metadata: dict,
    ) -> None:
        try:
            self.repository.transition(job_id, JobState.RUNNING)
            self._notify_state(on_state_change, job_id, JobState.RUNNING)
            context = JobContext(
                self,
                job_id,
                cancellation,
                stage_run_id=stage_run_id,
                input_version_ids=input_version_ids,
                metadata=metadata,
            )
            result = operation(context)
            if cancellation.is_set():
                self._notify_state(on_state_change, job_id, JobState.CANCELLED)
                self.repository.transition(job_id, JobState.CANCELLED)
            else:
                self._notify_state(on_state_change, job_id, JobState.SUCCEEDED)
                self.repository.transition(
                    job_id,
                    JobState.SUCCEEDED,
                    result_reference=self._sanitize_payload(result or {}),
                )
        except Exception as exc:
            try:
                self._notify_state(on_state_change, job_id, JobState.FAILED)
            except Exception:
                pass
            self.repository.transition(
                job_id,
                JobState.FAILED,
                error=self._safe_error(exc),
            )
        finally:
            with self._lock:
                self._futures.pop(job_id, None)
                self._cancellations.pop(job_id, None)

    @staticmethod
    def _notify_state(
        hook: JobStateHook | None,
        job_id: str,
        state: JobState,
    ) -> None:
        if hook is not None:
            hook(job_id, state)

    def _emit(self, job_id: str, event_type: str, payload: dict) -> JobEventView:
        with self._lock:
            event = self.repository.emit(
                job_id,
                event_type,
                self._sanitize_payload(payload),
            )
            return JobEventView.model_validate(event)

    def _safe_error(self, error: Exception) -> str:
        return self._redactor.text(str(error))[:4000]

    def _sanitize_payload(self, value):
        return self._redactor.payload(value)
