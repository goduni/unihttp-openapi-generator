"""Coverage for config validation and config-file edge paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from unihttp_openapi_generator.config import GeneratorConfig, OptionalStyle, Serializer
from unihttp_openapi_generator.config_file import ConfigFileError, load_file_settings


def test_omitted_optional_requires_adaptix() -> None:
    with pytest.raises(ValueError, match="adaptix"):
        GeneratorConfig(
            package_name="pkg",
            output_dir=Path("out"),
            optional=OptionalStyle.OMITTED,
            serializer=Serializer.PYDANTIC,
        )


def test_malformed_toml_raises(tmp_path: Path) -> None:
    cfg = tmp_path / "c.toml"
    cfg.write_text("this is = = not valid toml\n")
    with pytest.raises(ConfigFileError, match="failed to read config"):
        load_file_settings(cfg, tmp_path)


def test_no_config_anywhere_returns_empty(tmp_path: Path) -> None:
    # An empty directory: no explicit file, no auto file, no pyproject.toml.
    assert load_file_settings(None, tmp_path) == {}
