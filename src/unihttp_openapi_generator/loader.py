"""Load and validate OpenAPI 3.1 specifications from a file or URL."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlparse

import httpx
import yaml

logger = logging.getLogger("unihttp_openapi_generator")


class SpecLoadError(Exception):
    """Raised when a spec cannot be read, parsed, or (in strict mode) validated."""


def _is_url(source: str) -> bool:
    return urlparse(source).scheme in ("http", "https")


def _read_text(source: str) -> str:
    if _is_url(source):
        try:
            response = httpx.get(source, follow_redirects=True, timeout=30.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SpecLoadError(f"failed to fetch spec from {source!r}: {exc}") from exc
        return response.text
    try:
        with open(source, encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        raise SpecLoadError(f"failed to read spec file {source!r}: {exc}") from exc


def parse_spec_text(text: str) -> dict[str, Any]:
    """Parse YAML or JSON spec text into a mapping (JSON is a subset of YAML)."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SpecLoadError(f"failed to parse spec as YAML/JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SpecLoadError(f"spec root must be a mapping, got {type(data).__name__}")
    return data


def validate_spec(spec: dict[str, Any], *, strict: bool) -> None:
    """Validate against the OpenAPI schema. In soft mode, log instead of raising."""
    from openapi_spec_validator import validate
    from openapi_spec_validator.validation.exceptions import OpenAPIValidationError

    try:
        validate(spec)
    except OpenAPIValidationError as exc:
        if strict:
            raise SpecLoadError(f"spec failed OpenAPI validation: {exc.message}") from exc
        logger.warning("spec failed OpenAPI validation (continuing): %s", exc.message)


def _warn_version(spec: dict[str, Any]) -> None:
    version = spec.get("openapi")
    if not isinstance(version, str) or not version.startswith(("3.0", "3.1")):
        logger.warning(
            "spec declares openapi=%r; only OpenAPI 3.0.x / 3.1.x are supported, "
            "results may be wrong",
            version,
        )


def load_spec(source: str, *, strict: bool = False) -> dict[str, Any]:
    """Read, parse and validate an OpenAPI 3.0/3.1 spec from a path or URL."""
    spec = parse_spec_text(_read_text(source))
    _warn_version(spec)
    validate_spec(spec, strict=strict)
    return spec


def dump_json(spec: dict[str, Any]) -> str:
    """Serialize a spec back to canonical JSON (used by tests/snapshots)."""
    return json.dumps(spec, indent=2, sort_keys=True)
