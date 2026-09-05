from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends

from autometa import __version__
from autometa.api.dependencies import get_app_settings, get_database
from autometa.config import AgentStage, Settings
from autometa.persistence.database import Database
from autometa.schemas.system import SystemStatus

router = APIRouter(prefix="/system", tags=["system"])


def _public_provider_url(value: str) -> str:
    parsed = urlsplit(value)
    hostname = parsed.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    netloc = hostname
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


@router.get("/status", response_model=SystemStatus)
def system_status(
    database: Database = Depends(get_database),
    settings: Settings = Depends(get_app_settings),
) -> SystemStatus:
    models = {"default": settings.llm_model}
    models.update({stage.value: settings.model_for(stage) for stage in AgentStage})
    return SystemStatus(
        product="AutoMeta",
        version=__version__,
        database="ready" if database.is_ready() else "unavailable",
        provider_base_url=_public_provider_url(settings.llm_base_url),
        provider_configured=bool(settings.llm_api_key.get_secret_value()),
        models=models,
        data_directory=str(database.data_dir),
        host=settings.autometa_host,
        port=settings.autometa_port,
    )
