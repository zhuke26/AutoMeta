from fastapi.testclient import TestClient

from autometa.api.main import create_app
from autometa.config import Settings


def test_system_status_reports_readiness_without_secrets(tmp_path) -> None:
    secret = "STATUS_SENTINEL_SECRET"
    settings = Settings(
        _env_file=None,
        autometa_data_dir=tmp_path,
        llm_api_key=secret,
        llm_base_url=f"https://user:{secret}@example.test/v1?token={secret}#private",
        llm_model="general-model",
        extraction_model="extract-model",
    )
    test_app = create_app(settings)

    with TestClient(test_app) as client:
        response = client.get("/api/v1/system/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["product"] == "AutoMeta"
    assert payload["database"] == "ready"
    assert payload["provider_configured"] is True
    assert payload["provider_base_url"] == "https://example.test/v1"
    assert payload["models"]["default"] == "general-model"
    assert payload["models"]["extraction"] == "extract-model"
    assert "api_key" not in response.text.lower()
    assert secret not in response.text
