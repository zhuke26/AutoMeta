import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_autometa_api_is_importable() -> None:
    module = importlib.import_module("autometa.api.main")
    assert module.app.title == "AutoMeta"


def test_upload_directory_remains_at_repository_root() -> None:
    module = importlib.import_module("autometa.api.routers.extraction")
    assert module.UPLOAD_DIR.resolve() == (ROOT / "data" / "uploads").resolve()


def test_runtime_tree_contains_no_legacy_identity() -> None:
    forbidden = ("Auto" + "SR", "auto" + "sr")
    roots = [ROOT / "autometa", ROOT / "README.md", ROOT / "run_local.sh"]
    for root in roots:
        paths = [root] if root.is_file() else list(root.rglob("*"))
        for path in paths:
            if path.is_file() and path.suffix in {".py", ".html", ".md", ".sh"}:
                text = path.read_text(encoding="utf-8", errors="ignore")
                assert not any(token in text for token in forbidden), str(path)
