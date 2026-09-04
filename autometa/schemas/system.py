from pydantic import BaseModel


class SystemStatus(BaseModel):
    product: str
    version: str
    database: str
    provider_base_url: str
    provider_configured: bool
    models: dict[str, str]
    data_directory: str
    host: str
    port: int
