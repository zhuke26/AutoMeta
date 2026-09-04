from autometa.cli import build_uvicorn_options
from autometa.config import Settings


def test_uvicorn_defaults_are_local_only() -> None:
    options = build_uvicorn_options(Settings(_env_file=None, llm_model="test-model"))
    assert options == {"host": "127.0.0.1", "port": 8016}


def test_lan_binding_is_explicit() -> None:
    options = build_uvicorn_options(
        Settings(
            _env_file=None,
            llm_model="test-model",
            autometa_host="0.0.0.0",
            autometa_port=9000,
        )
    )
    assert options == {"host": "0.0.0.0", "port": 9000}
