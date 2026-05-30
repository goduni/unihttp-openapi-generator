"""Tests for exception and auth rendering."""

from __future__ import annotations

from typing import Any

from unihttp_openapi_generator.ir.builder import build_ir
from unihttp_openapi_generator.refs import RefResolver
from unihttp_openapi_generator.render.auth import iter_auth_credentials, render_auth_module
from unihttp_openapi_generator.render.exceptions import (
    collect_error_statuses,
    render_exceptions_module,
    status_exception_name,
)

_ERR_SPEC: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "Err", "version": "1.0.0"},
    "paths": {
        "/x": {
            "get": {
                "operationId": "getX",
                "tags": ["x"],
                "responses": {
                    "200": {"description": "ok"},
                    "404": {"description": "missing"},
                    "422": {"description": "bad"},
                    "500": {"description": "boom"},
                },
            }
        }
    },
    "components": {
        "securitySchemes": {
            "apiKey": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
            "oauth": {"type": "oauth2", "flows": {}},
            "basic": {"type": "http", "scheme": "basic"},
        }
    },
}


def _ir() -> Any:
    return build_ir(_ERR_SPEC, RefResolver(_ERR_SPEC))


def test_collect_error_statuses() -> None:
    assert collect_error_statuses(_ir()) == [404, 422, 500]


def test_status_exception_names() -> None:
    assert status_exception_name(404) == "NotFoundError"
    assert status_exception_name(422) == "UnprocessableEntityError"
    assert status_exception_name(599) == "Status599Error"


def test_exceptions_module_content() -> None:
    code = render_exceptions_module(_ir())
    assert "class ApiError(HTTPStatusError):" in code
    assert "class NotFoundError(ApiError):" in code
    assert "404: NotFoundError," in code
    assert "range(500, 600): ServerError," in code
    compile(code, "exceptions.py", "exec")


def test_auth_credentials() -> None:
    creds = {c.param_name: c for c in iter_auth_credentials(_ir())}
    assert creds["api_key"].transport == "header"
    assert creds["api_key"].target == "X-API-Key"
    # single bearer-like scheme (oauth2) gets the friendly ``token`` param name
    assert creds["token"].value_expr == 'f"Bearer {token}"'
    assert creds["basic"].py_type == "tuple[str, str] | None"
    assert "base64" in creds["basic"].value_expr


def test_auth_module_compiles() -> None:
    compile(render_auth_module(), "auth.py", "exec")


def test_bearer_param_named_token() -> None:
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {},
        "components": {
            "securitySchemes": {
                "MyBearer": {"type": "http", "scheme": "bearer"},
            }
        },
    }
    creds = iter_auth_credentials(build_ir(spec, RefResolver(spec)))
    assert creds[0].param_name == "token"
    assert creds[0].value_expr == 'f"Bearer {token}"'


def test_multiple_bearer_schemes_use_suffixed_token() -> None:
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {},
        "components": {
            "securitySchemes": {
                "oauth": {"type": "oauth2", "flows": {}},
                "oidc": {"type": "openIdConnect", "openIdConnectUrl": "https://x/.well-known"},
            }
        },
    }
    creds = {c.param_name: c for c in iter_auth_credentials(build_ir(spec, RefResolver(spec)))}
    assert "oauth_token" in creds
    assert "oidc_token" in creds
