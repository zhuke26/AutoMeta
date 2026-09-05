from __future__ import annotations

from sqlalchemy import select

from autometa.persistence.database import Database
from autometa.persistence.models import FileRecord


class FileRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(self, record: FileRecord) -> FileRecord:
        with self.database.session() as session:
            session.add(record)
            session.flush()
            return record

    def find_by_hash(
        self,
        review_id: str,
        sha256: str,
        *,
        kind: str,
    ) -> FileRecord | None:
        with self.database.session() as session:
            statement = select(FileRecord).where(
                FileRecord.review_id == review_id,
                FileRecord.kind == kind,
                FileRecord.sha256 == sha256,
            )
            return session.scalar(statement)

    def get(self, file_id: str) -> FileRecord | None:
        with self.database.session() as session:
            return session.get(FileRecord, file_id)

    def list_for_review(self, review_id: str) -> list[FileRecord]:
        with self.database.session() as session:
            statement = (
                select(FileRecord)
                .where(FileRecord.review_id == review_id)
                .order_by(FileRecord.created_at.asc())
            )
            return list(session.scalars(statement))

    def delete(self, file_id: str) -> bool:
        with self.database.session() as session:
            record = session.get(FileRecord, file_id)
            if record is None:
                return False
            session.delete(record)
            return True
