import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_pyproject_exposes_autometa_command_without_cuda_index() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["requires-python"] == ">=3.11,<3.13"
    assert data["project"]["license"] == "MIT"
    assert data["project"]["license-files"] == ["LICENSE"]
    assert data["project"]["scripts"]["autometa"] == "autometa.cli:main"
    serialized = str(data).lower()
    assert "cu128" not in serialized
    assert "extra-index-url" not in serialized
