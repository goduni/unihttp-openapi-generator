"""Tests for GeneratorConfig."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from unihttp_openapi_generator.config import (
    ClientKind,
    GeneratorConfig,
    MethodStyle,
    Serializer,
)


def _config(**overrides: object) -> GeneratorConfig:
    base: dict[str, object] = {"package_name": "acme_client", "output_dir": Path("/tmp/out")}
    base.update(overrides)
    return GeneratorConfig(**base)  # type: ignore[arg-type]


def test_defaults() -> None:
    cfg = _config()
    assert cfg.serializer is Serializer.ADAPTIX
    assert cfg.client is ClientKind.BOTH
    assert cfg.style.value == "declarative"
    assert cfg.check is False
    assert cfg.stubs is False


def test_rejects_stubs_with_imperative_style() -> None:
    # Imperative clients already spell every signature out in ``client.py``; a stub
    # would duplicate them and could drift from them.
    with pytest.raises(ValidationError, match="imperative"):
        _config(stubs=True, style=MethodStyle.IMPERATIVE)


def test_rejects_invalid_package_name() -> None:
    with pytest.raises(ValidationError):
        _config(package_name="not-a-valid-name")


@pytest.mark.parametrize(
    ("kind", "sync", "async_"),
    [
        (ClientKind.BOTH, True, True),
        (ClientKind.SYNC, True, False),
        (ClientKind.ASYNC, False, True),
    ],
)
def test_emit_flags(kind: ClientKind, sync: bool, async_: bool) -> None:
    cfg = _config(client=kind)
    assert cfg.emit_sync is sync
    assert cfg.emit_async is async_
