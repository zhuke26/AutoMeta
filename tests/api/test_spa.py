from pathlib import Path

from fastapi.testclient import TestClient

from autometa.api.main import app


client = TestClient(app)
STATIC_INDEX = Path(__file__).resolve().parents[2] / "autometa" / "static" / "index.html"


def test_root_serves_autometa_spa() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "AutoMeta" in response.text
    assert "Load Example" not in response.text


def test_spa_calls_only_versioned_api_paths() -> None:
    source = STATIC_INDEX.read_text(encoding="utf-8")
    assert "fetch('/api/" not in source.replace("fetch('/api/v1/", "")
