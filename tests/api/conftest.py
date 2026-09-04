import pytest
from fastapi.testclient import TestClient

from autometa.api.main import create_app
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
    test_app = create_app(database.settings, database=database)
    with TestClient(test_app) as test_client:
        yield test_client
