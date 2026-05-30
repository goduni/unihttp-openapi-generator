"""Coverage for the $ref resolver's pointer/URI edge paths."""

from __future__ import annotations

from typing import Any, cast

import pytest

from unihttp_openapi_generator.refs import RefError, RefResolver

_DOC: dict[str, Any] = {
    "root_scalar": "X",
    "list": [{"a": 1}, {"b": 2}],
    "components": {"schemas": {"User": {"type": "object"}}},
}


def test_resolve_whole_document() -> None:
    r = RefResolver(_DOC)
    resolved = r.resolve_ref("#")
    assert resolved.value == _DOC


def test_missing_pointer_segment_raises() -> None:
    r = RefResolver(_DOC)
    with pytest.raises(RefError, match="not found"):
        r.resolve_ref("#/components/schemas/Missing")


def test_resolve_through_list_index() -> None:
    r = RefResolver(_DOC)
    assert r.resolve_ref("#/list/0").value == {"a": 1}


def test_bad_list_index_raises() -> None:
    r = RefResolver(_DOC)
    with pytest.raises(RefError, match="bad list index"):
        r.resolve_ref("#/list/notanindex")


def test_traverse_non_container_raises() -> None:
    r = RefResolver(_DOC)
    with pytest.raises(RefError, match="non-container"):
        r.resolve_ref("#/root_scalar/whatever")


def test_non_string_ref_raises() -> None:
    r = RefResolver(_DOC)
    with pytest.raises(RefError, match="expected a \\$ref string"):
        r.resolve_ref(cast(str, 123))


def test_absolute_url_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    r = RefResolver({"openapi": "3.1.0"})
    # pre-seed the external document so no network access is attempted
    r._docs["http://ex/common.yaml"] = {"Foo": {"type": "object"}}
    resolved = r.resolve_ref("http://ex/common.yaml#/Foo")
    assert resolved.value == {"type": "object"}
    assert resolved.base_uri == "http://ex/common.yaml"


def test_relative_ref_against_url_base() -> None:
    r = RefResolver({"openapi": "3.1.0"}, root_uri="http://ex/dir/root.yaml")
    r._docs["http://ex/dir/common.yaml"] = {"Foo": {"type": "object"}}
    resolved = r.resolve_ref("common.yaml#/Foo")
    assert resolved.base_uri == "http://ex/dir/common.yaml"
