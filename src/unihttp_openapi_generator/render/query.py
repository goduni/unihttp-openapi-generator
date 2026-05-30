"""Render ``_query.py``: middleware that expands deepObject query params.

OpenAPI's ``style: deepObject`` serializes an object query parameter as sibling
keys ``key[subkey]=value``. unihttp's serializers (adaptix/pydantic/msgspec) can
only control the *value* of a single query key, not emit sibling top-level keys.
So expansion happens at the request level: a middleware rewrites dict-valued
``request.query`` entries whose key is a known deepObject parameter into the
bracketed form, deleting the original key. This is backend-agnostic — it only
mutates the ``request.query`` dict.
"""

from __future__ import annotations

from unihttp_openapi_generator.ir.document import IRDocument
from unihttp_openapi_generator.ir.operations import ParamLocation
from unihttp_openapi_generator.ir.types import MappingType, OptionalType, RefType

_QUERY_MODULE = '''"""Generated deepObject query expansion. Do not edit by hand."""

from __future__ import annotations

from typing import Any

from unihttp.http import HTTPRequest, HTTPResponse
from unihttp.middlewares.base import AsyncHandler, AsyncMiddleware, Handler, Middleware


def _expand(query: dict[str, Any], keys: frozenset[str]) -> None:
    for key in keys & query.keys():
        value = query[key]
        if isinstance(value, dict):
            del query[key]
            for sub_key, sub_value in value.items():
                query[f"{key}[{sub_key}]"] = sub_value


class DeepObjectQuerySyncMiddleware(Middleware):
    def __init__(self, keys: frozenset[str]) -> None:
        self._keys = keys

    def handle(self, request: HTTPRequest, next_handler: Handler) -> HTTPResponse:
        _expand(request.query, self._keys)
        return next_handler(request)


class DeepObjectQueryAsyncMiddleware(AsyncMiddleware):
    def __init__(self, keys: frozenset[str]) -> None:
        self._keys = keys

    async def handle(self, request: HTTPRequest, next_handler: AsyncHandler) -> HTTPResponse:
        _expand(request.query, self._keys)
        return await next_handler(request)
'''


def _is_object_param(param_type: object) -> bool:
    inner = param_type.inner if isinstance(param_type, OptionalType) else param_type
    return isinstance(inner, (RefType, MappingType))


def deep_object_query_keys(doc: IRDocument) -> list[str]:
    """Wire-names of object-typed query params declared ``style: deepObject``."""
    keys: list[str] = []
    seen: set[str] = set()
    for op in doc.operations:
        for param in op.parameters:
            if (
                param.location is ParamLocation.QUERY
                and param.style == "deepObject"
                and _is_object_param(param.type)
                and param.wire_name not in seen
            ):
                seen.add(param.wire_name)
                keys.append(param.wire_name)
    return keys


def render_query_module() -> str:
    return _QUERY_MODULE
