"""Coverage for the ruff post-processing wrappers' error paths."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from unihttp_openapi_generator.postprocess import (
    PostProcessError,
    format_path,
    format_python,
)


class _Completed:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode
        self.stdout = "stdout"
        self.stderr = "stderr"


def test_ruff_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(PostProcessError, match="ruff executable not found"):
        format_python("x = 1\n")


def test_format_python_nonzero_returncode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/ruff")

    def fake_run(args: list[str], **kwargs: object) -> _Completed:
        return _Completed(1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(PostProcessError, match="ruff check"):
        format_python("x = 1\n")


def test_format_path_check_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/ruff")

    def fake_run(args: list[str], **kwargs: object) -> _Completed:
        # returncode 2 from ``ruff check`` is neither clean (0) nor lint-only (1)
        return _Completed(2 if "check" in args else 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(PostProcessError, match="ruff check failed"):
        format_path(tmp_path / "f.py")


def test_format_path_format_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/ruff")

    def fake_run(args: list[str], **kwargs: object) -> _Completed:
        # check passes (1 == remaining lint findings, tolerated); format then fails
        return _Completed(1 if "check" in args else 3)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(PostProcessError, match="ruff format failed"):
        format_path(tmp_path / "f.py")
