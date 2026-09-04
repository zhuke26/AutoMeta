from fastapi import APIRouter, Depends

from autometa.api.dependencies import get_local_settings
from autometa.schemas.settings import PdfDisclosureSetting
from autometa.services.settings import LocalSettingsService


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/pdf-disclosure", response_model=PdfDisclosureSetting)
def get_pdf_disclosure(
    settings: LocalSettingsService = Depends(get_local_settings),
) -> PdfDisclosureSetting:
    return PdfDisclosureSetting(
        acknowledged=settings.pdf_disclosure_acknowledged(),
    )


@router.put("/pdf-disclosure", response_model=PdfDisclosureSetting)
def update_pdf_disclosure(
    request: PdfDisclosureSetting,
    settings: LocalSettingsService = Depends(get_local_settings),
) -> PdfDisclosureSetting:
    return PdfDisclosureSetting(
        acknowledged=settings.set_pdf_disclosure(request.acknowledged),
    )
