from fastapi.testclient import TestClient

from autometa.api.main import app


client = TestClient(app)


def test_versioned_health_endpoint() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "product": "AutoMeta"}


def test_all_api_routes_are_versioned() -> None:
    paths = set(app.openapi()["paths"])
    assert "/api/v1/protocol/draft" in paths
    assert "/api/v1/search" in paths
    assert "/api/v1/screen/stream" in paths
    assert "/api/v1/extract/stream" in paths
    assert "/api/v1/meta/run" in paths
    assert not any(path.startswith("/api/") and not path.startswith("/api/v1/") for path in paths)
