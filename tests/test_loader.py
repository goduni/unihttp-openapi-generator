"""Tests for the spec loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from unihttp_openapi_generator.loader import SpecLoadError, load_spec

_MINIMAL = {
    "openapi": "3.1.0",
    "info": {"title": "T", "version": "1.0.0"},
    "paths": {},
}


def test_loads_yaml(tmp_path: Path) -> None:
    p = tmp_path / "spec.yaml"
    p.write_text("openapi: 3.1.0\ninfo:\n  title: T\n  version: '1.0.0'\npaths: {}\n")
    spec = load_spec(str(p))
    assert spec["openapi"] == "3.1.0"


def test_loads_json(tmp_path: Path) -> None:
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(_MINIMAL))
    spec = load_spec(str(p))
    assert spec["info"]["title"] == "T"


def test_missing_file_raises() -> None:
    with pytest.raises(SpecLoadError):
        load_spec("/no/such/file.yaml")


def test_non_mapping_root_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("- just\n- a\n- list\n")
    with pytest.raises(SpecLoadError):
        load_spec(str(p))


def test_strict_validation_rejects_invalid(tmp_path: Path) -> None:
    p = tmp_path / "invalid.json"
    p.write_text(json.dumps({"openapi": "3.1.0"}))  # missing info/paths
    with pytest.raises(SpecLoadError):
        load_spec(str(p), strict=True)


def test_soft_validation_passes_invalid(tmp_path: Path) -> None:
    p = tmp_path / "invalid.json"
    p.write_text(json.dumps({"openapi": "3.1.0"}))
    spec = load_spec(str(p), strict=False)  # default: warn, do not raise
    assert spec["openapi"] == "3.1.0"
