"""Coverage for client-module rendering branches: imperative param defaults,
grouped imperative sub-clients, async deepObject middleware and basic-auth base64."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from unihttp_openapi_generator.config import (
    ClientKind,
    GeneratorConfig,
    Layout,
    MethodStyle,
)
from unihttp_openapi_generator.ir.builder import build_ir
from unihttp_openapi_generator.refs import RefResolver
from unihttp_openapi_generator.render.clients import render_client_module


def _config(**kwargs: Any) -> GeneratorConfig:
    base: dict[str, Any] = {"package_name": "pkg", "output_dir": Path("out")}
    base.update(kwargs)
    return GeneratorConfig(**base)


def _render(spec: dict[str, Any], **config_kwargs: Any) -> str:
    doc = build_ir(spec, RefResolver(spec))
    return render_client_module(doc, _config(**config_kwargs), "pkg")


_DEFAULTS_SPEC: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "Defaults", "version": "1.0.0"},
    "paths": {
        "/x": {
            "get": {
                "operationId": "getX",
                "tags": ["x"],
                "parameters": [
                    {
                        "name": "tags",
                        "in": "query",
                        "schema": {"type": "array", "items": {"type": "string"}, "default": ["a"]},
                    },
                    {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 10}},
                    {"name": "opt", "in": "query", "schema": {"type": "string"}},
                ],
                "responses": {"200": {"description": "ok"}},
            }
        }
    },
}


def test_imperative_grouped_param_defaults() -> None:
    # grouped layout exercises the imperative sub-client renderer; the params cover
    # the factory-default, scalar-default and no-default imperative branches.
    out = _render(
        _DEFAULTS_SPEC,
        style=MethodStyle.IMPERATIVE,
        layout=Layout.GROUPED,
        client=ClientKind.SYNC,
    )
    assert "tags: Omittable[list[str]] = Omitted()" in out  # mutable default -> Omittable
    assert "limit: int = 10" in out  # scalar default rendered inline
    assert "opt: Omittable[str] = Omitted()" in out  # optional-without-default
    assert "class XClient:" in out  # the per-tag sub-client


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
                    }
                ],
                "responses": {"200": {"description": "ok"}},
            }
        }
    },
    "components": {
        "schemas": {"Filter": {"type": "object", "properties": {"a": {"type": "integer"}}}}
    },
}


def test_async_deep_object_middleware_import() -> None:
    out = _render(_DEEP_SPEC, client=ClientKind.ASYNC)
    assert "DeepObjectQueryAsyncMiddleware" in out


_BASIC_AUTH_SPEC: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "Secure", "version": "1.0.0"},
    "paths": {
        "/x": {
            "get": {
                "operationId": "getX",
                "tags": ["x"],
                "responses": {"200": {"description": "ok"}},
            }
        }
    },
    "components": {"securitySchemes": {"basic": {"type": "http", "scheme": "basic"}}},
}


def test_basic_auth_prepends_base64_import() -> None:
    out = _render(_BASIC_AUTH_SPEC, client=ClientKind.SYNC)
    assert "import base64\n" in out
