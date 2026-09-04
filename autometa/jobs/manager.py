from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event, RLock
import time

from autometa.persistence.models import JobState
from autometa.repositories.jobs import JobRepository
from autometa.schemas.jobs import JobEventView, JobView


class JobNotFound(LookupError):
    pass


class JobConflict(RuntimeError):
    pass


class JobContext:
    def __init__(self, manager: "JobManager", job_id: str, cancellation: Event):
        self._manager = manager
        self.job_id = job_id
        self._cancellation = cancellation

    @property
    def cancelled(self) -> bool:
        return self._cancellation.is_set()

    def emit(self, event_type: str, payload: dict) -> JobEventView:
        return self._manager._emit(self.job_id, event_type, payload)


JobOperation = Callable[[JobContext], dict | None]


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

    @property
    def closed(self) -> bool:
        return self._closed

    def submit(self, review_id: str, stage: str, operation: JobOperation) -> JobView:
        with self._lock:
            if self._closed:
                raise JobConflict("Job manager is shut down")
            try:
                job = self.repository.create(review_id, stage)
            except RuntimeError as exc:
                raise JobConflict(str(exc)) from exc
            cancellation = Event()
            self._cancellations[job.id] = cancellation
            self._futures[job.id] = self._executor.submit(
                self._execute,
                job.id,
                operation,
                cancellation,
            )
            return JobView.model_validate(job)

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
    ) -> None:
        try:
            self.repository.transition(job_id, JobState.RUNNING)
            context = JobContext(self, job_id, cancellation)
            result = operation(context)
            if cancellation.is_set():
                self.repository.transition(job_id, JobState.CANCELLED)
            else:
                self.repository.transition(
                    job_id,
                    JobState.SUCCEEDED,
                    result_reference=self._sanitize_payload(result or {}),
                )
        except Exception as exc:
            self.repository.transition(
                job_id,
                JobState.FAILED,
                error=self._safe_error(exc),
            )
        finally:
            with self._lock:
                self._futures.pop(job_id, None)
                self._cancellations.pop(job_id, None)

    def _emit(self, job_id: str, event_type: str, payload: dict) -> JobEventView:
        with self._lock:
            event = self.repository.emit(
                job_id,
                event_type,
                self._sanitize_payload(payload),
            )
            return JobEventView.model_validate(event)

    def _safe_error(self, error: Exception) -> str:
        return self._redact_text(str(error))[:4000]

    def _sanitize_payload(self, value):
        if isinstance(value, str):
            return self._redact_text(value)
        if isinstance(value, dict):
            return {
                self._redact_text(str(key)): self._sanitize_payload(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [self._sanitize_payload(item) for item in value]
        return value

    def _redact_text(self, text: str) -> str:
        settings = self.repository.database.settings
        for value in (settings.llm_api_key, settings.pubmed_api_key):
            secret = (
                value.get_secret_value()
                if hasattr(value, "get_secret_value")
                else str(value or "")
            )
            if secret:
                text = text.replace(secret, "[REDACTED]")
        return text
