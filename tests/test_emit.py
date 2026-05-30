"""End-to-end emit tests: generate a package and import the client."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from unihttp_openapi_generator.config import ClientKind, GeneratorConfig, Serializer
from unihttp_openapi_generator.pipeline import run_generation


@pytest.fixture
def spec_file(sample_spec: dict[str, Any], tmp_path: Path) -> Path:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(sample_spec))
    return path


def _import_clean(name: str) -> Any:
    for mod in list(sys.modules):
        if mod == name or mod.startswith(f"{name}."):
            del sys.modules[mod]
    return importlib.import_module(name)


@pytest.mark.parametrize(
    "serializer", [Serializer.ADAPTIX, Serializer.PYDANTIC, Serializer.MSGSPEC]
)
def test_generated_package_imports_and_instantiates(
    spec_file: Path, tmp_path: Path, serializer: Serializer
) -> None:
    out = tmp_path / f"out_{serializer.value}"
    package = f"acme_{serializer.value}"
    config = GeneratorConfig(
        package_name=package,
        output_dir=out,
        serializer=serializer,
        client=ClientKind.BOTH,
    )
    run_generation(str(spec_file), config)

    assert (out / "pyproject.toml").exists()
    assert (out / package / "py.typed").exists()

    sys.path.insert(0, str(out))
    try:
        pkg = _import_clean(package)
        client_cls = pkg.SampleClient
        client = client_cls()  # default base_url, default backend, no request made
        # single-tag spec -> AUTO layout collapses to a flat client
        assert callable(client.list_pets)
        assert callable(client.create_pet)
        assert hasattr(pkg, "AsyncSampleClient")
    finally:
        sys.path.remove(str(out))
        for mod in list(sys.modules):
            if mod == package or mod.startswith(f"{package}."):
                del sys.modules[mod]


def test_pyproject_pins_unihttp_floor(spec_file: Path, tmp_path: Path) -> None:
    # The msgspec serializer requires unihttp >= 0.2.9, so the generated floor
    # must be at least that (an open lower bound still tracks newer releases).
    out = tmp_path / "out_pin"
    config = GeneratorConfig(
        package_name="acme_pin",
        output_dir=out,
        serializer=Serializer.MSGSPEC,
        client=ClientKind.BOTH,
    )
    run_generation(str(spec_file), config)
    pyproject = (out / "pyproject.toml").read_text()
    assert '"unihttp>=0.2.9"' in pyproject, pyproject
