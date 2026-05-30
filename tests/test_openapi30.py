"""OpenAPI 3.0 support: nullable keyword, boolean exclusive bounds, end-to-end."""

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from unihttp_openapi_generator.config import ClientKind, GeneratorConfig, Serializer
from unihttp_openapi_generator.ir.builder import build_ir
from unihttp_openapi_generator.ir.models import IRModel
from unihttp_openapi_generator.ir.types import OptionalType
from unihttp_openapi_generator.pipeline import run_generation
from unihttp_openapi_generator.postprocess import format_python
from unihttp_openapi_generator.refs import RefResolver
from unihttp_openapi_generator.render.models import render_models_module
from unihttp_openapi_generator.render.serializers import get_strategy

_SPEC_30: dict[str, Any] = {
    "openapi": "3.0.3",
    "info": {"title": "Legacy", "version": "1.0.0"},
    "paths": {
        "/widgets/{id}": {
            "get": {
                "operationId": "getWidget",
                "tags": ["widgets"],
                "parameters": [
                    {"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}
                ],
                "responses": {
                    "200": {
                        "description": "ok",
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Widget"}}
                        },
                    }
                },
            }
        }
    },
    "components": {
        "schemas": {
            "Widget": {
                "type": "object",
                "required": ["id", "score", "code"],
                "properties": {
                    "id": {"type": "integer"},
                    "score": {"type": "integer", "minimum": 1, "exclusiveMinimum": True},
                    "code": {"type": "string", "nullable": True},  # required AND nullable
                    "label": {"type": "string", "nullable": True},  # optional + nullable
                },
            }
        }
    },
}


def _widget() -> IRModel:
    ir = build_ir(_SPEC_30, RefResolver(_SPEC_30))
    decl = next(d for d in ir.declarations if d.name == "Widget")
    assert isinstance(decl, IRModel)
    return decl


def test_nullable_keyword_makes_optional() -> None:
    fields = {f.name: f for f in _widget().fields}
    # required + nullable -> optional type but still required (no default)
    assert isinstance(fields["code"].type, OptionalType)
    assert fields["code"].required is True
    assert fields["code"].has_default is False
    # optional + nullable
    assert isinstance(fields["label"].type, OptionalType)


def test_boolean_exclusive_minimum_normalized() -> None:
    score = next(f for f in _widget().fields if f.name == "score")
    # 3.0 `exclusiveMinimum: true` + `minimum: 1` -> numeric exclusive bound, no `minimum`
    assert score.constraints.get("exclusiveMinimum") == 1
    assert "minimum" not in score.constraints


def test_pydantic_renders_gt_from_boolean_exclusive() -> None:
    ir = build_ir(_SPEC_30, RefResolver(_SPEC_30))
    source = format_python(render_models_module(ir, get_strategy(Serializer.PYDANTIC)))
    assert "gt=1" in source
    assert "gt=True" not in source


def test_generates_and_imports_from_30_spec(tmp_path: Path) -> None:
    out = tmp_path / "out"
    package = "legacy_client"
    run_generation(
        # write spec to a JSON file so the loader path is exercised
        str(_write_spec(tmp_path)),
        GeneratorConfig(
            package_name=package,
            output_dir=out,
            serializer=Serializer.ADAPTIX,
            client=ClientKind.SYNC,
        ),
    )
    ruff = shutil.which("ruff")
    assert ruff is not None
    result = subprocess.run(
        [ruff, "check", "--isolated", str(out / package)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr

    sys.path.insert(0, str(out))
    try:
        for mod in [m for m in sys.modules if m == package or m.startswith(f"{package}.")]:
            del sys.modules[mod]
        pkg = importlib.import_module(package)
        assert callable(pkg.LegacyClient().get_widget)  # single tag -> flat client
    finally:
        sys.path.remove(str(out))
        for mod in [m for m in sys.modules if m == package or m.startswith(f"{package}.")]:
            del sys.modules[mod]


def _write_spec(tmp_path: Path) -> Path:
    import json

    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(_SPEC_30))
    return path
