"""Tests for TOML config-file resolution and CLI integration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from unihttp_openapi_generator.cli import app
from unihttp_openapi_generator.config_file import (
    ConfigFileError,
    load_file_settings,
    merge_settings,
)

runner = CliRunner()


def _write(path: Path, text: str) -> Path:
    path.write_text(text)
    return path


def test_load_namespaced_pyproject(tmp_path: Path) -> None:
    _write(
        tmp_path / "pyproject.toml",
        '[tool.unihttp-openapi-generator]\npackage_name = "p"\nserializer = "pydantic"\n',
    )
    settings = load_file_settings(None, tmp_path)
    assert settings == {"package_name": "p", "serializer": "pydantic"}


def test_load_standalone_toplevel(tmp_path: Path) -> None:
    cfg = _write(tmp_path / "c.toml", 'package_name = "p"\nclient = "sync"\n')
    assert load_file_settings(cfg, tmp_path) == {"package_name": "p", "client": "sync"}


def test_autodiscover_dedicated_file(tmp_path: Path) -> None:
    _write(tmp_path / "unihttp-openapi-generator.toml", 'layout = "flat"\n')
    assert load_file_settings(None, tmp_path) == {"layout": "flat"}


def test_missing_explicit_config_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigFileError):
        load_file_settings(tmp_path / "nope.toml", tmp_path)


def test_cli_overrides_file(tmp_path: Path) -> None:
    cfg = _write(
        tmp_path / "c.toml",
        'spec = "s.yaml"\noutput_dir = "out"\npackage_name = "fromfile"\nserializer = "pydantic"\n',
    )
    merged = merge_settings({"serializer": "adaptix", "spec": None}, cfg, tmp_path)
    assert merged["serializer"] == "adaptix"  # CLI wins
    assert merged["package_name"] == "fromfile"  # file used


def test_unknown_key_raises(tmp_path: Path) -> None:
    cfg = _write(tmp_path / "c.toml", 'spec="s"\noutput_dir="o"\npackage_name="p"\nbogus=1\n')
    with pytest.raises(ConfigFileError, match="unknown config key"):
        merge_settings({}, cfg, tmp_path)


def test_missing_required_raises(tmp_path: Path) -> None:
    cfg = _write(tmp_path / "c.toml", 'serializer = "adaptix"\n')
    with pytest.raises(ConfigFileError, match="missing required"):
        merge_settings({}, cfg, tmp_path)


@pytest.fixture
def spec_path(sample_spec: dict[str, Any], tmp_path: Path) -> Path:
    return _write(tmp_path / "spec.json", json.dumps(sample_spec))


def test_cli_generates_from_config_file(spec_path: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    cfg = _write(
        tmp_path / "gen.toml",
        f'spec = "{spec_path}"\noutput_dir = "{out}"\n'
        'package_name = "cfg_client"\nserializer = "pydantic"\nclient = "sync"\n',
    )
    result = runner.invoke(app, ["generate", "--config", str(cfg)])
    assert result.exit_code == 0, result.output
    assert (out / "cfg_client" / "client.py").is_file()
    # serializer from the file was honored -> pydantic BaseModel models
    assert "BaseModel" in (out / "cfg_client" / "models.py").read_text()


def test_cli_flag_overrides_config_file(spec_path: Path, tmp_path: Path) -> None:
    out = tmp_path / "out2"
    cfg = _write(
        tmp_path / "gen.toml",
        f'spec = "{spec_path}"\noutput_dir = "{out}"\n'
        'package_name = "cfg_client2"\nserializer = "pydantic"\n',
    )
    result = runner.invoke(app, ["generate", "--config", str(cfg), "--serializer", "adaptix"])
    assert result.exit_code == 0, result.output
    # adaptix wins -> dataclass models, not BaseModel
    models = (out / "cfg_client2" / "models.py").read_text()
    assert "@dataclass" in models and "BaseModel" not in models


def test_cli_missing_required_errors(tmp_path: Path) -> None:
    result = runner.invoke(app, ["generate", "--serializer", "adaptix"])
    assert result.exit_code != 0
