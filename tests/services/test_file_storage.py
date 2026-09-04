import pytest

from autometa.config import Settings
from autometa.persistence.database import Database
from autometa.persistence.models import ReviewMode
from autometa.repositories.reviews import ReviewRepository
from autometa.services.files import FileStorage, InvalidUpload


@pytest.fixture
def database(tmp_path):
    database = Database(
        Settings(
            _env_file=None,
            autometa_data_dir=tmp_path,
            autometa_max_upload_mb=1,
        )
    )
    database.create_schema()
    yield database
    database.dispose()


@pytest.fixture
def review(database):
    return ReviewRepository(database).create("Extraction review", ReviewMode.EXTRACTION)


@pytest.fixture
def file_storage(database):
    return FileStorage(database)


def test_pdf_is_stored_under_review_directory(file_storage, review) -> None:
    record = file_storage.save_bytes(
        review.id, "study.pdf", "application/pdf", b"%PDF-1.7\nbody"
    )

    assert record.relative_path.startswith(f"reviews/{review.id}/uploads/")
    assert file_storage.resolve(record).read_bytes().startswith(b"%PDF-")


def test_duplicate_pdf_reuses_record(file_storage, review) -> None:
    first = file_storage.save_bytes(
        review.id, "one.pdf", "application/pdf", b"%PDF-1.7\nsame"
    )
    second = file_storage.save_bytes(
        review.id, "two.pdf", "application/pdf", b"%PDF-1.7\nsame"
    )

    assert second.id == first.id
    assert second.original_name == "one.pdf"


@pytest.mark.parametrize(
    ("name", "mime_type", "content"),
    (
        ("fake.pdf", "application/pdf", b"not-pdf"),
        ("study.txt", "application/pdf", b"%PDF-1.7"),
        ("study.pdf", "text/plain", b"%PDF-1.7"),
        ("../study.pdf", "application/pdf", b"%PDF-1.7"),
    ),
)
def test_invalid_upload_is_rejected(file_storage, review, name, mime_type, content) -> None:
    with pytest.raises(InvalidUpload):
        file_storage.save_bytes(review.id, name, mime_type, content)


def test_oversized_upload_is_rejected(file_storage, review) -> None:
    with pytest.raises(InvalidUpload, match="size limit"):
        file_storage.save_bytes(
            review.id,
            "large.pdf",
            "application/pdf",
            b"%PDF-" + (b"x" * 1024 * 1024),
        )
