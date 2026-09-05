from __future__ import annotations

import csv
import hashlib
import io
import os
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from autometa.persistence.database import Database
from autometa.persistence.models import FileRecord
from autometa.repositories.files import FileRepository
from autometa.repositories.reviews import ReviewRepository


class InvalidUpload(ValueError):
    pass


class StoredFileNotFound(LookupError):
    pass


class FileStorage:
    def __init__(self, database: Database):
        self.database = database
        self.repository = FileRepository(database)
        self.reviews = ReviewRepository(database)
        self.data_dir = database.data_dir
        self.max_bytes = database.settings.autometa_max_upload_mb * 1024 * 1024

    def save_bytes(
        self,
        review_id: str,
        filename: str,
        mime_type: str,
        content: bytes,
    ) -> FileRecord:
        if self.reviews.get(review_id) is None:
            raise StoredFileNotFound(f"Review not found: {review_id}")
        self._validate_pdf(filename, mime_type, content)
        return self._save_validated(
            review_id,
            filename,
            "application/pdf",
            content,
            directory="uploads",
            suffix=".pdf",
            kind="pdf",
        )

    def save_dataset_bytes(
        self,
        review_id: str,
        filename: str,
        mime_type: str,
        content: bytes,
    ) -> FileRecord:
        if self.reviews.get(review_id) is None:
            raise StoredFileNotFound(f"Review not found: {review_id}")
        self._validate_csv(filename, mime_type, content)
        return self._save_validated(
            review_id,
            filename,
            "text/csv",
            content,
            directory="datasets",
            suffix=".csv",
            kind="csv",
        )

    def save_generated_figure(
        self,
        review_id: str,
        filename: str,
        mime_type: str,
        content: bytes,
    ) -> FileRecord:
        if self.reviews.get(review_id) is None:
            raise StoredFileNotFound(f"Review not found: {review_id}")
        self._validate_filename(filename, "Figure")
        allowed = {
            "image/svg+xml": ".svg",
            "image/png": ".png",
            "application/pdf": ".pdf",
        }
        suffix = allowed.get(mime_type)
        if suffix is None or Path(filename).suffix.lower() != suffix:
            raise InvalidUpload("Generated figure format is not supported")
        if not content or len(content) > self.max_bytes:
            raise InvalidUpload("Generated figure is empty or exceeds the size limit")
        return self._save_validated(
            review_id,
            filename,
            mime_type,
            content,
            directory="figures",
            suffix=suffix,
            kind="figure",
        )

    def _save_validated(
        self,
        review_id: str,
        filename: str,
        normalized_mime_type: str,
        content: bytes,
        *,
        directory: str,
        suffix: str,
        kind: str,
    ) -> FileRecord:
        digest = hashlib.sha256(content).hexdigest()
        existing = self.repository.find_by_hash(review_id, digest)
        if existing is not None:
            return existing

        record_id = uuid4().hex
        upload_dir = self.review_directory(review_id) / directory
        upload_dir.mkdir(parents=True, exist_ok=True)
        destination = upload_dir / f"{record_id}{suffix}"
        descriptor, temporary_name = tempfile.mkstemp(
            dir=upload_dir,
            prefix=".upload-",
            suffix=".part",
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, destination)
            record = FileRecord(
                id=record_id,
                review_id=review_id,
                original_name=filename,
                stored_name=destination.name,
                relative_path=destination.relative_to(self.data_dir).as_posix(),
                sha256=digest,
                mime_type=normalized_mime_type,
                kind=kind,
                size_bytes=len(content),
            )
            try:
                return self.repository.create(record)
            except Exception:
                destination.unlink(missing_ok=True)
                raise
        finally:
            Path(temporary_name).unlink(missing_ok=True)

    async def save_upload(self, review_id: str, upload: UploadFile) -> FileRecord:
        content = await self._read_upload(upload, "PDF")
        return self.save_bytes(
            review_id,
            upload.filename or "",
            upload.content_type or "",
            content,
        )

    async def save_dataset_upload(
        self,
        review_id: str,
        upload: UploadFile,
    ) -> FileRecord:
        content = await self._read_upload(upload, "CSV")
        return self.save_dataset_bytes(
            review_id,
            upload.filename or "",
            upload.content_type or "",
            content,
        )

    async def _read_upload(self, upload: UploadFile, label: str) -> bytes:
        chunks: list[bytes] = []
        size = 0
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > self.max_bytes:
                raise InvalidUpload(
                    f"{label} exceeds the {self.database.settings.autometa_max_upload_mb} MB size limit"
                )
            chunks.append(chunk)
        return b"".join(chunks)

    def list_for_review(self, review_id: str, kind: str | None = None) -> list[FileRecord]:
        if self.reviews.get(review_id) is None:
            raise StoredFileNotFound(f"Review not found: {review_id}")
        records = self.repository.list_for_review(review_id)
        return [record for record in records if kind is None or record.kind == kind]

    def get(self, file_id: str) -> FileRecord:
        record = self.repository.get(file_id)
        if record is None:
            raise StoredFileNotFound(file_id)
        return record

    def get_review_file(
        self,
        review_id: str,
        file_id: str,
        *,
        kind: str | None = None,
    ) -> FileRecord:
        record = self.get(file_id)
        if record.review_id != review_id or (kind is not None and record.kind != kind):
            raise StoredFileNotFound(file_id)
        return record

    def resolve(self, record: FileRecord) -> Path:
        path = (self.data_dir / record.relative_path).resolve()
        try:
            path.relative_to(self.data_dir)
        except ValueError as exc:
            raise StoredFileNotFound(record.id) from exc
        if not path.is_file():
            raise StoredFileNotFound(record.id)
        return path

    def review_directory(self, review_id: str) -> Path:
        return self.data_dir / "reviews" / review_id

    def stage_review_directory(self, review_id: str) -> tuple[Path, Path | None]:
        source = self.review_directory(review_id)
        if not source.exists():
            return source, None
        staged = source.parent / f".deleting-{review_id}-{uuid4().hex}"
        os.replace(source, staged)
        return source, staged

    @staticmethod
    def restore_review_directory(source: Path, staged: Path | None) -> None:
        if staged is not None and staged.exists():
            os.replace(staged, source)

    @staticmethod
    def purge_review_directory(staged: Path | None) -> None:
        if staged is not None:
            shutil.rmtree(staged, ignore_errors=False)

    def _validate_filename(self, filename: str, label: str) -> None:
        if not filename or Path(filename).name != filename or "/" in filename or "\\" in filename:
            raise InvalidUpload(f"{label} filename must not contain path separators")

    def _validate_pdf(self, filename: str, mime_type: str, content: bytes) -> None:
        self._validate_filename(filename, "PDF")
        if Path(filename).suffix.lower() != ".pdf":
            raise InvalidUpload("Only .pdf files are accepted")
        if mime_type.lower() != "application/pdf":
            raise InvalidUpload("Only application/pdf uploads are accepted")
        if not content.startswith(b"%PDF-"):
            raise InvalidUpload("Uploaded file does not have a PDF signature")
        if len(content) > self.max_bytes:
            raise InvalidUpload(
                f"PDF exceeds the {self.database.settings.autometa_max_upload_mb} MB size limit"
            )

    def _validate_csv(self, filename: str, mime_type: str, content: bytes) -> None:
        self._validate_filename(filename, "CSV")
        if Path(filename).suffix.lower() != ".csv":
            raise InvalidUpload("Only .csv dataset files are accepted")
        if mime_type.lower() not in {
            "text/csv",
            "application/csv",
            "application/vnd.ms-excel",
        }:
            raise InvalidUpload("Only CSV dataset uploads are accepted")
        if not content:
            raise InvalidUpload("CSV dataset is empty")
        if len(content) > self.max_bytes:
            raise InvalidUpload(
                f"CSV exceeds the {self.database.settings.autometa_max_upload_mb} MB size limit"
            )
        try:
            text = content.decode("utf-8-sig")
            header = next(csv.reader(io.StringIO(text)))
        except (UnicodeDecodeError, StopIteration, csv.Error) as exc:
            raise InvalidUpload("CSV dataset must be valid UTF-8 CSV") from exc
        if not any(column.strip() for column in header):
            raise InvalidUpload("CSV dataset must contain a header row")
