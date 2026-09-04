from autometa.repositories.settings import LocalSettingsRepository


PDF_DISCLOSURE_KEY = "pdf_model_disclosure"


class LocalSettingsService:
    def __init__(self, repository: LocalSettingsRepository):
        self.repository = repository

    def pdf_disclosure_acknowledged(self) -> bool:
        value = self.repository.get(PDF_DISCLOSURE_KEY) or {}
        return value.get("acknowledged") is True

    def set_pdf_disclosure(self, acknowledged: bool) -> bool:
        value = self.repository.set(
            PDF_DISCLOSURE_KEY,
            {"acknowledged": acknowledged},
        )
        return value.get("acknowledged") is True
