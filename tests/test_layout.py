"""Tests for client layout (flat vs grouped)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from unihttp_openapi_generator.config import ClientKind, GeneratorConfig, Layout
from unihttp_openapi_generator.ir.builder import build_ir
from unihttp_openapi_generator.refs import RefResolver
from unihttp_openapi_generator.render.clients import render_client_module


def _config(layout: Layout) -> GeneratorConfig:
    return GeneratorConfig(
        package_name="acme",
        output_dir=Path("/tmp/x"),
        client=ClientKind.BOTH,
        layout=layout,
    )


def test_resolve_layout() -> None:
    assert _config(Layout.AUTO).resolve_layout(0) is Layout.FLAT
    assert _config(Layout.AUTO).resolve_layout(1) is Layout.FLAT
    assert _config(Layout.AUTO).resolve_layout(3) is Layout.GROUPED
    assert _config(Layout.FLAT).resolve_layout(5) is Layout.FLAT
    assert _config(Layout.GROUPED).resolve_layout(1) is Layout.GROUPED


def test_flat_layout_puts_methods_on_root(sample_spec: dict[str, Any]) -> None:
    ir = build_ir(sample_spec, RefResolver(sample_spec))
    code = render_client_module(ir, _config(Layout.FLAT), "acme")
    assert "list_pets = bind_method(ListPets)" in code
    assert "create_pet = bind_method(CreatePet)" in code
    assert "Client" in code
    assert "PetsClient" not in code  # no sub-clients in flat layout


def test_grouped_layout_creates_subclients(sample_spec: dict[str, Any]) -> None:
    ir = build_ir(sample_spec, RefResolver(sample_spec))
    code = render_client_module(ir, _config(Layout.GROUPED), "acme")
    assert "class PetsClient:" in code
    assert "self.pets = PetsClient(self)" in code
    assert "class AsyncPetsClient:" in code
