from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_docker_image_uses_supported_cpu_runtime_and_packaged_frontend() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert dockerfile.startswith("FROM python:3.12-slim")
    assert "AUTOMETA_HOST=0.0.0.0" in dockerfile
    assert "EXPOSE 8016" in dockerfile
    assert "python -m alembic upgrade head" in dockerfile
    assert "python -m autometa serve" in dockerfile
    assert "node" not in dockerfile.lower()
    assert "cuda" not in dockerfile.lower()
    assert "frontend" in dockerignore
    assert ".env" in dockerignore
    assert "data" in dockerignore


def test_ci_builds_and_smoke_tests_the_container() -> None:
    workflow = (ROOT / ".github" / "workflows" / "foundation.yml").read_text(
        encoding="utf-8"
    )

    assert "Docker / Linux CPU" in workflow
    assert "docker build" in workflow
    assert "/api/v1/health" in workflow
