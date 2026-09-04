from pydantic import BaseModel


class PdfDisclosureSetting(BaseModel):
    acknowledged: bool
