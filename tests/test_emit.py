"""End-to-end emit tests: generate a package and import the client."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from unihttp_openapi_generator.config import ClientKind, GeneratorConfig, Serializer
from unihttp_openapi_generator.pipeline import run_generation
from unihttp_openapi_generator.tooling import ruff_executable


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


def test_no_stub_is_written_by_default(spec_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out_nostub"
    run_generation(
        str(spec_file),
        GeneratorConfig(package_name="nostub_client", output_dir=out),
    )
    assert not (out / "nostub_client" / "client.pyi").exists()


def test_stubs_writes_a_formatted_client_pyi(spec_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out_stub"
    run_generation(
        str(spec_file),
        GeneratorConfig(package_name="stub_client", output_dir=out, stubs=True),
    )
    stub = out / "stub_client" / "client.pyi"
    assert stub.is_file()
    source = stub.read_text()
    # The runtime module is untouched and still binds declaratively...
    assert "bind_method" in (out / "stub_client" / "client.py").read_text()
    # ...while the stub spells the same operations out.
    assert "def list_pets(" in source
    assert "bind_method" not in source
    # Module-level names are declared without values, and ruff's stub-mode formatting
    # keeps the empty ``__init__`` body as ``...``.
    assert "DEFAULT_BASE_URL: str\n" in source
    assert "base_url: str = DEFAULT_BASE_URL," in source
    assert ") -> None: ..." in source


def test_generated_stub_is_ruff_clean(spec_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out_stub_lint"
    run_generation(
        str(spec_file),
        GeneratorConfig(package_name="lint_client", output_dir=out, stubs=True),
    )
    result = subprocess.run(
        [ruff_executable(), "check", "--isolated", str(out / "lint_client" / "client.pyi")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_regenerating_without_stubs_removes_a_stale_one(spec_file: Path, tmp_path: Path) -> None:
    # Generation writes over an existing package rather than clearing it, and a stub
    # keeps overriding client.py for every type checker and IDE that reads it. Left
    # behind, it would serve the previous run's signatures forever -- worse than no
    # stub at all once the spec has moved on.
    out = tmp_path / "out_stale"
    stub = out / "stale_client" / "client.pyi"

    run_generation(
        str(spec_file),
        GeneratorConfig(package_name="stale_client", output_dir=out, stubs=True),
    )
    assert stub.is_file()

    run_generation(
        str(spec_file),
        GeneratorConfig(package_name="stale_client", output_dir=out, stubs=False),
    )
    assert not stub.exists()
