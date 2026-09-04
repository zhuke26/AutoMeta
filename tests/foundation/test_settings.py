from autometa.config import AgentStage, Settings


def test_stage_model_uses_global_default() -> None:
    settings = Settings(
        _env_file=None,
        llm_api_key="secret",
        llm_base_url="https://example.test/v1",
        llm_model="general-model",
    )
    assert settings.model_for(AgentStage.SEARCH) == "general-model"


def test_stage_model_override_wins() -> None:
    settings = Settings(
        _env_file=None,
        llm_api_key="secret",
        llm_base_url="https://example.test/v1",
        llm_model="general-model",
        extraction_model="extract-model",
    )
    assert settings.model_for(AgentStage.EXTRACTION) == "extract-model"


def test_secret_is_redacted_from_serialized_settings() -> None:
    settings = Settings(
        _env_file=None,
        llm_api_key="do-not-expose",
        llm_base_url="https://example.test/v1",
        llm_model="general-model",
    )
    assert "do-not-expose" not in str(settings.safe_summary())
