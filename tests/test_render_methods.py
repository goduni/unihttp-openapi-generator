"""Tests for method (BaseMethod) rendering."""

from __future__ import annotations

import dataclasses
import importlib
import sys
from pathlib import Path
from typing import Any

from unihttp.method import BaseMethod
from unihttp.omitted import Omitted

from unihttp_openapi_generator.config import Serializer
from unihttp_openapi_generator.ir.builder import build_ir
from unihttp_openapi_generator.postprocess import format_python
from unihttp_openapi_generator.refs import RefResolver
from unihttp_openapi_generator.render.methods import render_methods_module
from unihttp_openapi_generator.render.models import render_models_module
from unihttp_openapi_generator.render.serializers import get_strategy


def _build_package(spec: dict[str, Any], tmp_path: Path, package: str) -> None:
    ir = build_ir(spec, RefResolver(spec))
    strategy = get_strategy(Serializer.ADAPTIX)
    root = tmp_path / package
    (root / "methods").mkdir(parents=True)
    (root / "__init__.py").write_text("")
    (root / "models.py").write_text(
        format_python(render_models_module(ir, strategy), filename="models.py")
    )
    (root / "methods" / "__init__.py").write_text("")
    for tag in ir.tags:
        module = render_methods_module(ir, tag, package)
        (root / "methods" / f"{tag}.py").write_text(format_python(module, filename=f"{tag}.py"))


def test_methods_module_imports(sample_spec: dict[str, Any], tmp_path: Path) -> None:
    package = "genmethods_pkg"
    _build_package(sample_spec, tmp_path, package)
    sys.path.insert(0, str(tmp_path))
    try:
        pets = importlib.import_module(f"{package}.methods.pets")
        list_pets: Any = pets.ListPets
        assert issubclass(list_pets, BaseMethod)
        assert dataclasses.is_dataclass(pets.ListPets)
        # the server's "/v1" path prefix is folded into the operation url
        assert list_pets.__url__ == "/v1/pets"
        assert list_pets.__method__ == "GET"

        # required header has no default; optional query params default to Omitted()
        instance = list_pets(x_request_id="abc")
        assert isinstance(instance.limit, Omitted)
        assert instance.x_request_id == "abc"

        create_pet: Any = pets.CreatePet
        assert create_pet.__method__ == "POST"

        # multipart file field present
        upload: Any = pets.UploadPhoto
        field_names = {f.name for f in dataclasses.fields(upload)}
        assert {"pet_id", "file", "caption"} <= field_names
    finally:
        sys.path.remove(str(tmp_path))
        for name in list(sys.modules):
            if name.startswith(package):
                del sys.modules[name]


def _render_method(spec: dict[str, Any], method_name: str) -> str:
    from unihttp_openapi_generator.render.methods import render_method_class

    ir = build_ir(spec, RefResolver(spec))
    op = next(o for o in ir.operations if o.method_name == method_name)
    code, _ = render_method_class(op)
    return code


def test_param_default_rendered_without_omittable() -> None:
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {
            "/x": {
                "get": {
                    "operationId": "getX",
                    "tags": ["x"],
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "schema": {"type": "integer", "default": 10},
                        },
                        {
                            "name": "flag",
                            "in": "query",
                            "schema": {"type": "boolean", "default": False},
                        },
                        {"name": "plain", "in": "query", "schema": {"type": "integer"}},
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    code = _render_method(spec, "get_x")
    assert "limit: Query[int] = 10" in code
    assert "flag: Query[bool] = False" in code
    # optional-without-default keeps the Omittable + Omitted() form
    assert "plain: Query[Omittable[int]] = Omitted()" in code


def test_method_docstring_paragraphs() -> None:
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {
            "/x": {
                "get": {
                    "operationId": "getX",
                    "tags": ["x"],
                    "summary": "Short summary.",
                    "description": (
                        "A much longer description paragraph that explains the operation."
                    ),
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    code = _render_method(spec, "get_x")
    assert '"""Short summary.' in code
    # summary and description separated by a blank line
    assert "Short summary.\n\n" in code
    assert "longer description" in code


def test_blank_line_between_dunders_and_params(sample_spec: dict[str, Any]) -> None:
    ir = build_ir(sample_spec, RefResolver(sample_spec))
    source = format_python(render_methods_module(ir, "pets", "acme"), filename="pets.py")
    # methods with parameters get a blank line after __method__
    assert '__method__ = "GET"\n\n    x_request_id' in source


def test_body_field_and_param_descriptions_become_attribute_docstrings() -> None:
    """Schema prose on a parameter / spread body field has to land somewhere.

    ``IRBodyField.description`` and ``IRParameter.description`` are only worth carrying
    if they reach the generated package; a PEP 258 attribute docstring is the one place
    they fit without touching the constructor signature.
    """
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {
            "/d": {
                "post": {
                    "operationId": "createDoc",
                    "tags": ["d"],
                    "parameters": [
                        {
                            "name": "dry_run",
                            "in": "query",
                            "schema": {"type": "boolean"},
                            "description": "Validate without persisting.",
                        }
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["title"],
                                    "properties": {
                                        "title": {
                                            "type": "string",
                                            "description": "Document title.",
                                        },
                                        "body": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"204": {"description": "no content"}},
                }
            }
        },
    }
    ir = build_ir(spec, RefResolver(spec))
    source = format_python(render_methods_module(ir, "d", "pkg"), filename="d.py")
    assert '"""Document title."""' in source
    assert '"""Validate without persisting."""' in source
    # a field without prose gets no stray docstring
    assert source.count('"""') == 2 * 3  # module docstring + the two attribute ones
