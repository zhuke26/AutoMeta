import pytest
from fastapi.testclient import TestClient

from autometa.api.dependencies import get_database
from autometa.api.main import app
from autometa.config import Settings
from autometa.persistence.database import Database


@pytest.fixture
def database(tmp_path):
    database = Database(Settings(_env_file=None, autometa_data_dir=tmp_path))
    database.create_schema()
    yield database
    database.dispose()


@pytest.fixture
def client(database):
    app.dependency_overrides[get_database] = lambda: database
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
