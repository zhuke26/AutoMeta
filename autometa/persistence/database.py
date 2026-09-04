from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, event, inspect, update
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

from autometa.config import Settings
from autometa.persistence.models import Base, Job, JobState


class Database:
    def __init__(self, settings: Settings):
        self.data_dir = Path(settings.autometa_data_dir).expanduser().resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "autometa.db"
        self.url = URL.create("sqlite+pysqlite", database=str(self.path))
        self.engine: Engine = create_engine(
            self.url,
            connect_args={"check_same_thread": False},
        )
        event.listen(self.engine, "connect", self._enable_foreign_keys)
        self._session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
        )

    @staticmethod
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def inspect_table_names(self) -> list[str]:
        return inspect(self.engine).get_table_names()

    def mark_running_jobs_interrupted(self) -> int:
        with self.session() as session:
            result = session.execute(
                update(Job)
                .where(Job.state.in_((JobState.QUEUED, JobState.RUNNING)))
                .values(
                    state=JobState.INTERRUPTED,
                    finished_at=datetime.now(timezone.utc),
                )
            )
            return int(result.rowcount or 0)

    def dispose(self) -> None:
        self.engine.dispose()
