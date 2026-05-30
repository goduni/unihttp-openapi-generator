"""Render ``auth.py``: generic credential-injecting middlewares + client wiring helpers.

Four generic middlewares (sync/async × header/query) cover every security scheme;
the root client builds the right one from constructor credentials.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from unihttp_openapi_generator.ir.document import IRDocument
from unihttp_openapi_generator.ir.naming import field_name

_AUTH_MODULE = '''"""Generated authentication middlewares. Do not edit by hand."""

from __future__ import annotations

from unihttp.http import HTTPRequest, HTTPResponse
from unihttp.middlewares.base import AsyncHandler, AsyncMiddleware, Handler, Middleware


class HeaderAuthSyncMiddleware(Middleware):
    def __init__(self, name: str, value: str) -> None:
        self._name = name
        self._value = value

    def handle(self, request: HTTPRequest, next_handler: Handler) -> HTTPResponse:
        request.header[self._name] = self._value
        return next_handler(request)


class HeaderAuthAsyncMiddleware(AsyncMiddleware):
    def __init__(self, name: str, value: str) -> None:
        self._name = name
        self._value = value

    async def handle(self, request: HTTPRequest, next_handler: AsyncHandler) -> HTTPResponse:
        request.header[self._name] = self._value
        return await next_handler(request)


class QueryAuthSyncMiddleware(Middleware):
    def __init__(self, name: str, value: str) -> None:
        self._name = name
        self._value = value

    def handle(self, request: HTTPRequest, next_handler: Handler) -> HTTPResponse:
        request.query[self._name] = self._value
        return next_handler(request)


class QueryAuthAsyncMiddleware(AsyncMiddleware):
    def __init__(self, name: str, value: str) -> None:
        self._name = name
        self._value = value

    async def handle(self, request: HTTPRequest, next_handler: AsyncHandler) -> HTTPResponse:
        request.query[self._name] = self._value
        return await next_handler(request)
'''


@dataclass(frozen=True)
class AuthCredential:
    """A constructor credential and how to turn it into a middleware."""

    param_name: str
    py_type: str  # "str | None" or "tuple[str, str] | None"
    transport: str  # "header" or "query"
    target: str  # header/query name
    value_expr: str  # python expr producing the injected value from the param


def render_auth_module() -> str:
    return _AUTH_MODULE


def _is_bearer_like(scheme: Any) -> bool:
    if scheme.kind in ("oauth2", "openIdConnect"):
        return True
    return scheme.kind == "http" and (scheme.scheme or "").lower() == "bearer"


def iter_auth_credentials(doc: IRDocument) -> list[AuthCredential]:
    # Bearer-like schemes (http-bearer / oauth2 / openIdConnect) take a friendlier
    # ``token`` constructor param. If several would collide, fall back to
    # ``<scheme>_token`` for all of them.
    bearer_names = [s.name for s in doc.security_schemes.values() if _is_bearer_like(s)]
    collide = len(bearer_names) > 1

    creds: list[AuthCredential] = []
    for scheme in doc.security_schemes.values():
        param = field_name(scheme.name)
        if scheme.kind == "apiKey" and scheme.parameter_name:
            transport = "query" if scheme.location == "query" else "header"
            creds.append(
                AuthCredential(param, "str | None", transport, scheme.parameter_name, param)
            )
        elif scheme.kind == "http" and (scheme.scheme or "").lower() == "basic":
            value = f'"Basic " + base64.b64encode(":".join({param}).encode()).decode()'
            creds.append(
                AuthCredential(param, "tuple[str, str] | None", "header", "Authorization", value)
            )
        elif _is_bearer_like(scheme):
            token_param = f"{param}_token" if collide else "token"
            creds.append(
                AuthCredential(
                    token_param,
                    "str | None",
                    "header",
                    "Authorization",
                    f'f"Bearer {{{token_param}}}"',
                )
            )
    return creds


def needs_base64(creds: list[AuthCredential]) -> bool:
    return any("base64" in c.value_expr for c in creds)
