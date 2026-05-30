"""Post-process generated source: format and sort imports with ruff."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class PostProcessError(Exception):
    """Raised when an external formatter/checker fails."""


def _ruff() -> str:
    found = shutil.which("ruff")
    if found is None:
        raise PostProcessError("ruff executable not found on PATH")
    return found


def _run(args: list[str], source: str, *, filename: str) -> str:
    result = subprocess.run(
        [_ruff(), *args, "--stdin-filename", filename, "-"],
        input=source,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PostProcessError(
            f"ruff {' '.join(args)} failed for {filename}:\n{result.stderr or result.stdout}"
        )
    return result.stdout


def format_python(source: str, *, filename: str = "generated.py") -> str:
    """Sort imports, drop unused imports, then format the given source."""
    fixed = _run(
        ["check", "--select", "I,F401", "--fix", "--quiet"],
        source,
        filename=filename,
    )
    return _run(["format", "--quiet"], fixed, filename=filename)


def format_path(path: Path) -> None:
    """Run ruff import-sorting and formatting over files on disk (project-aware)."""
    target = str(path)
    fix = subprocess.run(
        [_ruff(), "check", "--select", "I,F401", "--fix", "--quiet", target],
        capture_output=True,
        text=True,
    )
    if fix.returncode not in (0, 1):  # 1 == remaining lint findings, acceptable here
        raise PostProcessError(f"ruff check failed for {target}:\n{fix.stderr or fix.stdout}")
    fmt = subprocess.run(
        [_ruff(), "format", "--quiet", target],
        capture_output=True,
        text=True,
    )
    if fmt.returncode != 0:
        raise PostProcessError(f"ruff format failed for {target}:\n{fmt.stderr or fmt.stdout}")
