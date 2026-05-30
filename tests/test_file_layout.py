"""Tests for the per-object file layout (``--file-layout per-object``)."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from unihttp_openapi_generator.config import FileLayout, GeneratorConfig, Serializer
from unihttp_openapi_generator.pipeline import run_generation

_SERIALIZERS = [Serializer.ADAPTIX, Serializer.PYDANTIC, Serializer.MSGSPEC]


def _cyclic_spec() -> dict[str, Any]:
    """A spec with two mutually-referential models (A has B, B has A)."""
    return {
        "openapi": "3.1.0",
        "info": {"title": "Cyclic", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/a": {
                "get": {
                    "operationId": "getA",
                    "tags": ["nodes"],
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {"schema": {"$ref": "#/components/schemas/A"}}
                            },
                        }
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "A": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {
                        "id": {"type": "integer"},
                        "b": {"$ref": "#/components/schemas/B"},
                    },
                },
                "B": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {
                        "id": {"type": "integer"},
                        "a": {"$ref": "#/components/schemas/A"},
                    },
                },
            }
        },
    }


def _write_spec(spec: dict[str, Any], tmp_path: Path) -> Path:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec))
    return path


def _import_clean(name: str) -> Any:
    for mod in list(sys.modules):
        if mod == name or mod.startswith(f"{name}."):
            del sys.modules[mod]
    return importlib.import_module(name)


def _drop(name: str) -> None:
    for mod in list(sys.modules):
        if mod == name or mod.startswith(f"{name}."):
            del sys.modules[mod]


def test_per_object_emits_one_file_per_declaration_and_method(
    sample_spec: dict[str, Any], tmp_path: Path
) -> None:
    spec_file = _write_spec(sample_spec, tmp_path)
    out = tmp_path / "out"
    config = GeneratorConfig(
        package_name="splitpkg",
        output_dir=out,
        serializer=Serializer.ADAPTIX,
        file_layout=FileLayout.PER_OBJECT,
    )
    run_generation(str(spec_file), config)
    pkg = out / "splitpkg"

    # One module per declaration (Pet/NewPet/PetKind/Animal/Metadata/Error).
    assert (pkg / "models" / "pet.py").is_file()
    assert (pkg / "models" / "new_pet.py").is_file()
    assert (pkg / "models" / "pet_kind.py").is_file()  # enum
    assert (pkg / "models" / "animal.py").is_file()  # alias (discriminated union)
    assert (pkg / "models" / "error.py").is_file()
    assert (pkg / "models" / "metadata.py").is_file()
    # No monolithic models.py in per-object mode.
    assert not (pkg / "models.py").exists()

    # One module per request method, grouped under methods/<tag>/.
    assert (pkg / "methods" / "pets" / "list_pets.py").is_file()
    assert (pkg / "methods" / "pets" / "create_pet.py").is_file()
    assert (pkg / "methods" / "pets" / "upload_photo.py").is_file()
    assert (pkg / "methods" / "pets" / "__init__.py").is_file()

    # _forward_refs.py exists and _serialization.py calls it.
    assert (pkg / "_forward_refs.py").is_file()
    assert "resolve_forward_refs()" in (pkg / "_serialization.py").read_text()

    # models/__init__ re-exports every declaration.
    models_init = (pkg / "models" / "__init__.py").read_text()
    for name in ("Pet", "NewPet", "PetKind", "Animal", "Error", "Metadata"):
        assert f"import {name}" in models_init
        assert name in models_init
    assert "__all__" in models_init

    # methods/__init__ re-exports every method (so `from pkg.methods import X` works).
    methods_init = (pkg / "methods" / "__init__.py").read_text()
    for name in ("ListPets", "CreatePet", "UploadPhoto"):
        assert name in methods_init


def test_single_layout_is_default_and_unchanged(
    sample_spec: dict[str, Any], tmp_path: Path
) -> None:
    spec_file = _write_spec(sample_spec, tmp_path)
    out = tmp_path / "out"
    config = GeneratorConfig(package_name="flatpkg", output_dir=out)
    assert config.file_layout is FileLayout.SINGLE
    run_generation(str(spec_file), config)
    pkg = out / "flatpkg"
    # Single layout: monolithic models.py + methods/<tag>.py, no split dirs.
    assert (pkg / "models.py").is_file()
    assert (pkg / "methods" / "pets.py").is_file()
    assert not (pkg / "models").exists()
    assert not (pkg / "_forward_refs.py").exists()


@pytest.mark.parametrize("serializer", _SERIALIZERS)
def test_cyclic_models_round_trip_per_object(serializer: Serializer, tmp_path: Path) -> None:
    """Cyclic A<->B in separate modules: no circular import, forward refs resolve."""
    spec_file = _write_spec(_cyclic_spec(), tmp_path)
    out = tmp_path / f"out_{serializer.value}"
    package = f"cyclic_{serializer.value}"
    config = GeneratorConfig(
        package_name=package,
        output_dir=out,
        serializer=serializer,
        file_layout=FileLayout.PER_OBJECT,
    )
    run_generation(str(spec_file), config)

    # A and B live in distinct modules.
    assert (out / package / "models" / "a.py").is_file()
    assert (out / package / "models" / "b.py").is_file()

    sys.path.insert(0, str(out))
    try:
        # Importing the package must not deadlock on the A<->B cycle.
        _import_clean(package)
        models = importlib.import_module(f"{package}.models")
        serialization = importlib.import_module(f"{package}._serialization")
        payload = {"id": 1, "b": {"id": 2, "a": {"id": 3}}}
        a = serialization.response_loader.load(payload, models.A)
        # Forward refs resolved across modules: nested B and A materialized.
        assert a.id == 1
        assert a.b.id == 2
        assert a.b.a.id == 3
    finally:
        sys.path.remove(str(out))
        _drop(package)
