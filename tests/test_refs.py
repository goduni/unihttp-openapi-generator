"""Tests for the $ref resolver."""

from __future__ import annotations

from pathlib import Path

import pytest

from unihttp_openapi_generator.refs import CircularRefError, RefResolver

_ROOT = {
    "components": {
        "schemas": {
            "User": {"type": "object", "properties": {"id": {"type": "integer"}}},
            "Alias": {"$ref": "#/components/schemas/User"},
            "Loop": {"$ref": "#/components/schemas/Loop"},
            "Weird~Key/Name": {"type": "string"},
        }
    }
}


def test_resolves_internal_ref() -> None:
    r = RefResolver(_ROOT)
    resolved = r.resolve_ref("#/components/schemas/User")
    assert resolved.value["type"] == "object"
    assert resolved.name == "User"


def test_follows_ref_chain() -> None:
    r = RefResolver(_ROOT)
    resolved = r.resolve_ref("#/components/schemas/Alias")
    assert resolved.value["type"] == "object"
    # The terminal node is User, so that is the canonical name.
    assert resolved.name == "User"


def test_detects_cycle() -> None:
    r = RefResolver(_ROOT)
    with pytest.raises(CircularRefError):
        r.resolve_ref("#/components/schemas/Loop")


def test_json_pointer_escaping() -> None:
    r = RefResolver(_ROOT)
    resolved = r.resolve_ref("#/components/schemas/Weird~0Key~1Name")
    assert resolved.value == {"type": "string"}


def test_unnamed_pointer_has_no_name() -> None:
    r = RefResolver(_ROOT)
    resolved = r.resolve_ref("#/components/schemas/User/properties/id")
    assert resolved.value == {"type": "integer"}
    assert resolved.name is None


def test_resolves_external_file_ref(tmp_path: Path) -> None:
    (tmp_path / "common.yaml").write_text(
        "components:\n  schemas:\n    Error:\n      type: object\n"
    )
    root_path = tmp_path / "root.yaml"
    root_path.write_text("openapi: 3.1.0\n")
    r = RefResolver({"openapi": "3.1.0"}, root_uri=str(root_path))
    resolved = r.resolve_ref("common.yaml#/components/schemas/Error")
    assert resolved.value == {"type": "object"}
    assert resolved.name == "Error"
    assert resolved.base_uri.endswith("common.yaml")
