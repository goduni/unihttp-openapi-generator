"""Jinja2 environment for rendering generated modules."""

from __future__ import annotations

from typing import Any

from jinja2 import Environment, PackageLoader, StrictUndefined


def _build_environment() -> Environment:
    env = Environment(
        loader=PackageLoader("unihttp_openapi_generator.render", "templates"),
        autoescape=False,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    return env


_ENV = _build_environment()


def render_template(name: str, /, **context: Any) -> str:
    return _ENV.get_template(name).render(**context)
