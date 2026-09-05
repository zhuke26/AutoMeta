import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

ROOT = Path(__file__).resolve().parents[2]

def assert_public_tree_policy(root: Path) -> None:
    tracked = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
    ).stdout
    ignore_policy = subprocess.run(
        ["git", "-C", str(root), "show", ":.gitignore"],
        check=True,
        capture_output=True,
    ).stdout
    with TemporaryDirectory(prefix="autometa-public-tree-policy-") as temporary:
        policy_root = Path(temporary)
        subprocess.run(["git", "init", "-q", str(policy_root)], check=True)
        (policy_root / ".gitignore").write_bytes(ignore_policy)
        (policy_root / ".git" / "info" / "exclude").write_bytes(b"")
        global_excludes = policy_root / "empty-global-excludes"
        global_excludes.write_bytes(b"")
        ignored = subprocess.run(
            [
                "git",
                "-c",
                f"core.excludesFile={global_excludes}",
                "-C",
                str(policy_root),
                "check-ignore",
                "--no-index",
                "-z",
                "--stdin",
            ],
            input=tracked,
            capture_output=True,
        )
    if ignored.returncode not in (0, 1):
        raise subprocess.CalledProcessError(
            ignored.returncode,
            ignored.args,
            output=ignored.stdout,
            stderr=ignored.stderr,
        )
    violations = sorted(
        path.decode("utf-8", errors="surrogateescape")
        for path in ignored.stdout.split(b"\0")
        if path
    )
    assert not violations, "Prohibited tracked paths: " + ", ".join(violations)


def test_private_workspace_paths_are_gitignored() -> None:
    ignore_file = ROOT / ".gitignore"
    assert ignore_file.exists()
    text = ignore_file.read_text(encoding="utf-8")
    required = {
        ".env",
        "data/",
        "runs/",
        "logs/",
        "tmp/",
        "paper_figures/",
        "baselines/",
        "docling_models/",
        "backups/",
        "*.docx",
        "node_modules/",
        "build/",
        "dist/",
        "*.egg-info/",
        "uv.lock",
        "*.tsbuildinfo",
        ".superpowers/",
        "/deploy/",
        "/tools/",
        "docs/simulated_evaluation/",
        "docs/benchmark_new_*",
        "docs/Research_Synthesis_Methods_投稿推荐说明.md",
        "docs/autometa_cost_list.md",
        "docs/autometa_evaluation_design.md",
        "docs/autometa_paper_document_for_main_figure.md",
        "docs/codex_optimization_log.md",
        "docs/ground_truth_literature_audit_20260722.md",
        "docs/对比基线实验数据汇总.md",
        "对比基线实验数据汇总.md",
        "docs/superpowers/plans/2026-09-01-autometa-paper-showcase.md",
        "docs/superpowers/specs/2026-09-01-autometa-paper-showcase-design.md",
    }
    assert required <= set(text.splitlines())


def test_public_metadata_files_exist() -> None:
    for relative in ("README.md", ".env.example", "LICENSE"):
        assert (ROOT / relative).is_file(), relative


def test_public_tree_policy_rejects_prohibited_tracked_content(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    (repository / ".gitignore").write_text(
        (ROOT / ".gitignore").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    prohibited = repository / "docs" / "benchmark_new_fixture.md"
    prohibited.parent.mkdir()
    prohibited.write_text("private benchmark\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repository), "add", ".gitignore"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repository), "add", "-f", prohibited.relative_to(repository)],
        check=True,
    )

    with pytest.raises(AssertionError, match="docs/benchmark_new_fixture.md"):
        assert_public_tree_policy(repository)


@pytest.mark.parametrize(
    "relative",
    (
        "nested/.env",
        "nested/.env.local",
        "nested/data/private.csv",
        "nested/runs/result.json",
        "nested/__pycache__/module.cpython-313.pyc",
        "nested/module.pyc",
        "nested/.pytest_cache/state",
        "nested/.ruff_cache/state",
        "nested/.coverage",
        "nested/htmlcov/index.html",
        "nested/.venv/pyvenv.cfg",
        "nested/venv/pyvenv.cfg",
        "nested/node_modules/package/index.js",
        "frontend/.vite/cache.json",
        "frontend/coverage/index.html",
        "nested/参考文献/研究.txt",
        pytest.param(
            "nested/data/研究\n结果.csv",
            marks=pytest.mark.skipif(
                os.name == "nt",
                reason=(
                    "Windows filenames cannot contain newlines; this case preserves "
                    "POSIX NUL-delimited filename coverage"
                ),
            ),
        ),
    ),
)
def test_public_tree_policy_rejects_nested_and_cache_content(
    tmp_path: Path,
    relative: str,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    (repository / ".gitignore").write_text(
        (ROOT / ".gitignore").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    prohibited = repository / relative
    prohibited.parent.mkdir(parents=True)
    prohibited.write_text("private\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repository), "add", ".gitignore"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repository), "add", "-f", relative],
        check=True,
    )

    with pytest.raises(AssertionError):
        assert_public_tree_policy(repository)


@pytest.mark.parametrize("exclude_source", ("info", "core.excludesFile"))
def test_public_tree_policy_ignores_external_exclude_sources(
    tmp_path: Path,
    exclude_source: str,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    (repository / ".gitignore").write_text(
        (ROOT / ".gitignore").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    public = repository / "public.txt"
    public.write_text("public\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repository), "add", ".gitignore", "public.txt"],
        check=True,
    )

    if exclude_source == "info":
        (repository / ".git" / "info" / "exclude").write_text(
            "public.txt\n",
            encoding="utf-8",
        )
    else:
        global_excludes = tmp_path / "global-excludes"
        global_excludes.write_text("public.txt\n", encoding="utf-8")
        subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "config",
                "core.excludesFile",
                str(global_excludes),
            ],
            check=True,
        )

    assert_public_tree_policy(repository)


def test_repository_satisfies_public_tree_policy() -> None:
    assert_public_tree_policy(ROOT)
