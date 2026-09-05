from __future__ import annotations

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from autometa.config import get_settings


def test_phase_one_database_upgrades_without_losing_rows(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AUTOMETA_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    config = Config("alembic.ini")
    command.upgrade(config, "0001")

    database_path = tmp_path / "autometa.db"
    engine = create_engine(f"sqlite+pysqlite:///{database_path}")
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO reviews "
            "(id, name, entry_mode, status, current_stage, created_at, updated_at) "
            "VALUES ('review-1', 'Existing review', 'guided', 'draft', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ))

    command.upgrade(config, "head")

    tables = set(inspect(engine).get_table_names())
    assert {
        "review_events",
        "researcher_edits",
        "provenance_edges",
        "rerun_relationships",
    } <= tables
    with engine.connect() as connection:
        assert connection.scalar(text(
            "SELECT name FROM reviews WHERE id = 'review-1'"
        )) == "Existing review"
        stage_run_columns = {
            column["name"] for column in inspect(connection).get_columns("stage_runs")
        }
        file_columns = {
            column["name"] for column in inspect(connection).get_columns("files")
        }
        file_unique_constraints = {
            tuple(item["column_names"])
            for item in inspect(connection).get_unique_constraints("files")
        }
    assert {
        "operation_kind",
        "request_payload",
        "input_artifact_version_ids",
        "output_artifact_version_ids",
    } <= stage_run_columns
    assert "kind" in file_columns
    assert ("review_id", "kind", "sha256") in file_unique_constraints

    engine.dispose()
    get_settings.cache_clear()
