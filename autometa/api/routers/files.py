from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from autometa.api.dependencies import get_file_storage
from autometa.schemas.files import FileView
from autometa.services.files import FileStorage, InvalidUpload, StoredFileNotFound


router = APIRouter(tags=["files"])


@router.post(
    "/reviews/{review_id}/files",
    response_model=list[FileView],
    status_code=status.HTTP_201_CREATED,
)
async def upload_review_files(
    review_id: str,
    files: list[UploadFile] = File(...),
    storage: FileStorage = Depends(get_file_storage),
) -> list[FileView]:
    try:
        records = [await storage.save_upload(review_id, upload) for upload in files]
    except StoredFileNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidUpload as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [FileView.model_validate(record) for record in records]


@router.get("/reviews/{review_id}/files", response_model=list[FileView])
def list_review_files(
    review_id: str,
    storage: FileStorage = Depends(get_file_storage),
) -> list[FileView]:
    try:
        return [
            FileView.model_validate(item)
            for item in storage.list_for_review(review_id, kind="pdf")
        ]
    except StoredFileNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/files/{file_id}/content", response_class=FileResponse)
def read_file(
    file_id: str,
    storage: FileStorage = Depends(get_file_storage),
) -> FileResponse:
    try:
        record = storage.get(file_id)
        path = storage.resolve(record)
    except StoredFileNotFound as exc:
        raise HTTPException(status_code=404, detail=f"File not found: {file_id}") from exc
    return FileResponse(path, media_type=record.mime_type, filename=record.original_name)


@router.post(
    "/reviews/{review_id}/datasets",
    response_model=list[FileView],
    status_code=status.HTTP_201_CREATED,
)
async def upload_review_datasets(
    review_id: str,
    files: list[UploadFile] = File(...),
    storage: FileStorage = Depends(get_file_storage),
) -> list[FileView]:
    try:
        records = [
            await storage.save_dataset_upload(review_id, upload)
            for upload in files
        ]
    except StoredFileNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidUpload as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [FileView.model_validate(record) for record in records]


@router.get("/reviews/{review_id}/datasets", response_model=list[FileView])
def list_review_datasets(
    review_id: str,
    storage: FileStorage = Depends(get_file_storage),
) -> list[FileView]:
    try:
        return [
            FileView.model_validate(item)
            for item in storage.list_for_review(review_id, kind="csv")
        ]
    except StoredFileNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
