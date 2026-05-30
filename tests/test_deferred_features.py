"""Tests for the four deferred features: --check, --style imperative,
pydantic Field(discriminator=...), and deepObject query expansion."""

from __future__ import annotations

import importlib
import inspect
import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from unihttp_openapi_generator.config import (
    ClientKind,
    GeneratorConfig,
    MethodStyle,
    Serializer,
)
from unihttp_openapi_generator.pipeline import CheckError, run_generation


@contextmanager
def _on_path(root: Path, package: str) -> Iterator[None]:
    sys.path.insert(0, str(root))
    try:
        yield
    finally:
        sys.path.remove(str(root))
        for mod in list(sys.modules):
            if mod == package or mod.startswith(f"{package}."):
                del sys.modules[mod]


def _write(spec: dict[str, Any], tmp_path: Path) -> Path:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec))
    return path


# --------------------------------------------------------------------------- #
# 1. --check                                                                  #
# --------------------------------------------------------------------------- #


def test_check_succeeds_on_sample(sample_spec: dict[str, Any], tmp_path: Path) -> None:
    spec = _write(sample_spec, tmp_path)
    out = tmp_path / "out"
    # Should not raise: the generated package is ruff + mypy --strict clean.
    run_generation(
        str(spec),
        GeneratorConfig(
            package_name="check_ok", output_dir=out, client=ClientKind.SYNC, check=True
        ),
    )


def test_check_surfaces_broken_output(
    sample_spec: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Deliberately corrupt the written package so the post-generation check fails.
    import unihttp_openapi_generator.pipeline as pipeline
    from unihttp_openapi_generator.emit import write_package

    def broken_write(doc: Any, config: Any) -> Path:
        root = write_package(doc, config)
        (root / config.package_name / "models.py").write_text("def : broken(\n")
        return root

    monkeypatch.setattr(pipeline, "write_package", broken_write)
    spec = _write(sample_spec, tmp_path)
    with pytest.raises(CheckError):
        run_generation(
            str(spec),
            GeneratorConfig(
                package_name="check_bad",
                output_dir=tmp_path / "bad",
                client=ClientKind.SYNC,
                check=True,
            ),
        )


# --------------------------------------------------------------------------- #
# 2. --style imperative                                                       #
# --------------------------------------------------------------------------- #


def test_imperative_flat_signature_and_call(sample_spec: dict[str, Any], tmp_path: Path) -> None:
    spec = _write(sample_spec, tmp_path)
    out = tmp_path / "out"
    package = "imp_flat_pkg"
    run_generation(
        str(spec),
        GeneratorConfig(
            package_name=package,
            output_dir=out,
            client=ClientKind.SYNC,
            style=MethodStyle.IMPERATIVE,
            check=True,  # ruff + mypy --strict must pass
        ),
    )
    with _on_path(out, package):
        client_mod = importlib.import_module(f"{package}.client")
        methods = importlib.import_module(f"{package}.methods.pets")
        cls = client_mod.SampleClient
        sig = inspect.signature(cls.list_pets)
        params = sig.parameters
        # Mirrors the dataclass fields: typed, keyword-only.
        assert params["x_request_id"].annotation == "str"
        assert params["x_request_id"].kind is inspect.Parameter.KEYWORD_ONLY
        assert "limit" in params and "tags" in params

        # Calling the method constructs the right BaseMethod.
        instance = cls.__new__(cls)
        captured: dict[str, Any] = {}

        def fake_call_method(method: Any) -> None:
            captured["method"] = method

        instance.call_method = fake_call_method
        cls.list_pets(instance, x_request_id="r1", limit=5)
        built = captured["method"]
        assert isinstance(built, methods.ListPets)
        assert built.x_request_id == "r1"
        assert built.limit == 5


def test_imperative_async_uses_await(sample_spec: dict[str, Any], tmp_path: Path) -> None:
    spec = _write(sample_spec, tmp_path)
    out = tmp_path / "out"
    package = "imp_async_pkg"
    run_generation(
        str(spec),
        GeneratorConfig(
            package_name=package,
            output_dir=out,
            client=ClientKind.ASYNC,
            style=MethodStyle.IMPERATIVE,
        ),
    )
    source = (out / package / "client.py").read_text()
    assert "async def list_pets(" in source
    assert "return await self.call_method(" in source


# --------------------------------------------------------------------------- #
# 3. pydantic Field(discriminator=...)                                        #
# --------------------------------------------------------------------------- #

_DISC_SPEC: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "Zoo", "version": "1.0.0"},
    "paths": {
        "/animals": {
            "get": {
                "operationId": "listAnimals",
                "responses": {
                    "200": {
                        "description": "ok",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Animal"},
                                }
                            }
                        },
                    }
                },
            }
        }
    },
    "components": {
        "schemas": {
            "Cat": {
                "type": "object",
                "required": ["kind", "meow"],
                "properties": {"kind": {"const": "cat"}, "meow": {"type": "boolean"}},
            },
            "Dog": {
                "type": "object",
                "required": ["kind", "bark"],
                "properties": {"kind": {"const": "dog"}, "bark": {"type": "boolean"}},
            },
            "Animal": {
                "oneOf": [
                    {"$ref": "#/components/schemas/Cat"},
                    {"$ref": "#/components/schemas/Dog"},
                ],
                "discriminator": {
                    "propertyName": "kind",
                    "mapping": {
                        "cat": "#/components/schemas/Cat",
                        "dog": "#/components/schemas/Dog",
                    },
                },
            },
            # A plain (non-discriminable) union -> fallback path.
            "Shape": {"oneOf": [{"type": "string"}, {"type": "integer"}]},
        }
    },
}


def test_pydantic_discriminated_union(tmp_path: Path) -> None:
    spec = _write(_DISC_SPEC, tmp_path)
    out = tmp_path / "out"
    package = "disc_pkg"
    run_generation(
        str(spec),
        GeneratorConfig(
            package_name=package,
            output_dir=out,
            serializer=Serializer.PYDANTIC,
            client=ClientKind.SYNC,
            check=True,
        ),
    )
    source = (out / package / "models.py").read_text()
    assert 'type Animal = Annotated[Cat | Dog, Field(discriminator="kind")]' in source
    # Fallback: a non-discriminable union stays a plain alias.
    assert "type Shape = str | int" in source

    with _on_path(out, package):
        from pydantic import TypeAdapter  # noqa: PLC0415

        models = importlib.import_module(f"{package}.models")
        ta = TypeAdapter(models.Animal)
        dog = ta.validate_python({"kind": "dog", "bark": True})
        assert type(dog).__name__ == "Dog"
        cat = ta.validate_python({"kind": "cat", "meow": False})
        assert type(cat).__name__ == "Cat"


def test_pydantic_non_discriminable_falls_back(sample_spec: dict[str, Any], tmp_path: Path) -> None:
    # Sample's ``Animal`` oneOf references Pet/NewPet, neither of which has a
    # single-value Literal ``kind`` field -> must NOT emit Field(discriminator=).
    spec = _write(sample_spec, tmp_path)
    out = tmp_path / "out"
    package = "fallback_pkg"
    run_generation(
        str(spec),
        GeneratorConfig(
            package_name=package,
            output_dir=out,
            serializer=Serializer.PYDANTIC,
            client=ClientKind.SYNC,
        ),
    )
    source = (out / package / "models.py").read_text()
    assert "type Animal = Pet | NewPet" in source
    assert "Field(discriminator=" not in source


# --------------------------------------------------------------------------- #
# 4. deepObject query expansion                                               #
# --------------------------------------------------------------------------- #

_DEEP_SPEC: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "Search", "version": "1.0.0"},
    "servers": [{"url": "https://api.example.com"}],
    "paths": {
        "/items": {
            "get": {
                "operationId": "searchItems",
                "parameters": [
                    {
                        "name": "filter",
                        "in": "query",
                        "style": "deepObject",
                        "explode": True,
                        "schema": {"$ref": "#/components/schemas/Filter"},
                    },
                    {"name": "q", "in": "query", "schema": {"type": "string"}},
                ],
                "responses": {
                    "200": {
                        "description": "ok",
                        "content": {
                            "application/json": {
                                "schema": {"type": "array", "items": {"type": "string"}}
                            }
                        },
                    }
                },
            }
        }
    },
    "components": {
        "schemas": {
            "Filter": {
                "type": "object",
                "properties": {"a": {"type": "integer"}, "b": {"type": "string"}},
            }
        }
    },
}


def test_deep_object_query_expansion(tmp_path: Path) -> None:
    spec = _write(_DEEP_SPEC, tmp_path)
    out = tmp_path / "out"
    package = "deep_pkg"
    run_generation(
        str(spec),
        GeneratorConfig(
            package_name=package,
            output_dir=out,
            serializer=Serializer.ADAPTIX,
            client=ClientKind.SYNC,
            check=True,
        ),
    )
    # The expansion module is generated and installed in the client.
    assert (out / package / "_query.py").exists()
    client_source = (out / package / "client.py").read_text()
    assert 'DeepObjectQuerySyncMiddleware(frozenset({"filter"}))' in client_source

    with _on_path(out, package):
        serialization = importlib.import_module(f"{package}._serialization")
        methods = importlib.import_module(f"{package}.methods.default")
        models = importlib.import_module(f"{package}.models")
        query = importlib.import_module(f"{package}._query")

        method = methods.SearchItems(filter=models.Filter(a=1, b="hi"), q="x")
        request = method.build_http_request(request_dumper=serialization.request_dumper)
        # Before expansion the object lives under a single nested key.
        assert request.query["filter"] == {"a": 1, "b": "hi"}

        captured: dict[str, Any] = {}

        def next_handler(req: Any) -> Any:
            captured["query"] = dict(req.query)
            return object()

        mw = query.DeepObjectQuerySyncMiddleware(frozenset({"filter"}))
        mw.handle(request, next_handler)
        assert captured["query"] == {"q": "x", "filter[a]": 1, "filter[b]": "hi"}


def test_no_query_module_without_deep_object(sample_spec: dict[str, Any], tmp_path: Path) -> None:
    spec = _write(sample_spec, tmp_path)
    out = tmp_path / "out"
    package = "nodeep_pkg"
    run_generation(
        str(spec),
        GeneratorConfig(package_name=package, output_dir=out, client=ClientKind.SYNC),
    )
    assert not (out / package / "_query.py").exists()
