"""Post-process generated source: format and sort imports with ruff."""

from __future__ import annotations

import subprocess
from pathlib import Path

from unihttp_openapi_generator.tooling import ruff_executable


class PostProcessError(Exception):
    """Raised when an external formatter/checker fails."""


def _run(args: list[str], source: str, *, filename: str) -> str:
    result = subprocess.run(
        [ruff_executable(), *args, "--stdin-filename", filename, "-"],
        input=source,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PostProcessError(
            f"ruff {' '.join(args)} failed for {filename}:\n{result.stderr or result.stdout}"
        )
    return result.stdout


def config_args(config_path: Path | None) -> list[str]:
    """Point ruff at the emitted package's own config, or at nothing at all.

    Never the ambient one. Whatever ruff discovers from the working directory belongs to
    whoever happens to be running the generator, and letting it through made the same
    spec produce different bytes depending on where it was generated -- wrapped at the
    caller's ``line-length`` rather than the package's own.
    """
    return ["--config", str(config_path)] if config_path is not None else ["--isolated"]


def format_python(
    source: str, *, filename: str = "generated.py", config_path: Path | None = None
) -> str:
    """Sort imports, drop unused imports, then format the given source."""
    args = config_args(config_path)
    fixed = _run(
        ["check", *args, "--select", "I,F401", "--fix", "--quiet"],
        source,
        filename=filename,
    )
    return _run(["format", *args, "--quiet"], fixed, filename=filename)


def format_path(path: Path, config_path: Path | None = None) -> None:
    """Run ruff import-sorting and formatting over files on disk."""
    target = str(path)
    args = config_args(config_path)
    fix = subprocess.run(
        [ruff_executable(), "check", *args, "--select", "I,F401", "--fix", "--quiet", target],
        capture_output=True,
        text=True,
    )
    if fix.returncode not in (0, 1):  # 1 == remaining lint findings, acceptable here
        raise PostProcessError(f"ruff check failed for {target}:\n{fix.stderr or fix.stdout}")
    fmt = subprocess.run(
        [ruff_executable(), "format", *args, "--quiet", target],
        capture_output=True,
        text=True,
    )
    if fmt.returncode != 0:
        raise PostProcessError(f"ruff format failed for {target}:\n{fmt.stderr or fmt.stdout}")
