"""Coverage for the pipeline check helper and CLI error/version paths."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from unihttp_openapi_generator import __version__
from unihttp_openapi_generator.cli import app
from unihttp_openapi_generator.pipeline import CheckError, _run_check

runner = CliRunner()


def test_run_check_tool_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(CheckError, match="not found on PATH"):
        _run_check("ruff", ["check"], Path("/nonexistent"))


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_invalid_package_name_is_bad_parameter(tmp_path: Path) -> None:
    # ``merge_settings`` succeeds (all required keys present) but ``GeneratorConfig``
    # rejects the package name -> the CLI turns the ValueError into a BadParameter.
    result = runner.invoke(
        app,
        ["generate", "spec.yaml", "-o", str(tmp_path), "--package-name", "not an identifier"],
    )
    assert result.exit_code != 0
    # the pydantic ValidationError (a ValueError) is surfaced as a BadParameter
    assert "Invalid value" in result.output
    assert "GeneratorConfig" in result.output
