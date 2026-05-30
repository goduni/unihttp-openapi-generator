"""Behavioral test: the generated adaptix retort serializes requests correctly."""

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


def test_request_serialization(spec_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    package = "behave_client"
    run_generation(
        str(spec_file),
        GeneratorConfig(
            package_name=package,
            output_dir=out,
            serializer=Serializer.ADAPTIX,
            client=ClientKind.SYNC,
        ),
    )
    sys.path.insert(0, str(out))
    try:
        serialization = importlib.import_module(f"{package}._serialization")
        pets = importlib.import_module(f"{package}.methods.pets")
        dumped: dict[str, Any] = serialization.request_dumper.dump(
            pets.ListPets(x_request_id="r1", limit=5, tags=["a", "b"])
        )
        # header param alias applied
        assert dumped["header"]["X-Request-ID"] == "r1"
        # explode=false array joined into a comma string
        assert dumped["query"]["tags"] == "a,b"
        assert dumped["query"]["limit"] == 5

        # omitted optional params are dropped entirely
        dumped_omitted: dict[str, Any] = serialization.request_dumper.dump(
            pets.ListPets(x_request_id="r1")
        )
        assert "limit" not in dumped_omitted.get("query", {})
    finally:
        sys.path.remove(str(out))
        for mod in list(sys.modules):
            if mod == package or mod.startswith(f"{package}."):
                del sys.modules[mod]


def test_json_object_body_is_spread_into_flat_aliased_body(tmp_path: Path) -> None:
    # A JSON object request body must serialize as the object itself (flat), not
    # wrapped under a "body" key. unihttp's Body marker keys each body field into
    # the JSON body, so the generator spreads the object's properties into
    # individual Body fields, with camelCase wire names aliased (adaptix).
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {
            "/widgets": {
                "post": {
                    "operationId": "createWidget",
                    "tags": ["widgets"],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["name"],
                                    "properties": {
                                        "name": {"type": "string"},
                                        "fooBar": {"type": "integer"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"201": {"description": "ok"}},
                }
            }
        },
    }
    out = tmp_path / "out"
    package = "widget_client"
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec))
    run_generation(
        str(spec_path),
        GeneratorConfig(
            package_name=package,
            output_dir=out,
            serializer=Serializer.ADAPTIX,
            client=ClientKind.SYNC,
        ),
    )
    sys.path.insert(0, str(out))
    try:
        serialization = importlib.import_module(f"{package}._serialization")
        methods = importlib.import_module(f"{package}.methods.widgets")
        method = methods.CreateWidget(name="gizmo", foo_bar=5)
        request = method.build_http_request(request_dumper=serialization.request_dumper)
        # flat body — NOT {"body": {...}} — with the camelCase wire name aliased
        assert request.body == {"name": "gizmo", "fooBar": 5}
    finally:
        sys.path.remove(str(out))
        for mod in list(sys.modules):
            if mod == package or mod.startswith(f"{package}."):
                del sys.modules[mod]
