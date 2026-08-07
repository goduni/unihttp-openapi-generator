"""Tests for ``client.pyi`` rendering (``--stubs``)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from unihttp_openapi_generator.config import ClientKind, GeneratorConfig, Layout
from unihttp_openapi_generator.ir.builder import build_ir
from unihttp_openapi_generator.refs import RefResolver
from unihttp_openapi_generator.render.clients import render_client_module
from unihttp_openapi_generator.render.stubs import render_client_stub


def _config(**kwargs: Any) -> GeneratorConfig:
    base: dict[str, Any] = {"package_name": "pkg", "output_dir": Path("out"), "stubs": True}
    base.update(kwargs)
    return GeneratorConfig(**base)


def _render(spec: dict[str, Any], **config_kwargs: Any) -> str:
    doc = build_ir(spec, RefResolver(spec))
    return render_client_stub(doc, _config(**config_kwargs), "pkg")


_PET: dict[str, Any] = {
    "type": "object",
    "properties": {"id": {"type": "string"}},
    "required": ["id"],
}

_SPEC: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "Sample", "version": "1.0.0"},
    "servers": [{"url": "https://api.example.com/v1"}],
    "paths": {
        "/pets/{petId}": {
            "get": {
                "operationId": "getPet",
                "tags": ["pets"],
                "summary": "Fetch one pet",
                "parameters": [
                    {
                        "name": "petId",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    },
                    {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 10}},
                    {"name": "q", "in": "query", "schema": {"type": "string"}},
                ],
                "responses": {
                    "200": {
                        "description": "ok",
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Pet"}}
                        },
                    }
                },
            }
        }
    },
    "components": {"schemas": {"Pet": _PET}},
}


def test_operation_becomes_an_explicit_def() -> None:
    out = _render(_SPEC, client=ClientKind.SYNC)
    assert (
        "def get_pet(self, *, pet_id: str, limit: int = 10, q: Omittable[str] = Omitted()) -> Pet:"
        in out
    )


def test_stub_does_not_bind_methods() -> None:
    out = _render(_SPEC, client=ClientKind.SYNC)
    assert "bind_method" not in out


def test_stub_carries_the_operation_docstring() -> None:
    out = _render(_SPEC, client=ClientKind.SYNC)
    assert '"""Fetch one pet"""' in out


def test_stub_declares_module_level_names_without_values() -> None:
    out = _render(_SPEC, client=ClientKind.SYNC)
    assert "SERVERS: dict[str, str]\n" in out
    assert "DEFAULT_BASE_URL: str\n" in out
    assert "SERVERS: dict[str, str] = {" not in out


def test_stub_has_no_future_import() -> None:
    # Stub files are never evaluated; forward references are implicitly lazy.
    out = _render(_SPEC, client=ClientKind.SYNC)
    assert "from __future__ import annotations" not in out


def test_stub_init_mirrors_the_runtime_signature() -> None:
    out = _render(_SPEC, client=ClientKind.SYNC)
    assert (
        "def __init__(self, base_url: str = DEFAULT_BASE_URL, *, session: Any = None, "
        "middleware: list[Any] | None = None) -> None: ..." in out
    )


def test_sync_client_subclasses_the_configured_backend() -> None:
    out = _render(_SPEC, client=ClientKind.SYNC)
    assert "class SampleClient(RequestsSyncClient):" in out
    assert "from unihttp.clients.requests import RequestsSyncClient" in out


def test_async_operations_are_coroutines() -> None:
    out = _render(_SPEC, client=ClientKind.ASYNC)
    assert "class AsyncSampleClient(AiohttpAsyncClient):" in out
    assert "async def get_pet(self, *, pet_id: str" in out


def test_both_kinds_emit_both_clients() -> None:
    out = _render(_SPEC, client=ClientKind.BOTH)
    assert "class SampleClient(RequestsSyncClient):" in out
    assert "class AsyncSampleClient(AiohttpAsyncClient):" in out


def test_grouped_layout_emits_subclients_bound_by_annotation() -> None:
    out = _render(_SPEC, client=ClientKind.SYNC, layout=Layout.GROUPED)
    assert "class PetsClient:" in out
    assert "    def __init__(self, root: Any) -> None: ..." in out
    assert "def call_method(self, method: BaseMethod[ResponseType]) -> ResponseType: ..." in out
    assert "    pets: PetsClient\n" in out


def test_grouped_async_subclient_is_awaitable() -> None:
    out = _render(_SPEC, client=ClientKind.ASYNC, layout=Layout.GROUPED)
    assert "class AsyncPetsClient:" in out
    assert (
        "async def call_method(self, method: BaseMethod[ResponseType]) -> ResponseType: ..." in out
    )
    assert "    pets: AsyncPetsClient\n" in out


_AUTH_SPEC: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "Auth", "version": "1.0.0"},
    "components": {
        "securitySchemes": {
            "apiKey": {"type": "apiKey", "in": "header", "name": "X-Key"},
        }
    },
    "security": [{"apiKey": []}],
    "paths": {
        "/x": {
            "get": {
                "operationId": "getX",
                "tags": ["x"],
                "responses": {"200": {"description": "ok"}},
            }
        }
    },
}


def test_auth_credentials_reach_the_stub_init() -> None:
    out = _render(_AUTH_SPEC, client=ClientKind.SYNC)
    assert "api_key: str | None = None" in out


_NO_PARAM_SPEC: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "Bare", "version": "1.0.0"},
    "paths": {
        "/ping": {
            "get": {
                "operationId": "ping",
                "tags": ["ops"],
                "responses": {"204": {"description": "no content"}},
            }
        }
    },
}


def test_parameterless_operation_renders_without_a_keyword_marker() -> None:
    out = _render(_NO_PARAM_SPEC, client=ClientKind.SYNC)
    assert "def ping(self) -> None:" in out
    # No servers in this spec, so neither module-level constant is declared.
    assert "DEFAULT_BASE_URL" not in out
    assert 'base_url: str = ""' in out


_COLLIDING_SPEC: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "Collide", "version": "1.0.0"},
    "paths": {
        "/a": {
            "get": {
                "operationId": "get_thing",
                "tags": ["a"],
                "responses": {"200": {"description": "ok"}},
            }
        },
        "/b": {
            "get": {
                "operationId": "getThing",
                "tags": ["b"],
                "responses": {"200": {"description": "ok"}},
            }
        },
    },
}


def test_flat_stub_attribute_names_match_the_runtime_client() -> None:
    # Whatever the runtime client ends up calling each operation -- including any
    # de-duplication of colliding names -- the stub must call it the same thing, or
    # the attribute simply does not exist as far as a type checker is concerned.
    config = _config(client=ClientKind.SYNC, layout=Layout.FLAT)
    doc = build_ir(_COLLIDING_SPEC, RefResolver(_COLLIDING_SPEC))
    runtime = render_client_module(doc, config, "pkg")
    out = render_client_stub(doc, config, "pkg")

    bound = re.findall(r"^    (\w+) = bind_method\(", runtime, re.MULTILINE)
    assert len(bound) == 2 and len(set(bound)) == 2
    for attr in bound:
        assert f"def {attr}(self)" in out


_DEPRECATED_SPEC: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "Old", "version": "1.0.0"},
    "paths": {
        "/legacy": {
            "get": {
                "operationId": "getLegacy",
                "tags": ["legacy"],
                "deprecated": True,
                "responses": {"200": {"description": "ok"}},
            }
        }
    },
}


def test_deprecated_operation_is_marked_in_the_stub_docstring() -> None:
    out = _render(_DEPRECATED_SPEC, client=ClientKind.SYNC)
    assert '"""Deprecated."""' in out
